"""AI Gateway — the only place business logic talks to models.

run(task, chain, meta) → OrchestrationResult (same shape as the phase-1 orchestrator so briefs/reviews keep working):
  for each (provider, model) in chain: budget check → circuit breaker → adapter.complete → validator → ledger (ai_calls) → health
Fallback continues on retryable ProviderError/ValidationError; every attempt is recorded. Budget: warn 80 % · soft 100 % (still runs,
flagged) · hard stop 120 % (raises BudgetExceeded). Keys come from the SecretStore; adapters are cached per provider config.
"""
from __future__ import annotations

import logging
import statistics
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx
from sqlalchemy import Engine, and_, func, select, text

from ...db.repositories.base import dumps, loads, utcnow
from ...db.tables import ai_calls, ai_models, ai_provider_health, ai_providers
from ..config import ProviderConfigRepository
from ..orchestrator import Attempt, OrchestrationResult
from ..providers.base import EchoProvider, ProviderError
from ..types import AIRequest, AITask
from ..validator import ChainValidator, JsonKeysValidator, NonEmptyValidator, ValidationError
from .adapters import HttpAdapter, make_adapter
from .catalog import cost_usd, default_models_for, estimate_tokens, guess_tier

log = logging.getLogger("ai.gateway")

BUDGET_DEFAULT_USD = 20.0
BUDGET_WARN, BUDGET_SOFT, BUDGET_HARD = 0.8, 1.0, 1.2
BREAKER_FAILS, BREAKER_COOLDOWN_S = 3, 300


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class RouteStep:
    provider: str
    model: str
    reason: str = ""


@dataclass
class CallMeta:
    site_id: str | None = None
    run_id: str | None = None
    content_id: int | None = None
    agent: str | None = None
    prompt_refs: dict[str, str] = field(default_factory=dict)
    memory_snapshot_id: int | None = None
    route_reason: str = ""


