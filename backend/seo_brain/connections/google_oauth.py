"""Browser-based Google OAuth (web-application flow) — the SaaS onboarding layer on top of the EXISTING auth core.

Reuses everything from gsc/client.py: the OAuth client (_client_config → .env / SecretStore), the scopes, and the
token file format (`Credentials.to_json()` at GSC_TOKEN_PATH) — so the GSC/GA4 clients, the pipelines and the CLI
keep working unchanged. Only the way consent is obtained changes: an /authorize URL + a /callback exchange instead
of run_local_server(). `openid email` is added to the web consent so the UI can show which account is connected;
the two data scopes stay exactly as before.

No plaintext DB storage: the refresh token stays in the git-ignored tokens/ file (same as always); the connected
account label (email — not a secret) sits next to it in tokens/google_account.json.
"""
from __future__ import annotations

import base64
import json
import logging
import secrets as _secrets
import time
from pathlib import Path
from typing import Any

from ..common.config import env, resolve_path
from ..gsc.client import SCOPES, GscAuthError, _client_config, delete_token, read_token_json, write_token_json

log = logging.getLogger("google.oauth")

WEB_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email", *SCOPES]
_STATE_TTL = 600
_states: dict[str, float] = {}


def _states_path() -> Path:
    return token_path().parent / "oauth_states.json"


def _load_states() -> None:
    """States survive an API restart between /authorize and /callback (small file next to the token)."""
    try:
        if _states_path().exists():
            now = time.time()
            _states.update({k: v for k, v in json.loads(_states_path().read_text(encoding="utf-8")).items() if v > now})
    except ValueError:
        pass


def _save_states() -> None:
    try:
        _states_path().parent.mkdir(parents=True, exist_ok=True)
        _states_path().write_text(json.dumps(_states), encoding="utf-8")
    except OSError:  # state persistence is best-effort; in-memory still works
        pass


def token_path() -> Path:
    return resolve_path(env("GSC_TOKEN_PATH", "tokens/gsc_token.json"))


def account_path() -> Path:
    return token_path().parent / "google_account.json"


def default_redirect_uri() -> str:
    # Desktop-type Google clients accept any loopback redirect without prior registration.
    return env("GOOGLE_OAUTH_REDIRECT", "http://127.0.0.1:8000/api/v1/connections/google/callback")


def _flow(redirect_uri: str):
    from google_auth_oauthlib.flow import Flow
    return Flow.from_client_config(_client_config(), scopes=WEB_SCOPES, redirect_uri=redirect_uri)


def begin(redirect_uri: str | None = None) -> dict[str, Any]:
    """Build the Google consent URL. Raises GscAuthError when the OAuth client is not configured."""
    ru = redirect_uri or default_redirect_uri()
    flow = _flow(ru)
    state = _secrets.token_urlsafe(24)
    now = time.time()
    _load_states()
    for k in [k for k, exp in _states.items() if exp < now]:
        _states.pop(k, None)
    _states[state] = now + _STATE_TTL
    _save_states()
    url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true", state=state)
    return {"url": url, "state": state, "redirect_uri": ru}


