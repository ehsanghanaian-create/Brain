"""WordPress -> SQLite sync (read-only). Discovers post types & taxonomies dynamically."""
from __future__ import annotations

import logging
import re
import sqlite3
from html import unescape

from ..common.config import SiteConfig
from ..common.logging_setup import new_run_id
from ..database.db import ensure_site, j, upsert, utcnow
from ..normalizer import normalize_url
from .client import WordPressClient, WPError

log = logging.getLogger("wordpress.sync")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", unescape(text)).strip()


def word_count(text: str) -> int:
    return len([w for w in text.split() if w])


def sync_wordpress(conn: sqlite3.Connection, site: SiteConfig, use_auth: bool = True, progress=None) -> dict:
    """`progress(step, info)` (optional) is called as the sync moves through taxonomies → categories → pages/posts → media so a
    caller (the WordPress sync orchestrator) can report live progress; it never receives credentials."""
    def _p(step: str, **info):
        if progress:
            try: progress(step, info)
            except Exception: pass  # noqa: BLE001 — progress reporting must never break the sync
    run_id = new_run_id("wp")
    ensure_site(conn, site)
    conn.execute("INSERT INTO sync_runs(run_id, site_id, source, started_at, status) VALUES (?,?,?,?,?)",
                 (run_id, site.site_id, "wordpress", utcnow(), "running"))
    conn.commit()
    client = WordPressClient(site.wp_url, site.site_id, use_auth=use_auth)
    stats = {"run_id": run_id, "posts": 0, "types": {}, "taxonomies": {}, "media": 0, "errors": []}
    try:
        root = client.root()
        log.info(f"WP site: {root.get('name')} — {root.get('url')} (auth={'app-password' if client.authenticated else 'public'})")

        # taxonomies
        _p("taxonomies")
        taxes = client.content_taxonomies()
        for slug, t in taxes.items():
            upsert(conn, "taxonomies", {
                "site_id": site.site_id, "slug": slug, "name": t.get("name"), "rest_base": t.get("rest_base"),
                "hierarchical": 1 if t.get("hierarchical") else 0, "object_types": j(t.get("types")),
            }, ["site_id", "slug"])
            table = "categories" if t.get("hierarchical") else "tags"
            _p("categories" if slug == "category" else "taxonomies", taxonomy=slug)
            n = 0
            try:
                for term in client.fetch_all(t["rest_base"], {"hide_empty": "false"}):
                    row = {
                        "site_id": site.site_id, "taxonomy": slug, "wp_id": term["id"], "name": unescape(term.get("name") or ""),
                        "slug": term.get("slug"), "url": normalize_url(term.get("link", ""), site_host=site.host),
                        "count": term.get("count", 0),
                    }
                    if table == "categories":
                        row["description"] = term.get("description")
                        row["parent_wp_id"] = term.get("parent", 0)
                    upsert(conn, table, row, ["site_id", "taxonomy", "wp_id"])
                    n += 1
            except WPError as e:
                stats["errors"].append(str(e))
                log.error(str(e))
            stats["taxonomies"][slug] = n

        # post types
        types = client.public_content_types()
        for slug, t in types.items():
            n = 0
            _p("pages" if slug == "page" else "posts", post_type=slug)
            try:
                items = client.fetch_all(t["rest_base"], {"status": "publish", "_embed": "0"})
            except WPError as e:
                stats["errors"].append(str(e))
                log.error(str(e))
                continue
            for it in items:
                content_html = (it.get("content") or {}).get("rendered") or ""
                text = html_to_text(content_html)
                yo = it.get("yoast_head_json") or {}
                url = normalize_url(it.get("link", ""), site_host=site.host)
                upsert(conn, "posts", {
                    "site_id": site.site_id, "wp_id": it["id"], "type": it.get("type", slug), "url": url,
                    "slug": it.get("slug"), "title": unescape((it.get("title") or {}).get("rendered") or ""),
                    "content_html": content_html, "content_text": text,
                    "excerpt": html_to_text((it.get("excerpt") or {}).get("rendered")),
                    "status": it.get("status"), "date_gmt": it.get("date_gmt"), "modified_gmt": it.get("modified_gmt"),
                    "author_id": it.get("author"), "featured_media": it.get("featured_media"),
                    "parent_wp_id": it.get("parent", 0),
                    "yoast_title": yo.get("title"), "yoast_description": yo.get("description"),
                    "yoast_canonical": normalize_url(yo["canonical"], site_host=site.host) if yo.get("canonical") else None,
                    "yoast_robots": j(yo.get("robots")), "yoast_schema": j(yo.get("schema")),
                    "word_count": word_count(text),
                }, ["site_id", "type", "wp_id"])
                # term relationships: WP exposes taxonomy arrays keyed by rest_base (categories, tags, <custom>)
                for tax_slug, tdef in taxes.items():
                    key = tdef["rest_base"]
                    ids = it.get(key)
                    if isinstance(ids, list):
                        for tid in ids:
                            conn.execute(
                                "INSERT OR IGNORE INTO post_terms(site_id, post_type, post_wp_id, taxonomy, term_wp_id) VALUES (?,?,?,?,?)",
                                (site.site_id, it.get("type", slug), it["id"], tax_slug, tid))
                n += 1
            stats["types"][slug] = n
            stats["posts"] += n

        # media (alt text is SEO-relevant)
        _p("media")
        try:
            for m in client.fetch_all("media", {"_fields": "id,source_url,alt_text,title,mime_type,post"}):
                upsert(conn, "media", {
                    "site_id": site.site_id, "wp_id": m["id"], "source_url": m.get("source_url"),
                    "alt_text": m.get("alt_text"), "title": unescape((m.get("title") or {}).get("rendered") or ""),
                    "mime_type": m.get("mime_type"), "post_wp_id": m.get("post"),
                }, ["site_id", "wp_id"])
                stats["media"] += 1
        except WPError as e:
            stats["errors"].append(str(e))
            log.error(str(e))

        status = "completed" if not stats["errors"] else "completed_with_errors"
        conn.execute("UPDATE sync_runs SET finished_at=?, status=?, rows_written=?, notes=? WHERE run_id=?",
                     (utcnow(), status, stats["posts"], j(stats), run_id))
        conn.commit()
        log.info(f"WordPress sync {status}: {stats['posts']} content items, taxonomies={stats['taxonomies']}, media={stats['media']}")
        return stats
    except Exception as e:
        conn.execute("UPDATE sync_runs SET finished_at=?, status='failed', notes=? WHERE run_id=?", (utcnow(), str(e), run_id))
        conn.commit()
        raise
    finally:
        client.close()
