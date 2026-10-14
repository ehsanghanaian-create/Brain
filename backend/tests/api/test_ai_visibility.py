"""AI visibility keeps observed traffic, official reports, and prompt samples separate."""
import sqlite3
from datetime import date, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.ga4.ai_referrals import classify_source, store_referrals
from seo_brain.ai.visibility_probe import ProbeUnavailable, probe_openai


def test_referral_source_is_conservative_and_resync_replaces_window(tmp_path):
    assert classify_source("https://www.chatgpt.com/") == "chatgpt"
    assert classify_source("perplexity.ai") == "perplexity"
    assert classify_source("bing.com") is None  # Ordinary search must not be counted as AI.
    assert classify_source("chatgpt.com.evil.example") is None
    path = tmp_path / "referrals.db"
    eng = make_engine("sqlite:///" + path.as_posix())
    migrate(eng)
    with eng.begin() as cx:
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url) VALUES ('s','Store','https://store.example/')"))
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    day = date(2026, 10, 10)
    rows = {"currency": "IRR", "commerce_available": True, "rows": [
        {"date": "2026-10-10", "landing_page": "/product/a?utm_source=x", "session_source": "chatgpt.com",
         "session_medium": "referral", "sessions": 2, "engaged_sessions": 1,
         "transactions": 1, "purchase_revenue": 100000},
        {"date": "2026-10-10", "landing_page": "/product/a?utm_source=y", "session_source": "chatgpt.com",
         "session_medium": "referral", "sessions": 1, "engaged_sessions": 1,
         "transactions": 0, "purchase_revenue": 0},
        {"date": "2026-10-10", "landing_page": "/product/a", "session_source": "bing.com",
         "session_medium": "organic", "sessions": 10, "engaged_sessions": 7,
         "transactions": 3, "purchase_revenue": 300000},
    ]}
    assert store_referrals(conn, "s", day, day, rows, "r1") == 1
    assert store_referrals(conn, "s", day, day, rows, "r2") == 1
    stored = conn.execute("SELECT landing_page,sessions,transactions,purchase_revenue,sync_run_id FROM ga4_ai_referrals_daily").fetchall()
    assert stored == [("/product/a", 3, 1.0, 100000.0, "r2")]
    assert store_referrals(conn, "s", day, day, {"currency": None, "commerce_available": False, "rows": []}, "r3") == 0
    assert conn.execute("SELECT COUNT(*) FROM ga4_ai_referrals_daily").fetchone()[0] == 0
    conn.close()


