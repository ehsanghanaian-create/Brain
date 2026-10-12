"""Observed commercial search path for a site's sales objective.

GSC top rows are a partial sample of search activity. They are useful leading
signals for product and category landing pages, never orders or revenue.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
from time import time
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine, text

from ...db.repositories.base import utcnow
from ..deps import engine, require_site

router = APIRouter(prefix="/sites/{site_id}/commerce", tags=["commerce"], dependencies=[Depends(require_site)])


def _page_kind(url: str) -> str:
    path = urlsplit(url).path.lower().strip("/")
    if path.startswith("product/"):
        return "product"
    if path.startswith(("category/", "product-category/")):
        return "category"
    if path == "shop" or path.startswith("shop/") or path == "categories":
        return "shop"
    return "other"


def _url_key(url: str) -> str:
    """Join source URLs despite a trailing slash or encoded Persian path."""
    parts = urlsplit(url)
    path = unquote(parts.path).rstrip("/") or "/"
    return f"{(parts.hostname or '').lower()}{path}{'?' + parts.query if parts.query else ''}"


@lru_cache(maxsize=128)
def _ga4_channel_report(site_id: str, property_id: str, days: int, quarter_hour: int) -> dict:
    """Read a bounded GA4 report; cache per worker to keep page navigation quick."""
    from ...ga4.client import Ga4Client

    body = {"dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "yesterday"}],
            "dimensions": [{"name": "sessionDefaultChannelGroup"}],
            "metrics": [{"name": "sessions"}, {"name": "transactions"}, {"name": "purchaseRevenue"}],
            "limit": 30}
    client = Ga4Client(site_id, save_raw=False)
    report = client._execute(client.svc.properties().runReport(
        property=f"properties/{property_id}", body=body), "commerceChannelReport", max_retries=1) or {}
    channels = []
    for row in report.get("rows", []):
        dimensions = row.get("dimensionValues") or []
        metrics = row.get("metricValues") or []
        if not dimensions or len(metrics) < 3:
            continue
        channels.append({"channel": str(dimensions[0].get("value") or "Unknown"),
                         "sessions": int(float(metrics[0].get("value") or 0)),
                         "transactions": float(metrics[1].get("value") or 0),
                         "purchase_revenue": float(metrics[2].get("value") or 0)})
    return {"status": "reported", "source": "ga4_data_api", "days": days,
            "currency": (report.get("metadata") or {}).get("currencyCode"),
            "property_time_zone": (report.get("metadata") or {}).get("timeZone"),
            "channels": sorted(channels, key=lambda row: -row["sessions"]),
            "organic_search": next((row for row in channels if row["channel"] == "Organic Search"), None),
            "tracking_verified": False}


@router.get("/measurement")
def sales_measurement(site_id: str, days: int = Query(28, ge=7, le=90), eng: Engine = Depends(engine)) -> dict:
    """GA4-reported session-channel commerce, with explicit tracking uncertainty."""
    with eng.connect() as cx:
        property_id = cx.execute(text("SELECT ga4_property FROM sites WHERE site_id=:s"), {"s": site_id}).scalar()
    if not property_id:
        return {"status": "not_configured", "source": "ga4_data_api", "days": days,
                "channels": [], "organic_search": None, "tracking_verified": False}
    try:
        return _ga4_channel_report(site_id, str(property_id).replace("properties/", ""), days, int(time() // 900))
    except Exception:  # OAuth, permission, API and quota failures are visible without exposing credentials.
        return {"status": "error", "source": "ga4_data_api", "days": days,
                "channels": [], "organic_search": None, "tracking_verified": False,
                "reason": "ga4_query_failed"}


@router.get("/path")
def sales_path(site_id: str, days: int = Query(28, ge=7, le=90), eng: Engine = Depends(engine)) -> dict:
    """Separate observed commercial search demand from unmeasured sales."""
    with eng.connect() as cx:
        latest = cx.execute(text("SELECT MAX(date) FROM gsc_daily WHERE site_id=:s"), {"s": site_id}).scalar()
        known_urls = [str(row[0]) for row in cx.execute(text("""
            SELECT url FROM pages WHERE site_id=:s AND url<>''
            UNION SELECT url FROM posts WHERE site_id=:s AND url<>''
            UNION SELECT url FROM categories WHERE site_id=:s AND url IS NOT NULL AND url<>''
        """), {"s": site_id})]
        if not latest:
            return {"site_id": site_id, "generated_at": utcnow(), "days": days,
                    "latest_gsc_date": None, "window": None, "previous_window": None,
                    "coverage": "gsc_observed_top_rows_only", "sales_measurement": "unavailable",
                    "inventory": {kind: sum(_page_kind(url) == kind for url in known_urls)
                                  for kind in ("product", "category", "shop")},
                    "stages": [], "daily": [], "top_pages": [], "priority_pages": [], "previous_available": False,
                    "previous_total_clicks": None}

        end = date.fromisoformat(latest)
        start = end - timedelta(days=days - 1)
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=days - 1)
        rows = cx.execute(text("""
            SELECT date, page, SUM(clicks) AS clicks, SUM(impressions) AS impressions
            FROM gsc_daily WHERE site_id=:s AND date BETWEEN :a AND :b
            GROUP BY date, page
        """), {"s": site_id, "a": previous_start.isoformat(), "b": latest}).all()
        issue_rows = cx.execute(text("""
            SELECT url, COUNT(*) FROM issue_cases
            WHERE site_id=:s AND status='open' GROUP BY url
        """), {"s": site_id}).all()
        opportunity_rows = cx.execute(text("""
            SELECT target_url, COUNT(*) FROM keyword_opportunities
            WHERE site_id=:s AND status='new' AND target_url IS NOT NULL GROUP BY target_url
        """), {"s": site_id}).all()
        link_rows = cx.execute(text("""
            SELECT target_url, COUNT(*) FROM link_suggestions
            WHERE site_id=:s AND status='new' AND target_url IS NOT NULL GROUP BY target_url
        """), {"s": site_id}).all()

    source_urls = {_url_key(url): url for url in known_urls}
    def counts_by_url(rows):
        counts: dict[str, int] = defaultdict(int)
        for url, count in rows:
            key = _url_key(url)
            source_urls.setdefault(key, url)
            counts[key] += int(count)
        return counts

    issues = counts_by_url(issue_rows)
    opportunities = counts_by_url(opportunity_rows)
    links = counts_by_url(link_rows)

    stages = {kind: {"kind": kind, "clicks": 0, "impressions": 0, "pages_observed": set()}
              for kind in ("product", "category", "shop")}
    daily: dict[str, dict] = {}
    pages: dict[str, dict] = {}
    previous: dict[str, int] = defaultdict(int)
    previous_seen: set[str] = set()
    previous_available = False
    for day, page, clicks, impressions in rows:
        kind = _page_kind(page)
        if kind == "other":
            continue
        clicks, impressions = int(clicks or 0), int(impressions or 0)
        key = _url_key(page)
        source_urls.setdefault(key, page)
        if day < start.isoformat():
            previous[key] += clicks
            previous_seen.add(key)
            previous_available = True
            continue
        stage = stages[kind]
        stage["clicks"] += clicks
        stage["impressions"] += impressions
        stage["pages_observed"].add(key)
        series = daily.setdefault(day, {"date": day, "product": 0, "category": 0, "shop": 0})
        series[kind] += clicks
        item = pages.setdefault(key, {"url": page, "kind": kind, "clicks": 0, "impressions": 0})
        item["clicks"] += clicks
        item["impressions"] += impressions

    top_pages = sorted(pages.values(), key=lambda row: (-row["impressions"], -row["clicks"], row["url"]))[:10]
    for item in pages.values():
        key = _url_key(item["url"])
        item["ctr"] = round(item["clicks"] / item["impressions"], 4) if item["impressions"] else None
        item["previous_clicks"] = previous[key] if key in previous_seen else None
        item["open_issues"] = issues.get(key, 0)
        item["new_keyword_opportunities"] = opportunities.get(key, 0)
        item["new_link_suggestions"] = links.get(key, 0)
    priority_pages = []
    for key in issues.keys() | opportunities.keys() | links.keys():
        url = source_urls[key]
        kind = _page_kind(url)
        if kind == "other":
            continue
        observed = pages.get(key)
        priority_pages.append({"url": observed["url"] if observed else url, "kind": kind,
                               "clicks": observed["clicks"] if observed else None,
                               "impressions": observed["impressions"] if observed else None,
                               "open_issues": issues.get(key, 0),
                               "new_keyword_opportunities": opportunities.get(key, 0),
                               "new_link_suggestions": links.get(key, 0)})
    priority_pages.sort(key=lambda row: (-(row["impressions"] if row["impressions"] is not None else -1),
                                         -row["open_issues"], -row["new_keyword_opportunities"],
                                         -row["new_link_suggestions"], row["url"]))
    selected_priority = []
    for signal in ("open_issues", "new_keyword_opportunities", "new_link_suggestions"):
        match = next((row for row in priority_pages if row[signal] > 0), None)
        if match is not None and match not in selected_priority:
            selected_priority.append(match)
    selected_priority.extend(row for row in priority_pages if row not in selected_priority)
    return {"site_id": site_id, "generated_at": utcnow(), "days": days,
            "latest_gsc_date": latest,
            "window": {"from": start.isoformat(), "to": latest},
            "previous_window": {"from": previous_start.isoformat(), "to": previous_end.isoformat()},
            "coverage": "gsc_observed_top_rows_only", "sales_measurement": "unavailable",
            "inventory": {kind: sum(_page_kind(url) == kind for url in known_urls)
                          for kind in ("product", "category", "shop")},
            "stages": [{**{k: v for k, v in stage.items() if k != "pages_observed"},
                        "pages_observed": len(stage["pages_observed"])} for stage in stages.values()],
            "daily": [daily[day] for day in sorted(daily)], "top_pages": top_pages,
            "priority_pages": selected_priority[:10],
            "previous_available": previous_available,
            "previous_total_clicks": sum(previous.values()) if previous_available else None}
