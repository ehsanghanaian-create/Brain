"""Phase 6 — Content Brain: workflow, briefs (from keywords/GSC/graph), calendar/board, graph sync, AI provider config + secret store."""
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.ai.config import ProviderConfig
from seo_brain.ai.config import test_provider as probe_provider
from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import ai_config as ai_config_router
from seo_brain.api.routers import graph as graph_router
from seo_brain.api.routers import sites as sites_router
from seo_brain.ai.config import ProviderConfigRepository
from seo_brain.brain.content.repository import TRANSITIONS
from seo_brain.core.secrets import SecretStore
from seo_brain.database.db import connect as legacy_connect
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate

SID = "demo"


@pytest.fixture
def c(tmp_path, monkeypatch):
    dbfile = tmp_path / "c.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(graph_router, "connect", lambda: legacy_connect(dbfile))
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    store = SecretStore(tmp_path / "secrets")
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng
    app.dependency_overrides[ai_config_router.cfg_repo] = lambda: ProviderConfigRepository(eng, store)
    client = TestClient(app)
    assert client.post("/api/v1/sites", json={"site_id": SID, "name": "Demo", "canonical_url": "https://demo.example/"}).status_code == 201
    client.post(f"/api/v1/sites/{SID}/initialize")
    client.eng, client.store, client.tmp = eng, store, tmp_path  # type: ignore[attr-defined]
    return client


def _seed(c):
    """pages + entities in graph, GSC rows, keywords (clustered) so briefs have real sources."""
    with c.eng.begin() as cx:
        for nid, t, label, url, props in (("page:https://demo.example/mvm/", "PAGE", "MVM page", "https://demo.example/mvm/", '{"title":"MVM","internal_links_in":4}'),
                                          ("page:https://demo.example/blog/", "PAGE", "Blog", "https://demo.example/blog/", '{}'),
                                          ("model:mvm", "MODEL", "MVM", None, '{"aliases":["ام وی ام"]}'), ("location:tehran", "LOCATION", "تهران", None, '{}'),
                                          ("service:emdad", "SERVICE", "امداد خودرو", None, '{}')):
            cx.execute(text("INSERT INTO graph_nodes(site_id,node_id,node_type,label,url,props,pagerank,updated_at) VALUES(:s,:n,:t,:l,:u,:p,0.1,datetime('now'))"),
                       {"s": SID, "n": nid, "t": t, "l": label, "u": url, "p": props})
        cx.execute(text("INSERT INTO graph_edges(site_id,edge_id,source_id,target_id,edge_type,weight) VALUES(:s,'e1','page:https://demo.example/mvm/','model:mvm','ABOUT',1)"), {"s": SID})
        for q, p, cl, imp, pos in (("امداد خودرو mvm", "https://demo.example/mvm/", 2, 300, 8.5), ("قیمت امداد خودرو mvm", "https://demo.example/mvm/", 0, 40, 12.0),
                                   ("امداد خودرو mvm تهران", "https://demo.example/blog/", 0, 25, 18.0)):
            cx.execute(text("INSERT INTO gsc_query_page(site_id,page,query,clicks,impressions,ctr,position) VALUES(:s,:p,:q,:c,:i,0,:o)"), {"s": SID, "p": p, "q": q, "c": cl, "i": imp, "o": pos})
    csv = "keyword,intent,priority,volume\nامداد خودرو mvm,transactional,high,1300\nامداد خودرو mvm تهران,local,medium,200\nامداد خودرو mvm کرج,local,low,80\n"
    c.post(f"/api/v1/sites/{SID}/keywords/import", files={"file": ("k.csv", csv.encode(), "text/csv")}, data={"dry_run": "false"})
    c.post(f"/api/v1/sites/{SID}/keywords/cluster")
    return {k["keyword"]: k for k in c.get(f"/api/v1/sites/{SID}/keywords").json()["items"]}


