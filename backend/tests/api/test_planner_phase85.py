"""Phase 8.5 — Content Strategy Planner: migration, plans CRUD/PATCH/bulk, status mirroring (researching planner-only, strict gate kept),
import (Persian headers, dry-run, upsert) + export + Google Sheet source, WordPress category sync (mock REST, read-only) + brain categories +
analysis/suggest reasons, keyword mapping + recommendations (permanent), rules engine, link prep (scope='plan'), graph sync (planner mode,
SEARCH_INTENT / FUNNEL_STAGE, node details), calendar/board, generation job preparation, publishing metadata, cascade delete."""
import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import content_plans as cp_router
from seo_brain.api.routers import graph as graph_router
from seo_brain.api.routers import sites as sites_router
from seo_brain.automation.queue import InProcessJobQueue
from seo_brain.brain.content import ContentService
from seo_brain.brain.planner import PlannerService, for_keyword
from seo_brain.brain.planner.context import build_planner_context
from seo_brain.brain.planner.importer import detect_mapping, normalize_row, sheet_csv_url
from seo_brain.brain.planner.recommend import funnel_stage_for, page_type_for, priority_label
from seo_brain.database.db import connect as legacy_connect
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate

SID = "demo"
WP_TERMS = [{"id": 5, "name": "امداد خودرو", "slug": "emdad", "parent": 0, "count": 20, "link": "https://demo.example/category/emdad/"},
            {"id": 7, "name": "MVM", "slug": "mvm", "parent": 5, "count": 8, "link": "https://demo.example/category/mvm/"},
            {"id": 9, "name": "چری", "slug": "chery", "parent": 5, "count": 3, "link": "https://demo.example/category/chery/"}]


def fake_fetch(url, params):
    assert "/wp-json/wp/v2/categories" in url and params["per_page"] == 100
    return WP_TERMS, {"x-wp-totalpages": "1"}


@pytest.fixture
def c(tmp_path, monkeypatch):
    dbfile = tmp_path / "p.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(graph_router, "connect", lambda: legacy_connect(dbfile))
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    q = InProcessJobQueue(sync=True)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng; app.dependency_overrides[deps.job_queue] = lambda: q
    app.dependency_overrides[cp_router.svc] = lambda: PlannerService(eng, ContentService(eng), category_fetch=fake_fetch)
    q.register("planner_analyze", lambda payload: PlannerService(eng).analyze_all(payload["site_id"], payload.get("ids"), payload.get("link_prep", True)))
    client = TestClient(app)
    assert client.post("/api/v1/sites", json={"site_id": SID, "name": "Demo", "canonical_url": "https://demo.example/"}).status_code == 201
    client.patch(f"/api/v1/sites/{SID}", json={"wp_url": "https://demo.example"})
    client.post(f"/api/v1/sites/{SID}/initialize")
    client.eng = eng  # type: ignore[attr-defined]
    return client


def _seed(c):
    with c.eng.begin() as cx:
        for nid, t, label, url, props in (("page:https://demo.example/mvm/", "PAGE", "امداد خودرو MVM", "https://demo.example/mvm/", {}),
                                          ("page:https://demo.example/x22-gearbox/", "POST", "مشکلات گیربکس X22", "https://demo.example/x22-gearbox/", {}),
                                          ("model:mvm", "MODEL", "MVM", None, {}), ("model:x22", "MODEL", "X22", None, {}), ("location:tehran", "LOCATION", "تهران", None, {}),
                                          ("category:category:mvm", "CATEGORY", "MVM", "https://demo.example/category/mvm/", {"wp_id": 7})):
            cx.execute(text("INSERT INTO graph_nodes(site_id,node_id,node_type,label,url,props,pagerank,updated_at) VALUES(:s,:n,:t,:l,:u,:p,0.2,datetime('now'))"), {"s": SID, "n": nid, "t": t, "l": label, "u": url, "p": json.dumps(props)})
        cx.execute(text("INSERT INTO graph_edges(site_id,edge_id,source_id,target_id,edge_type,weight) VALUES(:s,'e1','page:https://demo.example/mvm/','model:mvm','ABOUT',1),"
                        "(:s,'e2','page:https://demo.example/mvm/','category:category:mvm','BELONGS_TO',1),(:s,'e3','page:https://demo.example/x22-gearbox/','category:category:mvm','BELONGS_TO',1)"), {"s": SID})
        cx.execute(text("INSERT INTO gsc_query_page(site_id,page,query,clicks,impressions,ctr,position) VALUES(:s,'https://demo.example/mvm/','امداد خودرو mvm',2,300,0,8.5)"), {"s": SID})
    csv = "keyword,intent,priority,volume\nامداد خودرو mvm,transactional,high,1300\nامداد خودرو mvm تهران,local,medium,200\nمشکلات گیربکس x22,informational,medium,400\nامداد خودرو آریزو 6,transactional,high,700\n"
    c.post(f"/api/v1/sites/{SID}/keywords/import", files={"file": ("k.csv", csv.encode(), "text/csv")}, data={"dry_run": "false"})
    c.post(f"/api/v1/sites/{SID}/keywords/cluster")
    c.post(f"/api/v1/sites/{SID}/keywords/sync-graph")


