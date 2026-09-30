import json

import httpx
import pytest
from sqlalchemy import text

from seo_brain.ai.gateway.adapters import AtriaAdapter
from seo_brain.ai.config import PROVIDER_KINDS, RECOMMENDED_ROUTES, TASK_KINDS
from seo_brain.ai.types import AIMessage, AIRequest
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.remediation.playbooks import PLAYBOOKS
from seo_brain.remediation.service import RemediationError, RemediationService, issue_key, public_run


def test_all_analysis_problem_types_have_two_bounded_methods():
    expected = {"orphan", "no_body_inbound_links", "low_inbound_links", "high_outbound_links", "missing_h1",
                "multiple_h1", "duplicate_h1", "duplicate_title", "missing_meta_description", "images_missing_alt",
                "missing_canonical", "important_non_indexable", "thin_content", "redirect_in_sitemap"}
    assert set(PLAYBOOKS) == expected
    assert all(len(methods) == 2 and len({m["id"] for m in methods}) == 2 for methods in PLAYBOOKS.values())
    assert PROVIDER_KINDS["atria"]["base_url"] == "https://api.atria-asi.ai/v1"
    assert "seo_remediation" in TASK_KINDS
    assert RECOMMENDED_ROUTES["atria"] == {"seo_remediation": ("Atria-Dawn-Preview", None)}


def test_atria_uses_documented_completion_without_models_or_json_mode():
    calls = []

    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json={"model": body["model"], "choices": [{"message": {"content": '{"methods":[]}'}}]})

    adapter = AtriaAdapter("atria", "secret-test", None, ["Atria-Dawn-Preview"], {}, httpx.MockTransport(handler))
    try:
        assert adapter.test_connection()["ok"]
        response = adapter.complete(AIRequest("Atria-Dawn-Preview", [AIMessage("user", "suggest")], 100, 0,
                                              {"type": "object", "properties": {"methods": {}}}))
    finally:
        AtriaAdapter._next_call_at = 0
    assert json.loads(response.text) == {"methods": []}
    assert all(str(c.url) == "https://api.atria-asi.ai/v1/chat/completions" for c in calls)
    assert all(c.headers["authorization"] == "Bearer secret-test" for c in calls)
    assert all("response_format" not in json.loads(c.content) for c in calls)
    assert json.loads(calls[0].content)["max_tokens"] == 256


def test_atria_retries_retry_after_and_rejects_invalid_reply(monkeypatch):
    import seo_brain.ai.gateway.adapters as module
    from seo_brain.ai.providers.base import ProviderError

    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    adapter = AtriaAdapter("atria", "secret", None, ["Atria-Dawn-Preview"], {}, httpx.MockTransport(handler))
    request = AIRequest("Atria-Dawn-Preview", [AIMessage("user", "hi")], 10, 0)
    try:
        assert adapter.complete(request).text == "OK" and calls["n"] == 2
        invalid = AtriaAdapter("atria", "secret", None, ["Atria-Dawn-Preview"], {},
                               httpx.MockTransport(lambda _r: httpx.Response(200, text="not json")))
        with pytest.raises(ProviderError):
            invalid.complete(request)
    finally:
        AtriaAdapter._retry_at = 0
        AtriaAdapter._next_call_at = 0


def test_atria_honors_retry_after_longer_than_thirty_seconds(monkeypatch):
    import seo_brain.ai.gateway.adapters as module
    from seo_brain.ai.providers.base import ProviderError

    slept = []
    monkeypatch.setattr(module.time, "sleep", slept.append)
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return (httpx.Response(429, headers={"Retry-After": "42"}) if calls["n"] == 1 else
                httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]}))

    adapter = AtriaAdapter("atria", "secret", None, ["Atria-Dawn-Preview"], {}, httpx.MockTransport(handler))
    try:
        assert adapter.complete(AIRequest("Atria-Dawn-Preview", [AIMessage("user", "hi")], 10, 0)).text == "OK"
        assert slept and slept[-1] >= 41
        invalid = AtriaAdapter("atria", "secret", None, ["Atria-Dawn-Preview"], {},
                               httpx.MockTransport(lambda _r: httpx.Response(200, json={"choices": ["invalid"]})))
        with pytest.raises(ProviderError):
            invalid.complete(AIRequest("Atria-Dawn-Preview", [AIMessage("user", "hi")], 10, 0))
    finally:
        AtriaAdapter._retry_at = 0
        AtriaAdapter._next_call_at = 0


