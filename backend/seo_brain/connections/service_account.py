"""Google Search Console via SERVICE ACCOUNT — the simple alternative to the OAuth user flow (GSC only).

The user adds one e-mail to their Search Console property (Settings → Users and permissions) and SEO Brain can
read search analytics — no OAuth verification, no consent screen, no 7-day testing expiry.

Storage: the standard service-account JSON lives ENCRYPTED in the existing SecretStore (ref `google-service-account`).
It is never echoed by any endpoint — only the client e-mail (which the user must copy anyway) and the property list.
The last successful access check is cached in tokens/sa_gsc_check.json (non-secret, git-ignored).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

from ..common.config import env, resolve_path

log = logging.getLogger("google.service_account")

SA_REF = "google-service-account"
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"


def _store():
    from ..core.secrets import get_secret_store
    return get_secret_store()


def sa_info() -> dict[str, Any] | None:
    """Parsed service-account document, or None. Internal only — callers must never expose the private key."""
    try:
        raw = _store().get(SA_REF)
    except Exception:  # noqa: BLE001
        return None
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    return d if d.get("type") == "service_account" and d.get("client_email") else None


def sa_configured() -> bool:
    return sa_info() is not None


def sa_email() -> str | None:
    d = sa_info()
    return d.get("client_email") if d else None


def sa_credentials(scopes: list[str] | None = None):
    """google-auth credentials from the stored document (GSC read-only scope by default)."""
    d = sa_info()
    if not d:
        return None
    from google.oauth2 import service_account
    return service_account.Credentials.from_service_account_info(d, scopes=scopes or [GSC_SCOPE])


# ------------------------------------------------------------------ access check (sites().list()) + small cache
def _cache_path() -> Path:
    return resolve_path(env("GSC_TOKEN_PATH", "tokens/gsc_token.json")).parent / "sa_gsc_check.json"


def _read_cache() -> dict[str, Any]:
    p = _cache_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def check_access(list_sites: Callable[[], list[dict]] | None = None) -> dict[str, Any]:
    """Run sites().list() with the service account and cache the outcome. `list_sites` injectable for tests."""
    if not sa_configured():
        return {"status": "not_configured", "service_account_email": None, "properties": [],
                "message": "هیچ Service Accountای ثبت نشده است"}
    email = sa_email()
    try:
        if list_sites is None:
            from googleapiclient.discovery import build
            svc = build("searchconsole", "v1", credentials=sa_credentials(), cache_discovery=False)
            entries = (svc.sites().list().execute() or {}).get("siteEntry", [])
        else:
            entries = list_sites()
    except Exception as e:  # noqa: BLE001 — never leak internals; the class name is enough
        log.warning(f"service-account GSC check failed: {e.__class__.__name__}")
        return {"status": "error", "service_account_email": email, "properties": [],
                "message": f"بررسی دسترسی ناموفق بود ({e.__class__.__name__}) — بعداً دوباره تلاش کنید"}
    props = [{"property": e.get("siteUrl"), "permission": e.get("permissionLevel")} for e in entries if e.get("siteUrl")]
    out = {"status": "ok", "service_account_email": email, "properties": props,
           "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        _cache_path().parent.mkdir(parents=True, exist_ok=True)
        _cache_path().write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return out


def status() -> dict[str, Any]:
    """Configured/e-mail/cached properties — no key material, no live Google call."""
    cache = _read_cache()
    return {"configured": sa_configured(), "service_account_email": sa_email(),
            "accessible_properties": cache.get("properties", []), "last_check": cache.get("checked_at")}
