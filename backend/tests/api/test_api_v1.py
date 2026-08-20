"""API tests against an isolated temporary database (no dependency on data/seo.db)."""
import pytest
from fastapi.testclient import TestClient

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import graph as graph_router
from seo_brain.api.routers import sites as sites_router
from seo_brain.database.db import connect as legacy_connect
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.graph.model import GraphEdge, GraphNode
from seo_brain.graph.store import SqlGraphStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    dbfile = tmp_path / "api.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix())
    migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(graph_router, "connect", lambda: legacy_connect(dbfile))   # legacy analytics → same temp DB
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)                       # workspaces under tmp, not data/
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    from seo_brain.ai.gateway import Gateway as _GW
    app.dependency_overrides[deps.gateway] = (lambda g: (lambda: g))(_GW(eng))   # isolate: never the live DB gateway
    c = TestClient(app)
    c.eng = eng  # type: ignore[attr-defined]
    return c


def _seed(c: TestClient):
    r = c.post("/api/v1/sites", json={"site_id": "demo", "name": "Demo", "canonical_url": "https://demo.example/",
                                       "wp_url": "https://demo.example", "business_type": "auto-service"})
    assert r.status_code == 201, r.text
    store = SqlGraphStore(c.eng)
    store.upsert_nodes([GraphNode("site:demo", "demo", "SITE", {"label": "Demo"}),
                        GraphNode("page:https://demo.example/a", "demo", "PAGE", {"label": "A", "url": "https://demo.example/a"}),
                        GraphNode("query:امداد", "demo", "QUERY", {"label": "امداد"})])
    store.upsert_edges([GraphEdge("site:demo", "page:https://demo.example/a", "HAS_PAGE", site_id="demo"),
                        GraphEdge("page:https://demo.example/a", "query:امداد", "RANKS_FOR", 0.5, {"props": {"position": 8}}, "demo")])


