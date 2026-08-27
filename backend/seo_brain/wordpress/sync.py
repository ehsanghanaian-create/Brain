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


def _content_sort_key(row: dict) -> tuple[str, int, int]:
    """Choose one deterministic owner when WordPress publishes multiple objects at one URL."""
    modified = row.get("modified_gmt") or row.get("date_gmt") or ""
    # A page is the safer canonical owner when timestamps tie; wp_id makes the
    # result deterministic for malformed feeds with otherwise identical rows.
    type_priority = 2 if row.get("type") == "page" else 1
    return str(modified), type_priority, int(row.get("wp_id") or 0)


def _replace_post(conn: sqlite3.Connection, row: dict) -> None:
    """Persist the selected URL owner and remove stale identities/term relations."""
    key = (row["site_id"], row["type"], row["wp_id"])
    existing_key = conn.execute(
        "SELECT id, site_id, type, wp_id, url FROM posts WHERE site_id=? AND type=? AND wp_id=?", key
    ).fetchone()
    existing_url = conn.execute(
        "SELECT id, site_id, type, wp_id, url FROM posts WHERE site_id=? AND url=?",
        (row["site_id"], row["url"]),
    ).fetchone()

    # The URL identity is canonical throughout the crawler and graph. When an
    # old post and a replacement page share it, remove the losing cached object
    # before the regular WordPress-identity upsert.
    if existing_url and (existing_url["type"], existing_url["wp_id"]) != (row["type"], row["wp_id"]):
        conn.execute(
            "DELETE FROM post_terms WHERE site_id=? AND post_type=? AND post_wp_id=?",
            (row["site_id"], existing_url["type"], existing_url["wp_id"]),
        )
        conn.execute("DELETE FROM posts WHERE id=?", (existing_url["id"],))

    # A WordPress object may also have moved to a new URL. Its previous term
    # snapshot must be rebuilt instead of accumulating removed categories/tags.
    if existing_key:
        conn.execute(
            "DELETE FROM post_terms WHERE site_id=? AND post_type=? AND post_wp_id=?", key
        )
    upsert(conn, "posts", row, ["site_id", "type", "wp_id"])


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
    stats = {"run_id": run_id, "posts": 0, "types": {}, "taxonomies": {}, "media": 0,
             "duplicates": [], "errors": []}
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
        content_by_url: dict[str, tuple[dict, dict]] = {}
        for slug, t in types.items():
            stats["types"].setdefault(slug, 0)
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
                row = {
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
                }
                previous = content_by_url.get(url)
                if previous and (previous[0]["type"], previous[0]["wp_id"]) != (row["type"], row["wp_id"]):
                    winner, loser = (row, previous[0]) if _content_sort_key(row) > _content_sort_key(previous[0]) else (previous[0], row)
                    stats["duplicates"].append({
                        "url": url,
                        "kept": {"type": winner["type"], "wp_id": winner["wp_id"], "modified_gmt": winner.get("modified_gmt")},
                        "discarded": {"type": loser["type"], "wp_id": loser["wp_id"], "modified_gmt": loser.get("modified_gmt")},
                    })
                    log.warning("duplicate WordPress URL %s: keeping %s:%s, discarding %s:%s", url,
                                winner["type"], winner["wp_id"], loser["type"], loser["wp_id"])
                    if winner is row:
                        content_by_url[url] = (row, it)
                else:
                    content_by_url[url] = (row, it)

        # Persist only the deterministic URL owners. This keeps the posts table,
        # crawler and graph on the same one-URL/one-content identity model.
        for row, it in content_by_url.values():
            _replace_post(conn, row)
            for tax_slug, tdef in taxes.items():
                ids = it.get(tdef["rest_base"])
                if isinstance(ids, list):
                    for tid in ids:
                        conn.execute(
                            "INSERT OR IGNORE INTO post_terms(site_id, post_type, post_wp_id, taxonomy, term_wp_id) VALUES (?,?,?,?,?)",
                            (site.site_id, row["type"], row["wp_id"], tax_slug, tid))
            stats["types"].setdefault(row["type"], 0)
            stats["types"][row["type"]] += 1
        stats["posts"] = sum(stats["types"].values())

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
