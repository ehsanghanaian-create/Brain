"""WordPress site-URL normalization and validation.

User-facing "WordPress URL" fields (site wizard, connection re-test) accept free text,
so this is the one place that turns that text into a safe `scheme://host` base before
it is ever used to build a request URL. It must never let something that isn't a real
URL (a username, an Application Password, a bare token) end up as the hostname.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")


class InvalidWordPressUrlError(ValueError):
    """Raised with a clear, Persian, user-facing message — never includes the raw secret-looking input."""


def _redact(raw: str) -> str:
    """Best-effort redaction for error details: never echo something that looks like a credential."""
    if len(raw) <= 8:
        return "*" * len(raw)
    return raw[:3] + "…" + raw[-2:] + f" ({len(raw)} chars)"


def normalize_wordpress_url(raw: str | None) -> str:
    """Normalize a user-supplied WordPress site URL into `scheme://host[:port][/path]` (no trailing slash).

    - Trims whitespace.
    - Adds `https://` automatically when no scheme is present *and* the value looks like a
      real domain (e.g. `example.com`, `example.com/blog`, `localhost:8080`).
    - Refuses anything that doesn't look like a domain/URL — in particular a bare token or
      Application Password (no dot, no scheme, no slash) — with a clear error instead of
      silently building a broken request URL out of it.
    - Refuses credentials embedded in the URL (`user:pass@host`) and non-http(s) schemes.

    Raises `InvalidWordPressUrlError` otherwise.
    """
    if raw is None:
        raise InvalidWordPressUrlError("آدرس وردپرس خالی است.")
    value = raw.strip()
    if not value:
        raise InvalidWordPressUrlError("آدرس وردپرس خالی است.")
    if any(c.isspace() for c in value):
        raise InvalidWordPressUrlError(
            "این مقدار یک URL معتبر نیست (شامل فاصله است). "
            "به‌نظر می‌رسد به‌جای آدرس سایت، رمز عبور یا Application Password وارد شده باشد."
        )

    has_scheme = bool(_SCHEME_RE.match(value))
    candidate = value if has_scheme else f"https://{value}"

    try:
        parts = urlsplit(candidate)
    except ValueError as e:
        raise InvalidWordPressUrlError(f"آدرس وردپرس نامعتبر است: {e}") from e

    if has_scheme and parts.scheme not in ("http", "https"):
        raise InvalidWordPressUrlError(
            f"پروتکل «{parts.scheme}://» پشتیبانی نمی‌شود. آدرس وردپرس باید با http:// یا https:// شروع شود."
        )

    host = parts.hostname or ""
    if "@" in (parts.netloc or ""):
        raise InvalidWordPressUrlError(
            "آدرس نباید شامل نام‌کاربری یا رمز عبور باشد. فقط دامنه‌ی سایت وردپرس را وارد کنید "
            "(مثال: example.com یا https://example.com) — نام‌کاربری و Application Password در بخش جداگانه‌ی احراز هویت تنظیم می‌شوند."
        )
    if not host or (host != "localhost" and "." not in host and not _is_ip(host)):
        raise InvalidWordPressUrlError(
            f"«{_redact(value)}» یک دامنه یا URL معتبر به نظر نمی‌رسد. "
            "لطفاً آدرس سایت وردپرس را وارد کنید (مثال: example.com یا https://example.com)، "
            "نه یک نام‌کاربری، Application Password یا توکن."
        )

    path = parts.path.rstrip("/")
    # users often paste the REST root itself — store the SITE base, build /wp-json/ internally
    for suffix in ("/wp-json/wp/v2", "/wp-json"):
        if path.lower().endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            break
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _is_ip(host: str) -> bool:
    parts = host.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def wp_rest_root(base_url: str) -> str:
    """`https://example.com` -> `https://example.com/wp-json/`"""
    return base_url.rstrip("/") + "/wp-json/"


def wp_rest_v2(base_url: str) -> str:
    """`https://example.com` -> `https://example.com/wp-json/wp/v2/`"""
    return base_url.rstrip("/") + "/wp-json/wp/v2/"


# --------------------------------------------------------------------------- canonical WordPress base URL (one resolver for all)
def resolve_wordpress_base(raw: str | None, probe=None) -> tuple[str, dict]:
    """Single canonical resolver used by the connector, the sync orchestrator, the crawler config and the graph builder:
    normalize (scheme, no trailing slash, no `/wp-json`) and — when a `probe(url) -> status_code|None` is given — detect the
    working scheme: an `http://` base is upgraded to `https://` if `https://…/wp-json/` answers 2xx/3xx, and an `https://` base
    falls back to `http://` only when https fails at transport level and http answers. Returns (base, info)."""
    base = normalize_wordpress_url(raw)
    info: dict = {"input": raw, "normalized": base, "scheme_checked": False, "scheme_switched": False}
    if probe is None:
        return base, info
    info["scheme_checked"] = True
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(base)
    other = urlunsplit(("http" if parts.scheme == "https" else "https", parts.netloc, parts.path, "", ""))
    def ok(u: str) -> bool:
        try:
            code = probe(wp_rest_root(u))
        except Exception:  # noqa: BLE001
            return False
        return bool(code) and int(code) < 400
    if parts.scheme == "http":
        if ok(other):                       # prefer https whenever it works
            info["scheme_switched"] = True; return other, info
        return base, info
    if ok(base):
        return base, info
    if ok(other):                           # https broken (cert/transport) but http serves
        info["scheme_switched"] = True; return other, info
    return base, info
