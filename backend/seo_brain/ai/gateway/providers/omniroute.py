"""OmniRoute adapter — OmniRoute (https://github.com/diegosouzapw/OmniRoute) is an external AI gateway that fronts
Claude / OpenAI / Gemini / … behind one OpenAI-compatible endpoint (default http://127.0.0.1:20128/v1).

SEO Brain keeps its own Gateway (budget, breaker, ledger, validator, routing); OmniRoute is just another provider *behind*
it. Model ids are `provider/model` (e.g. `claude/opus-5`, `openai/gpt-4o`) or `auto`, `auto/fast`, `auto/cheap`, `auto/coding`
(OmniRoute's own routing). The serving provider/strategy is read from the `X-OmniRoute-Decision` header when present.

Wire format: POST {base}/chat/completions (stream or not), GET {base}/models. Auth: `Authorization: Bearer <key>` — optional
(fresh installs are keyless); the key comes from the SecretStore via the Gateway, never from code or env.
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterator

import httpx

from ...providers.base import ProviderError
from ...types import AIRequest, AIResponse
from ..adapters import OpenAICompatAdapter, _json_instruction, _strip_fences

DEFAULT_BASE_URL = "http://127.0.0.1:20128/v1"
AUTO_MODELS = ("auto", "auto/fast", "auto/cheap", "auto/coding")


def _decision(headers: httpx.Headers) -> dict[str, Any] | None:
    """Collect OmniRoute routing metadata (X-OmniRoute-* headers) without guessing their exact schema."""
    out = {k.lower().replace("x-omniroute-", ""): v for k, v in headers.items() if k.lower().startswith("x-omniroute-")}
    return out or None


class OmniRouteAdapter(OpenAICompatAdapter):
    kind = "omniroute"
    is_gateway = True

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.last_decision: dict[str, Any] | None = None
        self.last_health: dict[str, Any] | None = None

    def default_base_url(self) -> str:
        return DEFAULT_BASE_URL

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "X-Title": "SEO Brain"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    # ------------------------------------------------------------------ contract
    def capabilities(self) -> dict[str, Any]:
        return {"gateway": True, "streaming": True, "json_mode": True, "dynamic_models": True, "auto_routing": True, "auto_models": list(AUTO_MODELS),
                "fallback": "omniroute (circuit breaker / cooldown / model lockout) + SEO Brain chain", "decision_header": "X-OmniRoute-Decision",
                "auth": "bearer (optional)", "wire": "openai-compatible", "endpoints": ["/chat/completions", "/models"], "upstreams": ["claude", "openai", "gemini", "…"]}

    def test(self) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            models = self.list_models()
        except ProviderError as e:
            self.last_health = {"ok": False, "error": str(e), "retryable": e.retryable, "latency_ms": int((time.perf_counter() - t0) * 1000), "checked_at": time.time()}
            return {"ok": False, "provider": self.name, "error": str(e), "retryable": e.retryable}
        self.last_health = {"ok": True, "models": len(models), "latency_ms": int((time.perf_counter() - t0) * 1000), "checked_at": time.time()}
        return {"ok": True, "provider": self.name, "models": models[:200], "gateway": True, "endpoint": self.base_url}

    test_connection = test

    def list_models(self) -> list[str]:
        r = self._get(f"{self.base_url}/models")
        if r.status_code in (401, 403):
            raise ProviderError("unauthorized (OmniRoute API key required — Dashboard → Endpoints)", retryable=False)
        if r.status_code != 200:
            raise ProviderError(f"HTTP {r.status_code}", retryable=True)
        try:
            data = r.json()
        except ValueError as e:
            raise ProviderError("invalid JSON from OmniRoute", retryable=True) from e
        ids: list[str] = []
        rows = data.get("data") if isinstance(data, dict) else data
        if isinstance(rows, dict):                       # provider-grouped variant: {"claude": [...], "openai": [...]}
            for prov, lst in rows.items():
                for m in lst or []:
                    mid = m.get("id") if isinstance(m, dict) else str(m)
                    if mid: ids.append(mid if "/" in mid else f"{prov}/{mid}")
        else:
            for m in rows or []:
                mid = m.get("id") if isinstance(m, dict) else str(m)
                if mid: ids.append(mid)
        seen: set[str] = set(); out = []
        for m in list(AUTO_MODELS) + ids:                # auto-routing entries always selectable
            if m not in seen: seen.add(m); out.append(m)
        return out

    def _body(self, request: AIRequest, stream: bool) -> dict[str, Any]:
        msgs = [{"role": m.role, "content": m.content} for m in request.messages]
        if request.json_schema and msgs:
            msgs[-1] = {"role": msgs[-1]["role"], "content": msgs[-1]["content"] + _json_instruction(request.json_schema)}
        body: dict[str, Any] = {"model": request.model, "messages": msgs, "max_tokens": request.max_tokens}
        if request.temperature is not None and not any(x in request.model.lower() for x in ("opus-5", "sonnet-5", "opus-4-7", "opus-4-8", "fable")):
            body["temperature"] = request.temperature
        if request.json_schema:
            body["response_format"] = {"type": "json_object"}
        if stream:
            body["stream"] = True; body["stream_options"] = {"include_usage": True}
        return body

    def complete(self, request: AIRequest) -> AIResponse:
        """OmniRoute may answer with SSE even for non-stream requests (some `auto/*` combos), so completion always goes through
        the stream reader, which accepts both a JSON body and an event stream."""
        final: AIResponse | None = None
        for item in self.stream(request):
            if isinstance(item, AIResponse):
                final = item
        if final is None:
            raise ProviderError("empty response from OmniRoute", retryable=True)
        return final

    def stream(self, request: AIRequest) -> Iterator[str | AIResponse]:
        """Yield text deltas as they arrive; the final item is the assembled AIResponse (usage from the last chunk when sent)."""
        t0 = time.perf_counter()
        text_parts: list[str] = []; usage: dict[str, Any] = {}; model = request.model; finish = None; rid = None; headers = None
        try:
            with self._client.stream("POST", f"{self.base_url}/chat/completions", json=self._body(request, stream=True), headers=self._headers()) as r:
                if r.status_code >= 400:
                    r.read(); self._raise_status(r)
                headers = r.headers
                if "text/event-stream" not in r.headers.get("content-type", ""):
                    r.read()
                    try:
                        data = r.json()
                    except ValueError as e:
                        raise ProviderError(f"invalid JSON from OmniRoute: {r.text[:120]!r}", retryable=True) from e
                    if isinstance(data, dict) and data.get("error"):
                        raise ProviderError(f"OmniRoute error: {str(data['error'])[:160]}", retryable=True)
                    resp = self._to_response(request, data, r.headers, t0)
                    yield resp.text; yield resp; return
                for line in r.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        ev = json.loads(payload)
                    except ValueError:
                        continue
                    if ev.get("error"):
                        raise ProviderError(f"stream error: {str(ev['error'])[:160]}", retryable=True)
                    rid = ev.get("id", rid); model = ev.get("model") or model
                    if ev.get("usage"): usage = ev["usage"]
                    for ch in ev.get("choices") or []:
                        d = (ch.get("delta") or {}).get("content")
                        if d:
                            text_parts.append(d); yield d
                        if ch.get("finish_reason"): finish = ch["finish_reason"]
        except httpx.HTTPError as e:
            raise ProviderError(f"network error: {e.__class__.__name__}", retryable=True) from e
        text = "".join(text_parts)
        inp, out = int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0)
        self.last_decision = _decision(headers) if headers is not None else None
        yield AIResponse(text=_strip_fences(text) if request.json_schema else text, model=model, provider=self.name, input_tokens=inp, output_tokens=out,
                         cost_usd=self._cost(request.model, inp, out), latency_ms=int((time.perf_counter() - t0) * 1000),
                         raw={"id": rid, "finish_reason": finish, "streamed": True, "gateway": "omniroute", "decision": self.last_decision, "served_model": model})

    def _to_response(self, request: AIRequest, data: dict, headers: httpx.Headers, t0: float) -> AIResponse:
        choice = (data.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content")) or ""
        u = data.get("usage") or {}
        inp, out = int(u.get("prompt_tokens", 0) or 0), int(u.get("completion_tokens", 0) or 0)
        self.last_decision = _decision(headers)
        cost = u.get("cost") if isinstance(u.get("cost"), (int, float)) else self._cost(request.model, inp, out)
        return AIResponse(text=_strip_fences(text) if request.json_schema else text, model=data.get("model") or request.model, provider=self.name, input_tokens=inp, output_tokens=out,
                          cost_usd=float(cost or 0.0), latency_ms=int((time.perf_counter() - t0) * 1000),
                          raw={"id": data.get("id"), "finish_reason": choice.get("finish_reason"), "gateway": "omniroute", "decision": self.last_decision, "served_model": data.get("model")})

    def _raise_status(self, r: httpx.Response) -> None:
        self.last_decision = _decision(r.headers) or self.last_decision
        why = r.headers.get("x-omniroute-combo-terminal-reason") or r.headers.get("x-omniroute-recovery-next-step")
        if why:
            # OmniRoute explains combo failures in headers (attempted/excluded upstreams, recovery hint) — keep it in the error, never the key
            excl = r.headers.get("x-omniroute-combo-excluded")
            raise ProviderError(f"OmniRoute upstream failed (HTTP {r.status_code}): {why[:160]}" + (f" · excluded: {excl[:100]}" if excl else ""), retryable=r.status_code >= 500 or r.status_code in (400, 429))
        if r.status_code in (401, 403):
            raise ProviderError(f"unauthorized (HTTP {r.status_code}) — OmniRoute API key missing/invalid", retryable=False)
        if r.status_code == 404:
            raise ProviderError(f"model or endpoint not found (HTTP 404): {r.text[:120]}", retryable=False)
        if r.status_code == 429 or r.status_code >= 500:
            raise ProviderError(f"OmniRoute busy/error (HTTP {r.status_code})", retryable=True)
        if r.status_code >= 400:
            raise ProviderError(f"bad request (HTTP {r.status_code}): {r.text[:200]}", retryable=False)
