"""Independent SERP snapshots: no GSC fallback, daily cadence, quota, and site isolation."""
from datetime import datetime, timezone
from io import BytesIO
import json
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.analysis import serp_rank
from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate


def _engine(tmp_path):
    engine = make_engine("sqlite:///" + (tmp_path / "rank.db").as_posix())
    migrate(engine)
    with engine.begin() as cx:
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url) VALUES ('s','Store','https://store.example/')"))
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url) VALUES ('other','Other','https://other.example/')"))
        for keyword in ("first", "second", "third"):
            cx.execute(text("""INSERT INTO keywords(site_id,keyword,normalized,status,target_url)
                VALUES ('s',:k,:k,'new','https://store.example/target')"""), {"k": keyword})
        cx.execute(text("""INSERT INTO keywords(site_id,keyword,normalized,status)
            VALUES ('other','private','private','new')"""))
        cx.execute(text("""INSERT INTO gsc_daily(site_id,date,page,query,country,device,clicks,impressions,position)
            VALUES ('s','2026-10-12','https://store.example/target','first','IR','MOBILE',2,50,2)"""))
    return engine


def test_no_provider_never_invents_rank_from_gsc(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    monkeypatch.delenv("SERPKITE_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    now = datetime(2026, 10, 14, 3, 0, tzinfo=timezone.utc)  # 06:30 Tehran
    assert serp_rank.due(engine, "s", now) is False
    assert serp_rank.create_run(engine, "s", now) == {"status": "needs_provider"}
    view = serp_rank.overview(engine, "s")
    assert view["latest_run"] is None
    assert all(row["organic_position"] is None for row in view["keywords"])


def test_daily_limit_rotates_keywords_and_keeps_site_private(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    monkeypatch.setenv("SERPAPI_API_KEY", "test-only")
    serp_rank.save_settings(engine, "s", provider="serpapi", device="mobile", depth=20,
                            max_keywords_per_run=2, enabled=True)
    before = datetime(2026, 10, 14, 2, 0, tzinfo=timezone.utc)  # 05:30 Tehran
    after = datetime(2026, 10, 14, 3, 0, tzinfo=timezone.utc)
    assert serp_rank.due(engine, "s", before) is False
    assert serp_rank.due(engine, "s", after) is True
    first = serp_rank.create_run(engine, "s", after)
    assert first["status"] == "queued"
    assert serp_rank.create_run(engine, "s", after)["status"] == "already_scheduled"
    assert serp_rank.due(engine, "s", after) is False
    seen = []

    def fake_fetch(keyword, cfg):
        seen.append(keyword)
        return serp_rank.SerpResult([
            {"position": 1, "absolute_position": 1, "url": "https://rival.example/p"},
            {"position": 4, "absolute_position": 4, "url": "https://store.example/result"},
        ], "sample")

    monkeypatch.setattr(serp_rank.time, "sleep", lambda _: None)
    result = serp_rank.execute_run(engine, "s", first["run_id"], fetch=fake_fetch)
    assert result["status"] == "partial" and result["checked"] == 2
    assert seen == ["first", "second"]
    view = serp_rank.overview(engine, "s")
    assert view["keywords_total"] == 3
    assert view["keywords"][0]["organic_position"] == 4
    assert view["keywords"][0]["competitors"][0]["domain"] == "rival.example"
    assert view["keywords"][2]["organic_position"] is None
    assert serp_rank.overview(engine, "other")["keywords"][0]["organic_position"] is None
    second_day = datetime(2026, 10, 15, 3, 0, tzinfo=timezone.utc)
    second = serp_rank.create_run(engine, "s", second_day)
    serp_rank.execute_run(engine, "s", second["run_id"], fetch=fake_fetch)
    assert seen[2] == "third"


def test_provider_failure_is_visible_not_zero_rank(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    monkeypatch.setenv("SERPKITE_API_KEY", "test-only")
    run = serp_rank.create_run(engine, "s", datetime(2026, 10, 14, 3, 0, tzinfo=timezone.utc))

    def fail(_keyword, _cfg):
        raise serp_rank.ProviderError("provider_quota_or_rate_limit", stop_run=True)

    result = serp_rank.execute_run(engine, "s", run["run_id"], fetch=fail)
    assert result["status"] == "blocked" and result["failed"] == 1
    assert result["error_code"] == "provider_quota_or_rate_limit"
    view = serp_rank.overview(engine, "s")
    assert view["latest_run"]["status"] == "blocked"
    assert all(row["organic_position"] is None for row in view["keywords"])


def test_valid_observation_survives_later_provider_block(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    monkeypatch.setenv("SERPKITE_API_KEY", "test-only")
    monkeypatch.setattr(serp_rank.time, "sleep", lambda _: None)
    run = serp_rank.create_run(engine, "s", datetime(2026, 10, 14, 3, 0, tzinfo=timezone.utc))

    def first_then_fail(keyword, _cfg):
        if keyword != "first":
            raise serp_rank.ProviderError("provider_quota_or_rate_limit", stop_run=True)
        return serp_rank.SerpResult([
            {"position": 7, "absolute_position": 7, "url": "https://store.example/target"}
        ], "first-task")

    result = serp_rank.execute_run(engine, "s", run["run_id"], fetch=first_then_fail)
    assert result["status"] == "blocked" and result["checked"] == 2
    view = serp_rank.overview(engine, "s")
    assert view["keywords"][0]["organic_position"] == 7
    assert view["keywords"][1]["organic_position"] is None


def test_three_provider_errors_stop_the_batch_and_resume_without_more_calls(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    monkeypatch.setenv("SERPKITE_API_KEY", "test-only")
    monkeypatch.setattr(serp_rank.time, "sleep", lambda _: None)
    run = serp_rank.create_run(engine, "s", datetime(2026, 10, 14, 3, 0, tzinfo=timezone.utc))
    calls = []

    def empty(_keyword, _cfg):
        calls.append(_keyword)
        raise serp_rank.ProviderError("provider_empty_results")

    result = serp_rank.execute_run(engine, "s", run["run_id"], fetch=empty)
    assert result["status"] == "blocked"
    assert result["error_code"] == "provider_repeated_errors"
    assert len(calls) == 3
    assert result["failed"] == 3
    assert serp_rank.execute_run(engine, "s", run["run_id"], fetch=empty)["status"] == "blocked"
    assert len(calls) == 3


def test_resumed_run_with_three_prior_errors_does_not_call_provider(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    monkeypatch.setenv("SERPKITE_API_KEY", "test-only")
    run = serp_rank.create_run(engine, "s", datetime(2026, 10, 14, 3, 0, tzinfo=timezone.utc))
    with engine.begin() as cx:
        for keyword_id, keyword in cx.execute(text("SELECT id,keyword FROM keywords WHERE site_id='s'")):
            cx.execute(text("""INSERT INTO serp_rank_observations
              (run_id,site_id,keyword_id,keyword,status,checked_at,error_code)
              VALUES(:r,'s',:k,:keyword,'provider_error','2026-10-14T03:00:00Z','provider_empty_results')"""),
              {"r": run["run_id"], "k": keyword_id, "keyword": keyword})
        cx.execute(text("UPDATE serp_rank_runs SET status='running',keywords_checked=3,keywords_failed=3 WHERE id=:r"),
                   {"r": run["run_id"]})

    def should_not_run(_keyword, _cfg):
        raise AssertionError("provider called after repeated errors")

    result = serp_rank.execute_run(engine, "s", run["run_id"], fetch=should_not_run)
    assert result["status"] == "blocked"
    assert result["error_code"] == "provider_repeated_errors"


def test_serpkite_contract_uses_unmodified_google_organic_results(monkeypatch):
    monkeypatch.setenv("SERPKITE_API_KEY", "test-only")
    captured = {}

    def fake_response(request):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        return {"results": [
            {"position": 1, "link": "https://rival.example/a"},
            {"position": 3, "link": "https://store.example/p"},
        ], "meta": {"request_id": "sample", "parse_quality": "ok"}}

    monkeypatch.setattr(serp_rank, "_fetch_json", fake_response)
    result = serp_rank.fetch_serp("شلوار مردانه", {"provider": "serpkite", "device": "mobile", "depth": 10})
    assert captured["url"] == "https://api.serpkite.com/v1/search"
    assert captured["body"] == {"q": "شلوار مردانه", "country": "ir", "language": "fa",
                                "device": "mobile", "num": 10, "page": 1, "engine": "google",
                                "fields": "results.position,results.link,results.domain"}
    assert [row["position"] for row in result.organic] == [1, 3]
    assert result.task_id == "sample"


def test_empty_provider_page_is_not_reported_as_a_missing_rank(monkeypatch):
    monkeypatch.setenv("SERPKITE_API_KEY", "test-only")
    monkeypatch.setattr(serp_rank, "_fetch_json", lambda _: {
        "results": [], "meta": {"parse_quality": "empty", "credits_used": 0}})
    with pytest.raises(serp_rank.ProviderError) as caught:
        serp_rank.fetch_serp("لباس مردانه", {"provider": "serpkite", "device": "mobile", "depth": 10})
    assert caught.value.code == "provider_empty_results"


def test_key_monthly_limit_is_reported_as_quota_not_bad_credentials(monkeypatch):
    def limited(request, timeout):
        raise HTTPError(request.full_url, 403, "Forbidden", {},
                        BytesIO(b'{"error":{"code":"key_limit_reached"}}'))

    monkeypatch.setattr(serp_rank, "urlopen", limited)
    with pytest.raises(serp_rank.ProviderError) as caught:
        serp_rank._fetch_json(Request("https://api.serpkite.com/v1/search"))
    assert caught.value.code == "provider_quota_or_rate_limit"
    assert caught.value.stop_run


def test_rank_api_requires_provider_and_scopes_settings(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    monkeypatch.delenv("SERPKITE_API_KEY", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: engine
    client = TestClient(app)
    base = "/api/v1/sites/s/rank-tracking"
    response = client.get(base + "/overview")
    assert response.status_code == 200
    assert response.json()["settings"]["provider"] == "serpkite"
    assert response.json()["keywords_total"] == 3
    assert client.post(base + "/run").status_code == 409
    changed = client.put(base + "/settings", json={
        "enabled": True, "provider": "serpkite", "device": "desktop", "depth": 20,
        "max_keywords_per_run": 12})
    assert changed.status_code == 200
    assert changed.json()["depth"] == 20
    assert client.get("/api/v1/sites/other/rank-tracking/overview").json()["settings"]["depth"] == 10
    assert client.get("/api/v1/sites/missing/rank-tracking/overview").status_code == 404
