from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, Table
from sqlalchemy.dialects import postgresql, sqlite


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def loads(s: str | None, default: Any) -> Any:
    if s in (None, ""):
        return default
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default


class Repository:
    """Base repository bound to an Engine. Provides dialect-aware UPSERT."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def upsert(self, cx, table: Table, values: dict[str, Any], conflict: list[str], update: list[str] | None = None) -> None:
        """INSERT ... ON CONFLICT DO UPDATE for sqlite/postgres (Core, no ORM)."""
        dialect = self.engine.dialect.name
        insert = sqlite.insert if dialect == "sqlite" else postgresql.insert
        stmt = insert(table).values(**values)
        cols = update if update is not None else [c for c in values if c not in conflict]
        if cols:
            stmt = stmt.on_conflict_do_update(index_elements=conflict, set_={c: getattr(stmt.excluded, c) for c in cols})
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=conflict)
        cx.execute(stmt)
