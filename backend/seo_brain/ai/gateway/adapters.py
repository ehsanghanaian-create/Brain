"""Provider adapters — one interface (`AIProvider` compatible): complete(AIRequest) → AIResponse, test_connection(),
list_models(), estimate(). HTTP via httpx with an injectable transport (tests never hit the network).
Business logic never imports these directly — only the Gateway does."""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

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
                 transport: httpx.BaseTransport | None = None, timeout: float = 300.0):
        self.name = name
        self.api_key = api_key
        self.base_url = (base_url or self.default_base_url()).rstrip("/")
        self.models: tuple[str, ...] = tuple(models or [])
        self.prices = prices or {}
        to = httpx.Timeout(timeout, connect=20.0)   # read timeout is per-chunk when streaming
        if transport is not None:
            self._client = httpx.Client(timeout=to, transport=transport)
        else:
            from ...common.http import ai_proxy
            local = any(h in self.base_url for h in ("127.0.0.1", "localhost"))
            self._client = httpx.Client(timeout=to, proxy=None if local else ai_proxy())

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

    # ---- ProviderAdapter contract defaults (see ai/gateway/providers/__init__.py)
    def test(self) -> dict:
        return self.test_connection()

    def stream(self, request: AIRequest):
        """Default: no token streaming — yield the whole text once, then the AIResponse."""
        resp = self.complete(request)
        yield resp.text
        yield resp

    def capabilities(self) -> dict[str, Any]:
        return {"gateway": False, "streaming": False, "json_mode": True, "dynamic_models": True, "auth": "api_key" if self.api_key else "none", "wire": self.kind}