def test_ai_visibility_api_provenance_and_site_scope(tmp_path, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    eng = make_engine("sqlite:///" + (tmp_path / "api.db").as_posix())
    migrate(eng)
    with eng.begin() as cx:
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url) VALUES ('store','Store','https://salimore.com/')"))
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url) VALUES ('other','Other','https://other.example/')"))
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app)
    base = "/api/v1/sites/store/ai-visibility"
    initial = client.get(base + "/summary").json()
    assert initial["referrals"]["sessions"] is None
    assert initial["official"]["status"] == "not_imported"
    assert initial["prompts"]["mention_rate"] is None

    bad = client.post(base + "/prompts", json={"question": "برای پاییز چه لباسی بخرم؟",
                                                "target_url": "https://salimore.com.evil.example/a"})
    assert bad.status_code == 422
    made = client.post(base + "/prompts", json={"question": "برای پاییز چه لباسی بخرم؟",
                                                 "target_url": "https://salimore.com/product/a", "topic": "پاییز"})
    assert made.status_code == 201, made.text
    prompt_id = made.json()["id"]
    assert client.get(base + "/prompts").json()["probe_available"] is False
    assert client.post(base + "/prompts", json={"question": "برای پاییز چه لباسی بخرم؟"}).status_code == 409
    assert client.post(f"/api/v1/sites/other/ai-visibility/prompts/{prompt_id}/observations", json={
        "provider": "ChatGPT", "observed_at": (date.today() - timedelta(days=1)).isoformat(), "answer_text": "example"
    }).status_code == 404

    obs = client.post(base + f"/prompts/{prompt_id}/observations", json={
        "provider": "ChatGPT", "model": "example", "observed_at": (date.today() - timedelta(days=1)).isoformat(),
        "answer_text": "A raw, manually observed answer.", "brand_mentioned": True,
        "competitors": ["Competitor"], "citations": [
            {"url": "https://salimore.com/blog/guide", "kind": "inline"},
            {"url": "https://salimore.com.evil.example/page", "kind": "source"},
        ]
    })
    assert obs.status_code == 201, obs.text
    items = client.get(base + "/observations").json()["items"]
    assert items[0]["capture_method"] == "manual" and items[0]["competitors"] == ["Competitor"]
    assert [c["is_own_domain"] for c in items[0]["citations"]] == [1, 0]
    assert client.get("/api/v1/sites/other/ai-visibility/observations").json()["items"] == []

    today = (date.today() - timedelta(days=1)).isoformat()
    assert client.post(base + "/official-import", json={"source_label": "GSC export", "rows": [
        {"date": today, "platform": "google_ai_search", "citations": 4}
    ]}).status_code == 422
    imported = client.post(base + "/official-import", json={"source_label": "GSC AI report CSV 2026", "rows": [
        {"date": today, "platform": "google_ai_search", "impressions": 12,
         "page_url": "https://salimore.com/blog/guide"},
        {"date": today, "platform": "bing_ai", "citations": 2},
    ]})
    assert imported.status_code == 200, imported.text
    final = client.get(base + "/summary").json()
    assert final["prompts"]["samples"] == 1 and final["prompts"]["own_citations"] == 1
    assert final["prompts"]["mention_rate"] == 1
    assert {r["platform"] for r in final["official"]["platforms"]} == {"google_ai_search", "bing_ai"}
    assert final["referrals"]["sessions"] is None  # Console and prompt data do not create GA4 traffic.


def test_gsc_suggestions_and_today_sample_review(tmp_path, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    eng = make_engine("sqlite:///" + (tmp_path / "today.db").as_posix())
    migrate(eng)
    with eng.begin() as cx:
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url) VALUES ('s','Store','https://store.example/')"))
        cx.execute(text("""INSERT INTO gsc_query_page(site_id,page,query,clicks,impressions,ctr,position,date_from,date_to)
            VALUES ('s','https://store.example/p','کفش مردانه',5,80,0.06,7,'2026-10-01','2026-10-10')"""))
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app)
    base = "/api/v1/sites/s/ai-visibility"
    suggestions = client.get(base + "/prompt-suggestions").json()
    assert suggestions["date_to"] == "2026-10-10"
    assert suggestions["items"][0]["query"] == "کفش مردانه"
    prompt_id = client.post(base + "/prompts", json={"question": "برای خرید کفش مردانه چه باید کرد؟"}).json()["id"]
    observed = client.post(base + f"/prompts/{prompt_id}/observations", json={
        "provider": "ChatGPT", "observed_at": date.today().isoformat(), "answer_text": "Store is cited."
    })
    assert observed.status_code == 201, observed.text
    summary = client.get(base + "/summary").json()
    assert summary["prompts"]["samples"] == 1
    assert summary["prompts"]["assessed"] == 0
    reviewed = client.patch(base + f"/observations/{observed.json()['id']}/review", json={
        "brand_mentioned": True, "competitors": ["Other Store"]
    })
    assert reviewed.status_code == 200, reviewed.text
    assert client.get(base + "/summary").json()["prompts"]["mention_rate"] == 1
    assert client.get(base + "/observations").json()["items"][0]["competitors"] == ["Other Store"]


