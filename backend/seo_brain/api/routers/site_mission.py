"""Human-defined objective for a site; no inferred progress or invented targets."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text

from ...db.repositories.base import utcnow
from ..deps import engine, require_site

router = APIRouter(prefix="/sites/{site_id}/mission", tags=["sites"], dependencies=[Depends(require_site)])


class SiteMissionInput(BaseModel):
    objective: str = Field(default="", max_length=300)
    success_metric: str = Field(default="", max_length=200)


def _read(raw: str | None) -> dict[str, str]:
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {"objective": str(data.get("objective") or ""),
            "success_metric": str(data.get("success_metric") or "")}


@router.get("")
def get_mission(site_id: str, eng: Engine = Depends(engine)) -> dict:
    with eng.connect() as cx:
        row = cx.execute(text("SELECT value, updated_at FROM site_settings WHERE site_id=:s AND key='mission'"), {"s": site_id}).first()
    return {"site_id": site_id, **_read(row[0] if row else None), "updated_at": row[1] if row else None}


@router.put("")
def put_mission(site_id: str, body: SiteMissionInput, eng: Engine = Depends(engine)) -> dict:
    value = {"objective": body.objective.strip(), "success_metric": body.success_metric.strip()}
    with eng.begin() as cx:
        cx.execute(text("""INSERT INTO site_settings(site_id, key, value, updated_at) VALUES(:s,'mission',:v,:u)
                           ON CONFLICT(site_id, key) DO UPDATE SET value=:v, updated_at=:u"""),
                   {"s": site_id, "v": json.dumps(value, ensure_ascii=False), "u": utcnow()})
    return get_mission(site_id, eng)
