"""AI layer: Task → AIRouter → AIProvider → Validator → Memory (SEO Brain phases 9-12).

Phase 1 ships the contracts and an in-process reference implementation (EchoProvider) so the orchestrator
is testable end-to-end without any external API key. Real providers (Claude, OpenAI, Gemini, OpenRouter,
Ollama, custom OpenAI-compatible) are added in Phase 9 behind the same `AIProvider` protocol.
"""
from .types import AIMessage, AIRequest, AIResponse, AITask, TaskKind
from .providers.base import AIProvider, EchoProvider, ProviderError
from .router import AIRouter, Route
from .validator import ValidationError, Validator, JsonKeysValidator, NonEmptyValidator
from .memory import MemoryService
from .orchestrator import AIOrchestrator, OrchestrationResult

__all__ = ["AIMessage", "AIRequest", "AIResponse", "AITask", "TaskKind", "AIProvider", "EchoProvider", "ProviderError",
           "AIRouter", "Route", "ValidationError", "Validator", "JsonKeysValidator", "NonEmptyValidator", "MemoryService",
           "AIOrchestrator", "OrchestrationResult"]
