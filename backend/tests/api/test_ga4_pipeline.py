"""GA4 pipeline (twin of the GSC pipeline, wiring of existing components): client parsing/pagination with a fake
service, sync upsert into ga4_daily, job + endpoints (202/409), permission failure → not_authorized, invalid property,
snapshot merge into content_metrics, graph props on existing PAGE/POST nodes (no GA4 nodes), GA4 opportunities."""
import json
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import sites as sites_router
from seo_brain.automation.queue import InProcessJobQueue, get_job_queue
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.ga4.pipeline import STEPS, Ga4Pipeline

SID = "demo"


# --------------------------------------------------------------------------- GA4 client against a fake Data API service
class _FakeReq:
    def __init__(self, data):
        self._d = data

    def execute(self, num_retries=0):
        if isinstance(self._d, Exception):
            raise self._d
        return self._d


class _FakeProps:
    def __init__(self, responses):
        self._r = list(responses)

    def runReport(self, property=None, body=None):  # noqa: A002
        return _FakeReq(self._r.pop(0))


def _client_with(responses, tmp_path, monkeypatch):
    from seo_brain.ga4.client import Ga4Client
    c = Ga4Client.__new__(Ga4Client)
    c.site_id = SID
    c.save_raw = False
    props = _FakeProps(responses)
    c.svc = type("Svc", (), {"properties": staticmethod(lambda: props)})()
    return c


def test_ga4_client_parses_and_paginates(tmp_path, monkeypatch):
    page1 = {"rowCount": 3, "rows": [
        {"dimensionValues": [{"value": "20260810"}, {"value": "/a/"}], "metricValues": [{"value": "10"}, {"value": "8"}, {"value": "14"}, {"value": "0.61"}, {"value": "42.5"}, {"value": "2"}]},
        {"dimensionValues": [{"value": "20260810"}, {"value": "/b/"}], "metricValues": [{"value": "5"}, {"value": "5"}, {"value": "6"}, {"value": "0.3"}, {"value": "11"}, {"value": "0"}]}]}
    page2 = {"rowCount": 3, "rows": [
        {"dimensionValues": [{"value": "20260811"}, {"value": "/a/"}], "metricValues": [{"value": "7"}, {"value": "6"}, {"value": "9"}, {"value": "0.5"}, {"value": "30"}, {"value": "1"}]}]}
    c = _client_with([page1, page2], tmp_path, monkeypatch)
    rows = list(c.daily("471988572", date(2026, 8, 10), date(2026, 8, 11), row_limit=2))
    assert len(rows) == 3
    assert rows[0] == {"date": "2026-08-10", "path": "/a/", "sessions": 10, "total_users": 8, "screen_page_views": 14,
                      "engagement_rate": 0.61, "average_session_duration": 42.5, "conversions": 2.0}
    assert rows[2]["date"] == "2026-08-11" and rows[2]["sessions"] == 7


def test_ga4_client_falls_back_to_legacy_conversions_metric(tmp_path, monkeypatch):
    ok = {"rowCount": 1, "rows": [{"dimensionValues": [{"value": "20260810"}, {"value": "/a/"}],
                                  "metricValues": [{"value": "3"}, {"value": "3"}, {"value": "3"}, {"value": "0.4"}, {"value": "9"}, {"value": "1"}]}]}
    c = _client_with([RuntimeError("Field keyEvents is not a valid metric"), ok], tmp_path, monkeypatch)
    rows = list(c.daily("471988572", date(2026, 8, 10), date(2026, 8, 10)))
    assert len(rows) == 1 and rows[0]["conversions"] == 1.0


