"""Internal Link Intelligence endpoints (phase 8): /sites/{site_id}/links/*  — analyze · suggest · approve · export. No WordPress writes."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import Engine

from ...automation.queue import Job, JobQueue
from ...brain.content import ContentService
from ...brain.linking import LinkEngine
from ...brain.linking.audit import FLAG_FA
from ...brain.linking.journey import STAGE_FA
from ...brain.linking.repository import CONF_FA, KIND_FA, KINDS, STATUSES
from ..deps import engine, job_queue, require_site
from ..errors import ApiError

router = APIRouter(prefix="/sites/{site_id}/links", tags=["links"], dependencies=[Depends(require_site)])


class SuggestionStatus(BaseModel):
    status: Literal["new", "accepted", "dismissed", "done"]
    anchor: str | None = None


class PatternStatus(BaseModel):
    status: Literal["new", "accepted", "dismissed"]


class ContentTask(BaseModel):
    title: str | None = None
    note: str | None = None


def eng(e: Engine = Depends(engine)) -> LinkEngine:
    return LinkEngine(e)


@router.get("/meta")
def meta() -> dict:
    return {"kinds": [{"kind": k, "fa": KIND_FA[k]} for k in KINDS], "statuses": list(STATUSES), "confidence": [{"key": k, "fa": v, "range": r} for k, v, r in (("low", CONF_FA["low"], "0.45–0.60"), ("recommended", CONF_FA["recommended"], "0.60–0.80"), ("high", CONF_FA["high"], "0.80+"))],
            "flags": [{"flag": k, "fa": v} for k, v in FLAG_FA.items()], "stages": [{"stage": k, "fa": v} for k, v in STAGE_FA.items()],
            "journey": ["informational", "commercial", "service", "conversion"], "scopes": ["internal"], "future_scopes": ["external", "backlink", "competitor"]}


@router.post("/analyze")
def analyze(site_id: str, e: LinkEngine = Depends(eng), q: JobQueue = Depends(job_queue), force_sync: bool = False, response: Response = None) -> dict:  # type: ignore[assignment]
    """Queue analysis by default so its lifetime is independent from the browser request."""
    if force_sync:
        return {"mode": "sync", **e.analyze(site_id)}
    run = q.enqueue(Job(type="links_analyze", payload={"site_id": site_id}, site_id=site_id))
    if response is not None:
        response.status_code = 202
    return {"mode": "job", **run.to_dict()}


@router.get("/summary")
def summary(site_id: str, e: LinkEngine = Depends(eng)) -> dict:
    return {**e.repo.counts(site_id), "settings": e.settings(site_id)}


@router.get("/suggestions")
def suggestions(site_id: str, kind: str | None = None, status: str | None = "new", min_score: float = 0.0, confidence: str | None = None, target: str | None = None, source: str | None = None,
                q: str | None = None, sort: str = "score", limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), e: LinkEngine = Depends(eng)) -> dict:
    rows, total = e.repo.list(site_id, kind, status or None, min_score, target, source, q, confidence, sort, limit, offset)
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/suggestions/{sid}")
def suggestion(site_id: str, sid: int, e: LinkEngine = Depends(eng)) -> dict:
    s = e.repo.get(site_id, sid)
    if not s:
        raise HTTPException(404, "suggestion not found")
    return s


@router.patch("/suggestions/{sid}")
def set_suggestion(site_id: str, sid: int, body: SuggestionStatus, e: LinkEngine = Depends(eng)) -> dict:
    """accept → SUGGESTED_LINK edge (planned); done → same with props.done; dismiss → removes LINK_OPPORTUNITY. Anchor may be edited."""
    s = e.set_status(site_id, sid, body.status, body.anchor)
    if not s:
        raise HTTPException(404, "suggestion not found")
    return s


@router.post("/suggestions/{sid}/content-task", status_code=201)
def create_content_task(site_id: str, sid: int, body: ContentTask | None = None, e: LinkEngine = Depends(eng), db: Engine = Depends(engine)) -> dict:
    """Create a planned Content Brain item from an accepted suggestion (e.g. missing supporting article). Never automatic."""
    s = e.repo.get(site_id, sid)
    if not s:
        raise HTTPException(404, "suggestion not found")
    body = body or ContentTask()
    title = body.title or (f"لینک‌سازی: «{s['anchor']}» از {s['source_title']} به {s['target_title']}" if s["kind"] != "supports" else f"مقاله پشتیبان: {s['anchor']}")
    cs = ContentService(db, None)
    item = cs.create(site_id, title, target_keyword=s.get("anchor"), url=s["source_url"] if s["kind"] != "supports" else None,
                     metadata={"link_suggestion_id": sid, "source_url": s["source_url"], "target_url": s["target_url"], "anchor": s["anchor"], "reason": s["reason_fa"]},
                     notes=body.note or f"از پیشنهاد لینک #{sid}: {s['reason_fa']}")
    e.repo.set_status(site_id, sid, s["status"] if s["status"] != "new" else "accepted", content_task_id=item.id)
    return {"content_id": item.id, "title": item.title, "status": item.status, "suggestion": e.repo.get(site_id, sid)}


@router.get("/pages")
def pages(site_id: str, flag: str | None = None, sort: str = "health_score", order: Literal["asc", "desc"] = "asc", q: str | None = None,
          limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), e: LinkEngine = Depends(eng)) -> dict:
    rows, total = e.repo.pages(site_id, flag, sort, order, limit, offset, q)
    for r in rows:
        r["flags_fa"] = [FLAG_FA.get(f, f) for f in r["flags"]]
    return {"items": rows, "total": total}


@router.get("/pages/{node_id:path}")
def page(site_id: str, node_id: str, e: LinkEngine = Depends(eng)) -> dict:
    p = e.page_detail(site_id, node_id)
    if not p:
        raise HTTPException(404, "page not analyzed — run /links/analyze")
    return p


@router.get("/patterns")
def patterns(site_id: str, status: str | None = None, e: LinkEngine = Depends(eng)) -> list[dict]:
    return e.repo.patterns(site_id, status)


@router.patch("/patterns/{pid}")
def set_pattern(site_id: str, pid: int, body: PatternStatus, e: LinkEngine = Depends(eng)) -> dict:
    """accepted → written to Site Brain memory (successful_patterns, source internal_linking). Never automatic."""
    p = e.set_pattern_status(site_id, pid, body.status)
    if not p:
        raise HTTPException(404, "pattern not found")
    return p


@router.get("/settings")
def get_settings(site_id: str, e: LinkEngine = Depends(eng)) -> dict:
    return e.settings(site_id)


@router.put("/settings")
def put_settings(site_id: str, body: dict[str, Any], e: LinkEngine = Depends(eng)) -> dict:
    return e.put_settings(site_id, body)


@router.get("/export.csv")
def export_csv(site_id: str, status: str = "accepted,done", e: LinkEngine = Depends(eng)) -> Response:
    return Response(content=e.export_csv(site_id, status), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="links-{site_id}.csv"'})
