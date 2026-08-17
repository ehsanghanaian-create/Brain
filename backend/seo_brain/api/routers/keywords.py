"""Keyword Intelligence endpoints (phase 5). Site-scoped: /sites/{site_id}/keywords/*"""
from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from ...brain.keywords import KeywordImporter, KeywordService, KeywordsRepository
from ...brain.keywords.importer import TEMPLATE_CSV
from ...brain.keywords.repository import INTENTS, OPP_KINDS, OPP_STATUSES, PRIORITIES, STATUSES, Keyword
from ...brain.keywords.service import OPP_FA
from ..deps import engine, require_site
from ..errors import ApiError

router = APIRouter(prefix="/sites/{site_id}/keywords", tags=["keywords"], dependencies=[Depends(require_site)])

Intent = Literal["informational", "navigational", "commercial", "transactional", "local"]
Priority = Literal["high", "medium", "low"]
Status = Literal["new", "planned", "in_progress", "published", "ignored"]


class KeywordCreate(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)
    intent: Intent | None = None
    topic: str | None = None
    cluster_id: str | None = None
    volume: int | None = Field(default=None, ge=0)
    difficulty: float | None = Field(default=None, ge=0, le=100)
    priority: Priority | None = None
    target_url: str | None = None
    status: Status = "new"
    notes: str | None = None


class KeywordUpdate(BaseModel):
    keyword: str | None = Field(default=None, min_length=1, max_length=200)
    intent: Intent | None = None
    topic: str | None = None
    cluster_id: str | None = None
    volume: int | None = Field(default=None, ge=0)
    difficulty: float | None = Field(default=None, ge=0, le=100)
    priority: Priority | None = None
    target_url: str | None = None
    status: Status | None = None
    notes: str | None = None


class ClusterUpdate(BaseModel):
    name: str | None = None
    topic: str | None = None


class OppStatus(BaseModel):
    status: Literal["new", "accepted", "dismissed", "done"]


def svc(eng: Engine = Depends(engine)) -> KeywordService:
    return KeywordService(eng)


@router.get("")
def list_keywords(site_id: str, q: str | None = None, status: str | None = None, intent: str | None = None, cluster_id: str | None = None,
                  topic: str | None = None, priority: str | None = None, sort: str = "updated_at", order: Literal["asc", "desc"] = "desc",
                  limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), s: KeywordService = Depends(svc)) -> dict:
    """Paginated envelope {items,total,limit,offset}; items carry `gsc` (matched Search Console metrics) and `cluster`."""
    rows, total = s.repo.list(site_id, q, status, intent, cluster_id, topic, priority, sort, order, limit, offset)
    return {"items": s.enrich(site_id, rows), "total": total, "limit": limit, "offset": offset, "counts": s.repo.counts(site_id)}


@router.post("", status_code=201)
def create_keyword(site_id: str, body: KeywordCreate, s: KeywordService = Depends(svc)) -> dict:
    kw = Keyword(site_id=site_id, source="manual", **body.model_dump())
    if s.repo.get_by_normalized(site_id, kw.normalized):
        raise ApiError(409, f"کلمه کلیدی «{body.keyword}» قبلاً وجود دارد", code="conflict")
    row, _ = s.repo.upsert(kw)
    return s.enrich(site_id, [row])[0]


@router.get("/meta")
def meta() -> dict:
    return {"intents": list(INTENTS), "priorities": list(PRIORITIES), "statuses": list(STATUSES), "opportunity_kinds": [{"kind": k, "fa": OPP_FA[k]} for k in OPP_KINDS],
            "opportunity_statuses": list(OPP_STATUSES)}


@router.get("/template.csv", response_class=PlainTextResponse)
def template() -> str:
    return TEMPLATE_CSV


@router.post("/import")
async def import_keywords(site_id: str, file: UploadFile = File(...), mapping: str | None = Form(default=None), dry_run: bool = Form(default=True),
                          s: KeywordService = Depends(svc)) -> dict:
    """Upload CSV / TSV / XLSX (Excel or Google-Sheet export). `dry_run=true` returns detected mapping + preview only.
    `mapping` is an optional JSON object {source_column: field} to override auto-detection."""
    data = await file.read()
    if not data:
        raise ApiError(400, "فایل خالی است", code="bad_request")
    if len(data) > 15 * 1024 * 1024:
        raise ApiError(400, "حداکثر اندازه فایل ۱۵ مگابایت است", code="bad_request")
    mp: dict[str, str] | None = None
    if mapping:
        try:
            mp = json.loads(mapping)
            assert isinstance(mp, dict)
        except Exception:  # noqa: BLE001
            raise ApiError(422, "mapping باید یک شیء JSON باشد", code="validation_error")
    res = KeywordImporter(s.repo).run(site_id, data, file.filename, mp, dry_run=dry_run)
    return res.to_dict()


