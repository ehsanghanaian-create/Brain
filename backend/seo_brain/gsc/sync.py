"""GSC -> SQLite sync with incremental behaviour and aggregation.

Rows are stored per (date, page, query, country, device). Re-syncing a window upserts (idempotent).
`aggregate()` rebuilds gsc_query_page and queries for the stored window.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date

from ..common.config import SiteConfig
from ..common.logging_setup import new_run_id
from ..database.db import ensure_site, j, upsert, utcnow
from ..normalizer import normalize_url

log = logging.getLogger("gsc.sync")


def store_rows(conn: sqlite3.Connection, site: SiteConfig, rows, dimensions: list[str], run_id: str) -> int:
    n = 0
    idx = {d: i for i, d in enumerate(dimensions)}
    for r in rows:
        keys = r.get("keys", [])
        rec = {
            "site_id": site.site_id,
            "date": keys[idx["date"]] if "date" in idx else "",
            "page": normalize_url(keys[idx["page"]], site_host=site.host) if "page" in idx else "",
            "query": keys[idx["query"]] if "query" in idx else "",
            "country": keys[idx["country"]] if "country" in idx else "",
            "device": keys[idx["device"]] if "device" in idx else "",
            "clicks": int(r.get("clicks", 0)), "impressions": int(r.get("impressions", 0)),
            "ctr": float(r.get("ctr", 0)), "position": float(r.get("position", 0)), "sync_run_id": run_id,
        }
        upsert(conn, "gsc_daily", rec, ["site_id", "date", "page", "query", "country", "device"])
        n += 1
        if n % 2000 == 0:
            conn.commit()
    conn.commit()
    return n


def aggregate(conn: sqlite3.Connection, site: SiteConfig, date_from: str | None = None, date_to: str | None = None) -> dict:
    """Rebuild gsc_query_page + queries from gsc_daily (impression-weighted position)."""
    sid = site.site_id
    if not date_from:
        date_from = conn.execute("SELECT min(date) FROM gsc_daily WHERE site_id=?", (sid,)).fetchone()[0]
    if not date_to:
        date_to = conn.execute("SELECT max(date) FROM gsc_daily WHERE site_id=?", (sid,)).fetchone()[0]
    conn.execute("DELETE FROM gsc_query_page WHERE site_id=?", (sid,))
    conn.execute("""
        INSERT INTO gsc_query_page(site_id, page, query, clicks, impressions, ctr, position, date_from, date_to)
        SELECT site_id, page, query, SUM(clicks), SUM(impressions),
               CASE WHEN SUM(impressions)>0 THEN 1.0*SUM(clicks)/SUM(impressions) ELSE 0 END,
               CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) ELSE 0 END, ?, ?
        FROM gsc_daily WHERE site_id=? AND date BETWEEN ? AND ? GROUP BY site_id, page, query
    """, (date_from, date_to, sid, date_from, date_to))
    conn.execute("DELETE FROM queries WHERE site_id=?", (sid,))
    conn.execute("""
        INSERT INTO queries(site_id, query, clicks, impressions, ctr, position, pages_count)
        SELECT site_id, query, SUM(clicks), SUM(impressions),
               CASE WHEN SUM(impressions)>0 THEN 1.0*SUM(clicks)/SUM(impressions) ELSE 0 END,
               CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) ELSE 0 END,
               COUNT(DISTINCT page)
        FROM gsc_query_page WHERE site_id=? GROUP BY site_id, query
    """, (sid,))
    g = site.graph
    conn.execute("""
        UPDATE queries SET is_important = CASE
            WHEN impressions >= ? OR clicks >= ? OR (position <= 10 AND impressions >= 5) OR pages_count >= 2 THEN 1 ELSE 0 END,
          importance_reason = CASE
            WHEN impressions >= ? THEN 'high_impressions'
            WHEN clicks >= ? THEN 'high_clicks'
            WHEN position <= 10 AND impressions >= 5 THEN 'strong_ranking'
            WHEN pages_count >= 2 THEN 'multi_page_candidate'
            ELSE NULL END
        WHERE site_id=?
    """, (g.important_query_min_impressions, g.important_query_min_clicks, g.important_query_min_impressions, g.important_query_min_clicks, sid))
    conn.commit()
    stats = {
        "date_from": date_from, "date_to": date_to,
        "query_page_rows": conn.execute("SELECT count(*) FROM gsc_query_page WHERE site_id=?", (sid,)).fetchone()[0],
        "queries": conn.execute("SELECT count(*) FROM queries WHERE site_id=?", (sid,)).fetchone()[0],
        "important_queries": conn.execute("SELECT count(*) FROM queries WHERE site_id=? AND is_important=1", (sid,)).fetchone()[0],
    }
    log.info(f"GSC aggregate: {stats}")
    return stats


def sync_gsc(conn: sqlite3.Connection, site: SiteConfig, start: date, end: date, dimensions: list[str] | None = None,
             interactive: bool = True) -> dict:
    from .client import GscClient
    run_id = new_run_id("gsc")
    ensure_site(conn, site)
    dims = dimensions or site.gsc.dimensions
    conn.execute("INSERT INTO sync_runs(run_id, site_id, source, started_at, status, params) VALUES (?,?,?,?,?,?)",
                 (run_id, site.site_id, "gsc", utcnow(), "running", j({"start": start.isoformat(), "end": end.isoformat(), "dimensions": dims})))
    conn.commit()
    try:
        client = GscClient(site.site_id, interactive=interactive)
        prop, perm = client.resolve_property(site.gsc_property or site.canonical_url)
        if not prop:
            sites = [s.get("siteUrl") for s in client.list_sites()]
            raise RuntimeError(f"property {site.gsc_property!r} not found for this Google account; available: {sites}")
        log.info(f"GSC property: {prop} (permission={perm})")
        # dates dimension first is required by store_rows; ensure 'date' present
        if "date" not in dims:
            dims = ["date"] + dims
        n = store_rows(conn, site, client.query(prop, start, end, dims, row_limit=site.gsc.row_limit), dims, run_id)
        agg = aggregate(conn, site)
        conn.execute("UPDATE sync_runs SET finished_at=?, status='completed', rows_written=?, notes=? WHERE run_id=?",
                     (utcnow(), n, j({"property": prop, "permission": perm, **agg}), run_id))
        conn.commit()
        return {"run_id": run_id, "property": prop, "permission": perm, "rows": n, **agg}
    except Exception as e:
        conn.execute("UPDATE sync_runs SET finished_at=?, status='failed', notes=? WHERE run_id=?", (utcnow(), str(e)[:500], run_id))
        conn.commit()
        raise
