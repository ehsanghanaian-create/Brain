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


_PROXY_CHECK_CACHE: dict[str, tuple[float, bool]] = {}
PROXY_PROBE_TTL = 20.0


def proxy_reachable(url: str, ttl: float = PROXY_PROBE_TTL) -> bool:
    """TCP-connect probe of a proxy URL's host:port (cached `ttl` seconds). A closed SSH tunnel (nothing listening on
    127.0.0.1:1080) therefore degrades to a *direct* connection instead of failing every AI/WordPress call with
    ConnectError — when the machine has its own route (VPN) the call simply works; when it has none, the direct
    attempt fails with the same network error as before. URLs without host:port are assumed reachable."""
    import socket
    import time
    from urllib.parse import urlsplit
    now = time.monotonic()
    hit = _PROXY_CHECK_CACHE.get(url)
    if hit and now - hit[0] < ttl:
        return hit[1]
    u = urlsplit(url)
    ok = True
    if u.hostname and u.port:
        try:
            with socket.create_connection((u.hostname, u.port), timeout=1.5):
                pass
        except OSError:
            ok = False
    _PROXY_CHECK_CACHE[url] = (now, ok)
    if not ok and (hit is None or hit[1]):
        log.warning("proxy %s is not accepting connections — using a direct connection until it comes back", url)
    return ok


# AI_PROXY=auto — local proxy ports of the VPN clients people actually run (v2rayN/v2rayNG 10808/10809, Clash/Mihomo 7890,
# Clash Verge 7897, Nekoray/NekoBox 2080/2081, plain SOCKS 1080, Privoxy 8118, Hiddify 12334)
AUTO_PROXY_PORTS = (10808, 10809, 7890, 7897, 2080, 2081, 1080, 8118, 12334)
AUTO_PROBE_URL = "https://generativelanguage.googleapis.com/"
AUTO_PROBE_TTL = 60.0
_AUTO_CACHE: dict[str, tuple[float, str | None]] = {}


def _port_open(port: int, timeout: float = 0.25) -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _proxy_works(url: str) -> bool:
    """True when a real HTTPS request passes through the proxy (any HTTP status counts — we only test the tunnel)."""
    try:
        with httpx.Client(proxy=url, timeout=httpx.Timeout(8.0, connect=4.0), trust_env=False) as c:
            c.get(AUTO_PROBE_URL)
        return True
    except Exception:  # noqa: BLE001 — a dead/disconnected VPN client is simply "not a working proxy"
        return False


def detect_local_proxy(ttl: float = AUTO_PROBE_TTL) -> str | None:
    """Find the local proxy of a running VPN client and verify traffic really flows through it. Google and Anthropic
    refuse Iranian egress, so on a workstation the AI calls must leave through the VPN; on a server nothing listens on
    these ports and the answer is None (direct connection). Cached `ttl` seconds."""
    now = time.monotonic()
    hit = _AUTO_CACHE.get("auto")
    if hit and now - hit[0] < ttl:
        return hit[1]
    found: str | None = None
    for port in AUTO_PROXY_PORTS:
        if not _port_open(port):
            continue
        found = next((u for u in (f"http://127.0.0.1:{port}", f"socks5://127.0.0.1:{port}") if _proxy_works(u)), None)
        if found:
            break
    if hit is None or hit[1] != found:
        log.info("AI_PROXY=auto -> %s", found or "no local VPN proxy found, using a direct connection")
    _AUTO_CACHE["auto"] = (now, found)
    return found


def _egress(var: str) -> str | None:
    import os
    url = (os.environ.get(var) or "").strip() or None
    if url and url.lower() == "auto":      # VPN auto-detection is for AI providers only — client sites are reached directly
        return detect_local_proxy() if var == "AI_PROXY" else None
    return url if url and proxy_reachable(url) else None


def ai_proxy() -> str | None:
    """Optional egress proxy for CLOUD AI providers (Gemini/Claude/OpenAI…) — AI_PROXY env, same SSH-tunnel pattern
    as WP_PROXY, for networks where the provider endpoints are DPI-throttled. Local endpoints (Ollama, OmniRoute on
    127.0.0.1) are never proxied. Empty/unset, or the proxy port not listening (tunnel closed) → direct connection.
    `AI_PROXY=auto` finds a running VPN client's local proxy by itself (see detect_local_proxy)."""
    return _egress("AI_PROXY")


def site_proxy() -> str | None:
    """Optional egress proxy for requests to the user's OWN sites (WP REST test/sync, crawler, publisher) —
    e.g. WP_PROXY=socks5://127.0.0.1:1080 through an SSH tunnel when the local ISP filters the site's domain
    (TLS SNI drop). Google/AI provider traffic is unaffected. Empty/unset, or the tunnel closed → direct connection."""
    return _egress("WP_PROXY")


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