@pytest.fixture
def service(tmp_path, monkeypatch):
    engine = make_engine("sqlite:///" + (tmp_path / "test.db").as_posix())
    migrate(engine)
    with engine.begin() as cx:
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url,wp_url) VALUES ('gearboxemdad','Pilot','https://pilot.example/','https://wp.example')"))
        cx.execute(text("INSERT INTO seo_problems(site_id,problem_type,severity,url,related_url,detail) VALUES ('gearboxemdad','missing_meta_description','low','https://pilot.example/a','','{}')"))
        cx.execute(text("INSERT INTO pages(site_id,url,status_code,title,meta_description,h1,h1_count,images,content_hash) VALUES ('gearboxemdad','https://pilot.example/a',200,'A','','[\"A\"]',1,'[]','hash-1')"))
        cx.execute(text("INSERT INTO posts(site_id,wp_id,type,url,title,content_html,modified_gmt) VALUES ('gearboxemdad',7,'post','https://pilot.example/a','A','<p>text</p>','2026-09-01T00:00:00')"))
    svc = RemediationService(engine)
    import seo_brain.remediation.service as module
    monkeypatch.setattr(module, "resolve_auth", lambda site_id: object())
    monkeypatch.setattr(svc, "_probe_wp_access", lambda *_args: {"status": "ready", "reason": "test edit access"})
    monkeypatch.setattr(svc, "_rendered", lambda *_args: {"status": 200, "url": "https://pilot.example/a", "title": "A", "h1": ["A"],
                                                      "description": "", "canonical": "", "robots": "", "x_robots_tag": "", "links": [], "images": [],
                                                      "images_missing_alt": 0, "word_count": 20})
    svc._atria = lambda _site, _evidence, _templates: {
        "wp_meta_description": {"id": "wp_meta_description", "value": "توضیح پیشنهادی برای صفحه", "confidence": "high", "reason": "متناسب با عنوان"},
        "template_description": {"id": "template_description", "value": "توضیح در قالب", "confidence": "low"}
    }
    return svc


def test_stable_issue_key_and_proposal_binding(service):
    key = issue_key("gearboxemdad", "missing_meta_description", "https://pilot.example/a/")
    assert key == issue_key("gearboxemdad", "missing_meta_description", "https://pilot.example/a")
    listed = service.list_issues("gearboxemdad")
    assert listed["total"] == 1 and listed["items"][0]["issue_key"] == key
    proposal = service.propose("gearboxemdad", key)
    assert proposal["methods"][0]["available"]
    assert not proposal["methods"][1]["available"]
    assert "evidence" not in proposal
    with pytest.raises(RemediationError) as exc:
        service.create_run("gearboxemdad", proposal["id"], "wp_meta_description", proposal["evidence_hash"], "key-12345678")
    assert exc.value.code == "second_confirmation_required"
    with service.engine.begin() as cx:
        cx.execute(text("UPDATE pages SET content_hash='hash-2' WHERE site_id='gearboxemdad'"))
    with pytest.raises(RemediationError) as exc:
        service.create_run("gearboxemdad", proposal["id"], "wp_meta_description", proposal["evidence_hash"], "key-12345678", True)
    assert exc.value.code == "issue_changed"


def test_pilot_boundary_and_unavailable_credentials(service, monkeypatch):
    import seo_brain.remediation.service as module
    with pytest.raises(RemediationError) as exc:
        service.list_issues("another-site")
    assert exc.value.code in {"site_not_found", "pilot_only"}
    monkeypatch.setattr(module, "resolve_auth", lambda _site: None)
    key = service.list_issues("gearboxemdad")["items"][0]["issue_key"]
    proposal = service.propose("gearboxemdad", key)
    assert not proposal["methods"][0]["available"]
    assert "اتصال نوشتن وردپرس" in proposal["methods"][0]["reason"]
    run = service.create_run("gearboxemdad", proposal["id"], "wp_meta_description", proposal["evidence_hash"], "resume-after-auth-123", True)
    assert run["status"] == "needs_connection"
    with pytest.raises(RemediationError) as exc:
        service.resume_run("gearboxemdad", run["id"])
    assert exc.value.code == "wordpress_auth_required"
    monkeypatch.setattr(module, "resolve_auth", lambda _site: object())
    assert service.resume_run("gearboxemdad", run["id"])["status"] == "queued"


