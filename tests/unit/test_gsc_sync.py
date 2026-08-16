from src.common.config import SiteConfig, GraphConfig
from src.database.db import connect, init_db, ensure_site
from src.gsc.sync import store_rows, aggregate


def _site():
    return SiteConfig(site_id="t", name="t", canonical_url="https://emdadmodiran.com/", wp_url="https://emdadmodiran.com",
                      graph=GraphConfig(important_query_min_impressions=100, important_query_min_clicks=10))


def test_store_and_aggregate(tmp_path):
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    site = _site()
    ensure_site(conn, site)
    dims = ["date", "query", "page", "country", "device"]
    rows = [
        {"keys": ["2026-08-10", "امداد خودرو mvm", "https://emdadmodiran.com/mvm", "irn", "MOBILE"], "clicks": 5, "impressions": 100, "ctr": 0.05, "position": 4.0},
        {"keys": ["2026-08-11", "امداد خودرو mvm", "https://emdadmodiran.com/mvm/", "irn", "MOBILE"], "clicks": 15, "impressions": 100, "ctr": 0.15, "position": 6.0},
        {"keys": ["2026-08-11", "امداد خودرو mvm", "https://emdadmodiran.com/blog/امداد-خودرو-mvm/", "irn", "DESKTOP"], "clicks": 1, "impressions": 20, "ctr": 0.05, "position": 12.0},
        {"keys": ["2026-08-11", "چری", "https://emdadmodiran.com/mvm2/", "irn", "MOBILE"], "clicks": 0, "impressions": 3, "ctr": 0, "position": 40.0},
    ]
    n = store_rows(conn, site, rows, dims, "run1")
    assert n == 4
    # idempotent upsert
    assert store_rows(conn, site, rows, dims, "run2") == 4
    assert conn.execute("select count(*) from gsc_daily").fetchone()[0] == 4
    agg = aggregate(conn, site)
    # page normalized (trailing slash) => two dates merge into one page/query row
    qp = conn.execute("select clicks, impressions, position from gsc_query_page where page='https://emdadmodiran.com/mvm/'").fetchone()
    assert (qp[0], qp[1]) == (20, 200) and abs(qp[2] - 5.0) < 1e-9  # weighted position (4*100+6*100)/200
    q = conn.execute("select impressions, pages_count, is_important, importance_reason from queries where query='امداد خودرو mvm'").fetchone()
    assert q[0] == 220 and q[1] == 2 and q[2] == 1 and q[3] == "high_impressions"
    q2 = conn.execute("select is_important from queries where query='چری'").fetchone()
    assert q2[0] == 0
    assert agg["queries"] == 2 and agg["important_queries"] == 1
