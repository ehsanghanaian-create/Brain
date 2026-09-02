"""Site Report Center tests: summary, main keyword, keyword performance (weighted position),
problems/opportunities exposure, backlink & reportage CRUD + verification, site isolation."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import reports as reports_router
from seo_brain.api.routers import sites as sites_router
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate


@pytest.fixture
def client(tmp_path, monkeypatch):
    dbfile = tmp_path / "api.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix())
    migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    c = TestClient(app)
    c.eng = eng  # type: ignore[attr-defined]
    return c


def _seed(c: TestClient, site_id: str = "demo"):
    r = c.post("/api/v1/sites", json={"site_id": site_id, "name": site_id, "canonical_url": f"https://{site_id}.example/",
                                       "wp_url": f"https://{site_id}.example"})
    assert r.status_code == 201, r.text


def _seed_gsc(c: TestClient, site_id: str = "demo"):
    """Two 7-day windows: keyword moved from position 8 (prev) to 4 (current)."""
    with c.eng.begin() as cx:
        for day, pos, clicks in (("2026-08-01", 8.0, 2), ("2026-08-03", 8.0, 2),      # previous window
                                 ("2026-08-08", 4.0, 10), ("2026-08-10", 4.0, 10)):    # current window
            cx.execute(text("""INSERT INTO gsc_daily(site_id, date, page, query, country, device, clicks, impressions, ctr, position)
                               VALUES(:s,:d,'https://demo.example/a','امداد خودرو رنو','irn','MOBILE',:c,100,:c/100.0,:p)"""),
                       {"s": site_id, "d": day, "c": clicks, "p": pos})
        # a second query only in the current window
        cx.execute(text("""INSERT INTO gsc_daily(site_id, date, page, query, country, device, clicks, impressions, ctr, position)
                           VALUES(:s,'2026-08-09','https://demo.example/b','امداد رنو تهران','irn','DESKTOP',5,50,0.1,6.0)"""),
                   {"s": site_id})


def test_summary_empty_site_is_honest(client):
    _seed(client)
    body = client.get("/api/v1/sites/demo/report/summary").json()
    assert body["gsc"]["available"] is False
    assert body["ga4"]["available"] is False
    assert body["main_keyword"]["keyword"] is None
    assert body["counts"]["backlinks"] == 0 and body["counts"]["reportages"] == 0
    assert 0 <= body["score"] <= 100  # penalised for missing connections, still real


def test_main_keyword_set_and_weighted_position(client):
    _seed(client)
    _seed_gsc(client)
    # suggestions come from real GSC queries
    sug = client.get("/api/v1/sites/demo/report/main-keyword").json()["suggestions"]
    assert "امداد خودرو رنو" in [s["query"] for s in sug]
    r = client.put("/api/v1/sites/demo/report/main-keyword", json={"keyword": "امداد خودرو رنو"})
    assert r.status_code == 200
    body = client.get("/api/v1/sites/demo/report/main-keyword?days=7").json()
    perf = body["performance"]
    assert perf is not None
    assert perf["position"] == pytest.approx(4.0)           # current window, impression-weighted
    assert perf["prev_position"] == pytest.approx(8.0)      # previous window
    assert perf["clicks"] == 20
    assert perf["landing_page"] == "https://demo.example/a"
    # summary embeds the same performance block
    s = client.get("/api/v1/sites/demo/report/summary?days=7").json()
    assert s["main_keyword"]["keyword"] == "امداد خودرو رنو"
    assert s["main_keyword"]["performance"]["position"] == pytest.approx(4.0)


def test_keyword_performance_table_change_and_filters(client):
    _seed(client)
    _seed_gsc(client)
    body = client.get("/api/v1/sites/demo/report/keywords?days=7&order=clicks").json()
    assert body["status"] == "OK" and body["total"] == 2
    top = body["items"][0]
    assert top["query"] == "امداد خودرو رنو"
    assert top["change"] == pytest.approx(4.0)              # 8 -> 4 means +4 improvement
    assert top["landing_page"] == "https://demo.example/a"
    only = client.get("/api/v1/sites/demo/report/keywords?days=7&q=تهران").json()
    assert only["total"] == 1 and only["items"][0]["query"] == "امداد رنو تهران"
    assert only["items"][0]["prev_position"] is None and only["items"][0]["change"] is None


def test_problems_and_opportunities_exposed_with_categories(client):
    _seed(client)
    with client.eng.begin() as cx:
        cx.execute(text("""INSERT INTO seo_problems(site_id, problem_type, severity, url, detail)
                           VALUES('demo','orphan','high','https://demo.example/a','{}'),
                                 ('demo','missing_meta_description','low','https://demo.example/b',NULL)"""))
        cx.execute(text("""INSERT INTO seo_opportunities(site_id, opp_type, url, query, score, reason)
                           VALUES('demo','striking_distance','https://demo.example/a','امداد خودرو رنو',0.8,'r')"""))
    probs = client.get("/api/v1/sites/demo/report/problems").json()
    assert probs["summary"]["orphan"]["count"] == 1
    assert probs["items"][0]["severity"] == "high"          # ordered high first
    assert probs["items"][0]["category"] == "internal_linking"
    assert all(it["source"] == "crawler" for it in probs["items"])
    high_only = client.get("/api/v1/sites/demo/report/problems?severity=high").json()
    assert len(high_only["items"]) == 1
    opps = client.get("/api/v1/sites/demo/report/opportunities").json()
    assert opps["summary"]["striking_distance"]["count"] == 1
    assert opps["items"][0]["type_fa"].startswith("کلمات نزدیک")


def test_backlink_crud_and_totals(client):
    _seed(client)
    r = client.post("/api/v1/sites/demo/report/backlinks", json={
        "source_url": "https://news.example/post", "target_url": "https://demo.example/a",
        "anchor_text": "امداد خودرو رنو", "rel": "follow", "status": "active"})
    assert r.status_code == 201
    bid = r.json()["id"]
    dup = client.post("/api/v1/sites/demo/report/backlinks", json={
        "source_url": "https://news.example/post", "target_url": "https://demo.example/a"})
    assert dup.status_code == 409
    body = client.get("/api/v1/sites/demo/report/backlinks").json()
    assert body["totals"] == {"total": 1, "active": 1, "lost": 0, "follow": 1, "nofollow": 0, "referring_domains": 1}
    assert body["items"][0]["source_domain"] == "news.example"
    assert body["top_anchors"][0]["anchor_text"] == "امداد خودرو رنو"
    r = client.put(f"/api/v1/sites/demo/report/backlinks/{bid}", json={
        "source_url": "https://news.example/post", "target_url": "https://demo.example/a", "status": "lost"})
    assert r.status_code == 200
    assert client.get("/api/v1/sites/demo/report/backlinks").json()["totals"]["active"] == 0
    assert client.delete(f"/api/v1/sites/demo/report/backlinks/{bid}").status_code == 200
    assert client.delete(f"/api/v1/sites/demo/report/backlinks/{bid}").status_code == 404


def test_reportage_crud_and_verify(client, monkeypatch):
    _seed(client)
    r = client.post("/api/v1/sites/demo/report/reportages", json={
        "article_url": "https://mag.example/reportage-1", "target_url": "https://demo.example/a",
        "anchor_text": "امداد خودرو رنو", "target_keyword": "امداد خودرو رنو",
        "publication_date": "2026-08-01", "cost": 5000000, "status": "published"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    # verification is faked at the article-check boundary — no real HTTP in tests
    monkeypatch.setattr(reports_router, "_check_article",
                        lambda a, t: {"status": "link_found", "http_status": 200, "rel": "follow", "anchor": "امداد"})
    v = client.post(f"/api/v1/sites/demo/report/reportages/{rid}/verify").json()
    assert v["status"] == "link_found"
    item = client.get("/api/v1/sites/demo/report/reportages").json()["items"][0]
    assert item["status"] == "link_found" and item["verified_rel"] == "follow"
    assert item["verify_detail"]["http_status"] == 200
    monkeypatch.setattr(reports_router, "_check_article", lambda a, t: {"status": "link_missing", "http_status": 200})
    client.post(f"/api/v1/sites/demo/report/reportages/{rid}/verify")
    totals = client.get("/api/v1/sites/demo/report/reportages").json()["totals"]
    assert totals["link_missing"] == 1 and totals["cost_total"] == 5000000
    assert client.delete(f"/api/v1/sites/demo/report/reportages/{rid}").status_code == 200


def test_check_article_parses_link_and_rel(client, monkeypatch):
    """_check_article itself: HTML parsing, normalization, rel extraction (HTTP stubbed)."""
    html = '<html><body><p><a href="https://Demo.example/a/" rel="nofollow sponsored">امداد خودرو رنو</a></p></body></html>'

    class FakeResp:
        status_code = 200
        text = html

    class FakeClient:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, **kw): return FakeResp()

    monkeypatch.setattr(reports_router, "ReadOnlyClient", FakeClient)
    out = reports_router._check_article("https://mag.example/x", "https://demo.example/a")
    assert out["status"] == "link_found" and out["rel"] == "nofollow sponsored"
    out2 = reports_router._check_article("https://mag.example/x", "https://demo.example/other")
    assert out2["status"] == "target_changed"


def test_site_isolation(client):
    _seed(client, "site-a")
    _seed(client, "site-b")
    _seed_gsc(client, "site-a")
    client.put("/api/v1/sites/site-a/report/main-keyword", json={"keyword": "امداد خودرو رنو"})
    client.post("/api/v1/sites/site-a/report/backlinks", json={
        "source_url": "https://news.example/p", "target_url": "https://site-a.example/x"})
    client.post("/api/v1/sites/site-a/report/reportages", json={
        "article_url": "https://mag.example/r", "target_url": "https://site-a.example/x"})
    b = client.get("/api/v1/sites/site-b/report/summary").json()
    assert b["gsc"]["available"] is False
    assert b["main_keyword"]["keyword"] is None
    assert b["counts"]["backlinks"] == 0 and b["counts"]["reportages"] == 0
    assert client.get("/api/v1/sites/site-b/report/keywords").json()["status"] == "NO_GSC_DATA"
    assert client.get("/api/v1/sites/site-b/report/backlinks").json()["items"] == []
    assert client.get("/api/v1/sites/site-b/report/reportages").json()["items"] == []
    # unknown site 404s
    assert client.get("/api/v1/sites/nope/report/summary").status_code == 404
