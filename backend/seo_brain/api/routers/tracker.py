"""Public beacon endpoints (phase 1). No X-API-Token: these are called by the visitor's browser on the
managed sites, which cannot hold a secret and cannot be added to the admin CORS allowlist.

Two deliberate choices keep this safe and configuration-free:
  * the body arrives as text/plain, which makes the POST a CORS-simple request — no preflight, so the
    admin-only CORS allowlist in main.py stays untouched;
  * the site is identified by its own write key, not by a path parameter, so a key can be rotated or
    disabled per site without touching anything else. The key is public by nature (it ships in the page):
    it scopes writes to one site, it is not an authentication boundary.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import Engine

from ...tracking import TrackingService
from ..deps import engine

router = APIRouter(prefix="/track", tags=["tracking"])

MAX_BODY_BYTES = 64_000
_SCRIPT = Path(__file__).resolve().parents[2] / "tracking" / "static" / "track.js"


def svc(eng: Engine = Depends(engine)) -> TrackingService:
    return TrackingService(eng)


def _client_ip(request: Request) -> str:
    """First hop of X-Forwarded-For when present, else the socket peer. Hashed immediately, never stored."""
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "") or ""


def public_base(request: Request, api_prefix: str) -> str:
    """Absolute URL of the tracker root, as a browser on another domain must address it.

    Always the API's own origin, never the panel's: the two run on different ports locally and on
    different hosts in production. Override with TRACK_PUBLIC_URL when the API sits behind a domain.
    """
    from ...common.config import env
    override = env("TRACK_PUBLIC_URL")
    if override:
        return f"{override.rstrip('/')}/track"
    return f"{str(request.base_url).rstrip('/')}{api_prefix}/track"


@router.get("/{site_id}/t.js")
def tracker_script(site_id: str, request: Request, s: TrackingService = Depends(svc)) -> Response:
    """The per-site tracker, with its write key baked in. Include it once in the shared theme:

        <script src="https://seo.example.com/api/v1/track/<site_id>/t.js" defer></script>
    """
    key = s.repo.ensure_key(site_id)
    body = _SCRIPT.read_text(encoding="utf-8").replace("__WRITE_KEY__", key["write_key"]).replace("__ENDPOINT__", public_base(request, request.url.path.rsplit("/", 3)[0]))
    return Response(body, media_type="application/javascript; charset=utf-8",
                    headers={"Cache-Control": "public, max-age=3600", "X-Robots-Tag": "noindex"})


@router.post("", status_code=204)
async def beacon(request: Request, s: TrackingService = Depends(svc)) -> Response:
    """Accept a batch of hits. Always answers 204 — a tracker must never make a page wait or show an error."""
    try:
        raw = await request.body()
        if not raw or len(raw) > MAX_BODY_BYTES:
            return Response(status_code=204)
        payload = json.loads(raw.decode("utf-8", "replace"))
        if not isinstance(payload, dict):
            return Response(status_code=204)
        s.ingest(str(payload.get("k") or ""), payload, _client_ip(request),
                 request.headers.get("user-agent", ""), site_host="")
    except Exception:  # noqa: BLE001  (never surface ingestion problems to a visitor's browser)
        pass
    return Response(status_code=204)
