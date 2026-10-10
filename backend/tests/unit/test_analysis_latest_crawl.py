"""A fresh full crawl must not report retained pages from older snapshots."""
import json
from datetime import datetime, timedelta, timezone

from seo_brain.analysis.seo import run_analysis
from seo_brain.common.config import CrawlerConfig, SiteConfig
from seo_brain.crawler.parser import parse_html
from seo_brain.database.db import db, ensure_site


def test_capped_crawl_analysis_combines_recent_batches(tmp_path):
    site = SiteConfig(site_id="demo", name="Demo", canonical_url="https://demo.example/", wp_url="")
    now = datetime.now(timezone.utc)
    previous = (now - timedelta(days=2)).isoformat(timespec="seconds")
    current = now.isoformat(timespec="seconds")
    with db(tmp_path / "seo.db") as conn:
        ensure_site(conn, site)
        conn.execute("""INSERT INTO crawl_runs(run_id,site_id,started_at,status,notes)
            VALUES('crawl-current','demo',?,'completed_capped','{"scope":"site"}')""", (current,))
        for path, observed in (("previous", previous), ("current", current)):
            conn.execute("""INSERT INTO pages(site_id,url,crawl_status,status_code,h1,h1_count,
                indexable,word_count,images_missing_alt,in_sitemap,last_crawled)
                VALUES('demo',?,'ok',200,?,1,1,500,1,1,?)""",
                (f"https://demo.example/{path}/", f'["{path}"]', observed))
        run_analysis(conn, site)
        urls = [row[0] for row in conn.execute(
            "SELECT url FROM seo_problems WHERE problem_type='images_missing_alt' ORDER BY url"
        )]
    assert urls == ["https://demo.example/current/", "https://demo.example/previous/"]


