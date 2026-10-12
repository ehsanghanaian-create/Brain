"""Site-scoped, durable SEO issue history."""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine, text

from ..deps import engine, require_site
from ..errors import ApiError

router = APIRouter(prefix="/sites/{site_id}/issues", tags=["issue-cases"], dependencies=[Depends(require_site)])


def _decoded(row) -> dict:
    result = dict(row)
    if "detail" in result:
        try:
            result["detail"] = json.loads(result["detail"]) if result["detail"] else {}
        except (ValueError, TypeError):
            result["detail"] = {}
    return result


@router.get("")
def list_issues(site_id: str, status: Literal["open", "resolved", "all"] = "open",
                problem_type: str | None = Query(None, max_length=100), limit: int = Query(50, ge=1, le=200),
                offset: int = Query(0, ge=0), eng: Engine = Depends(engine)) -> dict:
    where = "WHERE site_id=:site_id AND (:status='all' OR status=:status) AND (:problem_type IS NULL OR problem_type=:problem_type)"
    params = {"site_id": site_id, "status": status, "problem_type": problem_type, "limit": limit, "offset": offset}
    with eng.connect() as cx:
        total = int(cx.execute(text("SELECT COUNT(*) FROM issue_cases " + where), params).scalar() or 0)
        items = [_decoded(r) for r in cx.execute(text("SELECT id,problem_type,url,related_url,severity,status,detail,first_seen,last_seen,last_run_id,seen_count,resolved_at "
                                                  "FROM issue_cases " + where + " ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,last_seen DESC,id DESC LIMIT :limit OFFSET :offset"), params).mappings()]
        counts = {r[0]: r[1] for r in cx.execute(text("SELECT status,COUNT(*) FROM issue_cases WHERE site_id=:site_id GROUP BY status"), params)}
    return {"site_id": site_id, "items": items, "total": total, "limit": limit, "offset": offset,
            "counts": {"open": counts.get("open", 0), "resolved": counts.get("resolved", 0)},
            "resolution_policy": "complete_successful_crawl_only"}


@router.get("/{case_id}")
def issue_detail(site_id: str, case_id: int, eng: Engine = Depends(engine)) -> dict:
    params = {"site_id": site_id, "case_id": case_id}
    with eng.connect() as cx:
        case = cx.execute(text("SELECT id,problem_type,url,related_url,severity,status,detail,first_seen,last_seen,last_run_id,seen_count,resolved_at "
                               "FROM issue_cases WHERE site_id=:site_id AND id=:case_id"), params).mappings().first()
        if not case:
            raise ApiError(404, "پرونده پیدا نشد", code="not_found")
        observations = [_decoded(r) for r in cx.execute(text("SELECT run_id,severity,detail,observed_at FROM issue_case_observations "
                                                        "WHERE site_id=:site_id AND case_id=:case_id ORDER BY observed_at DESC,id DESC LIMIT 100"), params).mappings()]
        events = [dict(r) for r in cx.execute(text("SELECT run_id,event_type,created_at FROM issue_case_events "
                                                 "WHERE site_id=:site_id AND case_id=:case_id ORDER BY created_at DESC,id DESC LIMIT 100"), params).mappings()]
    return {**_decoded(case), "observations": observations, "events": events}
