"""Content Brain endpoints (phase 6): /sites/{site_id}/content/*  — human approval workflow, no auto-publishing."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from ...brain.content import ContentService, WorkflowError
from ...brain.content.intelligence import ContentIntelligenceService
from ...brain.content.analytics import ContentAnalytics
from ...brain.content.repository import PRIORITIES, STATUSES, STATUS_FA, TRANSITIONS
from ..deps import engine, orchestrator, require_site
from ..errors import ApiError

router = APIRouter(prefix="/sites/{site_id}/content", tags=["content"], dependencies=[Depends(require_site)])
Status = Literal["planned", "brief_ready", "writing", "review", "approved", "published"]
Priority = Literal["high", "medium", "low"]


class ContentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    target_keyword_id: int | None = None
    target_keyword: str | None = None
    topic: str | None = None
    cluster_id: str | None = None
    intent: str | None = None
    priority: Priority | None = None
    publish_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    publish_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    ai_provider: str | None = None
    ai_model: str | None = None
    url: str | None = None
    metadata: dict[str, Any] | None = None
    notes: str | None = None


class ContentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=300)
    target_keyword_id: int | None = None
    target_keyword: str | None = None
    topic: str | None = None
    cluster_id: str | None = None
    intent: str | None = None
    priority: Priority | None = None
    publish_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    publish_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    ai_provider: str | None = None
    ai_model: str | None = None
    url: str | None = None
    wp_post_id: int | None = None
    metadata: dict[str, Any] | None = None
    notes: str | None = None
    clear_date: bool = False


class Transition(BaseModel):
    status: Status
    note: str | None = None


class BriefRequest(BaseModel):
    use_ai: bool = False
    mark_ready: bool = True


def svc(eng: Engine = Depends(engine), orch=Depends(orchestrator)) -> ContentService:
    return ContentService(eng, orch)


def intel(eng: Engine = Depends(engine), orch=Depends(orchestrator)) -> ContentIntelligenceService:
    return ContentIntelligenceService(eng, orch)


class DraftCreate(BaseModel):
    body: str = Field(min_length=1)
    format: Literal["markdown", "html", "text"] = "markdown"
    title: str | None = None
    meta_description: str | None = None
    source: str = "user"
    author: str | None = None
    change_summary: str | None = None
    provenance: dict[str, Any] | None = None


class ReviewRequest(BaseModel):
    draft_id: int | None = None
    use_ai: bool = False


class InsightStatus(BaseModel):
    status: Literal["new", "accepted", "dismissed"]


class ScoringSettings(BaseModel):
    weights: dict[str, float] | None = None
    thresholds: dict[str, float] | None = None
    min_words: dict[str, int] | None = None
    min_internal_links: int | None = None
    review_gate: Literal["strict", "advisory"] | None = None


@router.get("/meta")
def meta() -> dict:
    return {"statuses": [{"key": s, "fa": STATUS_FA[s], "next": list(TRANSITIONS[s])} for s in STATUSES], "priorities": list(PRIORITIES)}


@router.get("")
def list_content(site_id: str, status: str | None = None, q: str | None = None, topic: str | None = None, cluster_id: str | None = None, priority: str | None = None,
                 date_from: str | None = None, date_to: str | None = None, sort: str = "updated_at", order: Literal["asc", "desc"] = "desc",
                 limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), s: ContentService = Depends(svc)) -> dict:
    rows, total = s.repo.list(site_id, status, q, topic, cluster_id, priority, date_from, date_to, sort, order, limit, offset)
    return {"items": s.enrich(rows), "total": total, "limit": limit, "offset": offset, "counts": s.repo.counts(site_id)}


@router.post("", status_code=201)
def create_content(site_id: str, body: ContentCreate, s: ContentService = Depends(svc)) -> dict:
    it = s.create(site_id, body.title, **body.model_dump(exclude_none=True, exclude={"title"}))
    return s.enrich([it])[0]


@router.post("/from-opportunity/{oid}", status_code=201)
def from_opportunity(site_id: str, oid: int, s: ContentService = Depends(svc)) -> dict:
    try:
        return s.enrich([s.create_from_opportunity(site_id, oid)])[0]
    except KeyError:
        raise HTTPException(404, "opportunity not found")


@router.get("/board")
def board(site_id: str, s: ContentService = Depends(svc)) -> dict:
    return s.board(site_id)


@router.get("/calendar")
def calendar(site_id: str, date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"), s: ContentService = Depends(svc)) -> dict:
    today = date.today()
    f = date_from or (today.replace(day=1) - timedelta(days=7)).isoformat()
    t = date_to or (today + timedelta(days=45)).isoformat()
    return s.calendar(site_id, f, t)


@router.post("/sync-graph")
def sync_graph(site_id: str, s: ContentService = Depends(svc)) -> dict:
    return s.sync_graph(site_id)


# ----------------------------------------------------------------------------- phase 7: drafts / score / review / settings / insights
@router.get("/settings/scoring")
def get_scoring_settings(site_id: str, i: ContentIntelligenceService = Depends(intel)) -> dict:
    return i.drafts.settings(site_id, "scoring")


@router.put("/settings/scoring")
def put_scoring_settings(site_id: str, body: ScoringSettings, i: ContentIntelligenceService = Depends(intel)) -> dict:
    cur = i.drafts.settings(site_id, "scoring")
    patch = body.model_dump(exclude_none=True)
    for k in ("weights", "thresholds", "min_words"):
        if k in patch:
            patch[k] = {**cur.get(k, {}), **patch[k]}
    return i.drafts.put_settings(site_id, "scoring", {**cur, **patch})


@router.get("/insights")
def insights(site_id: str, status: str | None = None, i: ContentIntelligenceService = Depends(intel)) -> list[dict]:
    """Learned content patterns (only from large samples). Accepting one writes it into Site Brain memory (human confirmation)."""
    return i.list_insights(site_id, status)


@router.patch("/insights/{iid}")
def set_insight(site_id: str, iid: int, body: InsightStatus, i: ContentIntelligenceService = Depends(intel)) -> dict:
    r = i.set_insight_status(site_id, iid, body.status)
    if not r:
        raise HTTPException(404, "insight not found")
    return r



@router.get("/analytics/overview")
def analytics_overview(site_id: str, eng: Engine = Depends(engine)) -> dict:
    """Latest 28d GSC performance per published content (from content_metrics snapshots)."""
    return ContentAnalytics(eng).overview(site_id)


@router.post("/analytics/snapshot")
def analytics_snapshot(site_id: str, eng: Engine = Depends(engine)) -> dict:
    """Take today's 7d/28d snapshots for every content item with a URL (from gsc_daily, fallback gsc_query_page)."""
    return ContentAnalytics(eng).snapshot(site_id)


