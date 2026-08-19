from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import httpx
from sqlalchemy import Engine, select

from ..common.config import env, resolve_path
from ..common.urls import InvalidWordPressUrlError, normalize_wordpress_url, wp_rest_root, wp_rest_v2
from ..db.repositories.base import Repository, dumps, loads, utcnow
from ..db.tables import site_connections

log = logging.getLogger("connections")

STATUSES = ("ok", "not_configured", "not_authorized", "not_found", "error")


@dataclass
class ConnectionResult:
    kind: str                       # gsc | ga4 | wordpress
    status: str                     # see STATUSES
    message: str                    # human, Persian-friendly (frontend shows as-is)
    detail: dict[str, Any] = field(default_factory=dict)   # never secrets
    tested_at: str = field(default_factory=utcnow)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self); d["ok"] = self.ok
        return d


class ConnectionsRepository(Repository):
    def get_all(self, site_id: str) -> dict[str, ConnectionResult]:
        with self.engine.connect() as cx:
            rows = cx.execute(select(site_connections).where(site_connections.c.site_id == site_id)).all()
        out = {}
        for r in rows:
            m = r._mapping
            d = loads(m["detail"], {})
            out[m["kind"]] = ConnectionResult(kind=m["kind"], status=m["status"], message=d.pop("message", ""), detail=d, tested_at=m["tested_at"])
        return out

    def save(self, site_id: str, res: ConnectionResult) -> None:
        with self.engine.begin() as cx:
            self.upsert(cx, site_connections, {"site_id": site_id, "kind": res.kind, "status": res.status,
                                               "detail": dumps({**res.detail, "message": res.message}), "tested_at": res.tested_at},
                        conflict=["site_id", "kind"])


