"""Google account connection (web OAuth) — the browser replacement for `sync-gsc.py --auth-only`.

Two routers: `router` sits behind the normal X-API-Token dependency (status / authorize / disconnect, called through
the Next proxy), while `callback_router` is registered WITHOUT it — Google redirects the user's browser straight
here and cannot send our header. The callback only exchanges the code (guarded by the state nonce) and renders a
tiny Persian close-this-window page; it never echoes tokens.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse

from ...connections import google_oauth
from ...gsc.client import GscAuthError
from ..errors import ApiError

log = logging.getLogger("api.google")

router = APIRouter(prefix="/connections/google", tags=["connections"])
callback_router = APIRouter(prefix="/connections/google", tags=["connections"])


@router.get("/status")
def google_status() -> dict:
    """Connected Google account: email · scopes (GSC/GA4) · expiry · whether the OAuth client is configured."""
    return google_oauth.status()


@router.get("/authorize")
def google_authorize() -> dict:
    """Build the Google consent URL (web flow). The frontend opens it in a new tab; Google redirects to /callback."""
    try:
        out = google_oauth.begin()
    except GscAuthError as e:
        raise ApiError(409, str(e), code="google_client_not_configured")
    return {"url": out["url"], "redirect_uri": out["redirect_uri"]}


class GoogleClientBody(BaseModel):
    client_id: str = Field(min_length=10, max_length=200)
    client_secret: str = Field(min_length=10, max_length=200)


@router.put("/client")
def google_client_save(body: GoogleClientBody) -> dict:
    """Self-service setup: store the Google OAuth client (Desktop type) in the SecretStore — no .env editing.
    The secret is never returned; only `configured` + a masked client id hint."""
    try:
        return google_oauth.save_client(body.client_id, body.client_secret)
    except GscAuthError as e:
        raise ApiError(422, str(e), code="google_client_invalid")
    except Exception as e:  # noqa: BLE001 — e.g. SecretStore has no encryption backend
        raise ApiError(409, f"ذخیرهٔ امن ممکن نشد: {e.__class__.__name__}", code="secret_store_unavailable")


@router.delete("")
def google_disconnect() -> dict:
    """Revoke (best-effort) and remove the local token — GSC/GA4 syncs will report not_authorized afterwards."""
    return google_oauth.disconnect()


_PAGE = """<!doctype html><html dir="rtl" lang="fa"><head><meta charset="utf-8"><title>SEO Brain</title>
<style>body{{font-family:Tahoma,system-ui;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
.card{{background:#1e293b;border-radius:12px;padding:32px 40px;text-align:center;max-width:26rem}}h1{{font-size:1.1rem;margin:0 0 8px}}p{{color:#94a3b8;font-size:.9rem;margin:0}}</style></head>
<body><div class="card"><h1>{title}</h1><p>{body}</p></div><script>setTimeout(function(){{try{{window.close()}}catch(e){{}}}},2500)</script></body></html>"""


@callback_router.get("/callback", response_class=HTMLResponse, include_in_schema=True)
def google_callback(code: str | None = Query(default=None), state: str | None = Query(default=None),
                    error: str | None = Query(default=None)) -> HTMLResponse:
    """OAuth redirect target (no X-API-Token — Google's redirect cannot send it; the state nonce is the guard)."""
    if error or not code:
        log.warning(f"Google OAuth callback denied: {error or 'no code'}")
        return HTMLResponse(_PAGE.format(title="اتصال انجام نشد", body="دسترسی رد شد یا کد دریافت نشد. این پنجره را ببندید و دوباره تلاش کنید."), status_code=400)
    try:
        out = google_oauth.finish(code, state)
    except GscAuthError as e:
        return HTMLResponse(_PAGE.format(title="اتصال انجام نشد", body=str(e)), status_code=400)
    except Exception as e:  # noqa: BLE001 — never leak token internals to the browser
        log.error(f"Google OAuth exchange failed: {e.__class__.__name__}")
        return HTMLResponse(_PAGE.format(title="اتصال انجام نشد", body="تبادل کد با گوگل ناموفق بود؛ دوباره تلاش کنید."), status_code=400)
    who = out.get("email") or "حساب گوگل"
    return HTMLResponse(_PAGE.format(title="✅ اتصال برقرار شد", body=f"{who} متصل شد. این پنجره به‌زودی بسته می‌شود — به SEO Brain برگردید."))
