"""A fresh full crawl must not report retained pages from older snapshots."""
from seo_brain.analysis.seo import run_analysis
from seo_brain.common.config import SiteConfig
from seo_brain.crawler.parser import parse_html
from seo_brain.database.db import db, ensure_site


def test_parser_counts_main_outside_malformed_body():
    html = "<html><body></body><main><h1>Current page</h1><p>Useful text for readers</p></main></html>"
    parsed = parse_html(html, "https://demo.example/")
    assert parsed.word_count == 6


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