# --------------------------------------------------------------------------- google helpers
def _google_client_configured() -> bool:
    return bool(env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"))


def _token_info() -> dict[str, Any]:
    """Read the cached OAuth token (never returned to callers except scopes/expiry)."""
    p = resolve_path(env("GSC_TOKEN_PATH", "tokens/gsc_token.json"))
    if not p.exists():
        return {"present": False, "scopes": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {"present": False, "scopes": []}
    return {"present": bool(data.get("refresh_token")), "scopes": data.get("scopes") or [], "expiry": data.get("expiry")}


GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"


class ConnectionsService:
    """`gsc_client_factory` / `ga4_report_factory` are injectable for tests (no network in CI)."""

    def __init__(self, engine: Engine, gsc_client_factory: Callable[[str], Any] | None = None,
                 ga4_report_factory: Callable[[str], dict] | None = None, wp_fetch: Callable[[str], httpx.Response] | None = None):
        self.repo = ConnectionsRepository(engine)
        self._gsc_factory = gsc_client_factory
        self._ga4_report = ga4_report_factory
        self._wp_fetch = wp_fetch or (lambda url: httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": "SEO-Brain/0.2 (+local; read-only)"}))

    # -- status
    def status(self, site_id: str) -> dict[str, dict]:
        return {k: v.to_dict() for k, v in self.repo.get_all(site_id).items()}

    # -- Google Search Console
    def list_gsc_properties(self) -> dict[str, Any]:
        if not _google_client_configured():
            return {"status": "not_configured", "properties": [], "message": "GOOGLE_CLIENT_ID/SECRET در .env تنظیم نشده است"}
        tok = _token_info()
        if not tok["present"]:
            return {"status": "not_authorized", "properties": [], "message": "توکن Google وجود ندارد؛ یک‌بار `sync-gsc.py --auth-only` را اجرا کنید"}
        try:
            client = self._gsc_client("_")
            entries = client.list_sites()
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "properties": [], "message": f"خطا در فراخوانی Search Console: {e.__class__.__name__}: {e}"}
        return {"status": "ok", "properties": [{"property": e.get("siteUrl"), "permission": e.get("permissionLevel")} for e in entries]}

    def test_gsc(self, site_id: str, wanted: str | None) -> ConnectionResult:
        res = self._test_gsc(site_id, wanted)
        self.repo.save(site_id, res)
        return res

    def _test_gsc(self, site_id: str, wanted: str | None) -> ConnectionResult:
        if not wanted:
            return ConnectionResult("gsc", "not_configured", "برای این سایت هیچ property تعریف نشده است", {"hint": "sc-domain:example.com یا https://example.com/"})
        if not _google_client_configured():
            return ConnectionResult("gsc", "not_configured", "GOOGLE_CLIENT_ID/SECRET در .env تنظیم نشده است", {"property": wanted})
        tok = _token_info()
        if not tok["present"]:
            return ConnectionResult("gsc", "not_authorized", "توکن Google وجود ندارد؛ `sync-gsc.py --auth-only` را اجرا کنید", {"property": wanted})
        if GSC_SCOPE not in tok["scopes"]:
            return ConnectionResult("gsc", "not_authorized", "توکن فعلی اسکوپ Search Console را ندارد", {"property": wanted, "scopes": tok["scopes"]})
        try:
            client = self._gsc_client(site_id)
            site_url, permission = client.resolve_property(wanted)
        except Exception as e:  # noqa: BLE001
            return ConnectionResult("gsc", "error", f"خطا در فراخوانی Search Console: {e.__class__.__name__}: {e}", {"property": wanted})
        if not site_url:
            return ConnectionResult("gsc", "not_found", "این property در حساب Google متصل دیده نمی‌شود (URL-prefix و Domain هر دو بررسی شد)", {"property": wanted})
        if permission == "siteUnverifiedUser":
            return ConnectionResult("gsc", "not_authorized", "حساب متصل برای این property تأیید نشده است (siteUnverifiedUser)", {"property": site_url, "permission": permission})
        return ConnectionResult("gsc", "ok", "دسترسی Search Console تأیید شد", {"property": site_url, "permission": permission, "resolved_from": wanted})

    def _gsc_client(self, site_id: str):
        if self._gsc_factory:
            return self._gsc_factory(site_id)
        from ..gsc.client import GscClient  # lazy: google libs
        return GscClient(site_id, interactive=False, save_raw=False)

    # -- GA4
    def test_ga4(self, site_id: str, property_id: str | None) -> ConnectionResult:
        res = self._test_ga4(site_id, property_id)
        self.repo.save(site_id, res)
        return res

    def _test_ga4(self, site_id: str, property_id: str | None) -> ConnectionResult:
        if not property_id:
            return ConnectionResult("ga4", "not_configured", "شناسه property GA4 وارد نشده است (مثال: 123456789)", {})
        pid = str(property_id).replace("properties/", "").strip()
        if not pid.isdigit():
            return ConnectionResult("ga4", "not_configured", "شناسه GA4 باید عددی باشد (Admin → Property settings → Property ID)", {"property": property_id})
        if not _google_client_configured():
            return ConnectionResult("ga4", "not_configured", "GOOGLE_CLIENT_ID/SECRET در .env تنظیم نشده است", {"property": pid})
        tok = _token_info()
        if not tok["present"]:
            return ConnectionResult("ga4", "not_authorized", "توکن Google وجود ندارد", {"property": pid})
        if GA4_SCOPE not in tok["scopes"]:
            return ConnectionResult("ga4", "not_authorized",
                                    "توکن فعلی فقط اسکوپ Search Console دارد؛ برای GA4 باید یک‌بار با اسکوپ analytics.readonly مجوز بدهید (فاز بعدی: `sync-ga4.py --auth-only`)",
                                    {"property": pid, "scopes": tok["scopes"], "required_scope": GA4_SCOPE})
        try:
            report = self._ga4_report(pid) if self._ga4_report else self._run_ga4_probe(pid)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            status = "not_authorized" if "403" in msg or "PERMISSION_DENIED" in msg else ("not_found" if "404" in msg else "error")
            return ConnectionResult("ga4", status, f"خطا در فراخوانی GA4 Data API: {e.__class__.__name__}: {msg[:200]}", {"property": pid})
        return ConnectionResult("ga4", "ok", "دسترسی GA4 تأیید شد", {"property": pid, "rows": report.get("rowCount", 0)})

    def _run_ga4_probe(self, pid: str) -> dict:
        from googleapiclient.discovery import build  # lazy
        from ..gsc.client import get_credentials
        svc = build("analyticsdata", "v1beta", credentials=get_credentials(interactive=False), cache_discovery=False)
        body = {"dateRanges": [{"startDate": "7daysAgo", "endDate": "yesterday"}], "metrics": [{"name": "sessions"}], "limit": 1}
        return svc.properties().runReport(property=f"properties/{pid}", body=body).execute()

    # -- WordPress REST (public, GET only)
    def test_wordpress(self, site_id: str, wp_url: str | None) -> ConnectionResult:
        res = self._test_wordpress(wp_url)
        self.repo.save(site_id, res)
        return res

    def _test_wordpress(self, wp_url: str | None) -> ConnectionResult:
        if not wp_url:
            return ConnectionResult("wordpress", "not_configured", "آدرس وردپرس تنظیم نشده است", {})

        try:
            base = normalize_wordpress_url(wp_url)
        except InvalidWordPressUrlError as e:
            return ConnectionResult("wordpress", "error", str(e), {})

        root_url = wp_rest_root(base)
        try:
            r = self._wp_fetch(root_url)
        except httpx.UnsupportedProtocol:
            return ConnectionResult("wordpress", "error",
                                    "پروتکل آدرس نامعتبر است؛ آدرس وردپرس باید با http:// یا https:// شروع شود.",
                                    {"url": root_url})
        except httpx.ConnectTimeout:
            return ConnectionResult("wordpress", "error", "اتصال به سرور در زمان مقرر برقرار نشد (connect timeout).", {"url": root_url})
        except httpx.ReadTimeout:
            return ConnectionResult("wordpress", "error", "سرور در زمان مقرر پاسخ نداد (read timeout).", {"url": root_url})
        except httpx.TimeoutException:
            return ConnectionResult("wordpress", "error", "درخواست به دلیل timeout ناموفق بود.", {"url": root_url})
        except httpx.ConnectError as e:
            msg = str(e)
            if any(s in msg for s in ("getaddrinfo failed", "Name or service not known", "nodename nor servname", "Temporary failure in name resolution")):
                return ConnectionResult("wordpress", "error", "دامنه یافت نشد (خطای DNS)؛ آدرس وردپرس را بررسی کنید.", {"url": root_url})
            return ConnectionResult("wordpress", "error", f"اتصال به {root_url} برقرار نشد.", {"url": root_url})
        except httpx.RequestError as e:
            return ConnectionResult("wordpress", "error", f"اتصال به {root_url} برقرار نشد: {e.__class__.__name__}", {"url": root_url})

        if r.status_code == 401:
            return ConnectionResult("wordpress", "not_authorized", "REST API نیاز به احراز هویت دارد (401 Unauthorized).",
                                    {"url": root_url, "status_code": 401})
        if r.status_code == 403:
            return ConnectionResult("wordpress", "not_authorized",
                                    "دسترسی به REST API مسدود است (403 Forbidden) — احتمالاً توسط افزونه امنیتی یا فایروال.",
                                    {"url": root_url, "status_code": 403})
        if r.status_code == 404:
            return ConnectionResult("wordpress", "not_found",
                                    "مسیر REST API پیدا نشد (404) — بررسی کنید که آدرس درست است و REST API غیرفعال نشده باشد.",
                                    {"url": root_url, "status_code": 404})
        if r.status_code != 200:
            return ConnectionResult("wordpress", "not_found", f"REST API پاسخ {r.status_code} داد", {"url": root_url, "status_code": r.status_code})
        try:
            data = r.json()
        except ValueError:
            return ConnectionResult("wordpress", "error", "پاسخ /wp-json/ یک JSON معتبر نیست.", {"url": root_url})
        ns = data.get("namespaces", [])
        if "wp/v2" not in ns:
            return ConnectionResult("wordpress", "error",
                                    "پاسخ دریافت شد اما namespace استاندارد wp/v2 پیدا نشد — احتمالاً این یک سایت وردپرسی نیست.",
                                    {"url": root_url, "namespaces": ns[:20]})
        return ConnectionResult("wordpress", "ok", "REST API وردپرس در دسترس است (فقط خواندنی)",
                                {"url": root_url, "site_url": base, "rest_endpoint": wp_rest_v2(base),
                                 "name": data.get("name"), "namespaces": ns[:20], "wp_v2": True})
