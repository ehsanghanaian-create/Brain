"""Site Report Center (per-site aggregate report). Site-scoped: /sites/{site_id}/report/*

Read model only — every number here comes from data that already exists in the DB
(gsc_daily/gsc_query_page, ga4_daily, seo_problems, seo_opportunities, link_page_stats,
sync_runs, keywords) plus the two manual stores this feature owns (backlinks, reportages).
No pipeline is re-implemented; position aggregation follows gsc/sync.py (impression-weighted).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text

from ...automation.scheduler import plan_for_site
from ...common.http import ReadOnlyClient
from ..deps import engine, require_site

router = APIRouter(prefix="/sites/{site_id}/report", tags=["report"], dependencies=[Depends(require_site)])

# problem_type -> report category (technical / on_page / content / indexing / internal_linking)
PROBLEM_CATEGORY = {
    "orphan": "internal_linking", "no_body_inbound_links": "internal_linking",
    "low_inbound_links": "internal_linking", "high_outbound_links": "internal_linking",
    "missing_h1": "on_page", "multiple_h1": "on_page", "duplicate_h1": "on_page",
    "duplicate_title": "on_page", "missing_meta_description": "on_page",
    "missing_canonical": "technical", "redirect_in_sitemap": "technical",
    "important_non_indexable": "indexing",
    "thin_content": "content", "images_missing_alt": "content",
}
CATEGORY_FA = {
    "technical": "سئو تکنیکال", "on_page": "سئو داخلی صفحه", "content": "محتوا",
    "indexing": "ایندکس", "internal_linking": "لینک‌سازی داخلی", "other": "سایر",
}
PROBLEM_FA = {
    "orphan": "صفحه یتیم (بدون لینک ورودی)", "no_body_inbound_links": "بدون لینک ورودی از متن",
    "low_inbound_links": "لینک ورودی کم", "high_outbound_links": "لینک خروجی بیش از حد",
    "missing_h1": "بدون H1", "multiple_h1": "چند H1", "duplicate_h1": "H1 تکراری",
    "duplicate_title": "عنوان تکراری", "missing_meta_description": "بدون توضیحات متا",
    "missing_canonical": "بدون canonical", "redirect_in_sitemap": "ریدایرکت در سایت‌مپ",
    "important_non_indexable": "صفحه مهم غیرقابل ایندکس", "thin_content": "محتوای کم‌حجم",
    "images_missing_alt": "تصاویر بدون alt",
}
OPP_FA = {
    "striking_distance": "کلمات نزدیک به صفحه اول (جایگاه ۴ تا ۱۵)",
    "ctr_opportunity": "نمایش بالا / کلیک کم (بهبود عنوان و متا)",
    "cannibalization_candidate": "هم‌نوع‌خواری کلمه کلیدی بین صفحات",
    "internal_link": "فرصت لینک داخلی",
    "ga4_traffic_no_conversion": "ترافیک بدون تبدیل (GA4)",
    "ga4_low_engagement": "تعامل پایین بازدیدکننده (GA4)",
    "ga4_traffic_drop": "افت ترافیک (GA4)",
}

BacklinkStatus = Literal["active", "lost", "unverified"]
ReportageStatus = Literal["pending", "published", "link_found", "link_missing", "article_missing", "target_changed"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _rows(cx, sql: str, **params) -> list[dict[str, Any]]:
    res = cx.execute(text(sql), params)
    cols = list(res.keys())
    return [dict(zip(cols, r)) for r in res.fetchall()]


def _one(cx, sql: str, **params) -> dict[str, Any] | None:
    got = _rows(cx, sql, **params)
    return got[0] if got else None


# ---------------------------------------------------------------- GSC helpers

def _gsc_bounds(cx, site_id: str) -> tuple[str | None, str | None]:
    r = _one(cx, """SELECT MIN(date) AS a, MAX(date) AS b FROM (
        SELECT date FROM gsc_daily WHERE site_id=:s
        UNION ALL SELECT date FROM gsc_property_daily WHERE site_id=:s AND search_type='web')""", s=site_id)
    return (r["a"], r["b"]) if r else (None, None)


def _win(max_date: str, days: int) -> tuple[str, str, str, str]:
    """current (from..to) and previous (from..to) date windows ending at max_date."""
    end = datetime.fromisoformat(max_date)
    cur_from = (end - timedelta(days=days - 1)).date().isoformat()
    prev_to = (end - timedelta(days=days)).date().isoformat()
    prev_from = (end - timedelta(days=2 * days - 1)).date().isoformat()
    return cur_from, max_date, prev_from, prev_to


_GSC_TOTALS = """
SELECT COALESCE(SUM(clicks),0) AS clicks, COALESCE(SUM(impressions),0) AS impressions,
       CASE WHEN SUM(impressions)>0 THEN 1.0*SUM(clicks)/SUM(impressions) END AS ctr,
       CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) END AS position
