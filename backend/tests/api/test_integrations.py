"""Integration Center aggregation (`GET /sites/{id}/integrations`): one standard block per integration, read only
from the existing tables (site_connections · sync_runs · sites) — no new tables, no new state."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import sites as sites_router
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.gsc.pipeline import GscPipeline
from seo_brain.wordpress.orchestrator import WordPressSyncOrchestrator

SID = "demo"


@pytest.fixture
def env(tmp_path, monkeypatch):
    eng = make_engine("sqlite:///" + (tmp_path / "ic.db").as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("seo_brain.connections.service._google_client_configured", lambda: True)
    monkeypatch.setattr("seo_brain.connections.service._token_info", lambda: {"present": True, "scopes": []})
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng
    c = TestClient(app)
    r = c.post("/api/v1/sites", json={"site_id": SID, "name": "Demo", "canonical_url": "https://demo.example/",
                                      "wp_url": "https://demo.example/", "gsc_property": "sc-domain:demo.example"})
    assert r.status_code == 201, r.text
    return {"client": c, "eng": eng}


def test_integrations_aggregates_existing_tables_only(env):
    c, eng = env["client"], env["eng"]
    # existing state: one tested connection row + one pipeline run row (the tables the center must read)
    with eng.begin() as cx:
        cx.execute(text("INSERT INTO site_connections(site_id, kind, status, detail, tested_at) VALUES(:s,'wordpress','ok','{\"url\":\"https://demo.example/wp-json/\"}','2026-08-20T10:00:00Z')"), {"s": SID})
    st = WordPressSyncOrchestrator(eng).create(SID, stage="full")
    gst = GscPipeline(eng).create(SID)

    d = c.get(f"/api/v1/sites/{SID}/integrations").json()
    assert d["site_id"] == SID
    by = {i["kind"]: i for i in d["integrations"]}
    assert list(by) == ["wordpress", "gsc", "ga4"]
    for i in d["integrations"]:       # the standard contract
        assert {"kind", "label", "connection", "sync", "configured", "actions"} <= set(i)
        assert {"status", "tested_at", "detail"} <= set(i["connection"])
        assert {"status", "last_run", "progress", "coverage", "error"} <= set(i["sync"])

    wp = by["wordpress"]
    assert wp["connection"]["status"] == "ok" and wp["connection"]["tested_at"] == "2026-08-20T10:00:00Z"
    assert wp["sync"]["status"] == "queued" and wp["sync"]["run_id"] == st.run_id
    assert wp["configured"] is True and wp["actions"] == ["test", "sync", "rebuild"]
    assert "graph_nodes" in wp["sync"]["coverage"]

    g = by["gsc"]
    assert g["sync"]["run_id"] == gst.run_id and g["authorized"] is True and g["actions"] == ["test", "sync"]
    assert {"rows", "queries", "pages"} <= set(g["sync"]["coverage"])

    ga4 = by["ga4"]                    # real pipeline now; no analytics scope in this fixture → test-only actions
    assert ga4["connection"]["status"] == "never" and ga4["sync"]["status"] == "never"
    assert ga4["configured"] is False and ga4["actions"] == ["test"] and ga4["authorized"] is False


def test_integrations_never_state_and_no_new_tables(env):
    c, eng = env["client"], env["eng"]
    d = c.get(f"/api/v1/sites/{SID}/integrations").json()
    assert all(i["connection"]["status"] == "never" for i in d["integrations"])
    assert d["integrations"][0]["sync"]["status"] == "never"
    with eng.connect() as cx:
        tables = {r[0] for r in cx.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert not any("integration" in t for t in tables)      # aggregation only — no new status table