@router.get("/imports")
def imports(site_id: str, s: KeywordService = Depends(svc)) -> list[dict]:
    return s.repo.list_imports(site_id)


@router.get("/clusters")
def clusters(site_id: str, s: KeywordService = Depends(svc)) -> list[dict]:
    return [c.to_dict() for c in s.repo.list_clusters(site_id)]


@router.post("/cluster")
def run_cluster(site_id: str, threshold: float = Query(0.42, ge=0.1, le=0.95), sync_graph: bool = True, s: KeywordService = Depends(svc)) -> dict:
    out = s.run_clustering(site_id, threshold)
    if sync_graph:
        out["graph"] = s.sync_graph(site_id)
    return out


@router.patch("/clusters/{cluster_id}")
def update_cluster(site_id: str, cluster_id: str, body: ClusterUpdate, s: KeywordService = Depends(svc)) -> dict:
    c = s.repo.update_cluster(site_id, cluster_id, **body.model_dump(exclude_none=True))
    if not c:
        raise HTTPException(404, "cluster not found")
    return c.to_dict()


@router.get("/topic-map")
def topic_map(site_id: str, s: KeywordService = Depends(svc)) -> dict:
    return s.topic_map(site_id)


@router.post("/analyze")
def analyze(site_id: str, min_impressions: int = Query(5, ge=0), sync_graph: bool = True, s: KeywordService = Depends(svc)) -> dict:
    out = s.analyze(site_id, min_impressions)
    if sync_graph:
        out["graph"] = s.sync_graph(site_id)
    return out


@router.get("/opportunities")
def opportunities(site_id: str, kind: str | None = None, status: str | None = None, keyword_id: int | None = None, min_score: float = 0.0,
                  limit: int = Query(100, ge=1, le=1000), offset: int = 0, s: KeywordService = Depends(svc)) -> dict:
    rows, total = s.repo.list_opportunities(site_id, kind, status, keyword_id, min_score, limit, offset)
    kw = {k.id: k for k in s.repo.all(site_id)}
    items = []
    for o in rows:
        k = kw.get(o.keyword_id)
        items.append({**o.to_dict(), "kind_fa": OPP_FA.get(o.kind, o.kind), "keyword": k.keyword if k else None, "keyword_status": k.status if k else None})
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.patch("/opportunities/{oid}")
def set_opp_status(site_id: str, oid: int, body: OppStatus, s: KeywordService = Depends(svc)) -> dict:
    o = s.repo.set_opportunity_status(site_id, oid, body.status)
    if not o:
        raise HTTPException(404, "opportunity not found")
    return {**o.to_dict(), "kind_fa": OPP_FA.get(o.kind, o.kind)}


@router.post("/sync-graph")
def sync_graph(site_id: str, s: KeywordService = Depends(svc)) -> dict:
    return s.sync_graph(site_id)


@router.get("/{kid}")
def get_keyword(site_id: str, kid: int, s: KeywordService = Depends(svc)) -> dict:
    d = s.detail(site_id, kid)
    if not d:
        raise HTTPException(404, "keyword not found")
    return d


@router.patch("/{kid}")
def update_keyword(site_id: str, kid: int, body: KeywordUpdate, s: KeywordService = Depends(svc)) -> dict:
    if not s.repo.get(site_id, kid):
        raise HTTPException(404, "keyword not found")
    row = s.repo.update(site_id, kid, **body.model_dump(exclude_none=True))
    return s.enrich(site_id, [row])[0]  # type: ignore[list-item]


@router.delete("/{kid}")
def delete_keyword(site_id: str, kid: int, s: KeywordService = Depends(svc)) -> dict:
    if not s.repo.delete(site_id, kid):
        raise HTTPException(404, "keyword not found")
    return {"deleted": kid}