FROM {table} WHERE site_id=:s AND date BETWEEN :a AND :b {filter}
"""


def _gsc_block(cx, site_id: str, days: int) -> dict[str, Any]:
    lo, hi = _gsc_bounds(cx, site_id)
    if not hi:
        return {"available": False}
    cur_from, cur_to, prev_from, prev_to = _win(hi, days)
    property_count = (_one(cx, """SELECT COUNT(*) AS n FROM gsc_property_daily
        WHERE site_id=:s AND search_type='web' AND date BETWEEN :a AND :b""",
        s=site_id, a=cur_from, b=cur_to) or {}).get("n", 0)
    source = "gsc_property_daily" if property_count else "gsc_daily"
    table = source  # both values are constants above, never user input
    source_filter = "AND search_type='web'" if property_count else ""
    cur = _one(cx, _GSC_TOTALS.format(table=table, filter=source_filter), s=site_id, a=cur_from, b=cur_to) or {}
    prev = _one(cx, _GSC_TOTALS.format(table=table, filter=source_filter), s=site_id, a=prev_from, b=prev_to) or {}
    series = _rows(cx, f"""
        SELECT date, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
               CASE WHEN SUM(impressions)>0 THEN ROUND(SUM(position*impressions)/SUM(impressions), 2) END AS position
        FROM {table} WHERE site_id=:s AND date BETWEEN :a AND :b {source_filter}
        GROUP BY date ORDER BY date""",
        s=site_id, a=cur_from, b=cur_to)
    provenance = _one(cx, f"""SELECT sync_run_id, {"property" if property_count else "NULL AS property"}
        FROM {table} WHERE site_id=:s AND date BETWEEN :a AND :b {source_filter}
        ORDER BY date DESC LIMIT 1""", s=site_id, a=cur_from, b=cur_to) or {}
    metric_ref = {"source": source, "grain": "property_date" if property_count else "page_query_country_device_date",
                  "site_id": site_id, "search_type": "web", "property": provenance.get("property"),
                  "sync_run_id": provenance.get("sync_run_id"), "period_start": cur_from, "period_end": cur_to,
                  "covered_days": len(series), "expected_days": days,
                  "coverage_status": "ready" if property_count and len(series) == days else "partial"}
    return {"available": True, "date_from": lo, "date_to": hi,
            "window": {"from": cur_from, "to": cur_to, "days": days},
            "totals": cur, "previous": prev if prev.get("impressions") else None, "timeseries": series,
            "metric_ref": metric_ref}


def _keyword_perf(cx, site_id: str, keyword: str, days: int) -> dict[str, Any] | None:
    """Real GSC numbers for one exact query. Impression-weighted position, like gsc/sync.py."""
    lo, hi = _gsc_bounds(cx, site_id)
    if not hi:
        agg = _one(cx, """
            SELECT SUM(clicks) AS clicks, SUM(impressions) AS impressions,
                   CASE WHEN SUM(impressions)>0 THEN 1.0*SUM(clicks)/SUM(impressions) END AS ctr,
                   CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) END AS position,
                   MIN(date_from) AS date_from, MAX(date_to) AS date_to
            FROM gsc_query_page WHERE site_id=:s AND query=:q""", s=site_id, q=keyword)
        if not agg or not agg.get("impressions"):
            return None
        page = _one(cx, """SELECT page FROM gsc_query_page WHERE site_id=:s AND query=:q
                           ORDER BY clicks DESC, impressions DESC LIMIT 1""", s=site_id, q=keyword)
        return {**agg, "prev_position": None, "landing_page": page["page"] if page else None, "source": "gsc_query_page"}
    cur_from, cur_to, prev_from, prev_to = _win(hi, days)
    base = """
        SELECT SUM(clicks) AS clicks, SUM(impressions) AS impressions,
               CASE WHEN SUM(impressions)>0 THEN 1.0*SUM(clicks)/SUM(impressions) END AS ctr,
               CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) END AS position
        FROM gsc_daily WHERE site_id=:s AND query=:q AND date BETWEEN :a AND :b"""
    cur = _one(cx, base, s=site_id, q=keyword, a=cur_from, b=cur_to)
    if not cur or not cur.get("impressions"):
        return None
    prev = _one(cx, base, s=site_id, q=keyword, a=prev_from, b=prev_to) or {}
    page = _one(cx, """SELECT page FROM gsc_daily WHERE site_id=:s AND query=:q AND date BETWEEN :a AND :b
                       GROUP BY page ORDER BY SUM(clicks) DESC, SUM(impressions) DESC LIMIT 1""",
                s=site_id, q=keyword, a=cur_from, b=cur_to)
    return {**cur, "prev_position": prev.get("position"), "landing_page": page["page"] if page else None,
            "date_from": cur_from, "date_to": cur_to, "source": "gsc_daily"}


def _main_keyword(cx, site_id: str) -> str | None:
    r = _one(cx, "SELECT value FROM site_settings WHERE site_id=:s AND key='report'", s=site_id)
    if not r:
        return None
    try:
        return (json.loads(r["value"]) or {}).get("main_keyword") or None
    except Exception:
        return None


# ---------------------------------------------------------------- aggregate report

CONNECTION_KINDS = ("gsc", "wordpress", "ga4")


def _connections(cx, site_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Connected/disconnected per integration: configured (from the scheduler plan) + last tested state."""
    tested = {r["kind"]: r for r in _rows(cx,
        "SELECT kind, status, tested_at FROM site_connections WHERE site_id=:s", s=site_id)}
    out: dict[str, Any] = {}
    for kind in CONNECTION_KINDS:
        src = (plan.get("sources") or {}).get(kind) or {}
        t = tested.get(kind)
        out[kind] = {"configured": bool(src.get("configured")),
                     "connected": bool(src.get("configured")) and (t or {}).get("status") != "failed",
                     "tested_status": (t or {}).get("status"), "tested_at": (t or {}).get("tested_at"),
                     "last_success": src.get("last_success"), "next_at": src.get("next_at")}
    return out


def _sync_history(cx, site_id: str, limit: int = 15) -> list[dict[str, Any]]:
    rows = _rows(cx, """
        SELECT source, status, started_at, finished_at, rows_written FROM sync_runs
        WHERE site_id=:s AND source IN ('wordpress_pipeline','gsc_pipeline','ga4_pipeline','wordpress','gsc','ga4','analysis','graph')
        ORDER BY started_at DESC, id DESC LIMIT :lim""", s=site_id, lim=limit)
    for r in rows:
        dur = None
        try:
            if r["started_at"] and r["finished_at"]:
                a = datetime.fromisoformat(r["started_at"].replace("Z", "+00:00"))
                b = datetime.fromisoformat(r["finished_at"].replace("Z", "+00:00"))
                dur = max(0, round((b - a).total_seconds()))
        except ValueError:
            pass
        r["duration_seconds"] = dur
    return rows


def _crawl_coverage(cx, site_id: str) -> dict[str, Any]:
    """Expose the crawl budget and its limits alongside SEO health numbers."""
    latest = _one(cx, """SELECT run_id,status,started_at,finished_at,max_urls,urls_crawled,notes
        FROM crawl_runs WHERE site_id=:s ORDER BY started_at DESC LIMIT 1""", s=site_id)
    if not latest:
        return {"status": "not_started", "coverage_status": "not_started",
                "sitemap_urls": 0, "recent_crawled": 0, "window_days": 30,
                "latest_crawled": 0, "max_urls": None, "started_at": None}
    try:
        notes = json.loads(latest.get("notes") or "{}")
    except (ValueError, TypeError):
        notes = {}
    if not isinstance(notes, dict):
        notes = {}
    sitemap_urls = max(0, int(notes.get("sitemap_urls") or 0))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
    recent = (_one(cx, """SELECT COUNT(*) AS n FROM pages WHERE site_id=:s AND in_sitemap=1
        AND crawl_status='ok' AND last_crawled>=:cutoff""", s=site_id, cutoff=cutoff) or {}).get("n", 0)
    complete = latest["status"] in {"completed", "completed_capped"} and sitemap_urls > 0 and recent >= sitemap_urls
    return {"status": latest["status"], "coverage_status": "complete" if complete else "partial",
            "sitemap_urls": sitemap_urls, "recent_crawled": int(recent), "window_days": 30,
            "latest_crawled": int(latest.get("urls_crawled") or 0), "max_urls": latest.get("max_urls"),
            "started_at": latest.get("started_at"), "run_id": latest.get("run_id")}


