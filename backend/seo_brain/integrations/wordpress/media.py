"""WordPress Media Library for the content editor: browse/search the site's images and upload new ones with the
stored Application Password. Lives in integrations/wordpress — the only package allowed to send outbound writes
(tests/e2e test_10 scans everything else for HTTP write verbs)."""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable

import httpx
from sqlalchemy import Engine, text

from ...common.urls import wp_rest_v2
from ...wordpress.auth import resolve_auth

log = logging.getLogger("integrations.wordpress.media")

FIELDS = "id,source_url,alt_text,title,mime_type,media_details,date"
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}


def sniff_image_mime(data: bytes) -> str | None:
    """Trust the bytes, not the declared content type."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def safe_filename(filename: str | None, mime: str) -> str:
    ext = EXTENSIONS.get(mime, "bin")
    raw = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", raw.rsplit(".", 1)[0] if "." in raw else raw).strip("-.")[:60]
    return f"{stem or f'image-{int(time.time())}'}.{ext}"


def _item(m: dict[str, Any]) -> dict[str, Any]:
    details = m.get("media_details") or {}
    sizes = details.get("sizes") or {}
    thumb = (sizes.get("medium") or sizes.get("thumbnail") or {}).get("source_url") or m.get("source_url")
    title = m.get("title")
    return {"id": m.get("id"), "url": m.get("source_url"), "thumbnail": thumb, "alt": m.get("alt_text") or "",
            "title": (title.get("rendered") if isinstance(title, dict) else title) or "", "mime": m.get("mime_type"),
            "width": details.get("width"), "height": details.get("height"), "date": m.get("date")}


class WordPressMedia:
    """`http` is injectable for tests (no network in CI)."""

    def __init__(self, engine: Engine, http: Callable[..., httpx.Response] | None = None):
        self.engine = engine
        self._http = http

    def _request(self, method: str, url: str, auth: tuple[str, str], **kw) -> httpx.Response:
        if self._http:
            return self._http(method, url, auth=auth, **kw)
        from ...common.http import site_proxy
        headers = {"User-Agent": "SEO-Brain-Media/1.0", **(kw.pop("headers", None) or {})}
        return httpx.request(method, url, auth=auth, timeout=60, follow_redirects=True, proxy=site_proxy(), headers=headers, **kw)

    def _base(self, site_id: str):
        with self.engine.connect() as cx:
            wp_url = cx.execute(text("SELECT wp_url FROM sites WHERE site_id=:s"), {"s": site_id}).scalar()
        if not wp_url:
            return None, None, {"status": "error", "http": 409, "code": "wordpress_not_configured", "message": "آدرس وردپرس برای این سایت تنظیم نشده است"}
        auth = resolve_auth(site_id)
        if not auth:
            return None, None, {"status": "error", "http": 409, "code": "credentials_missing",
                                "message": "‏Application Password ذخیره نشده — در کارت وردپرس سایت، نام‌کاربری و رمز برنامه را وارد و تست کنید"}
        return wp_rest_v2(wp_url).rstrip("/"), (auth.username, auth.app_password), None

    @staticmethod
    def _error(r: httpx.Response, what: str) -> dict[str, Any]:
        if r.status_code in (401, 403):
            return {"status": "error", "http": r.status_code, "code": "not_authorized",
                    "message": "وردپرس اجازه نداد — کاربر Application Password باید نقش author یا بالاتر (upload_files) داشته باشد"}
        return {"status": "error", "http": 502 if r.status_code >= 500 else r.status_code, "code": "wordpress_error", "message": f"{what} ناموفق: HTTP {r.status_code}"}

    def list(self, site_id: str, page: int = 1, per_page: int = 24, search: str | None = None) -> dict[str, Any]:
        base, auth, err = self._base(site_id)
        if err:
            return err
        params: dict[str, Any] = {"per_page": per_page, "page": page, "media_type": "image", "_fields": FIELDS, "orderby": "date", "order": "desc"}
        if search:
            params["search"] = search
        try:
            r = self._request("GET", f"{base}/media", auth, params=params)
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "http": 502, "code": "wordpress_unreachable", "message": f"اتصال به وردپرس برقرار نشد ({e.__class__.__name__})"}
        if r.status_code != 200:
            return self._error(r, "دریافت رسانه‌ها")
        body = r.json()
        items = [_item(m) for m in body] if isinstance(body, list) else []
        return {"items": items, "page": page, "per_page": per_page,
                "total": int(r.headers.get("x-wp-total") or len(items)), "total_pages": int(r.headers.get("x-wp-totalpages") or 1)}

    def upload(self, site_id: str, filename: str | None, content: bytes, mime: str, alt_text: str | None = None, title: str | None = None) -> dict[str, Any]:
        base, auth, err = self._base(site_id)
        if err:
            return err
        name = safe_filename(filename, mime)
        headers = {"Content-Disposition": f'attachment; filename="{name}"', "Content-Type": mime}
        try:
            r = self._request("POST", f"{base}/media", auth, content=content, headers=headers)
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "http": 502, "code": "wordpress_unreachable", "message": f"بارگذاری در وردپرس ناموفق بود ({e.__class__.__name__})"}
        if r.status_code not in (200, 201):
            log.error(f"WP media upload failed for {site_id}: {r.status_code}")
            return self._error(r, "بارگذاری تصویر")
        m = r.json()
        meta = {k: v for k, v in (("alt_text", alt_text), ("title", title)) if v}
        if meta and m.get("id"):
            try:
                r2 = self._request("POST", f"{base}/media/{m['id']}", auth, json=meta)
                if r2.status_code == 200:
                    m = r2.json()
            except Exception:  # noqa: BLE001 — the file is already stored; alt/title are best-effort
                pass
        log.info(f"uploaded media {m.get('id')} to {site_id} ({name}, {len(content)} bytes)")
        return {"status": "uploaded", **_item(m)}
