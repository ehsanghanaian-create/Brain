from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine, inspect, text
from ...automation.queue import Job, JobQueue

from ...common.config import PROJECT_ROOT
from ...db.repositories import SitesRepository
from ...db.repositories.sites import Site
from ..deps import engine, job_queue, require_site, sites_repo
from ..errors import ApiError
from ..schemas import SiteCreate, SiteUpdate

router = APIRouter(prefix="/sites", tags=["sites"])


def _workspace_for(site: Site) -> str:
    from ...sites import SiteInitializer  # local import (module also imported below for the phase-3 endpoints)
    return SiteInitializer(None, PROJECT_ROOT).init_workspace(site)["path"]  # type: ignore[arg-type]


@router.get("")
def list_sites(repo: SitesRepository = Depends(sites_repo)) -> list[dict]:
    return [s.to_dict() for s in repo.list()]


@router.post("", status_code=201)
def create_site(body: SiteCreate, repo: SitesRepository = Depends(sites_repo)) -> dict:
    if repo.get(body.site_id):
        raise HTTPException(409, f"site '{body.site_id}' already exists")
    site = Site(site_id=body.site_id, name=body.name, canonical_url=str(body.canonical_url),
                wp_url=str(body.wp_url) if body.wp_url else None, language=body.language, country=body.country,
                business_type=body.business_type, gsc_property=body.gsc_property, ga4_property=body.ga4_property,
                mode=body.mode, timezone=body.timezone)
    site.workspace_path = _workspace_for(site)
    return repo.save(site).to_dict()


@router.get("/{site_id}")
def get_site(site: Site = Depends(require_site)) -> dict:
    return site.to_dict()


@router.patch("/{site_id}")
def update_site(body: SiteUpdate, site: Site = Depends(require_site), repo: SitesRepository = Depends(sites_repo)) -> dict:
    data = {k: (str(v) if k == "wp_url" else v) for k, v in body.model_dump(exclude_none=True).items()}
    if not site.workspace_path:
        data["workspace_path"] = _workspace_for(site)
    return repo.set_fields(site.site_id, **data).to_dict()


# tables that reference sites(site_id); a site with data is only deleted with ?force=true
# dependency order: dependents first (entity_mentions→entities, post_terms→posts, gsc_query_page→queries, graph_edges→graph_nodes)
_CHILD_TABLES = ("content_plan_generation_jobs", "content_plan_recommendations", "content_plan_sources", "content_plan_imports", "content_plan_events", "content_plan_keywords", "content_plans", "content_clusters", "content_categories",
                 "generation_runs", "draft_feedback", "memory_snapshots", "link_suggestions", "link_page_stats", "link_patterns", "content_scores", "content_reviews", "content_drafts", "content_metrics", "content_insights", "site_settings", "content_briefs", "content_events", "content_items", "keyword_opportunities", "keywords", "keyword_clusters", "keyword_imports",
                 "entity_mentions", "post_terms", "links", "gsc_query_page", "gsc_daily", "graph_edges", "seo_problems",
                 "seo_opportunities", "media", "schemas", "entities", "queries", "pages", "posts", "categories", "tags",
                 "taxonomies", "graph_nodes", "site_memory", "site_connections", "crawl_runs", "sync_runs")


def _related_counts(eng: Engine, site_id: str) -> dict[str, int]:
    out: dict[str, int] = {}
    existing = set(inspect(eng).get_table_names())
    with eng.connect() as cx:
        for t in _CHILD_TABLES:
            if t not in existing:
                continue
            n = cx.execute(text(f"SELECT COUNT(*) FROM {t} WHERE site_id = :s"), {"s": site_id}).scalar() or 0
            if n:
                out[t] = int(n)
    return out


