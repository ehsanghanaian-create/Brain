"""Phase 8.5 — Content Strategy Planner endpoints: /sites/{id}/content-plans/* (plans CRUD/bulk/transition, analysis, import/export/sources,
calendar/board, categories (WP sync read-only, brain, manual), keyword mapping, suggestions inbox, clusters, generation-job preparation,
publishing metadata (publishing disabled), insights, graph)."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from ...automation.queue import Job, JobQueue
from ...brain.content import ContentService, WorkflowError
from ...brain.planner import PlannerError, PlannerLearning, PlannerService
from ...brain.planner.repository import GEN_JOB_KINDS, KEYWORD_ROLES, PLAN_STATUSES
from ...db.repositories.sites import SitesRepository
from ..deps import engine, job_queue, orchestrator, require_site, sites_repo
from ..errors import ApiError

router = APIRouter(prefix="/sites/{site_id}/content-plans", tags=["content-plans"], dependencies=[Depends(require_site)])
ANALYZE_JOB_THRESHOLD = 200


def svc(eng: Engine = Depends(engine), orch=Depends(orchestrator)) -> PlannerService:
    return PlannerService(eng, ContentService(eng, orch))


class PlanBody(BaseModel):
    title: str | None = None
    url: str | None = None
    intent: str | None = None
    serp_intent: str | None = None
    page_type: str | None = None
    funnel_stage: str | None = None
    category_id: int | None = None
    category: str | None = None
    primary_keyword_id: int | None = None
    primary_keyword: str | None = None
    secondary_keywords: list[str] | None = None
    heading_structure: list[dict[str, Any]] | None = None
    seo_title: str | None = None
    meta_description: str | None = None
    topic_id: str | None = None
    content_cluster_id: int | None = None
    search_volume: int | None = None
    keyword_difficulty: float | None = None
    priority: str | None = None
    business_value: float | None = Field(default=None, ge=0, le=100)
    target_audience: str | None = None
    publish_date: str | None = None
    publish_time: str | None = None
    status: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] | None = None
    source: str | None = None

    def fields(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class BulkBody(BaseModel):
    ids: list[int] = Field(min_length=1)
    patch: dict[str, Any] = Field(default_factory=dict)


class IdsBody(BaseModel):
    ids: list[int] | None = None
    link_prep: bool = True


class TransitionBody(BaseModel):
    status: str
    note: str | None = None


class LinkItemBody(BaseModel):
    content_id: int | None = None


class BriefBody(BaseModel):
    use_ai: bool = False
    mark_ready: bool = True


class CategoryBody(BaseModel):
    name: str
    parent_id: int | None = None
    slug: str | None = None
    description: str | None = None


class CategoryPatch(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    description: str | None = None


class MappingSuggestBody(BaseModel):
    keyword_ids: list[int] | None = None
    limit: int = 100


class MappingApplyBody(BaseModel):
    items: list[dict[str, Any]] = Field(min_length=1)


class DecisionBody(BaseModel):
    status: Literal["accepted", "dismissed"]


class ClusterBody(BaseModel):
    name: str
    topic: str | None = None
    keyword_cluster_id: str | None = None
    category_id: int | None = None
    pillar_plan_id: int | None = None
    description: str | None = None


class SourceBody(BaseModel):
    name: str
    kind: Literal["google_sheet", "csv_url", "google_sheets_api"] = "google_sheet"
    url: str | None = None
    gid: str | None = None
    mapping: dict[str, str] | None = None
    key_columns: list[str] | None = None
    enabled: bool = True


class GenJobBody(BaseModel):
    kind: str = "article"
    params: dict[str, Any] = Field(default_factory=dict)


class PublishingBody(BaseModel):
    target: str | None = None
    wp_status: str | None = None
    scheduled_at: str | None = None
    author: str | None = None
    checklist: list[dict[str, Any]] | None = None
    cta: str | None = None
    notes: str | None = None
    canonical: str | None = None
    og_title: str | None = None


class KeywordsBody(BaseModel):
    items: list[dict[str, Any]]


def _err(e: Exception):
    if isinstance(e, WorkflowError):
        raise ApiError(409, str(e), code="invalid_transition")
    if isinstance(e, PlannerError):
        raise ApiError(422, str(e), code="validation_error")
    raise e


# ---------------------------------------------------------------------------- meta / list / crud
@router.get("/meta")
def meta(site_id: str, s: PlannerService = Depends(svc)) -> dict:
    return s.meta()


@router.get("")
def list_plans(site_id: str, status: str | None = None, category_id: int | None = None, page_type: str | None = None, intent: str | None = None, priority: str | None = None,
               cluster_id: str | None = None, content_cluster_id: int | None = None, q: str | None = None, date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"),
               has_item: bool | None = None, unscheduled: bool | None = None, sort: str = "updated_at", order: str = Query("desc", pattern="^(asc|desc)$"),
               limit: int = Query(200, ge=1, le=2000), offset: int = Query(0, ge=0), s: PlannerService = Depends(svc)) -> dict:
    items, total = s.repo.list_plans(site_id, status, category_id, page_type, intent, priority, cluster_id, content_cluster_id, q, date_from, date_to, has_item, unscheduled, None, sort, order, limit, offset)
    return {"items": s.enrich(items), "total": total, "counts": s.repo.counts(site_id)}


@router.post("", status_code=201)
def create_plan(site_id: str, body: PlanBody, analyze: bool = True, s: PlannerService = Depends(svc)) -> dict:
    try:
        return s.create(site_id, body.fields(), analyze=analyze)
    except (PlannerError, WorkflowError) as e:
        _err(e)


@router.post("/bulk")
def bulk(site_id: str, body: BulkBody, s: PlannerService = Depends(svc)) -> dict:
    return s.bulk(site_id, body.ids, body.patch)


@router.post("/bulk-delete")
def bulk_delete(site_id: str, body: IdsBody, with_item: bool = False, s: PlannerService = Depends(svc)) -> dict:
    return {"deleted": [pid for pid in (body.ids or []) if s.delete(site_id, pid, with_item)]}


@router.post("/analyze")
def analyze_all(site_id: str, body: IdsBody | None = None, s: PlannerService = Depends(svc), q: JobQueue = Depends(job_queue), response: Response = None) -> dict:  # type: ignore[assignment]
    body = body or IdsBody()
    n = len(body.ids) if body.ids else s.repo.counts(site_id)["total"]
    if n > ANALYZE_JOB_THRESHOLD:
        run = q.enqueue(Job(type="planner_analyze", payload={"site_id": site_id, "ids": body.ids, "link_prep": body.link_prep}, site_id=site_id))
        response.status_code = 202
        return {"mode": "job", "run_id": run.run_id, "type": "planner_analyze", "status": run.status, "plans": n}
    return {"mode": "sync", **s.analyze_all(site_id, body.ids, body.link_prep)}


@router.post("/backfill")
def backfill(site_id: str, s: PlannerService = Depends(svc)) -> dict:
    return s.backfill(site_id)


@router.post("/sync-graph")
def sync_graph(site_id: str, s: PlannerService = Depends(svc)) -> dict:
    return s.graph.sync(site_id)


@router.post("/sync-items")
def sync_items(site_id: str, s: PlannerService = Depends(svc)) -> dict:
    return {"synced": s.sync_all_from_items(site_id)}


# ---------------------------------------------------------------------------- calendar / board / graph
@router.get("/calendar")
def calendar(site_id: str, date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"), category_id: int | None = None, status: str | None = None,
             priority: str | None = None, s: PlannerService = Depends(svc)) -> dict:
    return s.calendar(site_id, date_from, date_to, category_id, status, priority)


@router.get("/board")
def board(site_id: str, category_id: int | None = None, s: PlannerService = Depends(svc)) -> dict:
    return s.board(site_id, category_id)


@router.get("/graph")
def graph(site_id: str, plan_id: int | None = None, category_id: int | None = None, s: PlannerService = Depends(svc)) -> dict:
    return s.graph_view(site_id, plan_id, category_id)


# ---------------------------------------------------------------------------- import / export / sources
@router.get("/import/template.csv")
def import_template(site_id: str) -> Response:
    return Response(PlannerService.template(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=content-plans-template.csv"})


@router.post("/import")
async def import_plans(site_id: str, file: UploadFile = File(...), dry_run: bool = Form(False), mapping: str | None = Form(None), key_columns: str | None = Form(None),
                       s: PlannerService = Depends(svc)) -> dict:
    """Upload CSV / TSV / XLSX (Excel or Google-Sheet export). `dry_run=true` returns mapping + preview only. `mapping` = JSON {column: field}."""
    import json
    data = await file.read()
    if not data:
        raise ApiError(422, "فایل خالی است", code="validation_error")
    mp = json.loads(mapping) if mapping else None
    keys = [k for k in (key_columns or "").split(",") if k] or None
    try:
        return s.import_table(site_id, data, file.filename, mp, dry_run, keys)
    except Exception as e:  # noqa: BLE001
        raise ApiError(422, f"خواندن فایل ناموفق بود: {e}", code="validation_error")


@router.get("/imports")
def imports(site_id: str, s: PlannerService = Depends(svc)) -> list[dict]:
    return s.repo.list_imports(site_id)


@router.get("/export.{fmt}")
def export_plans(site_id: str, fmt: Literal["csv", "xlsx"], columns: str | None = None, status: str | None = None, category_id: int | None = None, page_type: str | None = None,
                 intent: str | None = None, priority: str | None = None, q: str | None = None, s: PlannerService = Depends(svc)) -> Response:
    data, mt, name = s.export(site_id, fmt, [c for c in (columns or "").split(",") if c] or None, status=status, category_id=category_id, page_type=page_type, intent=intent, priority=priority, q=q)
    return Response(data, media_type=mt, headers={"Content-Disposition": f"attachment; filename={name}"})


@router.get("/sources")
def sources(site_id: str, s: PlannerService = Depends(svc)) -> list[dict]:
    return s.repo.list_sources(site_id)


@router.post("/sources", status_code=201)
def create_source(site_id: str, body: SourceBody, s: PlannerService = Depends(svc)) -> dict:
    return s.repo.save_source(site_id, None, **{k: v for k, v in body.model_dump().items() if v is not None})


@router.patch("/sources/{sid}")
def patch_source(site_id: str, sid: int, body: SourceBody, s: PlannerService = Depends(svc)) -> dict:
    if not s.repo.get_source(site_id, sid):
        raise HTTPException(404, "source not found")
    return s.repo.save_source(site_id, sid, **{k: v for k, v in body.model_dump().items() if v is not None})


@router.delete("/sources/{sid}")
def delete_source(site_id: str, sid: int, s: PlannerService = Depends(svc)) -> dict:
    if not s.repo.delete_source(site_id, sid):
        raise HTTPException(404, "source not found")
    return {"deleted": sid}


@router.post("/sources/{sid}/sync")
def sync_source(site_id: str, sid: int, dry_run: bool = False, s: PlannerService = Depends(svc)) -> dict:
    try:
        return s.sync_source(site_id, sid, dry_run)
    except PlannerError as e:
        _err(e)


# ---------------------------------------------------------------------------- categories
@router.get("/categories")
def categories(site_id: str, tree: bool = False, source: str | None = None, s: PlannerService = Depends(svc)) -> list[dict]:
    return s.repo.category_tree(site_id, source) if tree else s.repo.list_categories(site_id, source)


@router.post("/categories/sync")
def categories_sync(site_id: str, brain: bool = True, min_keywords: int = 3, s: PlannerService = Depends(svc), sites: SitesRepository = Depends(sites_repo)) -> dict:
    """WordPress categories via REST (read-only) + Brain topic categories from keyword clusters. 409 when WordPress is not configured (brain part still runs)."""
    site = sites.get(site_id)
    out: dict[str, Any] = {}
    wp_error = None
    if site and site.wp_url:
        try:
            out["wordpress"] = s.cats.sync_wordpress(site_id, site.wp_url)
        except Exception as e:  # noqa: BLE001
            wp_error = str(e)
    else:
        wp_error = "wordpress_not_configured"
    if brain:
        out["brain"] = s.cats.sync_brain(site_id, min_keywords)
    out["analysis"] = s.cats.analyze(site_id)
    s.graph.sync(site_id)
    if wp_error and not brain:
        raise ApiError(409, "آدرس وردپرس برای این سایت تنظیم نشده یا در دسترس نیست", code="wordpress_not_configured", details={"error": wp_error})
    out["wordpress_error"] = wp_error
    return out


@router.post("/categories/analyze")
def categories_analyze(site_id: str, s: PlannerService = Depends(svc)) -> dict:
    return s.cats.analyze(site_id)


@router.get("/categories/suggest")
def categories_suggest(site_id: str, keyword: str | None = None, keyword_id: int | None = None, plan_id: int | None = None, s: PlannerService = Depends(svc)) -> dict:
    if not (keyword or keyword_id or plan_id):
        raise ApiError(422, "keyword, keyword_id یا plan_id لازم است", code="validation_error")
    return s.cats.suggest(site_id, keyword, keyword_id, plan_id)


@router.post("/categories", status_code=201)
def create_category(site_id: str, body: CategoryBody, s: PlannerService = Depends(svc)) -> dict:
    return s.repo.upsert_category(site_id, "manual", body.name, slug=body.slug, parent_id=body.parent_id, description=body.description)


@router.get("/categories/{cid}")
def category_detail(site_id: str, cid: int, s: PlannerService = Depends(svc)) -> dict:
    c = s.repo.get_category(site_id, cid)
    if not c:
        raise HTTPException(404, "category not found")
    plans, _ = s.repo.list_plans(site_id, category_id=cid, limit=500)
    c["plans"] = s.enrich(plans)
    c["children"] = [x for x in s.repo.list_categories(site_id) if x["parent_id"] == cid]
    return c


@router.patch("/categories/{cid}")
def patch_category(site_id: str, cid: int, body: CategoryPatch, s: PlannerService = Depends(svc)) -> dict:
    c = s.repo.update_category(site_id, cid, **{k: v for k, v in body.model_dump().items() if v is not None})
    if not c:
        raise HTTPException(404, "category not found")
    return c


@router.delete("/categories/{cid}")
def delete_category(site_id: str, cid: int, s: PlannerService = Depends(svc)) -> dict:
    c = s.repo.get_category(site_id, cid)
    if not c:
        raise HTTPException(404, "category not found")
    if c["source"] == "wordpress":
        raise ApiError(409, "دسته‌های وردپرس فقط‌خواندنی هستند (از وردپرس همگام می‌شوند)", code="read_only")
    s.repo.delete_category(site_id, cid)
    return {"deleted": cid}


# ---------------------------------------------------------------------------- keyword mapping / suggestions / clusters / insights
@router.get("/keyword-mapping")
def keyword_mapping(site_id: str, status: str = Query("unmapped", pattern="^(unmapped|mapped|all)$"), q: str | None = None, limit: int = 300, s: PlannerService = Depends(svc)) -> dict:
    return s.mapper.overview(site_id, status, q, limit)


@router.post("/keyword-mapping/suggest")
def keyword_mapping_suggest(site_id: str, body: MappingSuggestBody | None = None, s: PlannerService = Depends(svc)) -> dict:
    body = body or MappingSuggestBody()
    return s.mapper.suggest(site_id, body.keyword_ids, body.limit)


@router.post("/keyword-mapping/apply")
def keyword_mapping_apply(site_id: str, body: MappingApplyBody, s: PlannerService = Depends(svc)) -> dict:
    for it in body.items:
        if it.get("role") and it["role"] not in KEYWORD_ROLES:
            raise ApiError(422, f"نقش نامعتبر: {it['role']}", code="validation_error")
    return s.mapper.apply(site_id, body.items, s)


@router.get("/suggestions")
def suggestions(site_id: str, status: str | None = "new", kind: str | None = None, s: PlannerService = Depends(svc)) -> list[dict]:
    return s.suggestions(site_id, status or "new", kind)


@router.patch("/suggestions/{rid}")
def decide_suggestion(site_id: str, rid: int, body: DecisionBody, s: PlannerService = Depends(svc)) -> dict:
    try:
        out = s.decide_suggestion(site_id, rid, body.status)
    except PlannerError as e:
        _err(e)
    if not out:
        raise HTTPException(404, "suggestion not found")
    return out


@router.get("/clusters")
def clusters(site_id: str, s: PlannerService = Depends(svc)) -> list[dict]:
    return s.repo.list_clusters(site_id)


@router.post("/clusters", status_code=201)
def create_cluster(site_id: str, body: ClusterBody, s: PlannerService = Depends(svc)) -> dict:
    return s.repo.upsert_cluster(site_id, body.name, None, **{k: v for k, v in body.model_dump().items() if k != "name" and v is not None})


@router.patch("/clusters/{cid}")
def patch_cluster(site_id: str, cid: int, body: ClusterBody, s: PlannerService = Depends(svc)) -> dict:
    return s.repo.upsert_cluster(site_id, body.name, cid, **{k: v for k, v in body.model_dump().items() if k != "name" and v is not None})


@router.delete("/clusters/{cid}")
def delete_cluster(site_id: str, cid: int, s: PlannerService = Depends(svc)) -> dict:
    if not s.repo.delete_cluster(site_id, cid):
        raise HTTPException(404, "cluster not found")
    return {"deleted": cid}


@router.get("/insights")
def insights(site_id: str, status: str | None = None, eng: Engine = Depends(engine)) -> list[dict]:
    return PlannerLearning(eng).list(site_id, status)


@router.post("/insights/learn")
def insights_learn(site_id: str, min_n: int = 5, eng: Engine = Depends(engine)) -> dict:
    return PlannerLearning(eng).learn(site_id, min_n=min_n)


@router.patch("/insights/{iid}")
def insight_status(site_id: str, iid: int, body: DecisionBody, eng: Engine = Depends(engine)) -> dict:
    out = PlannerLearning(eng).set_status(site_id, iid, body.status)
    if not out:
        raise HTTPException(404, "insight not found")
    return out


@router.get("/generation-jobs")
def generation_jobs(site_id: str, plan_id: int | None = None, s: PlannerService = Depends(svc)) -> list[dict]:
    return s.repo.list_generation_jobs(site_id, plan_id)


# ---------------------------------------------------------------------------- single plan (keep after static routes)
@router.get("/{pid}")
def get_plan(site_id: str, pid: int, s: PlannerService = Depends(svc)) -> dict:
    d = s.detail(site_id, pid)
    if not d:
        raise HTTPException(404, "plan not found")
    return d


@router.put("/{pid}")
@router.patch("/{pid}")
def update_plan(site_id: str, pid: int, body: PlanBody, s: PlannerService = Depends(svc)) -> dict:
    try:
        d = s.update(site_id, pid, body.fields())
    except (PlannerError, WorkflowError) as e:
        _err(e)
    if not d:
        raise HTTPException(404, "plan not found")
    return d


@router.delete("/{pid}")
def delete_plan(site_id: str, pid: int, with_item: bool = False, s: PlannerService = Depends(svc)) -> dict:
    if not s.delete(site_id, pid, with_item):
        raise HTTPException(404, "plan not found")
    return {"deleted": pid, "with_item": with_item}


@router.post("/{pid}/transition")
def transition(site_id: str, pid: int, body: TransitionBody, s: PlannerService = Depends(svc)) -> dict:
    if body.status not in PLAN_STATUSES:
        raise ApiError(422, f"وضعیت نامعتبر: {body.status}", code="validation_error")
    try:
        return s.transition(site_id, pid, body.status, note=body.note)
    except (PlannerError, WorkflowError) as e:
        _err(e)


@router.post("/{pid}/content-item")
def link_item(site_id: str, pid: int, body: LinkItemBody | None = None, s: PlannerService = Depends(svc)) -> dict:
    try:
        return s.ensure_item(site_id, pid, content_id=(body.content_id if body else None))
    except PlannerError as e:
        _err(e)


@router.post("/{pid}/brief")
def brief(site_id: str, pid: int, body: BriefBody | None = None, s: PlannerService = Depends(svc)) -> dict:
    body = body or BriefBody()
    try:
        return s.brief(site_id, pid, body.use_ai, body.mark_ready)
    except PlannerError as e:
        _err(e)


@router.post("/{pid}/analyze")
def analyze_plan(site_id: str, pid: int, link_prep: bool = True, s: PlannerService = Depends(svc)) -> dict:
    out = s.analyze_plan(site_id, pid, link_prep=link_prep)
    if not out:
        raise HTTPException(404, "plan not found")
    return out


@router.post("/{pid}/link-prep")
def link_prep(site_id: str, pid: int, s: PlannerService = Depends(svc)) -> dict:
    from ...brain.planner.context import build_planner_context
    p = s.repo.get_plan(site_id, pid)
    if not p:
        raise HTTPException(404, "plan not found")
    ctx = build_planner_context(s.engine, site_id)
    res = s.links.prepare(ctx, p)
    s.repo.update_plan(site_id, pid, actor="user", event="links_prepared", link_targets=res["inbound"] + res["outbound"])
    return res


@router.get("/{pid}/keywords")
def plan_keywords(site_id: str, pid: int, s: PlannerService = Depends(svc)) -> list[dict]:
    return s.repo.plan_keywords(site_id, pid)


@router.post("/{pid}/keywords")
def set_plan_keywords(site_id: str, pid: int, body: KeywordsBody, s: PlannerService = Depends(svc)) -> list[dict]:
    if not s.repo.get_plan(site_id, pid):
        raise HTTPException(404, "plan not found")
    for it in body.items:
        if it.get("role") and it["role"] not in KEYWORD_ROLES:
            raise ApiError(422, f"نقش نامعتبر: {it['role']}", code="validation_error")
    return s.repo.set_keywords(site_id, pid, body.items)


@router.delete("/{pid}/keywords/{kid}")
def remove_plan_keyword(site_id: str, pid: int, kid: int, s: PlannerService = Depends(svc)) -> dict:
    s.repo.remove_keyword(site_id, pid, kid)
    return {"removed": kid}


@router.get("/{pid}/events")
def plan_events(site_id: str, pid: int, s: PlannerService = Depends(svc)) -> list[dict]:
    return s.repo.events(site_id, pid)


@router.get("/{pid}/recommendations")
def plan_recommendations(site_id: str, pid: int, s: PlannerService = Depends(svc)) -> list[dict]:
    return s.repo.list_recommendations(site_id, status=None, plan_id=pid)


@router.post("/{pid}/generation-jobs", status_code=201)
def prepare_generation(site_id: str, pid: int, body: GenJobBody | None = None, s: PlannerService = Depends(svc)) -> dict:
    """Prepare (not run) an AI generation job: plan → generation_job → content_item → draft. Execution stays in AI Studio with human approval."""
    body = body or GenJobBody()
    if body.kind not in GEN_JOB_KINDS:
        raise ApiError(422, f"نوع کار نامعتبر: {body.kind}", code="validation_error", details={"allowed": list(GEN_JOB_KINDS)})
    try:
        return s.prepare_generation(site_id, pid, body.kind, body.params)
    except PlannerError as e:
        _err(e)


@router.put("/{pid}/publishing-metadata")
def publishing(site_id: str, pid: int, body: PublishingBody, s: PlannerService = Depends(svc)) -> dict:
    """Publishing metadata only — publishing is disabled; nothing is sent to WordPress."""
    d = s.set_publishing(site_id, pid, {k: v for k, v in body.model_dump().items() if v is not None})
    if not d:
        raise HTTPException(404, "plan not found")
    return d
