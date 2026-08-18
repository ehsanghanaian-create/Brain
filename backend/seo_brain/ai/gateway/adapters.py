"""Provider adapters — one interface (`AIProvider` compatible): complete(AIRequest) → AIResponse, test_connection(),
list_models(), estimate(). HTTP via httpx with an injectable transport (tests never hit the network).
Business logic never imports these directly — only the Gateway does."""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from ..providers.base import ProviderError
from ..types import AIRequest, AIResponse
from .catalog import estimate_tokens


def _json_instruction(schema: dict | None) -> str:
    if not schema:
        return ""
    keys = list((schema.get("properties") or {}).keys()) or list(schema.get("required") or [])
    return "\n\nپاسخ را فقط به‌صورت یک شیء JSON معتبر با کلیدهای " + ", ".join(keys) + " برگردان؛ بدون متن اضافه و بدون بلوک کد."


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


class HttpAdapter:
    """Base: holds name, base_url, key, model list, pricing lookup, httpx client (transport injectable)."""
    kind = "custom"

    def __init__(self, name: str, api_key: str | None, base_url: str | None, models: list[str] | None = None, prices: dict[str, tuple[float, float]] | None = None,
                 transport: httpx.BaseTransport | None = None, timeout: float = 120.0):
        self.name = name
        self.api_key = api_key
        self.base_url = (base_url or self.default_base_url()).rstrip("/")
        self.models: tuple[str, ...] = tuple(models or [])
        self.prices = prices or {}
        self._client = httpx.Client(timeout=timeout, transport=transport) if transport is not None else httpx.Client(timeout=timeout)

    def default_base_url(self) -> str:
        return ""

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _cost(self, model: str, inp: int, out: int) -> float:
        pi, po = self.prices.get(model, (0.0, 0.0))
        return round((inp * pi + out * po) / 1_000_000, 6)

    def _post(self, url: str, body: dict, headers: dict | None = None) -> dict:
        try:
            r = self._client.post(url, json=body, headers={**self._headers(), **(headers or {})})
        except httpx.HTTPError as e:
            raise ProviderError(f"network error: {e.__class__.__name__}", retryable=True) from e
        if r.status_code in (401, 403):
            raise ProviderError(f"unauthorized (HTTP {r.status_code})", retryable=False)
        if r.status_code == 404:
            raise ProviderError(f"model or endpoint not found (HTTP 404): {r.text[:120]}", retryable=False)
        if r.status_code == 429 or r.status_code >= 500:
            raise ProviderError(f"provider busy/error (HTTP {r.status_code})", retryable=True)
        if r.status_code >= 400:
            raise ProviderError(f"bad request (HTTP {r.status_code}): {r.text[:200]}", retryable=False)
        try:
            return r.json()
        except ValueError as e:
            raise ProviderError("invalid JSON from provider", retryable=True) from e

    def _get(self, url: str, headers: dict | None = None) -> httpx.Response:
        try:
            return self._client.get(url, headers={**self._headers(), **(headers or {})})
        except httpx.HTTPError as e:
            raise ProviderError(f"network error: {e.__class__.__name__}", retryable=True) from e

    def estimate(self, request: AIRequest) -> dict[str, Any]:
        inp = sum(estimate_tokens(m.content) for m in request.messages)
        out = min(request.max_tokens, max(200, inp // 2))
        return {"input_tokens": inp, "output_tokens": out, "cost_usd": self._cost(request.model, inp, out)}

    def test_connection(self) -> dict:
        try:
            models = self.list_models()
        except ProviderError as e:
            return {"ok": False, "provider": self.name, "error": str(e), "retryable": e.retryable}
        return {"ok": True, "provider": self.name, "models": models[:50]}

    def list_models(self) -> list[str]:  # pragma: no cover - overridden
        return list(self.models)

    def complete(self, request: AIRequest) -> AIResponse:  # pragma: no cover - overridden
        raise NotImplementedError


class AnthropicAdapter(HttpAdapter):
    kind = "anthropic"

    def default_base_url(self) -> str:
        return "https://api.anthropic.com"

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "x-api-key": self.api_key or "", "anthropic-version": "2023-06-01"}

    def list_models(self) -> list[str]:
        r = self._get(f"{self.base_url}/v1/models")
        if r.status_code in (401, 403):
            raise ProviderError("unauthorized", retryable=False)
        if r.status_code != 200:
            raise ProviderError(f"HTTP {r.status_code}", retryable=True)
        return [m.get("id") for m in (r.json().get("data") or []) if m.get("id")]

    def complete(self, request: AIRequest) -> AIResponse:
        t0 = time.perf_counter()
        system = "\n\n".join(m.content for m in request.messages if m.role == "system")
        msgs = [{"role": m.role, "content": m.content} for m in request.messages if m.role != "system"]
        if request.json_schema and msgs:
            msgs[-1] = {"role": msgs[-1]["role"], "content": msgs[-1]["content"] + _json_instruction(request.json_schema)}
        body: dict[str, Any] = {"model": request.model, "max_tokens": request.max_tokens, "temperature": request.temperature, "messages": msgs}
        if system:
            body["system"] = system
        data = self._post(f"{self.base_url}/v1/messages", body)
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        u = data.get("usage") or {}
        inp, out = int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
        return AIResponse(text=_strip_fences(text) if request.json_schema else text, model=data.get("model", request.model), provider=self.name, input_tokens=inp, output_tokens=out,
                          cost_usd=self._cost(request.model, inp, out), latency_ms=int((time.perf_counter() - t0) * 1000), raw={"id": data.get("id"), "stop_reason": data.get("stop_reason")})


class OpenAICompatAdapter(HttpAdapter):
    """OpenAI, OpenRouter, and any OpenAI-compatible endpoint (custom): POST {base}/chat/completions."""
    kind = "openai"

    def default_base_url(self) -> str:
        return "https://api.openai.com/v1"

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        if "openrouter" in self.base_url:
            h["HTTP-Referer"] = "http://127.0.0.1:3000"; h["X-Title"] = "SEO Brain"
        return h

    def list_models(self) -> list[str]:
        r = self._get(f"{self.base_url}/models")
        if r.status_code in (401, 403):
            raise ProviderError("unauthorized", retryable=False)
        if r.status_code != 200:
            raise ProviderError(f"HTTP {r.status_code}", retryable=True)
        return [m.get("id") for m in (r.json().get("data") or []) if m.get("id")]

    def complete(self, request: AIRequest) -> AIResponse:
        t0 = time.perf_counter()
        msgs = [{"role": m.role, "content": m.content} for m in request.messages]
        body: dict[str, Any] = {"model": request.model, "messages": msgs, "temperature": request.temperature, "max_tokens": request.max_tokens}
        if request.json_schema:
            body["response_format"] = {"type": "json_object"}
            msgs[-1] = {"role": msgs[-1]["role"], "content": msgs[-1]["content"] + _json_instruction(request.json_schema)}
        data = self._post(f"{self.base_url}/chat/completions", body)
        choice = (data.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content")) or ""
        u = data.get("usage") or {}
        inp, out = int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))
        return AIResponse(text=_strip_fences(text) if request.json_schema else text, model=data.get("model", request.model), provider=self.name, input_tokens=inp, output_tokens=out,
                          cost_usd=self._cost(request.model, inp, out), latency_ms=int((time.perf_counter() - t0) * 1000), raw={"id": data.get("id"), "finish_reason": choice.get("finish_reason")})


