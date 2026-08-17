"""Forward-only SQL migration runner.

Files: database/migrations/NNNN_name.sql (NNNN = zero-padded version). Applied versions are recorded in
`schema_migrations`. 0001 is the v0.1 baseline (idempotent `IF NOT EXISTS` DDL) so an existing data/seo.db
is adopted without changes. SQLite `ALTER TABLE ... ADD COLUMN` has no IF NOT EXISTS: statements failing
with "duplicate column name" are treated as already applied.

Works on a raw sqlite3 connection (legacy code path, `init_db`) and on a SQLAlchemy Engine (new code path).
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import Engine, text

from ..common.config import PROJECT_ROOT
import logging

log = logging.getLogger("db.migrate")
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"
_FILE_RE = re.compile(r"^(\d{4})_([A-Za-z0-9_\-]+)\.sql$")

_DDL_TRACK = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    " version TEXT PRIMARY KEY, name TEXT NOT NULL,"
    " applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))"
)


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def discover(directory: Path | None = None) -> list[Migration]:
    d = directory or MIGRATIONS_DIR
    out: list[Migration] = []
    for p in sorted(d.glob("*.sql")):
        m = _FILE_RE.match(p.name)
        if m:
            out.append(Migration(m.group(1), m.group(2), p))
    versions = [m.version for m in out]
    if len(versions) != len(set(versions)):
        raise RuntimeError(f"duplicate migration versions in {d}")
    return out


def _strip_trailing_comment(line: str) -> str:
    """Remove a `-- comment` that is not inside a single-quoted string."""
    in_str = False
    for i, ch in enumerate(line):
        if ch == "'":
            in_str = not in_str
        elif ch == "-" and not in_str and line[i:i + 2] == "--":
            return line[:i].rstrip()
    return line


def _split_statements(sql: str) -> list[str]:
    """Split on ';' at line ends, but keep CREATE TRIGGER ... BEGIN ... END; blocks intact."""
    stmts, buf, in_trigger = [], [], False
    for line in sql.splitlines():
        line = _strip_trailing_comment(line)
        stripped = line.strip()
        if not stripped:
            continue
        buf.append(line)
        up = stripped.upper()
        if up.startswith("CREATE TRIGGER"):
            in_trigger = True
        if in_trigger:
            if up.startswith("END;") or up == "END;":
                stmts.append("\n".join(buf)); buf, in_trigger = [], False
        elif stripped.endswith(";"):
            stmts.append("\n".join(buf)); buf = []
    if buf:
        stmts.append("\n".join(buf))
    return stmts


def _is_duplicate_column(err: Exception) -> bool:
    return "duplicate column name" in str(err).lower() or "already exists" in str(err).lower()


# --------------------------------------------------------------------------- sqlite3 path
def _applied_sqlite(conn: sqlite3.Connection) -> set[str]:
    conn.execute(_DDL_TRACK)
    return {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}


def migrate_sqlite(conn: sqlite3.Connection, directory: Path | None = None) -> list[str]:
    """Apply pending migrations on a raw sqlite3 connection. Returns applied versions."""
    applied = _applied_sqlite(conn)
    done: list[str] = []
    for m in discover(directory):
        if m.version in applied:
            continue
        for stmt in _split_statements(m.sql):
            try:
                conn.execute(stmt) if not stmt.upper().lstrip().startswith("CREATE TRIGGER") else conn.executescript(stmt)
            except sqlite3.OperationalError as e:
                if _is_duplicate_column(e) and stmt.upper().lstrip().startswith("ALTER TABLE"):
                    continue
                raise RuntimeError(f"migration {m.version}_{m.name} failed at: {stmt[:80]}… ({e})") from e
        conn.execute("INSERT INTO schema_migrations(version, name) VALUES (?, ?)", (m.version, m.name))
        conn.commit()
        done.append(m.version)
        log.info(f"applied migration {m.version}_{m.name}")
    return done


# --------------------------------------------------------------------------- SQLAlchemy path
def applied_versions(engine: Engine) -> set[str]:
    with engine.begin() as cx:
        cx.execute(text(_DDL_TRACK))
        return {r[0] for r in cx.execute(text("SELECT version FROM schema_migrations"))}


def migrate(engine: Engine, directory: Path | None = None) -> list[str]:
    """Apply pending migrations through SQLAlchemy (SQLite now; Postgres later)."""
    if engine.dialect.name == "sqlite":
        raw = engine.raw_connection()
        try:
            inner = raw.driver_connection  # underlying sqlite3.Connection
            return migrate_sqlite(inner, directory)
        finally:
            raw.close()
    applied = applied_versions(engine)
    done: list[str] = []
    for m in discover(directory):
        if m.version in applied:
            continue
        with engine.begin() as cx:
            for stmt in _split_statements(m.sql):
                try:
                    cx.execute(text(stmt))
                except Exception as e:  # noqa: BLE001
                    if _is_duplicate_column(e) and stmt.upper().lstrip().startswith("ALTER TABLE"):
                        continue
                    raise
            cx.execute(text("INSERT INTO schema_migrations(version, name) VALUES (:v, :n)"), {"v": m.version, "n": m.name})
        done.append(m.version)
        log.info(f"applied migration {m.version}_{m.name}")
    return done


def status(engine: Engine, directory: Path | None = None) -> list[dict]:
    applied = applied_versions(engine)
    return [{"version": m.version, "name": m.name, "applied": m.version in applied} for m in discover(directory)]


def pending(engine: Engine, directory: Path | None = None) -> Iterable[Migration]:
    applied = applied_versions(engine)
    return [m for m in discover(directory) if m.version not in applied]