@router.get("")
def full_report(site_id: str, days: int = Query(default=28, ge=7, le=365), eng: Engine = Depends(engine)) -> dict[str, Any]:
    """گزارش تجمیعی هر سایت: summary + وضعیت اتصال‌ها + تاریخچه همگام‌سازی — یک فراخوانی برای کل صفحه گزارش."""
    body = report_summary(site_id, days, eng)
    with eng.connect() as cx:
        connections = _connections(cx, site_id, body["freshness"]["auto_sync"])
        history = _sync_history(cx, site_id)
    running = any(r["status"] in ("queued", "running") for r in history)
    return {**body, "connections": connections, "sync_history": history, "sync_running": running}


# ---------------------------------------------------------------- summary

@router.get("/summary")
def report_summary(site_id: str, days: int = Query(default=28, ge=7, le=365), eng: Engine = Depends(engine)) -> dict[str, Any]:
    with eng.connect() as cx:
        site = _one(cx, "SELECT site_id, name, canonical_url, gsc_property, ga4_property, wp_url FROM sites WHERE site_id=:s", s=site_id)
        gsc = _gsc_block(cx, site_id, days)
        crawl_coverage = _crawl_coverage(cx, site_id)

        ga4 = {"available": False}
        ga4_bounds = _one(cx, """
            SELECT MIN(date) AS a, MAX(date) AS b FROM (
                SELECT date FROM ga4_daily WHERE site_id=:s AND source='page'
                UNION ALL SELECT date FROM ga4_site_daily WHERE site_id=:s AND channel='')""", s=site_id) or {}
        if ga4_bounds.get("b"):
            window_from, window_to, _, _ = _win(
                gsc["window"]["to"] if gsc["available"] else ga4_bounds["b"], days)
            site_days = (_one(cx, """SELECT COUNT(*) AS n FROM ga4_site_daily
                WHERE site_id=:s AND channel='' AND date BETWEEN :a AND :b""",
                s=site_id, a=window_from, b=window_to) or {}).get("n", 0)
            if site_days:
                g = _one(cx, """SELECT COALESCE(SUM(sessions),0) AS sessions, NULL AS users,
                    COALESCE(SUM(conversions),0) AS conversions, NULL AS engagement_rate
                    FROM ga4_site_daily WHERE site_id=:s AND channel='' AND date BETWEEN :a AND :b""",
                    s=site_id, a=window_from, b=window_to) or {}
                ga4_series = _rows(cx, """SELECT date, sessions, total_users AS users FROM ga4_site_daily
                    WHERE site_id=:s AND channel='' AND date BETWEEN :a AND :b ORDER BY date""",
                    s=site_id, a=window_from, b=window_to)
                channels = _rows(cx, """SELECT channel, SUM(sessions) AS sessions,
                    SUM(conversions) AS conversions FROM ga4_site_daily
                    WHERE site_id=:s AND channel!='' AND date BETWEEN :a AND :b
                    GROUP BY channel ORDER BY sessions DESC""", s=site_id, a=window_from, b=window_to)
                source = "ga4_site_daily"
            else:
                g = _one(cx, """
                    SELECT COALESCE(SUM(sessions),0) AS sessions, COALESCE(SUM(total_users),0) AS users,
                           COALESCE(SUM(conversions),0) AS conversions,
                           CASE WHEN SUM(sessions)>0 THEN SUM(engagement_rate*sessions)/SUM(sessions) END AS engagement_rate
                    FROM ga4_daily WHERE site_id=:s AND source='page' AND date BETWEEN :a AND :b""",
                    s=site_id, a=window_from, b=window_to) or {}
                ga4_series = _rows(cx, """
                    SELECT date, SUM(sessions) AS sessions, SUM(total_users) AS users FROM ga4_daily
                    WHERE site_id=:s AND source='page' AND date BETWEEN :a AND :b
                    GROUP BY date ORDER BY date""", s=site_id, a=window_from, b=window_to)
                channels = []
                source = "ga4_daily"
            ga4 = {"available": True, "date_from": ga4_bounds["a"], "date_to": ga4_bounds["b"],
                   "window": {"from": window_from, "to": window_to, "days": days}, "totals": {
                "sessions": g["sessions"], "users": g["users"], "conversions": g["conversions"],
                "engagement_rate": g["engagement_rate"]}, "timeseries": ga4_series, "channels": channels,
                "metric_ref": {"source": source, "grain": "site_date" if site_days else "page_date",
                               "covered_days": len(ga4_series), "expected_days": days,
                               "coverage_status": "ready" if site_days and len(ga4_series) == days else "partial",
                               "period_start": window_from, "period_end": window_to}}

        sev = {r["severity"]: r["n"] for r in _rows(cx,
            "SELECT severity, COUNT(*) AS n FROM seo_problems WHERE site_id=:s GROUP BY severity", s=site_id)}
        counts = {
            "indexable_pages": (_one(cx, "SELECT COUNT(*) AS n FROM pages WHERE site_id=:s AND indexable=1", s=site_id) or {}).get("n", 0),
            "keywords": (_one(cx, "SELECT COUNT(*) AS n FROM keywords WHERE site_id=:s", s=site_id) or {}).get("n", 0),
            "gsc_queries": (_one(cx, "SELECT COUNT(DISTINCT query) AS n FROM gsc_daily WHERE site_id=:s", s=site_id) or {}).get("n", 0),
            "problems": {"high": sev.get("high", 0), "medium": sev.get("medium", 0), "low": sev.get("low", 0),
                         "total": sum(sev.values())},
            "opportunities": (_one(cx, "SELECT COUNT(*) AS n FROM seo_opportunities WHERE site_id=:s", s=site_id) or {}).get("n", 0),
            "backlinks": (_one(cx, "SELECT COUNT(*) AS n FROM backlinks WHERE site_id=:s AND status!='lost'", s=site_id) or {}).get("n", 0),
            "reportages": (_one(cx, "SELECT COUNT(*) AS n FROM reportages WHERE site_id=:s", s=site_id) or {}).get("n", 0),
            "referring_domains": (_one(cx, """
                SELECT COUNT(*) AS n FROM (
                    SELECT source_domain AS d FROM backlinks WHERE site_id=:s AND status!='lost'
                    UNION SELECT publication_domain FROM reportages WHERE site_id=:s AND status IN ('published','link_found'))""",
                s=site_id) or {}).get("n", 0),
        }

        # health score: transparent, derived only from real signals (problems + connections)
        penalty = min(45.0, 3.0 * counts["problems"]["high"] + 1.0 * counts["problems"]["medium"] + 0.25 * counts["problems"]["low"])
        conn_penalty = (0 if gsc["available"] else 10) + (0 if ga4["available"] else 5)
        score = max(0, round(100 - penalty - conn_penalty))

        mk = _main_keyword(cx, site_id)
        main_keyword = {"keyword": mk, "performance": _keyword_perf(cx, site_id, mk, days) if mk else None}

        last_runs = _rows(cx, """
            SELECT source, MAX(COALESCE(finished_at, started_at)) AS at, status FROM sync_runs
            WHERE site_id=:s AND status IN ('completed','succeeded') AND source IN ('wordpress','gsc','ga4','analysis','graph')
            GROUP BY source""", s=site_id)
    plan = plan_for_site(eng, site_id)
    return {"site": site, "generated_at": _now(), "days": days, "score": score,
            "score_breakdown": {"problems_penalty": penalty, "connections_penalty": conn_penalty},
            "gsc": gsc, "ga4": ga4, "counts": counts, "main_keyword": main_keyword,
            "crawl_coverage": crawl_coverage,
            "freshness": {"last_runs": {r["source"]: r["at"] for r in last_runs}, "auto_sync": plan}}


