from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine

from ...brain.knowledge_pack import ContentKnowledgePackService
from ..deps import engine, require_site

router = APIRouter(prefix="/sites/{site_id}/knowledge-pack", tags=["content-knowledge"], dependencies=[Depends(require_site)])


def service(eng: Engine = Depends(engine)) -> ContentKnowledgePackService:
    return ContentKnowledgePackService(eng)


@router.get("")
def latest(site_id: str, rebuild_if_missing: bool = True, svc: ContentKnowledgePackService = Depends(service)) -> dict:
    return svc.latest(site_id, rebuild_if_missing=rebuild_if_missing) or {"site_id": site_id, "status": "missing"}


@router.post("/rebuild")
def rebuild(site_id: str, svc: ContentKnowledgePackService = Depends(service)) -> dict:
    return svc.rebuild(site_id)


@router.get("/history")
def history(site_id: str, limit: int = Query(20, ge=1, le=100), svc: ContentKnowledgePackService = Depends(service)) -> list[dict]:
    return svc.history(site_id, limit)
