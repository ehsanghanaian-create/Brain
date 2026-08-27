"""GSC Service Account connector (simple alternative to OAuth, GSC only): credential loading from the encrypted
SecretStore, SA-first provider for GscClient, status/check endpoints with a mocked sites().list, token-info union
(SA authorizes GSC without any OAuth token, GA4 gating untouched), and zero secret leakage in responses."""
import json

import pytest
from fastapi.testclient import TestClient

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.connections import service_account as sa_mod
from seo_brain.core.secrets import SecretStore
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate


def _fake_sa_json() -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return json.dumps({"type": "service_account", "project_id": "t", "private_key_id": "k", "private_key": pem,
                       "client_email": "seo-brain-gsc-reader@test-project.iam.gserviceaccount.com",
                       "client_id": "1", "token_uri": "https://oauth2.googleapis.com/token"})


@pytest.fixture
def env(tmp_path, monkeypatch):
    eng = make_engine("sqlite:///" + (tmp_path / "sa.db").as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setenv("GSC_TOKEN_PATH", str(tmp_path / "tokens" / "gsc_token.json"))
    store = SecretStore(tmp_path / "secrets")
    monkeypatch.setattr("seo_brain.core.secrets.get_secret_store", lambda: store)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng
    return {"client": TestClient(app), "store": store, "tmp": tmp_path}


def test_credential_loading_and_provider_priority(env, monkeypatch):
    from seo_brain.gsc.client import get_gsc_credentials
    # nothing configured → provider falls through to OAuth (which raises its precise error non-interactively)
    from seo_brain.gsc.client import GscAuthError
    with pytest.raises(GscAuthError):
        get_gsc_credentials(interactive=False)
    # store the SA (encrypted) → provider returns service-account credentials with the read-only GSC scope
    env["store"].set(sa_mod.SA_REF, _fake_sa_json())
    creds = get_gsc_credentials(interactive=False)
    assert creds.service_account_email == "seo-brain-gsc-reader@test-project.iam.gserviceaccount.com"
    assert list(creds.scopes) == [sa_mod.GSC_SCOPE]
    # token-info union: GSC authorized purely via SA; GA4 scope NOT granted (OAuth-only)
    from seo_brain.connections.service import GA4_SCOPE, _token_info
    tok = _token_info()
    assert tok["present"] is True and sa_mod.GSC_SCOPE in tok["scopes"] and GA4_SCOPE not in tok["scopes"]
    assert tok["source"] == "service_account" and tok["sa_email"].startswith("seo-brain-gsc-reader@")


def test_service_account_is_not_reported_as_oauth_connection(env):
    env["store"].set(sa_mod.SA_REF, _fake_sa_json())
    status = env["client"].get("/api/v1/connections/google/status").json()
    assert status["connected"] is False
    assert status["gsc_scope"] is False
    assert status["ga4_scope"] is False


def test_oauth_client_is_detected_in_encrypted_store(env):
    env["store"].set("google-client-id", "123456789.apps.googleusercontent.com")
    env["store"].set("google-client-secret", "configured-secret")
    from seo_brain.connections.service import _google_client_configured
    assert _google_client_configured() is True


def test_status_and_check_endpoints_no_secret_leakage(env, monkeypatch):
    c = env["client"]
    # not configured
    d = c.get("/api/v1/connections/gsc/service-account/status").json()
    assert d["configured"] is False and d["service_account_email"] is None and d["accessible_properties"] == []
    assert c.post("/api/v1/connections/gsc/service-account/check").json()["status"] == "not_configured"
    # configured → check with a mocked sites().list
    env["store"].set(sa_mod.SA_REF, _fake_sa_json())
    out = sa_mod.check_access(list_sites=lambda: [
        {"siteUrl": "sc-domain:renaultemdad.com", "permissionLevel": "siteFullUser"},
        {"siteUrl": "https://modirankhodro-emdad.com/", "permissionLevel": "siteRestrictedUser"}])
    assert out["status"] == "ok" and len(out["properties"]) == 2
    assert out["service_account_email"].endswith("iam.gserviceaccount.com")
    # status now serves the cached result (no live call) and the API responses never contain key material
    d = c.get("/api/v1/connections/gsc/service-account/status")
    body = d.text
    assert d.json()["configured"] is True and len(d.json()["accessible_properties"]) == 2
    assert d.json()["last_check"] and d.json()["service_account_email"].startswith("seo-brain-gsc-reader@")
    assert "PRIVATE KEY" not in body and "private_key" not in body and "token_uri" not in body


def test_check_endpoint_error_is_friendly(env, monkeypatch):
    c = env["client"]
    env["store"].set(sa_mod.SA_REF, _fake_sa_json())

    def boom(*a, **k):
        raise RuntimeError("boom-with-secret-internals")
    monkeypatch.setattr("googleapiclient.discovery.build", boom)      # the Google call fails inside check_access
    d = c.post("/api/v1/connections/gsc/service-account/check").json()
    assert d["status"] == "error" and "RuntimeError" in d["message"]
    assert "boom-with-secret-internals" not in json.dumps(d)          # only the class name, never internals


def test_gsc_client_uses_service_account_when_configured(env, monkeypatch):
    env["store"].set(sa_mod.SA_REF, _fake_sa_json())
    from seo_brain.gsc.client import GscClient
    built = {}
    def fake_build(api, ver, http=None, cache_discovery=False):
        built["api"], built["transport"] = api, http
        return object()
    monkeypatch.setattr("googleapiclient.discovery.build", fake_build)
    c = GscClient("demo", interactive=False, save_raw=False)
    assert built["api"] == "searchconsole"
    assert built["transport"].credentials.service_account_email.startswith("seo-brain-gsc-reader@")   # SA-first, proxy-aware pipeline
