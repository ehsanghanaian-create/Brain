"""GSC production pipeline (wiring of existing components): job registration, 202/409 endpoints, status from the
existing sync_runs table, snapshot triggered after a successful sync, graph refresh through the existing rebuild path
(no duplicate nodes), and no duplicate GSC tables/architecture."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import sites as sites_router
from seo_brain.automation.queue import InProcessJobQueue, get_job_queue
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.gsc.pipeline import STEPS, GscPipeline

SID = "demo"


@pytest.fixture
def env(tmp_path, monkeypatch):
    dbfile = tmp_path / "gsc.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    q = InProcessJobQueue(sync=True)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng; app.dependency_overrides[deps.job_queue] = lambda: q
    # GSC token / client guards → authorized by default (overridable per test)
    auth = {"client": True, "token": True}
    monkeypatch.setattr("seo_brain.connections.service._google_client_configured", lambda: auth["client"])
    monkeypatch.setattr("seo_brain.connections.service._token_info", lambda: {"present": auth["token"], "scopes": ["https://www.googleapis.com/auth/webmasters.readonly"]})

    calls = {"sync": 0, "opps": 0, "snap": 0, "graph": 0}

    def fake_sync(site_id, days):
        """Stands in for gsc.sync.sync_gsc: writes the same tables (gsc_daily → aggregate → gsc_query_page/queries)."""
        calls["sync"] += 1
        with eng.begin() as cx:
            for d, page, query, clk, imp, pos in (("2026-08-01", "https://demo.example/a/", "امداد رنو", 5, 100, 4.2),
                                                  ("2026-08-02", "https://demo.example/a/", "امداد رنو", 7, 120, 3.9),
                                                  ("2026-08-02", "https://demo.example/b/", "یدک کش", 1, 40, 12.0)):
                cx.execute(text("INSERT OR REPLACE INTO gsc_daily(site_id, date, page, query, country, device, clicks, impressions, ctr, position, sync_run_id) VALUES(:s,:d,:p,:q,'irn','MOBILE',:c,:i,:ctr,:pos,'gsc-fake')"),
                           {"s": site_id, "d": d, "p": page, "q": query, "c": clk, "i": imp, "ctr": clk / imp, "pos": pos})
            cx.execute(text("DELETE FROM gsc_query_page WHERE site_id=:s"), {"s": site_id})
            cx.execute(text("INSERT INTO gsc_query_page(site_id, page, query, clicks, impressions, ctr, position, date_from, date_to) SELECT site_id, page, query, SUM(clicks), SUM(impressions), 1.0*SUM(clicks)/SUM(impressions), SUM(position*impressions)/SUM(impressions), '2026-08-01', '2026-08-02' FROM gsc_daily WHERE site_id=:s GROUP BY page, query"), {"s": site_id})
            cx.execute(text("DELETE FROM queries WHERE site_id=:s"), {"s": site_id})
            cx.execute(text("INSERT INTO queries(site_id, query, clicks, impressions, ctr, position, pages_count, is_important) SELECT site_id, query, SUM(clicks), SUM(impressions), 1.0*SUM(clicks)/SUM(impressions), SUM(position*impressions)/SUM(impressions), COUNT(DISTINCT page), 1 FROM gsc_query_page WHERE site_id=:s GROUP BY query"), {"s": site_id})
        return {"run_id": "gsc-fake", "property": "sc-domain:demo.example", "rows": 3, "queries": 2, "important_queries": 2, "query_page_rows": 2, "date_from": "2026-08-01", "date_to": "2026-08-02"}

    def fake_opps(site_id):
        calls["opps"] += 1
        return {"opportunities": 1, "by_kind": {"improve_page": 1}}

    def fake_snapshot(site_id):
        calls["snap"] += 1
        with eng.begin() as cx:
            cx.execute(text("INSERT INTO content_metrics(site_id, content_id, url, window, date, clicks, impressions, ctr, position, top_queries, delta, created_at) VALUES(:s,1,'https://demo.example/a/','28d','2026-08-19',12,220,0.054,4.0,'[]','{}',datetime('now'))"), {"s": site_id})
        return {"snapshots": 1, "content_items": 1, "source": "gsc_daily"}

    def fake_graph(site_id):
        """Mimics the existing rebuild path: delete + rebuild → idempotent, never additive."""
        calls["graph"] += 1
        with eng.begin() as cx:
            cx.execute(text("DELETE FROM graph_nodes WHERE site_id=:s"), {"s": site_id})
            for nid, ntype, label in ((f"site:{site_id}", "SITE", "Demo"), ("query:امداد رنو", "QUERY", "امداد رنو"), ("page:a", "PAGE", "A")):
                cx.execute(text("INSERT INTO graph_nodes(site_id, node_id, node_type, label, props) VALUES(:s,:n,:t,:l,'{}')"), {"s": site_id, "n": nid, "t": ntype, "l": label})
            cx.execute(text("DELETE FROM graph_edges WHERE site_id=:s"), {"s": site_id})
            cx.execute(text("INSERT INTO graph_edges(site_id, edge_id, source_id, target_id, edge_type, weight, props) VALUES(:s,'e1','query:امداد رنو','page:a','RANKS_FOR',1.0,'{}')"), {"s": site_id})
        return {"graph_nodes": 3, "graph_edges": 1, "graph_status": "succeeded"}

    def make_pipe():
        return GscPipeline(eng, sync_fn=fake_sync, opportunities_fn=fake_opps, snapshot_fn=fake_snapshot, graph_fn=fake_graph)
    q.register("gsc_sync", lambda payload: make_pipe().run(payload["site_id"], run_id=payload.get("run_id"), days=payload.get("days"), job_id=payload.get("job_id")))
    c = TestClient(app)
    r = c.post("/api/v1/sites", json={"site_id": SID, "name": "Demo", "canonical_url": "https://demo.example/", "gsc_property": "sc-domain:demo.example"}); assert r.status_code == 201, r.text
    return {"client": c, "eng": eng, "q": q, "calls": calls, "auth": auth}


def test_gsc_sync_job_is_registered_as_builtin():
    """`gsc_sync` must be a builtin job type (registered by create_app), like wordpress_sync."""
    create_app()
    assert "gsc_sync" in get_job_queue()._handlers


def test_manual_sync_202_runs_pipeline_and_status_reads_sync_runs(env):
    c = env["client"]
    r = c.post(f"/api/v1/sites/{SID}/gsc/sync", json={"days": 30})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "queued" and body["job_id"].startswith("job-") and body["run_id"].startswith("gscpipe-")
    # queue is synchronous in tests → pipeline already ran through the job system
    st = c.get(f"/api/v1/sites/{SID}/gsc/sync/status").json()
    assert st["status"] == "succeeded" and st["progress"] == 1.0 and st["errors"] == [] and st["job"]["status"] == "succeeded"
    assert [s["key"] for s in st["steps"]] == [k for k, _ in STEPS] and all(s["status"] == "done" for s in st["steps"])
    assert env["calls"] == {"sync": 1, "opps": 1, "snap": 1, "graph": 1}
    # status is read from the existing sync_runs table (source gsc_pipeline), not a new table
    with env["eng"].connect() as cx:
        row = cx.execute(text("SELECT source, status, notes FROM sync_runs WHERE run_id=:r"), {"r": st["run_id"]}).first()
    assert row[0] == "gsc_pipeline" and row[1] == "succeeded" and json.loads(row[2])["items"]["rows"] == 3
    # coverage counters come from the real GSC tables
    cov = st["coverage"]
    assert cov["rows"] == 3 and cov["queries"] == 2 and cov["important_queries"] == 2 and cov["pages"] == 2
    assert cov["date_from"] == "2026-08-01" and cov["date_to"] == "2026-08-02" and cov["content_snapshots"] == 1
    assert st["property"] == "sc-domain:demo.example" and st["authorized"] is True


def test_guards_409_not_configured_not_authorized_and_already_running(env):
    c = env["client"]
    # no property → 409 gsc_not_configured
    c.post("/api/v1/sites", json={"site_id": "noprop", "name": "N", "canonical_url": "https://n.example/"})
    r = c.post("/api/v1/sites/noprop/gsc/sync", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "gsc_not_configured"
    # no token → 409 gsc_not_authorized
    env["auth"]["token"] = False
    r = c.post(f"/api/v1/sites/{SID}/gsc/sync", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "gsc_not_authorized"
    env["auth"]["token"] = True
    # status before any run → never
    assert c.get("/api/v1/sites/noprop/gsc/sync/status").json()["status"] == "never"
    # already_running guard: pending queued state blocks a second start
    pipe = GscPipeline(env["eng"])
    st = pipe.create(SID)
    r = c.post(f"/api/v1/sites/{SID}/gsc/sync", json={})
    assert r.status_code == 202 and r.json()["status"] == "already_running" and r.json()["run_id"] == st.run_id


def test_successful_gsc_connection_queues_initial_sync(env):
    c = env["client"]
    c.app.dependency_overrides[sites_router.connections_service] = lambda: _FakeGscOkService()
    r = c.post(f"/api/v1/sites/{SID}/connections/gsc/test", json={"property": "sc-domain:demo.example"}).json()
    assert r["ok"] and r["detail"]["sync_job"]["status"] in ("queued", "already_running")
    if r["detail"]["sync_job"]["status"] == "queued":
        assert r["detail"]["sync_job"]["job_id"].startswith("job-")
        assert env["calls"]["sync"] == 1 and env["calls"]["snap"] == 1     # snapshot triggered after successful sync
    # auto_sync=false opts out
    before = env["calls"]["sync"]
    r2 = c.post(f"/api/v1/sites/{SID}/connections/gsc/test", json={"property": "sc-domain:demo.example", "auto_sync": False}).json()
    assert r2["ok"] and "sync_job" not in r2["detail"] and env["calls"]["sync"] == before


def test_not_authorized_sync_marks_run_and_skips_downstream(env):
    c, q, eng = env["client"], env["q"], env["eng"]
    def denied(site_id, days):
        return {"_step_status": "failed", "_not_authorized": True, "error": "no token"}
    pipe = GscPipeline(eng, sync_fn=denied, opportunities_fn=lambda s: {}, snapshot_fn=lambda s: {}, graph_fn=lambda s: {})
    q.register("gsc_sync", lambda payload: pipe.run(payload["site_id"], run_id=payload.get("run_id"), job_id=payload.get("job_id")))
    assert c.post(f"/api/v1/sites/{SID}/gsc/sync", json={}).status_code == 202
    st = c.get(f"/api/v1/sites/{SID}/gsc/sync/status").json()
    assert st["status"] == "not_authorized"
    assert [s["status"] for s in st["steps"]] == ["failed", "skipped", "skipped", "skipped"]
    assert env["calls"]["snap"] == 0 and env["calls"]["graph"] == 0


def test_rerun_produces_no_duplicate_graph_nodes_or_gsc_rows(env):
    c, eng = env["client"], env["eng"]
    for _ in range(2):
        assert c.post(f"/api/v1/sites/{SID}/gsc/sync", json={}).status_code == 202
    with eng.connect() as cx:
        nodes = cx.execute(text("SELECT COUNT(*) FROM graph_nodes WHERE site_id=:s"), {"s": SID}).scalar()
        qnodes = cx.execute(text("SELECT COUNT(*) FROM graph_nodes WHERE site_id=:s AND node_type='QUERY'"), {"s": SID}).scalar()
        daily = cx.execute(text("SELECT COUNT(*) FROM gsc_daily WHERE site_id=:s"), {"s": SID}).scalar()
        dup = cx.execute(text("SELECT COUNT(*) FROM (SELECT node_id FROM graph_nodes WHERE site_id=:s GROUP BY node_id HAVING COUNT(*)>1)"), {"s": SID}).scalar()
    assert nodes == 3 and qnodes == 1 and daily == 3 and dup == 0       # rebuild + upsert ⇒ idempotent, never additive


def test_no_duplicate_gsc_tables_or_new_migrations(env):
    """The pipeline must reuse the existing schema — no gsc_queries/gsc_pages/gsc_metrics or any new gsc table."""
    with env["eng"].connect() as cx:
        tables = {r[0] for r in cx.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert {t for t in tables if "gsc" in t} == {"gsc_daily", "gsc_query_page"}
    for forbidden in ("gsc_queries", "gsc_pages", "gsc_metrics", "gsc_sync_status", "gsc_runs"):
        assert forbidden not in tables


class _FakeGscOkService:
    def test_gsc(self, site_id, wanted):
        from seo_brain.connections.service import ConnectionResult
        return ConnectionResult("gsc", "ok", "دسترسی Search Console تأیید شد", {"property": wanted, "permission": "siteOwner"})