def test_other_site_requires_own_credential_and_rendered_body_owner(service, monkeypatch):
    import seo_brain.remediation.service as module
    body = "این متن نمونه دربارهٔ خدمات سایت است و به اندازهٔ کافی یکتا است تا مالک خروجی بررسی شود."
    with service.engine.begin() as cx:
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url,wp_url) VALUES "
                        "('second','Second','https://second.example/','https://second.example/')"))
        cx.execute(text("INSERT INTO seo_problems(site_id,problem_type,severity,url,related_url,detail) VALUES "
                        "('second','missing_h1','medium','https://second.example/a','','{}')"))
        cx.execute(text("INSERT INTO pages(site_id,url,status_code,h1,h1_count,images,content_hash) VALUES "
                        "('second','https://second.example/a',200,'[]',0,'[]','hash-1')"))
        cx.execute(text("INSERT INTO posts(site_id,wp_id,type,url,title,content_html,modified_gmt) VALUES "
                        "('second',8,'post','https://second.example/a','A',:body,'2026-09-01T00:00:00')"),
                   {"body": f"<p>{body}</p>"})
    monkeypatch.setattr(service, "_rendered", lambda _site, _url, include_body=False: {
        "status": 200, "url": "https://second.example/a", "title": "A", "h1": [], "description": "",
        "canonical": "", "robots": "", "x_robots_tag": "", "images_missing_alt": 0, "word_count": 20,
        **({"_body_text": body} if include_body else {})})
    service._atria = lambda *_args: {"add_body_h1": {"id": "add_body_h1", "value": "عنوان یکتای مناسب صفحه", "confidence": "high"}}
    key = service.list_issues("second")["items"][0]["issue_key"]
    assert service.list_issues("second")["coverage"]["complete"] is False
    monkeypatch.setattr(module, "load_site_auth", lambda _site: None)
    unavailable = service.propose("second", key)
    assert not next(m for m in unavailable["methods"] if m["id"] == "add_body_h1")["available"]
    monkeypatch.setattr(module, "load_site_auth", lambda _site: object())
    ready = service.propose("second", key)
    method = next(m for m in ready["methods"] if m["id"] == "add_body_h1")
    assert method["available"] and method["uncertain"]
    monkeypatch.setattr(service, "_rendered", lambda _site, _url, include_body=False: {
        "status": 200, "url": "https://second.example/a", "title": "A", "h1": [], "description": "",
        "canonical": "", "robots": "", "x_robots_tag": "", "images_missing_alt": 0, "word_count": 20,
        **({"_body_text": "unrelated template content"} if include_body else {})})
    blocked = service.propose("second", key)
    assert not next(m for m in blocked["methods"] if m["id"] == "add_body_h1")["available"]


@pytest.mark.parametrize(("problem_type", "method_id"), [
    ("duplicate_h1", "unique_h1"),
    ("missing_canonical", "wp_canonical"),
    ("important_non_indexable", "remove_noindex"),
])
def test_car_model_template_ownership_blocks_ineffective_wordpress_write(service, problem_type, method_id):
    with service.engine.begin() as cx:
        cx.execute(text("UPDATE posts SET type='car_model' WHERE site_id='gearboxemdad'"))
        cx.execute(text("UPDATE seo_problems SET problem_type=:t WHERE site_id='gearboxemdad'"), {"t": problem_type})
    service._atria = lambda _site, _evidence, _templates: {method_id: {"id": method_id, "value": "مقدار پیشنهادی", "confidence": "high"}}
    key = service.list_issues("gearboxemdad")["items"][0]["issue_key"]
    proposal = service.propose("gearboxemdad", key)
    method = next(m for m in proposal["methods"] if m["id"] == method_id)
    assert method["owner"] == "frontend" and not method["available"] and method["status"] == "needs_connection"
    run = service.create_run("gearboxemdad", proposal["id"], method_id, proposal["evidence_hash"], "owner-locked-123", True)
    assert run["status"] == "needs_connection"
    with pytest.raises(RemediationError) as exc:
        service.resume_run("gearboxemdad", run["id"])
    assert exc.value.code == "frontend_connector_required"


def test_public_run_hides_wordpress_snapshot():
    assert "before_snapshot" not in public_run({"id": "x", "before_snapshot": {"meta": {"private": "secret"}}, "verification": {"ok": True, "before": "private"}})
    assert public_run({"verification": {"ok": True, "before": "private"}})["verification"] == {"ok": True}


def test_body_edits_are_exact_and_bounded():
    before = '<p>این عبارت درباره گیربکس است.</p>'
    edited = RemediationService._edit_body(before, {"kind": "wp_insert_link", "value": "گیربکس"}, "https://pilot.example/target")
    assert '<a href="https://pilot.example/target">گیربکس</a>' in edited
    with pytest.raises(RemediationError):
        RemediationService._edit_body(before, {"kind": "wp_insert_link", "value": "عبارت ناموجود"}, "https://pilot.example/target")


