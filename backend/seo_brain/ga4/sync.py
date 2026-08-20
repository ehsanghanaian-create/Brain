"""GA4 -> SQLite sync — the GA4 twin of gsc/sync.py.

Rows are stored per (date, page_path, source) in ga4_daily; re-syncing a window upserts (idempotent).
`source` = 'page' (pagePath) | 'landing' (landingPage). History is recorded in the existing sync_runs
table (source='ga4') exactly like GSC records source='gsc'.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date
from urllib.parse import unquote

from ..common.config import SiteConfig
from ..common.logging_setup import new_run_id
from ..database.db import ensure_site, j, upsert, utcnow

log = logging.getLogger("ga4.sync")


def store_rows(conn: sqlite3.Connection, site: SiteConfig, rows, source: str, run_id: str) -> int:
    n = 0
    for r in rows:
        upsert(conn, "ga4_daily", {
            "site_id": site.site_id, "date": r["date"], "page_path": unquote(r["path"] or "/"),
            "sessions": r["sessions"], "total_users": r["total_users"], "screen_page_views": r["screen_page_views"],
            "engagement_rate": r["engagement_rate"], "average_session_duration": r["average_session_duration"],
            "conversions": r["conversions"], "source": source, "sync_run_id": run_id,
        }, ["site_id", "date", "page_path", "source"])
        n += 1
        if n % 2000 == 0:
            conn.commit()
    conn.commit()
    return n


def sync_ga4(conn: sqlite3.Connection, site: SiteConfig, start: date, end: date, property_id: str | None = None,
             interactive: bool = False) -> dict:
    from .client import Ga4Client
    run_id = new_run_id("ga4")
    ensure_site(conn, site)
    pid = str(property_id or getattr(site, "ga4_property", "") or "").replace("properties/", "").strip()
    if not pid.isdigit():
        raise RuntimeError("GA4 property id is not configured for this site")
    conn.execute("INSERT INTO sync_runs(run_id, site_id, source, started_at, status, params) VALUES (?,?,?,?,?,?)",
                 (run_id, site.site_id, "ga4", utcnow(), "running", j({"start": start.isoformat(), "end": end.isoformat(), "property": pid})))
    conn.commit()
    try:
        client = Ga4Client(site.site_id, interactive=interactive)
        n_page = store_rows(conn, site, client.daily(pid, start, end, dimension="pagePath"), "page", run_id)
        n_land = store_rows(conn, site, client.daily(pid, start, end, dimension="landingPage"), "landing", run_id)
        stats = _stats(conn, site.site_id)
        conn.execute("UPDATE sync_runs SET finished_at=?, status='completed', rows_written=?, notes=? WHERE run_id=?",
                     (utcnow(), n_page + n_land, j({"property": pid, "page_rows": n_page, "landing_rows": n_land, **stats}), run_id))
        conn.commit()
        return {"run_id": run_id, "property": pid, "rows": n_page + n_land, "page_rows": n_page, "landing_rows": n_land, **stats}
    except Exception as e:
        conn.execute("UPDATE sync_runs SET finished_at=?, status='failed', notes=? WHERE run_id=?", (utcnow(), str(e)[:500], run_id))
        conn.commit()
        raise


def _stats(conn: sqlite3.Connection, sid: str) -> dict:
    r = conn.execute("SELECT MIN(date), MAX(date), COUNT(DISTINCT page_path), SUM(sessions), SUM(total_users), SUM(conversions) "
                     "FROM ga4_daily WHERE site_id=? AND source='page'", (sid,)).fetchone()
    return {"date_from": r[0], "date_to": r[1], "pages": int(r[2] or 0), "sessions": int(r[3] or 0),
            "users": int(r[4] or 0), "conversions": round(float(r[5] or 0), 1)}
