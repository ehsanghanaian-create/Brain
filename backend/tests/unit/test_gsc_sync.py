from seo_brain.common.config import SiteConfig, GraphConfig
from seo_brain.database.db import connect, init_db, ensure_site
from datetime import date

from seo_brain.gsc.sync import store_rows, store_property_rows, aggregate


def _site():
    return SiteConfig(site_id="t", name="t", canonical_url="https://example.com/", wp_url="https://example.com",
                      graph=GraphConfig(important_query_min_impressions=100, important_query_min_clicks=10))


def test_store_and_aggregate(tmp_path):
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    site = _site()
    ensure_site(conn, site)
    dims = ["date", "query", "page", "country", "device"]
    rows = [
        {"keys": ["2026-08-10", "امداد خودرو mvm", "https://example.com/mvm", "irn", "MOBILE"], "clicks": 5, "impressions": 100, "ctr": 0.05, "position": 4.0},
        {"keys": ["2026-08-11", "امداد خودرو mvm", "https://example.com/mvm/", "irn", "MOBILE"], "clicks": 15, "impressions": 100, "ctr": 0.15, "position": 6.0},
        {"keys": ["2026-08-11", "امداد خودرو mvm", "https://example.com/blog/امداد-خودرو-mvm/", "irn", "DESKTOP"], "clicks": 1, "impressions": 20, "ctr": 0.05, "position": 12.0},
        {"keys": ["2026-08-11", "چری", "https://example.com/mvm2/", "irn", "MOBILE"], "clicks": 0, "impressions": 3, "ctr": 0, "position": 40.0},
    ]
    n = store_rows(conn, site, rows, dims, "run1")
    assert n == 4
    # idempotent upsert
    assert store_rows(conn, site, rows, dims, "run2") == 4
    assert conn.execute("select count(*) from gsc_daily").fetchone()[0] == 4
    agg = aggregate(conn, site)
    # page normalized (trailing slash) => two dates merge into one page/query row
    qp = conn.execute("select clicks, impressions, position from gsc_query_page where page='https://example.com/mvm/'").fetchone()
    assert (qp[0], qp[1]) == (20, 200) and abs(qp[2] - 5.0) < 1e-9  # weighted position (4*100+6*100)/200
    q = conn.execute("select impressions, pages_count, is_important, importance_reason from queries where query='امداد خودرو mvm'").fetchone()
    assert q[0] == 220 and q[1] == 2 and q[2] == 1 and q[3] == "high_impressions"
    q2 = conn.execute("select is_important from queries where query='چری'").fetchone()
    assert q2[0] == 0
    assert agg["queries"] == 2 and agg["important_queries"] == 1


def test_property_totals_are_independent_and_window_replaces_old_rows(tmp_path):
    conn = connect(tmp_path / "property.db")
    init_db(conn)
    site = _site()
    ensure_site(conn, site)
    start, end = date(2026, 8, 10), date(2026, 8, 11)
    first = [{"keys": ["2026-08-10"], "clicks": 20, "impressions": 200, "position": 5.0},
             {"keys": ["2026-08-11"], "clicks": 30, "impressions": 300, "position": 6.0}]
    assert store_property_rows(conn, site, first, "sc-domain:example.com", start, end, "run1") == 2
    assert store_property_rows(conn, site, first[:1], "sc-domain:example.com", start, end, "run2") == 1
    got = conn.execute("SELECT date, clicks, sync_run_id FROM gsc_property_daily").fetchall()
    assert [tuple(r) for r in got] == [("2026-08-10", 20, "run2")]
