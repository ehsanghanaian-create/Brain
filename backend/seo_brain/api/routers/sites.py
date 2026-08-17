from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine, inspect, text

from ...common.config import PROJECT_ROOT
from ...db.repositories import SitesRepository
from ...db.repositories.sites import Site
from ..deps import engine, require_site, sites_repo
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
_CHILD_TABLES = ("keyword_opportunities", "keywords", "keyword_clusters", "keyword_imports",
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
    return {"site_id": site_id,
            "configured": {"gsc": site.gsc_property, "ga4": site.ga4_property, "wordpress": site.wp_url},
            "status": svc.status(site_id)}


@router.post("/{site_id}/connections/{kind}/test")
def test_connection(site_id: str, kind: str, body: ConnectionTestRequest | None = None, site: Site = Depends(require_site),
                    svc: ConnectionsService = Depends(connections_service), repo: SitesRepository = Depends(sites_repo)) -> dict:
    """Run a read-only permission test. If `property` is given and the test passes, it is stored on the site."""
    body = body or ConnectionTestRequest()
    if kind == "gsc":
        res = svc.test_gsc(site_id, body.property or site.gsc_property)
        if res.ok and body.property and body.property != site.gsc_property:
            repo.set_fields(site_id, gsc_property=res.detail.get("property") or body.property)
    elif kind == "ga4":
        res = svc.test_ga4(site_id, body.property or site.ga4_property)
        if res.ok and body.property and body.property != site.ga4_property:
            repo.set_fields(site_id, ga4_property=res.detail.get("property") or body.property)
    elif kind == "wordpress":
        res = svc.test_wordpress(site_id, body.property or site.wp_url)
        if res.ok and body.property and body.property != site.wp_url:
            repo.set_fields(site_id, wp_url=body.property.rstrip("/"))
    else:
        raise ApiError(404, f"unknown connection kind '{kind}'", code="not_found", details={"kinds": ["gsc", "ga4", "wordpress"]})
    return res.to_dict()


@router.post("/{site_id}/initialize")
def initialize_site(site_id: str, site: Site = Depends(require_site), eng: Engine = Depends(engine),
                    repo: SitesRepository = Depends(sites_repo)) -> dict:
    """Wizard step 3: workspace + site memory + graph namespace (idempotent)."""
    init = SiteInitializer(eng, PROJECT_ROOT)
    out = init.initialize(site)
    if site.workspace_path != out["workspace"]["path"]:
        repo.set_fields(site_id, workspace_path=out["workspace"]["path"])
    return out


gsc_router = APIRouter(prefix="/connections", tags=["sites"])


@gsc_router.get("/gsc/properties")
def gsc_properties(svc: ConnectionsService = Depends(connections_service)) -> dict:
    """Properties visible to the connected Google account (for the wizard's dropdown)."""
    return svc.list_gsc_properties()
