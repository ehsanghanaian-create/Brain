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
        # prices are indicative defaults (user-editable in AI Models) — correct them when Google publishes list prices
        {"model_id": "gemini-3.5-flash", "display": "Gemini 3.5 Flash", "tier": "balanced", "tags": ["persian", "long_form", "json", "translation", "cheap"], "context_tokens": 1000000, "price_in_per_m": 0.3, "price_out_per_m": 2.5},
        {"model_id": "gemini-3.6-flash", "display": "Gemini 3.6 Flash", "tier": "balanced", "tags": ["persian", "long_form", "json", "translation"], "context_tokens": 1000000, "price_in_per_m": 0.5, "price_out_per_m": 3.0},
        {"model_id": "gemini-3.8-flash", "display": "Gemini 3.8 Flash", "tier": "balanced", "tags": ["persian", "long_form", "json", "translation"], "context_tokens": 1000000, "price_in_per_m": 0.5, "price_out_per_m": 3.0},
        {"model_id": "gemini-3.5-flash-lite", "display": "Gemini 3.5 Flash Lite", "tier": "fast", "tags": ["cheap", "json", "translation"], "context_tokens": 1000000, "price_in_per_m": 0.1, "price_out_per_m": 0.4},
        {"model_id": "gemini-3.1-pro-preview", "display": "Gemini 3.1 Pro (preview)", "tier": "reasoning", "tags": ["reasoning", "long_form", "json", "translation"], "context_tokens": 1000000, "price_in_per_m": 1.25, "price_out_per_m": 10.0},
    ],
    "openrouter": [],
    # xAI list prices (USD / 1M tokens) as of 2026-09 — indicative, user-editable; real ids are discovered from /v1/models
    "xai": [
        {"model_id": "grok-4", "display": "Grok 4", "tier": "quality", "tags": ["persian", "long_form", "reasoning", "json"], "context_tokens": 256000, "price_in_per_m": 3.0, "price_out_per_m": 15.0},
        {"model_id": "grok-4-fast-reasoning", "display": "Grok 4 Fast (reasoning)", "tier": "balanced", "tags": ["persian", "long_form", "reasoning", "json", "cheap"], "context_tokens": 2000000, "price_in_per_m": 0.2, "price_out_per_m": 0.5},
        {"model_id": "grok-4-fast-non-reasoning", "display": "Grok 4 Fast", "tier": "fast", "tags": ["cheap", "json", "long_form"], "context_tokens": 2000000, "price_in_per_m": 0.2, "price_out_per_m": 0.5},
        {"model_id": "grok-3-mini", "display": "Grok 3 mini", "tier": "fast", "tags": ["cheap", "json"], "context_tokens": 131072, "price_in_per_m": 0.3, "price_out_per_m": 0.5},
    ],
    # Free-tier execution is cost-free until the provider quota is exhausted; the gateway falls back on HTTP 429.
    "groq": [
        {"model_id": "qwen/qwen3.6-27b", "display": "Qwen 3.6 27B (Groq free tier)", "tier": "quality", "tags": ["persian", "long_form", "reasoning", "json", "free_quota"], "context_tokens": 131072, "price_in_per_m": 0.0, "price_out_per_m": 0.0},
        {"model_id": "openai/gpt-oss-120b", "display": "GPT-OSS 120B (Groq free tier)", "tier": "reasoning", "tags": ["long_form", "reasoning", "json", "free_quota"], "context_tokens": 131072, "price_in_per_m": 0.0, "price_out_per_m": 0.0},
        {"model_id": "openai/gpt-oss-20b", "display": "GPT-OSS 20B (Groq free tier)", "tier": "fast", "tags": ["cheap", "json", "free_quota"], "context_tokens": 131072, "price_in_per_m": 0.0, "price_out_per_m": 0.0},
    ],
    "cloudflare": [
        {"model_id": "@cf/qwen/qwen3-30b-a3b-fp8", "display": "Qwen 3 30B A3B (Workers AI)", "tier": "balanced", "tags": ["persian", "reasoning", "json", "free_quota"], "context_tokens": 32768, "price_in_per_m": 0.0, "price_out_per_m": 0.0},
        {"model_id": "@cf/openai/gpt-oss-20b", "display": "GPT-OSS 20B (Workers AI)", "tier": "fast", "tags": ["json", "reasoning", "free_quota"], "context_tokens": 131072, "price_in_per_m": 0.0, "price_out_per_m": 0.0},
    ],
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


# discovered ids that are not chat/text models — never routed, never seeded (tts, image/video/music generation, embeddings,
# transcription, robotics, computer-use agents, deep-research agents, live/audio variants, tool-only previews)
NON_CHAT_MARKERS = ("tts", "image", "veo", "lyria", "embedding", "transcribe", "robotics", "computer-use", "deep-research", "antigravity",
                    "aqa", "omni", "nano-banana", "native-audio", "-live", "customtools", "imagen", "whisper", "moderation", "rerank", "audio")


def is_chat_model(model_id: str) -> bool:
    m = model_id.lower()
    return not any(x in m for x in NON_CHAT_MARKERS)


def guess_tier(model_id: str) -> tuple[str, list[str]]:
    m = model_id.lower()
    if "grok" in m:
        if "non-reasoning" in m or "mini" in m:
            return "fast", ["cheap", "json"]
        return ("balanced" if "fast" in m else "quality"), ["persian", "long_form", "reasoning", "json"]
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