_INVENTORY_CTE = """
WITH known AS (
    SELECT url, 1 AS wordpress, 0 AS crawled, 0 AS sitemap, 0 AS gsc,
           created_at AS first_seen, updated_at AS last_seen
    FROM posts WHERE site_id=:s AND url!=''
    UNION ALL
    SELECT url, 0, CASE WHEN last_crawled IS NOT NULL THEN 1 ELSE 0 END,
           COALESCE(in_sitemap,0), 0, created_at, COALESCE(last_crawled,updated_at)
    FROM pages WHERE site_id=:s AND url!=''
    UNION ALL
    SELECT page, 0, 0, 0, 1, MIN(date), MAX(date)
    FROM gsc_daily WHERE site_id=:s AND page!='' GROUP BY page
), inventory AS (
    SELECT url, MAX(wordpress) AS wordpress, MAX(crawled) AS crawled,
           MAX(sitemap) AS sitemap, MAX(gsc) AS gsc,
           MIN(first_seen) AS first_seen, MAX(last_seen) AS last_seen
    FROM known GROUP BY url
)
"""


@router.get("/inventory")
def page_inventory(site_id: str, q: str | None = None,
                   source: Literal["wordpress", "crawl", "sitemap", "gsc"] | None = None,
                   limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                   eng: Engine = Depends(engine)) -> dict[str, Any]:
    """Known URLs across independent sources; discovered is not claimed as every URL on the site."""
    clauses = []
    params: dict[str, Any] = {"s": site_id, "lim": limit, "off": offset}
    if q:
        clauses.append("i.url LIKE :q")
        params["q"] = "%" + q.strip() + "%"
    if source:
        clauses.append({"wordpress": "i.wordpress=1", "crawl": "i.crawled=1",
                        "sitemap": "i.sitemap=1", "gsc": "i.gsc=1"}[source])
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with eng.connect() as cx:
        summary = _one(cx, _INVENTORY_CTE + """SELECT COUNT(*) AS discovered,
            COALESCE(SUM(wordpress),0) AS wordpress, COALESCE(SUM(crawled),0) AS crawled,
            COALESCE(SUM(sitemap),0) AS sitemap, COALESCE(SUM(gsc),0) AS gsc
            FROM inventory""", s=site_id) or {}
        total = (_one(cx, _INVENTORY_CTE + f"SELECT COUNT(*) AS n FROM inventory i {where}", **params) or {}).get("n", 0)
        items = _rows(cx, _INVENTORY_CTE + f"""
            SELECT i.url, i.wordpress, i.crawled, i.sitemap, i.gsc, i.first_seen, i.last_seen,
                   p.type AS wp_type, p.status AS wp_status, p.title AS wp_title,
                   c.status_code, c.crawl_status, c.indexable, c.indexability_reason,
                   c.final_url, c.canonical, c.last_crawled
            FROM inventory i
            LEFT JOIN posts p ON p.site_id=:s AND p.url=i.url
            LEFT JOIN pages c ON c.site_id=:s AND c.url=i.url
            {where} ORDER BY i.url LIMIT :lim OFFSET :off""", **params)
    for item in items:
        item["sources"] = [key for key in ("wordpress", "sitemap", "crawled", "gsc") if item[key]]
        item["indexability_source"] = "crawler" if item["indexable"] is not None else None
    return {"summary": summary, "items": items, "total": total, "limit": limit, "offset": offset,
            "coverage_note": "فقط URLهای شناخته‌شده از منابع متصل؛ شمار کل صفحات واقعی سایت نیست."}