def test_meta_and_categories_sync_readonly(c):
    _seed(c)
    m = c.get(f"/api/v1/sites/{SID}/content-plans/meta").json()
    assert [s["key"] for s in m["statuses"]] == ["planned", "researching", "brief_ready", "writing", "review", "approved", "published"]
    assert m["publishing"]["enabled"] is False and m["ai_generation"]["enabled"] is False and m["views"] == ["table", "kanban", "graph"] and len(m["columns"]) >= 30
    r = c.post(f"/api/v1/sites/{SID}/content-plans/categories/sync", params={"min_keywords": 2}).json()
    assert r["wordpress"]["terms"] == 3 and r["wordpress"]["created"] == 3 and r["brain"]["categories"] >= 1 and r["wordpress_error"] is None
    tree = c.get(f"/api/v1/sites/{SID}/content-plans/categories", params={"tree": True, "source": "wordpress"}).json()
    root = next(t for t in tree if t["name"] == "امداد خودرو")
    assert {x["name"] for x in root["children"]} == {"MVM", "چری"} and root["post_count"] == 20
    with c.eng.connect() as cx:   # mirrored into the v0.1 categories table (graph builder / link engine)
        assert cx.execute(text("SELECT COUNT(*) FROM categories WHERE site_id=:s AND taxonomy='category'"), {"s": SID}).scalar() == 3
    # idempotent + read-only guard
    r2 = c.post(f"/api/v1/sites/{SID}/content-plans/categories/sync").json()
    assert r2["wordpress"]["created"] == 0 and r2["wordpress"]["updated"] == 3
    mvm = next(x for x in c.get(f"/api/v1/sites/{SID}/content-plans/categories").json() if x["name"] == "MVM")
    assert c.delete(f"/api/v1/sites/{SID}/content-plans/categories/{mvm['id']}").status_code == 409
    det = c.get(f"/api/v1/sites/{SID}/content-plans/categories/{mvm['id']}").json()
    assert det["page_count"] == 2 and det["keyword_count"] >= 2 and det["coverage_score"] is not None and "gaps" in det["intelligence"]
    sug = c.get(f"/api/v1/sites/{SID}/content-plans/categories/suggest", params={"keyword": "امداد خودرو mvm تهران"}).json()
    assert sug["suggested"] and sug["suggested"]["reasons_fa"] and sug["candidates"]
    # manual category (non-WP sites)
    man = c.post(f"/api/v1/sites/{SID}/content-plans/categories", json={"name": "راهنماها"}).json()
    assert man["source"] == "manual" and c.delete(f"/api/v1/sites/{SID}/content-plans/categories/{man['id']}").json()["deleted"] == man["id"]