class AnthropicAdapter(HttpAdapter):
    """Claude via the Messages API (raw HTTP through the shared httpx client so the fake transports keep working).

    - streams every completion (`stream: true`) and re-assembles text/usage from SSE — long articles no longer hit idle timeouts;
      a plain JSON body (older proxies, tests) is accepted too;
    - `temperature` is only sent to models that still accept it (removed on Opus 4.7+/Sonnet 5/Fable 5 → 400);
    - `estimate()` uses `/v1/messages/count_tokens` (exact input count) and falls back to the heuristic;
    - `stop_reason == "refusal"` surfaces as a non-retryable ProviderError instead of an empty draft.
    """
    kind = "anthropic"
    API_VERSION = "2023-06-01"
    # models where sampling params (temperature/top_p/top_k) are rejected with HTTP 400
    _NO_SAMPLING = ("opus-4-7", "opus-4-8", "opus-5", "sonnet-5", "fable", "mythos")

    def default_base_url(self) -> str:
        return "https://api.anthropic.com"

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "x-api-key": self.api_key or "", "anthropic-version": self.API_VERSION}

    @classmethod
    def accepts_temperature(cls, model: str) -> bool:
        m = (model or "").lower()
        return not any(x in m for x in cls._NO_SAMPLING)

    def list_models(self) -> list[str]:
        out: list[str] = []
        after = None
        for _ in range(5):  # paginate (page size 100) — read-only
            r = self._get(f"{self.base_url}/v1/models?limit=100" + (f"&after_id={after}" if after else ""))
            if r.status_code in (401, 403):
                raise ProviderError("unauthorized", retryable=False)
            if r.status_code != 200:
                raise ProviderError(f"HTTP {r.status_code}", retryable=True)
            data = r.json()
            page = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
            out += page
            if not data.get("has_more") or not page:
                break
            after = data.get("last_id") or page[-1]
        return out

    def _body(self, request: AIRequest, stream: bool) -> dict[str, Any]:
        system = "\n\n".join(m.content for m in request.messages if m.role == "system")
        msgs = [{"role": m.role, "content": m.content} for m in request.messages if m.role != "system"]
        if request.json_schema and msgs:
            msgs[-1] = {"role": msgs[-1]["role"], "content": msgs[-1]["content"] + _json_instruction(request.json_schema)}
        body: dict[str, Any] = {"model": request.model, "max_tokens": request.max_tokens, "messages": msgs}
        if self.accepts_temperature(request.model) and request.temperature is not None:
            body["temperature"] = request.temperature
        if system:
            body["system"] = system
        if stream:
            body["stream"] = True
        return body

    def estimate(self, request: AIRequest) -> dict[str, Any]:
        base = super().estimate(request)
        if not self.api_key:
            return base
        body = self._body(request, stream=False); body.pop("max_tokens", None); body.pop("temperature", None)
        try:
            data = self._post(f"{self.base_url}/v1/messages/count_tokens", body)
        except ProviderError:
            return base
        if isinstance(data, dict) and isinstance(data.get("input_tokens"), int):
            inp = int(data["input_tokens"]); out = base["output_tokens"]
            return {"input_tokens": inp, "output_tokens": out, "cost_usd": self._cost(request.model, inp, out), "exact": True}
        return base

    def complete(self, request: AIRequest, on_delta: Callable[[str], None] | None = None) -> AIResponse:
        t0 = time.perf_counter()
        body = self._body(request, stream=True)
        data = self._post_stream(f"{self.base_url}/v1/messages", body, on_delta)
        stop = data.get("stop_reason")
        if stop == "refusal":
            det = data.get("stop_details") or {}
            raise ProviderError(f"مدل درخواست را رد کرد (refusal{': ' + str(det.get('category')) if det.get('category') else ''})", retryable=False)
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        u = data.get("usage") or {}
        inp, out = int(u.get("input_tokens", 0) or 0), int(u.get("output_tokens", 0) or 0)
        return AIResponse(text=_strip_fences(text) if request.json_schema else text, model=data.get("model", request.model), provider=self.name, input_tokens=inp, output_tokens=out,
                          cost_usd=self._cost(request.model, inp, out), latency_ms=int((time.perf_counter() - t0) * 1000),
                          raw={"id": data.get("id"), "stop_reason": stop, "cache_read_input_tokens": u.get("cache_read_input_tokens"), "streamed": bool(data.get("_streamed"))})

    def _post_stream(self, url: str, body: dict, on_delta: Callable[[str], None] | None) -> dict:
        """POST with stream=true; consume SSE into a message dict. Falls back to plain JSON when the server does not stream."""
        try:
            with self._client.stream("POST", url, json=body, headers=self._headers()) as r:
                if r.status_code >= 400:
                    r.read()
                    self._raise_status(r)
                ctype = r.headers.get("content-type", "")
                if "text/event-stream" not in ctype:
                    r.read()
                    try:
                        return r.json()
                    except ValueError as e:
                        raise ProviderError("invalid JSON from provider", retryable=True) from e
                msg: dict[str, Any] = {"content": [], "usage": {}, "_streamed": True}
                blocks: dict[int, dict] = {}
                for line in r.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    try:
                        ev = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    et = ev.get("type")
                    if et == "message_start":
                        m = ev.get("message") or {}
                        msg.update({k: m.get(k) for k in ("id", "model")}); msg["usage"] = dict(m.get("usage") or {})
                    elif et == "content_block_start":
                        blocks[ev.get("index", 0)] = dict(ev.get("content_block") or {}); blocks[ev.get("index", 0)].setdefault("text", "")
                    elif et == "content_block_delta":
                        d = ev.get("delta") or {}
                        if d.get("type") == "text_delta":
                            b = blocks.setdefault(ev.get("index", 0), {"type": "text", "text": ""}); b["text"] = b.get("text", "") + d.get("text", "")
                            if on_delta:
                                on_delta(d.get("text", ""))
                    elif et == "message_delta":
                        d = ev.get("delta") or {}
                        if d.get("stop_reason"): msg["stop_reason"] = d["stop_reason"]
                        if d.get("stop_details"): msg["stop_details"] = d["stop_details"]
                        msg["usage"].update({k: v for k, v in (ev.get("usage") or {}).items() if v is not None})
                    elif et == "error":
                        err = ev.get("error") or {}
                        raise ProviderError(f"stream error: {err.get('type')}: {str(err.get('message'))[:160]}", retryable=err.get("type") in ("overloaded_error", "api_error"))
                msg["content"] = [blocks[i] for i in sorted(blocks)]
                return msg
        except httpx.HTTPError as e:
            raise ProviderError(f"network error: {e.__class__.__name__}", retryable=True) from e

    def _raise_status(self, r: httpx.Response) -> None:
        if r.status_code in (401, 403):
            raise ProviderError(f"unauthorized (HTTP {r.status_code})", retryable=False)
        if r.status_code == 404:
            raise ProviderError(f"model or endpoint not found (HTTP 404): {r.text[:120]}", retryable=False)
        if r.status_code == 429 or r.status_code >= 500:
            raise ProviderError(f"provider busy/error (HTTP {r.status_code})", retryable=True)
        raise ProviderError(f"bad request (HTTP {r.status_code}): {r.text[:200]}", retryable=False)


