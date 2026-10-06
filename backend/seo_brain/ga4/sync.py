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


def store_site_rows(conn: sqlite3.Connection, site: SiteConfig, rows: list[dict], property_id: str,
                    start: date, end: date, run_id: str, by_channel: bool = False) -> int:
    """Replace one fully fetched site/channel window, keeping the grains separate."""
    for row in rows:
        if not (start.isoformat() <= row["date"] <= end.isoformat()):
            raise ValueError("GA4 site response has an unexpected date")
        if by_channel and not row["channel"]:
            raise ValueError("GA4 channel response is missing its channel")
    conn.execute("SAVEPOINT ga4_site_window")
    try:
        conn.execute(f"DELETE FROM ga4_site_daily WHERE site_id=? AND date BETWEEN ? AND ? AND channel {'!=' if by_channel else '='} ''",
                     (site.site_id, start.isoformat(), end.isoformat()))
        for row in rows:
            upsert(conn, "ga4_site_daily", {
                "site_id": site.site_id, "date": row["date"], "channel": row["channel"],
                "property_id": property_id, "sessions": row["sessions"], "total_users": row["total_users"],
                "conversions": row["conversions"], "sync_run_id": run_id, "observed_at": utcnow(),
            }, ["site_id", "date", "channel"])
        conn.execute("RELEASE SAVEPOINT ga4_site_window")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT ga4_site_window")
        conn.execute("RELEASE SAVEPOINT ga4_site_window")
        raise
    conn.commit()
    return len(rows)


def store_rows(conn: sqlite3.Connection, site: SiteConfig, rows, source: str, run_id: str) -> int:
    grouped: dict[tuple[str, str], dict] = {}
    for r in rows:
        path = unquote(r["path"] or "/")
        key = (r["date"], path)
        current = grouped.get(key)
        if current is None:
            grouped[key] = {**r, "path": path, "_row_count": 1}
            continue

        previous_sessions = int(current["sessions"] or 0)
        incoming_sessions = int(r["sessions"] or 0)
        total_sessions = previous_sessions + incoming_sessions
        previous_count = int(current["_row_count"])
        current["engagement_rate"] = _weighted_metric(
            current["engagement_rate"], previous_sessions, r["engagement_rate"], incoming_sessions,
            previous_count,
        )
        current["average_session_duration"] = _weighted_metric(
            current["average_session_duration"], previous_sessions, r["average_session_duration"], incoming_sessions,
            previous_count,
        )
        current["sessions"] = total_sessions
        current["total_users"] = int(current["total_users"] or 0) + int(r["total_users"] or 0)
        current["screen_page_views"] = int(current["screen_page_views"] or 0) + int(r["screen_page_views"] or 0)
        current["conversions"] = float(current["conversions"] or 0) + float(r["conversions"] or 0)
        current["_row_count"] = previous_count + 1

    for n, r in enumerate(grouped.values(), start=1):
        upsert(conn, "ga4_daily", {
            "site_id": site.site_id, "date": r["date"], "page_path": r["path"],
            "sessions": r["sessions"], "total_users": r["total_users"], "screen_page_views": r["screen_page_views"],
            "engagement_rate": r["engagement_rate"], "average_session_duration": r["average_session_duration"],
            "conversions": r["conversions"], "source": source, "sync_run_id": run_id,
        }, ["site_id", "date", "page_path", "source"])
        if n % 2000 == 0:
            conn.commit()
    conn.commit()
    return len(grouped)


def _weighted_metric(previous, previous_weight: int, incoming, incoming_weight: int, previous_count: int) -> float:
    total_weight = previous_weight + incoming_weight
    if total_weight:
        return ((float(previous or 0) * previous_weight) + (float(incoming or 0) * incoming_weight)) / total_weight
    return ((float(previous or 0) * previous_count) + float(incoming or 0)) / (previous_count + 1)


def sync_ga4(conn: sqlite3.Connection, site: SiteConfig, start: date, end: date, property_id: str | None = None,
             interactive: bool = False) -> dict:
    from .client import Ga4Client
    run_id = new_run_id("ga4")
    ensure_site(conn, site)
    pid = str(property_id or getattr(site, "ga4_property", "") or "").replace("properties/", "").strip()
    if not pid.isdigit():
        raise RuntimeError("GA4 property id is not configured for this site")
    if not site.host:
        raise RuntimeError("Canonical site hostname is required to isolate GA4 data")
    conn.execute("INSERT INTO sync_runs(run_id, site_id, source, started_at, status, params) VALUES (?,?,?,?,?,?)",
                 (run_id, site.site_id, "ga4", utcnow(), "running", j({"start": start.isoformat(), "end": end.isoformat(), "property": pid})))
    conn.commit()
    try:
        client = Ga4Client(site.site_id, interactive=interactive)
        n_page = store_rows(conn, site, client.daily(pid, start, end, dimension="pagePath", host_name=site.host), "page", run_id)
        n_land = store_rows(conn, site, client.daily(pid, start, end, dimension="landingPage", host_name=site.host), "landing", run_id)
        n_site = store_site_rows(conn, site, list(client.site_daily(pid, start, end, host_name=site.host)), pid, start, end, run_id)
        n_channel = store_site_rows(conn, site, list(client.site_daily(pid, start, end, by_channel=True, host_name=site.host)),
                                    pid, start, end, run_id, by_channel=True)
        conn.execute("DELETE FROM ga4_daily WHERE site_id=? AND date BETWEEN ? AND ? AND sync_run_id<>?",
                     (site.site_id, start.isoformat(), end.isoformat(), run_id))
        conn.commit()
        stats = _stats(conn, site.site_id)
        conn.execute("UPDATE sync_runs SET finished_at=?, status='completed', rows_written=?, notes=? WHERE run_id=?",
                     (utcnow(), n_page + n_land + n_site + n_channel,
                      j({"property": pid, "page_rows": n_page, "landing_rows": n_land,
                         "site_days": n_site, "channel_rows": n_channel, **stats}), run_id))
        conn.commit()
        return {"run_id": run_id, "property": pid, "rows": n_page + n_land + n_site + n_channel,
                "page_rows": n_page, "landing_rows": n_land, "site_days": n_site,
                "channel_rows": n_channel, **stats}
    except Exception as e:
        conn.execute("UPDATE sync_runs SET finished_at=?, status='failed', notes=? WHERE run_id=?", (utcnow(), str(e)[:500], run_id))
        conn.commit()
        raise


def _stats(conn: sqlite3.Connection, sid: str) -> dict:
    r = conn.execute("SELECT MIN(date), MAX(date), COUNT(DISTINCT page_path), SUM(sessions), SUM(total_users), SUM(conversions) "
                     "FROM ga4_daily WHERE site_id=? AND source='page'", (sid,)).fetchone()
    site = conn.execute("SELECT MIN(date), MAX(date), COUNT(*), SUM(sessions), SUM(conversions) "
                        "FROM ga4_site_daily WHERE site_id=? AND channel=''", (sid,)).fetchone()
    if site[2]:
        return {"date_from": site[0], "date_to": site[1], "pages": int(r[2] or 0),
                "sessions": int(site[3] or 0), "users": None,
                "conversions": round(float(site[4] or 0), 1), "metric_source": "ga4_site_daily"}
    return {"date_from": r[0], "date_to": r[1], "pages": int(r[2] or 0), "sessions": int(r[3] or 0),
            "users": int(r[4] or 0), "conversions": round(float(r[5] or 0), 1),
            "metric_source": "ga4_daily_page_rows"}
