"""AIOrchestrator — the single entry point for every AI call in the platform.

    task ──▶ memory.context_messages ──▶ router.resolve ──▶ provider.complete ──▶ validator ──▶ (memory.record_success)
                                            │ fallback on ProviderError / ValidationError
                                            ▼ next route in chain

Every attempt is returned in `OrchestrationResult.attempts` (provider, model, ok, error, latency) so the UI
and the `ai_calls` usage log (phase 9) can show exactly what happened. Nothing is written to memory unless a
response passed validation and the caller asked for it (`learn=`).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .memory import MemoryService
from .providers.base import ProviderError
from .router import AIRouter, Route
from .types import AIMessage, AIResponse, AITask
from .validator import ChainValidator, JsonKeysValidator, NonEmptyValidator, ValidationError, Validator

log = logging.getLogger("ai.orchestrator")


@dataclass
class Attempt:
    provider: str
    model: str
    ok: bool
    error: str | None = None
    latency_ms: int = 0


@dataclass
class OrchestrationResult:
    response: AIResponse | None
    attempts: list[Attempt] = field(default_factory=list)
    route_used: Route | None = None
    memory_used: bool = False

    @property
    def ok(self) -> bool:
        return self.response is not None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "route_used": self.route_used.__dict__ if self.route_used else None,
                "memory_used": self.memory_used, "attempts": [a.__dict__ for a in self.attempts],
                "response": None if not self.response else {"text": self.response.text, "parsed": self.response.parsed,
                                                              "model": self.response.model, "provider": self.response.provider,
                                                              "input_tokens": self.response.input_tokens,
                                                              "output_tokens": self.response.output_tokens,
                                                              "cost_usd": self.response.cost_usd, "latency_ms": self.response.latency_ms}}


class AIOrchestrator:
    def __init__(self, router: AIRouter, memory: MemoryService | None = None, validator: Validator | None = None):
        self.router = router
        self.memory = memory
        self.validator = validator or ChainValidator(NonEmptyValidator(), JsonKeysValidator())

    def run(self, task: AITask, learn: dict[str, str] | None = None) -> OrchestrationResult:
        """Execute a task through the route chain. `learn={"pattern": ..., "evidence": ...}` records a memory
        entry on success (only after validation)."""
        result = OrchestrationResult(response=None)
        messages: list[AIMessage] = []
        if self.memory is not None:
            ctx = self.memory.context_messages(task.site_id)
            if ctx:
                messages.extend(ctx)
                result.memory_used = True
        messages.extend(task.messages)
        task_for_provider = AITask(**{**task.__dict__, "messages": messages})

        for route in self.router.resolve(task):
            provider = self.router.providers[route.provider]
            t0 = time.perf_counter()
            try:
                resp = provider.complete(self.router.build_request(task_for_provider, route))
                resp = self.validator.validate(task, resp)
            except (ProviderError, ValidationError) as e:
                ms = int((time.perf_counter() - t0) * 1000)
                result.attempts.append(Attempt(route.provider, route.model, False, f"{e.__class__.__name__}: {e}", ms))
                log.warning(f"ai route {route.provider}/{route.model} failed for {task.kind.value}: {e}")
                continue
            ms = int((time.perf_counter() - t0) * 1000)
            result.attempts.append(Attempt(route.provider, route.model, True, None, ms))
            result.response, result.route_used = resp, route
            if learn and self.memory is not None:
                self.memory.record_success(task.site_id, learn.get("pattern", ""), learn.get("evidence", ""),
                                           source=f"{task.kind.value}:{route.provider}/{route.model}", run_id=task.run_id)
            return result
        return result
