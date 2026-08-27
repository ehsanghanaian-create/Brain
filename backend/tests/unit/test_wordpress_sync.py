import sqlite3

from seo_brain.common.config import SiteConfig
from seo_brain.database.db import init_db
from seo_brain.wordpress.sync import sync_wordpress


class _DuplicateUrlWordPress:
    def __init__(self, *args, **kwargs):
        pass

    authenticated = False

    def root(self):
        return {"name": "Demo", "url": "https://demo.example"}

    def content_taxonomies(self):
        return {}

    def public_content_types(self):
        return {
            "post": {"rest_base": "posts"},
            "page": {"rest_base": "pages"},
        }

    def fetch_all(self, rest_base, params=None):
        if rest_base == "media":
            return []
        common = {
            "link": "https://demo.example/service/",
            "slug": "service",
            "content": {"rendered": "<p>content</p>"},
            "excerpt": {"rendered": ""},
            "status": "publish",
            "author": 1,
            "featured_media": 0,
            "parent": 0,
        }
        if rest_base == "posts":
            return [{**common, "id": 10, "type": "post", "title": {"rendered": "Old post"},
                     "date_gmt": "2025-01-01T00:00:00", "modified_gmt": "2026-07-30T00:00:00"}]
        if rest_base == "pages":
            return [{**common, "id": 20, "type": "page", "title": {"rendered": "Replacement page"},
                     "date_gmt": "2026-08-11T00:00:00", "modified_gmt": "2026-08-11T00:00:00"}]
        raise AssertionError(rest_base)

    def close(self):
        pass


def test_duplicate_wordpress_url_keeps_newest_content_and_is_idempotent(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    site = SiteConfig("demo", "Demo", "https://demo.example/", "https://demo.example")

    # Simulate the partial snapshot left by the old implementation before it
    # reached the newer page with the same URL.
    conn.execute(
        "INSERT INTO sites(site_id,name,canonical_url,wp_url,language) VALUES(?,?,?,?,?)",
        (site.site_id, site.name, site.canonical_url, site.wp_url, site.language),
    )
    conn.execute(
        "INSERT INTO posts(site_id,wp_id,type,url,title,modified_gmt) VALUES(?,?,?,?,?,?)",
        (site.site_id, 10, "post", "https://demo.example/service/", "Old post", "2026-07-30T00:00:00"),
    )
    conn.execute(
        "INSERT INTO post_terms(site_id,post_type,post_wp_id,taxonomy,term_wp_id) VALUES(?,?,?,?,?)",
        (site.site_id, "post", 10, "category", 99),
    )
    conn.commit()
    monkeypatch.setattr("seo_brain.wordpress.sync.WordPressClient", _DuplicateUrlWordPress)

    first = sync_wordpress(conn, site, use_auth=False)
    second = sync_wordpress(conn, site, use_auth=False)

    rows = conn.execute("SELECT type,wp_id,url,title FROM posts WHERE site_id=?", (site.site_id,)).fetchall()
    assert [tuple(r) for r in rows] == [("page", 20, "https://demo.example/service/", "Replacement page")]
    assert conn.execute("SELECT COUNT(*) FROM post_terms WHERE site_id=?", (site.site_id,)).fetchone()[0] == 0
    for stats in (first, second):
        assert stats["posts"] == 1
        assert stats["types"] == {"post": 0, "page": 1}
        assert stats["duplicates"] == [{
            "url": "https://demo.example/service/",
            "kept": {"type": "page", "wp_id": 20, "modified_gmt": "2026-08-11T00:00:00"},
            "discarded": {"type": "post", "wp_id": 10, "modified_gmt": "2026-07-30T00:00:00"},
        }]

