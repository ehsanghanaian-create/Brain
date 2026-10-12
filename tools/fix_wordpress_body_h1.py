"""One-off, guarded repair for duplicate H1s in WordPress post bodies.

Run inside the SEO Brain backend container. Credentials are loaded from its
encrypted per-site SecretStore; they are never accepted as command arguments.
The script only touches posts currently flagged as multiple_h1, and only when
the live theme supplies exactly one H1 outside the post body.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import text

from seo_brain.db.engine import make_engine
from seo_brain.wordpress.auth import load_site_auth


SITES = {
    "emdadasanmotors": ("emdadasanmotors.com", "#re-title"),
    "modiranemdad": ("modiranemdad.com", ".page-header h1"),
    "hyundaemdad": ("hyundaemdad.com", ".elementor-widget-container > h1.elementor-heading-title"),
    "emdadkermanmotor": ("emdadkermanmotor.com", ".re-article-hero__body > h1"),
}
H1_OPEN = re.compile(r"<h1\b", re.IGNORECASE)
H1_CLOSE = re.compile(r"</h1\s*>", re.IGNORECASE)
EMPTY_H1 = re.compile(r"<h1\b[^>]*>\s*</h1\s*>", re.IGNORECASE | re.DOTALL)
HEADERS = {"User-Agent": "SEO-Brain/0.2 remediation-verifier"}


def transform_body_h1(raw: str) -> str:
    """Remove empty body H1s and demote meaningful ones without rewriting other HTML."""
    without_empty = EMPTY_H1.sub("", raw)
    return H1_CLOSE.sub("</h2>", H1_OPEN.sub("<h2", without_empty))


def path_key(url: str) -> str:
    return unquote(urlparse(url).path).rstrip("/").casefold()


def issue_urls(site_id: str) -> set[str]:
    with make_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT url FROM seo_problems WHERE site_id=:site AND problem_type='multiple_h1'"),
            {"site": site_id},
        )
        return {path_key(row[0]) for row in rows}


def all_posts(client: httpx.Client, domain: str) -> list[dict]:
    posts: list[dict] = []
    for page in range(1, 20):
        response = client.get(
            f"https://{domain}/wp-json/wp/v2/posts",
            params={"per_page": 100, "page": page, "_fields": "id,link"},
        )
        response.raise_for_status()
        batch = response.json()
        posts.extend(batch)
        if len(batch) < 100:
            break
    return posts


def live_h1(client: httpx.Client, url: str, template_selector: str) -> tuple[int, bool]:
    response = client.get(url, params={"seo_brain_verify": str(int(time.time()))})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    h1s = soup.find_all("h1")
    template = soup.select_one(template_selector)
    return len(h1s), bool(template and h1s and template is h1s[0])


def snapshot(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as output:
        output.write(json.dumps(data, ensure_ascii=False) + "\n")
        output.flush()
        os.fsync(output.fileno())


def run(site_id: str, apply: bool, limit: int | None) -> None:
    domain, selector = SITES[site_id]
    auth = load_site_auth(site_id)
    if not auth:
        raise SystemExit(f"{site_id}: per-site WordPress Application Password is not configured")

    with httpx.Client(timeout=35, follow_redirects=True, headers=HEADERS) as public, httpx.Client(
        timeout=35, follow_redirects=True, headers=HEADERS,
        auth=httpx.BasicAuth(auth.username, auth.app_password),
    ) as private:
        issues = issue_urls(site_id)
        posts = [post for post in all_posts(public, domain) if path_key(post["link"]) in issues]
        posts.sort(key=lambda post: post["id"])
        print(f"{site_id}: {len(issues)} issue URLs; {len(posts)} matching posts", flush=True)

        edited = skipped = failed = 0
        backup = Path(f"/app/data/h1-backups/{site_id}-{time.strftime('%Y%m%d')}.jsonl")
        for post in posts[:limit]:
            post_id, url = post["id"], post["link"]
            try:
                response = private.get(
                    f"https://{domain}/wp-json/wp/v2/posts/{post_id}",
                    params={"context": "edit", "_fields": "id,link,modified_gmt,content"},
                )
                response.raise_for_status()
                current = response.json()
                if current["id"] != post_id or path_key(current["link"]) != path_key(url):
                    raise ValueError("post identity changed")
                raw = current["content"]["raw"]
                rendered = current["content"]["rendered"]
                raw_open, raw_close = len(H1_OPEN.findall(raw)), len(H1_CLOSE.findall(raw))
                rendered_h1 = len(H1_OPEN.findall(rendered))
                count, template_first = live_h1(public, url, selector)
                if count == 1:
                    skipped += 1
                    continue
                if not template_first or raw_open < 1 or raw_open != raw_close or raw_open != rendered_h1 or count != rendered_h1 + 1:
                    raise ValueError(
                        f"unexpected heading ownership: live={count}, template={template_first}, "
                        f"raw={raw_open}/{raw_close}, rendered={rendered_h1}"
                    )
                updated = transform_body_h1(raw)
                if not apply:
                    print(f"PLAN {site_id} post={post_id} body_h1={raw_open}", flush=True)
                    continue

                snapshot(backup, {
                    "site_id": site_id, "post_id": post_id, "url": url,
                    "modified_gmt": current.get("modified_gmt"), "content_raw": raw,
                    "previous_h1": count, "saved_at": time.time(),
                })
                saved = private.post(
                    f"https://{domain}/wp-json/wp/v2/posts/{post_id}",
                    json={"content": updated},
                )
                saved.raise_for_status()
                if saved.json().get("id") != post_id:
                    raise ValueError("WordPress returned a different post ID")
                verified = False
                for _ in range(3):
                    count_after, template_after = live_h1(public, url, selector)
                    if count_after == 1 and template_after:
                        verified = True
                        break
                    time.sleep(2)
                if not verified:
                    raise ValueError(f"live verification failed: h1={count_after}")
                edited += 1
                print(f"DONE {site_id} post={post_id} body_h1={raw_open}", flush=True)
                time.sleep(0.3)
            except Exception as exc:
                failed += 1
                print(f"FAILED {site_id} post={post_id}: {type(exc).__name__}: {str(exc)[:180]}", flush=True)
                if failed >= 3:
                    print(f"HALTED {site_id}: three posts failed; inspect before retrying", flush=True)
                    break
        print(f"SUMMARY {site_id} edited={edited} skipped={skipped} failed={failed} backup={backup if apply else 'none'}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=tuple(SITES), required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    run(args.site, args.apply, args.limit)
