"""SQLAlchemy engine factory.

DATABASE_URL examples:
  sqlite:///C:/path/data/seo.db          (default: sqlite at data/seo.db under the project root)
  postgresql+psycopg://user:pw@host/db   (server phase; same tables, same repositories)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event

from ..common.config import database_path, env


def database_url(path: str | Path | None = None) -> str:
    if path is None:
        url = env("DATABASE_URL")
        if url:
            return url
    p = Path(path) if path else database_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return "sqlite:///" + p.resolve().as_posix()


def make_engine(url: str | None = None) -> Engine:
    url = url or database_url()
    eng = create_engine(url, future=True)
    if eng.dialect.name == "sqlite":
        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys = ON")
            cur.execute("PRAGMA journal_mode = WAL")
            cur.close()
    return eng


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Process-wide engine for the configured database."""
    return make_engine()
