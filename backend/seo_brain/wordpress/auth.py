"""WordPress Application-Password credentials per site — stored ONLY in the SecretStore (DPAPI/Fernet encrypted, ref
`wp-auth-{site_id}`), never in the DB, logs, traces or API responses (only `username` + a 4-char hint are ever returned).

Resolution order used by the connector and the diagnostics: explicit credentials → per-site SecretStore → `.env`
(`WP_USERNAME` / `WP_APP_PASSWORD`, legacy single-site setup) → none (public, read-only REST only).
The same credentials are also required by the explicit, human-triggered publishing flow.  Merely connecting a site
never writes anything; a write happens only after a separate publish/schedule action in Content Brain.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ..common.config import env
from ..core.secrets import SecretStore, get_secret_store


@dataclass(frozen=True)
class WpAuth:
    username: str
    app_password: str
    source: str                 # explicit | site | env

    @property
    def basic(self) -> tuple[str, str]:
        return (self.username, self.app_password)

    def public(self) -> dict:
        return {"configured": True, "username": self.username, "key_hint": SecretStore.hint(self.app_password), "source": self.source}


def _ref(site_id: str) -> str:
    return f"wp-auth-{site_id}"


def save_site_auth(site_id: str, username: str, app_password: str, store: SecretStore | None = None) -> dict:
    username = (username or "").strip(); app_password = (app_password or "").strip()
    if not username or not app_password:
        raise ValueError("نام‌کاربری و Application Password هر دو لازم‌اند.")
    (store or get_secret_store()).set(_ref(site_id), json.dumps({"username": username, "app_password": app_password}))
    return WpAuth(username, app_password, "site").public()


def clear_site_auth(site_id: str, store: SecretStore | None = None) -> bool:
    return (store or get_secret_store()).delete(_ref(site_id))


def load_site_auth(site_id: str, store: SecretStore | None = None) -> WpAuth | None:
    raw = (store or get_secret_store()).get(_ref(site_id))
    if not raw:
        return None
    try:
        d = json.loads(raw)
        return WpAuth(d["username"], d["app_password"], "site") if d.get("username") and d.get("app_password") else None
    except (ValueError, KeyError, TypeError):
        return None


def env_auth() -> WpAuth | None:
    u, p = env("WP_USERNAME"), env("WP_APP_PASSWORD")
    return WpAuth(u, p, "env") if u and p else None


def resolve_auth(site_id: str | None, username: str | None = None, app_password: str | None = None, store: SecretStore | None = None) -> WpAuth | None:
    if username and app_password:
        return WpAuth(username.strip(), app_password.strip(), "explicit")
    if site_id:
        a = load_site_auth(site_id, store)
        if a:
            return a
    return env_auth()


def auth_status(site_id: str, store: SecretStore | None = None) -> dict:
    """What the UI may know: configured? username? hint? source? — never the password."""
    a = resolve_auth(site_id, store=store)
    return a.public() if a else {"configured": False, "username": None, "key_hint": None, "source": None}
