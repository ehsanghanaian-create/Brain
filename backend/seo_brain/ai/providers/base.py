"""AIProvider contract + reference EchoProvider (no network, used by tests and as a safe default)."""
from __future__ import annotations

import json
import time
from typing import Protocol, runtime_checkable

from ..types import AIRequest, AIResponse


class ProviderError(RuntimeError):
    """Raised for provider-side failures (auth, rate limit, network, invalid model). Router may fall back."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@runtime_checkable
class AIProvider(Protocol):
    name: str
    models: tuple[str, ...]

    def complete(self, request: AIRequest) -> AIResponse: ...
    def test_connection(self) -> dict: ...


class EchoProvider:
    """Deterministic provider: returns the last user message (or a JSON object with the requested keys).

    Never calls the network. Useful for tests, dry-runs and the 'manual' site mode where the UI shows what
    *would* be sent without spending tokens.
    """
    name = "echo"
    models = ("echo-1",)

    def __init__(self, fail: bool = False):
        self._fail = fail

    def complete(self, request: AIRequest) -> AIResponse:
        t0 = time.perf_counter()
        if self._fail:
            raise ProviderError("echo provider configured to fail", retryable=True)
        last_user = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
        if request.json_schema:
            keys = list((request.json_schema.get("properties") or {}).keys()) or list(request.json_schema.get("required") or [])
            text = json.dumps({k: f"echo:{k}" for k in keys}, ensure_ascii=False)
        else:
            text = last_user
        return AIResponse(text=text, model=request.model, provider=self.name, input_tokens=len(last_user.split()),
                          output_tokens=len(text.split()), cost_usd=0.0, latency_ms=int((time.perf_counter() - t0) * 1000),
                          raw={"echo": True})

    def test_connection(self) -> dict:
        return {"ok": not self._fail, "provider": self.name, "models": list(self.models)}
