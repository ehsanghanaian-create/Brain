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


def _workspace_for(site_id: str) -> str:
    p = PROJECT_ROOT / "data" / "sites" / site_id
    for sub in ("raw", "exports", "uploads", "vault"):
        (p / sub).mkdir(parents=True, exist_ok=True)
    return str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")


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
                mode=body.mode, workspace_path=_workspace_for(body.site_id))
    return repo.save(site).to_dict()


@router.get("/{site_id}")
def get_site(site: Site = Depends(require_site)) -> dict:
    return site.to_dict()


@router.patch("/{site_id}")
def update_site(body: SiteUpdate, site: Site = Depends(require_site), repo: SitesRepository = Depends(sites_repo)) -> dict:
    data = body.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(site, k, str(v) if k == "wp_url" else v)
    if not site.workspace_path:
        site.workspace_path = _workspace_for(site.site_id)
    return repo.save(site).to_dict()


# tables that reference sites(site_id); a site with data is only deleted with ?force=true
# dependency order: dependents first (entity_mentions→entities, post_terms→posts, gsc_query_page→queries, graph_edges→graph_nodes)
_CHILD_TABLES = ("entity_mentions", "post_terms", "links", "gsc_query_page", "gsc_daily", "graph_edges", "seo_problems",
                 "seo_opportunities", "media", "schemas", "entities", "queries", "pages", "posts", "categories", "tags",
                 "taxonomies", "graph_nodes", "site_memory", "crawl_runs", "sync_runs")


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