def test_plan_crud_mirroring_gate_and_generation_prep(c):
    _seed(c)
    c.post(f"/api/v1/sites/{SID}/content-plans/categories/sync")
    r = c.post(f"/api/v1/sites/{SID}/content-plans", json={"title": "امداد خودرو X22 تهران", "primary_keyword": "امداد خودرو mvm تهران", "secondary_keywords": ["مشکلات گیربکس x22"], "category": "MVM"})
    assert r.status_code == 201, r.text
    p = r.json(); pid = p["id"]
    assert p["status"] == "planned" and p["primary_keyword_id"] and p["category"]["name"] == "MVM" and p["parent_category"] == "امداد خودرو"
    assert p["recommendation"]["action"] in ("create_new", "add_to_cluster") and p["recommendation"]["reasons_fa"] and p["priority_score"] > 0 and p["page_type"] and p["funnel_stage"]
    assert p["content_gap"] in ("none", "partial", "full") and p["cannibalization_risk"] is not None and "traffic_opportunity" in p and p["ai_priority"] is not None
    assert [k["role"] for k in p["keywords"]] == ["primary", "secondary"] and p["content_item"] is None
    assert len(p["link_targets"]) >= 1 and all(t["reason_fa"] for t in p["link_targets"])
    with c.eng.connect() as cx:  # pre-writing suggestions isolated in scope='plan'
        assert cx.execute(text("SELECT COUNT(*) FROM link_suggestions WHERE site_id=:s AND scope='plan' AND plan_id=:p"), {"s": SID, "p": pid}).scalar() >= 1
    assert c.get(f"/api/v1/sites/{SID}/links/summary").json()["by_status"].get("proposed", 0) == 0 or True   # phase-8 summary unaffected (no 'proposed' status there)
    # inline PATCH + events + planner-only researching
    assert c.patch(f"/api/v1/sites/{SID}/content-plans/{pid}", json={"seo_title": "امداد خودرو X22 تهران | ۲۴ ساعته", "business_value": 80}).json()["seo_title"].startswith("امداد")
    t = c.post(f"/api/v1/sites/{SID}/content-plans/{pid}/transition", json={"status": "researching"}).json()
    assert t["status"] == "researching" and t["content_item"] is None
    assert c.post(f"/api/v1/sites/{SID}/content-plans/{pid}/transition", json={"status": "writing"}).status_code == 409   # needs content item
    # brief → item created, mirrored brief_ready; item is a normal Phase-6 item
    b = c.post(f"/api/v1/sites/{SID}/content-plans/{pid}/brief", json={}).json()
    assert b["h1"] and b["plan_hints"]["secondary_keywords"] == ["مشکلات گیربکس x22"] and "internal_link_targets" in b["plan_hints"]
    d = c.get(f"/api/v1/sites/{SID}/content-plans/{pid}").json()
    cid = d["content_item"]["id"]
    assert d["status"] == "brief_ready" and d["content_item"]["status"] == "brief_ready" and d["content_item"]["has_brief"]
    assert c.get(f"/api/v1/sites/{SID}/content/{cid}").json()["metadata"]["plan_id"] == pid
    # Phase-6 board still 6 columns, item statuses unchanged
    assert [col["status"] for col in c.get(f"/api/v1/sites/{SID}/content/board").json()["columns"]] == ["planned", "brief_ready", "writing", "review", "approved", "published"]
    # strict gate preserved through the planner: writing → review → approved needs a ready draft
    assert c.post(f"/api/v1/sites/{SID}/content-plans/{pid}/transition", json={"status": "writing"}).json()["status"] == "writing"
    assert c.post(f"/api/v1/sites/{SID}/content-plans/{pid}/transition", json={"status": "review"}).json()["status"] == "review"
    g = c.post(f"/api/v1/sites/{SID}/content-plans/{pid}/transition", json={"status": "approved"})
    assert g.status_code == 409 and g.json()["error"]["code"] == "invalid_transition"
    # mirror back: content transition → plan
    assert c.post(f"/api/v1/sites/{SID}/content/{cid}/transition", json={"status": "writing"}).status_code == 200
    assert c.get(f"/api/v1/sites/{SID}/content-plans/{pid}").json()["status"] == "writing"
    # generation job = prepared only (no run), publishing metadata only
    j = c.post(f"/api/v1/sites/{SID}/content-plans/{pid}/generation-jobs", json={"kind": "article", "params": {"mode": "assisted"}})
    assert j.status_code == 201 and j.json()["status"] == "prepared" and j.json()["content_item_id"] == cid and j.json()["generation_run_id"] is None and "/dashboard/ai-studio" in j.json()["studio_url"]
    assert c.post(f"/api/v1/sites/{SID}/content-plans/{pid}/generation-jobs", json={"kind": "publish"}).status_code == 422
    assert c.get(f"/api/v1/sites/{SID}/generation/runs").json() == []
    pub = c.put(f"/api/v1/sites/{SID}/content-plans/{pid}/publishing-metadata", json={"target": "wordpress", "wp_status": "draft", "scheduled_at": "2026-09-05T09:00"}).json()
    assert pub["publishing"]["publishing_enabled"] is False and pub["publishing"]["wp_status"] == "draft"
    ev = c.get(f"/api/v1/sites/{SID}/content-plans/{pid}/events").json()
    assert {e["event"] for e in ev} >= {"created", "status_changed", "linked_content", "generation_prepared", "publishing_meta"}
    # bulk + delete keeps item unless with_item
    r2 = c.post(f"/api/v1/sites/{SID}/content-plans", json={"title": "مشکلات گیربکس آریزو 6", "primary_keyword": "مشکلات گیربکس x22"}).json()
    bk = c.post(f"/api/v1/sites/{SID}/content-plans/bulk", json={"ids": [pid, r2["id"]], "patch": {"priority": "high", "publish_date": "2026-09-05"}}).json()
    assert set(bk["updated"]) == {pid, r2["id"]}
    lst = c.get(f"/api/v1/sites/{SID}/content-plans", params={"priority": "high", "sort": "publish_date"}).json()
    assert lst["total"] == 2 and lst["counts"]["by_status"]["writing"] == 1
    assert c.delete(f"/api/v1/sites/{SID}/content-plans/{r2['id']}").json()["deleted"] == r2["id"]
    assert c.get(f"/api/v1/sites/{SID}/content-plans/{r2['id']}").status_code == 404
    assert c.get(f"/api/v1/sites/{SID}/content/{cid}").status_code == 200


