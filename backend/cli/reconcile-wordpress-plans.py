"""Read-only preview by default; --apply imports live WordPress posts into Content Brain.

This command never writes to WordPress. It creates an online SQLite backup before
any SEO Brain write, and refuses unexpected plan counts.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import httpx

from seo_brain.brain.planner.wordpress_reconcile import action_counts, apply_actions, plan_actions
from seo_brain.common.config import PROJECT_ROOT
from seo_brain.common.urls import wp_rest_v2
from seo_brain.db.engine import get_engine
from seo_brain.wordpress.auth import resolve_auth
from sqlalchemy import text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expect-published", type=int)
    parser.add_argument("--expect-brief", type=int)
    parser.add_argument("--expect-linked-published", type=int)
    args = parser.parse_args()
    engine = get_engine()
    with engine.connect() as cx:
        row = cx.execute(text("SELECT wp_url FROM sites WHERE site_id=:s"), {"s": args.site}).first()
    if not row or not row[0]:
        raise SystemExit("WordPress URL missing")
    credentials = resolve_auth(args.site)
    if not credentials:
        raise SystemExit("WordPress Application Password missing")
    root = wp_rest_v2(row[0]).rstrip("/")
    with httpx.Client(auth=credentials.basic, headers={"User-Agent": "SEO-Brain-Writer/1.0"},
                      follow_redirects=True, timeout=35) as client:
        posts = []
        for page in range(1, 21):
            r = client.get(root + "/posts", params={"context": "edit", "per_page": 100, "page": page,
                                                        "_fields": "id,slug,status,link,modified_gmt"})
            if r.status_code != 200 or not isinstance(r.json(), list):
                raise RuntimeError(f"WordPress listing failed on page {page}: HTTP {r.status_code}")
            posts.extend(r.json())
            if page >= int(r.headers.get("x-wp-totalpages") or 1):
                break
        else:
            raise RuntimeError("WordPress listing exceeded the safety page limit")

        def full_post(post_id: int) -> dict:
            r = client.get(root + f"/posts/{post_id}", params={"context": "edit",
                "_fields": "id,slug,status,link,modified_gmt,title,content,excerpt"})
            if r.status_code != 200 or not isinstance(r.json(), dict):
                raise RuntimeError(f"WordPress post {post_id} could not be read: HTTP {r.status_code}")
            return r.json()

        actions = plan_actions(engine, args.site, posts, full_post)
    counts = action_counts(actions)
    print({"site": args.site, "wordpress_posts": len(posts), "actions": counts, "mode": "apply" if args.apply else "preview"})
    if not args.apply:
        return
    if any(value is None for value in (args.expect_published, args.expect_brief, args.expect_linked_published)):
        raise SystemExit("--apply requires all three expected counts")
    expected = {"published": args.expect_published, "brief": args.expect_brief,
                "linked_published": args.expect_linked_published}
    if any(counts.get(key) != value for key, value in expected.items()):
        raise RuntimeError(f"Preview counts changed: expected {expected}; found {counts}")
    db_path = Path(engine.url.database or "")
    if not db_path.is_file():
        raise RuntimeError("SQLite database path is unavailable")
    backup_dir = PROJECT_ROOT / "backups" / ("pre-plan-reconcile-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    backup_path = backup_dir / "seo.db"
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
        quick_check = target.execute("PRAGMA quick_check").fetchone()[0]
    backup_path.chmod(0o600)
    if quick_check != "ok":
        raise RuntimeError("Database backup failed quick_check")
    print({"backup": str(backup_path), "quick_check": quick_check})
    print({"applied": apply_actions(engine, args.site, actions, expected=expected)})


if __name__ == "__main__":
    main()
