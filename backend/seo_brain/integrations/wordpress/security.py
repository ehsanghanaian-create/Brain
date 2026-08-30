"""WordPressSecurityService — the `security.*` capability on the EXISTING WordPress connection.

Brain never blocks anything on its own: every call here is a human-triggered relay to the
site's own `ip-htaccess-blocker` plugin (REST base /wp-json/seo-brain/v1/), authenticated with
the site's stored Application Password (SecretStore) exactly like the writer/tester. All
operations are site-scoped and audited in `security_audit`.
"""
from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from sqlalchemy import Engine, text

from ...wordpress.auth import resolve_auth

PLUGIN_BASE = "/wp-json/seo-brain/v1"


def normalize_single_ip(raw: str) -> str | None:
    """Single IPv4/IPv6 only — hostname/URL/wildcard/CIDR are rejected (spec)."""
    value = (raw or "").strip()
    if not value or "/" in value or "*" in value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


class WordPressSecurityService:
    def __init__(self, engine: Engine, http: Callable[..., httpx.Response] | None = None):
        self.engine = engine
        self._http = http

    # ------------------------------------------------------------------ plumbing (same pattern as WordPressWriter)
    def _request(self, method: str, url: str, auth: tuple[str, str], **kw) -> httpx.Response:
        if self._http:
            return self._http(method, url, auth=auth, **kw)
        from ...common.http import site_proxy
        return httpx.request(method, url, auth=auth, timeout=25, follow_redirects=True, proxy=site_proxy(),
                             headers={"User-Agent": "SEO-Brain-Security/1.0"}, **kw)

    def _site(self, site_id: str):
        with self.engine.connect() as cx:
            return cx.execute(text("SELECT wp_url, canonical_url FROM sites WHERE site_id=:s"), {"s": site_id}).first()

    def _base(self, site_id: str) -> tuple[str | None, tuple[str, str] | None, dict | None]:
        """(plugin_base_url, auth, error_payload)"""
        site = self._site(site_id)
        if not site:
            return None, None, {"connected": False, "code": "site_not_found", "message": "سایت پیدا نشد"}
        if not site[0]:
            return None, None, {"connected": False, "code": "wp_url_missing", "message": "آدرس وردپرس برای این سایت تنظیم نشده است"}
        auth = resolve_auth(site_id)
        if not auth:
            return None, None, {"connected": False, "code": "credentials_missing",
                                "message": "اتصال وردپرس این سایت کامل نیست — در کارت وردپرس، نام‌کاربری و رمز برنامه را وارد کنید"}
        return site[0].rstrip("/") + PLUGIN_BASE, (auth.username, auth.app_password), None

    @staticmethod
    def _map_error(exc_or_response) -> dict:
        """Map transport/HTTP failures to safe Persian messages (raw backend errors never reach the UI)."""
        if isinstance(exc_or_response, httpx.Response):
            r = exc_or_response
            code = r.status_code
            is_json = "json" in (r.headers.get("content-type") or "").lower()
            detail = None
            if is_json:
                try:
                    detail = (r.json() or {}).get("code")
                except Exception:  # noqa: BLE001
                    detail = None
            if code in (401, 403):
                return {"code": "auth_failed", "message": "دسترسی رد شد — رمز برنامهٔ وردپرس یا سطح دسترسی کاربر را بررسی کنید"}
            if code == 404 and detail == "rest_no_route" or code == 404 and is_json:
                return {"code": "plugin_missing", "message": "پلاگین امنیتی روی این سایت نصب یا فعال نیست"}
            if code == 404:
                return {"code": "plugin_missing", "message": "پلاگین امنیتی روی این سایت نصب یا فعال نیست"}
            if code == 400 and detail == "invalid_ip":
                return {"code": "invalid_ip", "message": "آدرس IP معتبر نیست"}
            if code == 429:
                return {"code": "rate_limited", "message": "درخواست‌ها زیاد است — کمی بعد دوباره تلاش کنید"}
            if code in (502, 503):
                return {"code": "site_unavailable", "message": "سایت موقتاً در دسترس نیست"}
            return {"code": f"http_{code}", "message": "پاسخ نامعتبر از سایت — بعداً دوباره تلاش کنید"}
        e = exc_or_response
        if isinstance(e, httpx.TimeoutException):
            return {"code": "timeout", "message": "سایت پاسخ نداد (تایم‌اوت)"}
        return {"code": "network_error", "message": "اتصال به سایت برقرار نشد"}

    def _audit(self, site_id: str, ip: str, action: str, ok: bool, status: str | None, message: str | None,
               reason: str | None, actor: str) -> None:
        with self.engine.begin() as cx:
            cx.execute(text(
                "INSERT INTO security_audit(site_id, ip, action, reason, ok, status, message, actor, created_at) "
                "VALUES(:s, :ip, :a, :r, :ok, :st, :m, :actor, :t)"),
                {"s": site_id, "ip": ip, "a": action, "r": reason, "ok": 1 if ok else 0,
                 "st": status, "m": message, "actor": actor,
                 "t": datetime.now(timezone.utc).isoformat(timespec="seconds")})

    # ------------------------------------------------------------------ capability: security.get_status
    def get_status(self, site_id: str) -> dict[str, Any]:
        base, auth, err = self._base(site_id)
        if err:
            return err
        try:
            r = self._request("GET", f"{base}/status", auth)
        except Exception as e:  # noqa: BLE001
            return {"connected": False, **self._map_error(e)}
        if r.status_code != 200:
            return {"connected": False, **self._map_error(r)}
        d = r.json()
        return {"connected": True, "plugin_version": d.get("plugin_version"), "site": d.get("site"),
                "writable": bool(d.get("writable", True)), "count": int(d.get("count") or 0)}

    # ------------------------------------------------------------------ capability: security.list_blocked_ips
    def list_blocked(self, site_id: str) -> dict[str, Any]:
        base, auth, err = self._base(site_id)
        if err:
            return {**err, "items": []}
        try:
            r = self._request("GET", f"{base}/security/blocked", auth)
        except Exception as e:  # noqa: BLE001
            return {"connected": False, **self._map_error(e), "items": []}
        if r.status_code != 200:
            return {"connected": False, **self._map_error(r), "items": []}
        return {"connected": True, "items": (r.json() or {}).get("items", [])}

    # ------------------------------------------------------------------ capability: security.block_ip / unblock_ip
    def _mutate(self, site_id: str, action: str, ip_raw: str, reason: str | None, actor: str) -> dict[str, Any]:
        ip = normalize_single_ip(ip_raw)
        if not ip:
            return {"success": False, "code": "invalid_ip", "message": "فقط یک IP تکی معتبر (IPv4/IPv6) مجاز است"}
        base, auth, err = self._base(site_id)
        if err:
            self._audit(site_id, ip, action, False, "error", err.get("message"), reason, actor)
            return {"success": False, **err}
        path = "/security/block-ip" if action == "block" else "/security/unblock-ip"
        body: dict[str, Any] = {"ip": ip}
        if action == "block":
            body["reason"] = reason or ""
            body["duration"] = "permanent"
        try:
            r = self._request("POST", f"{base}{path}", auth, json=body)
        except Exception as e:  # noqa: BLE001
            m = self._map_error(e)
            self._audit(site_id, ip, action, False, "error", m["message"], reason, actor)
            return {"success": False, **m}
        if r.status_code != 200:
            m = self._map_error(r)
            self._audit(site_id, ip, action, False, "error", m["message"], reason, actor)
            return {"success": False, **m}
        d = r.json() or {}
        status = d.get("status") or ("blocked" if action == "block" else "unblocked")
        self._audit(site_id, ip, action, True, status, None, reason, actor)
        return {"success": True, "ip": ip, "status": status}

    def block_ip(self, site_id: str, ip: str, reason: str | None = None, actor: str = "human") -> dict[str, Any]:
        return self._mutate(site_id, "block", ip, reason, actor)

    def unblock_ip(self, site_id: str, ip: str, actor: str = "human") -> dict[str, Any]:
        return self._mutate(site_id, "unblock", ip, None, actor)

    # ------------------------------------------------------------------ audit
    def audit(self, site_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.engine.connect() as cx:
            rows = cx.execute(text(
                "SELECT ip, action, reason, ok, status, message, actor, created_at FROM security_audit "
                "WHERE site_id=:s ORDER BY id DESC LIMIT :l"), {"s": site_id, "l": limit}).mappings().all()
        return [dict(r) for r in rows]


def resolve_site_by_domain(engine: Engine, domain: str) -> str | None:
    """Map an ads-data domain (renaultemdad.com) to the platform site_id (renaultemdad)."""
    host = (domain or "").strip().lower().removeprefix("www.")
    if not host:
        return None
    with engine.connect() as cx:
        for sid, canonical, wp in cx.execute(text("SELECT site_id, canonical_url, wp_url FROM sites")):
            for u in (canonical, wp):
                if u and host == (httpx.URL(u).host or "").lower().removeprefix("www."):
                    return sid
    return None
