"""Commercial search signals must stay separate from sales claims."""
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.routers import commerce
from seo_brain.api.main import create_app
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate


def test_sales_path_scopes_commercial_pages_and_preserves_unknown_sales(tmp_path, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    eng = make_engine("sqlite:///" + (tmp_path / "sales.db").as_posix())
    migrate(eng)
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app)
    for site in ("one", "two"):
        assert client.post("/api/v1/sites", json={"site_id": site, "name": site, "canonical_url": f"https://{site}.example/"}).status_code == 201
    with eng.begin() as cx:
        cx.execute(text("""
            INSERT INTO pages(site_id,url,crawl_status) VALUES
            ('one','https://one.example/product/shirt/','ok'),
            ('one','https://one.example/category/shirts/','ok'),
            ('one','https://one.example/blog/style/','ok')
        """))
        cx.execute(text("""
            INSERT INTO gsc_daily(site_id,date,page,query,clicks,impressions,position) VALUES
            ('one','2026-09-09','https://one.example/product/shirt/','shirt',3,30,8),
            ('one','2026-10-09','https://one.example/product/shirt/','shirt',5,50,6),
            ('one','2026-10-10','https://one.example/category/shirts/','shirts',7,70,5),
            ('one','2026-10-10','https://one.example/blog/style/','style',100,200,2),
            ('two','2026-10-10','https://two.example/product/secret/','secret',999,999,1)
        """))
        cx.execute(text("""INSERT INTO issue_cases(site_id,fingerprint,problem_type,url,severity,first_seen,last_seen)
                           VALUES('one','issue','missing_h1','https://one.example/category/shirts/','medium','2026-10-10','2026-10-10')"""))
        cx.execute(text("""INSERT INTO keywords
            (site_id,keyword,normalized,created_at,updated_at)
            VALUES ('one','shirt','shirt','2026-10-10','2026-10-10')"""))
        cx.execute(text("""INSERT INTO keyword_opportunities
            (site_id,keyword_id,kind,target_url,score,created_at,updated_at)
            VALUES ('one',1,'missing_content','https://one.example/product/shirt',0.7,'2026-10-10','2026-10-10')"""))
        cx.execute(text("""INSERT INTO link_suggestions
            (site_id,kind,source_node_id,target_node_id,target_url,score,confidence,created_at,updated_at)
            VALUES ('one','contextual','source','target','https://one.example/product/shirt',0.8,'high','2026-10-10','2026-10-10')"""))
    response = client.get("/api/v1/sites/one/commerce/path", params={"days": 28})
    assert response.status_code == 200
    data = response.json()
    assert data["latest_gsc_date"] == "2026-10-10"
    assert data["sales_measurement"] == "unavailable"
    assert data["coverage"] == "gsc_observed_top_rows_only"
    assert sum(stage["clicks"] for stage in data["stages"]) == 12
    assert data["previous_total_clicks"] == 3
    assert data["inventory"] == {"product": 1, "category": 1, "shop": 0}
    assert len(data["top_pages"]) == 2
    category = next(item for item in data["top_pages"] if item["kind"] == "category")
    assert category["open_issues"] == 1 and category["previous_clicks"] is None
    product = next(item for item in data["top_pages"] if item["kind"] == "product")
    assert product["new_keyword_opportunities"] == 1
    assert product["new_link_suggestions"] == 1
    assert any(item["url"] == product["url"] and item["new_link_suggestions"] == 1
               for item in data["priority_pages"])
    assert all("two.example" not in item["url"] for item in data["top_pages"])
    assert client.get("/api/v1/sites/one/commerce/measurement").json()["status"] == "not_configured"
    with eng.begin() as cx:
        cx.execute(text("UPDATE sites SET ga4_property='properties/123' WHERE site_id='one'"))
    monkeypatch.setattr(commerce, "_ga4_channel_report", lambda *args: {
        "status": "reported", "source": "ga4_data_api", "days": args[2],
        "channels": [{"channel": "Organic Search", "sessions": 12, "transactions": 0, "purchase_revenue": 0}],
        "organic_search": {"channel": "Organic Search", "sessions": 12, "transactions": 0, "purchase_revenue": 0},
        "tracking_verified": False})
    measured = client.get("/api/v1/sites/one/commerce/measurement").json()
    assert measured["organic_search"]["sessions"] == 12
    assert measured["tracking_verified"] is False
    assert client.get("/api/v1/sites/missing/commerce/path").status_code == 404
