"""Pydantic schemas for the v1 API (request bodies; responses are plain dicts from the domain layer)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

Mode = Literal["manual", "assisted", "autopilot"]


class SiteCreate(BaseModel):
    site_id: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]{1,62}$", description="stable slug, e.g. emdadmodiran")
    name: str
    canonical_url: HttpUrl
    wp_url: HttpUrl | None = None
    language: str | None = "fa-IR"
    country: str | None = "IR"
    business_type: str | None = None
    gsc_property: str | None = None
    ga4_property: str | None = None
    mode: Mode = "manual"


class SiteUpdate(BaseModel):
    name: str | None = None
    wp_url: HttpUrl | None = None
    language: str | None = None
    country: str | None = None
    business_type: str | None = None
    gsc_property: str | None = None
    ga4_property: str | None = None
    mode: Mode | None = None


class MemoryUpdate(BaseModel):
    business_rules: list[str] | None = None
    tone: dict[str, Any] | None = None
    content_rules: list[str] | None = None
    successful_patterns: list[dict[str, Any]] | None = None


class AIRunRequest(BaseModel):
    kind: str = "generic"
    prompt: str
    system: str | None = None
    json_keys: list[str] | None = None
    learn_pattern: str | None = None
    learn_evidence: str | None = None


class JobEnqueue(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
