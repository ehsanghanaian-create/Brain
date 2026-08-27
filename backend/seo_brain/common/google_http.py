"""Proxy-aware transport for googleapiclient services.

``googleapiclient`` defaults to httplib2. In the Docker runtime httplib2 has
no PySocks support, so it silently bypasses the configured HTTP(S) proxy and
TLS connections fail on networks where Google is reachable only through the
Windows host bridge. This adapter keeps the official discovery clients while
routing token refresh and API requests through the proxy environment understood
by requests/httpx.
"""
from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import urlsplit

import httpx


_SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}


def _proxy_from_environment() -> str | None:
    """Use explicit process proxies without inheriting unsupported Windows registry values."""
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        value = os.environ.get(name)
        if value and urlsplit(value).scheme.lower() in _SUPPORTED_PROXY_SCHEMES:
            return value
    return None


class _GoogleResponse(dict[str, str]):
    """Minimal httplib2-compatible response consumed by googleapiclient."""

    def __init__(self, response: httpx.Response):
        super().__init__(response.headers)
        self.status = response.status_code
        self.reason = response.reason_phrase


class ProxyAwareGoogleHttp:
    """Authenticated googleapiclient transport with bounded network retries."""

    def __init__(self, credentials: Any, *, timeout_seconds: float = 60.0, max_attempts: int = 4):
        self.credentials = credentials
        self.max_attempts = max(1, max_attempts)
        # trust_env=False is deliberate: on Windows urllib/httpx can inherit the
        # Internet Settings SOCKS entry as ``socks4://`` even when this process
        # did not opt into it. httpx rejects that legacy scheme at construction.
        # Docker supplies an explicit HTTP(S)_PROXY, which is selected above.
        self._client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            proxy=_proxy_from_environment(),
            trust_env=False,
        )

    def request(self, uri: str, method: str = "GET", body: Any = None,
                headers: dict[str, str] | None = None, **_: Any):
        from google.auth.exceptions import TransportError as GoogleTransportError
        from google.auth.transport.requests import Request

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            request_headers = dict(headers or {})
            try:
                self.credentials.before_request(Request(), method, uri, request_headers)
                response = self._client.request(method, uri, headers=request_headers, content=body)
                return _GoogleResponse(response), response.content
            except (httpx.TransportError, GoogleTransportError, OSError) as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    raise
                time.sleep(min(0.5 * (2 ** (attempt - 1)), 4.0))
        raise last_error or RuntimeError("Google API request failed")

    def close(self) -> None:
        self._client.close()


def build_google_service(api: str, version: str, credentials: Any):
    """Build an official Google discovery client over the proxy-aware transport."""
    from googleapiclient.discovery import build

    return build(api, version, http=ProxyAwareGoogleHttp(credentials), cache_discovery=False)
