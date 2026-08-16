"""Google Search Console client (official googleapiclient) — read-only, quota-aware.

Design (per spec §21-24):
  OAuth (installed-app flow, browser once) -> refresh token cached under tokens/ (git-ignored)
  -> searchanalytics.query with pagination (startRow) -> raw JSON under data/raw/gsc -> SQLite.
Claude never calls GSC directly; it reads SQLite.
"""
from __future__ import annotations

import json
import logging
import random
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator

from ..common.config import env, raw_data_dir, resolve_path

log = logging.getLogger("gsc")

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
MAX_ROWS_PER_REQUEST = 25000
RETRYABLE = {429, 500, 502, 503, 504}


class GscAuthError(Exception):
    pass


def _client_config() -> dict:
    cid, csec = env("GOOGLE_CLIENT_ID"), env("GOOGLE_CLIENT_SECRET")
    if not cid or not csec:
        raise GscAuthError("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing in .env (create an OAuth 'Desktop app' client in Google Cloud and enable the Search Console API)")
    return {"installed": {
        "client_id": cid, "client_secret": csec, "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": ["http://localhost"],
    }}


def get_credentials(interactive: bool = True):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    token_path = resolve_path(env("GSC_TOKEN_PATH", "tokens/gsc_token.json"))
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception as e:  # noqa: BLE001
            log.warning(f"token refresh failed ({e.__class__.__name__}); re-authorization required")
    _client_config()  # raises a precise error if the OAuth client is not configured
    if not interactive:
        raise GscAuthError("no valid GSC token; run: python scripts/sync-gsc.py --auth-only")
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_config(_client_config(), SCOPES)
    # bind to loopback only; opens the browser once
    creds = flow.run_local_server(host="127.0.0.1", port=0, open_browser=True, prompt="consent")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    log.info(f"GSC token stored at {token_path} (git-ignored)")
    return creds


class GscClient:
    def __init__(self, site_id: str, interactive: bool = True, save_raw: bool = True):
        from googleapiclient.discovery import build
        self.site_id = site_id
        self.creds = get_credentials(interactive=interactive)
        self.svc = build("searchconsole", "v1", credentials=self.creds, cache_discovery=False)
        self.save_raw = save_raw
        self.raw_dir: Path = raw_data_dir() / "gsc" / site_id
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
                    log.error(f"GSC auth/permission error {status} on {what}: {e}", extra={"api": "gsc", "endpoint": what, "status": status, "final_state": "AUTH_FAILED"})
                    raise GscAuthError(str(e)) from e
                if status in RETRYABLE and attempt <= max_retries:
                    log.warning(f"GSC {status} on {what}; retry {attempt}/{max_retries} in {delay:.0f}s", extra={"api": "gsc", "endpoint": what, "status": status, "retry": attempt})
                    time.sleep(delay + random.uniform(0, 1))
                    delay = min(delay * 2, 64)
                    continue
                log.error(f"GSC error {status} on {what}: {e}", extra={"api": "gsc", "endpoint": what, "status": status, "final_state": "FAILED"})
                raise

    # -- sites ---------------------------------------------------------------------
    def list_sites(self) -> list[dict]:
        data = self._execute(self.svc.sites().list(), "sites.list") or {}
        entries = data.get("siteEntry", [])
        if self.save_raw:
            (self.raw_dir / "sites.json").write_text(json.dumps(entries, indent=1), encoding="utf-8")
        return entries

    def resolve_property(self, wanted: str) -> tuple[str | None, str | None]:
        """Return (siteUrl, permissionLevel) for `wanted`; tries URL-prefix and domain forms."""
        entries = self.list_sites()
        cands = {wanted}
        host = wanted.replace("https://", "").replace("http://", "").strip("/")
        cands.update({f"sc-domain:{host}", f"https://{host}/", f"http://{host}/", f"https://www.{host}/"})
        for e in entries:
            if e.get("siteUrl") in cands:
                return e["siteUrl"], e.get("permissionLevel")
        return None, None

    # -- search analytics -----------------------------------------------------------
    def query(self, site_url: str, start: date, end: date, dimensions: list[str], row_limit: int = MAX_ROWS_PER_REQUEST,
              search_type: str = "web", data_state: str = "final") -> Iterator[dict]:
        start_row = 0
        page = 0
        while True:
            body = {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": dimensions,
                    "rowLimit": min(row_limit, MAX_ROWS_PER_REQUEST), "startRow": start_row, "type": search_type,
                    "dataState": data_state}
            data = self._execute(self.svc.searchanalytics().query(siteUrl=site_url, body=body), "searchanalytics.query") or {}
            rows = data.get("rows", [])
            if self.save_raw:
                fn = self.raw_dir / f"sa_{start.isoformat()}_{end.isoformat()}_{'-'.join(dimensions)}_p{page}.json"
                fn.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            for r in rows:
                yield r
            log.info(f"GSC rows fetched: {len(rows)} (startRow={start_row})", extra={"api": "gsc", "endpoint": "searchanalytics.query", "count": len(rows)})
            if len(rows) < body["rowLimit"]:
                break
            start_row += len(rows)
            page += 1
            time.sleep(0.5)  # gentle pacing


def date_window(lookback_days: int, end_offset_days: int = 3) -> tuple[date, date]:
    """GSC data lags ~2-3 days; end = today - end_offset."""
    end = date.today() - timedelta(days=end_offset_days)
    start = end - timedelta(days=max(lookback_days, 1) - 1)
    return start, end