class GeminiAdapter(HttpAdapter):
    kind = "google"

    def default_base_url(self) -> str:
        return "https://generativelanguage.googleapis.com/v1beta"

    def list_models(self) -> list[str]:
        r = self._get(f"{self.base_url}/models?key={self.api_key}")
        if r.status_code in (400, 401, 403):
            raise ProviderError("unauthorized", retryable=False)
        if r.status_code != 200:
            raise ProviderError(f"HTTP {r.status_code}", retryable=True)
        return [str(m.get("name", "")).replace("models/", "") for m in (r.json().get("models") or [])]

    def complete(self, request: AIRequest) -> AIResponse:
        t0 = time.perf_counter()
        system = "\n\n".join(m.content for m in request.messages if m.role == "system")
        contents = [{"role": "user" if m.role == "user" else "model", "parts": [{"text": m.content}]} for m in request.messages if m.role != "system"]
        if request.json_schema and contents:
            contents[-1]["parts"][0]["text"] += _json_instruction(request.json_schema)
        body: dict[str, Any] = {"contents": contents, "generationConfig": {"temperature": request.temperature, "maxOutputTokens": request.max_tokens, **({"responseMimeType": "application/json"} if request.json_schema else {})}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        data = self._post(f"{self.base_url}/models/{request.model}:generateContent?key={self.api_key}", body)
        cands = data.get("candidates") or []
        text = "".join(p.get("text", "") for c in cands[:1] for p in ((c.get("content") or {}).get("parts") or []))
        u = data.get("usageMetadata") or {}
        inp, out = int(u.get("promptTokenCount", 0)), int(u.get("candidatesTokenCount", 0))
        return AIResponse(text=_strip_fences(text) if request.json_schema else text, model=request.model, provider=self.name, input_tokens=inp, output_tokens=out,
                          cost_usd=self._cost(request.model, inp, out), latency_ms=int((time.perf_counter() - t0) * 1000), raw={"finish_reason": (cands[0].get("finishReason") if cands else None)})


class OllamaAdapter(HttpAdapter):
    kind = "ollama"

    def default_base_url(self) -> str:
        return "http://127.0.0.1:11434"

    def list_models(self) -> list[str]:
        r = self._get(f"{self.base_url}/api/tags")
        if r.status_code != 200:
            raise ProviderError(f"HTTP {r.status_code}", retryable=True)
        return [m.get("name") for m in (r.json().get("models") or []) if m.get("name")]

    def complete(self, request: AIRequest) -> AIResponse:
        t0 = time.perf_counter()
        msgs = [{"role": m.role, "content": m.content} for m in request.messages]
        if request.json_schema:
            msgs[-1] = {"role": msgs[-1]["role"], "content": msgs[-1]["content"] + _json_instruction(request.json_schema)}
        body: dict[str, Any] = {"model": request.model, "messages": msgs, "stream": False, "options": {"temperature": request.temperature, "num_predict": request.max_tokens}}
        if request.json_schema:
            body["format"] = "json"
        data = self._post(f"{self.base_url}/api/chat", body)
        text = ((data.get("message") or {}).get("content")) or ""
        inp, out = int(data.get("prompt_eval_count", 0) or 0), int(data.get("eval_count", 0) or 0)
        return AIResponse(text=_strip_fences(text) if request.json_schema else text, model=request.model, provider=self.name, input_tokens=inp, output_tokens=out, cost_usd=0.0,
                          latency_ms=int((time.perf_counter() - t0) * 1000), raw={"done_reason": data.get("done_reason")})


ADAPTERS = {"anthropic": AnthropicAdapter, "openai": OpenAICompatAdapter, "openrouter": OpenAICompatAdapter, "custom": OpenAICompatAdapter, "google": GeminiAdapter, "ollama": OllamaAdapter}


def make_adapter(kind: str, name: str, api_key: str | None, base_url: str | None, models: list[str] | None, prices: dict[str, tuple[float, float]] | None,
                 transport: httpx.BaseTransport | None = None) -> HttpAdapter:
    cls = ADAPTERS.get(kind)
    if not cls:
        raise ProviderError(f"unknown provider kind '{kind}'", retryable=False)
    a = cls(name, api_key, base_url, models, prices, transport)
    if kind == "openrouter" and not base_url:
        a.base_url = "https://openrouter.ai/api/v1"
    return a
