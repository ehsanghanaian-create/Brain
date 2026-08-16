"""URL normalization — the single definition of "URL identity" used across the system.

Rules:
- scheme lowercased; http -> https ONLY when the site's canonical scheme is https and host matches
- host lowercased; optional leading "www." folded to the site's canonical host form
- default ports removed
- fragments removed
- duplicate slashes collapsed in the path
- percent-encoding normalized: unreserved chars decoded, everything else re-encoded uniformly
  (Persian paths compare equal whether they arrive encoded or decoded)
- trailing slash: normalized to the site convention (WordPress default = trailing slash) for
  paths without a file extension; file-like paths (".xml", ".jpg", ...) are left untouched
- tracking parameters removed (utm_*, fbclid, gclid, ...); other query params kept and sorted
- empty query removed
"""
from __future__ import annotations

import posixpath
import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "yclid", "_ga", "_gl", "ref", "igshid",
}
_FILE_EXT_RE = re.compile(r"\.[a-z0-9]{1,5}$", re.I)
_DEFAULT_PORTS = {"http": "80", "https": "443"}
# safe chars kept literally in path segments (RFC3986 unreserved + sub-delims commonly used in URLs)
_PATH_SAFE = "-._~!$&'()*+,;=:@/"


def _norm_path(path: str, trailing_slash: bool) -> str:
    if not path:
        path = "/"
    path = re.sub(r"/{2,}", "/", path)
    # decode then re-encode uniformly (idempotent for already-decoded Persian text)
    decoded = unquote(path)
    # collapse . and .. segments
    decoded = posixpath.normpath(decoded) if decoded != "/" else "/"
    if not decoded.startswith("/"):
        decoded = "/" + decoded
    if trailing_slash and decoded != "/" and not _FILE_EXT_RE.search(decoded) and not decoded.endswith("/"):
        decoded += "/"
    if not trailing_slash and decoded != "/" and decoded.endswith("/"):
        decoded = decoded.rstrip("/")
    return quote(decoded, safe=_PATH_SAFE)


def strip_tracking_params(query: str) -> str:
    if not query:
        return ""
    pairs = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    pairs.sort()
    return urlencode(pairs, doseq=True)


def normalize_url(url: str, *, site_host: str | None = None, canonical_scheme: str = "https",
                  trailing_slash: bool = True, fold_www: bool = True) -> str:
    """Return the normalized form of `url`. Relative URLs must be resolved by the caller first."""
    url = url.strip()
    parts = urlsplit(url)
    scheme = (parts.scheme or canonical_scheme).lower()
    host = (parts.hostname or "").lower()
    if not host:
        # not absolute; return as-is (caller should have resolved)
        return url
    port = parts.port
    if fold_www and site_host:
        bare = site_host[4:] if site_host.startswith("www.") else site_host
        if host in (bare, "www." + bare):
            host = site_host  # fold to site convention
    if site_host and host == site_host and scheme in ("http", "https"):
        scheme = canonical_scheme
    netloc = host
    if port and str(port) != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{port}"
    path = _norm_path(parts.path, trailing_slash)
    query = strip_tracking_params(parts.query)
    return urlunsplit((scheme, netloc, path, query, ""))


def url_identity(url: str, site_host: str | None = None) -> str:
    """Identity key used for de-duplication (same as normalize_url; alias for readability)."""
    return normalize_url(url, site_host=site_host)


def is_same_site(url: str, allowed_hosts: list[str] | set[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    allowed = {h.lower() for h in allowed_hosts}
    return host in allowed or (host.startswith("www.") and host[4:] in allowed) or ("www." + host) in allowed