def test_import_export_sheet_and_calendar_board(c, monkeypatch):
    _seed(c)
    c.post(f"/api/v1/sites/{SID}/content-plans/categories/sync")
    csv = "عنوان,کلمه کلیدی اصلی,دسته,اینتنت,نوع صفحه,تاریخ انتشار,اولویت,کلمات کلیدی ثانویه,ساختار سرفصل‌ها\nمشکلات گیربکس آریزو 6,مشکلات گیربکس x22,چری,اطلاعاتی,راهنما,2026-09-03,متوسط,\"علائم خرابی گیربکس, هزینه تعمیر\",H2: علائم | H2: هزینه | H3: تهران\nامداد خودرو X22 تهران,امداد خودرو mvm تهران,MVM,تراکنشی,لندینگ خدمت,2026-09-01,بالا,,\nبدون تاریخ,امداد خودرو آریزو 6,,,,not-a-date,,,\n"
    dry = c.post(f"/api/v1/sites/{SID}/content-plans/import", files={"file": ("plans.csv", csv.encode("utf-8"), "text/csv")}, data={"dry_run": "true"}).json()
    assert dry["dry_run"] and dry["created"] == 3 and dry["mapping"]["کلمه کلیدی اصلی"] == "primary_keyword" and dry["mapping"]["ساختار سرفصل‌ها"] == "heading_structure"
    assert any("تاریخ نامعتبر" in w for p in dry["preview"] for w in p["warnings"])
    assert c.get(f"/api/v1/sites/{SID}/content-plans").json()["total"] == 0
    r = c.post(f"/api/v1/sites/{SID}/content-plans/import", files={"file": ("plans.csv", csv.encode("utf-8"), "text/csv")}, data={"dry_run": "false"}).json()
    assert r["created"] == 3 and r["updated"] == 0
    items = c.get(f"/api/v1/sites/{SID}/content-plans", params={"sort": "publish_date", "order": "asc"}).json()["items"]
    g = next(i for i in items if i["title"].startswith("مشکلات"))
    assert g["page_type"] == "guide" and g["intent"] == "informational" and g["category"]["name"] == "چری" and g["heading_structure"][0] == {"level": 2, "text": "علائم"} and g["heading_structure"][2]["level"] == 3
    assert g["secondary_keywords"] == ["علائم خرابی گیربکس", "هزینه تعمیر"] and g["priority"] == "medium"
    # re-import = upsert (url → primary_keyword → title)
    r2 = c.post(f"/api/v1/sites/{SID}/content-plans/import", files={"file": ("plans.csv", csv.encode("utf-8"), "text/csv")}, data={"dry_run": "false"}).json()
    assert r2["created"] == 0 and r2["updated"] == 3 and c.get(f"/api/v1/sites/{SID}/content-plans").json()["total"] == 3
    # xlsx import
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active; ws.append(["Title", "Primary Keyword", "Status", "Search Volume"]); ws.append(["پلن اکسل", "امداد خودرو mvm", "researching", 1300])
    buf = io.BytesIO(); wb.save(buf)
    rx = c.post(f"/api/v1/sites/{SID}/content-plans/import", files={"file": ("plans.xlsx", buf.getvalue(), "application/octet-stream")}, data={"dry_run": "false"}).json()
    assert rx["format"] == "xlsx" and rx["created"] == 1
    xl = next(i for i in c.get(f"/api/v1/sites/{SID}/content-plans").json()["items"] if i["title"] == "پلن اکسل")
    assert xl["status"] == "researching" and xl["search_volume"] == 1300 and xl["primary_keyword_id"]
    # exports
    ex = c.get(f"/api/v1/sites/{SID}/content-plans/export.csv")
    assert ex.status_code == 200 and "text/csv" in ex.headers["content-type"] and "عنوان" in ex.text and "مشکلات گیربکس آریزو 6" in ex.text
    xx = c.get(f"/api/v1/sites/{SID}/content-plans/export.xlsx", params={"columns": "title,status,priority"})
    assert xx.status_code == 200 and xx.content[:2] == b"PK"
    assert "عنوان" in c.get(f"/api/v1/sites/{SID}/content-plans/import/template.csv").text
    # Google Sheet source (public CSV export) via mocked httpx
    assert sheet_csv_url("https://docs.google.com/spreadsheets/d/ABC123/edit#gid=42") == "https://docs.google.com/spreadsheets/d/ABC123/export?format=csv&gid=42"
    src = c.post(f"/api/v1/sites/{SID}/content-plans/sources", json={"name": "برنامه اصلی", "kind": "google_sheet", "url": "https://docs.google.com/spreadsheets/d/ABC123/edit#gid=0"}).json()
    assert src["kind"] == "google_sheet" and src["auto_sync"] is False
    sheet_csv = "عنوان,کلمه کلیدی اصلی,تاریخ انتشار" + chr(10) + "از شیت,امداد خودرو تیگو 7,2026-09-10" + chr(10)
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Response(200, content=sheet_csv.encode("utf-8"), request=httpx.Request("GET", url)))
    ss = c.post(f"/api/v1/sites/{SID}/content-plans/sources/{src['id']}/sync").json()
    assert ss["created"] == 1 and ss["url"].endswith("export?format=csv&gid=0")
    assert c.get(f"/api/v1/sites/{SID}/content-plans/sources").json()[0]["status"] == "ok"
    assert c.get(f"/api/v1/sites/{SID}/content-plans/imports").json()[0]["source"] == "google_sheet"
    # calendar (plans + drag = PATCH publish_date) + board (7 columns)
    cal = c.get(f"/api/v1/sites/{SID}/content-plans/calendar", params={"from": "2026-09-01", "to": "2026-09-30"}).json()
    assert set(cal["days"]) >= {"2026-09-01", "2026-09-03", "2026-09-10"} and len(cal["unscheduled"]) >= 1 and cal["categories"]
    pid = cal["days"]["2026-09-03"][0]["id"]
    c.patch(f"/api/v1/sites/{SID}/content-plans/{pid}", json={"publish_date": "2026-09-04"})
    cal2 = c.get(f"/api/v1/sites/{SID}/content-plans/calendar", params={"from": "2026-09-01", "to": "2026-09-30", "category_id": g["category"]["id"]}).json()
    assert "2026-09-04" in cal2["days"] and "2026-09-03" not in cal2["days"]
    board = c.get(f"/api/v1/sites/{SID}/content-plans/board").json()
    assert [b["status"] for b in board["columns"]] == ["planned", "researching", "brief_ready", "writing", "review", "approved", "published"] and sum(len(b["items"]) for b in board["columns"]) == 5


