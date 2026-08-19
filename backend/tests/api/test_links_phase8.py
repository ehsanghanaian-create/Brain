"""Phase 8 — Internal Link Intelligence: journey model, scoring, anchors, audit/health, analyze API, statuses → graph, patterns → memory, content task, export, job mode."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import graph as graph_router
from seo_brain.api.routers import sites as sites_router
from seo_brain.automation.queue import InProcessJobQueue
from seo_brain.brain.linking.audit import health_score
from seo_brain.brain.linking.journey import is_meaningful, journey_score
from seo_brain.brain.linking.scoring import confidence_of
from seo_brain.database.db import connect as legacy_connect
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate

SID = "demo"


@pytest.fixture
def c(tmp_path, monkeypatch):
    dbfile = tmp_path / "l.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(graph_router, "connect", lambda: legacy_connect(dbfile))
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    q = InProcessJobQueue(sync=True)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng; app.dependency_overrides[deps.job_queue] = lambda: q
    from seo_brain.brain.linking import LinkEngine
    q.register("links_analyze", lambda payload: LinkEngine(eng).analyze(payload["site_id"]))
    client = TestClient(app)
    assert client.post("/api/v1/sites", json={"site_id": SID, "name": "Demo", "canonical_url": "https://demo.example/"}).status_code == 201
    client.post(f"/api/v1/sites/{SID}/initialize")
    client.eng = eng  # type: ignore[attr-defined]
    return client


def _seed(c):
    """A small site: hub category, service pages (MVM, Sandero), informational posts (gearbox problems, Renault history), contact page, orphan service page."""
    P = "https://demo.example"
    pages = [
        ("cat:services", "CATEGORY", "خدمات امداد خودرو", f"{P}/services/", 0.30, {}),
        ("page:mvm", "PAGE", "امداد خودرو MVM در تهران", f"{P}/mvm/", 0.20, {"title": "امداد خودرو MVM در تهران", "h2": ["خدمات امداد خودرو mvm", "مناطق تحت پوشش"]}),
        ("page:sandero", "PAGE", "امداد خودرو ساندرو", f"{P}/sandero/", 0.05, {"title": "امداد خودرو ساندرو", "h2": ["خدمات امداد خودرو ساندرو"]}),
        ("post:gearbox", "POST", "مشکلات گیربکس ساندرو و راه‌حل‌ها", f"{P}/blog/sandero-gearbox/", 0.10, {"title": "مشکلات گیربکس ساندرو", "h2": ["علت خرابی گیربکس ساندرو", "هزینه تعمیر گیربکس ساندرو"]}),
        ("post:history", "POST", "تاریخچه رنو در ایران", f"{P}/blog/renault-history/", 0.08, {"title": "تاریخچه رنو در ایران", "h2": ["ورود رنو به ایران"]}),
        ("page:contact", "PAGE", "تماس با نمونه سایت — شماره امداد", f"{P}/contact/", 0.15, {"title": "تماس با ما"}),
        ("page:orphan", "PAGE", "امداد خودرو تیگو ۷", f"{P}/tiggo7/", 0.01, {"title": "امداد خودرو تیگو ۷", "h2": ["خدمات امداد خودرو تیگو 7"]}),
    ]
    with c.eng.begin() as cx:
        for nid, t, label, url, pr, props in pages:
            cx.execute(text("INSERT INTO graph_nodes(site_id,node_id,node_type,label,url,props,pagerank,community,updated_at) VALUES(:s,:n,:t,:l,:u,:p,:pr,1,datetime('now'))"),
                       {"s": SID, "n": nid, "t": t, "l": label, "u": url, "p": json.dumps(props, ensure_ascii=False), "pr": pr})
            cx.execute(text("INSERT INTO pages(site_id,url,final_url,status_code,title,h1,h2,word_count,indexable) VALUES(:s,:u,:u,200,:t,:h1,:h,800,1)"),
                       {"s": SID, "u": url, "t": label, "h1": json.dumps([label], ensure_ascii=False), "h": json.dumps(props.get("h2", []), ensure_ascii=False)})
        for nid, t, label in (("model:mvm", "MODEL", "MVM"), ("model:sandero", "MODEL", "ساندرو"), ("brand:renault", "BRAND", "رنو"), ("service:emdad", "SERVICE", "امداد خودرو"), ("model:tiggo7", "MODEL", "تیگو ۷")):
            cx.execute(text("INSERT INTO graph_nodes(site_id,node_id,node_type,label,props,updated_at) VALUES(:s,:n,:t,:l,'{}',datetime('now'))"), {"s": SID, "n": nid, "t": t, "l": label})
        edges = [("page:mvm", "model:mvm", "ABOUT"), ("page:mvm", "service:emdad", "OFFERS"), ("page:sandero", "model:sandero", "ABOUT"), ("page:sandero", "brand:renault", "ABOUT"), ("page:sandero", "service:emdad", "OFFERS"),
                 ("post:gearbox", "model:sandero", "ABOUT"), ("post:gearbox", "brand:renault", "ABOUT"), ("post:history", "brand:renault", "ABOUT"), ("page:orphan", "model:tiggo7", "ABOUT"), ("page:orphan", "service:emdad", "OFFERS"),
                 ("page:mvm", "cat:services", "BELONGS_TO"), ("page:sandero", "cat:services", "BELONGS_TO"), ("page:orphan", "cat:services", "BELONGS_TO")]
        for i, (a, b, et) in enumerate(edges):
            cx.execute(text("INSERT INTO graph_edges(site_id,edge_id,source_id,target_id,edge_type,weight) VALUES(:s,:e,:a,:b,:t,1)"), {"s": SID, "e": f"e{i}", "a": a, "b": b, "t": et})
        links = [(f"{P}/services/", f"{P}/mvm/", "امداد MVM", 0), (f"{P}/services/", f"{P}/sandero/", "اینجا", 0), (f"{P}/mvm/", f"{P}/contact/", "تماس", 0), (f"{P}/sandero/", f"{P}/contact/", "تماس", 0),
                 (f"{P}/blog/renault-history/", f"{P}/blog/sandero-gearbox/", "گیربکس ساندرو", 0), (f"{P}/services/", f"{P}/blog/sandero-gearbox/", "مشکلات گیربکس", 1)]
        for a, b, anchor, nav in links:
            cx.execute(text("INSERT INTO links(site_id,source_url,target_url,anchor_text,is_internal,is_nav) VALUES(:s,:a,:b,:x,1,:n)"), {"s": SID, "a": a, "b": b, "x": anchor, "n": nav})
        cx.execute(text("INSERT INTO gsc_query_page(site_id,page,query,clicks,impressions,ctr,position) VALUES(:s,:p,'امداد خودرو ساندرو',3,400,0,9.5)"), {"s": SID, "p": f"{P}/sandero/"})
    csv = "keyword,intent,priority,target_url\nامداد خودرو ساندرو,transactional,high,https://demo.example/sandero/\nامداد خودرو mvm,transactional,high,https://demo.example/mvm/\nمشکلات گیربکس ساندرو,informational,medium,https://demo.example/blog/sandero-gearbox/\nامداد خودرو تیگو 7,local,high,https://demo.example/tiggo7/\n"
    c.post(f"/api/v1/sites/{SID}/keywords/import", files={"file": ("k.csv", csv.encode(), "text/csv")}, data={"dry_run": "false"})
    c.post(f"/api/v1/sites/{SID}/keywords/cluster"); c.post(f"/api/v1/sites/{SID}/keywords/sync-graph")


def test_journey_model_and_confidence_and_health():
    assert journey_score("informational", "service")[0] == 0.95 and journey_score("informational", "commercial")[0] == 1.0
    assert journey_score("informational", "conversion")[0] == 0.85 and journey_score("commercial", "service")[0] == 1.0
    assert journey_score("informational", "informational")[0] == 0.55                       # same level = less valuable
    assert journey_score("service", "informational")[0] == 0.3                              # backwards («تاریخچه رنو»)
    assert journey_score("hub", "service")[0] == 0.9 and journey_score("service", "hub")[0] == 0.5
    assert is_meaningful("informational", "service") and is_meaningful("hub", "service") and not is_meaningful("service", "informational") and not is_meaningful("informational", "informational")
    assert confidence_of(0.5) == "low" and confidence_of(0.6) == "recommended" and confidence_of(0.79) == "recommended" and confidence_of(0.8) == "high"
    hs_orphan, parts = health_score(0, 0, 5, 0, 0, 0, True, 0.5)
    hs_good, _ = health_score(6, 3, 8, 4, 0.2, 0.0, False, 0.9)
    assert hs_orphan < 35 and parts["orphan_risk"] == 0 and parts["inbound_contextual"] == 0
    assert hs_good >= 90 and 0 <= hs_good <= 100


def test_analyze_produces_explainable_journey_aware_suggestions(c):
    _seed(c)
    r = c.post(f"/api/v1/sites/{SID}/links/analyze")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "sync" and d["suggestions"] > 0 and d["stats"]["orphans"] >= 1 and set(d["by_confidence"]) <= {"low", "recommended", "high"}
    items = c.get(f"/api/v1/sites/{SID}/links/suggestions", params={"limit": 200}).json()["items"]
    # gearbox (informational, entity ساندرو) → sandero service page: forward journey, shared entity, contextual anchor
    s = next(x for x in items if x["source_node_id"] == "post:gearbox" and x["target_node_id"] == "page:sandero")
    assert s["source_stage"] == "informational" and s["target_stage"] == "service" and s["kind"] == "supports"
    assert s["score_breakdown"]["intent"] >= 0.95 and s["score_breakdown"]["entities"] > 0 and "ساندرو" in s["anchor"]
    assert "ساندرو" in s["reason_fa"] and "سفر کاربر" in s["reason_fa"] and s["confidence"] in ("recommended", "high")
    assert s["evidence"]["journey"]["source_stage"] == "informational" and s["evidence"]["target_gsc"]["position"] == 9.5
    # backwards / same-level pairs are ranked lower or absent: history → gearbox is same-level (informational→informational, already linked anyway) → not suggested
    assert not any(x["source_node_id"] == "post:history" and x["target_node_id"] == "post:gearbox" for x in items)     # existing link → dropped
    lower = [x for x in items if x["source_node_id"] == "page:sandero" and x["target_node_id"] == "post:history"]       # service → informational (backwards)
    assert not lower or lower[0]["score"] < s["score"]
    # orphan rescue for tiggo7 exists with hub/service sources; caps: ≤5 per target, ≤3 per source
    orphan_s = [x for x in items if x["target_node_id"] == "page:orphan"]
    assert orphan_s and all(x["kind"] == "orphan_rescue" for x in orphan_s) and len(orphan_s) <= 5
    from collections import Counter
    per_source = Counter(x["source_node_id"] for x in items if x["kind"] != "anchor_fix")
    assert max(per_source.values()) <= 3
    per_target = Counter(x["target_node_id"] for x in items if x["kind"] != "anchor_fix")
    assert max(per_target.values()) <= 5
    # anchor_fix for the generic «اینجا» link services → sandero
    af = [x for x in items if x["kind"] == "anchor_fix"]
    assert af and af[0]["source_node_id"] == "cat:services" and af[0]["target_node_id"] == "page:sandero" and "اینجا" in af[0]["reason_fa"]
    # every suggestion has Persian reason + evidence + confidence label
    assert all(x["reason_fa"] and x["confidence_fa"] and x["kind_fa"] and 0.45 <= x["score"] <= 1.0 for x in items if x["kind"] != "anchor_fix")
    # graph: LINK_OPPORTUNITY + SUPPORTS edges (only meaningful, topic ≥ 0.6)
    view = c.get(f"/api/v1/sites/{SID}/graph/view", params={"mode": "links"}).json()
    rel = view["stats"]["by_relation"]
    assert rel.get("LINK_OPPORTUNITY", 0) >= 3 and rel.get("SUPPORTS", 0) >= 1
    sup = [e for e in view["edges"] if e["relation_type"] == "SUPPORTS"]
    assert all(e["weight"] >= 0.6 for e in sup) and any(e["source"] == "post:gearbox" and e["target"] == "page:sandero" for e in sup)
    assert not any(e["source"] == "post:history" and e["target"] == "post:gearbox" for e in sup)             # same-level: no SUPPORTS noise
    # pages audit + health + node details
    pages = c.get(f"/api/v1/sites/{SID}/links/pages", params={"flag": "orphan"}).json()["items"]
    assert any(p["node_id"] == "page:orphan" and p["health_score"] < 40 for p in pages)
    detail = c.get(f"/api/v1/sites/{SID}/links/pages/page:sandero").json()
    assert detail["inbound_body"] == 1 and detail["suggestions_to"] and "health_breakdown" in detail and detail["stage"] == "service"
    nd = c.get(f"/api/v1/sites/{SID}/graph/node-details/page:sandero").json()
    assert "link_health" in nd and 0 <= nd["link_health"]["score"] <= 100 and nd["link_suggestions"]["to"]
    summ = c.get(f"/api/v1/sites/{SID}/links/summary").json()
    assert summ["by_status"]["new"] == len(items) and summ["flags"]["orphan"] >= 1 and summ["avg_health"] is not None
    # determinism: second run keeps counts (no duplicates)
    d2 = c.post(f"/api/v1/sites/{SID}/links/analyze").json()
    assert d2["suggestions"] == d["suggestions"] and d2["created"] == 0 and c.get(f"/api/v1/sites/{SID}/links/summary").json()["by_status"]["new"] == len(items)


def test_statuses_graph_patterns_memory_content_task_export_settings_and_job(c):
    _seed(c)
    c.post(f"/api/v1/sites/{SID}/links/analyze")
    items = c.get(f"/api/v1/sites/{SID}/links/suggestions", params={"limit": 200}).json()["items"]
    s = next(x for x in items if x["source_node_id"] == "post:gearbox" and x["target_node_id"] == "page:sandero")
    # accept with edited anchor → SUGGESTED_LINK edge, LINK_OPPORTUNITY removed
    acc = c.patch(f"/api/v1/sites/{SID}/links/suggestions/{s['id']}", json={"status": "accepted", "anchor": "امداد خودرو ساندرو در تهران"}).json()
    assert acc["status"] == "accepted" and acc["anchor"] == "امداد خودرو ساندرو در تهران"
    edges = c.get(f"/api/v1/sites/{SID}/graph/view", params={"mode": "links"}).json()["edges"]
    assert any(e["relation_type"] == "SUGGESTED_LINK" and e["source"] == "post:gearbox" and e["target"] == "page:sandero" for e in edges)
    assert not any(e["relation_type"] == "LINK_OPPORTUNITY" and e["source"] == "post:gearbox" and e["target"] == "page:sandero" for e in edges)
    # done keeps SUGGESTED_LINK with done flag; dismiss removes
    assert c.patch(f"/api/v1/sites/{SID}/links/suggestions/{s['id']}", json={"status": "done"}).json()["status"] == "done"
    other = next(x for x in items if x["id"] != s["id"] and x["kind"] != "anchor_fix")
    c.patch(f"/api/v1/sites/{SID}/links/suggestions/{other['id']}", json={"status": "dismissed"})
    edges = c.get(f"/api/v1/sites/{SID}/graph/view", params={"mode": "links"}).json()["edges"]
    assert not any(e["relation_type"] in ("LINK_OPPORTUNITY", "SUGGESTED_LINK") and e["source"] == other["source_node_id"] and e["target"] == other["target_node_id"] for e in edges)
    # re-analyze keeps user statuses
    c.post(f"/api/v1/sites/{SID}/links/analyze")
    assert c.get(f"/api/v1/sites/{SID}/links/suggestions/{s['id']}").json()["status"] == "done"
    assert c.get(f"/api/v1/sites/{SID}/links/summary").json()["by_status"]["dismissed"] == 1
    # patterns appear after ≥2 decisions; accept → Site Brain memory (source internal_linking); never automatic before that
    pats = c.get(f"/api/v1/sites/{SID}/links/patterns").json()
    assert pats and all(p["status"] == "new" for p in pats)
    mem0 = len(c.get(f"/api/v1/sites/{SID}/memory").json()["successful_patterns"])
    jp = next((p for p in pats if p["pattern_key"].startswith("journey:")), pats[0])
    ap = c.patch(f"/api/v1/sites/{SID}/links/patterns/{jp['id']}", json={"status": "accepted"}).json()
    mem = c.get(f"/api/v1/sites/{SID}/memory").json()["successful_patterns"]
    assert ap["status"] == "accepted" and ap["memory_pattern_ref"] and len(mem) == mem0 + 1 and mem[-1]["source"] == "internal_linking"
    # content task from an accepted suggestion → planned Content Brain item, linked back
    ct = c.post(f"/api/v1/sites/{SID}/links/suggestions/{s['id']}/content-task", json={"title": "راهنمای مشکلات رایج رنو ساندرو"})
    assert ct.status_code == 201 and ct.json()["status"] == "planned" and ct.json()["suggestion"]["content_task_id"] == ct.json()["content_id"]
    assert c.get(f"/api/v1/sites/{SID}/content/{ct.json()['content_id']}").json()["metadata"]["link_suggestion_id"] == s["id"]
    # export csv (accepted+done)
    ex = c.get(f"/api/v1/sites/{SID}/links/export.csv")
    assert ex.status_code == 200 and "text/csv" in ex.headers["content-type"] and "امداد خودرو ساندرو در تهران" in ex.text and ex.text.count("\n") >= 2
    # settings + job mode when page count exceeds threshold
    st = c.put(f"/api/v1/sites/{SID}/links/settings", json={"min_score": 0.5, "max_per_source": 2, "sync_threshold_pages": 0}).json()
    assert st["min_score"] == 0.5 and st["max_per_source"] == 2 and st["weights"]["topic"] == 0.3
    r = c.post(f"/api/v1/sites/{SID}/links/analyze")
    assert r.status_code == 202 and r.json()["mode"] == "job" and r.json()["type"] == "links_analyze"
    run = c.get(f"/api/v1/jobs/{r.json()['run_id']}").json()
    assert run["status"] == "succeeded" and run["result"]["suggestions"] >= 1
    assert c.get(f"/api/v1/sites/{SID}/links/meta").json()["future_scopes"] == ["external", "backlink", "competitor"]
    # WordPress untouched: no write endpoints exist under /links
    paths = c.get("/api/openapi.json").json()["paths"]
    assert not any("wordpress" in p and "links" in p for p in paths)