@pytest.mark.parametrize(("post_status", "meta", "expected"), [
    (403, {"emdad_meta_description": ""}, "needs_connection"),
    (200, {}, "needs_connection"),
    (200, {"emdad_meta_description": ""}, "ready"),
])
def test_wordpress_preflight_checks_target_permission_and_meta(service, monkeypatch, post_status, meta, expected):
    import seo_brain.remediation.service as module

    class Auth:
        basic = httpx.BasicAuth("seo-bot", "test-password")

    monkeypatch.setattr(module, "resolve_auth", lambda _site: Auth())

    def handler(request):
        if request.url.path.endswith("/types/post"):
            return httpx.Response(200, json={"rest_base": "posts"})
        return httpx.Response(post_status, json={"id": 7, "type": "post", "slug": "a", "meta": meta,
                                                  "content": {"raw": "<p>text</p>"}, "title": {"raw": "A"}})

    monkeypatch.setattr(service, "_wp_client", lambda *_args: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(service, "_probe_wp_access", RemediationService._probe_wp_access.__get__(service))
    access = service._probe_wp_access("gearboxemdad", "wp_meta_description", {"wp_id": 7, "type": "post"}, {})
    assert access["status"] == expected
    if post_status == 403:
        assert "مجوز" in access["reason"] or "دسترسی" in access["reason"]
    elif not meta:
        assert "emdad_meta_description" in access["reason"]


def test_proposal_and_queue_preserve_permission_block(service, monkeypatch):
    key = service.list_issues("gearboxemdad")["items"][0]["issue_key"]
    monkeypatch.setattr(service, "_probe_wp_access", lambda *_args: {
        "status": "needs_connection", "reason": "وردپرس ویرایش این پست را رد کرد."})
    blocked = service.propose("gearboxemdad", key)
    method = blocked["methods"][0]
    assert not method["available"] and method["status"] == "needs_connection"
    assert "وردپرس ویرایش" in method["reason"] and method["access"]["status"] == "needs_connection"
    run = service.create_run("gearboxemdad", blocked["id"], method["id"], blocked["evidence_hash"], "permission-block-123", True)
    assert run["status"] == "needs_connection"
    assert "وردپرس ویرایش" in service.get_run("gearboxemdad", run["id"])["error"]

    monkeypatch.setattr(service, "_probe_wp_access", lambda *_args: {"status": "ready", "reason": "ok"})
    ready = service.propose("gearboxemdad", key)
    monkeypatch.setattr(service, "_probe_wp_access", lambda *_args: {
        "status": "needs_connection", "reason": "دسترسی پس گرفته شد."})
    # Finish the first run to release the per-site active-run guard.
    service.update_run(run["id"], status="failed")
    revoked = service.create_run("gearboxemdad", ready["id"], ready["methods"][0]["id"],
                                 ready["evidence_hash"], "permission-revoked-123", True)
    assert revoked["status"] == "needs_connection"
    assert revoked["error"] == "دسترسی پس گرفته شد."


def test_recrawl_replaces_removed_source_links(service, tmp_path):
    from seo_brain.common.config import SiteConfig
    from seo_brain.crawler.crawler import CrawlResult, Crawler
    from seo_brain.crawler.parser import parse_html
    from seo_brain.database.db import connect

    url = "https://pilot.example/a"
    crawler = Crawler(SiteConfig(site_id="gearboxemdad", name="Pilot", canonical_url="https://pilot.example/", wp_url="https://wp.example"))
    crawler.raw_dir = tmp_path
    conn = connect(service.engine.url.database)
    try:
        before = '<h1>A</h1><p><a href="https://pilot.example/old">Old</a></p>'
        after = '<h1>A</h1><p><a href="https://pilot.example/new">New</a></p>'
        crawler.persist(conn, CrawlResult(url=url, status_code=200, content_type="text/html",
                                          html=before, parsed=parse_html(before, url)), 0, None, False, "crawl-1")
        crawler.persist(conn, CrawlResult(url=url, status_code=200, content_type="text/html",
                                          html=after, parsed=parse_html(after, url)), 0, None, False, "crawl-2")
        targets = {row[0] for row in conn.execute("SELECT target_url FROM links WHERE site_id=? AND source_url=?", ("gearboxemdad", url))}
        assert targets == {"https://pilot.example/new/"}
    finally:
        conn.close()
        crawler.http.close()


def test_remediation_api_exposes_methods_and_blocks_unconnected_template(service):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from seo_brain.api.deps import require_site
    from seo_brain.api.routers import remediation

    app = FastAPI()
    app.include_router(remediation.router, prefix="/api/v1")
    app.dependency_overrides[require_site] = lambda: {"site_id": "gearboxemdad"}
    app.dependency_overrides[remediation.service] = lambda: service
    client = TestClient(app)
    root = "/api/v1/sites/gearboxemdad/remediation"
    listing = client.get(root + "/problems")
    assert listing.status_code == 200 and listing.json()["total"] == 1
    key = listing.json()["items"][0]["issue_key"]
    proposal = client.post(root + f"/problems/{key}/proposals")
    assert proposal.status_code == 200 and proposal.json()["roadmap"]
    pid = proposal.json()["id"]
    detail = client.get(root + f"/proposals/{pid}").json()
    assert "evidence" not in detail and len(detail["methods"]) == 2
    blocked = client.post(root + "/runs", json={"proposal_id": pid, "method_id": "template_description",
                                                  "evidence_hash": detail["evidence_hash"], "idempotency_key": "template-test-123", "uncertain_confirmed": True})
    assert blocked.status_code == 202 and blocked.json()["status"] == "needs_connection"
    assert "before_snapshot" not in blocked.json()
    history = client.get(root + f"/problems/{key}/runs").json()
    assert len(history) == 1 and history[0]["id"] == blocked.json()["id"]


def test_wordpress_write_verification_idempotency_and_rollback(service, monkeypatch):
    import seo_brain.remediation.service as module

    monkeypatch.setattr(module, "resolve_auth", lambda site_id: object())
    key = service.list_issues("gearboxemdad")["items"][0]["issue_key"]
    proposal = service.propose("gearboxemdad", key)
    run = service.create_run("gearboxemdad", proposal["id"], "wp_meta_description", proposal["evidence_hash"], "same-request-123", True)
    assert run["status"] == "queued" and run["_created"]
    again = service.create_run("gearboxemdad", proposal["id"], "wp_meta_description", proposal["evidence_hash"], "same-request-123", True)
    assert again["id"] == run["id"] and not again["_created"]
    with pytest.raises(RemediationError) as exc:
        service.create_run("gearboxemdad", proposal["id"], "wp_meta_description", proposal["evidence_hash"], "another-request-123", True)
    assert exc.value.code == "site_busy"

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    remote = {"id": 7, "type": "post", "modified_gmt": "2026-09-01T00:00:00", "title": {"raw": "A"},
              "content": {"raw": "<p>text</p>"}, "meta": {"emdad_meta_description": ""}}
    writes = []
    monkeypatch.setattr(service, "_wp_client", lambda *_args: Client())
    monkeypatch.setattr(service, "_wp_resource", lambda *_args: ("https://wp.example/wp-json/wp/v2/posts/7", dict(remote)))

    def request(_client, method, _endpoint, payload=None):
        if method == "GET": return dict(remote)
        writes.append(payload)
        remote["meta"].update(payload["meta"])
        remote["modified_gmt"] = "2026-09-29T01:00:00"
        return dict(remote)

    monkeypatch.setattr(service, "_wp_request", request)
    before = {"status": 200, "url": "https://pilot.example/a", "title": "A", "h1": ["A"], "description": "", "canonical": "", "robots": "", "x_robots_tag": "",
              "links": [], "images": [], "images_missing_alt": 0, "word_count": 20}
    after = {**before, "description": "توضیح پیشنهادی برای صفحه"}
    monkeypatch.setattr(service, "_rendered", lambda *_args: after if writes else before)
    def refresh(*_args):
        with service.engine.begin() as cx:
            cx.execute(text("DELETE FROM seo_problems WHERE site_id='gearboxemdad'"))
        return {"crawl": {"run_id": "crawl-test"}, "analysis": {"run_id": "analysis-test"}}
    monkeypatch.setattr(service, "_refresh_analysis", refresh)
    done = service.execute("gearboxemdad", run["id"])
    assert done["status"] == "verified" and len(writes) == 1
    assert service.execute("gearboxemdad", run["id"])["status"] == "verified" and len(writes) == 1
    remote["meta"]["emdad_meta_description"] = "تغییر جدید مدیر سایت"
    with pytest.raises(RemediationError) as exc:
        service.rollback("gearboxemdad", run["id"])
    assert exc.value.code == "rollback_conflict"
    remote["meta"]["emdad_meta_description"] = "توضیح پیشنهادی برای صفحه"
    assert service.rollback("gearboxemdad", run["id"])["status"] == "rolled_back"
    assert writes[-1] == {"meta": {"emdad_meta_description": ""}}
    with service.engine.connect() as cx:
        events = [row[0] for row in cx.execute(text("SELECT event_type FROM seo_remediation_events WHERE run_id=:r ORDER BY id"), {"r": run["id"]})]
    assert events == ["before_snapshot", "after_snapshot", "verification", "rollback"]
