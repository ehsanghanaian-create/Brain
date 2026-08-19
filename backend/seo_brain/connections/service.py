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


def _redact(v: str | None, keep: int = 3) -> str:
    """Show only the shape of a user-supplied value in traces (never the value itself)."""
    if not v:
        return "∅"
    v = str(v)
    return v if ("://" in v or "." in v) and " " not in v and len(v) <= 120 else f"«{v[:keep]}…{v[-2:]} ({len(v)} chars)»"


def _step(trace: list[str], msg: str) -> None:
    trace.append(f"[{utcnow()[11:23]}] {msg}")


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
        trace: list[str] = []
        res = self._test_gsc(site_id, wanted, trace)
        res.detail = {**res.detail, "trace": trace}
        self.repo.save(site_id, res)
        return res

    def _test_gsc(self, site_id: str, wanted: str | None, trace: list[str] | None = None) -> ConnectionResult:
        trace = trace if trace is not None else []
        _step(trace, f"input property = {_redact(wanted)}")
        if not wanted:
            return ConnectionResult("gsc", "not_configured", "برای این سایت هیچ property تعریف نشده است", {"hint": "sc-domain:example.com یا https://example.com/"})
        _step(trace, f"GOOGLE_CLIENT_ID/SECRET in .env: {'yes' if _google_client_configured() else 'NO'}")
        if not _google_client_configured():
            return ConnectionResult("gsc", "not_configured", "GOOGLE_CLIENT_ID/SECRET در .env تنظیم نشده است", {"property": wanted})
        tok = _token_info()
        _step(trace, f"OAuth token file {resolve_path(env('GSC_TOKEN_PATH', 'tokens/gsc_token.json')).name}: present={tok['present']} scopes={len(tok['scopes'])} expiry={tok.get('expiry') or '?'}")
        if not tok["present"]:
            return ConnectionResult("gsc", "not_authorized", "توکن Google وجود ندارد؛ `sync-gsc.py --auth-only` را اجرا کنید", {"property": wanted})
        if GSC_SCOPE not in tok["scopes"]:
            _step(trace, f"missing scope {GSC_SCOPE}")
            return ConnectionResult("gsc", "not_authorized", "توکن فعلی اسکوپ Search Console را ندارد", {"property": wanted, "scopes": tok["scopes"]})
        _step(trace, "scope webmasters.readonly: ok → calling Search Console sites.list / resolve_property")
        try:
            client = self._gsc_client(site_id)
            site_url, permission = client.resolve_property(wanted)
        except Exception as e:  # noqa: BLE001
            _step(trace, f"API error: {e.__class__.__name__}: {str(e)[:200]}")
            return ConnectionResult("gsc", "error", f"خطا در فراخوانی Search Console: {e.__class__.__name__}: {e}", {"property": wanted})
        _step(trace, f"resolved: site_url={site_url or '∅'} permission={permission or '∅'}")
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
        tok = _token_info()
        res.detail = {**res.detail, "trace": [f"input property id = {_redact(property_id)}", f"google client configured = {_google_client_configured()}",
                                              f"token present = {tok['present']}, scopes = {len(tok['scopes'])}, analytics.readonly = {GA4_SCOPE in tok['scopes']}", f"status = {res.status}: {res.message}"]}
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
        trace: list[str] = []
        res = self._test_wordpress(wp_url, trace)
        res.detail = {**res.detail, "trace": trace}
        self.repo.save(site_id, res)
        return res

    def _test_wordpress(self, wp_url: str | None, trace: list[str] | None = None) -> ConnectionResult:
        trace = trace if trace is not None else []
        _step(trace, f"input = {_redact(wp_url)}")
        if not wp_url:
            return ConnectionResult("wordpress", "not_configured", "آدرس وردپرس تنظیم نشده است", {})

        try:
            base = normalize_wordpress_url(wp_url)
        except InvalidWordPressUrlError as e:
            _step(trace, f"normalize → rejected: {str(e)[:120]}")
            return ConnectionResult("wordpress", "error", str(e), {})
        _step(trace, f"normalize → {base}")

        root_url = wp_rest_root(base)
        _step(trace, f"GET {root_url} (timeout 20s, follow_redirects, UA SEO-Brain read-only)")
        import time as _t
        t0 = _t.perf_counter()
        try:
            r = self._wp_fetch(root_url)
            _step(trace, f"response HTTP {r.status_code} in {int((_t.perf_counter() - t0) * 1000)}ms · content-type={r.headers.get('content-type', '?')} · {len(r.content)} bytes" + (f" · final url {r.url}" if str(getattr(r, 'url', '')) not in ('', root_url) else ""))
        except httpx.UnsupportedProtocol:
            _step(trace, "httpx.UnsupportedProtocol")
            return ConnectionResult("wordpress", "error",
                                    "پروتکل آدرس نامعتبر است؛ آدرس وردپرس باید با http:// یا https:// شروع شود.",
                                    {"url": root_url})
        except httpx.ConnectTimeout:
            _step(trace, "httpx.ConnectTimeout (TCP connect > timeout)")
            return ConnectionResult("wordpress", "error", "اتصال به سرور در زمان مقرر برقرار نشد (connect timeout).", {"url": root_url})
        except httpx.ReadTimeout:
            _step(trace, "httpx.ReadTimeout (connected, no response body in time)")
            return ConnectionResult("wordpress", "error", "سرور در زمان مقرر پاسخ نداد (read timeout).", {"url": root_url})
        except httpx.TimeoutException:
            return ConnectionResult("wordpress", "error", "درخواست به دلیل timeout ناموفق بود.", {"url": root_url})
        except httpx.ConnectError as e:
            msg = str(e)
            _step(trace, f"httpx.ConnectError: {msg[:160]}")
            if any(s in msg for s in ("getaddrinfo failed", "Name or service not known", "nodename nor servname", "Temporary failure in name resolution")):
                return ConnectionResult("wordpress", "error", "دامنه یافت نشد (خطای DNS)؛ آدرس وردپرس را بررسی کنید.", {"url": root_url})
            return ConnectionResult("wordpress", "error", f"اتصال به {root_url} برقرار نشد.", {"url": root_url})
        except httpx.RequestError as e:
            _step(trace, f"httpx.{e.__class__.__name__}: {str(e)[:160]}")
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
            _step(trace, f"body is not JSON (first bytes: {r.text[:80]!r})")
            return ConnectionResult("wordpress", "error", "پاسخ /wp-json/ یک JSON معتبر نیست.", {"url": root_url})
        ns = data.get("namespaces", [])
        _step(trace, f"JSON ok · name={data.get('name')!r} · namespaces={len(ns)} · wp/v2={'yes' if 'wp/v2' in ns else 'NO'}")
        if "wp/v2" not in ns:
            return ConnectionResult("wordpress", "error",
                                    "پاسخ دریافت شد اما namespace استاندارد wp/v2 پیدا نشد — احتمالاً این یک سایت وردپرسی نیست.",
                                    {"url": root_url, "namespaces": ns[:20]})
        diag = self._wp_diagnostics(base, root_url, r, trace)
        return ConnectionResult("wordpress", "ok", "REST API وردپرس در دسترس است (فقط خواندنی)",
                                {"url": root_url, "site_url": base, "rest_endpoint": wp_rest_v2(base),
                                 "name": data.get("name"), "namespaces": ns[:20], "wp_v2": True, "diagnostics": diag})

    # -- WordPress diagnostics: 3 read-only probes. Credentials (if any) come from env WP_USERNAME/WP_APP_PASSWORD
    #    and are used only as Basic auth for users/me — never stored, returned or written to logs/traces.
    def _wp_diagnostics(self, base: str, root_url: str, root_resp: httpx.Response | None, trace: list[str]) -> list[dict[str, Any]]:
        import base64 as _b64
        import time as _t
        out: list[dict[str, Any]] = []

        def probe(name: str, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
            t0 = _t.perf_counter()
            try:
                rr = self._wp_fetch(url) if not headers else httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": "SEO-Brain/0.2 (+local; read-only)", **headers})
                ms = int((_t.perf_counter() - t0) * 1000)
                entry = {"step": name, "url": url, "ok": rr.status_code < 400, "status_code": rr.status_code, "ms": ms, "content_type": rr.headers.get("content-type", "")[:60]}
                _step(trace, f"probe {name}: GET {url} → HTTP {rr.status_code} in {ms}ms")
                return entry
            except httpx.RequestError as e:
                ms = int((_t.perf_counter() - t0) * 1000)
                _step(trace, f"probe {name}: GET {url} → {e.__class__.__name__}")
                return {"step": name, "url": url, "ok": False, "status_code": None, "ms": ms, "error": e.__class__.__name__}

        # 1) base URL (the site itself)
        out.append({**probe("base_url", base + "/"), "fa": "آدرس سایت"})
        # 2) /wp-json/ (reuse the response we already have)
        if root_resp is not None:
            out.append({"step": "wp_json", "url": root_url, "ok": root_resp.status_code == 200, "status_code": root_resp.status_code, "ms": None, "content_type": root_resp.headers.get("content-type", "")[:60], "fa": "REST API ریشه (/wp-json/)"})
        else:
            out.append({**probe("wp_json", root_url), "fa": "REST API ریشه (/wp-json/)"})
        # 3) /wp-json/wp/v2/users/me — authenticated only when env creds exist (optional; SEO Brain stays read-only)
        user, pw = env("WP_USERNAME"), env("WP_APP_PASSWORD")
        me_url = wp_rest_v2(base) + "users/me"
        if user and pw:
            token = _b64.b64encode(f"{user}:{pw}".encode()).decode()
            e = probe("users_me_auth", me_url, {"Authorization": f"Basic {token}"})
            e["fa"] = "احراز هویت (users/me با Application Password از .env)"
            e["auth"] = "env WP_USERNAME/WP_APP_PASSWORD (not logged)"
            if e.get("status_code") == 401:
                e["hint"] = "نام‌کاربری یا Application Password نادرست است (401)."
            elif e.get("status_code") == 403:
                e["hint"] = "کاربر مجاز نیست یا احراز هویت Basic/Application Passwords غیرفعال است (403)."
            out.append(e)
        else:
            e = probe("users_me_anon", me_url)
            e["fa"] = "users/me بدون احراز هویت (اختیاری)"
            e["ok"] = e.get("status_code") in (200, 401, 403)   # 401/403 = endpoint exists; anonymous access is (correctly) refused
            e["hint"] = ("401 طبیعی است: SEO Brain فقط‌خواندنی است و برای اتصال به Application Password نیازی ندارد. (برای همگام‌سازی با احراز هویت، WP_USERNAME/WP_APP_PASSWORD را در .env بگذارید)" if e.get("status_code") == 401
                         else "403 بدون احراز هویت: users/me برای بازدیدکننده ناشناس توسط افزونه امنیتی/فایروال بسته شده — برای قابلیت‌های فقط‌خواندنی SEO Brain مشکلی نیست." if e.get("status_code") == 403
                         else "پاسخ غیرمنتظره برای users/me؛ فقط اطلاعاتی است و اتصال فقط‌خواندنی را تحت تأثیر قرار نمی‌دهد.")
            out.append(e)
        return out
