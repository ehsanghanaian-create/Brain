from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...common.config import PROJECT_ROOT
from ...db.repositories import SitesRepository
from ...db.repositories.sites import Site
from ..deps import require_site, sites_repo
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
