"""Server-style OAuth renewal using real credential serialization and encrypted storage."""
import json
from urllib.parse import parse_qs

import pytest

from seo_brain.core.secrets import SecretStore
from seo_brain.gsc import client


@pytest.fixture
def saved_token(tmp_path, monkeypatch):
    directory = tmp_path / "secrets"
    store = SecretStore(directory)
    store.backend = "fernet"  # Exercise the Linux server backend on Windows too.
    monkeypatch.setattr("seo_brain.core.secrets.get_secret_store", lambda: store)
    monkeypatch.setenv("GSC_TOKEN_PATH", str(tmp_path / "legacy.json"))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    raw = json.dumps({
        "token": "expired-access", "refresh_token": "persistent-refresh-grant",
        "client_id": "test-client.apps.googleusercontent.com",
        "client_secret": "test-client-secret", "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": client.SCOPES, "expiry": "2000-01-01T00:00:00Z",
    })
    client.write_token_json(raw)
    return directory, raw


def test_expired_access_renews_and_survives_store_reopen(saved_token, monkeypatch):
    directory, _ = saved_token
    requests = []

    def request(**kwargs):
        requests.append(kwargs)
        assert kwargs["url"] == "https://oauth2.googleapis.com/token"
        body = parse_qs(kwargs["body"].decode())
        assert body["grant_type"] == ["refresh_token"]
        assert body["refresh_token"] == ["persistent-refresh-grant"]
        # Google normally returns no replacement refresh token on renewal.
        return type("Response", (), {
            "status": 200, "headers": {},
            "data": json.dumps({"access_token": "renewed-access", "expires_in": 3600,
                                "token_type": "Bearer"}).encode(),
        })()

    monkeypatch.setattr("google.auth.transport.requests.Request", lambda: request)
    creds = client.get_credentials(interactive=False)
    assert creds.valid and creds.token == "renewed-access"
    assert creds.refresh_token == "persistent-refresh-grant"
    assert len(requests) == 1

    reopened = SecretStore(directory)
    reopened.backend = "fernet"
    monkeypatch.setattr("seo_brain.core.secrets.get_secret_store", lambda: reopened)
    persisted = json.loads(reopened.get(client.TOKEN_REF))
    assert persisted["token"] == "renewed-access"
    assert persisted["refresh_token"] == "persistent-refresh-grant"
    assert persisted["expiry"] != "2000-01-01T00:00:00Z"
    assert b"persistent-refresh-grant" not in (directory / (client.TOKEN_REF + ".bin")).read_bytes()
    assert not (directory.parent / "legacy.json").exists()
    # A new credentials object uses durable storage without another HTTP request.
    again = client.get_credentials(interactive=False)
    assert again is not creds and again.valid and again.token == "renewed-access"
    assert len(requests) == 1


def test_invalid_grant_keeps_stored_credentials_for_diagnosis(saved_token, monkeypatch):
    _, original = saved_token
    calls = []

    def request(**kwargs):
        calls.append(kwargs)
        return type("Response", (), {
            "status": 400, "headers": {},
            "data": b'{"error":"invalid_grant","error_description":"Token revoked"}',
        })()

    monkeypatch.setattr("google.auth.transport.requests.Request", lambda: request)
    monkeypatch.setattr(client.time, "sleep", lambda _: pytest.fail("invalid_grant must not retry"))
    monkeypatch.setattr("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config",
                        lambda *a, **k: pytest.fail("Refresh failure must not open consent"))
    with pytest.raises(client.GscAuthError):
        client.get_credentials(interactive=True)
    assert client.read_token_json() == original
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["transport", "retryable_refresh"])
@pytest.mark.parametrize("recovers", [True, False])
def test_transient_refresh_retries_without_reconsent(saved_token, monkeypatch, failure, recovers):
    from datetime import datetime, timedelta, timezone
    from google.auth.exceptions import RefreshError, TransportError
    from google.oauth2.credentials import Credentials

    _, original = saved_token
    calls, delays = [], []

    def refresh(creds, request):
        calls.append(request)
        if recovers and len(calls) == 3:
            creds.token = "recovered-access"
            creds.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
            return
        if failure == "transport":
            raise TransportError("Network temporarily unavailable")
        raise RefreshError("Server temporarily unavailable", retryable=True)

    monkeypatch.setattr(Credentials, "refresh", refresh)
    monkeypatch.setattr(client.time, "sleep", delays.append)
    monkeypatch.setattr("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config",
                        lambda *a, **k: pytest.fail("Temporary outage must not open consent"))
    if recovers:
        creds = client.get_credentials(interactive=True)
        assert creds.valid and creds.token == "recovered-access"
        stored = json.loads(client.read_token_json())
        assert stored["token"] == "recovered-access"
        assert stored["refresh_token"] == "persistent-refresh-grant"
    else:
        with pytest.raises(RuntimeError, match="temporarily unavailable"):
            client.get_credentials(interactive=True)
        assert client.read_token_json() == original
    assert len(calls) == 3
    assert delays == [1, 2]
