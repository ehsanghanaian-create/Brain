"""Google Analytics 4 Data API client — read-only, quota-aware; the GA4 twin of gsc/client.py.

Auth: the ONE shared Google OAuth token (gsc.client.get_credentials — tokens/gsc_token.json, git-ignored) with the
analytics.readonly scope. No second OAuth flow, no service accounts, credentials never logged.
Raw responses are cached under data/raw/ga4/{site_id} exactly like the GSC client does.
"""
from __future__ import annotations

import json
import logging
import random
import time
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from ..common.config import raw_data_dir
from ..gsc.client import GscAuthError, get_credentials

log = logging.getLogger("ga4")

MAX_ROWS_PER_REQUEST = 10000                      # Data API v1beta limit per request
RETRYABLE = {429, 500, 502, 503, 504}

DIMENSIONS = {"page": "pagePath", "landing": "landingPage"}
METRICS = ["sessions", "totalUsers", "screenPageViews", "engagementRate", "averageSessionDuration", "keyEvents"]
_METRICS_LEGACY = ["sessions", "totalUsers", "screenPageViews", "engagementRate", "averageSessionDuration", "conversions"]


class Ga4Client:
    def __init__(self, site_id: str, interactive: bool = False, save_raw: bool = True):
        from ..common.google_http import build_google_service
        self.site_id = site_id
        self.creds = get_credentials(interactive=interactive)
        self.svc = build_google_service("analyticsdata", "v1beta", self.creds)
        self.save_raw = save_raw
        self.raw_dir: Path = raw_data_dir() / "ga4" / site_id
        if save_raw:
            self.raw_dir.mkdir(parents=True, exist_ok=True)

    def _execute(self, req, what: str, max_retries: int = 5):
        from googleapiclient.errors import HttpError
        delay = 2.0
        for attempt in range(1, max_retries + 2):
            try:
                return req.execute(num_retries=0)
            except HttpError as e:
                status = e.resp.status if e.resp else None
                if status in (401, 403):
                    log.error(f"GA4 auth/permission error {status} on {what}", extra={"api": "ga4", "endpoint": what, "status": status, "final_state": "AUTH_FAILED"})
                    raise GscAuthError(str(e)) from e
                if status in RETRYABLE and attempt <= max_retries:
                    log.warning(f"GA4 {status} on {what}; retry {attempt}/{max_retries} in {delay:.0f}s", extra={"api": "ga4", "endpoint": what, "status": status, "retry": attempt})
                    time.sleep(delay + random.uniform(0, 1))
                    delay = min(delay * 2, 64)
                    continue
                log.error(f"GA4 error {status} on {what}", extra={"api": "ga4", "endpoint": what, "status": status, "final_state": "FAILED"})
                raise

    def run_report(self, property_id: str, body: dict) -> dict:
        return self._execute(self.svc.properties().runReport(property=f"properties/{property_id}", body=body), "runReport") or {}

    # ------------------------------------------------------------------ daily rows (date x path), paginated
    def daily(self, property_id: str, start: date, end: date, dimension: str = "pagePath", row_limit: int = MAX_ROWS_PER_REQUEST) -> Iterator[dict[str, Any]]:
        """Yield {date, path, sessions, total_users, screen_page_views, engagement_rate, average_session_duration, conversions}."""
        metrics = METRICS
        offset = 0
        page = 0
        while True:
            body = {"dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
                    "dimensions": [{"name": "date"}, {"name": dimension}],
                    "metrics": [{"name": m} for m in metrics],
                    "limit": min(row_limit, MAX_ROWS_PER_REQUEST), "offset": offset,
                    "orderBys": [{"dimension": {"dimensionName": "date"}}]}
            try:
                data = self.run_report(property_id, body)
            except Exception as e:  # noqa: BLE001 — older properties reject keyEvents; retry once with 'conversions'
                if metrics is METRICS and "keyEvents" in str(e):
                    metrics = _METRICS_LEGACY
                    continue
                raise
            rows = data.get("rows", [])
            if self.save_raw:
                fn = self.raw_dir / f"rr_{start.isoformat()}_{end.isoformat()}_{dimension}_p{page}.json"
                fn.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            for r in rows:
                dv = [d.get("value", "") for d in r.get("dimensionValues", [])]
                mv = [m.get("value", "0") for m in r.get("metricValues", [])]
                yield {"date": f"{dv[0][:4]}-{dv[0][4:6]}-{dv[0][6:8]}" if len(dv[0]) == 8 else dv[0], "path": dv[1],
                       "sessions": int(float(mv[0] or 0)), "total_users": int(float(mv[1] or 0)), "screen_page_views": int(float(mv[2] or 0)),
                       "engagement_rate": float(mv[3] or 0), "average_session_duration": float(mv[4] or 0), "conversions": float(mv[5] or 0)}
            log.info(f"GA4 rows fetched: {len(rows)} (offset={offset}, dim={dimension})", extra={"api": "ga4", "endpoint": "runReport", "count": len(rows)})
            total = int(data.get("rowCount") or 0)
            offset += len(rows)
            page += 1
            if not rows or offset >= total:
                break
            time.sleep(0.5)  # gentle pacing