@router.delete("/{site_id}", status_code=200)
def delete_site(site_id: str, force: bool = Query(False, description="also delete all site data (graph, GSC, crawl, memory)"),
                site: Site = Depends(require_site), eng: Engine = Depends(engine)) -> dict:
    """Delete a site. Refuses (409 `site_has_data`) when related rows exist unless force=true.
    Files in the workspace directory are never deleted by the API."""
    related = _related_counts(eng, site_id)
    if related and not force:
        raise ApiError(409, f"site '{site_id}' has data in {len(related)} tables; pass force=true to delete everything",
                       code="site_has_data", details=related)
    existing = set(inspect(eng).get_table_names())
    with eng.begin() as cx:
        if "generation_artifacts" in existing:   # keyed by run_id, not site_id
            cx.execute(text("DELETE FROM generation_artifacts WHERE run_id IN (SELECT run_id FROM generation_runs WHERE site_id = :s)"), {"s": site_id})
        for t in _CHILD_TABLES:
            if t in existing:
                cx.execute(text(f"DELETE FROM {t} WHERE site_id = :s"), {"s": site_id})
        cx.execute(text("DELETE FROM sites WHERE site_id = :s"), {"s": site_id})
    return {"deleted": site_id, "related_rows_deleted": related, "workspace_kept": site.workspace_path}


# ----------------------------------------------------------------------------- phase 3: connections + initialisation
from ...connections import ConnectionsService  # noqa: E402
from ...sites import SiteInitializer  # noqa: E402
from ..schemas import ConnectionTestRequest  # noqa: E402


def connections_service(eng: Engine = Depends(engine)) -> ConnectionsService:
    return ConnectionsService(eng)


@router.get("/{site_id}/connections")
def get_connections(site_id: str, site: Site = Depends(require_site), svc: ConnectionsService = Depends(connections_service)) -> dict:
    """Last known status per connection kind (gsc | ga4 | wordpress) + what is configured on the site."""
    from ...wordpress.auth import auth_status
    return {"site_id": site_id,
            "configured": {"gsc": site.gsc_property, "ga4": site.ga4_property, "wordpress": site.wp_url},
            "status": svc.status(site_id),
            "wordpress_auth": auth_status(site_id)}        # additive: configured/username/key_hint/source — never the password


@router.post("/{site_id}/connections/{kind}/test")
def test_connection(site_id: str, kind: str, body: ConnectionTestRequest | None = None, site: Site = Depends(require_site),
                    svc: ConnectionsService = Depends(connections_service), repo: SitesRepository = Depends(sites_repo),
                    eng: Engine = Depends(engine), q: JobQueue = Depends(job_queue)) -> dict:
    """Run a read-only permission test. If `property` is given and the test passes, it is stored on the site."""
    body = body or ConnectionTestRequest()
    if kind == "gsc":
        res = svc.test_gsc(site_id, body.property or site.gsc_property)
        if res.ok and body.property and body.property != site.gsc_property:
            repo.set_fields(site_id, gsc_property=res.detail.get("property") or body.property)
        # production workflow: a verified GSC connection queues the sync → opportunities → snapshot → graph pipeline (never inline)
        if res.ok and body.auto_sync:
            try:
                res.detail["sync_job"] = _queue_gsc_sync(site_id, eng, q, days=None, reason="connection_test")
            except Exception as e:  # noqa: BLE001 — the connection result itself must still be returned
                res.detail["sync_job"] = {"status": "not_queued", "error": f"{e.__class__.__name__}: {str(e)[:120]}"}
    elif kind == "ga4":
        res = svc.test_ga4(site_id, body.property or site.ga4_property)
        if res.ok and body.property and body.property != site.ga4_property:
            repo.set_fields(site_id, ga4_property=res.detail.get("property") or body.property)
        # production workflow: a verified GA4 connection queues the sync → snapshot → graph pipeline (never inline)
        if res.ok and body.auto_sync:
            try:
                res.detail["sync_job"] = _queue_ga4_sync(site_id, eng, q, days=None, reason="connection_test")
            except Exception as e:  # noqa: BLE001 — the connection result itself must still be returned
                res.detail["sync_job"] = {"status": "not_queued", "error": f"{e.__class__.__name__}: {str(e)[:120]}"}
    elif kind == "wordpress":
        from ...wordpress.auth import clear_site_auth, save_site_auth
        if body.clear_wp_credentials:
            clear_site_auth(site_id)
        res = svc.test_wordpress(site_id, body.property or site.wp_url, body.wp_username, body.wp_app_password)
        normalized = res.detail.get("site_url") if res.ok else None
        if normalized and normalized != site.wp_url:
            repo.set_fields(site_id, wp_url=normalized)
        # persist the Application Password (SecretStore only) when the identity check succeeded with the supplied credentials
        if body.wp_username and body.wp_app_password and (res.detail.get("auth") or {}).get("status") == "ok":
            save_site_auth(site_id, body.wp_username, body.wp_app_password)
            res.detail["auth"]["stored"] = True
        # production workflow: a successful (public) connection queues the WordPress → sync → graph pipeline (never inline)
        if res.ok and body.auto_sync:
            try:
                res.detail["sync_job"] = _queue_wordpress_sync(site_id, eng, q, stage="full", crawl=True, max_urls=None, reason="connection_test")
            except Exception as e:  # noqa: BLE001 — the connection result itself must still be returned
                res.detail["sync_job"] = {"status": "not_queued", "error": f"{e.__class__.__name__}: {str(e)[:120]}"}
    else:
        raise ApiError(404, f"unknown connection kind '{kind}'", code="not_found", details={"kinds": ["gsc", "ga4", "wordpress"]})
    return res.to_dict()


