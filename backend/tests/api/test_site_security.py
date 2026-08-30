"""security.* capability — connector reuse, auth, idempotency, isolation, error mapping (no real HTTP)."""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.integrations.wordpress.security import WordPressSecurityService, normalize_single_ip, resolve_site_by_domain

SID = "renaultemdad"
TEST_IP = "203.0.113.77"


@pytest.fixture()
def c(tmp_path, monkeypatch):
    eng = make_engine("sqlite:///" + (tmp_path / "sec.db").as_posix())
    migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app)
    client.eng = eng  # type: ignore[attr-defined]
    return client


def _seed_site(c, site_id=SID, url="https://renaultemdad.com"):
    with c.eng.begin() as cx:
        cx.execute(text("INSERT OR REPLACE INTO sites(site_id, name, canonical_url, wp_url, mode, created_at, updated_at) "
                        "VALUES(:s, :s, :u, :u, 'manual', '2026-01-01', '2026-01-01')"), {"s": site_id, "u": url})


class FakePlugin:
    """In-memory stand-in for the WP plugin REST API (contract of v1.2.0)."""

    def __init__(self):
        self.ips: dict[str, dict] = {}
        self.fail: str | None = None  # None | 'auth' | 'missing' | 'timeout' | 'maintenance'
        self.seen_auth: tuple | None = None

    def __call__(self, method, url, auth=None, **kw):
        self.seen_auth = auth
        if self.fail == "timeout":
            raise httpx.ConnectTimeout("boom")
        if self.fail == "auth":
            return httpx.Response(401, json={"code": "rest_forbidden"})
        if self.fail == "missing":
            return httpx.Response(404, json={"code": "rest_no_route"})
        if self.fail == "maintenance":
            return httpx.Response(503, text="down")
        if url.endswith("/status"):
            return httpx.Response(200, json={"connected": True, "plugin": "seo-brain", "plugin_version": "1.2.0",
                                             "site": "renaultemdad.com", "writable": True, "count": len(self.ips)})
        if url.endswith("/security/blocked"):
            return httpx.Response(200, json={"items": [{"ip": ip, **m, "expires_at": None, "status": "blocked"}
                                                       for ip, m in self.ips.items()]})
        body = json.loads(kw.get("json") and json.dumps(kw["json"]) or "{}")
        ip = body.get("ip", "")
        if url.endswith("/security/block-ip"):
            if ip in self.ips:
                return httpx.Response(200, json={"success": True, "ip": ip, "status": "already_blocked"})
            self.ips[ip] = {"reason": body.get("reason") or None, "blocked_at": "2026-08-30T00:00:00+00:00"}
            return httpx.Response(200, json={"success": True, "ip": ip, "status": "blocked"})
        if url.endswith("/security/unblock-ip"):
            if ip not in self.ips:
                return httpx.Response(200, json={"success": True, "ip": ip, "status": "already_unblocked"})
            del self.ips[ip]
            return httpx.Response(200, json={"success": True, "ip": ip, "status": "unblocked"})
        return httpx.Response(404, json={"code": "rest_no_route"})


@pytest.fixture()
def svc(c, monkeypatch):
    _seed_site(c)
    plugin = FakePlugin()
    monkeypatch.setattr("seo_brain.integrations.wordpress.security.resolve_auth",
                        lambda site_id: type("A", (), {"username": f"admin-{site_id}", "app_password": f"pw-{site_id}"})()
                        if site_id == SID else None)
    return WordPressSecurityService(c.eng, http=plugin), plugin


def test_ip_normalization_rejects_everything_but_single_ips():
    assert normalize_single_ip(" 203.0.113.77 ") == "203.0.113.77"
    assert normalize_single_ip("2001:0db8:0000::0001") == "2001:db8::1"   # normalized
    for bad in ("renaultemdad.com", "https://x.com", "1.2.3.0/24", "1.2.3.*", "", "not-an-ip"):
        assert normalize_single_ip(bad) is None, bad


def test_status_block_unblock_idempotency_and_audit(c, svc):
    s, plugin = svc
    st = s.get_status(SID)
    assert st["connected"] is True and st["plugin_version"] == "1.2.0" and st["count"] == 0
    assert plugin.seen_auth == (f"admin-{SID}", f"pw-{SID}")            # existing connector credentials reused

    r1 = s.block_ip(SID, TEST_IP, "ترافیک مشکوک")
    assert r1 == {"success": True, "ip": TEST_IP, "status": "blocked"}
    assert s.block_ip(SID, TEST_IP, None)["status"] == "already_blocked"  # idempotent
    assert [i["ip"] for i in s.list_blocked(SID)["items"]] == [TEST_IP]

    u1 = s.unblock_ip(SID, TEST_IP)
    assert u1["status"] == "unblocked"
    assert s.unblock_ip(SID, TEST_IP)["status"] == "already_unblocked"   # idempotent
    assert s.list_blocked(SID)["items"] == []

    audit = s.audit(SID)
    assert [a["action"] for a in audit] == ["unblock", "unblock", "block", "block"]
    assert all(a["ok"] for a in audit) and audit[-1]["reason"] == "ترافیک مشکوک"


def test_invalid_ip_never_reaches_the_site(c, svc):
    s, plugin = svc
    r = s.block_ip(SID, "1.2.3.0/24")
    assert r["success"] is False and r["code"] == "invalid_ip" and plugin.ips == {}


def test_error_mapping_auth_missing_timeout_maintenance(c, svc):
    s, plugin = svc
    for fail, code in (("auth", "auth_failed"), ("missing", "plugin_missing"),
                       ("timeout", "timeout"), ("maintenance", "site_unavailable")):
        plugin.fail = fail
        st = s.get_status(SID)
        assert st["connected"] is False and st["code"] == code, fail
        b = s.block_ip(SID, TEST_IP, None)
        assert b["success"] is False and b["code"] == code, fail
    plugin.fail = None


def test_site_and_credential_isolation(c, svc):
    s, plugin = svc
    _seed_site(c, "othersite", "https://example.org")                    # no credentials stored for it
    r = s.block_ip("othersite", TEST_IP, None)
    assert r["success"] is False and r["code"] == "credentials_missing"  # never falls back to another site's auth
    assert s.get_status("ghost")["code"] == "site_not_found"
    assert resolve_site_by_domain(c.eng, "renaultemdad.com") == SID
    assert resolve_site_by_domain(c.eng, "www.renaultemdad.com") == SID
    assert resolve_site_by_domain(c.eng, "unknown.example") is None


def test_api_routes_are_site_scoped_and_never_leak_secrets(c, monkeypatch):
    _seed_site(c)
    plugin = FakePlugin()
    monkeypatch.setattr("seo_brain.integrations.wordpress.security.resolve_auth",
                        lambda site_id: type("A", (), {"username": "u", "app_password": "SUPER-SECRET-PW"})())
    monkeypatch.setattr("seo_brain.api.routers.site_security.WordPressSecurityService",
                        lambda eng: WordPressSecurityService(eng, http=plugin))
    r = c.post(f"/api/v1/sites/{SID}/security/block", json={"ip": TEST_IP, "reason": "test"})
    assert r.status_code == 200 and r.json()["status"] == "blocked"
    assert "SUPER-SECRET-PW" not in r.text
    st = c.get(f"/api/v1/sites/{SID}/security/status").json()
    assert st["connected"] is True and "SUPER-SECRET-PW" not in json.dumps(st)
    res = c.get("/api/v1/security/resolve-site", params={"domain": "renaultemdad.com"}).json()
    assert res == {"domain": "renaultemdad.com", "site_id": SID, "configured": True}
