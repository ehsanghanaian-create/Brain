"""A capped scheduled crawl must eventually reach every sitemap URL."""
import sqlite3

import pytest

from seo_brain.common.config import CrawlerConfig, SiteConfig
from seo_brain.crawler import crawler as crawler_module
from seo_brain.database.db import db, ensure_site, utcnow


def test_site_crawl_prioritizes_uncrawled_then_oldest_urls(tmp_path, monkeypatch):
    monkeypatch.setattr(crawler_module, "raw_data_dir", lambda: tmp_path)
    crawler = crawler_module.Crawler(SiteConfig(
        site_id="pilot", name="Pilot", canonical_url="https://pilot.example/",
        wp_url="https://pilot.example",
    ))
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE pages(site_id TEXT,url TEXT,last_crawled TEXT)")
    connection.executemany("INSERT INTO pages VALUES('pilot',?,?)", [
        ("https://pilot.example/a/", "2026-10-09T12:00:00Z"),
        ("https://pilot.example/b/", "2026-10-01T12:00:00Z"),
    ])
    sitemap = {"https://pilot.example/a/", "https://pilot.example/b/",
               "https://pilot.example/c/"}
    try:
        assert crawler.ordered_seeds(connection, sitemap) == [
            "https://pilot.example/", "https://pilot.example/c/",
            "https://pilot.example/b/", "https://pilot.example/a/",
        ]
        assert crawler.ordered_seeds(connection, sitemap, [
            "https://pilot.example/a", "https://pilot.example/c",
            "https://pilot.example/a/",
        ]) == ["https://pilot.example/a/", "https://pilot.example/c/"]
        connection.execute("INSERT INTO pages VALUES('pilot','https://pilot.example/','2026-10-10T12:00:00Z')")
        assert crawler.ordered_seeds(connection, sitemap)[0] == "https://pilot.example/c/"
    finally:
        crawler.http.close()
        connection.close()


def test_crawler_deduplicates_configured_tracking_query(tmp_path, monkeypatch):
    monkeypatch.setattr(crawler_module, "raw_data_dir", lambda: tmp_path)
    crawler = crawler_module.Crawler(SiteConfig(
        site_id="pilot", name="Pilot", canonical_url="https://pilot.example/",
        wp_url="https://pilot.example",
        crawler=CrawlerConfig(ignored_query_params=["source", "items"]),
    ))
    try:
        assert crawler.norm("https://pilot.example/style-builder/?source=article_a") == (
            "https://pilot.example/style-builder/")
        assert crawler.norm("https://pilot.example/style-builder/?size=large&source=article_a") == (
            "https://pilot.example/style-builder/?size=large")
        assert crawler.norm("https://pilot.example/style-builder/?items=12,14&source=product_bundle") == (
            "https://pilot.example/style-builder/")
    finally:
        crawler.http.close()


def test_second_crawl_of_same_site_is_rejected_before_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(crawler_module, "raw_data_dir", lambda: tmp_path)
    site = SiteConfig(site_id="pilot", name="Pilot", canonical_url="https://pilot.example/",
                      wp_url="https://pilot.example")
    crawler = crawler_module.Crawler(site)
    try:
        with db(tmp_path / "seo.db") as conn:
            ensure_site(conn, site)
            conn.execute("""INSERT INTO crawl_runs(run_id,site_id,started_at,status)
                VALUES('first','pilot',?,'running')""", (utcnow(),))
            with pytest.raises(RuntimeError, match="crawl already running"):
                crawler.run(conn)
            assert conn.execute("SELECT COUNT(*) FROM crawl_runs WHERE site_id='pilot'").fetchone()[0] == 1
    finally:
        crawler.http.close()


def test_sitemap_inventory_retains_uncrawled_pages_and_retires_removed_urls(tmp_path, monkeypatch):
    monkeypatch.setattr(crawler_module, "raw_data_dir", lambda: tmp_path)
    crawler = crawler_module.Crawler(SiteConfig(
        site_id="pilot", name="Pilot", canonical_url="https://pilot.example/",
        wp_url="https://pilot.example",
    ))
    connection = sqlite3.connect(":memory:")
    connection.execute("""CREATE TABLE pages(site_id TEXT,url TEXT,in_sitemap INTEGER,
        crawl_status TEXT,UNIQUE(site_id,url))""")
    connection.executemany("INSERT INTO pages VALUES('pilot',?,?,?)", [
        ("https://pilot.example/old/", 1, "ok"),
        ("https://pilot.example/a/", 1, "ok"),
    ])
    try:
        crawler.record_sitemap_inventory(connection, {
            "https://pilot.example/a/", "https://pilot.example/new/",
        })
        assert connection.execute("SELECT url,in_sitemap,crawl_status FROM pages ORDER BY url").fetchall() == [
            ("https://pilot.example/a/", 1, "ok"),
            ("https://pilot.example/new/", 1, "pending"),
            ("https://pilot.example/old/", 0, "ok"),
        ]
        crawler.record_sitemap_inventory(connection, set())
        assert connection.execute("SELECT COUNT(*) FROM pages WHERE in_sitemap=1").fetchone()[0] == 2
    finally:
        crawler.http.close()
        connection.close()
