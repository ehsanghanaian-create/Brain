"""Read-only HTTP helper with retry + exponential backoff + rate limiting.

Only GET is exposed on purpose (READ-ONLY system).
"""
from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass

import httpx

log = logging.getLogger("http")

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


def ai_proxy() -> str | None:
    """Optional egress proxy for CLOUD AI providers (Gemini/Claude/OpenAI…) — AI_PROXY env, same SSH-tunnel pattern
    as WP_PROXY, for networks where the provider endpoints are DPI-throttled. Local endpoints (Ollama, OmniRoute on
    127.0.0.1) are never proxied. Empty/unset → direct connection."""
    import os
    return (os.environ.get("AI_PROXY") or "").strip() or None


def site_proxy() -> str | None:
    """Optional egress proxy for requests to the user's OWN sites (WP REST test/sync, crawler, publisher) —
    e.g. WP_PROXY=socks5://127.0.0.1:1080 through an SSH tunnel when the local ISP filters the site's domain
    (TLS SNI drop). Google/AI provider traffic is unaffected. Empty/unset → direct connection."""
    import os
    return (os.environ.get("WP_PROXY") or "").strip() or None


@dataclass
class RateLimiter:
    min_interval: float = 1.0
    _lock: threading.Lock = threading.Lock()
    _last: float = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()


class ReadOnlyClient:
    """GET-only wrapper around httpx.Client."""

    def __init__(self, user_agent: str, timeout: float = 20.0, max_retries: int = 3,
                 min_interval: float = 1.0, follow_redirects: bool = True, auth: tuple[str, str] | None = None,
                 verify: bool = True):
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Language": "fa,en;q=0.8"},
            timeout=timeout, follow_redirects=follow_redirects, auth=auth, verify=verify, proxy=site_proxy(),
        )
        self.max_retries = max_retries
        self.rate = RateLimiter(min_interval=min_interval)

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def get(self, url: str, *, params: dict | None = None, headers: dict | None = None,
            follow_redirects: bool | None = None, api: str = "http") -> httpx.Response:
        attempt = 0
        delay = 1.0
        while True:
            attempt += 1
            self.rate.wait()
            try:
                kw = {"params": params, "headers": headers}
                if follow_redirects is not None:
                    kw["follow_redirects"] = follow_redirects
                resp = self._client.get(url, **kw)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                if attempt > self.max_retries:
                    log.error("GET failed permanently", extra={"api": api, "endpoint": url, "status": None,
                                                                "retry": attempt - 1, "final_state": "FAILED"})
                    raise
                log.warning(f"GET transport error ({e.__class__.__name__}); retry {attempt}/{self.max_retries} in {delay:.1f}s",
                            extra={"api": api, "endpoint": url, "retry": attempt})
                time.sleep(delay + random.uniform(0, 0.3))
                delay *= 2
                continue
            if resp.status_code in RETRYABLE_STATUS and attempt <= self.max_retries:
                ra = resp.headers.get("Retry-After")
                wait = float(ra) if ra and ra.isdigit() else delay
                log.warning(f"GET {resp.status_code}; retry {attempt}/{self.max_retries} in {wait:.1f}s",
                            extra={"api": api, "endpoint": url, "status": resp.status_code, "retry": attempt})
                time.sleep(wait + random.uniform(0, 0.3))
                delay *= 2
                continue
            if resp.status_code in (401, 403):
                log.error("authentication/authorization failure — stopping",
                          extra={"api": api, "endpoint": url, "status": resp.status_code, "final_state": "AUTH_FAILED"})
            return resp
