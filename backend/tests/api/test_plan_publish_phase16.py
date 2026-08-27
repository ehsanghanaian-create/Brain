"""Phase 16 — Planner → AI draft → WordPress publish (the ONE mode-gated writer).

Covers: generate_for_plan builds the workspace spec from plan + metadata.ai (پرامپت دستی included), creates/links the
content item and a versioned draft; WordPressWriter.publish_plan sends title/HTML/category/calendar-date with the
Application Password, gates scheduler publishes on mode='autopilot', audits publishing JSON + events; capability probe
checks roles without writing; due_autopilot_plans picks only arrived, unpublished plans on autopilot sites; the
generate/publish endpoints queue jobs (202)."""
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
from seo_brain.brain.generation.workspace import ContentTestWorkspace
from seo_brain.brain.planner import PlannerService
from seo_brain.brain.planner.generation import ai_settings, due_autopilot_plans, generate_for_plan
from seo_brain.database.db import connect as legacy_connect
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.integrations.wordpress import WordPressWriter
from seo_brain.integrations.wordpress.writer import _md_to_html
from seo_brain.wordpress.auth import WpAuth

SID = "demo"


@pytest.fixture
def c(tmp_path, monkeypatch):
    dbfile = tmp_path / "p16.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(graph_router, "connect", lambda: legacy_connect(dbfile))
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    q = InProcessJobQueue(sync=True)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng; app.dependency_overrides[deps.job_queue] = lambda: q
    app.dependency_overrides[cp_router.svc] = lambda: PlannerService(eng, ContentService(eng))
    client = TestClient(app)
    assert client.post("/api/v1/sites", json={"site_id": SID, "name": "Demo", "canonical_url": "https://demo.example/"}).status_code == 201
    client.patch(f"/api/v1/sites/{SID}", json={"wp_url": "https://demo.example"})
    client.post(f"/api/v1/sites/{SID}/initialize")
    client.eng, client.q = eng, q  # type: ignore[attr-defined]
    return client