@router.get("/{site_id}/integrations")
def integrations(site_id: str, site: Site = Depends(require_site), eng: Engine = Depends(engine)) -> dict:
    """Integration Center aggregation — one standard block per integration, read ONLY from the existing tables
    (site_connections · sync_runs · sites) plus the live counters the pipelines already expose. No new state."""
    import json as _json
    from ...gsc.pipeline import GscPipeline
    from ...wordpress.orchestrator import WordPressSyncOrchestrator

    with eng.connect() as cx:
        conn_rows = {r[0]: {"status": r[1], "tested_at": r[2], "detail": r[3]} for r in
                     cx.execute(text("SELECT kind, status, tested_at, detail FROM site_connections WHERE site_id=:s"), {"s": site_id}).all()}

    def connection(kind: str) -> dict:
        r = conn_rows.get(kind)
        if not r:
            return {"status": "never", "tested_at": None, "detail": {}}
        try:
            detail = _json.loads(r["detail"]) if r["detail"] else {}
        except ValueError:
            detail = {}
        return {"status": r["status"], "tested_at": r["tested_at"], "detail": detail}

    def sync_block(st: dict | None, coverage: dict) -> dict:
        st = st or {}
        return {"status": st.get("status", "never"), "last_run": st.get("finished_at") or st.get("started_at"),
                "progress": st.get("progress", 0), "step": st.get("step"), "step_fa": st.get("step_fa"),
                "run_id": st.get("run_id"), "coverage": coverage, "error": (st.get("errors") or [None])[-1] if st.get("errors") else None}

    wp = WordPressSyncOrchestrator(eng)
    gsc = GscPipeline(eng)
    from ...connections.service import GA4_SCOPE, GSC_SCOPE, _token_info
    from ...ga4.pipeline import Ga4Pipeline as _Ga4Pipeline
    _tok = _token_info()
    gsc_authorized = bool(_tok.get("present") and GSC_SCOPE in (_tok.get("scopes") or []))
    ga4_authorized = bool(gsc_authorized and GA4_SCOPE in (_tok.get("scopes") or []))
    _ga4_pipe = _Ga4Pipeline(eng)
    out = [
        {"kind": "wordpress", "label": "وردپرس", "connection": connection("wordpress"),
         "sync": sync_block(wp.latest(site_id), wp.counts(site_id)),
         "configured": bool(site.wp_url), "property": site.wp_url,
         "actions": ["test"] + (["sync", "rebuild"] if site.wp_url else [])},
        {"kind": "gsc", "label": "Google Search Console", "connection": connection("gsc"),
         "sync": sync_block(gsc.latest(site_id), gsc.coverage(site_id)),
         "configured": bool(site.gsc_property), "property": site.gsc_property, "authorized": gsc_authorized,
         "actions": ["test"] + (["sync"] if site.gsc_property and gsc_authorized else [])},
        {"kind": "ga4", "label": "Google Analytics 4", "connection": connection("ga4"),
         "sync": sync_block(_ga4_pipe.latest(site_id), _ga4_pipe.coverage(site_id)),
         "configured": bool(site.ga4_property), "property": site.ga4_property, "authorized": ga4_authorized,
         "actions": ["test"] + (["sync"] if site.ga4_property and ga4_authorized else [])},
    ]
    return {"site_id": site_id, "integrations": out}