def test_workflow_transitions_enforced(c):
    _seed(c)
    # phase 7 strict review gate would block review→approved without a reviewed draft; this test covers the workflow mechanics only
    assert c.put(f"/api/v1/sites/{SID}/content/settings/scoring", json={"review_gate": "advisory"}).json()["review_gate"] == "advisory"
    r = c.post(f"/api/v1/sites/{SID}/content", json={"title": "امداد خودرو MVM در تهران", "target_keyword": "امداد خودرو mvm تهران", "priority": "high", "publish_date": "2026-09-01"})
    assert r.status_code == 201, r.text
    d = r.json(); cid = d["id"]
    assert d["status"] == "planned" and d["target_keyword_id"] and d["intent"] == "local" and d["cluster_id"] and d["allowed_transitions"] == ["brief_ready"]
    # cannot skip stages, cannot mark brief_ready without a brief, cannot publish without url
    assert c.post(f"/api/v1/sites/{SID}/content/{cid}/transition", json={"status": "writing"}).status_code == 409
    r = c.post(f"/api/v1/sites/{SID}/content/{cid}/transition", json={"status": "brief_ready"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition" and "brief" in r.json()["error"]["message"]
    b = c.post(f"/api/v1/sites/{SID}/content/{cid}/brief", json={"use_ai": False, "mark_ready": True}).json()
    assert b["version"] == 1 and c.get(f"/api/v1/sites/{SID}/content/{cid}").json()["status"] == "brief_ready"
    for nxt in ("writing", "review", "approved"):
        assert c.post(f"/api/v1/sites/{SID}/content/{cid}/transition", json={"status": nxt, "note": "ok"}).json()["status"] == nxt
    r = c.post(f"/api/v1/sites/{SID}/content/{cid}/transition", json={"status": "published"})
    assert r.status_code == 409 and "URL" in r.json()["error"]["message"]
    c.patch(f"/api/v1/sites/{SID}/content/{cid}", json={"url": "https://demo.example/mvm-tehran/"})
    assert c.post(f"/api/v1/sites/{SID}/content/{cid}/transition", json={"status": "published"}).json()["status"] == "published"
    # back is allowed one step, status can't be patched directly
    assert c.post(f"/api/v1/sites/{SID}/content/{cid}/transition", json={"status": "approved"}).json()["status"] == "approved"
    ev = c.get(f"/api/v1/sites/{SID}/content/{cid}/events").json()
    assert ev[0]["to_status"] == "approved" and any(e["note"] and "brief v1" in e["note"] for e in ev) and ev[-1]["note"] == "created"
    assert set(TRANSITIONS) == {"planned", "brief_ready", "writing", "review", "approved", "published"}
    assert c.get(f"/api/v1/sites/{SID}/content/meta").json()["statuses"][0]["key"] == "planned"


def test_brief_uses_keyword_cluster_gsc_graph_and_links(c):
    kws = _seed(c)
    cid = c.post(f"/api/v1/sites/{SID}/content", json={"title": "امداد خودرو MVM", "target_keyword_id": kws["امداد خودرو mvm"]["id"]}).json()["id"]
    b = c.post(f"/api/v1/sites/{SID}/content/{cid}/brief", json={"use_ai": True}).json()
    assert b["h1"] and b["seo_title"].endswith("| Demo") and b["intent"] == "transactional"
    h2s = [o["h2"] for o in b["outline"]]
    assert "امداد خودرو mvm تهران" in h2s                      # cluster sibling
    assert "قیمت امداد خودرو mvm" in h2s                        # related GSC query
    assert any("سؤالات" in h for h in h2s)
    assert {e["label"] for e in b["entities"]} >= {"MVM"}         # graph entity matched on alias/token
    assert any("قیمت" in q["question"] for q in b["questions"]) and any(q["source"].startswith("gsc") for q in b["questions"])
    assert b["sources"]["existing_pages"][0]["url"] == "https://demo.example/mvm/" and b["sources"]["existing_pages"][0]["recommendation"] == "بهبود همین صفحه"
    assert b["sources"]["competitors"]["available"] is False
    assert b["sources"]["gsc"]["keyword"]["impressions"] == 300
    assert b["provenance"]["ai_used"] is False and "Echo" in b["provenance"]["note"]   # only echo provider → rules kept, said so
    assert "## لینک‌های داخلی" in b["markdown"] and "H1 پیشنهادی" in b["markdown"]
    # second generation → version 2 and item.brief_id moves
    b2 = c.post(f"/api/v1/sites/{SID}/content/{cid}/brief").json()
    assert b2["version"] == 2 and c.get(f"/api/v1/sites/{SID}/content/{cid}").json()["brief"]["id"] == b2["id"]
    assert len(c.get(f"/api/v1/sites/{SID}/content/{cid}/briefs").json()) == 2


def test_calendar_board_from_opportunity_and_graph_sync(c):
    kws = _seed(c)
    c.post(f"/api/v1/sites/{SID}/keywords/analyze")
    opps = c.get(f"/api/v1/sites/{SID}/keywords/opportunities").json()["items"]
    o = next(x for x in opps if x["kind"] == "create_content")
    it = c.post(f"/api/v1/sites/{SID}/content/from-opportunity/{o['id']}").json()
    assert it["metadata"]["opportunity_id"] == o["id"] and it["target_keyword_id"] == o["keyword_id"]
    assert c.get(f"/api/v1/sites/{SID}/keywords/opportunities", params={"status": "accepted"}).json()["total"] == 1
    c.post(f"/api/v1/sites/{SID}/content", json={"title": "مقاله A", "publish_date": "2026-09-03"})
    c.post(f"/api/v1/sites/{SID}/content", json={"title": "مقاله B", "publish_date": "2026-09-03", "publish_time": "10:00"})
    cal = c.get(f"/api/v1/sites/{SID}/content/calendar", params={"from": "2026-09-01", "to": "2026-09-30"}).json()
    assert len(cal["days"]["2026-09-03"]) == 2 and any(u["id"] == it["id"] for u in cal["unscheduled"])
    board = c.get(f"/api/v1/sites/{SID}/content/board").json()
    assert board["columns"][0]["status"] == "planned" and len(board["columns"][0]["items"]) == 3 and board["counts"]["scheduled"] == 2
    # move via patch date / clear
    a = next(x for x in board["columns"][0]["items"] if x["title"] == "مقاله A")
    assert c.patch(f"/api/v1/sites/{SID}/content/{a['id']}", json={"publish_date": "2026-09-10"}).json()["publish_date"] == "2026-09-10"
    assert c.patch(f"/api/v1/sites/{SID}/content/{a['id']}", json={"clear_date": True}).json()["publish_date"] is None
    # graph: CONTENT nodes + CONTENT_FOR/CLUSTERED_IN edges (keywords synced first), visible in content map, details work
    c.post(f"/api/v1/sites/{SID}/keywords/sync-graph")
    g = c.post(f"/api/v1/sites/{SID}/content/sync-graph").json()
    assert g["nodes"] == 3 and g["edges"] >= 2
    v = c.get(f"/api/v1/sites/{SID}/graph/view", params={"mode": "content", "types": "CONTENT,KEYWORD,TOPIC"}).json()
    assert v["stats"]["by_type"]["CONTENT"] == 3 and v["stats"]["by_relation"].get("CONTENT_FOR", 0) >= 1
    d = c.get(f"/api/v1/sites/{SID}/graph/node-details/content:{it['id']}").json()
    assert d["type"] == "CONTENT" and d["content"]["status"] == "planned" and d["content"]["content_id"] == it["id"]
    # delete cascades briefs/events; graph resync drops the node
    assert c.delete(f"/api/v1/sites/{SID}/content/{it['id']}").json() == {"deleted": it["id"]}
    c.post(f"/api/v1/sites/{SID}/content/sync-graph")
    assert c.get(f"/api/v1/sites/{SID}/graph/view", params={"mode": "content", "types": "CONTENT"}).json()["stats"]["by_type"]["CONTENT"] == 2


def test_provider_config_secret_store_and_routes(c):
    r = c.post("/api/v1/ai/provider-configs", json={"name": "Claude", "kind": "anthropic", "api_key": "sk-ant-abcdefghijk1234"})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["has_key"] and p["key_hint"] == "1234" and "api_key" not in p and "secret_ref" not in p and p["default_model"] == "claude-sonnet-5"
    # secret is encrypted on disk, readable back only through the store
    files = list((c.tmp / "secrets").glob("*.bin"))
    assert len(files) == 1 and b"sk-ant" not in files[0].read_bytes()
    assert c.store.get("ai-provider-%d" % p["id"]) == "sk-ant-abcdefghijk1234"
    assert c.post("/api/v1/ai/provider-configs", json={"name": "Claude", "kind": "anthropic"}).status_code == 409
    assert c.post("/api/v1/ai/provider-configs", json={"name": "X", "kind": "nope"}).status_code == 422
    # ollama needs no key; custom base url
    o = c.post("/api/v1/ai/provider-configs", json={"name": "Local", "kind": "ollama", "base_url": "http://127.0.0.1:11434"}).json()
    assert o["has_key"] is False and o["kind_label"].startswith("مدل محلی")
    # update key + clear key
    p2 = c.patch(f"/api/v1/ai/provider-configs/{p['id']}", json={"api_key": "sk-ant-newkey-9999", "default_model": "claude-sonnet-5"}).json()
    assert p2["key_hint"] == "9999" and p2["default_model"] == "claude-sonnet-5"
    assert c.patch(f"/api/v1/ai/provider-configs/{p['id']}", json={"clear_key": True}).json()["has_key"] is False and not list((c.tmp / "secrets").glob("*.bin"))
    # routes
    rt = c.get("/api/v1/ai/task-routes").json()
    assert len(rt["routes"]) == 17 and all(r["provider_id"] is None for r in rt["routes"])
    rr = c.put("/api/v1/ai/task-routes/content_writing", json={"provider_id": p["id"], "model": "claude-sonnet-5", "fallback_provider_id": o["id"], "fallback_model": "llama3"}).json()
    assert rr["provider_name"] == "Claude" and rr["fallback_provider_name"] == "Local"
    assert c.put("/api/v1/ai/task-routes/nope", json={}).status_code == 422
    # deleting a provider clears routes pointing at it
    c.delete(f"/api/v1/ai/provider-configs/{o['id']}")
    assert next(x for x in c.get("/api/v1/ai/task-routes").json()["routes"] if x["task_kind"] == "content_writing")["fallback_provider_id"] is None
    assert c.get("/api/v1/ai/provider-kinds").json()[0]["kind"] == "anthropic"
    # test endpoint without key → not_configured (no network)
    assert c.post(f"/api/v1/ai/provider-configs/{p['id']}/test").json()["status"] == "not_configured"


def test_test_provider_with_fake_http():
    def fake(url, headers=None):
        if "anthropic" in url:
            assert headers["x-api-key"] == "k"
            return httpx.Response(200, json={"data": [{"id": "claude-x"}]}, request=httpx.Request("GET", url))
        if "11434" in url:
            return httpx.Response(200, json={"models": [{"name": "llama3"}]}, request=httpx.Request("GET", url))
        return httpx.Response(401, json={}, request=httpx.Request("GET", url))
    ok = probe_provider(ProviderConfig(name="a", kind="anthropic"), "k", fetch=fake)
    assert ok["ok"] and ok["models_found"] == ["claude-x"]
    assert probe_provider(ProviderConfig(name="o", kind="ollama", base_url="http://127.0.0.1:11434"), None, fetch=fake)["models_found"] == ["llama3"]
    assert probe_provider(ProviderConfig(name="g", kind="openai"), "bad", fetch=fake)["status"] == "not_authorized"
    assert probe_provider(ProviderConfig(name="g", kind="openai"), None, fetch=fake)["status"] == "not_configured"