@router.post("/analytics/learn")
def analytics_learn(site_id: str, min_n: int = Query(5, ge=2), eng: Engine = Depends(engine)) -> dict:
    """Derive insights from snapshots — only when every gate passes (min impressions/clicks/age, n ≥ min_n). Nothing is applied automatically."""
    return ContentAnalytics(eng).learn(site_id, min_n=min_n)


@router.get("/analytics/settings")
def analytics_settings(site_id: str, i: ContentIntelligenceService = Depends(intel)) -> dict:
    return i.drafts.settings(site_id, "analytics")


@router.put("/analytics/settings")
def put_analytics_settings(site_id: str, body: dict, i: ContentIntelligenceService = Depends(intel)) -> dict:
    cur = i.drafts.settings(site_id, "analytics")
    allowed = {k: v for k, v in body.items() if k in ("min_impressions", "min_clicks", "min_age_days", "windows")}
    return i.drafts.put_settings(site_id, "analytics", {**cur, **allowed})


@router.get("/{cid}/metrics")
def content_metrics_ep(site_id: str, cid: int, window: str = "28d", eng: Engine = Depends(engine)) -> list[dict]:
    return ContentAnalytics(eng).metrics(site_id, cid, window)


@router.get("/{cid}")
def get_content(site_id: str, cid: int, s: ContentService = Depends(svc)) -> dict:
    d = s.detail(site_id, cid)
    if not d:
        raise HTTPException(404, "content not found")
    return d