def finish(code: str, state: str | None, redirect_uri: str | None = None) -> dict[str, Any]:
    """Exchange the callback code, store the token in the EXISTING file format, remember the account email."""
    _load_states()
    if not state or _states.pop(state, 0) < time.time():
        raise GscAuthError("state نامعتبر یا منقضی است — دوباره «اتصال حساب گوگل» را بزنید")
    _save_states()
    flow = _flow(redirect_uri or default_redirect_uri())
    old_refresh = None
    try:                                                       # reconnect: remember the previous grant to revoke it
        old = json.loads(read_token_json() or "null")
        old_refresh = (old or {}).get("refresh_token")
    except ValueError:
        pass
    flow.fetch_token(code=code)
    creds = flow.credentials
    if old_refresh and old_refresh != creds.refresh_token:
        _revoke(old_refresh)                                   # best-effort: no orphaned grants left on the Google account
    write_token_json(creds.to_json())                          # same format get_credentials() reads (SecretStore, encrypted)
    tp = token_path()
    tp.parent.mkdir(parents=True, exist_ok=True)
    email = _email_from_id_token(getattr(creds, "id_token", None))
    account_path().write_text(json.dumps({"email": email, "scopes": list(creds.scopes or []),
                                          "connected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, ensure_ascii=False), encoding="utf-8")
    log.info("Google account connected via web flow (token stored, git-ignored)")
    return {"connected": True, "email": email, "scopes": list(creds.scopes or [])}


def _email_from_id_token(id_token: str | None) -> str | None:
    """The id_token comes straight from Google over TLS during our own code exchange — decode payload only."""
    if not id_token or id_token.count(".") != 2:
        return None
    try:
        payload = id_token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return data.get("email")
    except Exception:  # noqa: BLE001
        return None


def status() -> dict[str, Any]:
    from .service import GA4_SCOPE, _google_client_configured, _token_info
    tok = _token_info()
    acct: dict[str, Any] = {}
    if account_path().exists():
        try:
            acct = json.loads(account_path().read_text(encoding="utf-8"))
        except ValueError:
            acct = {}
    return {"connected": bool(tok.get("present")), "email": acct.get("email"),
            "scopes": tok.get("scopes") or [], "expiry": tok.get("expiry"),
            "gsc_scope": any(s.endswith("webmasters.readonly") for s in (tok.get("scopes") or [])),
            "ga4_scope": GA4_SCOPE in (tok.get("scopes") or []),
            "client_configured": _google_client_configured() or _has_store_client(),
            "client_id_hint": client_hint(),
            "connected_at": acct.get("connected_at")}


def client_hint() -> str | None:
    """Masked Client ID for the UI (never the secret)."""
    cid = env("GOOGLE_CLIENT_ID")
    if not cid:
        try:
            from ..core.secrets import get_secret_store
            cid = get_secret_store().get("google-client-id")
        except Exception:  # noqa: BLE001
            cid = None
    return (cid[:8] + "…" + cid[-28:]) if cid and len(cid) > 40 else (cid[:8] + "…" if cid else None)


def save_client(client_id: str, client_secret: str) -> dict[str, Any]:
    """Store the Google OAuth client in the EXISTING SecretStore (refs the auth core already reads). Never returned."""
    from ..core.secrets import get_secret_store
    cid, csec = client_id.strip(), client_secret.strip()
    if not cid.endswith(".apps.googleusercontent.com"):
        raise GscAuthError("Client ID باید به apps.googleusercontent.com ختم شود (OAuth Client از نوع Desktop بسازید)")
    if len(csec) < 10:
        raise GscAuthError("Client Secret معتبر نیست")
    st = get_secret_store()
    st.set("google-client-id", cid)
    st.set("google-client-secret", csec)
    log.info("Google OAuth client stored in SecretStore (encrypted)")
    return {"configured": True, "client_id_hint": client_hint()}


def _has_store_client() -> bool:
    try:
        from ..core.secrets import get_secret_store
        st = get_secret_store()
        return bool(st.get("google-client-id") and st.get("google-client-secret"))
    except Exception:  # noqa: BLE001
        return False


def _revoke(refresh_token: str | None) -> bool:
    if not refresh_token:
        return False
    try:
        import httpx
        r = httpx.post("https://oauth2.googleapis.com/revoke", params={"token": refresh_token}, timeout=10)
        return r.status_code == 200
    except Exception:  # noqa: BLE001 — revoke is best-effort
        return False


def disconnect() -> dict[str, Any]:
    """Best-effort revoke at Google, then remove the stored token (SecretStore + legacy file) and account info."""
    revoked = False
    try:
        tok = json.loads(read_token_json() or "null")
        revoked = _revoke((tok or {}).get("refresh_token"))
    except ValueError:
        pass
    removed = delete_token()
    ap = account_path()
    if ap.exists():
        ap.unlink()
        removed = True
    return {"disconnected": removed, "revoked": revoked}