class OpenAICompatAdapter(HttpAdapter):
    """OpenAI-compatible clouds (OpenAI, Groq, Cloudflare, OpenRouter, custom)."""
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


class CloudflareAdapter(OpenAICompatAdapter):
    """Workers AI exposes OpenAI chat completions but not ``GET /ai/v1/models``.

    Model discovery therefore uses SEO Brain's curated catalog, while the read-only
    connection probe verifies the account token against Cloudflare's token endpoint.
    This validates the real stored credential without spending inference quota.
    """

    kind = "cloudflare"

    def list_models(self) -> list[str]:
        return list(self.models)

    def _token_verify_url(self) -> str:
        match = re.search(r"^(?P<root>.+?/accounts/(?P<account>[^/]+))/ai(?:/v1)?$", self.base_url)
        if not match:
            raise ProviderError("invalid Cloudflare Workers AI base URL", retryable=False)
        return f"{match.group('root')}/tokens/verify"

    def test_connection(self) -> dict:
        try:
            r = self._get(self._token_verify_url())
        except ProviderError as e:
            return {"ok": False, "provider": self.name, "error": str(e), "retryable": e.retryable}
        if r.status_code in (401, 403):
            return {"ok": False, "provider": self.name, "error": f"unauthorized (HTTP {r.status_code})", "retryable": False}
        if r.status_code != 200:
            return {"ok": False, "provider": self.name, "error": f"HTTP {r.status_code}", "retryable": r.status_code >= 500}
        try:
            valid = r.json().get("success") is not False
        except ValueError:
            valid = False
        if not valid:
            return {"ok": False, "provider": self.name, "error": "Cloudflare token verification failed", "retryable": False}
        return {"ok": True, "provider": self.name, "models": self.list_models()[:50]}


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


ADAPTERS = {"anthropic": AnthropicAdapter, "openai": OpenAICompatAdapter, "openrouter": OpenAICompatAdapter,
            "groq": OpenAICompatAdapter, "cloudflare": CloudflareAdapter, "custom": OpenAICompatAdapter,
            "google": GeminiAdapter, "ollama": OllamaAdapter}


def make_adapter(kind: str, name: str, api_key: str | None, base_url: str | None, models: list[str] | None, prices: dict[str, tuple[float, float]] | None,
                 transport: httpx.BaseTransport | None = None) -> HttpAdapter:
    if kind == "omniroute":                                   # external gateway adapter (lazy import avoids a cycle)
        from .providers.omniroute import OmniRouteAdapter
        return OmniRouteAdapter(name, api_key, base_url, models, prices, transport)
    cls = ADAPTERS.get(kind)
    if not cls:
        raise ProviderError(f"unknown provider kind '{kind}'", retryable=False)
    a = cls(name, api_key, base_url, models, prices, transport)
    if kind == "openrouter" and not base_url:
        a.base_url = "https://openrouter.ai/api/v1"
    return a
