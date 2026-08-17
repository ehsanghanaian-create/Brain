from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskKind(str, Enum):
    CONTENT_WRITING = "content_writing"
    SEO_ANALYSIS = "seo_analysis"
    RESEARCH = "research"
    BRIEF = "brief"
    KEYWORD_ANALYSIS = "keyword_analysis"
    INTERNAL_LINKING = "internal_linking"
    SCHEMA = "schema"
    GENERIC = "generic"


@dataclass
class AIMessage:
    role: str          # system | user | assistant
    content: str


@dataclass
class AITask:
    """What the caller wants done. Provider/model are chosen by the router, never by the caller."""
    kind: TaskKind
    site_id: str
    messages: list[AIMessage]
    json_schema: dict[str, Any] | None = None       # when set, providers must return JSON matching it (validator checks keys)
    max_tokens: int = 2048
    temperature: float = 0.3
    prompt_id: str | None = None                    # Prompt Library reference (phase 11)
    prompt_version: str | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None


@dataclass
class AIRequest:
    """Provider-level request produced by the router (task + resolved model)."""
    model: str
    messages: list[AIMessage]
    max_tokens: int
    temperature: float
    json_schema: dict[str, Any] | None = None


@dataclass
class AIResponse:
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)
    parsed: Any = None      # filled by the validator when json_schema was requested