def test_partial_sitemap_does_not_invent_missing_inbound_links(tmp_path):
    site = SiteConfig(site_id="demo", name="Demo", canonical_url="https://demo.example/", wp_url="")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db(tmp_path / "seo.db") as conn:
        ensure_site(conn, site)
        conn.execute("""INSERT INTO crawl_runs(run_id,site_id,started_at,status,notes)
            VALUES('crawl-current','demo',?,'completed_capped','{"scope":"site","sitemap_urls":2}')""", (now,))
        conn.execute("""INSERT INTO pages(site_id,url,crawl_status,status_code,title,h1,h1_count,
            indexable,word_count,images_missing_alt,in_sitemap,last_crawled)
            VALUES('demo','https://demo.example/a/','ok',200,'A','["A"]',1,1,500,0,1,?)""", (now,))
        run_analysis(conn, site)
        assert conn.execute("SELECT COUNT(*) FROM seo_problems WHERE problem_type IN "
                            "('orphan','no_body_inbound_links','low_inbound_links')").fetchone()[0] == 0
        notes = json.loads(conn.execute(
            "SELECT notes FROM sync_runs WHERE source='analysis' ORDER BY id DESC LIMIT 1").fetchone()[0])
        assert notes["link_graph_complete"] is False

        conn.execute("""INSERT INTO pages(site_id,url,crawl_status,status_code,title,h1,h1_count,
            indexable,word_count,images_missing_alt,in_sitemap,last_crawled)
            VALUES('demo','https://demo.example/b/','ok',200,'B','["B"]',1,1,500,0,1,?)""", (now,))
        run_analysis(conn, site)
        assert conn.execute("SELECT COUNT(*) FROM seo_problems WHERE problem_type='orphan'").fetchone()[0] == 0
        conn.execute("UPDATE crawl_runs SET status='completed' WHERE run_id='crawl-current'")
        run_analysis(conn, site)
        assert conn.execute("SELECT COUNT(*) FROM seo_problems WHERE problem_type='orphan'").fetchone()[0] == 2
        conn.execute("""INSERT INTO crawl_runs(run_id,site_id,started_at,status,notes)
            VALUES('crawl-next','demo',?,'completed_capped','{"scope":"site","sitemap_urls":2}')""",
            ((datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(timespec="seconds"),))
        run_analysis(conn, site)
        assert conn.execute("SELECT COUNT(*) FROM seo_problems WHERE problem_type='orphan'").fetchone()[0] == 2


def test_stale_self_redirect_is_not_a_sitemap_redirect(tmp_path):
    site = SiteConfig(site_id="demo", name="Demo", canonical_url="https://demo.example/", wp_url="")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source = "https://demo.example/a/"
    with db(tmp_path / "seo.db") as conn:
        ensure_site(conn, site)
        conn.execute("""INSERT INTO crawl_runs(run_id,site_id,started_at,status,notes)
            VALUES('crawl-current','demo',?,'completed','{"scope":"site","sitemap_urls":1}')""", (now,))
        conn.execute("""INSERT INTO pages(site_id,url,crawl_status,status_code,title,h1,h1_count,
            indexable,word_count,images_missing_alt,in_sitemap,last_crawled,redirect_chain,final_url)
            VALUES('demo',?,'ok',200,'A','["A"]',1,1,500,0,1,?,?,?)""",
            (source, now, json.dumps([[source, 308]]), source))
        run_analysis(conn, site)
        assert conn.execute("SELECT COUNT(*) FROM seo_problems WHERE problem_type='redirect_in_sitemap'").fetchone()[0] == 0
        conn.execute("UPDATE pages SET final_url='https://demo.example/b/' WHERE url=?", (source,))
        run_analysis(conn, site)
        assert conn.execute("SELECT COUNT(*) FROM seo_problems WHERE problem_type='redirect_in_sitemap'").fetchone()[0] == 1


def test_tracking_variants_do_not_become_separate_problem_pages(tmp_path):
    site = SiteConfig(site_id="demo", name="Demo", canonical_url="https://demo.example/", wp_url="",
                      crawler=CrawlerConfig(ignored_query_params=["source"]))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db(tmp_path / "seo.db") as conn:
        ensure_site(conn, site)
        conn.execute("""INSERT INTO crawl_runs(run_id,site_id,started_at,status,notes)
            VALUES('crawl-current','demo',?,'completed','{"scope":"site","sitemap_urls":1}')""", (now,))
        for url, missing, in_sitemap in (("https://demo.example/style-builder/", 0, 1),
                                         ("https://demo.example/style-builder/?source=article_a", 3, 0)):
            conn.execute("""INSERT INTO pages(site_id,url,crawl_status,status_code,title,h1,h1_count,
                indexable,word_count,images_missing_alt,in_sitemap,last_crawled)
                VALUES('demo',?,'ok',200,'Builder','["Builder"]',1,1,500,?,?,?)""",
                (url, missing, in_sitemap, now))
        run_analysis(conn, site)
        assert conn.execute("SELECT COUNT(*) FROM seo_problems WHERE problem_type='images_missing_alt'").fetchone()[0] == 0


def test_explicit_empty_alt_is_not_a_missing_alt_finding_in_old_snapshot(tmp_path):
    site = SiteConfig(site_id="demo", name="Demo", canonical_url="https://demo.example/", wp_url="")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    images = [{"src": "https://demo.example/decorative.webp", "alt": "", "decorative": False},
              {"src": "https://demo.example/missing.webp", "alt": None, "decorative": False}]
    with db(tmp_path / "seo.db") as conn:
        ensure_site(conn, site)
        conn.execute("""INSERT INTO crawl_runs(run_id,site_id,started_at,status,notes)
            VALUES('crawl-current','demo',?,'completed','{"scope":"site","sitemap_urls":1}')""", (now,))
        conn.execute("""INSERT INTO pages(site_id,url,crawl_status,status_code,title,h1,h1_count,
            indexable,word_count,images,images_missing_alt,in_sitemap,last_crawled)
            VALUES('demo','https://demo.example/','ok',200,'Home','["Home"]',1,1,500,?,2,1,?)""",
            (json.dumps(images), now))
        run_analysis(conn, site)
        row = conn.execute("SELECT detail FROM seo_problems WHERE problem_type='images_missing_alt'").fetchone()
        assert json.loads(row[0])["images_missing_alt"] == 1
        images.pop()
        conn.execute("UPDATE pages SET images=? WHERE site_id='demo'", (json.dumps(images),))
        run_analysis(conn, site)
        assert conn.execute("SELECT COUNT(*) FROM seo_problems WHERE problem_type='images_missing_alt'").fetchone()[0] == 0


def test_parser_counts_main_outside_malformed_body():
    html = "<html><body></body><main><h1>Current page</h1><p>Useful text for readers</p></main></html>"
    parsed = parse_html(html, "https://demo.example/")
    assert parsed.word_count == 6


def test_noindex_page_does_not_require_canonical_or_meta_description(tmp_path):
    site = SiteConfig(site_id="demo", name="Demo", canonical_url="https://demo.example/", wp_url="")
    with db(tmp_path / "seo.db") as conn:
        ensure_site(conn, site)
        conn.execute("INSERT INTO crawl_runs(run_id,site_id,started_at,status,notes) VALUES "
                     "('crawl-current','demo','2026-09-30T10:00:00Z','completed','{\"scope\":\"site\"}')")
        conn.execute("INSERT INTO pages(site_id,url,crawl_status,status_code,title,h1,h1_count,indexable,"
                     "indexability_reason,word_count,images_missing_alt,in_sitemap,last_crawled,crawl_run_id) "
                     "VALUES ('demo','https://demo.example/tag/cars/','ok',200,'Cars','[\"Cars\"]',1,0,"
                     "'noindex',100,0,0,'2026-09-30T10:01:00Z','crawl-current')")
        run_analysis(conn, site)
        findings = {row[0] for row in conn.execute("SELECT problem_type FROM seo_problems")}
    assert "missing_canonical" not in findings
    assert "missing_meta_description" not in findings


def test_global_navigation_alone_does_not_make_noindex_archive_important(tmp_path):
    site = SiteConfig(site_id="demo", name="Demo", canonical_url="https://demo.example/", wp_url="")
    target = "https://demo.example/category/cars/"
    with db(tmp_path / "seo.db") as conn:
        ensure_site(conn, site)
        conn.execute("INSERT INTO crawl_runs(run_id,site_id,started_at,status,notes) VALUES "
                     "('crawl-current','demo','2026-09-30T10:00:00Z','completed','{\"scope\":\"site\"}')")
        for url, indexable in [(target, 0)] + [(f"https://demo.example/source-{i}/", 1) for i in range(3)]:
            conn.execute("INSERT INTO pages(site_id,url,crawl_status,status_code,title,meta_description,h1,h1_count,"
                         "canonical,indexable,indexability_reason,word_count,images_missing_alt,in_sitemap,last_crawled,crawl_run_id) "
                         "VALUES ('demo',?,'ok',200,'Page','Description','[\"Page\"]',1,?,?,?,500,0,0,"
                         "'2026-09-30T10:01:00Z','crawl-current')",
                         (url, url, indexable, "noindex" if not indexable else None))
        for i in range(3):
            conn.execute("INSERT INTO links(site_id,source_url,target_url,is_internal,is_nav) VALUES "
                         "('demo',?,?,1,1)", (f"https://demo.example/source-{i}/", target))
        run_analysis(conn, site)
        assert conn.execute("SELECT COUNT(*) FROM seo_problems WHERE problem_type='important_non_indexable'").fetchone()[0] == 0
        conn.execute("UPDATE links SET is_nav=0 WHERE site_id='demo' AND target_url=?", (target,))
        run_analysis(conn, site)
        assert conn.execute("SELECT COUNT(*) FROM seo_problems WHERE problem_type='important_non_indexable'").fetchone()[0] == 1


def test_analysis_excludes_old_pages_and_non_html_responses(tmp_path):
    site = SiteConfig(site_id="demo", name="Demo", canonical_url="https://demo.example/", wp_url="")
    with db(tmp_path / "seo.db") as conn:
        ensure_site(conn, site)
        conn.execute("INSERT INTO crawl_runs(run_id,site_id,started_at,status,notes) VALUES "
                     "('crawl-current','demo','2026-09-30T10:00:00Z','completed','{\"scope\":\"site\"}')")
        base = ("INSERT INTO pages(site_id,url,crawl_status,status_code,title,meta_description,h1,h1_count,canonical,"
                "indexable,word_count,images_missing_alt,in_sitemap,last_crawled,crawl_run_id) "
                "VALUES ('demo',?,'ok',200,'Page','Useful description','[\"Page\"]',?, ?,1,500,0,1,?,?)")
        old = "https://demo.example/old"
        target = "https://demo.example/current"
        conn.execute(base, (old, 1, old, "2026-09-01T10:00:00Z", "crawl-old"))
        conn.execute(base, (target, 1, target, "2026-09-30T10:01:00Z", "crawl-current"))
        conn.execute(base, ("https://demo.example/feed.xml", None, None,
                            "2026-09-30T10:01:00Z", "crawl-current"))
        conn.execute("INSERT INTO links(site_id,source_url,target_url,is_internal,is_nav) "
                     "VALUES ('demo',?,?,1,0)", (old, target))
        result = run_analysis(conn, site)
        findings = conn.execute("SELECT problem_type,url FROM seo_problems WHERE site_id='demo'").fetchall()
    assert result["problems"] == 1
    assert [(row[0], row[1]) for row in findings] == [("orphan", target)]


def test_paginated_archive_keeps_its_heading_without_duplicate_h1_findings(tmp_path):
    site = SiteConfig(site_id="demo", name="Demo", canonical_url="https://demo.example/", wp_url="")
    archive = ["https://demo.example/blog/", "https://demo.example/blog/page/2/",
               "https://demo.example/blog/page/3/", "https://demo.example/blog/page/10/",
               "https://demo.example/blog/page/21/"]
    with db(tmp_path / "seo.db") as conn:
        ensure_site(conn, site)
        conn.execute("INSERT INTO crawl_runs(run_id,site_id,started_at,status,notes) VALUES "
                     "('crawl-current','demo','2026-09-30T10:00:00Z','completed','{\"scope\":\"site\"}')")
        for url in reversed(archive):
            conn.execute("INSERT INTO pages(site_id,url,crawl_status,status_code,title,meta_description,h1,h1_count,"
                         "canonical,indexable,word_count,images_missing_alt,in_sitemap,last_crawled,crawl_run_id) "
                         "VALUES ('demo',?,'ok',200,?,'Useful description','[\"Articles\"]',1,?,1,500,0,1,"
                         "'2026-09-30T10:01:00Z','crawl-current')", (url, "Archive", url))
        run_analysis(conn, site)
        assert conn.execute("SELECT COUNT(*) FROM seo_problems WHERE problem_type='duplicate_h1'").fetchone()[0] == 0
        # Pagination can share its section H1, but each indexable page still
        # needs a distinct document title (usually including its page number).
        assert conn.execute("SELECT COUNT(*) FROM seo_problems WHERE problem_type='duplicate_title'").fetchone()[0] == 5
        other = "https://demo.example/service/"
        conn.execute("INSERT INTO pages(site_id,url,crawl_status,status_code,title,meta_description,h1,h1_count,"
                     "canonical,indexable,word_count,images_missing_alt,in_sitemap,last_crawled,crawl_run_id) "
                     "VALUES ('demo',?,'ok',200,'Service','Useful description','[\"Articles\"]',1,?,1,500,0,1,"
                     "'2026-09-30T10:01:00Z','crawl-current')", (other, other))
        run_analysis(conn, site)
        urls = [row[0] for row in conn.execute(
            "SELECT url FROM seo_problems WHERE problem_type='duplicate_h1' ORDER BY url")]
    assert urls == [archive[0], other]


def test_canonical_alias_with_identical_content_is_not_a_second_heading_problem(tmp_path):
    site = SiteConfig(site_id="demo", name="Demo", canonical_url="https://demo.example/", wp_url="")
    primary = "https://demo.example/service/"
    alias = "https://demo.example/old-service/"
    different = "https://demo.example/other-service/"
    with db(tmp_path / "seo.db") as conn:
        ensure_site(conn, site)
        conn.execute("INSERT INTO crawl_runs(run_id,site_id,started_at,status,notes) VALUES "
                     "('crawl-current','demo','2026-09-30T10:00:00Z','completed','{\"scope\":\"site\"}')")
        for url, canonical, content_hash in ((alias, primary, "same"), (primary, primary, "same"),
                                              (different, primary, "different")):
            conn.execute("INSERT INTO pages(site_id,url,crawl_status,status_code,title,meta_description,h1,h1_count,"
                         "canonical,content_hash,indexable,word_count,images_missing_alt,in_sitemap,last_crawled,crawl_run_id) "
                         "VALUES ('demo',?,'ok',200,'Service','Useful description','[\"Service\"]',1,?,?,1,500,0,1,"
                         "'2026-09-30T10:01:00Z','crawl-current')", (url, canonical, content_hash))
        run_analysis(conn, site)
        urls = [row[0] for row in conn.execute(
            "SELECT url FROM seo_problems WHERE problem_type='duplicate_h1' ORDER BY url")]
        title_urls = [row[0] for row in conn.execute(
            "SELECT url FROM seo_problems WHERE problem_type='duplicate_title' ORDER BY url")]
    assert urls == [different, primary]
    assert title_urls == [different, primary]