@router.get("/inventory/page")
def inventory_page(site_id: str, url: str = Query(min_length=8), eng: Engine = Depends(engine)) -> dict[str, Any]:
    """One URL's observed facts; canonical and redirects remain evidence, not an automatic identity merge."""
    from urllib.parse import urlsplit
    from ...normalizer import normalize_url

    with eng.connect() as cx:
        site = _one(cx, "SELECT canonical_url FROM sites WHERE site_id=:s", s=site_id) or {}
        host = urlsplit(site.get("canonical_url") or "").hostname
        normalized = normalize_url(url, site_host=host)
        item = _one(cx, _INVENTORY_CTE + """SELECT * FROM inventory WHERE url=:url""",
                    s=site_id, url=normalized)
        if not item:
            raise HTTPException(404, "URL not found in the known inventory")
        post = _one(cx, """SELECT type,status,title,modified_gmt,yoast_title,yoast_description
            FROM posts WHERE site_id=:s AND url=:url""", s=site_id, url=normalized)
        crawl = _one(cx, """SELECT status_code,crawl_status,indexable,indexability_reason,canonical,final_url,
            title,meta_description,word_count,depth,last_crawled,crawl_run_id,in_sitemap
            FROM pages WHERE site_id=:s AND url=:url""", s=site_id, url=normalized)
        search = _one(cx, """SELECT MIN(date) AS date_from, MAX(date) AS date_to,
            SUM(clicks) AS clicks, SUM(impressions) AS impressions,
            COUNT(DISTINCT query) AS query_count FROM gsc_daily WHERE site_id=:s AND page=:url""",
            s=site_id, url=normalized)
        problems = _rows(cx, """SELECT problem_type,severity,detail,created_at FROM seo_problems
            WHERE site_id=:s AND url=:url ORDER BY created_at DESC LIMIT 50""", s=site_id, url=normalized)
    return {"url": normalized, "sources": [k for k in ("wordpress", "sitemap", "crawled", "gsc") if item[k]],
            "first_seen": item["first_seen"], "last_seen": item["last_seen"],
            "wordpress": post, "crawl": crawl, "gsc_page_query_rows": search if search.get("date_to") else None,
            "problems": problems, "note": "دادهٔ GSC صفحه از ردیف‌های page/query است و ممکن است کامل نباشد."}


@router.get("/monthly")
def monthly_progress(site_id: str, months: int = Query(12, ge=1, le=24),
                     through: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
                     eng: Engine = Depends(engine)) -> dict[str, Any]:
    """Monthly site trends with source and day coverage; no claim that a partial month is final."""
    import calendar

    try:
        last = datetime.strptime(through, "%Y-%m").date() if through else datetime.now(timezone.utc).date().replace(day=1)
    except ValueError as exc:
        raise HTTPException(422, "invalid month") from exc
    keys = []
    year, month = last.year, last.month
    for _ in range(months):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    keys.reverse()
    with eng.connect() as cx:
        rows = []
        for key in keys:
            first = key + "-01"
            last_day = calendar.monthrange(int(key[:4]), int(key[5:]))[1]
            end = f"{key}-{last_day:02d}"
            property_days = (_one(cx, """SELECT COUNT(*) AS n FROM gsc_property_daily
                WHERE site_id=:s AND search_type='web' AND date BETWEEN :a AND :b""",
                s=site_id, a=first, b=end) or {}).get("n", 0)
            gsc_source = "gsc_property_daily" if property_days else "gsc_daily"
            extra = "AND search_type='web'" if property_days else ""
            search = _one(cx, f"""SELECT COUNT(DISTINCT date) AS days, SUM(clicks) AS clicks,
                SUM(impressions) AS impressions FROM {gsc_source}
                WHERE site_id=:s AND date BETWEEN :a AND :b {extra}""", s=site_id, a=first, b=end) or {}
            site_days = (_one(cx, """SELECT COUNT(*) AS n FROM ga4_site_daily
                WHERE site_id=:s AND channel='' AND date BETWEEN :a AND :b""",
                s=site_id, a=first, b=end) or {}).get("n", 0)
            if site_days:
                analytics = _one(cx, """SELECT COUNT(*) AS days, SUM(sessions) AS sessions,
                    SUM(conversions) AS conversions FROM ga4_site_daily
                    WHERE site_id=:s AND channel='' AND date BETWEEN :a AND :b""",
                    s=site_id, a=first, b=end) or {}
            else:
                analytics = _one(cx, """SELECT COUNT(DISTINCT date) AS days, SUM(sessions) AS sessions,
                    SUM(conversions) AS conversions FROM ga4_daily
                    WHERE site_id=:s AND source='page' AND date BETWEEN :a AND :b""",
                    s=site_id, a=first, b=end) or {}
            complete_calendar = end < datetime.now(timezone.utc).date().isoformat()
            rows.append({"month": key, "gsc": {
                "clicks": search.get("clicks"), "impressions": search.get("impressions"),
                "source": gsc_source if search.get("days") else None,
                "covered_days": search.get("days") or 0, "expected_days": last_day,
                "status": "ready" if property_days == last_day and complete_calendar else
                          "partial" if search.get("days") else "missing"},
                "ga4": {"sessions": analytics.get("sessions"), "conversions": analytics.get("conversions"),
                        "source": ("ga4_site_daily" if site_days else "ga4_daily") if analytics.get("days") else None,
                        "covered_days": analytics.get("days") or 0, "expected_days": last_day,
                        "status": "ready" if site_days == last_day and complete_calendar else
                                  "partial" if analytics.get("days") else "missing"}})
    return {"site_id": site_id, "months": rows, "note": "ماه‌های ناقص و داده‌های صفحه‌ای برای نتیجه‌گیری قطعی مناسب نیستند."}


# ---------------------------------------------------------------- main keyword

class MainKeywordIn(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)


@router.get("/main-keyword")
def get_main_keyword(site_id: str, days: int = Query(default=28, ge=7, le=365), eng: Engine = Depends(engine)) -> dict[str, Any]:
    with eng.connect() as cx:
        mk = _main_keyword(cx, site_id)
        suggestions = _rows(cx, """
            SELECT query, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
                   CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) END AS position
            FROM gsc_daily WHERE site_id=:s GROUP BY query ORDER BY SUM(clicks) DESC LIMIT 10""", s=site_id)
        return {"keyword": mk, "performance": _keyword_perf(cx, site_id, mk, days) if mk else None,
                "suggestions": suggestions}


