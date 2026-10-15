"""Google Ads account-level IP exclusions over the official REST API.

The visitor IP comes only from our trusted server-side collector. Google Ads is
used as the destination for a manually approved account-level exclusion; it is
never treated as an IP source and this module contains no automatic blocking.
"""
from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from ..common.config import env
from ..common.google_http import _proxy_from_environment
from ..core.secrets import get_secret_store
from ..gsc.client import GscAuthError, get_credentials, read_token_json

GOOGLE_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"
API_VERSION = "v25"
API_BASE = f"https://googleads.googleapis.com/{API_VERSION}"
_DIGITS = re.compile(r"\D+")


class GoogleAdsApiError(RuntimeError):
    def __init__(self, message: str, *, code: str = "google_ads_error", request_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.request_id = request_id


@dataclass(frozen=True)
class AdsConfig:
    developer_token: str | None
    customer_id: str
    login_customer_id: str | None = None


def _secret_or_env(secret_ref: str, env_name: str) -> str | None:
    value = env(env_name)
    if value:
        return value.strip()
    try:
        stored = get_secret_store().get(secret_ref)
        return stored.strip() if stored else None
    except Exception:  # noqa: BLE001 - status must remain safe when a store is unavailable
        return None


def _customer_id(value: str | None) -> str | None:
    digits = _DIGITS.sub("", value or "")
    return digits if len(digits) == 10 else None


def _config() -> AdsConfig:
    token = _secret_or_env("google-ads-developer-token", "GOOGLE_ADS_DEVELOPER_TOKEN")
    customer_id = _customer_id(_secret_or_env("google-ads-customer-id", "GOOGLE_ADS_CUSTOMER_ID"))
    login_customer_id = _customer_id(_secret_or_env("google-ads-login-customer-id", "GOOGLE_ADS_LOGIN_CUSTOMER_ID"))
    if not customer_id:
        raise GoogleAdsApiError("Customer ID ده‌رقمی گوگل ادز تنظیم نشده است", code="customer_id_missing")
    return AdsConfig(token, customer_id, login_customer_id)


def _oauth_has_ads_scope() -> bool:
    try:
        raw = json.loads(read_token_json() or "null") or {}
    except ValueError:
        return False
    scopes = raw.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    return GOOGLE_ADS_SCOPE in scopes


def status() -> dict[str, Any]:
    token = _secret_or_env("google-ads-developer-token", "GOOGLE_ADS_DEVELOPER_TOKEN")
    customer_id = _customer_id(_secret_or_env("google-ads-customer-id", "GOOGLE_ADS_CUSTOMER_ID"))
    login_customer_id = _customer_id(_secret_or_env("google-ads-login-customer-id", "GOOGLE_ADS_LOGIN_CUSTOMER_ID"))
    oauth_scope = _oauth_has_ads_scope()
    # Google Ads moved API access levels to Google Cloud projects in September
    # 2026; the developer-token header is optional and ignored by the API.
    configured = bool(customer_id)
    return {
        "ready": bool(configured and oauth_scope),
        "configured": configured,
        "developer_token_configured": bool(token),
        "oauth_ads_scope": oauth_scope,
        "customer_id": customer_id,
        "login_customer_id": login_customer_id,
        "api_version": API_VERSION,
        "mode": "manual_approval",
        "automatic_blocking": False,
    }


def _credentials():
    if not _oauth_has_ads_scope():
        raise GoogleAdsApiError(
            "حساب گوگل باید یک‌بار با دسترسی Google Ads دوباره متصل شود",
            code="ads_oauth_scope_missing",
        )
    try:
        return get_credentials(interactive=False)
    except GscAuthError as exc:
        raise GoogleAdsApiError("مجوز OAuth گوگل آماده نیست یا منقضی شده است", code="google_oauth_not_ready") from exc


def _error_message(response: httpx.Response) -> tuple[str, str]:
    try:
        payload = response.json()
        error = payload.get("error") or {}
        status = str(error.get("status") or f"http_{response.status_code}").lower()
        message = str(error.get("message") or response.reason_phrase)
        return status, message[:600]
    except ValueError:
        return f"http_{response.status_code}", response.reason_phrase


def _headers(config: AdsConfig, access_token: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    if config.developer_token:
        headers["developer-token"] = config.developer_token
    if config.login_customer_id:
        headers["login-customer-id"] = config.login_customer_id
    return headers


def _access_token(credentials: Any) -> str:
    from google.auth.transport.requests import Request

    if not credentials.valid:
        try:
            credentials.refresh(Request())
        except Exception as exc:  # noqa: BLE001
            raise GoogleAdsApiError("تازه‌سازی مجوز گوگل ناموفق بود", code="google_oauth_refresh_failed") from exc
    if not credentials.token:
        raise GoogleAdsApiError("توکن دسترسی گوگل در دسترس نیست", code="google_oauth_token_missing")
    return credentials.token


def _request(client: httpx.Client, method: str, url: str, *, headers: dict[str, str], body: dict[str, Any]) -> httpx.Response:
    try:
        response = client.request(method, url, headers=headers, json=body)
    except (httpx.TransportError, OSError) as exc:
        raise GoogleAdsApiError("ارتباط با Google Ads API برقرار نشد", code="google_ads_network_error") from exc
    if response.is_error:
        code, message = _error_message(response)
        raise GoogleAdsApiError(message, code=code, request_id=response.headers.get("request-id"))
    return response


def _existing_ip_resource(client: httpx.Client, config: AdsConfig, headers: dict[str, str], ip: str) -> str | None:
    return list_ip_exclusions(client=client, config=config, headers=headers).get(ip)


def _normalized_exclusion_ip(address: str) -> str:
    """Google reports an exact IPv4/IPv6 exclusion as /32 or /128."""
    try:
        network = ipaddress.ip_network(address, strict=False)
        if network.prefixlen == network.max_prefixlen:
            return str(network.network_address)
        return str(network)
    except ValueError:
        return address


def list_ip_exclusions(*, client: httpx.Client | None = None, config: AdsConfig | None = None,
                       headers: dict[str, str] | None = None) -> dict[str, str]:
    """Read the account's actual IP exclusions, including ones added outside SEO Brain."""
    config = config or _config()
    if headers is None:
        headers = _headers(config, _access_token(_credentials()))
    owned_client = client is None
    client = client or httpx.Client(timeout=45.0, follow_redirects=True,
                                    proxy=_proxy_from_environment(), trust_env=False)
    # The query is fixed; visitor input is matched only after the response arrives.
    query = (
        "SELECT customer_negative_criterion.resource_name, "
        "customer_negative_criterion.ip_block.ip_address "
        "FROM customer_negative_criterion "
        "WHERE customer_negative_criterion.type = 'IP_BLOCK'"
    )
    url = f"{API_BASE}/customers/{config.customer_id}/googleAds:search"
    page_token: str | None = None
    items: dict[str, str] = {}
    try:
        while True:
            # Google Ads Search uses a fixed page size; v25 rejects pageSize.
            body: dict[str, Any] = {"query": query}
            if page_token:
                body["pageToken"] = page_token
            response = _request(client, "POST", url, headers=headers, body=body)
            payload = response.json()
            for result in payload.get("results") or []:
                criterion = result.get("customerNegativeCriterion") or {}
                address = (criterion.get("ipBlock") or {}).get("ipAddress")
                resource = criterion.get("resourceName")
                if address and resource:
                    items[_normalized_exclusion_ip(address)] = resource
            page_token = payload.get("nextPageToken")
            if not page_token:
                return items
    finally:
        if owned_client:
            client.close()


def exclude_ip(ip_address: str) -> dict[str, Any]:
    """Create one account-level IP exclusion, idempotently.

    The API supports up to 500 account-level IP exclusions. Exact IPs only are
    accepted here; CIDR blocking is intentionally unavailable in the dashboard.
    """
    try:
        ip = str(ipaddress.ip_address(ip_address.strip()))
    except ValueError as exc:
        raise GoogleAdsApiError("IP معتبر نیست", code="invalid_ip") from exc

    config = _config()
    credentials = _credentials()
    access_token = _access_token(credentials)
    headers = _headers(config, access_token)
    client = httpx.Client(
        timeout=45.0,
        follow_redirects=True,
        proxy=_proxy_from_environment(),
        trust_env=False,
    )
    try:
        existing = _existing_ip_resource(client, config, headers, ip)
        if existing:
            return {
                "status": "already_excluded",
                "customer_id": config.customer_id,
                "resource_name": existing,
                "request_id": None,
            }
        url = f"{API_BASE}/customers/{config.customer_id}/customerNegativeCriteria:mutate"
        response = _request(client, "POST", url, headers=headers, body={
            "operations": [{"create": {"ipBlock": {"ipAddress": ip}}}],
            "partialFailure": False,
            "validateOnly": False,
            "responseContentType": "RESOURCE_NAME_ONLY",
        })
        payload = response.json()
        results = payload.get("results") or []
        if not results or not results[0].get("resourceName"):
            raise GoogleAdsApiError("گوگل نتیجه قابل ثبت برنگرداند", code="google_ads_empty_result")
        return {
            "status": "succeeded",
            "customer_id": config.customer_id,
            "resource_name": results[0]["resourceName"],
            "request_id": response.headers.get("request-id"),
        }
    finally:
        client.close()


def remove_ip(ip_address: str) -> dict[str, Any]:
    """Remove only the exact account-level IP exclusion currently held by Google."""
    try:
        ip = str(ipaddress.ip_address(ip_address.strip()))
    except ValueError as exc:
        raise GoogleAdsApiError("IP معتبر نیست", code="invalid_ip") from exc

    config = _config()
    headers = _headers(config, _access_token(_credentials()))
    with httpx.Client(timeout=45.0, follow_redirects=True,
                      proxy=_proxy_from_environment(), trust_env=False) as client:
        resource = _existing_ip_resource(client, config, headers, ip)
        if not resource:
            return {
                "status": "already_removed", "customer_id": config.customer_id,
                "resource_name": None, "request_id": None,
            }
        expected_prefix = f"customers/{config.customer_id}/customerNegativeCriteria/"
        if not resource.startswith(expected_prefix):
            raise GoogleAdsApiError("شناسه exclusion با حساب گوگل تطابق ندارد", code="resource_account_mismatch")
        url = f"{API_BASE}/customers/{config.customer_id}/customerNegativeCriteria:mutate"
        response = _request(client, "POST", url, headers=headers, body={
            "operations": [{"remove": resource}],
            "partialFailure": False,
            "validateOnly": False,
            "responseContentType": "RESOURCE_NAME_ONLY",
        })
        results = response.json().get("results") or []
        if not results or results[0].get("resourceName") != resource:
            raise GoogleAdsApiError("گوگل حذف IP exclusion را تأیید نکرد", code="google_ads_empty_result")
        return {
            "status": "removed", "customer_id": config.customer_id,
            "resource_name": resource, "request_id": response.headers.get("request-id"),
        }

