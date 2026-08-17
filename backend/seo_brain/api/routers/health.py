from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Engine

from ...db.migrate import status as migration_status
from ..deps import engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health(eng: Engine = Depends(engine)) -> dict:
    ms = migration_status(eng)
    return {"status": "ok", "version": "0.2.0", "database": eng.dialect.name,
            "migrations": {"applied": [m["version"] for m in ms if m["applied"]],
                           "pending": [m["version"] for m in ms if not m["applied"]]}}
