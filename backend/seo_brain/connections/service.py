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
from ..core.secrets import SecretStore
from ..db.tables import site_connections

SecretStoreHint = SecretStore.hint

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
    if env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"):
        return True
    try:
        from ..core.secrets import get_secret_store
        store = get_secret_store()
        return bool(store.get("google-client-id") and store.get("google-client-secret"))
    except Exception:  # noqa: BLE001 — unavailable secret storage is equivalent to an unconfigured client
        return False


def _token_info() -> dict[str, Any]:
    """Read the cached OAuth token via the shared storage helper (SecretStore-first, legacy-file fallback)."""
    from ..gsc.client import read_token_json
    raw = read_token_json()
    if not raw:
        return _merge_sa({"present": False, "oauth_present": False, "scopes": [], "oauth_scopes": [],
                          "expiry": None, "source": None})
    try:
        data = json.loads(raw)
    except ValueError:
        return _merge_sa({"present": False, "oauth_present": False, "scopes": [], "oauth_scopes": [],
                          "expiry": None, "source": None})
    oauth_scopes = list(data.get("scopes") or [])
    oauth_present = bool(data.get("refresh_token"))
    out = {"present": oauth_present, "oauth_present": oauth_present, "scopes": oauth_scopes,
           "oauth_scopes": oauth_scopes, "expiry": data.get("expiry"), "source": "oauth"}
    return _merge_sa(out)


