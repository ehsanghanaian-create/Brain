"""AIRouter: maps a TaskKind (optionally per site) to an ordered chain of (provider, model) with fallback.

Phase 1: routes are configured in code / config dict. Phase 10 persists them in `ai_routes` and exposes
them in the UI (Content Writing → Claude, SEO Analysis → GPT, Research → Gemini, …).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .providers.base import AIProvider
from .types import AIRequest, AITask, TaskKind


@dataclass(frozen=True)
class Route:
    provider: str
    model: str


@dataclass
class AIRouter:
    providers: dict[str, AIProvider]
    routes: dict[TaskKind, list[Route]] = field(default_factory=dict)      # primary first, then fallbacks
    site_routes: dict[tuple[str, TaskKind], list[Route]] = field(default_factory=dict)
    default: list[Route] = field(default_factory=list)

    def register(self, provider: AIProvider) -> None:
        self.providers[provider.name] = provider

    def set_route(self, kind: TaskKind, chain: list[Route], site_id: str | None = None) -> None:
        if site_id:
            self.site_routes[(site_id, kind)] = list(chain)
        else:
            self.routes[kind] = list(chain)

    def resolve(self, task: AITask) -> list[Route]:
        chain = self.site_routes.get((task.site_id, task.kind)) or self.routes.get(task.kind) or self.default
        chain = [r for r in chain if r.provider in self.providers]
        if not chain:
            raise LookupError(f"no AI route configured for task '{task.kind.value}' (site={task.site_id})")
        return chain

    def build_request(self, task: AITask, route: Route) -> AIRequest:
        return AIRequest(model=route.model, messages=list(task.messages), max_tokens=task.max_tokens,
                         temperature=task.temperature, json_schema=task.json_schema)

    def describe(self) -> dict:
        return {"providers": sorted(self.providers), "default": [r.__dict__ for r in self.default],
                "routes": {k.value: [r.__dict__ for r in v] for k, v in self.routes.items()},
                "site_routes": {f"{s}:{k.value}": [r.__dict__ for r in v] for (s, k), v in self.site_routes.items()}}