@router.patch("/{cid}")
def update_content(site_id: str, cid: int, body: ContentUpdate, s: ContentService = Depends(svc)) -> dict:
    if not s.repo.get(site_id, cid):
        raise HTTPException(404, "content not found")
    data = body.model_dump(exclude_none=True, exclude={"clear_date"})
    if body.clear_date:
        data["publish_date"] = None; data["publish_time"] = None
    try:
        it = s.repo.update(site_id, cid, **data)
    except WorkflowError as e:
        raise ApiError(409, str(e), code="invalid_transition")
    return s.enrich([it])[0]  # type: ignore[list-item]


@router.post("/{cid}/transition")
def transition(site_id: str, cid: int, body: Transition, s: ContentService = Depends(svc)) -> dict:
    """Human approval workflow. Forward one step or back; 'published' requires a URL. Never publishes anywhere."""
    try:
        ContentIntelligenceService(s.engine, None).check_gate(site_id, cid, body.status)
        it = s.repo.transition(site_id, cid, body.status, actor="user", note=body.note)
    except KeyError:
        raise HTTPException(404, "content not found")
    except WorkflowError as e:
        raise ApiError(409, str(e), code="invalid_transition", details={"allowed": list(TRANSITIONS.get((s.repo.get(site_id, cid) or {}).status if s.repo.get(site_id, cid) else "planned", ()))})
    return s.enrich([it])[0]


@router.delete("/{cid}")
def delete_content(site_id: str, cid: int, s: ContentService = Depends(svc)) -> dict:
    if not s.repo.delete(site_id, cid):
        raise HTTPException(404, "content not found")
    return {"deleted": cid}


@router.post("/{cid}/brief")
def generate_brief(site_id: str, cid: int, body: BriefRequest | None = None, s: ContentService = Depends(svc)) -> dict:
    body = body or BriefRequest()
    try:
        b = s.generate_brief(site_id, cid, use_ai=body.use_ai, mark_ready=body.mark_ready)
    except KeyError:
        raise HTTPException(404, "content not found")
    return b.to_dict()


@router.get("/{cid}/briefs")
def list_briefs(site_id: str, cid: int, s: ContentService = Depends(svc)) -> list[dict]:
    return [b.to_dict() for b in s.repo.briefs(site_id, cid)]


@router.get("/{cid}/events")
def events(site_id: str, cid: int, s: ContentService = Depends(svc)) -> list[dict]:
    return s.repo.events(site_id, cid)


@router.get("/{cid}/drafts")
def list_drafts(site_id: str, cid: int, i: ContentIntelligenceService = Depends(intel)) -> list[dict]:
    return [d.to_dict(with_body=False) for d in i.drafts.list(site_id, cid)]


@router.post("/{cid}/drafts", status_code=201)
def create_draft(site_id: str, cid: int, body: DraftCreate, i: ContentIntelligenceService = Depends(intel)) -> dict:
    """Every modification creates a new version (previous content, change summary, author/source, AI provenance kept)."""
    try:
        d = i.create_draft(site_id, cid, body.body, body.format, body.title, body.meta_description, body.source, body.author, body.change_summary, body.provenance)
    except KeyError:
        raise HTTPException(404, "content not found")
    return d.to_dict()


@router.get("/{cid}/drafts/{did}")
def get_draft(site_id: str, cid: int, did: int, i: ContentIntelligenceService = Depends(intel)) -> dict:
    d = i.drafts.get(site_id, did)
    if not d or d.content_id != cid:
        raise HTTPException(404, "draft not found")
    return d.to_dict()


@router.post("/{cid}/score")
def score_content(site_id: str, cid: int, draft_id: int | None = None, i: ContentIntelligenceService = Depends(intel)) -> dict:
    try:
        return i.score(site_id, cid, draft_id)
    except KeyError:
        raise ApiError(404, "no draft to score — create a draft first", code="not_found")


@router.post("/{cid}/review")
def review_content(site_id: str, cid: int, body: ReviewRequest | None = None, i: ContentIntelligenceService = Depends(intel)) -> dict:
    """Rules review (+ advisory AI when a real provider is routed). Sets draft.review_status ready|changes_requested."""
    body = body or ReviewRequest()
    try:
        return i.review(site_id, cid, body.draft_id, body.use_ai)
    except KeyError:
        raise ApiError(404, "no draft to review — create a draft first", code="not_found")


@router.get("/{cid}/intelligence")
def intelligence_history(site_id: str, cid: int, i: ContentIntelligenceService = Depends(intel)) -> dict:
    return i.history(site_id, cid)