@router.post("/{site_id}/initialize")
def initialize_site(site_id: str, site: Site = Depends(require_site), eng: Engine = Depends(engine),
                    repo: SitesRepository = Depends(sites_repo)) -> dict:
    """Wizard step 3: workspace + site memory + graph namespace (idempotent)."""
    init = SiteInitializer(eng, PROJECT_ROOT)
    out = init.initialize(site)
    if site.workspace_path != out["workspace"]["path"]:
        repo.set_fields(site_id, workspace_path=out["workspace"]["path"])
    return out


# --------------------------------------------------------------------------- WordPress → sync → graph pipeline (wiring of existing components)
def _queue_wordpress_sync(site_id: str, eng: Engine, q: JobQueue, stage: str, crawl: bool, max_urls: int | None, reason: str) -> dict:
    from ...wordpress.orchestrator import WordPressSyncOrchestrator
    orch = WordPressSyncOrchestrator(eng)
    if orch.is_running(site_id):
        cur = orch.latest(site_id) or {}
        return {"status": "already_running", "run_id": cur.get("run_id"), "job_id": cur.get("job_id"), "step": cur.get("step")}
    st = orch.create(site_id, stage=stage)
    run = q.enqueue(Job(type="wordpress_sync", payload={"site_id": site_id, "run_id": st.run_id, "stage": stage, "crawl": crawl, "max_urls": max_urls, "reason": reason}, site_id=site_id))
    orch.attach_job(st.run_id, run.run_id)
    return {"status": "queued", "job_id": run.run_id, "run_id": st.run_id, "stage": stage}


class WordPressSyncStart(BaseModel):
    crawl: bool = True
    max_urls: int | None = Field(default=None, ge=1, le=5000)


@router.post("/{site_id}/wordpress/sync", status_code=202)
def wordpress_sync_start(site_id: str, body: WordPressSyncStart | None = None, site: Site = Depends(require_site), eng: Engine = Depends(engine), q: JobQueue = Depends(job_queue)) -> dict:
    """Queue the full pipeline: categories → pages → posts → taxonomies → category intelligence → crawl (enrichment) → build graph. Never inline."""
    body = body or WordPressSyncStart()
    if not site.wp_url:
        raise ApiError(409, "آدرس وردپرس برای این سایت تنظیم نشده است — ابتدا اتصال وردپرس را تست کنید", code="wordpress_not_configured")
    return _queue_wordpress_sync(site_id, eng, q, stage="full", crawl=body.crawl, max_urls=body.max_urls, reason="manual")


@router.get("/{site_id}/wordpress/sync/status")
def wordpress_sync_status(site_id: str, site: Site = Depends(require_site), eng: Engine = Depends(engine), q: JobQueue = Depends(job_queue)) -> dict:
    """Latest pipeline run (persisted in sync_runs): status · step · progress · started/finished · items · errors + current table/graph counts."""
    from ...wordpress.orchestrator import WordPressSyncOrchestrator
    return {"site_id": site_id, "wp_url": site.wp_url, **WordPressSyncOrchestrator(eng).status(site_id, q)}


@router.post("/{site_id}/graph/rebuild", status_code=202)
def graph_rebuild(site_id: str, site: Site = Depends(require_site), eng: Engine = Depends(engine), q: JobQueue = Depends(job_queue)) -> dict:
    """Manual graph rebuild from the data already synced (WordPress pages/posts = source of truth; crawl/keywords/content/planner layers re-applied)."""
    return _queue_wordpress_sync(site_id, eng, q, stage="graph_only", crawl=False, max_urls=None, reason="graph_rebuild")


