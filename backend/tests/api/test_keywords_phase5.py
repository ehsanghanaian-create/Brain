"""Phase 5 — Keyword Intelligence: normalization, import (csv/xlsx/persian headers), CRUD, clustering, opportunities, graph sync."""
import io

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import graph as graph_router
from seo_brain.api.routers import sites as sites_router
from seo_brain.brain.keywords import cluster_keywords, normalize_keyword, tokenize
from seo_brain.brain.keywords.repository import Keyword
from seo_brain.database.db import connect as legacy_connect
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate

SID = "demo"


@pytest.fixture
def c(tmp_path, monkeypatch):
    dbfile = tmp_path / "kw.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(graph_router, "connect", lambda: legacy_connect(dbfile))
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app)
    assert client.post("/api/v1/sites", json={"site_id": SID, "name": "Demo", "canonical_url": "https://demo.example/"}).status_code == 201
    client.post(f"/api/v1/sites/{SID}/initialize")
    client.eng = eng  # type: ignore[attr-defined]
    return client


def _seed_gsc_and_pages(eng):
    """Two pages in the graph + GSC rows for three queries + links table (inbound counts)."""
    with eng.begin() as cx:
        for url, label in (("https://demo.example/mvm/", "MVM"), ("https://demo.example/blog/", "Blog")):
            cx.execute(text("INSERT INTO graph_nodes(site_id,node_id,node_type,label,url,props,updated_at) VALUES(:s,:n,'PAGE',:l,:u,'{}',datetime('now'))"),
                       {"s": SID, "n": f"page:{url}", "l": label, "u": url})
            cx.execute(text("INSERT INTO pages(site_id,url,final_url,status_code) VALUES(:s,:u,:u,200)"), {"s": SID, "u": url})
        gsc = [("امداد خودرو mvm", "https://demo.example/mvm/", 2, 300, 0.0067, 8.5),
               ("امداد خودرو mvm", "https://demo.example/blog/", 0, 20, 0.0, 14.0),
               ("امداد خودرو ام وی ام تهران", "https://demo.example/mvm/", 0, 60, 0.0, 4.2),
               ("خرابی خودرو در جاده", "https://demo.example/blog/", 0, 8, 0.0, 35.0)]
        for q, p, cl, imp, ctr, pos in gsc:
            cx.execute(text("INSERT INTO gsc_query_page(site_id,page,query,clicks,impressions,ctr,position) VALUES(:s,:p,:q,:c,:i,:r,:o)"),
                       {"s": SID, "p": p, "q": q, "c": cl, "i": imp, "r": ctr, "o": pos})
        # blog has 1 inbound link, mvm has 5
        for i in range(5):
            cx.execute(text("INSERT INTO links(site_id,source_url,target_url,anchor_text,is_internal,is_nav) VALUES(:s,:src,'https://demo.example/mvm/','x',1,0)"), {"s": SID, "src": f"https://demo.example/p{i}/"})
        cx.execute(text("INSERT INTO links(site_id,source_url,target_url,anchor_text,is_internal,is_nav) VALUES(:s,'https://demo.example/','https://demo.example/blog/','x',1,0)"), {"s": SID})


def test_normalize_and_tokenize():
    assert normalize_keyword("امداد خودرو  MVM  ") == "امداد خودرو mvm"
    assert normalize_keyword("امداد‌خودرو ي ك ۱۲۳") == "امداد خودرو ی ک 123"      # ZWNJ→space, Arabic ي/ك→Persian, digits
    assert normalize_keyword("Best Car TOWING!") == "best car towing"
    assert tokenize("بهترین امداد خودرو در تهران") == ["امداد", "خودرو", "تهران"]


