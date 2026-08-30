"""Site security endpoints — the `security.*` capability of the existing WordPress connection.

Every mutation is an explicit human action relayed to the site's own plugin; Brain never
blocks anything autonomously. All routes are site-scoped and audited.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from ...integrations.wordpress.security import WordPressSecurityService, resolve_site_by_domain
from ..deps import engine

router = APIRouter(tags=["site-security"])


def service(eng: Engine = Depends(engine)) -> WordPressSecurityService:
    return WordPressSecurityService(eng)


class BlockRequest(BaseModel):
    ip: str = Field(min_length=3, max_length=64)
    reason: str | None = Field(default=None, max_length=300)


class UnblockRequest(BaseModel):
    ip: str = Field(min_length=3, max_length=64)


@router.get("/sites/{site_id}/security/status")
def security_status(site_id: str, svc: WordPressSecurityService = Depends(service)) -> dict[str, Any]:
    return svc.get_status(site_id)


@router.get("/sites/{site_id}/security/blocked")
def security_blocked(site_id: str, svc: WordPressSecurityService = Depends(service)) -> dict[str, Any]:
    return svc.list_blocked(site_id)


@router.post("/sites/{site_id}/security/block")
def security_block(site_id: str, body: BlockRequest, svc: WordPressSecurityService = Depends(service)) -> dict[str, Any]:
    return svc.block_ip(site_id, body.ip, body.reason)


@router.post("/sites/{site_id}/security/unblock")
def security_unblock(site_id: str, body: UnblockRequest, svc: WordPressSecurityService = Depends(service)) -> dict[str, Any]:
    return svc.unblock_ip(site_id, body.ip)


@router.get("/sites/{site_id}/security/audit")
def security_audit(site_id: str, limit: int = Query(default=50, ge=1, le=500),
                   svc: WordPressSecurityService = Depends(service)) -> dict[str, Any]:
    return {"items": svc.audit(site_id, limit)}


@router.get("/security/resolve-site")
def security_resolve_site(domain: str = Query(min_length=3, max_length=200),
                          eng: Engine = Depends(engine)) -> dict[str, Any]:
    """ads-data domain → platform site_id (so the ads dashboard can offer site-scoped blocking)."""
    sid = resolve_site_by_domain(eng, domain)
    return {"domain": domain, "site_id": sid, "configured": sid is not None}