# --------------------------------------------------------------------------- GSC → sync → graph pipeline (wiring of existing components)
def _queue_gsc_sync(site_id: str, eng: Engine, q: JobQueue, days: int | None, reason: str) -> dict:
    from ...gsc.pipeline import GscPipeline
    pipe = GscPipeline(eng)
    if pipe.is_running(site_id):
        cur = pipe.latest(site_id) or {}
        return {"status": "already_running", "run_id": cur.get("run_id"), "job_id": cur.get("job_id"), "step": cur.get("step")}
    st = pipe.create(site_id)
    run = q.enqueue(Job(type="gsc_sync", payload={"site_id": site_id, "run_id": st.run_id, "days": days, "reason": reason}, site_id=site_id))
    pipe.attach_job(st.run_id, run.run_id)
    return {"status": "queued", "job_id": run.run_id, "run_id": st.run_id}


class GscSyncStart(BaseModel):
    days: int | None = Field(default=None, ge=1, le=480)


@router.post("/{site_id}/gsc/sync", status_code=202)
def gsc_sync_start(site_id: str, body: GscSyncStart | None = None, site: Site = Depends(require_site), eng: Engine = Depends(engine), q: JobQueue = Depends(job_queue)) -> dict:
    """Queue the GSC pipeline: Search Console data → keyword opportunities → content snapshot → graph. Never inline; no browser OAuth in the worker."""
    body = body or GscSyncStart()
    if not site.gsc_property:
        raise ApiError(409, "برای این سایت property سرچ‌کنسول تنظیم نشده است — ابتدا اتصال GSC را تست کنید", code="gsc_not_configured")
    from ...connections.service import GSC_SCOPE, _token_info
    tok = _token_info()
    if not tok.get("present") or GSC_SCOPE not in (tok.get("scopes") or []):
        raise ApiError(409, "توکن Google موجود نیست؛ برای اتصال حساب گوگل، از بخش «حساب گوگل» در مرکز اتصال‌ها اتصال را انجام دهید", code="gsc_not_authorized")
    return _queue_gsc_sync(site_id, eng, q, days=body.days, reason="manual")


@router.get("/{site_id}/gsc/sync/status")
def gsc_sync_status(site_id: str, site: Site = Depends(require_site), eng: Engine = Depends(engine), q: JobQueue = Depends(job_queue)) -> dict:
    """Latest pipeline run (from the existing sync_runs table) + live coverage: date range, rows, queries, pages, snapshots."""
    from ...connections.service import GSC_SCOPE, _token_info
    from ...gsc.pipeline import GscPipeline
    return {"site_id": site_id, "property": site.gsc_property or None,
            "authorized": bool((tok := _token_info()).get("present") and GSC_SCOPE in (tok.get("scopes") or [])),
            **GscPipeline(eng).status(site_id, q)}


# --------------------------------------------------------------------------- GA4 → sync → graph pipeline (wiring of existing components)
def _queue_ga4_sync(site_id: str, eng: Engine, q: JobQueue, days: int | None, reason: str) -> dict:
    from ...ga4.pipeline import Ga4Pipeline
    pipe = Ga4Pipeline(eng)
    if pipe.is_running(site_id):
        cur = pipe.latest(site_id) or {}
        return {"status": "already_running", "run_id": cur.get("run_id"), "job_id": cur.get("job_id"), "step": cur.get("step")}
    st = pipe.create(site_id)
    run = q.enqueue(Job(type="ga4_sync", payload={"site_id": site_id, "run_id": st.run_id, "days": days, "reason": reason}, site_id=site_id))
    pipe.attach_job(st.run_id, run.run_id)
    return {"status": "queued", "job_id": run.run_id, "run_id": st.run_id}


class Ga4SyncStart(BaseModel):
    days: int | None = Field(default=None, ge=1, le=480)


