"""SQLite access layer. Thin, explicit, no ORM."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from ..common.config import database_path

from ..common.config import PROJECT_ROOT
SCHEMA_PATH = PROJECT_ROOT / "database" / "migrations" / "0001_init.sql"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path) if path else database_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Bring the database to the latest schema (baseline 0001 + all later migrations). Idempotent."""
    from ..db.migrate import migrate_sqlite  # local import: keeps this legacy module dependency-light
    migrate_sqlite(conn)
    conn.commit()


@contextmanager
def db(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        init_db(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert(conn: sqlite3.Connection, table: str, row: dict[str, Any], conflict_cols: Iterable[str],
           update_cols: Iterable[str] | None = None) -> None:
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    conflict = ",".join(conflict_cols)
    if update_cols is None:
        update_cols = [c for c in cols if c not in set(conflict_cols) and c not in ("id", "created_at")]
    sets = ",".join(f"{c}=excluded.{c}" for c in update_cols)
    if "updated_at" in _columns(conn, table) and "updated_at" not in update_cols:
        sets = (sets + "," if sets else "") + "updated_at=excluded.updated_at"
        if "updated_at" not in row:
            cols.append("updated_at")
            row = {**row, "updated_at": utcnow()}
            placeholders += ",?"
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT({conflict}) DO UPDATE SET {sets}"
    if not sets:
        sql = f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, [row[c] for c in cols])


_COLS_CACHE: dict[str, set[str]] = {}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if table not in _COLS_CACHE:
        _COLS_CACHE[table] = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    return _COLS_CACHE[table]


def rows(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def one(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    r = conn.execute(sql, tuple(params)).fetchone()
    return dict(r) if r else None


def scalar(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Any:
    r = conn.execute(sql, tuple(params)).fetchone()
    return r[0] if r else None


def j(obj: Any) -> str | None:
    return None if obj is None else json.dumps(obj, ensure_ascii=False)


def ensure_site(conn: sqlite3.Connection, site) -> None:
    upsert(conn, "sites", {
        "site_id": site.site_id, "name": site.name, "canonical_url": site.canonical_url,
        "wp_url": site.wp_url, "language": site.language, "gsc_property": site.gsc_property,
    }, ["site_id"])
