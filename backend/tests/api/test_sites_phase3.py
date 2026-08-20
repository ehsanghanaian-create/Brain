"""Phase 3: connections tests (GSC/GA4/WordPress with injected fakes), site initialisation, Site Brain memory fields."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import sites as sites_router
from seo_brain.connections import service as conn_service
from seo_brain.connections.service import ConnectionsService
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.sites import slugify_domain


class FakeGsc:
    def __init__(self, entries):
        self.entries = entries

    def list_sites(self):
        return self.entries

    def resolve_property(self, wanted):
        host = wanted.replace("https://", "").replace("http://", "").strip("/")
        for e in self.entries:
            if e["siteUrl"] in {wanted, f"sc-domain:{host}", f"https://{host}/"}:
                return e["siteUrl"], e["permissionLevel"]
        return None, None


@pytest.fixture
def env(tmp_path, monkeypatch):
    dbfile = tmp_path / "p3.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(sites_router.SiteInitializer, "__init__", _init_with_root(tmp_path), raising=True)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng
    # a successful WordPress connection now queues the sync → graph pipeline job; keep it in-process and inert here
    from seo_brain.automation.queue import InProcessJobQueue
    q = InProcessJobQueue(sync=True); q.register("wordpress_sync", lambda payload: {"noop": True})
    app.dependency_overrides[deps.job_queue] = lambda: q
    return {"client": TestClient(app), "eng": eng, "root": tmp_path, "monkeypatch": monkeypatch, "queue": q}


def _init_with_root(root):
    from seo_brain.sites.initializer import SiteInitializer
    orig = SiteInitializer.__init__

    def __init__(self, engine, r=None):
        orig(self, engine, root)
    return __init__


def _create(c, sid="demo", **extra):
    r = c.post("/api/v1/sites", json={"site_id": sid, "name": "Demo", "canonical_url": "https://demo.example/", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_migration_0003_and_memory_fields(env):
    c = env["client"]
    assert "0003" in c.get("/api/v1/health").json()["migrations"]["applied"]
    _create(c)
    m = c.get("/api/v1/sites/demo/memory").json()
    assert m["audience"] == {} and m["cta_rules"] == [] and m["forbidden_claims"] == []
    r = c.put("/api/v1/sites/demo/memory", json={
        "business_rules": ["فقط تهران"], "tone": {"voice": "formal", "person": "second"},
        "audience": {"segments": ["مالکان MVM"], "pains": ["خرابی در جاده"], "intent_notes": "فوری"},
        "cta_rules": ["شماره تماس در پاراگراف اول"], "content_rules": ["H1 یکتا"], "forbidden_claims": ["ارزان‌ترین"]})
    assert r.status_code == 200
    body = r.json()
    assert body["audience"]["segments"] == ["مالکان MVM"] and body["cta_rules"] == ["شماره تماس در پاراگراف اول"] and body["forbidden_claims"] == ["ارزان‌ترین"]
    ctx = c.get("/api/v1/sites/demo/memory/context").json()["messages"][0]["content"]
    for needle in ("فقط تهران", "voice=formal", "segments: مالکان MVM", "CTA rules", "NEVER claim", "ارزان‌ترین"):
        assert needle in ctx


def test_slugify_domain():
    assert slugify_domain("https://www.Emdad-Modiran.com/") == "emdad-modiran"
    assert slugify_domain("renaultemdad.com") == "renaultemdad"
    assert slugify_domain("shop.example.co.uk") == "shop-example-co"


def test_initialize_is_idempotent(env):
    c, root = env["client"], env["root"]
    _create(c)
    r = c.post("/api/v1/sites/demo/initialize")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["workspace"]["path"] == "data/sites/demo" and (root / "data" / "sites" / "demo" / "README.md").exists()
    for sub in ("raw", "exports", "uploads", "vault", "logs"):
        assert (root / "data" / "sites" / "demo" / sub).is_dir()
    assert out["memory"]["initialized"] is True and out["graph"]["site_node"] == "site:demo" and out["graph"]["nodes"] == 1
    again = c.post("/api/v1/sites/demo/initialize").json()
    assert again["memory"]["existed"] and again["graph"]["existed"] and again["graph"]["nodes"] == 1
    n = c.get("/api/v1/sites/demo/graph/node/site:demo").json()
    assert n["type"] == "SITE" and n["metadata"]["label"] == "Demo"


def test_connections_status_and_gsc_flow(env, monkeypatch):
    c = env["client"]
    _create(c)
    st = c.get("/api/v1/sites/demo/connections").json()
    assert st["configured"] == {"gsc": None, "ga4": None, "wordpress": None} and st["status"] == {}

    # not configured (no property)
    r = c.post("/api/v1/sites/demo/connections/gsc/test", json={})
    assert r.status_code == 200 and r.json()["status"] == "not_configured" and r.json()["ok"] is False

    # google client not configured
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False); monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(conn_service, "env", lambda k, d=None: {"GSC_TOKEN_PATH": str(env["root"] / "tok.json")}.get(k, d))
    r = c.post("/api/v1/sites/demo/connections/gsc/test", json={"property": "sc-domain:demo.example"}).json()
    assert r["status"] == "not_configured" and "GOOGLE_CLIENT_ID" in r["message"]

    # configured + token with scope + fake client → ok, property stored on the site
    monkeypatch.setattr(conn_service, "env", lambda k, d=None: {"GOOGLE_CLIENT_ID": "x", "GOOGLE_CLIENT_SECRET": "y",
                                                                  "GSC_TOKEN_PATH": str(env["root"] / "tok.json")}.get(k, d))
    (env["root"] / "tok.json").write_text(json.dumps({"refresh_token": "r", "scopes": [conn_service.GSC_SCOPE]}), encoding="utf-8")
    fake = FakeGsc([{"siteUrl": "sc-domain:demo.example", "permissionLevel": "siteOwner"}])
    app = c.app; app.dependency_overrides[sites_router.connections_service] = lambda: ConnectionsService(env["eng"], gsc_client_factory=lambda sid: fake)
    r = c.post("/api/v1/sites/demo/connections/gsc/test", json={"property": "https://demo.example/"}).json()
    assert r["ok"] and r["detail"]["property"] == "sc-domain:demo.example" and r["detail"]["permission"] == "siteOwner"
    assert c.get("/api/v1/sites/demo").json()["gsc_property"] == "sc-domain:demo.example"
    st = c.get("/api/v1/sites/demo/connections").json()
    assert st["status"]["gsc"]["status"] == "ok" and st["status"]["gsc"]["tested_at"]

    # not found in account
    r = c.post("/api/v1/sites/demo/connections/gsc/test", json={"property": "https://other.example/"}).json()
    assert r["status"] == "not_found"

    # properties listing for the wizard dropdown
    props = c.get("/api/v1/connections/gsc/properties").json()
    assert props["status"] == "ok" and props["properties"][0]["property"] == "sc-domain:demo.example"


def test_ga4_scope_gate_and_ok(env, monkeypatch):
    c = env["client"]; _create(c)
    tok = env["root"] / "tok.json"
    monkeypatch.setattr(conn_service, "env", lambda k, d=None: {"GOOGLE_CLIENT_ID": "x", "GOOGLE_CLIENT_SECRET": "y", "GSC_TOKEN_PATH": str(tok)}.get(k, d))
    # _token_info reads through the shared storage helper now — keep the test hermetic (no real store/network)
    monkeypatch.setattr("seo_brain.gsc.client.read_token_json", lambda: tok.read_text(encoding="utf-8") if tok.exists() else None)
    tok.write_text(json.dumps({"refresh_token": "r", "scopes": [conn_service.GSC_SCOPE]}), encoding="utf-8")
    r = c.post("/api/v1/sites/demo/connections/ga4/test", json={"property": "123456"}).json()
    assert r["status"] == "not_authorized" and r["detail"]["required_scope"] == conn_service.GA4_SCOPE
    assert c.post("/api/v1/sites/demo/connections/ga4/test", json={"property": "abc"}).json()["status"] == "not_configured"
    tok.write_text(json.dumps({"refresh_token": "r", "scopes": [conn_service.GSC_SCOPE, conn_service.GA4_SCOPE]}), encoding="utf-8")
    c.app.dependency_overrides[sites_router.connections_service] = lambda: ConnectionsService(env["eng"], ga4_report_factory=lambda pid: {"rowCount": 1})
    r = c.post("/api/v1/sites/demo/connections/ga4/test", json={"property": "properties/123456"}).json()
    assert r["ok"] and r["detail"]["property"] == "123456"
    assert c.get("/api/v1/sites/demo").json()["ga4_property"] == "123456"


def test_wordpress_probe_with_fake_http(env):
    c = env["client"]; _create(c)
    def fake_fetch(url):
        return httpx.Response(200, json={"name": "Demo WP", "namespaces": ["wp/v2", "yoast/v1"]}, request=httpx.Request("GET", url))
    c.app.dependency_overrides[sites_router.connections_service] = lambda: ConnectionsService(env["eng"], wp_fetch=fake_fetch)
    r = c.post("/api/v1/sites/demo/connections/wordpress/test", json={"property": "https://demo.example"}).json()
    assert r["ok"] and r["detail"]["wp_v2"] is True and r["detail"]["name"] == "Demo WP"
    assert c.get("/api/v1/sites/demo").json()["wp_url"] == "https://demo.example"
    assert c.post("/api/v1/sites/demo/connections/nope/test", json={}).status_code == 404


def test_wordpress_url_without_scheme_is_normalized(env):
    c = env["client"]; _create(c)
    seen_urls = []
    def fake_fetch(url):
        seen_urls.append(url)
        return httpx.Response(200, json={"name": "Demo WP", "namespaces": ["wp/v2"]}, request=httpx.Request("GET", url))
    c.app.dependency_overrides[sites_router.connections_service] = lambda: ConnectionsService(env["eng"], wp_fetch=fake_fetch)
    r = c.post("/api/v1/sites/demo/connections/wordpress/test", json={"property": "demo.example"}).json()
    assert r["ok"] and r["detail"]["url"] == "https://demo.example/wp-json/"
    assert r["detail"]["rest_endpoint"] == "https://demo.example/wp-json/wp/v2/"
    assert seen_urls[0] == "https://demo.example/wp-json/"                      # main probe first, then diagnostics
    # public stage only: base URL + /wp-json/ — users/me is NEVER requested without credentials
    assert set(seen_urls) == {"https://demo.example/wp-json/", "https://demo.example/"}
    assert c.get("/api/v1/sites/demo").json()["wp_url"] == "https://demo.example"
    steps = [(d["step"], d["stage"]) for d in r["detail"]["diagnostics"]]
    assert steps == [("base_url", "public"), ("rest_public", "public"), ("auth", "auth")] and all("fa" in d for d in r["detail"]["diagnostics"])
    assert r["detail"]["diagnostics"][2]["skipped"] is True and r["detail"]["auth"] == {"configured": False, "status": "not_configured", "message": "بدون احراز هویت (اختیاری)"}
    assert r["detail"]["trace"] and any("normalize → https://demo.example" in t for t in r["detail"]["trace"])


@pytest.mark.parametrize("raw,stored", [
    ("https://demo.example/wp-json/", "https://demo.example"),
    ("demo.example/wp-json", "https://demo.example"),
    ("https://demo.example/blog/wp-json/wp/v2/", "https://demo.example/blog"),
    ("HTTPS://Demo.Example/", "https://Demo.Example"),
])
def test_wordpress_rest_root_pasted_is_reduced_to_site_base(env, raw, stored):
    c = env["client"]; _create(c)
    def fake_fetch(url):
        return httpx.Response(200, json={"name": "Demo WP", "namespaces": ["wp/v2"]}, request=httpx.Request("GET", url))
    c.app.dependency_overrides[sites_router.connections_service] = lambda: ConnectionsService(env["eng"], wp_fetch=fake_fetch)
    r = c.post("/api/v1/sites/demo/connections/wordpress/test", json={"property": raw}).json()
    assert r["ok"], r
    assert r["detail"]["site_url"] == stored and r["detail"]["url"] == stored + "/wp-json/"
    assert c.get("/api/v1/sites/demo").json()["wp_url"] == stored


@pytest.mark.parametrize("raw", ["ftp://demo.example", "demo", "user:pass@demo.example", "https://", "http://?x=1", "mailto:a@b.c", "aaaa bbbb cccc dddd eeee ffff", "xxxxxxxxxxxxxxxxxxxxxxxx"])
def test_wordpress_malformed_urls_rejected_without_network(env, raw):
    c = env["client"]; _create(c)
    calls = []
    def fake_fetch(url):
        calls.append(url); raise AssertionError("no network for malformed input")
    c.app.dependency_overrides[sites_router.connections_service] = lambda: ConnectionsService(env["eng"], wp_fetch=fake_fetch)
    r = c.post("/api/v1/sites/demo/connections/wordpress/test", json={"property": raw}).json()
    assert r["status"] == "error" and not r["ok"] and calls == [] and r["detail"].get("trace")
    assert "xxxxxxxxxxxxxxxxxxxxxxxx" not in r["message"] and "pass@" not in r["message"]


def _wp_auth_env(env, tmp_secret_dir="secrets"):
    """Isolated SecretStore for per-site WordPress credentials + public /wp-json/ fake + capture of authenticated probes."""
    from seo_brain.core.secrets import SecretStore
    from seo_brain.wordpress import auth as wp_auth
    store = SecretStore(env["root"] / tmp_secret_dir)
    env["monkeypatch"].setattr(wp_auth, "get_secret_store", lambda: store)
    env["monkeypatch"].setattr(conn_service, "env", lambda k, d=None: d)         # no .env credentials
    public_urls = []
    def fake_fetch(url):
        public_urls.append(url)
        return httpx.Response(200, json={"name": "Demo WP", "namespaces": ["wp/v2"]}, request=httpx.Request("GET", url))
    auth_calls = []
    def fake_fetch_auth(url, basic, _responses={}):
        auth_calls.append((url, basic))
        user, pw = basic
        if pw == "aaaa bbbb cccc dddd eeee ffff" and user == "editor":
            return httpx.Response(200, json={"id": 7, "name": "Editor Demo", "roles": ["editor"], "capabilities": {"read": True}}, request=httpx.Request("GET", url))
        if pw == "blocked":
            return httpx.Response(403, json={"code": "rest_forbidden"}, request=httpx.Request("GET", url))
        if pw == "slow":
            raise httpx.ConnectTimeout("timeout")
        return httpx.Response(401, json={"code": "incorrect_password"}, request=httpx.Request("GET", url))
    env["client"].app.dependency_overrides[sites_router.connections_service] = lambda: ConnectionsService(env["eng"], wp_fetch=fake_fetch, wp_fetch_auth=fake_fetch_auth)
    return store, public_urls, auth_calls


def test_wordpress_public_rest_works_without_credentials_and_users_me_is_not_called(env):
    c = env["client"]; _create(c)
    store, public_urls, auth_calls = _wp_auth_env(env)
    r = c.post("/api/v1/sites/demo/connections/wordpress/test", json={"property": "https://demo.example"}).json()
    assert r["ok"] and r["status"] == "ok"
    assert auth_calls == [] and not any("users/me" in u for u in public_urls)          # never anonymous users/me
    assert r["detail"]["auth"]["configured"] is False and r["detail"]["diagnostics"][-1]["skipped"] is True
    st = c.get("/api/v1/sites/demo/connections").json()
    assert st["wordpress_auth"] == {"configured": False, "username": None, "key_hint": None, "source": None}


def test_wordpress_valid_application_password_connects_user_and_is_stored_encrypted(env):
    c = env["client"]; _create(c)
    store, public_urls, auth_calls = _wp_auth_env(env)
    r = c.post("/api/v1/sites/demo/connections/wordpress/test", json={"property": "https://demo.example", "wp_username": "editor", "wp_app_password": "aaaa bbbb cccc dddd eeee ffff"}).json()
    assert r["ok"], r
    a = r["detail"]["auth"]
    assert a["status"] == "ok" and a["user_name"] == "Editor Demo" and a["roles"] == ["editor"] and a["username"] == "editor" and a["key_hint"] == "ffff" and a["stored"] is True and a["source"] == "explicit"
    assert "احراز هویت تأیید شد" in r["message"]
    step = next(d for d in r["detail"]["diagnostics"] if d["step"] == "auth")
    assert step["ok"] is True and step["status_code"] == 200 and "Editor Demo" in step["hint"]
    assert auth_calls[0][0] == "https://demo.example/wp-json/wp/v2/users/me?context=edit" and auth_calls[0][1] == ("editor", "aaaa bbbb cccc dddd eeee ffff")
    # password never leaks into the response/trace; stored only in the SecretStore (encrypted) — and reused on the next test without resending
    import base64
    blob = json.dumps(r, ensure_ascii=False)
    assert "aaaa bbbb" not in blob and base64.b64encode(b"editor:aaaa bbbb cccc dddd eeee ffff").decode() not in blob
    assert store.exists("wp-auth-demo")
    st = c.get("/api/v1/sites/demo/connections").json()["wordpress_auth"]
    assert st == {"configured": True, "username": "editor", "key_hint": "ffff", "source": "site"}
    r2 = c.post("/api/v1/sites/demo/connections/wordpress/test", json={"property": "https://demo.example"}).json()
    assert r2["detail"]["auth"]["status"] == "ok" and r2["detail"]["auth"]["source"] == "site"
    # clear credentials → back to public-only
    r3 = c.post("/api/v1/sites/demo/connections/wordpress/test", json={"property": "https://demo.example", "clear_wp_credentials": True}).json()
    assert r3["detail"]["auth"]["configured"] is False and not store.exists("wp-auth-demo")


@pytest.mark.parametrize("pw,expected_status,substr,code", [
    ("wrong-password-1234", "not_authorized", "نادرست", 401),
    ("blocked", "forbidden", "403", 403),
    ("slow", "timeout", "timeout", None),
])
def test_wordpress_invalid_application_password_gives_clear_error(env, pw, expected_status, substr, code):
    c = env["client"]; _create(c)
    store, public_urls, auth_calls = _wp_auth_env(env)
    r = c.post("/api/v1/sites/demo/connections/wordpress/test", json={"property": "https://demo.example", "wp_username": "editor", "wp_app_password": pw}).json()
    assert r["ok"] and r["status"] == "ok"                      # public REST still fine — auth failure is reported separately, never as UnsupportedProtocol
    a = r["detail"]["auth"]
    assert a["configured"] is True and a["status"] == expected_status and substr in a["message"] and "احراز هویت ناموفق" in r["message"]
    step = next(d for d in r["detail"]["diagnostics"] if d["step"] == "auth")
    assert step["ok"] is False and step["status_code"] == code and step["hint"]
    assert not store.exists("wp-auth-demo")                     # failed credentials are NOT stored
    assert pw not in json.dumps(r, ensure_ascii=False) and pw not in " ".join(r["detail"]["trace"])


def test_wordpress_application_password_pasted_as_url_gives_clear_error(env):
    """Regression for the reported bug: an Application-Password-like value must never reach
    httpx as a URL (which raised UnsupportedProtocol on something like `<token>/wp-json/`)."""
    c = env["client"]; _create(c)
    calls = []
    def fake_fetch(url):
        calls.append(url)
        raise AssertionError("must not attempt an HTTP request for a non-URL value")
    c.app.dependency_overrides[sites_router.connections_service] = lambda: ConnectionsService(env["eng"], wp_fetch=fake_fetch)
    r = c.post("/api/v1/sites/demo/connections/wordpress/test", json={"property": "f6wOsgR8NahkD5waVkCHKxXu"})
    body = r.json()
    assert not body["ok"] and body["status"] == "error"
    assert "f6wOsgR8NahkD5waVkCHKxXu" not in body["message"]
    assert calls == []  # no network call attempted
    assert c.get("/api/v1/sites/demo").json()["wp_url"] is None  # nothing bad got stored


@pytest.mark.parametrize("exc,expected_status,expected_substr", [
    (httpx.UnsupportedProtocol("bad"), "error", "پروتکل"),
    (httpx.ConnectTimeout("timeout"), "error", "timeout"),
    (httpx.ConnectError("[Errno -2] Name or service not known"), "error", "DNS"),
])
def test_wordpress_network_errors_are_differentiated(env, exc, expected_status, expected_substr):
    c = env["client"]; _create(c)
    def fake_fetch(url):
        raise exc
    c.app.dependency_overrides[sites_router.connections_service] = lambda: ConnectionsService(env["eng"], wp_fetch=fake_fetch)
    r = c.post("/api/v1/sites/demo/connections/wordpress/test", json={"property": "https://demo.example"}).json()
    assert r["status"] == expected_status
    assert expected_substr in r["message"]


@pytest.mark.parametrize("status_code,expected_status", [(401, "not_authorized"), (403, "not_authorized"), (404, "not_found")])
def test_wordpress_http_error_statuses_are_differentiated(env, status_code, expected_status):
    c = env["client"]; _create(c)
    def fake_fetch(url):
        return httpx.Response(status_code, json={}, request=httpx.Request("GET", url))
    c.app.dependency_overrides[sites_router.connections_service] = lambda: ConnectionsService(env["eng"], wp_fetch=fake_fetch)
    r = c.post("/api/v1/sites/demo/connections/wordpress/test", json={"property": "https://demo.example"}).json()
    assert r["status"] == expected_status
    assert r["detail"]["status_code"] == status_code


def test_concurrent_connection_tests_do_not_overwrite_each_other(env):
    """Regression: three parallel tests each saving the whole row lost the GSC property (last writer wins)."""
    c = env["client"]; _create(c)
    tok = env["root"] / "tok.json"
    env["monkeypatch"].setattr(conn_service, "env", lambda k, d=None: {"GOOGLE_CLIENT_ID": "x", "GOOGLE_CLIENT_SECRET": "y", "GSC_TOKEN_PATH": str(tok)}.get(k, d))
    env["monkeypatch"].setattr("seo_brain.gsc.client.read_token_json", lambda: tok.read_text(encoding="utf-8") if tok.exists() else None)
    tok.write_text(json.dumps({"refresh_token": "r", "scopes": [conn_service.GSC_SCOPE, conn_service.GA4_SCOPE]}), encoding="utf-8")
    fake = FakeGsc([{"siteUrl": "sc-domain:demo.example", "permissionLevel": "siteOwner"}])
    def fake_fetch(url):
        return httpx.Response(200, json={"name": "Demo", "namespaces": ["wp/v2"]}, request=httpx.Request("GET", url))
    c.app.dependency_overrides[sites_router.connections_service] = lambda: ConnectionsService(
        env["eng"], gsc_client_factory=lambda sid: fake, ga4_report_factory=lambda pid: {"rowCount": 0}, wp_fetch=fake_fetch)
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(3) as ex:
        list(ex.map(lambda kv: c.post(f"/api/v1/sites/demo/connections/{kv[0]}/test", json={"property": kv[1]}),
                    [("gsc", "sc-domain:demo.example"), ("ga4", "555"), ("wordpress", "https://demo.example")]))
    s = c.get("/api/v1/sites/demo").json()
    assert s["gsc_property"] == "sc-domain:demo.example" and s["ga4_property"] == "555" and s["wp_url"] == "https://demo.example"
    st = c.get("/api/v1/sites/demo/connections").json()
    assert st["configured"] == {"gsc": "sc-domain:demo.example", "ga4": "555", "wordpress": "https://demo.example"}


def test_delete_site_with_connections_and_memory(env):
    c = env["client"]; _create(c)
    c.post("/api/v1/sites/demo/initialize")
    c.post("/api/v1/sites/demo/connections/gsc/test", json={})          # writes a site_connections row
    r = c.delete("/api/v1/sites/demo")
    assert r.status_code == 409 and {"site_connections", "site_memory", "graph_nodes"} <= set(r.json()["error"]["details"])
    assert c.delete("/api/v1/sites/demo?force=true").status_code == 200
    assert c.get("/api/v1/sites/demo").status_code == 404
