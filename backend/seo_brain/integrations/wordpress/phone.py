"""Change a site's phone number from inside Brain.

The number is stored in several places and several shapes. What Brain can reach through the WordPress REST API with the
site's Application Password is the content of posts and pages; the header/"call now" button usually lives in Elementor
data, in options, or hardcoded in a theme/mu-plugin file, and REST cannot write those. So this service:

  scan()    — where the number appears (Brain's synced copy + the live home page), per page and per shape
  replace() — rewrites every post/page it can reach (dry-run first), then re-scans and reports what is left

Writes go out through the WordPressWriter (the one module allowed to send outbound writes); whatever REST cannot reach
is returned as `remaining` together with the operator runbook, so the user always knows what still shows the old number.
"""
from __future__ import annotations

from typing import Any, Callable

import httpx
from sqlalchemy import Engine, text

from ...brain.ops.phone_change import digits, plan as runbook_plan, to_escaped, to_fa
from ...wordpress.auth import resolve_auth
from ...common.urls import wp_rest_v2
from .writer import WordPressWriter

MAX_PAGES = 300          # a phone number never legitimately appears in more than a few dozen posts
FIELDS = ("content_html", "title", "excerpt")
FIELD_FA = {"content_html": "متن صفحه", "title": "عنوان", "excerpt": "خلاصه"}
REST_FIELD = {"content_html": "content", "title": "title", "excerpt": "excerpt"}


def forms(phone: str) -> list[str]:
    """Every shape the eight-digit tail is written in: Latin/Persian × (no separator, space, dash) + escaped Persian."""
    tail = digits(phone)[-8:]
    fa = to_fa(tail)
    out = [tail, f"{tail[:4]} {tail[4:]}", f"{tail[:4]}-{tail[4:]}", fa, f"{fa[:4]} {fa[4:]}", f"{fa[:4]}-{fa[4:]}", to_escaped(tail)]
    return [f for i, f in enumerate(out) if f not in out[:i]]


def swap(textval: str, old: str, new: str) -> str:
    """Replace every shape of `old` with the matching shape of `new`, keeping separators and string length."""
    for o, n in zip(forms(old), forms(new)):
        textval = textval.replace(o, n)
    return textval



def _outside_main_content(html: str, shapes: list[str]) -> int:
    """Occurrences that live OUTSIDE the page's main content — the header, footer and widgets. Those come from the
    theme, an Elementor template or a plugin, so the REST content endpoints cannot rewrite them."""
    if not html:
        return 0
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for selector in ("main", "article", ".entry-content", ".site-content", ".elementor-widget-theme-post-content"):
            for el in soup.select(selector):
                el.decompose()
        rest = str(soup)
    except Exception:  # noqa: BLE001 — a broken page should not break the scan
        rest = html
    return sum(rest.count(s) for s in shapes)