def test_health_reports_migrations(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and "0002" in body["migrations"]["applied"] and body["migrations"]["pending"] == []


def test_sites_crud_and_workspace(client):
    assert client.get("/api/v1/sites").json() == []
    _seed(client)
    sites = client.get("/api/v1/sites").json()
    assert [s["site_id"] for s in sites] == ["demo"] and sites[0]["mode"] == "manual"
    assert sites[0]["workspace_path"] == "data/sites/demo"
    r = client.patch("/api/v1/sites/demo", json={"mode": "assisted", "country": "IR"})
    assert r.status_code == 200 and r.json()["mode"] == "assisted" and r.json()["country"] == "IR"
    assert client.post("/api/v1/sites", json={"site_id": "demo", "name": "x", "canonical_url": "https://x.example/"}).status_code == 409
    assert client.get("/api/v1/sites/nope").status_code == 404
    assert client.post("/api/v1/sites", json={"site_id": "Bad Slug", "name": "x", "canonical_url": "https://x.example/"}).status_code == 422


def test_graph_endpoints_neo4j_shape(client):
    _seed(client)
    s = client.get("/api/v1/sites/demo/graph/summary").json()
    assert s["nodes"] == 3 and s["edges"] == 2 and s["by_relation_type"]["RANKS_FOR"] == 1
    n = client.get("/api/v1/sites/demo/graph/node/page:https://demo.example/a").json()
    assert set(n) == {"id", "site_id", "type", "metadata"} and n["type"] == "PAGE"
    sg = client.get("/api/v1/sites/demo/graph/subgraph", params={"center": "site:demo", "hops": 2}).json()
    assert len(sg["nodes"]) == 3 and len(sg["edges"]) == 2
    e = sg["edges"][0]
    assert set(e) == {"source", "target", "relation_type", "weight", "metadata", "site_id"}
    nb = client.get("/api/v1/sites/demo/graph/neighbors/query:امداد", params={"direction": "in"}).json()
    assert len(nb["edges"]) == 1
    assert client.get("/api/v1/sites/demo/graph/nodes", params={"types": "query"}).json()[0]["id"] == "query:امداد"
    sr = client.get("/api/v1/sites/demo/graph/search", params={"q": "امداد"}).json()
    assert [x["id"] for x in sr["nodes"]] == ["query:امداد"] and "fts" in sr
    assert client.get("/api/v1/sites/demo/graph/node/nope").status_code == 404
    assert client.get("/api/v1/sites/demo/graph/orphans").status_code == 200


def test_memory_and_ai_orchestrator_endpoints(client):
    _seed(client)
    m = client.get("/api/v1/sites/demo/memory").json()
    assert m["business_rules"] == [] and m["tone"] == {}
    r = client.put("/api/v1/sites/demo/memory", json={"business_rules": ["فقط تهران"], "tone": {"voice": "friendly"}})
    assert r.status_code == 200 and r.json()["business_rules"] == ["فقط تهران"]
    ctx = client.get("/api/v1/sites/demo/memory/context").json()["messages"]
    assert ctx and ctx[0]["role"] == "system" and "فقط تهران" in ctx[0]["content"]

    assert client.get("/api/v1/ai/routes").json()["providers"] == ["echo"]
    r = client.post("/api/v1/ai/sites/demo/run", json={"kind": "brief", "prompt": "write", "json_keys": ["title", "h1"],
                                                       "learn_pattern": "brief ok", "learn_evidence": "test"})
    body = r.json()
    assert r.status_code == 200 and body["ok"] and body["memory_used"] and body["response"]["parsed"] == {"title": "echo:title", "h1": "echo:h1"}
    assert client.get("/api/v1/sites/demo/memory").json()["successful_patterns"][0]["pattern"] == "brief ok"
    assert client.post("/api/v1/ai/sites/demo/run", json={"kind": "nope", "prompt": "x"}).status_code == 422


def test_jobs_endpoints(client):
    r = client.post("/api/v1/jobs", json={"type": "noop", "payload": {"site_id": "demo", "x": 1}})
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    import time
    for _ in range(50):
        st = client.get(f"/api/v1/jobs/{run_id}").json()
        if st["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.02)
    assert st["status"] == "succeeded" and st["result"]["echo"]["site_id"] == "demo" and st["result"]["echo"]["x"] == 1
    assert st["result"]["echo"]["job_id"] == run_id       # the queue exposes the job's own run id to every handler payload
    assert client.post("/api/v1/jobs", json={"type": "unknown"}).status_code == 422
    assert client.get("/api/v1/jobs/none").status_code == 404


def test_api_token_enforced_when_set(tmp_path, monkeypatch):
    eng = make_engine("sqlite:///" + (tmp_path / "tok.db").as_posix()); migrate(eng)
    monkeypatch.setenv("API_TOKEN", "s3cret")
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng
    from seo_brain.ai.gateway import Gateway as _GW
    app.dependency_overrides[deps.gateway] = (lambda g: (lambda: g))(_GW(eng))
    c = TestClient(app)
    assert c.get("/api/v1/health").status_code == 200                # health is open
    assert c.get("/api/v1/sites").status_code == 401
    assert c.get("/api/v1/sites", headers={"X-API-Token": "wrong"}).status_code == 401
    assert c.get("/api/v1/sites", headers={"X-API-Token": "s3cret"}).status_code == 200


def test_legacy_dashboard_mounted(client):
    r = client.get("/legacy/api/sites")
    assert r.status_code == 200
    assert client.get("/").json()["legacy_dashboard"] == "/legacy"


def test_error_envelope_and_request_id(client):
    r = client.get("/api/v1/sites/nope", headers={"X-Request-ID": "req-1"})
    assert r.status_code == 404 and r.headers["X-Request-ID"] == "req-1"
    assert r.json() == {"error": {"code": "not_found", "message": "unknown site_id 'nope'", "details": None, "request_id": "req-1"}}
    r = client.post("/api/v1/sites", json={"site_id": "BAD", "name": "x", "canonical_url": "nope"})
    body = r.json()["error"]
    assert r.status_code == 422 and body["code"] == "validation_error" and isinstance(body["details"], list) and body["details"][0]["loc"]
    assert client.get("/api/v1/health").headers.get("X-Request-ID")


def test_delete_site_refuses_then_forces(client):
    _seed(client)
    client.put("/api/v1/sites/demo/memory", json={"tone": {"voice": "x"}})
    r = client.delete("/api/v1/sites/demo")
    assert r.status_code == 409 and r.json()["error"]["code"] == "site_has_data"
    assert r.json()["error"]["details"]["graph_nodes"] == 3 and r.json()["error"]["details"]["site_memory"] == 1
    r = client.delete("/api/v1/sites/demo?force=true")
    assert r.status_code == 200 and r.json()["deleted"] == "demo" and r.json()["related_rows_deleted"]["graph_edges"] == 2
    assert client.get("/api/v1/sites/demo").status_code == 404
    assert client.get("/api/v1/sites").json() == []
    # a site without data deletes without force
    client.post("/api/v1/sites", json={"site_id": "empty", "name": "E", "canonical_url": "https://e.example/"})
    assert client.delete("/api/v1/sites/empty").status_code == 200


def test_graph_modes_view_and_details(client):
    _seed(client)
    modes = client.get("/api/v1/sites/demo/graph/modes").json()
    assert [m["key"] for m in modes] == ["seo", "content", "links", "planner"] and all(m["title_fa"] for m in modes)
    v = client.get("/api/v1/sites/demo/graph/view", params={"mode": "seo"}).json()
    assert v["mode"]["key"] == "seo" and {n["id"] for n in v["nodes"]} == {"site:demo", "page:https://demo.example/a", "query:امداد"}
    assert {(e["source"], e["relation_type"], e["target"]) for e in v["edges"]} == {("site:demo", "HAS_PAGE", "page:https://demo.example/a"), ("page:https://demo.example/a", "RANKS_FOR", "query:امداد")}
    assert v["stats"]["by_type"] == {"SITE": 1, "PAGE": 1, "QUERY": 1} and v["truncated"] is False
    # links mode: only page-ish nodes and LINKS_TO edges (none seeded) → nodes without edges dropped when include_isolated=false
    lv = client.get("/api/v1/sites/demo/graph/view", params={"mode": "links", "include_isolated": "false"}).json()
    assert lv["nodes"] == [] and lv["edges"] == []
    lv2 = client.get("/api/v1/sites/demo/graph/view", params={"mode": "links"}).json()
    assert [n["id"] for n in lv2["nodes"]] == ["page:https://demo.example/a"]
    # types filter narrows within the mode; unknown mode → 422; limit → truncated flag
    tv = client.get("/api/v1/sites/demo/graph/view", params={"mode": "seo", "types": "QUERY"}).json()
    assert [n["type"] for n in tv["nodes"]] == ["QUERY"] and tv["edges"] == []
    assert client.get("/api/v1/sites/demo/graph/view", params={"mode": "nope"}).status_code == 422
    assert client.get("/api/v1/sites/demo/graph/view", params={"mode": "seo", "limit": 1}).json()["truncated"] is True
    # details per node kind
    d = client.get("/api/v1/sites/demo/graph/node-details/query:امداد").json()
    assert d["type"] == "QUERY" and d["keyword"]["related_pages"][0]["id"] == "page:https://demo.example/a" and d["degree"] == 1
    p = client.get("/api/v1/sites/demo/graph/node-details/page:https://demo.example/a").json()
    assert p["type"] == "PAGE" and "page" in p and p["page"]["content_status"] == "unknown" and p["related"]["queries"][0]["label"] == "امداد"
    s = client.get("/api/v1/sites/demo/graph/node-details/site:demo").json()
    assert s["type"] == "SITE" and "site" in s
    assert client.get("/api/v1/sites/demo/graph/node-details/nope:x").status_code == 404
