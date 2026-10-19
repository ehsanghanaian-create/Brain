"""Optional, TLS-verified WordPress REST origin pinning for a split storefront.

Only WordPress REST clients use this transport. Crawls and other requests to the
public storefront continue to resolve normally. The configured origin hostname
remains the HTTP Host and TLS SNI name, so certificate verification stays on.
"""
from __future__ import annotations

import ipaddress
import os
import re
import secrets

import httpx

from ..common.http import site_proxy


class PinnedWordPressTransport(httpx.BaseTransport):
    def __init__(self, wp_host: str, origin_host: str, origin_ip: str):
        self._hosts = {wp_host.lower(), origin_host.lower()}
        self._origin_host = origin_host.lower()
        self._origin_ip = str(ipaddress.ip_address(origin_ip))
        self._transport = httpx.HTTPTransport(verify=True, retries=0)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.scheme != "https" or request.url.host.lower() not in self._hosts:
            return self._transport.handle_request(request)
        headers = request.headers.copy()
        headers["Host"] = self._origin_host
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=self._origin_ip),
            headers=headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": self._origin_host},
        )
        return self._transport.handle_request(pinned)

    def close(self) -> None:
        self._transport.close()


def wordpress_rest_transport(url: str) -> PinnedWordPressTransport | None:
    """Opt in for one configured WordPress host; never reroute other sites."""
    pinned_host = (os.getenv("WP_REST_PINNED_HOST") or "").strip().lower()
    origin_host = (os.getenv("WP_REST_ORIGIN_HOST") or "").strip().lower()
    origin_ip = (os.getenv("WP_REST_ORIGIN_IP") or "").strip()
    if not pinned_host and not origin_host and not origin_ip:
        return None
    if not pinned_host or not origin_host or not origin_ip:
        raise ValueError("WP_REST_PINNED_HOST, WP_REST_ORIGIN_HOST and WP_REST_ORIGIN_IP must be set together")
    for host in (pinned_host, origin_host):
        if not re.fullmatch(r"(?=.{1,253}$)[a-z0-9-]+(?:\.[a-z0-9-]+)+", host):
            raise ValueError("WordPress REST hosts must be DNS hostnames")
    parsed = httpx.URL(url)
    if parsed.host and parsed.host.lower() not in {pinned_host, origin_host}:
        return None
    if parsed.scheme != "https" or not parsed.host or parsed.port not in (None, 443):
        raise ValueError("Pinned WordPress REST requires an HTTPS URL on port 443")
    return PinnedWordPressTransport(pinned_host, origin_host, origin_ip)


def fresh_rest_params(url: str, params: dict | None = None) -> dict | None:
    """Bypass the storefront's public REST cache for the configured WordPress host.

    The storefront may serve a successful but stale response when its origin is
    unreachable. A unique query parameter makes every sync read a cache miss.
    Other sites retain their existing request and caching behaviour.
    """
    fresh_host = (os.getenv("WP_REST_FRESH_HOST") or "").strip().lower()
    if not fresh_host or httpx.URL(url).host != fresh_host:
        return params
    return {**(params or {}), "_seo_brain_refresh": secrets.token_hex(12)}


def require_fresh_rest_response(url: str, response: httpx.Response) -> None:
    """Never record a cached fallback as a successful WordPress sync."""
    fresh_host = (os.getenv("WP_REST_FRESH_HOST") or "").strip().lower()
    if not fresh_host or httpx.URL(url).host != fresh_host or response.status_code >= 400:
        return
    cache_status = (response.headers.get("x-cache-status") or "").strip().upper()
    if cache_status and cache_status not in {"MISS", "BYPASS"}:
        raise RuntimeError(
            f"WordPress REST freshness check failed on {httpx.URL(url).path}: "
            f"X-Cache-Status={cache_status}"
        )


def wordpress_get(url: str, *, auth: tuple[str, str] | None = None, timeout: float = 20.0,
                  user_agent: str = "SEO-Brain/0.2 (+local; read-only)") -> httpx.Response:
    """One-shot GET shared by the connection probe and sync URL resolver."""
    transport = wordpress_rest_transport(url)
    with httpx.Client(transport=transport, proxy=None if transport else site_proxy(),
                      timeout=timeout, follow_redirects=True, auth=auth,
                      headers={"User-Agent": user_agent}) as client:
        response = client.get(url, params=fresh_rest_params(url))
        require_fresh_rest_response(url, response)
        return response