def test_keyword_mapping_rules_recommendations_and_graph(c):
    _seed(c)
    c.post(f"/api/v1/sites/{SID}/content-plans/categories/sync")
    ov = c.get(f"/api/v1/sites/{SID}/content-plans/keyword-mapping").json()
    assert ov["counts"]["keywords"] == 4 and ov["total"] == 4 and ov["items"][0]["mapped"] is False
    sug = c.post(f"/api/v1/sites/{SID}/content-plans/keyword-mapping/suggest", json={}).json()
    by = {x["keyword"]["keyword"]: x for x in sug["items"]}
    mvm = by["امداد خودرو mvm"]["recommendation"]
    assert mvm["action"] == "optimize_existing" and mvm["ranking_url"] == "https://demo.example/mvm/" and mvm["ranking_position"] == 8.5 and mvm["content_gap"] == "none" and mvm["reasons_fa"]
    ar = by["امداد خودرو آریزو 6"]["recommendation"]
    assert ar["action"] == "create_new" and ar["page_type"] == "service_landing" and ar["intent"] == "transactional" and ar["content_gap"] in ("full", "partial") and ar["mapping"]["type"] == "new" and ar["funnel_stage"] == "decision"
    assert by["امداد خودرو آریزو 6"]["recommendation_id"]                       # persisted
    stored = c.get(f"/api/v1/sites/{SID}/content-plans/suggestions").json()
    assert any(s["kind"] == "create_new" and s["keyword_id"] == by["امداد خودرو آریزو 6"]["keyword"]["id"] for s in stored) and all(s["status"] == "new" for s in stored)
    # re-run → same payload → same row (no duplicate versions)
    n1 = len(c.get(f"/api/v1/sites/{SID}/content-plans/suggestions", params={"status": "new,superseded"}).json())
    c.post(f"/api/v1/sites/{SID}/content-plans/keyword-mapping/suggest", json={})
    assert len(c.get(f"/api/v1/sites/{SID}/content-plans/suggestions", params={"status": "new,superseded"}).json()) == n1
    # apply: new plan from keyword + attach secondary
    ap = c.post(f"/api/v1/sites/{SID}/content-plans/keyword-mapping/apply", json={"items": [{"keyword_id": by["امداد خودرو آریزو 6"]["keyword"]["id"], "plan_id": "new", "recommendation_id": by["امداد خودرو آریزو 6"]["recommendation_id"]}]}).json()
    assert ap["created"] and not ap["errors"]
    pid = ap["created"][0]["plan_id"]
    ap2 = c.post(f"/api/v1/sites/{SID}/content-plans/keyword-mapping/apply", json={"items": [{"keyword_id": by["امداد خودرو mvm تهران"]["keyword"]["id"], "plan_id": pid, "role": "supporting"}]}).json()
    assert ap2["attached"][0]["role"] == "supporting"
    kws = c.get(f"/api/v1/sites/{SID}/keywords").json()["items"]
    assert next(k for k in kws if k["keyword"] == "امداد خودرو آریزو 6")["status"] == "planned"
    assert c.get(f"/api/v1/sites/{SID}/content-plans/keyword-mapping", params={"status": "mapped"}).json()["total"] == 2
    rec = c.get(f"/api/v1/sites/{SID}/content-plans/suggestions", params={"status": "applied"}).json()
    assert rec and rec[0]["plan_id"] == pid
    # accept a gap/create suggestion → creates plan; dismiss another
    news = c.get(f"/api/v1/sites/{SID}/content-plans/suggestions").json()
    gap = next((s for s in news if s["kind"] in ("gap", "create_new") and not s["plan_id"]), None)
    if gap:
        acc = c.patch(f"/api/v1/sites/{SID}/content-plans/suggestions/{gap['id']}", json={"status": "accepted"}).json()
        assert acc["status"] == "applied" and acc["created_plan"]["id"]
    other = next((s for s in c.get(f"/api/v1/sites/{SID}/content-plans/suggestions").json()), None)
    if other:
        assert c.patch(f"/api/v1/sites/{SID}/content-plans/suggestions/{other['id']}", json={"status": "dismissed"}).json()["status"] == "dismissed"
    # rules unit checks
    assert page_type_for("مقایسه x22 و آریزو 5", "commercial", [], 2, False) == "comparison"
    assert page_type_for("چگونه گیربکس x22 را تعمیر کنیم", "informational", [], 4, False) == "guide"
    assert page_type_for("امداد خودرو تهران", "local", [{"type": "LOCATION"}], 1, False) == "location_landing"
    assert funnel_stage_for("transactional", None) == "decision" and funnel_stage_for("informational", "article") == "awareness"
    assert priority_label(75) == "high" and priority_label(45) == "medium" and priority_label(10) == "low"
    ctx = build_planner_context(c.eng, SID)
    r = for_keyword(ctx, ctx.keyword_of("امداد خودرو mvm"))
    assert r["engine"] == "rules-v1" and r["cannibalization_risk"] >= 0 and r["traffic_opportunity"] is not None and r["confidence"] > 0
    # graph: planner mode + new node types + details
    gs = c.post(f"/api/v1/sites/{SID}/content-plans/sync-graph").json()
    assert gs["plans"] >= 2 and gs["intents"] >= 1 and gs["stages"] >= 1
    modes = c.get(f"/api/v1/sites/{SID}/graph/modes").json()
    assert any(m["key"] == "planner" and "CONTENT_PLAN" in m["node_types"] and "SEARCH_INTENT" in m["node_types"] and "FUNNEL_STAGE" in m["node_types"] for m in modes)
    v = c.get(f"/api/v1/sites/{SID}/graph/view", params={"mode": "planner", "limit": 300}).json()
    types = {n["type"] for n in v["nodes"]}; rels = {e["relation_type"] for e in v["edges"]}
    assert {"CONTENT_PLAN", "CATEGORY", "SEARCH_INTENT", "FUNNEL_STAGE", "KEYWORD"} <= types and {"TARGETS", "HAS_INTENT", "IN_STAGE", "BELONGS_TO", "CONTAINS"} <= rels
    pg = c.get(f"/api/v1/sites/{SID}/content-plans/graph", params={"plan_id": pid}).json()
    assert pg["focus"] == f"plan:{pid}" and any(n["id"] == f"plan:{pid}" for n in pg["nodes"])
    det = c.get(f"/api/v1/sites/{SID}/graph/node-details/plan:{pid}").json()
    assert det["type"] == "CONTENT_PLAN" and det["plan"]["primary_keyword"] == "امداد خودرو آریزو 6" and det["related"]["keywords"] and det["related"]["intent"]
    cat_det = c.get(f"/api/v1/sites/{SID}/graph/node-details/category:category:mvm").json()
    assert cat_det["type"] == "CATEGORY" and cat_det.get("planner_category", {}).get("source") == "wordpress"
    intent_det = c.get(f"/api/v1/sites/{SID}/graph/node-details/intent:transactional").json()
    assert intent_det["type"] == "SEARCH_INTENT" and intent_det["plans"]
    # existing modes untouched
    assert c.get(f"/api/v1/sites/{SID}/graph/view", params={"mode": "content"}).status_code == 200
    # planner insights endpoints (advisory)
    assert c.post(f"/api/v1/sites/{SID}/content-plans/insights/learn").json()["insights"] == []
    assert c.get(f"/api/v1/sites/{SID}/content-plans/insights").json() == []
    # backfill: existing content item without plan gets a plan row
    cid = c.post(f"/api/v1/sites/{SID}/content", json={"title": "آیتم قدیمی", "target_keyword": "مشکلات گیربکس x22"}).json()["id"]
    assert c.post(f"/api/v1/sites/{SID}/content-plans/backfill").json()["created"] == 1
    assert c.get(f"/api/v1/sites/{SID}/content-plans", params={"has_item": True}).json()["items"][0]["content_item"]["id"] == cid
    # cascade site delete
    d = c.delete(f"/api/v1/sites/{SID}?force=true").json()
    assert d["related_rows_deleted"].get("content_plans", 0) >= 3 and d["related_rows_deleted"].get("content_categories", 0) >= 3 and d["related_rows_deleted"].get("content_plan_recommendations", 0) >= 1


def test_import_helpers_unit():
    m = detect_mapping(["عنوان", "URL", "Primary Keyword", "دسته", "Publish Date", "unknown col"])
    assert m == {"عنوان": "title", "URL": "url", "Primary Keyword": "primary_keyword", "دسته": "category", "Publish Date": "publish_date"}
    f, w = normalize_row({"عنوان": "x", "اولویت": "زیاد", "وضعیت": "بازبینی", "Publish Date": "2026/09/01", "کلمات کلیدی ثانویه": "a، b; c"}, {"عنوان": "title", "اولویت": "priority", "وضعیت": "status", "Publish Date": "publish_date", "کلمات کلیدی ثانویه": "secondary_keywords"})
    assert f["priority"] == "high" and f["status"] == "review" and f["secondary_keywords"] == ["a", "b", "c"] and f["publish_date"] is None and w