# --------------------------------------------------------------------------- pipeline + endpoints
@pytest.fixture
def env(tmp_path, monkeypatch):
    dbfile = tmp_path / "ga4.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    q = InProcessJobQueue(sync=True)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng; app.dependency_overrides[deps.job_queue] = lambda: q
    auth = {"client": True, "token": True, "scope": True}
    monkeypatch.setattr("seo_brain.connections.service._google_client_configured", lambda: auth["client"])
    monkeypatch.setattr("seo_brain.connections.service._token_info",
                        lambda: {"present": auth["token"], "scopes": (["https://www.googleapis.com/auth/webmasters.readonly"] +
                                                                     (["https://www.googleapis.com/auth/analytics.readonly"] if auth["scope"] else []))})
    calls = {"sync": 0, "snap": 0, "graph": 0}

    def fake_sync(site_id, days):
        """Stands in for ga4.sync.sync_ga4: writes the same ga4_daily rows (upsert) the real sync would."""
        calls["sync"] += 1
        with eng.begin() as cx:
            for d, path, sess, users, views, eng_r, conv in (
                    ("2026-08-01", "/emdad-renault/", 120, 90, 150, 0.62, 0.0),     # traffic, zero conversion
                    ("2026-08-02", "/emdad-renault/", 130, 95, 160, 0.60, 0.0),
                    ("2026-08-02", "/blog/renault-tips/", 60, 50, 70, 0.20, 1.0)):  # weak engagement
                cx.execute(text("INSERT INTO ga4_daily(site_id, date, page_path, sessions, total_users, screen_page_views, engagement_rate, average_session_duration, conversions, source, sync_run_id) "
                                "VALUES(:s,:d,:p,:se,:u,:v,:e,30,:c,'page','ga4-fake') "
                                "ON CONFLICT(site_id, date, page_path, source) DO UPDATE SET sessions=excluded.sessions"),
                           {"s": site_id, "d": d, "p": path, "se": sess, "u": users, "v": views, "e": eng_r, "c": conv})
        return {"run_id": "ga4-fake", "property": "471988572", "rows": 3, "pages": 2, "sessions": 310, "users": 235, "conversions": 1.0,
                "date_from": "2026-08-01", "date_to": "2026-08-02"}

    def fake_snapshot(site_id):
        calls["snap"] += 1
        from seo_brain.brain.content.analytics import ContentAnalytics
        return ContentAnalytics(eng).snapshot(site_id, today=date(2026, 8, 3)) | {"_real": True}

    def fake_graph(site_id):
        """Real GraphBuild + run_analysis on the test DB — GA4 props and opportunities must appear."""
        calls["graph"] += 1
        from seo_brain.analysis.seo import run_analysis
        from seo_brain.common.config import SiteConfig
        from seo_brain.graph import GraphBuild
        site = SiteConfig(site_id=site_id, name="Demo", canonical_url="https://demo.example/", wp_url="")
        conn = sqlite3.connect(str(dbfile)); conn.row_factory = sqlite3.Row
        try:
            run_analysis(conn, site)
            out = GraphBuild(conn, site).build(); conn.commit()
        finally:
            conn.close()
        return {"graph_nodes": out["nodes"], "graph_edges": out["edges"]}

    def make_pipe():
        return Ga4Pipeline(eng, sync_fn=fake_sync, snapshot_fn=fake_snapshot, graph_fn=fake_graph)
    q.register("ga4_sync", lambda payload: make_pipe().run(payload["site_id"], run_id=payload.get("run_id"), days=payload.get("days"), job_id=payload.get("job_id")))
    c = TestClient(app)
    r = c.post("/api/v1/sites", json={"site_id": SID, "name": "Demo", "canonical_url": "https://demo.example/", "ga4_property": "471988572"})
    assert r.status_code == 201, r.text
    # crawled pages so PAGE nodes exist for props + opportunity URL matching; content item for the snapshot
    with eng.begin() as cx:
        for u in ("https://demo.example/emdad-renault/", "https://demo.example/blog/renault-tips/"):
            cx.execute(text("INSERT INTO pages(site_id, url, crawl_status, status_code, indexable, title, meta_description, h1_count, word_count, internal_links_out, external_links_out, images_missing_alt, in_sitemap, depth, last_crawled, created_at, updated_at) "
                            "VALUES(:s,:u,'ok',200,1,'عنوان تست طولانی برای صفحه','توضیحات متا به اندازه کافی طولانی برای تست',1,500,3,0,0,1,1,datetime('now'),datetime('now'),datetime('now'))"), {"s": SID, "u": u})
        cx.execute(text("INSERT INTO content_items(site_id, title, url, status, created_at, updated_at) VALUES(:s,'امداد رنو','https://demo.example/emdad-renault/','published',datetime('now'),datetime('now'))"), {"s": SID})
    return {"client": c, "eng": eng, "q": q, "calls": calls, "auth": auth}


def test_ga4_job_registered_and_full_pipeline_runs(env):
    create_app()
    assert "ga4_sync" in get_job_queue()._handlers
    c = env["client"]
    r = c.post(f"/api/v1/sites/{SID}/ga4/sync", json={"days": 30})
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "queued" and r.json()["run_id"].startswith("ga4pipe-")
    st = c.get(f"/api/v1/sites/{SID}/ga4/sync/status").json()
    assert st["status"] == "succeeded" and st["progress"] == 1.0 and st["errors"] == [] and st["job"]["status"] == "succeeded"
    assert [s["key"] for s in st["steps"]] == [k for k, _ in STEPS]
    assert env["calls"] == {"sync": 1, "snap": 1, "graph": 1}
    cov = st["coverage"]
    assert cov["rows"] == 3 and cov["pages"] == 2 and cov["sessions"] == 310 and cov["users"] == 235
    assert cov["top_pages"][0]["path"] == "/emdad-renault/" and cov["top_pages"][0]["sessions"] == 250
    assert st["property"] == "471988572" and st["authorized"] is True
    # state lives in the existing sync_runs table
    with env["eng"].connect() as cx:
        row = cx.execute(text("SELECT source, status FROM sync_runs WHERE run_id=:r"), {"r": st["run_id"]}).first()
    assert row[0] == "ga4_pipeline" and row[1] == "succeeded"