def _mk_plan(c, **over):
    body = {"title": "امداد خودرو MVM در تهران", "primary_keyword": "امداد خودرو mvm", "secondary_keywords": ["یدک‌کش mvm"],
            "intent": "transactional", "target_audience": "مالکان MVM", "publish_date": "2026-01-15", "publish_time": "10:30", **over}
    r = c.post(f"/api/v1/sites/{SID}/content-plans", json=body, params={"analyze": "false"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _wp_category(c, wp_id=7, name="MVM"):
    with c.eng.begin() as cx:
        cx.execute(text("INSERT INTO content_categories(site_id, name, slug, source, wordpress_category_id, created_at, updated_at) "
                        "VALUES(:s,:n,:n,'wordpress',:w,datetime('now'),datetime('now'))"), {"s": SID, "n": name, "w": wp_id})
        return int(cx.execute(text("SELECT id FROM content_categories WHERE site_id=:s AND name=:n"), {"s": SID, "n": name}).scalar())


class FakeWorkspace:
    """Records the spec/save calls; save_draft delegates to the real workspace so a real versioned draft exists."""

    def __init__(self, eng):
        from seo_brain.ai.gateway import Gateway
        self.eng = eng
        self.real = ContentTestWorkspace(eng, Gateway(eng))
        self.calls: list = []

    def generate(self, site_id, spec, provider=None, model=None):
        self.calls.append(("generate", spec, provider, model))
        return {"ok": True, "run_id": "ws-test-1", "result": {"markdown": "# تیتر\n\nمتن **مهم** آزمایشی", "title": spec.title, "meta_description": "توضیح متا"},
                "seo": {"score": {"total": 82}, "word_count": 450}, "meta": {"provider": provider or "grok", "model": model or "grok-4", "placeholder": False}}

    def save_draft(self, site_id, content_id, markdown, title=None, meta_description=None, meta=None, actor="human"):
        self.calls.append(("save_draft", content_id, actor))
        return self.real.save_draft(site_id, content_id, markdown, title=title, meta_description=meta_description, meta=meta or {}, actor=actor)


def wp_http(responses: dict, seen: list):
    def handler(method, url, auth=None, **kw):
        seen.append({"method": method, "url": url, "auth": auth, "json": kw.get("json")})
        status, body = responses.get((method, url.rsplit("/", 1)[-1].split("?")[0]), (200, {}))
        if isinstance(body, str):                                            # host-firewall style HTML block page
            return httpx.Response(status, text=body, headers={"content-type": "text/html"}, request=httpx.Request(method, url))
        return httpx.Response(status, json=body, request=httpx.Request(method, url))
    return handler


def test_generate_for_plan_builds_spec_from_plan_and_metadata_ai(c):
    cat = _wp_category(c)
    pid = _mk_plan(c, category_id=cat, notes="نکته داخلی")
    c.patch(f"/api/v1/sites/{SID}/content-plans/{pid}",
            json={"metadata": {"ai": {"provider": "grok", "model": "grok-4", "tone": "friendly", "word_count": 800,
                                      "audience": "رانندگان", "content_type": "service_landing", "prompt": "پرامپت دستی من"}}})
    fw = FakeWorkspace(c.eng)
    out = generate_for_plan(c.eng, SID, pid, workspace=fw)
    assert out["status"] == "generated" and out["provider"] == "grok" and out["model"] == "grok-4" and out["seo_score"] == 82
    _, spec, provider, model = fw.calls[0]
    assert (provider, model) == ("grok", "grok-4")
    assert spec.title == "امداد خودرو MVM در تهران" and spec.keyword == "امداد خودرو mvm" and spec.secondary_keywords == ["یدک‌کش mvm"]
    assert spec.intent == "transactional" and spec.tone == "friendly" and spec.word_count == 800 and spec.audience == "رانندگان"
    assert spec.content_type == "service_landing" and spec.category == "MVM"
    assert "پرامپت دستی من" in spec.instructions and "نکته داخلی" in spec.instructions
    assert fw.calls[1][2] == "ai:planner:human"
    plan = c.get(f"/api/v1/sites/{SID}/content-plans/{pid}").json()
    assert plan["status"] == "review" and plan["content_item_id"] == out["content_id"]
    with c.eng.connect() as cx:
        d = cx.execute(text("SELECT body, version FROM content_drafts WHERE site_id=:s AND content_id=:c ORDER BY version DESC"), {"s": SID, "c": out["content_id"]}).first()
        ev = [r[0] for r in cx.execute(text("SELECT event FROM content_plan_events WHERE site_id=:s AND content_plan_id=:p"), {"s": SID, "p": pid})]
    assert d and "متن **مهم**" in d[0] and "draft_generated" in ev
    assert ai_settings((None,) * 11 + (json.dumps({"ai": {"tone": "x"}}),))["tone"] == "x"


def test_publish_plan_payload_gates_and_audit(c, monkeypatch):
    monkeypatch.setattr("seo_brain.integrations.wordpress.writer.resolve_auth", lambda sid: WpAuth("ehsan", "app-pass", "test"))
    cat = _wp_category(c, wp_id=7)
    pid = _mk_plan(c, category_id=cat)
    fw = FakeWorkspace(c.eng)
    gen = generate_for_plan(c.eng, SID, pid, workspace=fw)
    seen: list = []
    w = WordPressWriter(c.eng, http=wp_http({("POST", "posts"): (201, {"id": 321, "link": "https://demo.example/mvm-emdad/", "status": "future"})}, seen))
    out = w.publish_plan(SID, pid, actor="human")
    assert out["status"] == "published" and out["wp_post_id"] == 321 and out["category_wp_id"] == 7
    req = seen[0]
    assert req["url"].endswith("/wp-json/wp/v2/posts") and req["auth"] == ("ehsan", "app-pass")
    assert req["json"]["categories"] == [7] and req["json"]["date"] == "2026-01-15T10:30:00"          # exact calendar date/time
    assert "<h2>تیتر</h2>" in req["json"]["content"] and "<strong>مهم</strong>" in req["json"]["content"]
    plan = c.get(f"/api/v1/sites/{SID}/content-plans/{pid}").json()
    assert plan["status"] == "published" and plan["publishing"]["wp_post_id"] == 321 and plan["publishing"]["actor"] == "human"
    with c.eng.connect() as cx:
        item = cx.execute(text("SELECT status, url FROM content_items WHERE site_id=:s AND id=:c"), {"s": SID, "c": gen["content_id"]}).first()
    assert item[0] == "published" and item[1] == "https://demo.example/mvm-emdad/"
    assert w.publish_plan(SID, pid)["status"] == "already_published"
    # mode gate: scheduler may publish ONLY on autopilot; a human click passes in any mode
    pid2 = _mk_plan(c, title="مقاله دوم", publish_date="2026-01-16")
    generate_for_plan(c.eng, SID, pid2, workspace=fw)
    assert w.publish_plan(SID, pid2, actor="scheduler")["status"] == "skipped_mode"
    c.patch(f"/api/v1/sites/{SID}", json={"mode": "autopilot"})
    assert w.publish_plan(SID, pid2, actor="scheduler")["status"] == "published"
    # no draft yet → Persian guidance, nothing sent
    pid3 = _mk_plan(c, title="مقاله سوم", publish_date=None)
    n = len(seen)
    assert w.publish_plan(SID, pid3)["status"] == "no_draft" and len(seen) == n


def test_capability_probe_roles_and_endpoint(c, monkeypatch):
    monkeypatch.setattr("seo_brain.integrations.wordpress.writer.resolve_auth", lambda sid: WpAuth("ehsan", "app-pass", "test"))
    ok = WordPressWriter(c.eng, http=wp_http({("GET", "me"): (200, {"slug": "ehsan", "roles": ["editor"]})}, []))
    r = ok.capability(SID)
    assert r["configured"] and r["can_publish"] and r["username"] == "ehsan" and "انتشار مجاز" in r["message"]
    low = WordPressWriter(c.eng, http=wp_http({("GET", "me"): (200, {"slug": "x", "roles": ["subscriber"]})}, []))
    assert low.capability(SID)["can_publish"] is False
    # host firewall (LiteSpeed anti-enumeration) blocks wp/v2/users* with an HTML 403 → fall back to posts?context=edit
    waf_ok = WordPressWriter(c.eng, http=wp_http({("GET", "me"): (403, "<html>403 Forbidden</html>"), ("GET", "posts"): (200, [])}, []))
    r2 = waf_ok.capability(SID)
    assert r2["configured"] and r2["can_publish"] and "فایروال" in r2["message"]
    waf_bad = WordPressWriter(c.eng, http=wp_http({("GET", "me"): (403, "<html>403</html>"), ("GET", "posts"): (401, {"code": "rest_forbidden_context"})}, []))
    assert waf_bad.capability(SID)["can_publish"] is False
    # a JSON 401 (real WordPress auth failure) must NOT trigger the fallback
    json401 = []
    auth_bad = WordPressWriter(c.eng, http=wp_http({("GET", "me"): (401, {"code": "incorrect_password"})}, json401))
    assert auth_bad.capability(SID)["can_publish"] is False and len(json401) == 1
    monkeypatch.setattr("seo_brain.integrations.wordpress.writer.resolve_auth", lambda sid: None)
    ep = c.get(f"/api/v1/sites/{SID}/wordpress/publish-capability").json()
    assert ep["site_id"] == SID and ep["configured"] is False and "Application Password" in ep["message"]


def test_wp_connection_test_waf_fallback_saves_auth_status_ok(c):
    """کارت وردپرس: وقتی فایروال هاست users/me را با HTML 403 می‌بندد، probe جایگزین posts?context=edit احراز هویت را تأیید می‌کند."""
    from seo_brain.connections.service import ConnectionsService

    def pub(url):
        if "wp-json" in url:
            return httpx.Response(200, json={"name": "دمو", "namespaces": ["wp/v2"]}, request=httpx.Request("GET", url))
        return httpx.Response(200, text="<html>home</html>", headers={"content-type": "text/html"}, request=httpx.Request("GET", url))

    def auth_fetch(url, basic):
        if "/users/me" in url:
            return httpx.Response(403, text="<html>403 Forbidden</html>", headers={"content-type": "text/html"}, request=httpx.Request("GET", url))
        assert "posts?context=edit" in url and basic == ("ehsan", "pw")
        return httpx.Response(200, json=[], request=httpx.Request("GET", url))

    svc = ConnectionsService(c.eng, wp_fetch=pub, wp_fetch_auth=auth_fetch)
    res = svc.test_wordpress(SID, "https://demo.example", "ehsan", "pw")
    a = res.detail["auth"]
    assert res.status == "ok" and a["status"] == "ok" and "فایروال" in a["message"]
    assert any(d["step"] == "auth_fallback" and d["ok"] for d in res.detail["diagnostics"])
    # probe جایگزین هم رد شود → احراز هویت واقعاً ناموفق است
    def auth_bad(url, basic):
        if "/users/me" in url:
            return httpx.Response(403, text="<html>403</html>", headers={"content-type": "text/html"}, request=httpx.Request("GET", url))
        return httpx.Response(401, json={"code": "incorrect_password"}, request=httpx.Request("GET", url))
    res2 = ConnectionsService(c.eng, wp_fetch=pub, wp_fetch_auth=auth_bad).test_wordpress(SID, "https://demo.example", "ehsan", "bad")
    assert res2.detail["auth"]["status"] == "not_authorized"


def test_due_autopilot_plans_calendar_logic(c):
    pid_due = _mk_plan(c, title="سررسید", publish_date="2020-01-01")
    pid_future = _mk_plan(c, title="آینده", publish_date="2099-01-01")
    assert due_autopilot_plans(c.eng) == []                                  # site not autopilot yet
    c.patch(f"/api/v1/sites/{SID}", json={"mode": "autopilot"})
    due = due_autopilot_plans(c.eng)
    assert {d["plan_id"] for d in due} == {pid_due} and due[0]["site_id"] == SID and pid_future not in {d["plan_id"] for d in due}
    with c.eng.begin() as cx:                                                # already published → excluded
        cx.execute(text("UPDATE content_plans SET publishing=:p WHERE id=:i"), {"p": json.dumps({"wp_post_id": 9}), "i": pid_due})
    assert due_autopilot_plans(c.eng) == []


def test_generate_and_publish_endpoints_queue_jobs(c):
    done: list = []
    fw = FakeWorkspace(c.eng)
    c.q.register("plan_generate", lambda p: done.append(("gen", p)) or generate_for_plan(c.eng, p["site_id"], p["plan_id"], actor=p.get("actor", "human"), workspace=fw))
    c.q.register("plan_publish", lambda p: done.append(("pub", p)))
    pid = _mk_plan(c)
    r = c.post(f"/api/v1/sites/{SID}/content-plans/{pid}/generate")
    assert r.status_code == 202 and r.json()["status"] == "queued" and r.json()["job_id"]
    assert done and done[0][0] == "gen" and done[0][1]["plan_id"] == pid and done[0][1]["actor"] == "human"
    r2 = c.post(f"/api/v1/sites/{SID}/content-plans/{pid}/publish")
    assert r2.status_code == 202 and done[-1][0] == "pub" and done[-1][1]["generate_if_missing"] is True


def test_md_to_html_and_write_guard_location():
    html = _md_to_html("# عنوان\n\n- یک\n- دو\n\nمتن [پیوند](https://x.ir) و *مورب*")
    assert "<h2>عنوان</h2>" in html and "<ul>" in html and '<a href="https://x.ir">پیوند</a>' in html and "<em>مورب</em>" in html
    from pathlib import Path
    p = Path(WordPressWriter.__module__.replace(".", "/"))
    assert p.parts[:2] == ("seo_brain", "integrations")                      # the ONE writer lives in the excluded slot
