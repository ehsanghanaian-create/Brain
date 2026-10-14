"""Research evidence stays site-scoped and competitor fetching stays public-only."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.analysis import research_intelligence as research_service
from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import research
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate


def _client(tmp_path, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    engine = make_engine("sqlite:///" + (tmp_path / "research.db").as_posix())
    migrate(engine)
    with engine.begin() as cx:
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url) VALUES ('s','Store','https://store.example/')"))
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url) VALUES ('other','Other','https://other.example/')"))
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: engine
    return TestClient(app), engine


def test_research_separates_gsc_questions_and_competitor_samples(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    latest = date.today() - timedelta(days=2)
    previous = latest - timedelta(days=45)
    with engine.begin() as cx:
        for offset in range(18):
            cx.execute(text("""INSERT INTO gsc_daily
                (site_id,date,page,query,country,device,clicks,impressions,position)
                VALUES ('s',:d,'https://store.example/guide','چطور شلوار انتخاب کنم','IR','MOBILE',1,12,8)"""),
                {"d": (previous + timedelta(days=offset)).isoformat()})
        cx.execute(text("""INSERT INTO gsc_daily
            (site_id,date,page,query,country,device,clicks,impressions,position)
            VALUES ('s',:d,'https://store.example/guide','چطور شلوار انتخاب کنم','IR','MOBILE',2,40,5)"""),
            {"d": latest.isoformat()})
        cx.execute(text("""INSERT INTO gsc_daily
            (site_id,date,page,query,country,device,clicks,impressions,position)
            VALUES ('s',:d,'https://store.example/pants','شلوار راسته مردانه','IR','MOBILE',1,30,11)"""),
            {"d": latest.isoformat()})
        cx.execute(text("""INSERT INTO gsc_daily
            (site_id,date,page,query,country,device,clicks,impressions,position)
            VALUES ('other',:d,'https://other.example/private','secret rival query','IR','MOBILE',1,50,4)"""),
            {"d": latest.isoformat()})
        cx.execute(text("""INSERT INTO ai_visibility_prompts
            (site_id,question,topic,created_at,updated_at) VALUES
            ('s','چه شلواری مناسب است؟','شلوار',:now,:now)"""), {"now": latest.isoformat()})
        prompt_id = cx.execute(text("SELECT id FROM ai_visibility_prompts WHERE site_id='s'")).scalar()
        cx.execute(text("""INSERT INTO ai_visibility_observations
            (site_id,prompt_id,provider,observed_at,capture_method,answer_text,created_at)
            VALUES ('s',:p,'ChatGPT',:day,'manual','Sample response',:day)"""),
            {"p": prompt_id, "day": latest.isoformat()})
        observation_id = cx.execute(text("SELECT id FROM ai_visibility_observations WHERE site_id='s'")).scalar()
        cx.execute(text("""INSERT INTO ai_visibility_citations
            (observation_id,url,domain,citation_kind,is_own_domain)
            VALUES (:id,'https://rival.example/guide','rival.example','source',0)"""),
            {"id": observation_id})
    response = client.get("/api/v1/sites/s/research/overview?days=28")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["gsc"]["previous_days"] == 18
    assert result["gsc"]["latest_date"] == latest.isoformat()
    assert {row["query"] for row in result["gsc"]["candidates"]} == {
        "چطور شلوار انتخاب کنم", "شلوار راسته مردانه"}
    assert next(row for row in result["gsc"]["candidates"] if row["query"] == "شلوار راسته مردانه")["signal"] == "new_in_sample"
    assert result["questions"]["observed_search_questions"][0]["query"] == "چطور شلوار انتخاب کنم"
    assert result["questions"]["scope"] == "no_access_to_private_ai_user_prompts"
    assert result["competitors"]["ai_citation_domains"][0]["domain"] == "rival.example"
    assert "secret rival query" not in str(result)
    other = client.get("/api/v1/sites/other/research/overview").json()
    assert other["competitors"]["ai_citation_domains"] == []


def test_competitor_queue_comparison_and_safe_host_validation(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(research, "get_job_queue", lambda: SimpleNamespace(enqueue=lambda job: SimpleNamespace(run_id="job-test")))
    base = "/api/v1/sites/s/research"
    invalid = client.post(base + "/competitors", json={"url": "https://store.example/own"})
    assert invalid.status_code == 422
    invalid_own = client.post(base + "/competitors", json={"url": "https://rival.example/p",
                                                          "own_url": "https://other.example/own"})
    assert invalid_own.status_code == 422
    created = client.post(base + "/competitors", json={"url": "https://rival.example/p",
                                                      "own_url": "https://store.example/own", "focus_query": "شلوار مردانه"})
    assert created.status_code == 202, created.text
    page_id = created.json()["id"]
    assert client.post(base + f"/competitors/{page_id}/refresh").json()["already_queued"] is True
    with engine.begin() as cx:
        cx.execute(text("""INSERT INTO pages(site_id,url,title,h1,h2,word_count,crawl_status)
            VALUES ('s','https://store.example/own','Our title','[\"Our H1\"]','[\"Our H2\"]',250,'ok')"""))
    monkeypatch.setattr(research_service, "fetch_public_metadata", lambda url: {
        "http_status": 200, "title": "Rival title", "meta_description": "Rival description",
        "h1_json": '["Rival H1"]', "h2_json": '["Rival H2"]', "canonical": url, "word_count": 400})
    assert research_service.refresh_competitor(engine, "s", page_id)["status"] == "ready"
    tracked = client.get(base + "/overview").json()["competitors"]["tracked_pages"][0]
    assert tracked["title"] == "Rival title" and tracked["own_page"]["title"] == "Our title"
    assert tracked["h1"] == ["Rival H1"] and tracked["own_page"]["h1"] == ["Our H1"]
    assert client.get("/api/v1/sites/other/research/overview").json()["competitors"]["tracked_pages"] == []
    assert client.delete(f"/api/v1/sites/other/research/competitors/{page_id}").status_code == 404
    assert client.delete(base + f"/competitors/{page_id}").json() == {"deleted": page_id}

    monkeypatch.setattr(research_service.socket, "getaddrinfo", lambda *a, **k: [
        (None, None, None, None, ("127.0.0.1", 443))])
    with pytest.raises(ValueError, match="non_public_address"):
        research_service._public_https_target("https://private.example/secret")
    with pytest.raises(ValueError, match="ip_literal_forbidden"):
        research_service._public_https_target("https://127.0.0.1/")
