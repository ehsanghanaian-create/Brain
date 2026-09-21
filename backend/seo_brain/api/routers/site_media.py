"""WordPress Media Library endpoints for the content editor: /sites/{id}/wordpress/media (browse) and /upload."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import Engine

from ..deps import engine, require_site
from ..errors import ApiError

router = APIRouter(prefix="/sites/{site_id}/wordpress/media", tags=["wordpress-media"], dependencies=[Depends(require_site)])
MAX_BYTES = 10 * 1024 * 1024


def _raise(out: dict) -> None:
    if out.get("status") == "error":
        raise ApiError(int(out.get("http") or 502), out.get("message") or "خطای وردپرس", code=out.get("code") or "wordpress_media_error")


@router.get("")
def list_media(site_id: str, page: int = Query(1, ge=1), per_page: int = Query(24, ge=1, le=100), search: str | None = Query(None, max_length=120),
               eng: Engine = Depends(engine)) -> dict:
    from ...integrations.wordpress.media import WordPressMedia
    out = WordPressMedia(eng).list(site_id, page=page, per_page=per_page, search=(search or "").strip() or None)
    _raise(out)
    return out


@router.post("/upload", status_code=201)
async def upload_media(site_id: str, file: UploadFile = File(...), alt_text: str | None = Form(None, max_length=300), title: str | None = Form(None, max_length=200),
                       eng: Engine = Depends(engine)) -> dict:
    from ...integrations.wordpress.media import WordPressMedia, sniff_image_mime
    data = await file.read()
    if not data:
        raise ApiError(422, "فایل خالی است", code="empty_file")
    if len(data) > MAX_BYTES:
        raise ApiError(413, "حجم تصویر باید کمتر از ۱۰ مگابایت باشد", code="file_too_large")
    mime = sniff_image_mime(data)
    if not mime:
        raise ApiError(422, "فقط تصویر JPG، PNG، WebP یا GIF قابل بارگذاری است", code="unsupported_media_type")
    out = WordPressMedia(eng).upload(site_id, file.filename, data, mime, alt_text=(alt_text or "").strip() or None, title=(title or "").strip() or None)
    _raise(out)
    return out