@router.put("/main-keyword")
def set_main_keyword(site_id: str, body: MainKeywordIn, eng: Engine = Depends(engine)) -> dict[str, Any]:
    kw = body.keyword.strip()
    with eng.begin() as cx:
        cur = _one(cx, "SELECT value FROM site_settings WHERE site_id=:s AND key='report'", s=site_id)
        try:
            value = json.loads(cur["value"]) if cur else {}
        except Exception:
            value = {}
        value["main_keyword"] = kw
        cx.execute(text("""INSERT INTO site_settings(site_id, key, value, updated_at) VALUES(:s,'report',:v,:u)
                           ON CONFLICT(site_id, key) DO UPDATE SET value=:v, updated_at=:u"""),
                   {"s": site_id, "v": json.dumps(value, ensure_ascii=False), "u": _now()})
    with eng.connect() as cx:
        return {"keyword": kw, "performance": _keyword_perf(cx, site_id, kw, 28)}


# ---------------------------------------------------------------- keyword performance

@router.get("/keywords")
def keyword_performance(site_id: str, days: int = Query(default=28, ge=7, le=365),
                        q: str | None = None, min_impressions: int = Query(default=0, ge=0),
                        scope: Literal["all", "tracked"] = "all",
                        order: Literal["clicks", "impressions", "position", "ctr", "change"] = "clicks",
                        dir: Literal["asc", "desc"] = "desc",
                        limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0),
                        eng: Engine = Depends(engine)) -> dict[str, Any]:
    with eng.connect() as cx:
        tracked: set[str] | None = None
        if scope == "tracked":
            tracked = {r["keyword"] for r in _rows(cx, "SELECT keyword FROM keywords WHERE site_id=:s", s=site_id)}
        lo, hi = _gsc_bounds(cx, site_id)
        if not hi:
            return {"status": "NO_GSC_DATA", "items": [], "total": 0, "tracked_count": len(tracked or [])}
        cur_from, cur_to, prev_from, prev_to = _win(hi, days)
        like = f"%{q.strip()}%" if q and q.strip() else None
        rows = _rows(cx, f"""
            WITH cur AS (
                SELECT query, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
                       CASE WHEN SUM(impressions)>0 THEN 1.0*SUM(clicks)/SUM(impressions) END AS ctr,
                       CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) END AS position
                FROM gsc_daily WHERE site_id=:s AND date BETWEEN :a AND :b
                {"AND query LIKE :like" if like else ""}
                GROUP BY query HAVING SUM(impressions) >= :mi),
            prev AS (
                SELECT query, CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) END AS position
                FROM gsc_daily WHERE site_id=:s AND date BETWEEN :pa AND :pb GROUP BY query),
            pg AS (
                SELECT query, page, SUM(clicks) AS c,
                       ROW_NUMBER() OVER (PARTITION BY query ORDER BY SUM(clicks) DESC, SUM(impressions) DESC) AS rn
                FROM gsc_daily WHERE site_id=:s AND date BETWEEN :a AND :b GROUP BY query, page)
            SELECT cur.query, cur.clicks, cur.impressions, cur.ctr, cur.position,
                   prev.position AS prev_position,
                   CASE WHEN prev.position IS NOT NULL AND cur.position IS NOT NULL
                        THEN prev.position - cur.position END AS change,
                   pg.page AS landing_page
            FROM cur LEFT JOIN prev ON prev.query = cur.query
            LEFT JOIN pg ON pg.query = cur.query AND pg.rn = 1""",
            s=site_id, a=cur_from, b=cur_to, pa=prev_from, pb=prev_to, mi=min_impressions,
            **({"like": like} if like else {}))
        if tracked is not None:
            rows = [r for r in rows if r["query"] in tracked]
        key = {"clicks": lambda r: r["clicks"] or 0, "impressions": lambda r: r["impressions"] or 0,
               "position": lambda r: r["position"] if r["position"] is not None else 9999,
               "ctr": lambda r: r["ctr"] or 0, "change": lambda r: r["change"] if r["change"] is not None else -9999}[order]
        rows.sort(key=key, reverse=(dir == "desc"))
        total = len(rows)
        return {"status": "OK", "scope": scope, "tracked_count": len(tracked) if tracked is not None else None,
                "window": {"from": cur_from, "to": cur_to, "days": days,
                           "previous": {"from": prev_from, "to": prev_to}},
                "total": total, "items": rows[offset:offset + limit]}


# ---------------------------------------------------------------- problems & opportunities

@router.get("/problems")
def report_problems(site_id: str, severity: Literal["high", "medium", "low"] | None = None,
                    category: str | None = None, limit: int = Query(default=500, ge=1, le=2000),
                    eng: Engine = Depends(engine)) -> dict[str, Any]:
    with eng.connect() as cx:
        rows = _rows(cx, """
            SELECT id, problem_type, severity, url, related_url, detail, created_at FROM seo_problems
            WHERE site_id=:s ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, problem_type
            LIMIT :lim""", s=site_id, lim=limit)
    items = []
    for r in rows:
        cat = PROBLEM_CATEGORY.get(r["problem_type"], "other")
        if severity and r["severity"] != severity:
            continue
        if category and cat != category:
            continue
        try:
            detail = json.loads(r["detail"]) if r["detail"] else None
        except Exception:
            detail = r["detail"]
        items.append({**r, "detail": detail, "category": cat, "category_fa": CATEGORY_FA[cat],
                      "title_fa": PROBLEM_FA.get(r["problem_type"], r["problem_type"]), "source": "crawler"})
    summary: dict[str, dict[str, Any]] = {}
    for it in items:
        b = summary.setdefault(it["problem_type"], {"count": 0, "severity": it["severity"],
                                                     "category": it["category"], "category_fa": it["category_fa"],
                                                     "title_fa": it["title_fa"]})
        b["count"] += 1
    return {"summary": summary, "items": items, "categories": CATEGORY_FA}


@router.get("/opportunities")
def report_opportunities(site_id: str, opp_type: str | None = None,
                         limit: int = Query(default=200, ge=1, le=1000),
                         eng: Engine = Depends(engine)) -> dict[str, Any]:
    with eng.connect() as cx:
        rows = _rows(cx, f"""
            SELECT id, opp_type, url, related_url, query, score, reason, confidence, detail, created_at
            FROM seo_opportunities WHERE site_id=:s {"AND opp_type=:t" if opp_type else ""}
            ORDER BY score DESC LIMIT :lim""", s=site_id, lim=limit, **({"t": opp_type} if opp_type else {}))
    for r in rows:
        try:
            r["detail"] = json.loads(r["detail"]) if r["detail"] else None
        except Exception:
            pass
        r["type_fa"] = OPP_FA.get(r["opp_type"], r["opp_type"])
    by_type: dict[str, int] = {}
    for r in rows:
        by_type[r["opp_type"]] = by_type.get(r["opp_type"], 0) + 1
    return {"summary": {t: {"count": n, "type_fa": OPP_FA.get(t, t)} for t, n in by_type.items()}, "items": rows}


