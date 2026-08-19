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
