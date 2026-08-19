"""AI Content Test Workspace endpoints (temporary visual test surface for generation, on top of the Phase-9 gateway):
GET /sites/{id}/ai-workspace/options · POST /estimate · POST /generate · POST /save-draft · GET /history."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...ai.gateway import BudgetExceeded, Gateway
from ...brain.generation.workspace import ContentSpec, ContentTestWorkspace
from ..deps import gateway, require_site
from ..errors import ApiError

router = APIRouter(prefix="/sites/{site_id}/ai-workspace", tags=["ai-workspace"], dependencies=[Depends(require_site)])


def ws(g: Gateway = Depends(gateway)) -> ContentTestWorkspace:
    return ContentTestWorkspace(g.engine, g)


class SpecBody(BaseModel):
    title: str = Field(min_length=1)
    keyword: str = Field(min_length=1)
    secondary_keywords: list[str] = Field(default_factory=list)
    intent: str = "informational"
    content_type: str = "article"
    category: str | None = None
    audience: str | None = None
    tone: str = "formal"
    word_count: int = Field(default=1200, ge=150, le=6000)
    instructions: str | None = None
    provider: str | None = None
    model: str | None = None

    def spec(self) -> ContentSpec:
        return ContentSpec(title=self.title, keyword=self.keyword, secondary_keywords=[s.strip() for s in self.secondary_keywords if s.strip()], intent=self.intent, content_type=self.content_type,
                           category=self.category, audience=self.audience, tone=self.tone, word_count=self.word_count, instructions=self.instructions)


class SaveDraftBody(BaseModel):
    content_id: int
    markdown: str = Field(min_length=1)
    title: str | None = None
    meta_description: str | None = None
    meta: dict[str, Any] | None = None


@router.get("/options")
def options(site_id: str, w: ContentTestWorkspace = Depends(ws)) -> dict:
    return w.options(site_id)


@router.post("/estimate")
def estimate(site_id: str, body: SpecBody, w: ContentTestWorkspace = Depends(ws)) -> dict:
    return w.estimate(site_id, body.spec(), body.provider, body.model)


@router.post("/generate")
def generate(site_id: str, body: SpecBody, w: ContentTestWorkspace = Depends(ws)) -> dict:
    """Runs the single writer step through Gateway (Echo or a configured provider). Output is shown only — saving is a separate human action."""
    try:
        out = w.generate(site_id, body.spec(), body.provider, body.model)
    except BudgetExceeded as e:
        raise ApiError(409, str(e), code="budget_exceeded")
    if not out.get("ok"):
        raise ApiError(502, f"تولید ناموفق بود: {out.get('error')}", code="generation_failed", details={"attempts": out.get("attempts"), "route": out.get("route")})
    return out


@router.post("/save-draft", status_code=201)
def save_draft(site_id: str, body: SaveDraftBody, w: ContentTestWorkspace = Depends(ws)) -> dict:
    try:
        return w.save_draft(site_id, body.content_id, body.markdown, body.title, body.meta_description, body.meta)
    except KeyError:
        raise ApiError(404, "content not found", code="not_found")


@router.get("/history")
def history(site_id: str, limit: int = 20, w: ContentTestWorkspace = Depends(ws)) -> list[dict]:
    return w.history(site_id, limit)