@router.post("/{site_id}/ga4/sync", status_code=202)
def ga4_sync_start(site_id: str, body: Ga4SyncStart | None = None, site: Site = Depends(require_site), eng: Engine = Depends(engine), q: JobQueue = Depends(job_queue)) -> dict:
    """Queue the GA4 pipeline: Analytics data → content snapshot → graph/opportunities. Never inline; no OAuth in the worker."""
    body = body or Ga4SyncStart()
    if not site.ga4_property:
        raise ApiError(409, "برای این سایت property گوگل‌آنالیتیکس تنظیم نشده است — ابتدا اتصال GA4 را تست کنید", code="ga4_not_configured")
    from ...connections.service import GA4_SCOPE, _google_client_configured, _token_info
    tok = _token_info()
    if not _google_client_configured() or not tok.get("present") or GA4_SCOPE not in (tok.get("scopes") or []):
        raise ApiError(409, "توکن Google با اسکوپ analytics.readonly موجود نیست؛ اتصال GA4 را دوباره تست کنید", code="ga4_not_authorized")
    return _queue_ga4_sync(site_id, eng, q, days=body.days, reason="manual")


@router.get("/{site_id}/ga4/sync/status")
def ga4_sync_status(site_id: str, site: Site = Depends(require_site), eng: Engine = Depends(engine), q: JobQueue = Depends(job_queue)) -> dict:
    """Latest pipeline run (from the existing sync_runs table) + live coverage: date range, rows, sessions, users, conversions, top pages."""
    from ...connections.service import GA4_SCOPE, _google_client_configured, _token_info
    from ...ga4.pipeline import Ga4Pipeline
    tok = _token_info()
    return {"site_id": site_id, "property": site.ga4_property or None,
            "authorized": bool(_google_client_configured() and tok.get("present") and GA4_SCOPE in (tok.get("scopes") or [])),
            **Ga4Pipeline(eng).status(site_id, q)}


class AutoSyncUpdate(BaseModel):
    enabled: bool | None = None
    interval_hours: int | None = Field(default=None, ge=1, le=168)


@router.get("/{site_id}/auto-sync")
def auto_sync_get(site_id: str, site: Site = Depends(require_site), eng: Engine = Depends(engine)) -> dict:
    """Automatic-refresh plan for the card UI: enabled · interval · per-integration last/next/configured."""
    from ...automation.scheduler import plan_for_site
    return {"site_id": site_id, **plan_for_site(eng, site_id)}


@router.put("/{site_id}/auto-sync")
def auto_sync_put(site_id: str, body: AutoSyncUpdate, site: Site = Depends(require_site), eng: Engine = Depends(engine)) -> dict:
    """Toggle automatic refresh / change the interval (stored in the existing site_settings table)."""
    from ...automation.scheduler import plan_for_site, save_auto_sync_settings
    save_auto_sync_settings(eng, site_id, enabled=body.enabled, interval_hours=body.interval_hours)
    return {"site_id": site_id, **plan_for_site(eng, site_id)}


gsc_router = APIRouter(prefix="/connections", tags=["sites"])


@gsc_router.get("/gsc/service-account/status")
def gsc_sa_status() -> dict:
    """Service-account connection state for the card: configured · e-mail · cached properties · last check. No secrets."""
    from ...connections.service_account import status as sa_status
    return sa_status()


@gsc_router.post("/gsc/service-account/check")
def gsc_sa_check() -> dict:
    """Live access check: sites().list() with the service account → the properties the user has granted it."""
    from ...connections.service_account import check_access
    return check_access()


@gsc_router.get("/ga4/properties")
def ga4_properties(svc: ConnectionsService = Depends(connections_service)) -> dict:
    """GA4 properties visible to the connected Google account (Admin API) — for the selector in the GA4 card."""
    return svc.list_ga4_properties()


@gsc_router.get("/gsc/properties")
def gsc_properties(svc: ConnectionsService = Depends(connections_service)) -> dict:
    """Properties visible to the connected Google account (for the wizard's dropdown)."""
    return svc.list_gsc_properties()
