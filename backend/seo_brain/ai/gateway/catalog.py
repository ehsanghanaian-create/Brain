"""Built-in model catalog: tier, tags, context, list prices (USD per 1M tokens). Editable per provider in `ai_models`.
Prices are indicative defaults — the user can correct them in AI Models; local/OpenRouter default to 0 or user-set."""
from __future__ import annotations

from typing import Any

TIERS = ("fast", "balanced", "quality", "reasoning")

DEFAULT_CATALOG: dict[str, list[dict[str, Any]]] = {
    # Anthropic list prices (USD / 1M tokens) as of 2026-08; aliases without date suffix are the stable IDs.
    "anthropic": [
        {"model_id": "claude-sonnet-5", "display": "Claude Sonnet 5", "tier": "balanced", "tags": ["persian", "long_form", "json", "translation"], "context_tokens": 1000000, "price_in_per_m": 3.0, "price_out_per_m": 15.0},
        {"model_id": "claude-opus-5", "display": "Claude Opus 5", "tier": "quality", "tags": ["persian", "long_form", "reasoning", "json"], "context_tokens": 1000000, "price_in_per_m": 5.0, "price_out_per_m": 25.0},
        {"model_id": "claude-haiku-4-5", "display": "Claude Haiku 4.5", "tier": "fast", "tags": ["cheap", "json", "translation"], "context_tokens": 200000, "price_in_per_m": 1.0, "price_out_per_m": 5.0},
        {"model_id": "claude-opus-4-8", "display": "Claude Opus 4.8", "tier": "quality", "tags": ["persian", "long_form", "reasoning", "json"], "context_tokens": 1000000, "price_in_per_m": 5.0, "price_out_per_m": 25.0},
        {"model_id": "claude-sonnet-4-6", "display": "Claude Sonnet 4.6", "tier": "balanced", "tags": ["persian", "long_form", "json"], "context_tokens": 1000000, "price_in_per_m": 3.0, "price_out_per_m": 15.0},
        {"model_id": "claude-fable-5", "display": "Claude Fable 5", "tier": "reasoning", "tags": ["persian", "long_form", "reasoning", "json"], "context_tokens": 1000000, "price_in_per_m": 10.0, "price_out_per_m": 50.0},
    ],
    "openai": [
        {"model_id": "gpt-5", "display": "GPT-5", "tier": "reasoning", "tags": ["reasoning", "long_form", "json"], "context_tokens": 400000, "price_in_per_m": 1.25, "price_out_per_m": 10.0},
        {"model_id": "gpt-5-mini", "display": "GPT-5 mini", "tier": "balanced", "tags": ["cheap", "json"], "context_tokens": 400000, "price_in_per_m": 0.25, "price_out_per_m": 2.0},
        {"model_id": "gpt-4.1", "display": "GPT-4.1", "tier": "quality", "tags": ["long_form", "json", "translation"], "context_tokens": 1000000, "price_in_per_m": 2.0, "price_out_per_m": 8.0},
        {"model_id": "gpt-4o-mini", "display": "GPT-4o mini", "tier": "fast", "tags": ["cheap", "json", "translation"], "context_tokens": 128000, "price_in_per_m": 0.15, "price_out_per_m": 0.6},
    ],
    "google": [
        {"model_id": "gemini-2.5-pro", "display": "Gemini 2.5 Pro", "tier": "reasoning", "tags": ["reasoning", "long_form", "json", "translation"], "context_tokens": 1000000, "price_in_per_m": 1.25, "price_out_per_m": 10.0},
        {"model_id": "gemini-2.5-flash", "display": "Gemini 2.5 Flash", "tier": "fast", "tags": ["cheap", "json", "translation"], "context_tokens": 1000000, "price_in_per_m": 0.3, "price_out_per_m": 2.5},
    ],
    "openrouter": [],
    "ollama": [],
    "custom": [],
    # OmniRoute auto-routing entries (prices unknown → 0, user-editable); real provider/model ids are discovered from /v1/models
    "omniroute": [
        {"model_id": "auto", "display": "OmniRoute auto (14-factor routing)", "tier": "balanced", "tags": ["json", "long_form", "gateway"], "context_tokens": None, "price_in_per_m": 0.0, "price_out_per_m": 0.0},
        {"model_id": "auto/fast", "display": "OmniRoute auto/fast", "tier": "fast", "tags": ["json", "cheap", "gateway"], "context_tokens": None, "price_in_per_m": 0.0, "price_out_per_m": 0.0},
        {"model_id": "auto/cheap", "display": "OmniRoute auto/cheap", "tier": "fast", "tags": ["json", "cheap", "gateway"], "context_tokens": None, "price_in_per_m": 0.0, "price_out_per_m": 0.0},
        {"model_id": "auto/coding", "display": "OmniRoute auto/coding", "tier": "balanced", "tags": ["json", "gateway", "coding"], "context_tokens": None, "price_in_per_m": 0.0, "price_out_per_m": 0.0},
    ],
}


def default_models_for(kind: str) -> list[dict[str, Any]]:
    return [dict(m) for m in DEFAULT_CATALOG.get(kind, [])]


def guess_tier(model_id: str) -> tuple[str, list[str]]:
    m = model_id.lower()
    if "sonnet" in m:
        return "balanced", ["persian", "long_form", "json"]
    if "haiku" in m:
        return "fast", ["cheap", "json"]
    if any(x in m for x in ("opus", "fable", "gpt-4.1")):
        return "quality", ["long_form", "json"]
    if any(x in m for x in ("o1", "o3", "gpt-5", "reason", "pro", "r1", "think")):
        return "reasoning", ["reasoning", "json"]
    if any(x in m for x in ("mini", "flash", "haiku", "small", "lite", "nano", "8b", "7b", "3b")):
        return "fast", ["cheap", "json"]
    return "balanced", ["json"]


def cost_usd(input_tokens: int, output_tokens: int, price_in_per_m: float, price_out_per_m: float) -> float:
    return round((input_tokens * (price_in_per_m or 0) + output_tokens * (price_out_per_m or 0)) / 1_000_000, 6)


def estimate_tokens(text: str) -> int:
    """Rough, provider-agnostic estimate (~3.2 chars/token for Persian, 4 for Latin)."""
    if not text:
        return 0
    fa = sum(1 for ch in text if "؀" <= ch <= "ۿ")
    return int(fa / 3.2 + (len(text) - fa) / 4.0) + 1