class Gateway:
    def __init__(self, engine: Engine, transport_factory: Callable[[str], httpx.BaseTransport | None] | None = None):
        self.engine = engine
        self.cfg = ProviderConfigRepository(engine)
        self.validator = ChainValidator(NonEmptyValidator(), JsonKeysValidator())
        self._adapters: dict[str, Any] = {}
        self._transport_factory = transport_factory
        self._lock = threading.Lock()

    # ------------------------------------------------------------ providers / models
    def providers(self) -> dict[str, dict[str, Any]]:
        out = {}
        for p in self.cfg.list():
            if p.enabled:
                out[p.name] = p.to_dict() | {"_id": p.id, "_kind": p.kind}
        return out

    def adapter(self, provider_name: str):
        with self._lock:
            if provider_name in self._adapters:
                return self._adapters[provider_name]
        if provider_name == "echo":
            a = EchoProvider()
        else:
            p = self.cfg.get_by_name(provider_name)
            if not p or not p.enabled:
                raise ProviderError(f"provider '{provider_name}' not configured/enabled", retryable=False)
            models = self.models(p.id)
            prices = {m["model_id"]: (m["price_in_per_m"], m["price_out_per_m"]) for m in models}
            transport = self._transport_factory(p.kind) if self._transport_factory else None
            a = make_adapter(p.kind, p.name, self.cfg.api_key(p), p.base_url, [m["model_id"] for m in models] or (p.models or []), prices, transport)
        with self._lock:
            self._adapters[provider_name] = a
        return a

    def invalidate(self, provider_name: str | None = None) -> None:
        with self._lock:
            if provider_name:
                self._adapters.pop(provider_name, None)
            else:
                self._adapters.clear()

    def models(self, provider_id: int | None = None, enabled_only: bool = False) -> list[dict[str, Any]]:
        conds = []
        if provider_id is not None: conds.append(ai_models.c.provider_id == provider_id)
        if enabled_only: conds.append(ai_models.c.enabled == 1)
        with self.engine.connect() as cx:
            rows = cx.execute(select(ai_models).where(and_(*conds)) if conds else select(ai_models)).all()
        out = []
        for r in rows:
            d = dict(r._mapping); d["tags"] = loads(d["tags"], []); d["enabled"] = bool(d["enabled"]); out.append(d)
        return out

    def seed_catalog(self, provider_id: int, kind: str, discovered: list[str] | None = None) -> int:
        """Insert catalog defaults for the provider kind (idempotent) + discovered models with guessed tiers; keeps user edits."""
        n = 0
        with self.engine.begin() as cx:
            existing = {r[0] for r in cx.execute(select(ai_models.c.model_id).where(ai_models.c.provider_id == provider_id)).all()}
            for m in default_models_for(kind):
                if m["model_id"] in existing:
                    continue
                cx.execute(ai_models.insert().values(provider_id=provider_id, model_id=m["model_id"], display=m.get("display"), tier=m["tier"], tags=dumps(m["tags"]), context_tokens=m.get("context_tokens"),
                                                     price_in_per_m=m["price_in_per_m"], price_out_per_m=m["price_out_per_m"], enabled=1, source="catalog", updated_at=utcnow())); n += 1; existing.add(m["model_id"])
            for mid in discovered or []:
                if mid in existing:
                    continue
                tier, tags = guess_tier(mid)
                cx.execute(ai_models.insert().values(provider_id=provider_id, model_id=mid, display=mid, tier=tier, tags=dumps(tags + (["local"] if kind == "ollama" else [])), price_in_per_m=0, price_out_per_m=0,
                                                     enabled=1, source="discovered", updated_at=utcnow())); n += 1; existing.add(mid)
        self.invalidate()
        return n

    def update_model(self, mid: int, **fields) -> dict | None:
        allowed = {k: v for k, v in fields.items() if k in ("display", "tier", "tags", "context_tokens", "price_in_per_m", "price_out_per_m", "enabled") and v is not None}
        if "tags" in allowed: allowed["tags"] = dumps(allowed["tags"])
        if "enabled" in allowed: allowed["enabled"] = int(bool(allowed["enabled"]))
        if allowed:
            allowed["updated_at"] = utcnow(); allowed["source"] = "user"
            with self.engine.begin() as cx:
                cx.execute(ai_models.update().where(ai_models.c.id == mid).values(**allowed))
        self.invalidate()
        with self.engine.connect() as cx:
            r = cx.execute(select(ai_models).where(ai_models.c.id == mid)).first()
        if not r:
            return None
        d = dict(r._mapping); d["tags"] = loads(d["tags"], []); d["enabled"] = bool(d["enabled"]); return d

    # ------------------------------------------------------------ budget
    def budget(self, site_id: str | None) -> dict[str, Any]:
        limit = BUDGET_DEFAULT_USD
        if site_id:
            with self.engine.connect() as cx:
                r = cx.execute(text("SELECT value FROM site_settings WHERE site_id=:s AND key='ai'"), {"s": site_id}).first()
            if r:
                limit = float(loads(r[0], {}).get("budget_usd_month", limit))
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        with self.engine.connect() as cx:
            spent = cx.execute(select(func.coalesce(func.sum(ai_calls.c.cost_usd), 0.0)).where(and_(ai_calls.c.site_id == site_id, ai_calls.c.created_at >= f"{month}-01"))).scalar() or 0.0
        ratio = spent / limit if limit else 0.0
        state = "hard_stop" if ratio >= BUDGET_HARD else ("soft_limit" if ratio >= BUDGET_SOFT else ("warning" if ratio >= BUDGET_WARN else "ok"))
        return {"month": month, "limit_usd": limit, "spent_usd": round(float(spent), 4), "ratio": round(ratio, 3), "state": state,
                "thresholds": {"warning": BUDGET_WARN, "soft_limit": BUDGET_SOFT, "hard_stop": BUDGET_HARD}}

    # ------------------------------------------------------------ health / breaker
    def health(self) -> list[dict[str, Any]]:
        with self.engine.connect() as cx:
            return [dict(r._mapping) for r in cx.execute(select(ai_provider_health)).all()]

    def _breaker_open(self, provider: str) -> bool:
        with self.engine.connect() as cx:
            r = cx.execute(select(ai_provider_health.c.breaker_open_until).where(ai_provider_health.c.provider == provider)).first()
        return bool(r and r[0] and r[0] > utcnow())

    def _record_health(self, provider: str, ok: bool, latency_ms: int, error: str | None) -> None:
        with self.engine.begin() as cx:
            r = cx.execute(select(ai_provider_health).where(ai_provider_health.c.provider == provider)).first()
            if not r:
                cx.execute(ai_provider_health.insert().values(provider=provider, calls=1, failures=0 if ok else 1, consecutive_failures=0 if ok else 1, p50_ms=latency_ms if ok else None,
                                                             breaker_open_until=None, last_error=error, updated_at=utcnow()))
                return
            m = dict(r._mapping)
            consec = 0 if ok else m["consecutive_failures"] + 1
            until = m["breaker_open_until"]
            if consec >= BREAKER_FAILS:
                until = (datetime.now(timezone.utc) + timedelta(seconds=BREAKER_COOLDOWN_S)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            elif ok:
                until = None
            lat = cx.execute(select(ai_calls.c.latency_ms).where(and_(ai_calls.c.provider == provider, ai_calls.c.ok == 1)).order_by(ai_calls.c.id.desc()).limit(50)).all()
            p50 = int(statistics.median([x[0] for x in lat])) if lat else (latency_ms if ok else m["p50_ms"])
            cx.execute(ai_provider_health.update().where(ai_provider_health.c.provider == provider).values(calls=m["calls"] + 1, failures=m["failures"] + (0 if ok else 1), consecutive_failures=consec,
                                                                                                          p50_ms=p50, breaker_open_until=until, last_error=error if not ok else m["last_error"], updated_at=utcnow()))

    # ------------------------------------------------------------ estimate
    def estimate(self, task: AITask, chain: list[RouteStep]) -> dict[str, Any]:
        step = chain[0] if chain else RouteStep("echo", "echo-1")
        inp = sum(estimate_tokens(m.content) for m in task.messages)
        out = min(task.max_tokens, max(200, inp // 2))
        price = (0.0, 0.0)
        for m in self.models():
            if m["model_id"] == step.model:
                price = (m["price_in_per_m"], m["price_out_per_m"]); break
        exact = False
        if step.provider != "echo":
            # adapters may know better (Anthropic: /v1/messages/count_tokens); never fail the estimate on network problems
            try:
                a = self.adapter(step.provider)
                r = a.estimate(AIRequest(model=step.model, messages=task.messages, max_tokens=task.max_tokens, temperature=task.temperature, json_schema=task.json_schema))
                if r.get("exact"):
                    inp, out, exact = int(r["input_tokens"]), int(r["output_tokens"]), True
            except Exception:  # noqa: BLE001
                pass
        return {"provider": step.provider, "model": step.model, "input_tokens": inp, "output_tokens": out, "cost_usd": cost_usd(inp, out, *price), "exact": exact}

    # ------------------------------------------------------------ run
    def run(self, task: AITask, chain: list[RouteStep], meta: CallMeta | None = None) -> OrchestrationResult:
        meta = meta or CallMeta(site_id=task.site_id, run_id=task.run_id)
        result = OrchestrationResult(response=None)
        b = self.budget(meta.site_id)
        if b["state"] == "hard_stop":
            raise BudgetExceeded(f"بودجه ماهانه AI سایت تمام شده است ({b['spent_usd']:.2f} از {b['limit_usd']:.2f} دلار؛ حد سخت ۱۲۰٪)")
        last_err = None
        for step in chain or [RouteStep("echo", "echo-1", "no chain")]:
            if step.provider != "echo" and self._breaker_open(step.provider):
                result.attempts.append(Attempt(step.provider, step.model, False, "circuit breaker open", 0)); continue
            try:
                adapter = self.adapter(step.provider)
            except ProviderError as e:
                result.attempts.append(Attempt(step.provider, step.model, False, str(e), 0)); last_err = str(e); continue
            req = AIRequest(model=step.model, messages=task.messages, max_tokens=task.max_tokens, temperature=task.temperature, json_schema=task.json_schema)
            t0 = time.perf_counter()
            for attempt_no in range(2):     # one retry on retryable errors
                try:
                    resp = adapter.complete(req)
                    resp = self.validator.validate(task, resp)
                    ms = int((time.perf_counter() - t0) * 1000)
                    result.attempts.append(Attempt(step.provider, step.model, True, None, ms))
                    result.response = resp
                    from ..router import Route
                    result.route_used = Route(step.provider, step.model)
                    self._ledger(task, meta, resp, result.attempts, ok=True)
                    if step.provider != "echo": self._record_health(step.provider, True, resp.latency_ms, None)
                    return result
                except ValidationError as e:
                    ms = int((time.perf_counter() - t0) * 1000); last_err = f"ValidationError: {e}"
                    result.attempts.append(Attempt(step.provider, step.model, False, last_err, ms))
                    if attempt_no == 0:
                        time.sleep(0.1)
                        continue
                    break
                except ProviderError as e:
                    ms = int((time.perf_counter() - t0) * 1000); last_err = f"ProviderError: {e}"
                    result.attempts.append(Attempt(step.provider, step.model, False, last_err, ms))
                    if step.provider != "echo": self._record_health(step.provider, False, ms, str(e))
                    if not e.retryable or attempt_no == 1:
                        break
                    time.sleep(0.2)
        self._ledger(task, meta, None, result.attempts, ok=False, error=last_err)
        return result

    def _ledger(self, task: AITask, meta: CallMeta, resp, attempts: list[Attempt], ok: bool, error: str | None = None) -> None:
        with self.engine.begin() as cx:
            cx.execute(ai_calls.insert().values(site_id=meta.site_id, run_id=meta.run_id, content_id=meta.content_id, agent=meta.agent, task_kind=task.kind.value if hasattr(task.kind, "value") else str(task.kind),
                                                provider=resp.provider if resp else (attempts[-1].provider if attempts else "?"), model=resp.model if resp else (attempts[-1].model if attempts else "?"),
                                                prompt_refs=dumps(meta.prompt_refs), memory_snapshot_id=meta.memory_snapshot_id, input_tokens=resp.input_tokens if resp else 0, output_tokens=resp.output_tokens if resp else 0,
                                                cost_usd=(resp.cost_usd or 0.0) if resp else 0.0, latency_ms=resp.latency_ms if resp else 0, ok=int(ok), error=error, attempts=dumps([a.__dict__ for a in attempts]),
                                                route_reason=meta.route_reason, created_at=utcnow()))

    # ------------------------------------------------------------ usage
    def usage(self, site_id: str | None, date_from: str | None = None, date_to: str | None = None, group_by: str = "model") -> dict[str, Any]:
        col = {"model": ai_calls.c.model, "task": ai_calls.c.task_kind, "provider": ai_calls.c.provider, "agent": ai_calls.c.agent}.get(group_by, ai_calls.c.model)
        conds = []
        if site_id: conds.append(ai_calls.c.site_id == site_id)
        if date_from: conds.append(ai_calls.c.created_at >= date_from)
        if date_to: conds.append(ai_calls.c.created_at <= date_to + "T23:59:59Z")
        with self.engine.connect() as cx:
            rows = cx.execute(select(col, func.count(), func.sum(ai_calls.c.input_tokens), func.sum(ai_calls.c.output_tokens), func.sum(ai_calls.c.cost_usd), func.avg(ai_calls.c.latency_ms), func.sum(ai_calls.c.ok))
                              .where(and_(*conds) if conds else True).group_by(col).order_by(func.sum(ai_calls.c.cost_usd).desc())).all()
            days = cx.execute(select(func.substr(ai_calls.c.created_at, 1, 10), func.sum(ai_calls.c.cost_usd), func.count()).where(and_(*conds) if conds else True).group_by(func.substr(ai_calls.c.created_at, 1, 10)).order_by(func.substr(ai_calls.c.created_at, 1, 10))).all()
        return {"group_by": group_by, "rows": [{"key": r[0], "calls": r[1], "input_tokens": int(r[2] or 0), "output_tokens": int(r[3] or 0), "cost_usd": round(float(r[4] or 0), 4), "avg_latency_ms": int(r[5] or 0), "ok": int(r[6] or 0)} for r in rows],
                "by_day": [{"date": d[0], "cost_usd": round(float(d[1] or 0), 4), "calls": d[2]} for d in days], "budget": self.budget(site_id)}
