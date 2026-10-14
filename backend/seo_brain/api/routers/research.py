"""Market research with explicit evidence provenance and bounded refresh jobs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import Engine, text

from ...analysis.research_intelligence import overview
from ...automation import get_job_queue
from ...automation.queue import Job
from ...db.repositories.base import utcnow
from ..deps import engine, require_site
from ..errors import ApiError

router = APIRouter(prefix="/sites/{site_id}/research", tags=["research"],
                   dependencies=[Depends(require_site)])


class CompetitorCreate(BaseModel):
    url: HttpUrl
    focus_query: str = Field(default="", max_length=200)
    own_url: HttpUrl | None = None


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().rstrip(".").removeprefix("www.")


def _queue_refresh(eng: Engine, site_id: str, page_id: int) -> dict:
    with eng.begin() as cx:
        row = cx.execute(text("""SELECT status,last_requested_at FROM research_competitor_pages
            WHERE site_id=:s AND id=:i"""), {"s": site_id, "i": page_id}).mappings().first()
        if not row:
            raise ApiError(404, "صفحهٔ رقیب پیدا نشد", code="not_found")
        if row["status"] == "queued" and row["last_requested_at"]:
            requested = datetime.fromisoformat(row["last_requested_at"].replace("Z", "+00:00"))
            if requested > datetime.now(timezone.utc) - timedelta(hours=2):
                return {"id": page_id, "status": "queued", "already_queued": True}
        cx.execute(text("""UPDATE research_competitor_pages SET status='queued',last_requested_at=:now,
            updated_at=:now WHERE site_id=:s AND id=:i"""),
            {"now": utcnow(), "s": site_id, "i": page_id})
    try:
        run = get_job_queue().enqueue(Job(type="competitor_refresh",
                                         payload={"site_id": site_id, "competitor_id": page_id}, site_id=site_id))
    except Exception:
        with eng.begin() as cx:
            cx.execute(text("""UPDATE research_competitor_pages SET status='error',error_code='queue_unavailable'
                WHERE site_id=:s AND id=:i"""), {"s": site_id, "i": page_id})
        raise ApiError(503, "صف بررسی رقیب در دسترس نیست", code="queue_unavailable")
    return {"id": page_id, "status": "queued", "job_id": run.run_id}


@router.get("/overview")
def research_overview(site_id: str, days: int = Query(28, ge=7, le=90), eng: Engine = Depends(engine)) -> dict:
    return overview(eng, site_id, days)


@router.post("/competitors", status_code=202)
def create_competitor(site_id: str, body: CompetitorCreate, eng: Engine = Depends(engine)) -> dict:
    url = str(body.url)
    own_url = str(body.own_url) if body.own_url else ""
    with eng.begin() as cx:
        site_host = _host(cx.execute(text("SELECT canonical_url FROM sites WHERE site_id=:s"),
                                     {"s": site_id}).scalar() or "")
        if urlsplit(url).scheme != "https" or _host(url) == site_host:
            raise ApiError(422, "آدرس رقیب باید HTTPS و متعلق به سایت دیگری باشد", code="invalid_competitor_url")
        if own_url and (_host(own_url) != site_host or urlsplit(own_url).scheme != "https"):
            raise ApiError(422, "صفحهٔ خودی باید متعلق به همین سایت باشد", code="invalid_own_url")
        existing = cx.execute(text("SELECT id FROM research_competitor_pages WHERE site_id=:s AND url=:u"),
                              {"s": site_id, "u": url}).scalar()
        if existing:
            raise ApiError(409, "این صفحهٔ رقیب قبلاً ثبت شده است", code="duplicate_competitor")
        now = utcnow()
        result = cx.execute(text("""INSERT INTO research_competitor_pages
            (site_id,url,focus_query,own_url,status,created_at,updated_at)
            VALUES (:s,:u,:q,:own,'pending',:now,:now)"""),
            {"s": site_id, "u": url, "q": body.focus_query.strip(), "own": own_url, "now": now})
        page_id = int(result.lastrowid)
    return _queue_refresh(eng, site_id, page_id)


@router.post("/competitors/{page_id}/refresh", status_code=202)
def refresh_competitor_page(site_id: str, page_id: int, eng: Engine = Depends(engine)) -> dict:
    return _queue_refresh(eng, site_id, page_id)


@router.delete("/competitors/{page_id}")
def delete_competitor_page(site_id: str, page_id: int, eng: Engine = Depends(engine)) -> dict:
    with eng.begin() as cx:
        result = cx.execute(text("DELETE FROM research_competitor_pages WHERE site_id=:s AND id=:i"),
                            {"s": site_id, "i": page_id})
    if not result.rowcount:
        raise ApiError(404, "صفحهٔ رقیب پیدا نشد", code="not_found")
    return {"deleted": page_id}
