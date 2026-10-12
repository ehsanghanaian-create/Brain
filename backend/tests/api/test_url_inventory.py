"""URL inventory keeps source evidence separate and never implies zero for missing GSC."""
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate


def test_inventory_union_filters_pagination_and_site_scope(tmp_path, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    eng = make_engine("sqlite:///" + (tmp_path / "inventory.db").as_posix())
    migrate(eng)
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app)
    for site in ("one", "two"):
        assert client.post("/api/v1/sites", json={"site_id": site, "name": site, "canonical_url": f"https://{site}.example/"}).status_code == 201
    with eng.begin() as cx:
        cx.execute(text("INSERT INTO posts(site_id,wp_id,type,url,title,status) VALUES('one',1,'page','https://one.example/a/','Page A','publish')"))
        cx.execute(text("INSERT INTO pages(site_id,url,title,crawl_status,status_code,indexable,in_sitemap,last_crawled) VALUES('one','https://one.example/a/','Crawl A','ok',200,1,1,'2026-10-11')"))
        cx.execute(text("INSERT INTO gsc_query_page(site_id,page,query,clicks,impressions,position,date_from,date_to) VALUES('one','https://one.example/a/','query',3,100,8,'2026-10-01','2026-10-08')"))
        cx.execute(text("INSERT INTO gsc_query_page(site_id,page,query,clicks,impressions,position,date_from,date_to) VALUES('one','https://one.example/a/','query 2',2,50,12,'2026-10-01','2026-10-08')"))
        cx.execute(text("INSERT INTO pages(site_id,url,crawl_status,status_code) VALUES('one','https://one.example/b/','error',500)"))
        cx.execute(text("INSERT INTO posts(site_id,wp_id,type,url,title,status) VALUES('one',2,'post','https://one.example/c/','Page C','publish')"))
        cx.execute(text("INSERT INTO posts(site_id,wp_id,type,url,title,status) VALUES('two',1,'page','https://two.example/private/','Private','publish')"))
        cx.execute(text("INSERT INTO crawl_runs(run_id,site_id,started_at,status,max_urls,urls_crawled) VALUES('crawl-1','one','2026-10-11','completed',2,2)"))
    base = "/api/v1/sites/one/urls"
    response = client.get(base).json()
    assert response["total"] == 3
    assert response["coverage"]["crawl"]["max_urls"] == 2
    assert response["coverage"]["gsc_scope"] == "observed_top_rows_only"
    assert response["coverage"]["missing_source_means_zero"] is False
    a = next(x for x in response["items"] if x["url"].endswith("/a/"))
    assert a["sources"] == ["wordpress", "crawl", "gsc"]
    assert a["gsc_clicks"] == 5 and a["gsc_impressions"] == 150
    assert round(a["gsc_position"], 2) == 9.33
    assert next(x for x in response["items"] if x["url"].endswith("/c/"))["gsc_clicks"] is None
    assert client.get(base, params={"source": "gsc"}).json()["total"] == 1
    assert client.get(base, params={"source": "crawl"}).json()["total"] == 2
    assert client.get(base, params={"search": "Page C"}).json()["total"] == 1
    assert client.get(base, params={"limit": 1, "offset": 1}).json()["items"][0]["url"].endswith("/b/")
    assert client.get(base, params={"source": "invalid"}).status_code == 422
    assert client.get("/api/v1/sites/two/urls").json()["total"] == 1
    assert client.get("/api/v1/sites/missing/urls").status_code == 404
    with eng.begin() as cx:
        cx.execute(text("INSERT INTO gsc_daily(site_id,date,page,query,clicks,impressions,position) VALUES('one','2026-09-03','https://one.example/a/','query',2,20,10),('one','2026-10-03','https://one.example/a/','query',4,40,8),('one','2026-10-04','https://one.example/a/','second',1,10,12)"))
        cx.execute(text("INSERT INTO issue_cases(site_id,fingerprint,problem_type,url,severity,first_seen,last_seen) VALUES('one','one-issue','missing_h1','https://one.example/a/','medium','2026-09-01','2026-10-11')"))
        cx.execute(text("INSERT INTO keywords(site_id,keyword,normalized) VALUES('one','query','query')"))
        cx.execute(text("INSERT INTO keyword_opportunities(site_id,keyword_id,kind,target_url,score) VALUES('one',1,'improve_page','https://one.example/a/',0.8)"))
    detail = client.get(base + "/detail", params={"url": "https://one.example/a/"}).json()
    assert detail["inventory"]["sources"] == ["wordpress", "crawl", "gsc"]
    assert [(m["month"], m["clicks"]) for m in detail["monthly_gsc"]] == [("2026-09", 2), ("2026-10", 5)]
    assert round(detail["monthly_gsc"][-1]["position"], 1) == 8.8
    assert detail["gsc_latest_date"] == "2026-10-04"
    assert detail["top_queries"][0]["query"] == "query"
    assert detail["issue_cases"][0]["problem_type"] == "missing_h1"
    assert detail["new_keyword_opportunities"] == 1
    assert detail["missing_month_means_zero"] is False
    empty = client.get(base + "/detail", params={"url": "https://one.example/c/"}).json()
    assert empty["monthly_gsc"] == [] and empty["gsc_latest_date"] is None
    assert client.get(base + "/detail", params={"url": "https://two.example/private/"}).status_code == 404