class PhoneService:
    def __init__(self, engine: Engine, http: Callable[..., httpx.Response] | None = None):
        self.engine = engine
        self._http = http
        self.writer = WordPressWriter(engine, http)

    # ------------------------------------------------------------------ helpers
    def _site(self, site_id: str):
        with self.engine.connect() as cx:
            return cx.execute(text("SELECT wp_url, canonical_url, name FROM sites WHERE site_id=:s"), {"s": site_id}).first()

    def _fetch(self, url: str) -> str:
        """Read the live page. A site that is down, filtered or behind a WAF must not break the scan — the report then
        simply says the live page could not be read."""
        try:
            if self._http:
                r = self._http("GET", url, auth=None)
            else:
                from ...common.http import site_proxy
                r = httpx.get(url, timeout=25, follow_redirects=True, proxy=site_proxy(), headers={"User-Agent": "SEO-Brain/1.0"})
        except Exception:  # noqa: BLE001
            return ""
        return r.text if r.status_code == 200 else ""

    # ------------------------------------------------------------------ scan
    def scan(self, site_id: str, phone: str) -> dict[str, Any]:
        """Where does this number appear? Brain's synced copy tells which posts/pages; the live home page tells whether
        the header/footer (theme, Elementor or a plugin) still prints it — that part REST cannot rewrite."""
        site = self._site(site_id)
        if not site:
            raise KeyError(site_id)
        shapes = forms(phone)
        with self.engine.connect() as cx:
            rows = cx.execute(text("SELECT wp_id, type, url, title, content_html, excerpt FROM posts WHERE site_id=:s"), {"s": site_id}).all()
        pages: list[dict[str, Any]] = []
        for wp_id, ptype, url, title, content, excerpt in rows:
            hits = {}
            for field, value in (("content_html", content or ""), ("title", title or ""), ("excerpt", excerpt or "")):
                n = sum(value.count(s) for s in shapes)
                if n:
                    hits[field] = n
            if hits:
                pages.append({"wp_id": wp_id, "type": ptype, "url": url, "title": title, "hits": hits, "total": sum(hits.values())})
        pages.sort(key=lambda p: -p["total"])
        home = self._fetch((site[1] or site[0] or "").rstrip("/") + "/") if (site[0] or site[1]) else ""
        home_read = bool(home)
        in_home_html = sum(home.count(s) for s in shapes)
        template_hits = _outside_main_content(home, shapes)
        return {"site_id": site_id, "phone": phone, "forms": shapes, "pages": pages[:MAX_PAGES],
                "pages_total": len(pages), "occurrences": sum(p["total"] for p in pages),
                "template": {"home_html": in_home_html, "outside_content": template_hits, "home_read": home_read,
                             "note": ("شماره در قالب/هدر یا دیتای المنتور هم هست — این بخش از راه REST قابل نوشتن نیست"
                                      if template_hits else "در HTML صفحهٔ اصلی بیرون از متن صفحه‌ها چیزی پیدا نشد"
                                      if home_read else "صفحهٔ اصلی سایت خوانده نشد (سایت در دسترس نبود) — فقط نسخهٔ همگام‌شده بررسی شد")}}

    # ------------------------------------------------------------------ replace
    def replace(self, site_id: str, old_phone: str, new_phone: str, *, dry_run: bool = True, actor: str = "human",
                only_ids: list[int] | None = None) -> dict[str, Any]:
        site = self._site(site_id)
        if not site or not site[0]:
            return {"status": "not_configured", "message": "آدرس وردپرس این سایت تنظیم نشده است"}
        if len(digits(old_phone)[-8:]) != 8 or len(digits(new_phone)[-8:]) != 8:
            return {"status": "invalid", "message": "هر دو شماره باید دست‌کم هشت رقم داشته باشند"}
        if digits(old_phone)[-8:] == digits(new_phone)[-8:]:
            return {"status": "invalid", "message": "شمارهٔ قدیمی و جدید یکی است"}
        auth = resolve_auth(site_id)
        if not auth:
            return {"status": "credentials_missing", "message": "‏Application Password این سایت ذخیره نشده — در کارت وردپرس واردش کنید"}
        found = self.scan(site_id, old_phone)
        targets = [p for p in found["pages"] if not only_ids or p["wp_id"] in set(only_ids)]
        base = wp_rest_v2(site[0]).rstrip("/")
        results: list[dict[str, Any]] = []
        changed = 0
        for page in targets:
            rest_type = "pages" if page["type"] == "page" else "posts"
            item = {"wp_id": page["wp_id"], "url": page["url"], "title": page["title"], "hits": page["total"], "fields": sorted(page["hits"])}
            if dry_run:
                item["status"] = "would_change"
                results.append(item)
                continue
            try:
                r = self.writer.rest("GET", f"{base}/{rest_type}/{page['wp_id']}?context=edit", (auth.username, auth.app_password))
                if r.status_code != 200:
                    item.update(status="read_failed", message=f"HTTP {r.status_code}")
                    results.append(item)
                    continue
                current = r.json()
                payload: dict[str, Any] = {}
                for field in FIELDS:
                    if field not in page["hits"]:
                        continue
                    key = REST_FIELD[field]
                    raw = (current.get(key) or {}).get("raw") if isinstance(current.get(key), dict) else current.get(key)
                    if not isinstance(raw, str) or not raw:
                        continue
                    swapped = swap(raw, old_phone, new_phone)
                    if swapped != raw:
                        payload[key] = swapped
                if not payload:
                    item.update(status="nothing_in_rest", message="شماره در نسخهٔ قابل‌ویرایش این صفحه نبود (احتمالاً در دیتای المنتور است)")
                    results.append(item)
                    continue
                w = self.writer.rest("POST", f"{base}/{rest_type}/{page['wp_id']}", (auth.username, auth.app_password), json=payload)
                if w.status_code in (200, 201):
                    item.update(status="changed", fields_written=sorted(payload))
                    changed += 1
                else:
                    item.update(status="write_failed", message=f"HTTP {w.status_code}: {w.text[:120]}")
            except Exception as e:  # noqa: BLE001
                item.update(status="error", message=f"{e.__class__.__name__}")
            results.append(item)
        after = None if dry_run else self.scan(site_id, old_phone)
        book = runbook_plan(old_phone, new_phone, (site[1] or site[0] or "").replace("https://", "").replace("http://", "").strip("/"),
                            site_url=(site[1] or site[0] or ""))
        remaining = {"template_or_elementor": found["template"]["outside_content"],
                     "pages_left": (after or found)["pages_total"] - changed if not dry_run else None,
                     "note": "هرچه از راه REST قابل نوشتن نبود (هدر/المنتور/آپشن‌ها/فایل‌های قالب) با دستورالعمل زیر روی هاست انجام می‌شود"}
        return {"status": "preview" if dry_run else "applied", "site_id": site_id, "old_phone": old_phone, "new_phone": new_phone,
                "forms": found["forms"], "pages_found": len(found["pages"]), "pages_targeted": len(targets), "changed": changed,
                "results": results, "remaining": remaining, "runbook": book["runbook"],
                "next_step": "پس از اعمال، همگام‌سازی وردپرس را بزنید تا نسخهٔ داخل Brain هم تازه شود"}