def test_openai_probe_keeps_raw_citations_and_requires_search(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "completed", "model": "test-model", "output": [
                {"type": "web_search_call", "status": "completed"},
                {"type": "message", "content": [{"type": "output_text", "text": "A cited answer.",
                    "annotations": [{"type": "url_citation", "url": "https://store.example/guide",
                                     "end_index": 14}]}]},
            ]}

    import seo_brain.ai.visibility_probe as probe
    requests = []

    def fake_post(url, **kwargs):
        requests.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(probe.httpx, "post", fake_post)
    sample = probe_openai("What should I buy?", "fa-IR", "IR", "test-model", "secret")
    assert sample["answer_text"] == "A cited answer."
    assert sample["citations"][0]["url"] == "https://store.example/guide"
    assert requests[0][0] == "https://api.openai.com/v1/responses"
    assert requests[0][1]["json"]["tool_choice"] == "required"
    assert requests[0][1]["json"]["store"] is False
    assert "What should I buy?" in requests[0][1]["json"]["input"]
    assert "{question}" not in requests[0][1]["json"]["input"]
    monkeypatch.setattr(probe.httpx, "post", lambda *a, **kw: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "No web search", "annotations": []}]}]}))
    try:
        probe_openai("What should I buy?", "fa-IR", "IR", "test-model", "secret")
        assert False, "A response without a web search must be rejected"
    except ProbeUnavailable:
        pass


def test_api_probe_is_explicit_scoped_and_unassessed(tmp_path, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    eng = make_engine("sqlite:///" + (tmp_path / "probe.db").as_posix())
    migrate(eng)
    with eng.begin() as cx:
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url) VALUES ('s','Store','https://store.example/')"))
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url) VALUES ('other','Other','https://other.example/')"))
    from seo_brain.ai.config import ProviderConfigRepository
    import seo_brain.ai.visibility_probe as probe

    monkeypatch.setattr(ProviderConfigRepository, "list", lambda self: [SimpleNamespace(
        kind="openai", enabled=True, default_model="test-model")])
    monkeypatch.setattr(ProviderConfigRepository, "api_key", lambda self, provider: "fake-key")
    monkeypatch.setattr(probe, "probe_openai", lambda *args: {
        "answer_text": "A web answer", "citations": [{"url": "https://store.example/p", "kind": "inline", "position": 8}],
        "model": "test-model", "status": "complete"})
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app)
    base = "/api/v1/sites/s/ai-visibility"
    prompt_id = client.post(base + "/prompts", json={"question": "Which product should I choose?"}).json()["id"]
    assert client.get(base + "/prompts").json()["probe_available"] is True
    assert client.post(f"/api/v1/sites/other/ai-visibility/prompts/{prompt_id}/probe").status_code == 404
    assert client.get(base + "/summary").json()["prompts"]["samples"] == 0
    created = client.post(base + f"/prompts/{prompt_id}/probe")
    assert created.status_code == 201, created.text
    sample = client.get(base + "/observations").json()["items"][0]
    assert sample["capture_method"] == "provider_api" and sample["brand_mentioned"] is None
    assert sample["citations"][0]["is_own_domain"] == 1
    assert client.get(base + "/summary").json()["prompts"]["assessed"] == 0


def test_site_deletion_accounts_for_ai_citations(tmp_path, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    eng = make_engine("sqlite:///" + (tmp_path / "delete.db").as_posix())
    migrate(eng)
    with eng.begin() as cx:
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url) VALUES ('s','Store','https://store.example/')"))
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app)
    base = "/api/v1/sites/s/ai-visibility"
    prompt_id = client.post(base + "/prompts", json={"question": "Which product should I choose?"}).json()["id"]
    response = client.post(base + f"/prompts/{prompt_id}/observations", json={
        "provider": "ChatGPT", "observed_at": date.today().isoformat(), "answer_text": "A web answer.",
        "citations": [{"url": "https://store.example/p"}],
    })
    assert response.status_code == 201
    refused = client.delete("/api/v1/sites/s")
    assert refused.status_code == 409
    assert refused.json()["error"]["details"]["ai_visibility_citations"] == 1
    deleted = client.delete("/api/v1/sites/s?force=true")
    assert deleted.status_code == 200, deleted.text
    with eng.connect() as cx:
        assert cx.execute(text("SELECT COUNT(*) FROM ai_visibility_citations")).scalar() == 0
