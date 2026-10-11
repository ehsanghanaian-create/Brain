"""Read-only URL inventory across crawler, WordPress and observed GSC pages.

This is a projection over source tables, not a claim that any source has complete
coverage. In particular, absent GSC rows never mean zero search traffic.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine, text

from ..deps import engine, require_site
from ..errors import ApiError

router = APIRouter(prefix="/sites/{site_id}/urls", tags=["url-inventory"], dependencies=[Depends(require_site)])

_URLS = """
WITH urls AS (
  SELECT url FROM pages WHERE site_id=:site_id AND url <> ''
  UNION SELECT url FROM posts WHERE site_id=:site_id AND url <> ''
  UNION SELECT url FROM categories WHERE site_id=:site_id AND url IS NOT NULL AND url <> ''
  UNION SELECT url FROM tags WHERE site_id=:site_id AND url IS NOT NULL AND url <> ''
  UNION SELECT page AS url FROM gsc_query_page WHERE site_id=:site_id AND page <> ''
), gsc AS (
  SELECT page, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
         CASE WHEN SUM(impressions)>0 THEN SUM(position * impressions) / SUM(impressions) ELSE NULL END AS position,
         MIN(date_from) AS date_from, MAX(date_to) AS date_to, MAX(updated_at) AS updated_at
  FROM gsc_query_page WHERE site_id=:site_id GROUP BY page
), wp_terms AS (
  SELECT url, MAX(name) AS name FROM (
    SELECT url, name FROM categories WHERE site_id=:site_id AND url IS NOT NULL
    UNION ALL SELECT url, name FROM tags WHERE site_id=:site_id AND url IS NOT NULL
  ) GROUP BY url
), inventory AS (
  SELECT u.url, COALESCE(p.title, wp.title, wt.name) AS title,
         wp.type AS wordpress_type, wp.status AS wordpress_status,
         p.crawl_status, p.status_code, p.indexable, p.canonical, p.in_sitemap,
         p.last_crawled, p.crawl_run_id,
         g.clicks AS gsc_clicks, g.impressions AS gsc_impressions, g.position AS gsc_position,
         g.date_from AS gsc_date_from, g.date_to AS gsc_date_to, g.updated_at AS gsc_updated_at,
         CASE WHEN wp.url IS NOT NULL OR wt.url IS NOT NULL THEN 1 ELSE 0 END AS has_wordpress,
         CASE WHEN p.url IS NOT NULL THEN 1 ELSE 0 END AS has_crawl,
         CASE WHEN g.page IS NOT NULL THEN 1 ELSE 0 END AS has_gsc
  FROM urls u
  LEFT JOIN pages p ON p.site_id=:site_id AND p.url=u.url
  LEFT JOIN posts wp ON wp.site_id=:site_id AND wp.url=u.url
  LEFT JOIN wp_terms wt ON wt.url=u.url
  LEFT JOIN gsc g ON g.page=u.url
)
"""

_FILTER = """WHERE (:search='' OR url LIKE :pattern OR title LIKE :pattern)
  AND (:source='all' OR (:source='wordpress' AND has_wordpress=1)
       OR (:source='crawl' AND has_crawl=1) OR (:source='gsc' AND has_gsc=1))"""


@router.get("")
def list_urls(
    site_id: str,
    search: str = Query("", max_length=200),
    source: Literal["all", "wordpress", "crawl", "gsc"] = "all",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    eng: Engine = Depends(engine),
) -> dict:
    params = {"site_id": site_id, "search": search.strip(), "pattern": f"%{search.strip()}%", "source": source,
              "limit": limit, "offset": offset}
    with eng.connect() as cx:
        total = int(cx.execute(text(_URLS + "SELECT COUNT(*) FROM inventory " + _FILTER), params).scalar() or 0)
        rows = cx.execute(text(_URLS + "SELECT * FROM inventory " + _FILTER + " ORDER BY url LIMIT :limit OFFSET :offset"), params).mappings().all()
        crawl = cx.execute(text("SELECT run_id, status, started_at, finished_at, max_urls, urls_crawled, urls_failed "
                                "FROM crawl_runs WHERE site_id=:site_id ORDER BY started_at DESC, id DESC LIMIT 1"), params).mappings().first()
        latest_gsc_date = cx.execute(text("SELECT MAX(date_to) FROM gsc_query_page WHERE site_id=:site_id"), params).scalar()
    items = []
    for row in rows:
        item = dict(row)
        item["sources"] = [name for name, flag in (("wordpress", "has_wordpress"), ("crawl", "has_crawl"), ("gsc", "has_gsc")) if item.pop(flag)]
        items.append(item)
    return {"site_id": site_id, "items": items, "total": total, "limit": limit, "offset": offset,
            "coverage": {"crawl": dict(crawl) if crawl else None, "gsc_latest_date": latest_gsc_date,
                         "gsc_scope": "observed_top_rows_only", "missing_source_means_zero": False}}


@router.get("/detail")
def url_detail(site_id: str, url: str = Query(min_length=8, max_length=2048),
               eng: Engine = Depends(engine)) -> dict:
    """One URL across source inventory, monthly GSC observations and durable issues.

    Months without observed rows are omitted rather than being filled with zero.
    Search Console's top-row export is partial, so even present monthly totals are
    labelled as observed rows rather than site-wide or absolute traffic.
    """
    params = {"site_id": site_id, "url": url}
    with eng.connect() as cx:
        row = cx.execute(text(_URLS + "SELECT * FROM inventory WHERE url=:url LIMIT 1"), params).mappings().first()
        if not row:
            raise ApiError(404, "این URL در داده‌های ثبت‌شدهٔ سایت پیدا نشد", code="not_found")
        months = cx.execute(text("""
            SELECT substr(date,1,7) AS month, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
                   CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) ELSE NULL END AS position,
                   MIN(date) AS date_from, MAX(date) AS date_to
            FROM gsc_daily WHERE site_id=:site_id AND page=:url
            GROUP BY substr(date,1,7) ORDER BY month DESC LIMIT 12
        """), params).mappings().all()
        latest = cx.execute(text("SELECT MAX(date) FROM gsc_daily WHERE site_id=:site_id AND page=:url"), params).scalar()
        queries = cx.execute(text("""
            SELECT query,SUM(clicks) AS clicks,SUM(impressions) AS impressions,
                   CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) ELSE NULL END AS position
            FROM gsc_daily WHERE site_id=:site_id AND page=:url
              AND date>=date((SELECT MAX(date) FROM gsc_daily WHERE site_id=:site_id AND page=:url),'-90 days')
            GROUP BY query ORDER BY impressions DESC,clicks DESC LIMIT 10
        """), params).mappings().all()
        issues = cx.execute(text("""
            SELECT id,problem_type,severity,status,first_seen,last_seen
            FROM issue_cases WHERE site_id=:site_id AND url=:url
            ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END,last_seen DESC LIMIT 20
        """), params).mappings().all()
        opportunity_count = int(cx.execute(text("""
            SELECT COUNT(*) FROM keyword_opportunities
            WHERE site_id=:site_id AND target_url=:url AND status='new'
        """), params).scalar() or 0)
    inventory = dict(row)
    inventory["sources"] = [source for source, flag in (("wordpress", "has_wordpress"), ("crawl", "has_crawl"), ("gsc", "has_gsc")) if inventory.pop(flag)]
    return {"site_id": site_id, "url": url, "inventory": inventory,
            "monthly_gsc": [dict(item) for item in reversed(months)],
            "gsc_latest_date": latest, "top_queries": [dict(item) for item in queries],
            "issue_cases": [dict(item) for item in issues], "new_keyword_opportunities": opportunity_count,
            "coverage": "gsc_observed_top_rows_only", "missing_month_means_zero": False}
