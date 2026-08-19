"""External provider adapters that plug into the AI Gateway (additive to `ai/gateway/adapters.py`).

`ProviderAdapter` is the contract every adapter satisfies (structural — HttpAdapter subclasses conform):
    test() · list_models() · complete() · stream() · estimate() · capabilities()
"""
from __future__ import annotations

from typing import Any, Iterator, Protocol, runtime_checkable

from ...types import AIRequest, AIResponse


@runtime_checkable
class ProviderAdapter(Protocol):
    name: str
    kind: str

    def test(self) -> dict[str, Any]: ...
    def list_models(self) -> list[str]: ...
    def complete(self, request: AIRequest) -> AIResponse: ...
    def stream(self, request: AIRequest) -> Iterator[str | AIResponse]: ...
    def estimate(self, request: AIRequest) -> dict[str, Any]: ...
    def capabilities(self) -> dict[str, Any]: ...


from .omniroute import OmniRouteAdapter  # noqa: E402

__all__ = ["ProviderAdapter", "OmniRouteAdapter"]
