"""Web Google OAuth (SaaS onboarding on the existing auth core): authorize URL, callback exchange writes the SAME
token format the GSC/GA4 clients read, callback works without X-API-Token (state nonce is the guard), status/email,
disconnect, and GA4 property discovery via the Admin API — no duplicate OAuth architecture."""
import json

import pytest
from fastapi.testclient import TestClient

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.connections import google_oauth
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate


@pytest.fixture
def env(tmp_path, monkeypatch):
    eng = make_engine("sqlite:///" + (tmp_path / "g.db").as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("GSC_TOKEN_PATH", str(tmp_path / "tokens" / "gsc_token.json"))
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng
    return {"client": TestClient(app), "tmp": tmp_path}


def test_authorize_builds_google_url_with_existing_scopes_and_state(env):
    c = env["client"]
    r = c.get("/api/v1/connections/google/authorize")
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert url.startswith("https://accounts.google.com/o/oauth2/auth")
    assert "webmasters.readonly" in url and "analytics.readonly" in url          # data scopes unchanged
    assert "userinfo.email" in url and "access_type=offline" in url and "state=" in url
    assert "127.0.0.1%3A8000%2Fapi%2Fv1%2Fconnections%2Fgoogle%2Fcallback" in url or "callback" in r.json()["redirect_uri"]


def test_callback_exchanges_code_and_writes_compatible_token(env, monkeypatch):
    c = env["client"]
    state = c.get("/api/v1/connections/google/authorize").json()["url"].split("state=")[1].split("&")[0]

    class _Creds:
        token = "at-1"
        refresh_token = "rt-1"
        scopes = google_oauth.WEB_SCOPES
        id_token = "x." + __import__("base64").urlsafe_b64encode(json.dumps({"email": "user@example.com"}).encode()).decode().rstrip("=") + ".y"
        def to_json(self):
            return json.dumps({"token": self.token, "refresh_token": self.refresh_token, "scopes": self.scopes,
                               "client_id": "test-client-id", "client_secret": "test-secret", "expiry": "2027-01-01T00:00:00Z"})

    class _Flow:
        credentials = _Creds()
        def fetch_token(self, code=None):
            assert code == "auth-code-1"

    monkeypatch.setattr(google_oauth, "_flow", lambda ru: _Flow())
    r = c.get("/api/v1/connections/google/callback", params={"code": "auth-code-1", "state": state})
    assert r.status_code == 200 and "اتصال برقرار شد" in r.text and "user@example.com" in r.text
    assert "at-1" not in r.text and "rt-1" not in r.text                          # never echo tokens
    # token file: same format the existing clients read (connections.service._token_info parses it)
    from seo_brain.connections.service import _token_info
    tok = _token_info()
    assert tok["present"] is True and "https://www.googleapis.com/auth/analytics.readonly" in tok["scopes"]
    # status now connected with the account email
    st = c.get("/api/v1/connections/google/status").json()
    assert st["connected"] is True and st["email"] == "user@example.com" and st["gsc_scope"] and st["ga4_scope"]
    # replayed/expired state → 400, token untouched
    r2 = c.get("/api/v1/connections/google/callback", params={"code": "auth-code-1", "state": state})
    assert r2.status_code == 400
    # disconnect removes the local files
    monkeypatch.setattr("httpx.post", lambda *a, **k: type("R", (), {"status_code": 200})())
    d = c.delete("/api/v1/connections/google").json()
    assert d["disconnected"] is True
    assert c.get("/api/v1/connections/google/status").json()["connected"] is False


def test_callback_is_reachable_without_api_token_but_other_routes_are_not(env, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "secret-token")
    c = env["client"]
    assert c.get("/api/v1/connections/google/status").status_code == 401                       # protected
    r = c.get("/api/v1/connections/google/callback", params={"error": "access_denied"})        # public (Google redirect)
    assert r.status_code == 400 and "X-API-Token" not in r.text and "اتصال انجام نشد" in r.text
    assert c.get("/api/v1/connections/google/status", headers={"X-API-Token": "secret-token"}).status_code == 200


def test_ga4_property_discovery_via_admin_api(env, monkeypatch):
    c = env["client"]
    # not authorized before any token exists
    assert c.get("/api/v1/connections/ga4/properties").json()["status"] == "not_authorized"
    monkeypatch.setattr("seo_brain.connections.service._token_info",
                        lambda: {"present": True, "scopes": ["https://www.googleapis.com/auth/webmasters.readonly",
                                                             "https://www.googleapis.com/auth/analytics.readonly"]})

    class _Req:
        def __init__(self, data): self._d = data
        def execute(self): return self._d

    class _Summaries:
        def list(self, pageSize=200, pageToken=None):  # noqa: N803
            return _Req({"accountSummaries": [{"displayName": "شرکت نمونه", "propertySummaries": [
                {"property": "properties/471988572", "displayName": "سایت نمونه"},
                {"property": "properties/340307505", "displayName": "سایت دوم"}]}]})

    class _Admin:
        def accountSummaries(self): return _Summaries()  # noqa: N802

    from seo_brain.api.routers import sites as sites_router
    from seo_brain.connections import ConnectionsService
    eng = make_engine("sqlite:///:memory:"); migrate(eng)
    c.app.dependency_overrides[sites_router.connections_service] = lambda: ConnectionsService(eng, ga4_admin_factory=lambda: _Admin())
    out = c.get("/api/v1/connections/ga4/properties").json()
    assert out["status"] == "ok" and len(out["properties"]) == 2
    assert out["properties"][0] == {"property_id": "471988572", "display_name": "سایت نمونه", "account": "شرکت نمونه"}


def test_client_save_uses_secret_store_and_masks(env, monkeypatch, tmp_path):
    from seo_brain.core.secrets import SecretStore
    store = SecretStore(tmp_path / "secrets")
    monkeypatch.setattr("seo_brain.core.secrets.get_secret_store", lambda: store)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    c = env["client"]
    # invalid id → 422 with a clear Persian error
    r = c.put("/api/v1/connections/google/client", json={"client_id": "not-a-google-id-at-all", "client_secret": "GOCSPX-abcdefgh"})
    assert r.status_code == 422 and "apps.googleusercontent.com" in r.json()["error"]["message"]
    # valid → stored encrypted in the EXISTING SecretStore refs; the secret is never returned
    cid = "918100000000-abcdefghijklmnop.apps.googleusercontent.com"
    r = c.put("/api/v1/connections/google/client", json={"client_id": cid, "client_secret": "GOCSPX-supersecret123"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is True and "supersecret" not in json.dumps(body)
    assert body["client_id_hint"].startswith("91810000") and "…" in body["client_id_hint"] and len(body["client_id_hint"]) < len(cid)
    assert store.get("google-client-id") == cid and store.get("google-client-secret") == "GOCSPX-supersecret123"
    # status reports the client as configured purely from the store (no .env)
    st = c.get("/api/v1/connections/google/status").json()
    assert st["client_configured"] is True and st["client_id_hint"] == body["client_id_hint"]


def test_oauth_state_survives_restart(env, monkeypatch):
    c = env["client"]
    state = c.get("/api/v1/connections/google/authorize").json()["url"].split("state=")[1].split("&")[0]
    google_oauth._states.clear()                      # simulate an API restart between /authorize and /callback

    class _Creds:
        token, refresh_token, scopes, id_token = "at", "rt", google_oauth.WEB_SCOPES, None
        def to_json(self):
            return json.dumps({"token": "at", "refresh_token": "rt", "scopes": self.scopes, "expiry": "2027-01-01T00:00:00Z"})

    class _Flow:
        credentials = _Creds()
        def fetch_token(self, code=None):
            pass

    monkeypatch.setattr(google_oauth, "_flow", lambda ru: _Flow())
    r = c.get("/api/v1/connections/google/callback", params={"code": "c1", "state": state})
    assert r.status_code == 200 and "اتصال برقرار شد" in r.text     # the state was reloaded from the file


def test_no_cli_hints_in_user_facing_messages():
    """Every not-authorized message must point at the Google Account card, never at a terminal command."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2] / "seo_brain"
    offenders = []
    for p in root.rglob("*.py"):
        for line in p.read_text(encoding="utf-8").splitlines():
            ls = line.strip()
            if "auth-only" in ls and ("«" in ls or "؛" in ls) and not ls.startswith("#"):
                offenders.append((p.name, ls[:90]))
    assert not offenders, offenders
