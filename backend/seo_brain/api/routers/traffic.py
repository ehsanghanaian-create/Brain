"""Traffic Intel read endpoints (phase 1–2). Site-scoped: /sites/{site_id}/traffic/*

Exact numbers and estimates are kept in separate endpoints on purpose. /overview, /entries, /calls and
/behavior are measured first-party facts. /keywords is a modelled estimate and says so in its own payload —
Search Console never reports a query per visitor, so nothing can make that number exact.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import Engine

from ...db.repositories.sites import Site
from ...tracking import TrackingService
from ..deps import engine, require_site
from .tracker import public_base

router = APIRouter(prefix="/sites/{site_id}/traffic", tags=["traffic"], dependencies=[Depends(require_site)])



def svc(eng: Engine = Depends(engine)) -> TrackingService:
    return TrackingService(eng)


def _brand_terms(site: Site) -> tuple[str, ...]:
    """Words that make a query 'branded' for this site — the site name plus its host, minus noise."""
    words = [w for w in (site.name or "").replace("‌", " ").split() if len(w) > 2]
    host = (site.canonical_url or "").replace("https://", "").replace("http://", "").split("/")[0]
    if host:
        words.append(host.split(".")[0])
    return tuple(dict.fromkeys(words))


@router.get("/overview")
def overview(site_id: str, days: int = Query(28, ge=1, le=480), s: TrackingService = Depends(svc)) -> dict:
    """Sessions, pageviews, tel: clicks and channel split for the window, plus a daily series and coverage."""
    return s.overview(site_id, days)


@router.get("/entries")
def entries(site_id: str, days: int = Query(28, ge=1, le=480), limit: int = Query(50, ge=1, le=500), s: TrackingService = Depends(svc)) -> dict:
    """Landing pages with both sides side by side: first-party sessions/conversions and Search Console clicks."""
    return s.organic_entries(site_id, days, limit)


@router.get("/calls")
def calls(site_id: str, days: int = Query(28, ge=1, le=480), limit: int = Query(50, ge=1, le=500), s: TrackingService = Depends(svc)) -> dict:
    """tel: clicks by page, hour, day and channel. This is intent to call — not a completed call."""
    return s.repo.calls(site_id, days, limit)


@router.get("/behavior")
def behavior(site_id: str, days: int = Query(28, ge=1, le=480), path: str | None = None, limit: int = Query(50, ge=1, le=500),
             s: TrackingService = Depends(svc)) -> dict:
    """Scroll depth, click positions, most-viewed pages and exit pages. `path` narrows to a single page."""
    return s.repo.behavior(site_id, days, path, limit)


@router.get("/keywords")
def keywords(site_id: str, days: int = Query(28, ge=1, le=480), limit: int = Query(100, ge=1, le=500),
             site: Site = Depends(require_site), s: TrackingService = Depends(svc)) -> dict:
    """ESTIMATED keyword → conversion attribution. Every row carries a share and a confidence grade."""
    return s.keyword_estimate(site_id, days, limit, _brand_terms(site))


@router.get("/paid")
def paid(site_id: str, days: int = Query(90, ge=1, le=90), limit: int = Query(100, ge=1, le=500), s: TrackingService = Depends(svc)) -> dict:
    """Sessions carrying a gclid — the only traffic whose keyword is exactly recoverable (via Ads API, 90-day window)."""
    return s.paid_keywords(site_id, days, limit)


@router.get("/setup")
def setup(site_id: str, request: Request, site: Site = Depends(require_site), s: TrackingService = Depends(svc)) -> dict:
    """Write key + the one-line snippet to paste into the shared theme, and whether any data has arrived yet."""
    key = s.repo.ensure_key(site_id)
    base = public_base(request, request.url.path.split("/sites/")[0])   # the API's origin, not the panel's
    return {
        "site_id": site_id,
        "write_key": key["write_key"],
        "enabled": bool(int(key.get("enabled", 1))),
        "created_at": key.get("created_at"),
        "rotated_at": key.get("rotated_at"),
        "script_path": f"/api/v1/track/{site_id}/t.js",   # kept so an older frontend build keeps rendering
        "script_url": f"{base}/{site_id}/t.js",
        "beacon_url": base,
        "snippet": f'<script src="{base}/{site_id}/t.js" defer></script>',
        "coverage": s.repo.has_data(site_id),
        "canonical_url": site.canonical_url,
    }


class TrackerToggle(BaseModel):
    enabled: bool


@router.patch("/setup")
def set_enabled(site_id: str, body: TrackerToggle, s: TrackingService = Depends(svc)) -> dict:
    """Stop or resume ingestion for this site without touching the theme."""
    s.repo.ensure_key(site_id)
    s.repo.set_enabled(site_id, body.enabled)
    return s.repo.ensure_key(site_id)


@router.post("/setup/rotate", status_code=201)
def rotate(site_id: str, s: TrackingService = Depends(svc)) -> dict:
    """New write key and new hashing secret. Sites keep reporting only after the theme picks up the new script."""
    return s.repo.rotate_key(site_id)


@router.get("/coverage")
def coverage(site_id: str, s: TrackingService = Depends(svc)) -> dict:
    """Row counts and date range — used by the UI to decide between the empty state and the report."""
    return s.repo.has_data(site_id)
