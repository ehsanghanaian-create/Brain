"""Read-only Google Ads account performance for the Ads Data dashboard."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from ..common.google_http import _proxy_from_environment
from .ip_exclusions import (
    API_BASE,
    AdsConfig,
    GoogleAdsApiError,
    _access_token,
    _config,
    _credentials,
    _headers,
    _request,
)


def _search(client: httpx.Client, config: AdsConfig, headers: dict[str, str], query: str) -> list[dict[str, Any]]:
    url = f"{API_BASE}/customers/{config.customer_id}/googleAds:search"
    results: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        body: dict[str, Any] = {"query": query}
        if page_token:
            body["pageToken"] = page_token
        payload = _request(client, "POST", url, headers=headers, body=body).json()
        results.extend(payload.get("results") or [])
        page_token = payload.get("nextPageToken")
        if not page_token:
            return results


def today_report() -> dict[str, Any]:
    """Return the Ads account's calendar day, using its own time zone."""
    config = _config()
    headers = _headers(config, _access_token(_credentials()))
    with httpx.Client(
        timeout=45.0,
        follow_redirects=True,
        proxy=_proxy_from_environment(),
        trust_env=False,
    ) as client:
        customer_rows = _search(
            client, config, headers,
            "SELECT customer.id, customer.currency_code, customer.time_zone FROM customer LIMIT 1",
        )
        if not customer_rows:
            raise GoogleAdsApiError("حساب Google Ads در پاسخ API پیدا نشد", code="ads_account_not_found")
        customer = customer_rows[0].get("customer") or {}
        account_time_zone = str(customer.get("timeZone") or "UTC")
        try:
            account_date = datetime.now(ZoneInfo(account_time_zone)).date().isoformat()
        except (KeyError, ValueError) as exc:
            raise GoogleAdsApiError("منطقهٔ زمانی حساب Google Ads نامعتبر است", code="ads_time_zone_invalid") from exc
        rows = _search(
            client, config, headers,
            "SELECT campaign.id, campaign.name, segments.date, "
            "metrics.impressions, metrics.clicks, metrics.invalid_clicks, metrics.cost_micros "
            f"FROM campaign WHERE segments.date = '{account_date}'",
        )

    campaigns: list[dict[str, Any]] = []
    for row in rows:
        campaign = row.get("campaign") or {}
        metrics = row.get("metrics") or {}
        campaigns.append({
            "id": str(campaign.get("id") or ""),
            "name": str(campaign.get("name") or ""),
            "impressions": int(metrics.get("impressions") or 0),
            "clicks": int(metrics.get("clicks") or 0),
            "invalid_clicks": int(metrics.get("invalidClicks") or 0),
            "cost_micros": int(metrics.get("costMicros") or 0),
        })
    campaigns.sort(key=lambda item: (-item["clicks"], item["name"]))
    return {
        "source": "google_ads_api",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": account_date,
        "customer_id": config.customer_id,
        "currency_code": customer.get("currencyCode") or "",
        "time_zone": account_time_zone,
        "totals": {
            key: sum(item[key] for item in campaigns)
            for key in ("impressions", "clicks", "invalid_clicks", "cost_micros")
        },
        "campaigns": campaigns,
    }