# ---------------------------------------------------------------- backlinks (manual store + provider abstraction)

class BacklinkIn(BaseModel):
    source_url: str = Field(min_length=8, max_length=2000)
    target_url: str = Field(min_length=8, max_length=2000)
    anchor_text: str | None = Field(default=None, max_length=500)
    link_type: str = Field(default="generic", max_length=40)
    rel: str | None = Field(default=None, max_length=40)
    first_seen: str | None = None
    status: BacklinkStatus = "unverified"
    notes: str | None = Field(default=None, max_length=2000)


def _domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


@router.get("/backlinks")
def list_backlinks(site_id: str, status: BacklinkStatus | None = None, eng: Engine = Depends(engine)) -> dict[str, Any]:
    with eng.connect() as cx:
        rows = _rows(cx, f"""
            SELECT id, source_url, source_domain, target_url, anchor_text, link_type, rel, provider,
                   first_seen, last_seen, status, notes, created_at, updated_at
            FROM backlinks WHERE site_id=:s {"AND status=:st" if status else ""} ORDER BY created_at DESC""",
            s=site_id, **({"st": status} if status else {}))
        anchors = _rows(cx, """
            SELECT anchor_text, COUNT(*) AS backlinks, COUNT(DISTINCT source_domain) AS domains
            FROM backlinks WHERE site_id=:s AND status!='lost' AND COALESCE(anchor_text,'')!=''
            GROUP BY anchor_text ORDER BY backlinks DESC LIMIT 20""", s=site_id)
    totals = {"total": len(rows),
              "active": sum(1 for r in rows if r["status"] == "active"),
              "lost": sum(1 for r in rows if r["status"] == "lost"),
              "follow": sum(1 for r in rows if (r["rel"] or "follow") == "follow" and r["status"] != "lost"),
              "nofollow": sum(1 for r in rows if r["rel"] in ("nofollow", "sponsored", "ugc") and r["status"] != "lost"),
              "referring_domains": len({r["source_domain"] for r in rows if r["status"] != "lost"})}
    return {"provider": None, "provider_note": "منبع بک‌لینک خارجی متصل نیست؛ رکوردها دستی/ریپورتاژ هستند.",
            "totals": totals, "top_anchors": anchors, "items": rows}


@router.post("/backlinks", status_code=201)
def create_backlink(site_id: str, body: BacklinkIn, eng: Engine = Depends(engine)) -> dict[str, Any]:
    now = _now()
    with eng.begin() as cx:
        try:
            r = cx.execute(text("""
                INSERT INTO backlinks(site_id, source_url, source_domain, target_url, anchor_text, link_type, rel,
                                      provider, first_seen, last_seen, status, notes, created_at, updated_at)
                VALUES(:s,:su,:sd,:tu,:a,:lt,:rel,'manual',:fs,:fs,:st,:no,:now,:now)"""),
                {"s": site_id, "su": body.source_url.strip(), "sd": _domain(body.source_url),
                 "tu": body.target_url.strip(), "a": body.anchor_text, "lt": body.link_type, "rel": body.rel,
                 "fs": body.first_seen or now[:10], "st": body.status, "no": body.notes, "now": now})
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(409, "این بک‌لینک قبلاً ثبت شده است") from exc
            raise
        new_id = r.lastrowid
    return {"id": new_id}


@router.put("/backlinks/{backlink_id}")
def update_backlink(site_id: str, backlink_id: int, body: BacklinkIn, eng: Engine = Depends(engine)) -> dict[str, Any]:
    with eng.begin() as cx:
        r = cx.execute(text("""
            UPDATE backlinks SET source_url=:su, source_domain=:sd, target_url=:tu, anchor_text=:a,
                   link_type=:lt, rel=:rel, status=:st, notes=:no, updated_at=:now
            WHERE site_id=:s AND id=:i"""),
            {"s": site_id, "i": backlink_id, "su": body.source_url.strip(), "sd": _domain(body.source_url),
             "tu": body.target_url.strip(), "a": body.anchor_text, "lt": body.link_type, "rel": body.rel,
             "st": body.status, "no": body.notes, "now": _now()})
        if r.rowcount == 0:
            raise HTTPException(404, "backlink not found")
    return {"ok": True}


@router.delete("/backlinks/{backlink_id}")
def delete_backlink(site_id: str, backlink_id: int, eng: Engine = Depends(engine)) -> dict[str, Any]:
    with eng.begin() as cx:
        r = cx.execute(text("DELETE FROM backlinks WHERE site_id=:s AND id=:i"), {"s": site_id, "i": backlink_id})
        if r.rowcount == 0:
            raise HTTPException(404, "backlink not found")
    return {"ok": True}


# ---------------------------------------------------------------- reportages

class ReportageIn(BaseModel):
    article_url: str = Field(min_length=8, max_length=2000)
    target_url: str = Field(min_length=8, max_length=2000)
    anchor_text: str | None = Field(default=None, max_length=500)
    target_keyword: str | None = Field(default=None, max_length=200)
    publication_date: str | None = None
    link_type: str | None = Field(default=None, max_length=40)
    cost: int | None = Field(default=None, ge=0)
    status: ReportageStatus = "pending"
    notes: str | None = Field(default=None, max_length=2000)


_REPORTAGE_COLS = """id, publication_domain, article_url, target_url, anchor_text, target_keyword,
publication_date, link_type, cost, status, verified_rel, last_verified_at, verify_detail, notes, created_at, updated_at"""


