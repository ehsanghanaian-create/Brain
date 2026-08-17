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
    return {"client": TestClient(app), "eng": eng, "root": tmp_path, "monkeypatch": monkeypatch}


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


def test_concurrent_connection_tests_do_not_overwrite_each_other(env):
    """Regression: three parallel tests each saving the whole row lost the GSC property (last writer wins)."""
    c = env["client"]; _create(c)
    tok = env["root"] / "tok.json"
    env["monkeypatch"].setattr(conn_service, "env", lambda k, d=None: {"GOOGLE_CLIENT_ID": "x", "GOOGLE_CLIENT_SECRET": "y", "GSC_TOKEN_PATH": str(tok)}.get(k, d))
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
