"""Operator tools: text a human (or an agent with hosting access) runs by hand. Nothing here touches a client site."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text

from ...ai.prompts.library import PromptLibrary
from ...brain.ops.phone_change import PhoneChangeError, plan as phone_change_plan
from ...integrations.wordpress.phone import PhoneService
from ..deps import engine
from ..errors import ApiError

router = APIRouter(prefix="/tools", tags=["tools"])
PROMPT_KEY = "ops.phone_change"        # scope "ops": an operator runbook, so the library does not require {{memory_pack}}


class PhoneChangeBody(BaseModel):
    old_phone: str = Field(min_length=4, max_length=40)
    new_phone: str = Field(min_length=4, max_length=40)
    site_id: str | None = None           # a site in the platform: fills the domain/URL of the runbook
    site: str | None = None              # or a bare domain, for a site Brain does not manage
    db_name: str | None = None
    prefix: str = "wp_"


@router.post("/phone-change")
def phone_change(body: PhoneChangeBody, eng: Engine = Depends(engine)) -> dict[str, Any]:
    """Turn «old number → new number» into the full replacement runbook (files, DB, escaped Elementor data, caches).

    The text comes from the prompt library (`task.phone_change`), so editing the prompt in the platform changes what
    this returns; every derived value (8-digit blocks, Persian and escaped forms, SQL) is computed here."""
    site, site_url = (body.site or "").strip(), ""
    if body.site_id:
        with eng.connect() as cx:
            row = cx.execute(text("SELECT name, canonical_url, wp_url FROM sites WHERE site_id=:s"), {"s": body.site_id}).first()
        if not row:
            raise ApiError(404, f"سایت «{body.site_id}» پیدا نشد", code="site_not_found")
        site_url = (row[2] or row[1] or "").rstrip("/") + "/"
        site = site or site_url.replace("https://", "").replace("http://", "").strip("/") or row[0]
    lib = PromptLibrary(eng)
    version = lib.active_version(PROMPT_KEY, body.site_id)
    if not version:                      # first use on this install: put the built-in runbook into the library
        lib.seed()
        version = lib.active_version(PROMPT_KEY, body.site_id)
    try:
        out = phone_change_plan(body.old_phone, body.new_phone, site, db_name=body.db_name or "", prefix=body.prefix,
                                site_url=site_url, template=(version or {}).get("template"))
    except PhoneChangeError as e:
        raise ApiError(422, str(e), code="phone_change_invalid") from e
    return {"site": site or None, "old8": out["old8"], "new8": out["new8"], "replacements": out["pairs"],
            "sql": {k: out["variables"][k] for k in ("sql_text", "sql_escaped", "sql_cache", "sql_verify")},
            "prompt_ref": (version or {}).get("ref"), "runbook": out["runbook"]}

class PhoneReplaceBody(BaseModel):
    old_phone: str = Field(min_length=4, max_length=40)
    new_phone: str = Field(min_length=4, max_length=40)
    dry_run: bool = True
    only_ids: list[int] | None = None


@router.get("/sites/{site_id}/phone/scan")
def phone_scan(site_id: str, phone: str, eng: Engine = Depends(engine)) -> dict[str, Any]:
    """Where a number appears on the site: Brain's synced copy per page, plus whether the live home page prints it
    outside page content (header/Elementor/theme — the part REST cannot rewrite)."""
    try:
        return PhoneService(eng).scan(site_id, phone)
    except KeyError as e:
        raise ApiError(404, f"سایت «{site_id}» پیدا نشد", code="site_not_found") from e


@router.post("/sites/{site_id}/phone/replace")
def phone_replace(site_id: str, body: PhoneReplaceBody, eng: Engine = Depends(engine)) -> dict[str, Any]:
    """Change the number on the site. `dry_run` (default) only previews; the human click in the UI is the approval for
    the write, exactly like «انتشار» in the calendar. Whatever REST cannot reach comes back as the operator runbook."""
    try:
        out = PhoneService(eng).replace(site_id, body.old_phone, body.new_phone, dry_run=body.dry_run, only_ids=body.only_ids)
    except KeyError as e:
        raise ApiError(404, f"سایت «{site_id}» پیدا نشد", code="site_not_found") from e
    if out.get("status") == "invalid":
        raise ApiError(422, out["message"], code="phone_change_invalid")
    return out