def test_snapshot_and_graph_and_opportunities_use_existing_structures(env):
    c, eng = env["client"], env["eng"]
    assert c.post(f"/api/v1/sites/{SID}/ga4/sync", json={}).status_code == 202
    with eng.connect() as cx:
        # content analytics: GA4 columns on the SAME content_metrics rows (no parallel table)
        m = cx.execute(text("SELECT ga4_sessions, ga4_users, ga4_views, ga4_conversions, ga4_engagement_rate FROM content_metrics WHERE site_id=:s AND window='28d'"), {"s": SID}).first()
        assert m is not None and m[0] == 250 and m[1] == 185 and m[2] == 310
        # graph: props on the existing PAGE node — and NO ga4 node types
        props = json.loads(cx.execute(text("SELECT props FROM graph_nodes WHERE site_id=:s AND url LIKE '%emdad-renault%'"), {"s": SID}).scalar())
        assert props["ga4_sessions"] == 250 and props["ga4_users"] == 185 and props["last_ga4_sync"] == "2026-08-02"
        assert props["ga4_engagement_rate"] == pytest.approx(0.61, abs=0.02)
        types = {r[0] for r in cx.execute(text("SELECT DISTINCT node_type FROM graph_nodes WHERE site_id=:s"), {"s": SID})}
        assert not any("GA4" in t.upper() or "METRIC" in t.upper() for t in types)
        # opportunity engine (existing seo_opportunities): traffic-without-conversion + low engagement
        opps = {r[0]: r[1] for r in cx.execute(text("SELECT opp_type, reason FROM seo_opportunities WHERE site_id=:s AND opp_type LIKE 'ga4%'"), {"s": SID})}
    assert "ga4_traffic_no_conversion" in opps and "تبدیل پایین" in opps["ga4_traffic_no_conversion"]
    assert "ga4_low_engagement" in opps


def test_upsert_idempotent_rerun_no_duplicates(env):
    c, eng = env["client"], env["eng"]
    for _ in range(2):
        assert c.post(f"/api/v1/sites/{SID}/ga4/sync", json={}).status_code == 202
    with eng.connect() as cx:
        daily = cx.execute(text("SELECT COUNT(*) FROM ga4_daily WHERE site_id=:s"), {"s": SID}).scalar()
        dup = cx.execute(text("SELECT COUNT(*) FROM (SELECT node_id FROM graph_nodes WHERE site_id=:s GROUP BY node_id HAVING COUNT(*)>1)"), {"s": SID}).scalar()
        tables = {r[0] for r in cx.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert daily == 3 and dup == 0
    assert {t for t in tables if "ga4" in t} == {"ga4_daily"}       # exactly one new table


def test_guards_and_permission_failure(env):
    c, q, eng = env["client"], env["q"], env["eng"]
    # invalid/missing property → 409
    c.post("/api/v1/sites", json={"site_id": "noprop", "name": "N", "canonical_url": "https://n.example/"})
    r = c.post("/api/v1/sites/noprop/ga4/sync", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ga4_not_configured"
    # missing analytics scope → 409
    env["auth"]["scope"] = False
    r = c.post(f"/api/v1/sites/{SID}/ga4/sync", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ga4_not_authorized"
    env["auth"]["scope"] = True
    # permission failure inside the job (Google 403) → run ends not_authorized, downstream skipped
    def denied(site_id, days):
        return {"_step_status": "failed", "_not_authorized": True, "error": "permission denied"}
    pipe = Ga4Pipeline(eng, sync_fn=denied, snapshot_fn=lambda s: {}, graph_fn=lambda s: {})
    q.register("ga4_sync", lambda payload: pipe.run(payload["site_id"], run_id=payload.get("run_id"), job_id=payload.get("job_id")))
    assert c.post(f"/api/v1/sites/{SID}/ga4/sync", json={}).status_code == 202
    st = c.get(f"/api/v1/sites/{SID}/ga4/sync/status").json()
    assert st["status"] == "not_authorized" and [s["status"] for s in st["steps"]] == ["failed", "skipped", "skipped"]


def test_connection_test_queues_initial_ga4_sync(env):
    c = env["client"]
    c.app.dependency_overrides[sites_router.connections_service] = lambda: _FakeGa4OkService()
    r = c.post(f"/api/v1/sites/{SID}/connections/ga4/test", json={"property": "471988572"}).json()
    assert r["ok"] and r["detail"]["sync_job"]["status"] in ("queued", "already_running")
    r2 = c.post(f"/api/v1/sites/{SID}/connections/ga4/test", json={"property": "471988572", "auto_sync": False}).json()
    assert r2["ok"] and "sync_job" not in r2["detail"]


class _FakeGa4OkService:
    def test_ga4(self, site_id, property_id):
        from seo_brain.connections.service import ConnectionResult
        return ConnectionResult("ga4", "ok", "دسترسی GA4 تأیید شد", {"property": property_id, "rows": 1})
