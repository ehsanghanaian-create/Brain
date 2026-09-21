"""Changing the phone number from inside Brain: scan Brain's synced copy, preview, then rewrite every post/page the
WordPress REST API can reach — and report honestly what it could not (header/Elementor/theme files)."""
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import ops as ops_router
from seo_brain.api.routers import sites as sites_router
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.integrations.wordpress.phone import PhoneService, forms, swap

OLD, NEW = "02122477005", "02122144279"
HOME_HTML = "<header>تماس فوری ۲۲۴۷۷۰۰۵</header><main>تماس: 22477005</main>"   # one hit in the header, one in content


class FakeWp:
    """Minimal WordPress REST: GET a post (context=edit) and POST an update; plus the live home page."""
    def __init__(self):
        self.items = {
            11: {"type": "page", "content": {"raw": "<p>تماس با ما: 2247-7005 و ۲۲۴۷۷۰۰۵</p>"}, "title": {"raw": "امداد"}},
            12: {"type": "post", "content": {"raw": "<p>بدون شماره</p>"}, "title": {"raw": "شمارهٔ ۲۲۴۷-۷۰۰۵"}},
        }
        self.writes: list[tuple[str, dict]] = []
        self.fail_write_for: set[int] = set()

    def __call__(self, method: str, url: str, auth=None, **kw) -> httpx.Response:
        if "/wp-json/wp/v2/" not in url:
            return httpx.Response(200, text=HOME_HTML, request=httpx.Request(method, url))
        tail = url.split("/wp-json/wp/v2/")[1]
        kind, rest = tail.split("/", 1)
        wp_id = int(rest.split("?")[0])
        req = httpx.Request(method, url)
        if method == "GET":
            item = self.items.get(wp_id)
            return httpx.Response(200 if item else 404, json=item or {"code": "not_found"}, request=req)
        if wp_id in self.fail_write_for:
            return httpx.Response(500, json={"code": "boom"}, request=req)
        body = kw.get("json") or {}
        self.writes.append((f"{kind}/{wp_id}", body))
        for key, value in body.items():
            self.items[wp_id][key] = {"raw": value}
        return httpx.Response(200, json=self.items[wp_id], request=req)


@pytest.fixture
def env(tmp_path, monkeypatch):
    eng = make_engine("sqlite:///" + (tmp_path / "phone.db").as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    with eng.begin() as cx:
        cx.execute(text("INSERT INTO sites(site_id, name, canonical_url, wp_url, mode) VALUES('demo','Demo','https://demo.example/','https://demo.example','assisted')"))
        cx.execute(text("INSERT INTO posts(site_id, wp_id, type, url, slug, title, content_html, excerpt, status) VALUES"
                        "('demo', 11, 'page', 'https://demo.example/', 'home', 'امداد', '<p>تماس با ما: 2247-7005 و ۲۲۴۷۷۰۰۵</p>', '', 'publish'),"
                        "('demo', 12, 'post', 'https://demo.example/p', 'p', 'شمارهٔ ۲۲۴۷-۷۰۰۵', '<p>بدون شماره</p>', '', 'publish'),"
                        "('demo', 13, 'post', 'https://demo.example/q', 'q', 'بدون شماره', '<p>هیچ</p>', '', 'publish')"))
    wp = FakeWp()

    class Auth:
        username, app_password = "brain", "app pass"

    monkeypatch.setattr("seo_brain.integrations.wordpress.phone.resolve_auth", lambda site_id: Auth())
    monkeypatch.setattr("seo_brain.integrations.wordpress.writer.resolve_auth", lambda site_id: Auth())
    svc = PhoneService(eng, wp)
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    monkeypatch.setattr(ops_router, "PhoneService", lambda e: svc)
    client = TestClient(app)
    return client, svc, wp, eng


def test_forms_and_swap_keep_every_shape():
    assert forms(OLD) == ["22477005", "2247 7005", "2247-7005", "۲۲۴۷۷۰۰۵", "۲۲۴۷ ۷۰۰۵", "۲۲۴۷-۷۰۰۵",
                          "\\u06f2\\u06f2\\u06f4\\u06f7\\u06f7\\u06f0\\u06f0\\u06f5"]
    text_in = "تماس 22477005 / ۲۲۴۷ ۷۰۰۵ / \\u06f2\\u06f2\\u06f4\\u06f7\\u06f7\\u06f0\\u06f0\\u06f5"
    out = swap(text_in, OLD, NEW)
    assert out == "تماس 22144279 / ۲۲۱۴ ۴۲۷۹ / \\u06f2\\u06f2\\u06f1\\u06f4\\u06f4\\u06f2\\u06f7\\u06f9"
    assert len(out) == len(text_in)                                              # serialized data keeps its lengths


def test_scan_separates_pages_from_the_template(env):
    client, _svc, _wp, _eng = env
    d = client.get("/api/v1/tools/sites/demo/phone/scan", params={"phone": OLD}).json()
    assert d["pages_total"] == 2 and d["occurrences"] == 3
    home = next(p for p in d["pages"] if p["wp_id"] == 11)
    assert home["hits"] == {"content_html": 2} and next(p for p in d["pages"] if p["wp_id"] == 12)["hits"] == {"title": 1}
    assert d["template"]["home_read"] is True and d["template"]["outside_content"] == 1   # the header hit, not page content
    assert "المنتور" in d["template"]["note"]


def test_preview_changes_nothing_then_apply_rewrites_what_rest_can_reach(env):
    client, _svc, wp, _eng = env
    preview = client.post("/api/v1/tools/sites/demo/phone/replace", json={"old_phone": OLD, "new_phone": NEW, "dry_run": True}).json()
    assert preview["status"] == "preview" and preview["pages_targeted"] == 2 and wp.writes == []
    assert {r["status"] for r in preview["results"]} == {"would_change"} and "runbook" in preview

    applied = client.post("/api/v1/tools/sites/demo/phone/replace", json={"old_phone": OLD, "new_phone": NEW, "dry_run": False}).json()
    assert applied["status"] == "applied" and applied["changed"] == 2
    assert sorted(path for path, _ in wp.writes) == ["pages/11", "posts/12"]
    assert wp.items[11]["content"]["raw"] == "<p>تماس با ما: 2214-4279 و ۲۲۱۴۴۲۷۹</p>"
    assert wp.items[12]["title"]["raw"] == "شمارهٔ ۲۲۱۴-۴۲۷۹"
    assert applied["remaining"]["template_or_elementor"] == 1 and "دستورالعمل" in applied["remaining"]["note"]


def test_write_failures_are_reported_per_page(env):
    client, _svc, wp, _eng = env
    wp.fail_write_for = {11}
    out = client.post("/api/v1/tools/sites/demo/phone/replace", json={"old_phone": OLD, "new_phone": NEW, "dry_run": False}).json()
    assert out["changed"] == 1
    failed = next(r for r in out["results"] if r["wp_id"] == 11)
    assert failed["status"] == "write_failed" and "500" in failed["message"]


def test_guards(env):
    client, _svc, _wp, _eng = env
    assert client.post("/api/v1/tools/sites/demo/phone/replace", json={"old_phone": OLD, "new_phone": OLD}).status_code == 422
    assert client.get("/api/v1/tools/sites/nope/phone/scan", params={"phone": OLD}).status_code == 404