@router.get("/reportages")
def list_reportages(site_id: str, status: ReportageStatus | None = None, eng: Engine = Depends(engine)) -> dict[str, Any]:
    with eng.connect() as cx:
        rows = _rows(cx, f"""SELECT {_REPORTAGE_COLS} FROM reportages WHERE site_id=:s
                             {"AND status=:st" if status else ""} ORDER BY COALESCE(publication_date, created_at) DESC""",
                     s=site_id, **({"st": status} if status else {}))
    for r in rows:
        try:
            r["verify_detail"] = json.loads(r["verify_detail"]) if r["verify_detail"] else None
        except Exception:
            pass
    totals = {"total": len(rows),
              "link_found": sum(1 for r in rows if r["status"] == "link_found"),
              "link_missing": sum(1 for r in rows if r["status"] in ("link_missing", "article_missing", "target_changed")),
              "pending": sum(1 for r in rows if r["status"] in ("pending", "published")),
              "cost_total": sum(r["cost"] or 0 for r in rows)}
    return {"totals": totals, "items": rows}


@router.post("/reportages", status_code=201)
def create_reportage(site_id: str, body: ReportageIn, eng: Engine = Depends(engine)) -> dict[str, Any]:
    now = _now()
    with eng.begin() as cx:
        try:
            r = cx.execute(text("""
                INSERT INTO reportages(site_id, publication_domain, article_url, target_url, anchor_text,
                                       target_keyword, publication_date, link_type, cost, status, notes,
                                       created_at, updated_at)
                VALUES(:s,:pd,:au,:tu,:a,:tk,:p,:lt,:c,:st,:no,:now,:now)"""),
                {"s": site_id, "pd": _domain(body.article_url), "au": body.article_url.strip(),
                 "tu": body.target_url.strip(), "a": body.anchor_text, "tk": body.target_keyword,
                 "p": body.publication_date, "lt": body.link_type, "c": body.cost, "st": body.status,
                 "no": body.notes, "now": now})
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(409, "این ریپورتاژ قبلاً ثبت شده است") from exc
            raise
        new_id = r.lastrowid
    return {"id": new_id}


@router.put("/reportages/{reportage_id}")
def update_reportage(site_id: str, reportage_id: int, body: ReportageIn, eng: Engine = Depends(engine)) -> dict[str, Any]:
    with eng.begin() as cx:
        r = cx.execute(text("""
            UPDATE reportages SET publication_domain=:pd, article_url=:au, target_url=:tu, anchor_text=:a,
                   target_keyword=:tk, publication_date=:p, link_type=:lt, cost=:c, status=:st, notes=:no, updated_at=:now
            WHERE site_id=:s AND id=:i"""),
            {"s": site_id, "i": reportage_id, "pd": _domain(body.article_url), "au": body.article_url.strip(),
             "tu": body.target_url.strip(), "a": body.anchor_text, "tk": body.target_keyword,
             "p": body.publication_date, "lt": body.link_type, "c": body.cost, "st": body.status,
             "no": body.notes, "now": _now()})
        if r.rowcount == 0:
            raise HTTPException(404, "reportage not found")
    return {"ok": True}


@router.delete("/reportages/{reportage_id}")
def delete_reportage(site_id: str, reportage_id: int, eng: Engine = Depends(engine)) -> dict[str, Any]:
    with eng.begin() as cx:
        r = cx.execute(text("DELETE FROM reportages WHERE site_id=:s AND id=:i"), {"s": site_id, "i": reportage_id})
        if r.rowcount == 0:
            raise HTTPException(404, "reportage not found")
    return {"ok": True}


def _norm_url(url: str) -> str:
    p = urlparse(unquote(url).strip().lower())
    host = (p.hostname or "").removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}"


def _check_article(article_url: str, target_url: str) -> dict[str, Any]:
    """Fetch the article (read-only, proxy-aware) and look for a link to target_url."""
    with ReadOnlyClient(user_agent="SEOBrainLinkCheck/1.0", timeout=25.0, max_retries=2, min_interval=0.0) as http:
        resp = http.get(article_url)
    if resp.status_code in (404, 410):
        return {"status": "article_missing", "http_status": resp.status_code}
    if resp.status_code >= 400:
        return {"status": None, "http_status": resp.status_code, "error": f"HTTP {resp.status_code}"}
    from bs4 import BeautifulSoup  # local import: keeps router import light
    soup = BeautifulSoup(resp.text, "lxml")
    want = _norm_url(target_url)
    want_host = want.split("/", 1)[0]
    found, same_host = None, None
    for a in soup.find_all("a", href=True):
        got = _norm_url(a["href"])
        if not got:
            continue
        if got == want:
            found = a
            break
        if got.split("/", 1)[0] == want_host and same_host is None:
            same_host = a
    if found is not None:
        rel = " ".join(found.get("rel") or []) or "follow"
        return {"status": "link_found", "http_status": resp.status_code, "rel": rel,
                "anchor": found.get_text(strip=True)[:200]}
    if same_host is not None:
        rel = " ".join(same_host.get("rel") or []) or "follow"
        return {"status": "target_changed", "http_status": resp.status_code, "rel": rel,
                "found_href": same_host["href"][:500], "anchor": same_host.get_text(strip=True)[:200]}
    return {"status": "link_missing", "http_status": resp.status_code}


@router.post("/reportages/{reportage_id}/verify")
def verify_reportage(site_id: str, reportage_id: int, eng: Engine = Depends(engine)) -> dict[str, Any]:
    with eng.connect() as cx:
        row = _one(cx, "SELECT article_url, target_url FROM reportages WHERE site_id=:s AND id=:i",
                   s=site_id, i=reportage_id)
    if not row:
        raise HTTPException(404, "reportage not found")
    try:
        result = _check_article(row["article_url"], row["target_url"])
    except Exception as exc:
        result = {"status": None, "error": str(exc)[:300]}
    now = _now()
    with eng.begin() as cx:
        if result.get("status"):
            cx.execute(text("""UPDATE reportages SET status=:st, verified_rel=:rel, last_verified_at=:t,
                               verify_detail=:d, updated_at=:t WHERE site_id=:s AND id=:i"""),
                       {"s": site_id, "i": reportage_id, "st": result["status"], "rel": result.get("rel"),
                        "t": now, "d": json.dumps(result, ensure_ascii=False)})
        else:
            cx.execute(text("""UPDATE reportages SET last_verified_at=:t, verify_detail=:d, updated_at=:t
                               WHERE site_id=:s AND id=:i"""),
                       {"s": site_id, "i": reportage_id, "t": now, "d": json.dumps(result, ensure_ascii=False)})
    return {"verified_at": now, **result}