def test_import_csv_persian_headers_dry_run_then_write(c):
    csv = "کلمه کلیدی,اینتنت,موضوع,حجم,اولویت,صفحه هدف,وضعیت\nامداد خودرو mvm,تراکنشی,امداد MVM,۱٬۳۰۰,بالا,https://demo.example/mvm/,برنامه\nامداد خودرو MVM,,,,,,\n,,,,,,\nخرابی خودرو در جاده,اطلاعاتی,,90,کم,,\n"
    r = c.post(f"/api/v1/sites/{SID}/keywords/import", files={"file": ("kw.csv", csv.encode("utf-8"), "text/csv")}, data={"dry_run": "true"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dry_run"] and d["format"] == "csv" and d["mapping"]["کلمه کلیدی"] == "keyword" and d["mapping"]["حجم"] == "volume"
    assert d["rows_total"] == 3 and d["rows_valid"] == 2 and d["rows_skipped"] == 1 and "تکراری" in d["errors"][0]["error"]
    assert d["preview"][0]["volume"] == 1300 and d["preview"][0]["intent"] == "transactional" and d["preview"][0]["priority"] == "high" and d["preview"][0]["status"] == "planned"
    assert c.get(f"/api/v1/sites/{SID}/keywords").json()["total"] == 0          # dry run wrote nothing
    r = c.post(f"/api/v1/sites/{SID}/keywords/import", files={"file": ("kw.csv", csv.encode("utf-8"), "text/csv")}, data={"dry_run": "false"})
    d = r.json()
    assert d["rows_imported"] == 2 and d["import_id"] and c.get(f"/api/v1/sites/{SID}/keywords").json()["total"] == 2
    # re-import updates instead of duplicating
    d2 = c.post(f"/api/v1/sites/{SID}/keywords/import", files={"file": ("kw.csv", csv.encode("utf-8"), "text/csv")}, data={"dry_run": "false"}).json()
    assert d2["rows_imported"] == 0 and d2["rows_updated"] == 2
    assert len(c.get(f"/api/v1/sites/{SID}/keywords/imports").json()) == 2
    assert c.get(f"/api/v1/sites/{SID}/keywords/template.csv").status_code == 200


def test_import_xlsx_with_mapping_override_and_missing_keyword_column(c):
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Query", "Avg. monthly searches", "URL", "Weird"])
    ws.append(["امداد خودرو تیگو", 500, "https://demo.example/tiggo/", "x"])
    ws.append(["امداد خودرو چری", "1,200", "", "y"])
    buf = io.BytesIO(); wb.save(buf)
    r = c.post(f"/api/v1/sites/{SID}/keywords/import", files={"file": ("kw.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, data={"dry_run": "true"})
    d = r.json()
    assert d["format"] == "xlsx" and d["mapping"] == {"Query": "keyword", "Avg. monthly searches": "volume", "URL": "target_url"} and d["unmapped_columns"] == ["Weird"]
    assert d["preview"][1]["volume"] == 1200
    # explicit mapping override: use "Weird" as notes
    r = c.post(f"/api/v1/sites/{SID}/keywords/import", files={"file": ("kw.xlsx", buf.getvalue(), "application/octet-stream")},
               data={"dry_run": "false", "mapping": '{"Query":"keyword","Weird":"notes"}'})
    assert r.json()["rows_imported"] == 2 and c.get(f"/api/v1/sites/{SID}/keywords?q=تیگو").json()["items"][0]["notes"] == "x"
    # no keyword column
    r = c.post(f"/api/v1/sites/{SID}/keywords/import", files={"file": ("bad.csv", b"a,b\n1,2\n", "text/csv")}, data={"dry_run": "true"})
    assert r.json()["rows_valid"] == 0 and "کلمه کلیدی" in r.json()["errors"][0]["error"]
    assert c.post(f"/api/v1/sites/{SID}/keywords/import", files={"file": ("e.csv", b"", "text/csv")}).status_code == 400


def test_crud_and_list_filters(c):
    r = c.post(f"/api/v1/sites/{SID}/keywords", json={"keyword": "امداد خودرو تهران", "intent": "local", "priority": "high", "volume": 880})
    assert r.status_code == 201, r.text
    kid = r.json()["id"]
    assert c.post(f"/api/v1/sites/{SID}/keywords", json={"keyword": "امداد  خودرو تهران"}).status_code == 409   # same normalized
    assert c.post(f"/api/v1/sites/{SID}/keywords", json={"keyword": "x", "intent": "nope"}).status_code == 422
    r = c.patch(f"/api/v1/sites/{SID}/keywords/{kid}", json={"status": "planned", "target_url": "https://demo.example/tehran/", "difficulty": 33.5})
    assert r.json()["status"] == "planned" and r.json()["difficulty"] == 33.5
    lst = c.get(f"/api/v1/sites/{SID}/keywords", params={"status": "planned", "intent": "local", "sort": "volume", "order": "desc"}).json()
    assert lst["total"] == 1 and lst["items"][0]["id"] == kid and lst["counts"]["total"] == 1 and lst["counts"]["with_target"] == 1
    assert c.get(f"/api/v1/sites/{SID}/keywords", params={"q": "تهران"}).json()["total"] == 1
    assert c.get(f"/api/v1/sites/{SID}/keywords", params={"q": "zzz"}).json()["total"] == 0
    d = c.get(f"/api/v1/sites/{SID}/keywords/{kid}").json()
    assert d["keyword"] == "امداد خودرو تهران" and d["gsc"] is None and d["opportunities"] == []
    assert c.get(f"/api/v1/sites/{SID}/keywords/meta").json()["intents"][0] == "informational"
    assert c.delete(f"/api/v1/sites/{SID}/keywords/{kid}").json() == {"deleted": kid}
    assert c.get(f"/api/v1/sites/{SID}/keywords/{kid}").status_code == 404


def test_clustering_idf_groups_by_discriminating_tokens():
    kws = [Keyword(SID, "امداد خودرو mvm", id=1), Keyword(SID, "امداد خودرو mvm تهران", id=2), Keyword(SID, "امداد خودرو mvm کرج", id=3),
           Keyword(SID, "امداد خودرو چری", id=4), Keyword(SID, "امداد خودرو چری تهران", id=5), Keyword(SID, "قیمت لنت ترمز", id=6),
           Keyword(SID, "امداد خودرو تیگو", id=7, cluster_id="m-manual", topic="تیگو")]
    clusters, assign = cluster_keywords(kws)
    by = {}
    for kid, cid in assign.items():
        by.setdefault(cid, set()).add(kid)
    groups = sorted(sorted(v) for v in by.values())
    assert [1, 2, 3] in groups and [4, 5] in groups and [6] in groups and [7] in groups   # manual cluster preserved
    mvm = next(cl for cl in clusters if cl.keywords_count == 3)
    assert mvm.name == "امداد خودرو mvm" and "mvm" in mvm.topic
    manual = next(cl for cl in clusters if cl.method == "manual")
    assert manual.topic == "تیگو"


def test_end_to_end_gsc_opportunities_topic_map_and_graph(c):
    _seed_gsc_and_pages(c.eng)
    csv = "keyword,priority,volume,target_url\nامداد خودرو mvm,high,1300,\nامداد خودرو ام وی ام تهران,medium,200,\nخرابی خودرو در جاده,low,50,\nشماره امداد خودرو,high,900,\n"
    assert c.post(f"/api/v1/sites/{SID}/keywords/import", files={"file": ("k.csv", csv.encode(), "text/csv")}, data={"dry_run": "false"}).json()["rows_imported"] == 4
    lst = c.get(f"/api/v1/sites/{SID}/keywords").json()
    g = {i["keyword"]: i["gsc"] for i in lst["items"]}
    assert g["امداد خودرو mvm"]["impressions"] == 320 and g["امداد خودرو mvm"]["position"] == 8.8 and g["امداد خودرو mvm"]["top_page"] == "https://demo.example/mvm/"
    assert g["شماره امداد خودرو"] is None
    # opportunities
    a = c.post(f"/api/v1/sites/{SID}/keywords/analyze", params={"min_impressions": 5}).json()
    assert a["with_gsc"] == 3 and a["opportunities"] >= 4 and a["graph"]["keywords"] == 4
    opps = c.get(f"/api/v1/sites/{SID}/keywords/opportunities").json()["items"]
    kinds = {(o["keyword"], o["kind"]) for o in opps}
    assert ("امداد خودرو mvm", "improve_page") in kinds            # pos 8.8, 320 imp
    assert ("امداد خودرو mvm", "update_title") in kinds            # ctr 0.6% vs ~3.5% expected
    assert ("شماره امداد خودرو", "create_content") in kinds        # no GSC data, no target
    assert ("خرابی خودرو در جاده", "create_content") in kinds      # position 35 > 20
    assert ("امداد خودرو ام وی ام تهران", "add_internal_links") not in kinds  # target mvm has 5 inbound
    for o in opps:
        assert 0 < o["score"] <= 1 and o["reason"] and o["kind_fa"]
    # status change + re-analyze keeps accepted
    oid = next(o["id"] for o in opps if o["kind"] == "create_content")
    assert c.patch(f"/api/v1/sites/{SID}/keywords/opportunities/{oid}", json={"status": "accepted"}).json()["status"] == "accepted"
    c.post(f"/api/v1/sites/{SID}/keywords/analyze")
    assert c.get(f"/api/v1/sites/{SID}/keywords/opportunities", params={"status": "accepted"}).json()["total"] == 1
    # topic map + clusters
    cl = c.post(f"/api/v1/sites/{SID}/keywords/cluster").json()
    assert cl["clusters"] >= 2
    tm = c.get(f"/api/v1/sites/{SID}/keywords/topic-map").json()
    assert sum(x["keywords_count"] for x in tm["clusters"]) == 4 and tm["unclustered"] == []
    big = tm["clusters"][0]
    assert big["gsc"]["impressions"] >= 0 and "members" in big
    cid = big["cluster_id"]
    assert c.patch(f"/api/v1/sites/{SID}/keywords/clusters/{cid}", json={"topic": "موضوع دستی"}).json()["topic"] == "موضوع دستی"
    c.post(f"/api/v1/sites/{SID}/keywords/cluster")
    assert next(x for x in c.get(f"/api/v1/sites/{SID}/keywords/clusters").json() if x["cluster_id"] == cid)["topic"] == "موضوع دستی"
    # graph integration: KEYWORD + TOPIC nodes, CLUSTERED_IN + KEYWORD_TARGETS edges visible in the SEO map
    v = c.get(f"/api/v1/sites/{SID}/graph/view", params={"mode": "seo", "types": "KEYWORD,TOPIC,PAGE"}).json()
    assert v["stats"]["by_type"]["KEYWORD"] == 4 and v["stats"]["by_type"]["TOPIC"] == cl["clusters"]
    assert v["stats"]["by_relation"]["CLUSTERED_IN"] == 4 and v["stats"]["by_relation"]["KEYWORD_TARGETS"] >= 2
    kd = c.get(f"/api/v1/sites/{SID}/graph/node-details/keyword:{lst['items'][0]['id']}").json()
    assert kd["type"] == "KEYWORD" and "keyword" in kd
    # deleting a keyword removes its opportunities and (after sync) its node
    kid = next(i["id"] for i in lst["items"] if i["keyword"] == "شماره امداد خودرو")
    c.delete(f"/api/v1/sites/{SID}/keywords/{kid}")
    assert c.get(f"/api/v1/sites/{SID}/keywords/opportunities", params={"keyword_id": kid}).json()["total"] == 0
    c.post(f"/api/v1/sites/{SID}/keywords/sync-graph")
    assert c.get(f"/api/v1/sites/{SID}/graph/view", params={"mode": "seo", "types": "KEYWORD"}).json()["stats"]["by_type"]["KEYWORD"] == 3