def _merge_sa(out: dict[str, Any]) -> dict[str, Any]:
    """A configured Service Account authorizes GSC even without any OAuth token (GA4 gating stays OAuth-only)."""
    try:
        from .service_account import sa_configured, sa_email
        if sa_configured():
            out["present"] = True
            if GSC_SCOPE not in out["scopes"]:
                out["scopes"] = [GSC_SCOPE, *out["scopes"]]
            out["sa_email"] = sa_email()
            out["source"] = "oauth+sa" if out.get("source") == "oauth" else "service_account"
    except Exception:  # noqa: BLE001
        pass
    return out


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
                 ga4_report_factory: Callable[[str], dict] | None = None, wp_fetch: Callable[[str], httpx.Response] | None = None,
                 wp_fetch_auth: Callable[[str, tuple[str, str]], httpx.Response] | None = None,
                 ga4_admin_factory: Callable[[], Any] | None = None):
        self.repo = ConnectionsRepository(engine)
        self._gsc_factory = gsc_client_factory
        self._ga4_report = ga4_report_factory
        self._ga4_admin = ga4_admin_factory
        from ..common.http import site_proxy
        self._wp_fetch = wp_fetch or (lambda url: httpx.get(url, timeout=20, follow_redirects=True, proxy=site_proxy(), headers={"User-Agent": "SEO-Brain/0.2 (+local; read-only)"}))
        if wp_fetch_auth is not None:
            self._wp_fetch_auth = wp_fetch_auth  # type: ignore[method-assign]

    # -- status
    def status(self, site_id: str) -> dict[str, dict]:
        return {k: v.to_dict() for k, v in self.repo.get_all(site_id).items()}

    # -- Google Search Console
    def list_gsc_properties(self) -> dict[str, Any]:
        from .service_account import sa_configured
        if not _google_client_configured() and not sa_configured():
            return {"status": "not_configured", "properties": [], "message": "نه Service Account ثبت شده و نه OAuth Client (GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET) پیکربندی شده است"}
        tok = _token_info()
        if not tok["present"]:
            return {"status": "not_authorized", "properties": [], "message": "توکن Google وجود ندارد؛ برای اتصال حساب گوگل، از بخش «حساب گوگل» در مرکز اتصال‌ها اتصال را انجام دهید"}
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
        from .service_account import sa_configured
        _step(trace, f"Google credential provider: OAuth client={'yes' if _google_client_configured() else 'no'}, service account={'yes' if sa_configured() else 'no'}")
        if not _google_client_configured() and not sa_configured():
            return ConnectionResult("gsc", "not_configured", "نه Service Account ثبت شده و نه OAuth Client (GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET) پیکربندی شده است", {"property": wanted})
        tok = _token_info()
        _step(trace, f"OAuth token file {resolve_path(env('GSC_TOKEN_PATH', 'tokens/gsc_token.json')).name}: present={tok['present']} scopes={len(tok['scopes'])} expiry={tok.get('expiry') or '?'}")
        if not tok["present"]:
            return ConnectionResult("gsc", "not_authorized", "توکن Google وجود ندارد؛ برای اتصال حساب گوگل، از بخش «حساب گوگل» در مرکز اتصال‌ها اتصال را انجام دهید", {"property": wanted})
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
    def list_ga4_properties(self) -> dict[str, Any]:
        """GA4 property discovery (Analytics Admin API accountSummaries) — same shared Google token, read-only."""
        if not _google_client_configured():
            return {"status": "not_configured", "properties": [], "message": "GOOGLE_CLIENT_ID/SECRET تنظیم نشده است"}
        tok = _token_info()
        if not tok["present"]:
            return {"status": "not_authorized", "properties": [], "message": "توکن Google وجود ندارد؛ ابتدا «اتصال حساب گوگل» را انجام دهید"}
        if GA4_SCOPE not in tok["scopes"]:
            return {"status": "not_authorized", "properties": [], "message": "توکن فعلی اسکوپ analytics.readonly ندارد؛ حساب گوگل را دوباره متصل کنید"}
        try:
            svc = self._ga4_admin() if self._ga4_admin else self._build_ga4_admin()
            out: list[dict[str, Any]] = []
            token = None
            while True:
                resp = svc.accountSummaries().list(pageSize=200, pageToken=token).execute() if token else svc.accountSummaries().list(pageSize=200).execute()
                for acc in resp.get("accountSummaries", []):
                    for ps in acc.get("propertySummaries", []):
                        out.append({"property_id": str(ps.get("property", "")).replace("properties/", ""),
                                    "display_name": ps.get("displayName"), "account": acc.get("displayName"), "website_url": None})
                token = resp.get("nextPageToken")
                if not token:
                    break
            for p_ in out[:30]:                     # web stream URL → exact domain matching in onboarding (quota-capped)
                try:
                    streams = svc.properties().dataStreams().list(parent=f"properties/{p_['property_id']}").execute()
                    for st_ in streams.get("dataStreams", []):
                        uri = (st_.get("webStreamData") or {}).get("defaultUri")
                        if uri:
                            p_["website_url"] = uri
                            break
                except Exception:  # noqa: BLE001 — per-property; matching just falls back to the name heuristic
                    continue
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            st = "not_authorized" if "403" in msg or "PERMISSION_DENIED" in msg else "error"
            return {"status": st, "properties": [], "message": f"خطا در فراخوانی Analytics Admin API: {e.__class__.__name__}: {msg[:200]}"}
        return {"status": "ok", "properties": out}

    @staticmethod
    def _build_ga4_admin():
        from ..common.google_http import build_google_service
        from ..gsc.client import get_credentials
        return build_google_service("analyticsadmin", "v1beta", get_credentials(interactive=False))

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
                                    "توکن فعلی اسکوپ GA4 را ندارد؛ در بخش «حساب گوگل» دکمهٔ «اتصال دوباره» را بزنید و هر دو دسترسی را تأیید کنید",
                                    {"property": pid, "scopes": tok["scopes"], "required_scope": GA4_SCOPE})
        try:
            report = self._ga4_report(pid) if self._ga4_report else self._run_ga4_probe(pid)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            status = "not_authorized" if "403" in msg or "PERMISSION_DENIED" in msg else ("not_found" if "404" in msg else "error")
            return ConnectionResult("ga4", status, f"خطا در فراخوانی GA4 Data API: {e.__class__.__name__}: {msg[:200]}", {"property": pid})
        return ConnectionResult("ga4", "ok", "دسترسی GA4 تأیید شد", {"property": pid, "rows": report.get("rowCount", 0)})

    def _run_ga4_probe(self, pid: str) -> dict:
        from ..common.google_http import build_google_service
        from ..gsc.client import get_credentials
        svc = build_google_service("analyticsdata", "v1beta", get_credentials(interactive=False))
        body = {"dateRanges": [{"startDate": "7daysAgo", "endDate": "yesterday"}], "metrics": [{"name": "sessions"}], "limit": 1}
        return svc.properties().runReport(property=f"properties/{pid}", body=body).execute()

    # -- WordPress REST (public, GET only)
    def test_wordpress(self, site_id: str, wp_url: str | None, username: str | None = None, app_password: str | None = None) -> ConnectionResult:
        """Stage 1: public REST (`/wp-json/`, no credentials). Stage 2: Application-Password identity check
        (`/wp-json/wp/v2/users/me`, Basic auth) — ONLY when credentials exist (body → SecretStore → .env); never anonymously."""
        from ..wordpress.auth import resolve_auth
        trace: list[str] = []
        res = self._test_wordpress(wp_url, trace, auth=resolve_auth(site_id, username, app_password))
        res.detail = {**res.detail, "trace": trace}
        self.repo.save(site_id, res)
        return res

    def _test_wordpress(self, wp_url: str | None, trace: list[str] | None = None, auth=None) -> ConnectionResult:
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
        diag, auth_detail = self._wp_diagnostics(base, root_url, r, trace, auth)
        msg = "REST API وردپرس در دسترس است (فقط خواندنی)"
        if auth_detail["configured"]:
            msg += " · " + ("احراز هویت تأیید شد" + (f" ({auth_detail.get('user_name') or auth_detail.get('username')})" if auth_detail.get("status") == "ok" else "") if auth_detail.get("status") == "ok" else f"احراز هویت ناموفق: {auth_detail.get('message')}")
        return ConnectionResult("wordpress", "ok", msg,
                                {"url": root_url, "site_url": base, "rest_endpoint": wp_rest_v2(base),
                                 "name": data.get("name"), "namespaces": ns[:20], "wp_v2": True, "diagnostics": diag, "auth": auth_detail})

    # -- WordPress diagnostics (read-only). Stage 1 = public REST (base URL + /wp-json/), Stage 2 = Application-Password
    #    identity check on /wp-json/wp/v2/users/me with Basic auth — executed ONLY when credentials are available
    #    (explicit → per-site SecretStore → .env). Credentials are never stored here, returned, logged or traced.
    def _wp_diagnostics(self, base: str, root_url: str, root_resp: httpx.Response | None, trace: list[str], auth=None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        import time as _t
        out: list[dict[str, Any]] = []

        def probe(name: str, url: str, basic: tuple[str, str] | None = None) -> dict[str, Any]:
            t0 = _t.perf_counter()
            try:
                rr = self._wp_fetch(url) if basic is None else self._wp_fetch_auth(url, basic)
                ms = int((_t.perf_counter() - t0) * 1000)
                _step(trace, f"probe {name}: GET {url}{' (authenticated as ' + basic[0] + ')' if basic else ''} → HTTP {rr.status_code} in {ms}ms")
                return {"step": name, "url": url, "ok": rr.status_code < 400, "status_code": rr.status_code, "ms": ms, "content_type": rr.headers.get("content-type", "")[:60], "_resp": rr}
            except httpx.TimeoutException as e:
                _step(trace, f"probe {name}: GET {url} → timeout ({e.__class__.__name__})")
                return {"step": name, "url": url, "ok": False, "status_code": None, "ms": int((_t.perf_counter() - t0) * 1000), "error": "timeout"}
            except httpx.RequestError as e:
                _step(trace, f"probe {name}: GET {url} → {e.__class__.__name__}")
                return {"step": name, "url": url, "ok": False, "status_code": None, "ms": int((_t.perf_counter() - t0) * 1000), "error": e.__class__.__name__}

        # ---- Stage 1: public REST
        e1 = probe("base_url", base + "/"); e1.pop("_resp", None); e1.update({"stage": "public", "fa": "آدرس سایت"}); out.append(e1)
        if root_resp is not None:
            out.append({"step": "rest_public", "stage": "public", "fa": "REST API عمومی (/wp-json/)", "url": root_url, "ok": root_resp.status_code == 200, "status_code": root_resp.status_code, "ms": None, "content_type": root_resp.headers.get("content-type", "")[:60]})
        else:
            e2 = probe("rest_public", root_url); e2.pop("_resp", None); e2.update({"stage": "public", "fa": "REST API عمومی (/wp-json/)"}); out.append(e2)

        # ---- Stage 2: Application Password (optional, never anonymous)
        me_url = wp_rest_v2(base) + "users/me?context=edit"
        if auth is None:
            out.append({"step": "auth", "stage": "auth", "fa": "احراز هویت (Application Password)", "url": me_url, "ok": None, "status_code": None, "ms": None, "skipped": True,
                        "hint": "نام‌کاربری و Application Password وارد نشده — اتصال فقط‌خواندنی عمومی فعال است. برای تأیید هویت و خواندن احراز‌هویت‌شده، آن‌ها را وارد کنید."})
            return out, {"configured": False, "status": "not_configured", "message": "بدون احراز هویت (اختیاری)"}
        e3 = probe("auth", me_url, auth.basic)
        rr = e3.pop("_resp", None)
        e3.update({"stage": "auth", "fa": "احراز هویت (users/me با Application Password)", "username": auth.username, "source": auth.source})
        code = e3.get("status_code")
        e4 = None
        if code in (401, 403) and rr is not None and "json" not in (rr.headers.get("content-type") or "").lower():
            # هاست‌های LiteSpeed/افزونه‌های امنیتی اغلب کل مسیر wp/v2/users* را با 403 (صفحه HTML) می‌بندند حتی با auth درست —
            # در این حالت احراز هویت را با یک probe فقط‌خواندنی نیازمند مجوز ویرایش (posts?context=edit) می‌سنجیم.
            alt_url = wp_rest_v2(base) + "posts?context=edit&per_page=1"
            e4 = probe("auth_fallback", alt_url, auth.basic); e4.pop("_resp", None)
            e4.update({"stage": "auth", "fa": "احراز هویت جایگزین (posts?context=edit — مسیر users توسط فایروال هاست بسته است)", "username": auth.username, "source": auth.source})
            alt_code = e4.get("status_code")
            if alt_code == 200:
                e3["hint"] = f"HTTP {code} با صفحه HTML — فایروال هاست مسیر users را می‌بندد؛ احراز هویت با probe جایگزین تأیید شد."
                e4["ok"] = True; e4["hint"] = "۲۰۰ — دسترسی ویرایش (edit_posts) تأیید شد"
                st = {"configured": True, "status": "ok", "message": "احراز هویت تأیید شد — مسیر users توسط فایروال هاست بسته است؛ دسترسی ویرایش با probe جایگزین تأیید شد"}
            elif alt_code in (401, 403):
                e3["ok"] = False
                e4["ok"] = False; e4["hint"] = "نام‌کاربری/Application Password نادرست است یا کاربر مجوز ویرایش ندارد."
                st = {"configured": True, "status": "not_authorized", "message": "نام‌کاربری یا Application Password نادرست است (probe جایگزین هم رد شد)"}
            else:
                e3["ok"] = False
                e4["hint"] = f"پاسخ غیرمنتظره probe جایگزین: HTTP {alt_code}" if alt_code else f"خطای شبکه: {e4.get('error')}"
                st = {"configured": True, "status": "error", "message": f"احراز هویت نامشخص — probe جایگزین: {alt_code or e4.get('error')}"}
            st.update({"username": auth.username, "source": auth.source, "key_hint": SecretStoreHint(auth.app_password)})
            out.append(e3); out.append(e4)
            return out, st
        if code == 200:
            info = {}
            try:
                j = rr.json() if rr is not None else {}
                info = {"user_id": j.get("id"), "user_name": j.get("name"), "roles": (j.get("roles") or [])[:5], "capabilities_read": bool((j.get("capabilities") or {}).get("read", True))}
            except ValueError:
                pass
            e3["ok"] = True; e3["hint"] = f"کاربر متصل شد: {info.get('user_name') or auth.username}" + (f" · نقش‌ها: {', '.join(info['roles'])}" if info.get("roles") else "")
            st = {"configured": True, "status": "ok", "message": "احراز هویت تأیید شد", **info}
        elif code == 401:
            e3["ok"] = False; e3["hint"] = "۴۰۱ — نام‌کاربری یا Application Password اشتباه است (یا Application Passwords در وردپرس غیرفعال است)."
            st = {"configured": True, "status": "not_authorized", "message": "نام‌کاربری یا Application Password نادرست است (401)"}
        elif code == 403:
            e3["ok"] = False; e3["hint"] = "۴۰۳ — کاربر مجاز نیست یا افزونه امنیتی/فایروال درخواست‌های Basic auth را مسدود می‌کند."
            st = {"configured": True, "status": "forbidden", "message": "دسترسی رد شد (403) — مجوز کاربر یا افزونه امنیتی"}
        elif e3.get("error") == "timeout":
            e3["hint"] = "timeout — مشکل اتصال به سرور هنگام احراز هویت."
            st = {"configured": True, "status": "timeout", "message": "اتصال هنگام احراز هویت timeout شد"}
        elif e3.get("error"):
            e3["hint"] = f"خطای شبکه: {e3['error']}"
            st = {"configured": True, "status": "error", "message": f"خطای شبکه هنگام احراز هویت ({e3['error']})"}
        else:
            e3["ok"] = False; e3["hint"] = f"پاسخ غیرمنتظره HTTP {code}"
            st = {"configured": True, "status": "error", "message": f"پاسخ غیرمنتظره HTTP {code}"}
        st.update({"username": auth.username, "source": auth.source, "key_hint": SecretStoreHint(auth.app_password)})
        out.append(e3)
        return out, st

    def _wp_fetch_auth(self, url: str, basic: tuple[str, str]) -> httpx.Response:
        """Authenticated GET (Basic = Application Password). Separate hook so tests can fake it; the password never reaches logs."""
        from ..common.http import site_proxy
        return httpx.get(url, timeout=20, follow_redirects=True, auth=basic, proxy=site_proxy(), headers={"User-Agent": "SEO-Brain/0.2 (+local; read-only)"})
