"""FastAPI dependencies: engine, repositories, GraphStore, AI orchestrator, job queue, site resolution, auth."""
from __future__ import annotations

import secrets
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, Path
from sqlalchemy import Engine

from ..ai import AIOrchestrator, AIRouter, EchoProvider, MemoryService, Route, TaskKind
from ..automation import JobQueue, get_job_queue
from ..common.config import env
from ..db.engine import get_engine
from ..db.migrate import migrate
from ..db.repositories import GraphRepository, SiteMemoryRepository, SitesRepository
from ..graph.store import GraphStore, get_graph_store


@lru_cache(maxsize=1)
def engine() -> Engine:
    eng = get_engine()
    migrate(eng)          # bring the DB to the latest schema on first use (idempotent)
    return eng


def sites_repo(eng: Engine = Depends(engine)) -> SitesRepository:
    return SitesRepository(eng)


def graph_repo(eng: Engine = Depends(engine)) -> GraphRepository:
    return GraphRepository(eng)


def memory_repo(eng: Engine = Depends(engine)) -> SiteMemoryRepository:
    return SiteMemoryRepository(eng)


def graph_store(eng: Engine = Depends(engine)) -> GraphStore:
    return get_graph_store(eng)


def job_queue() -> JobQueue:
    return get_job_queue()


_gateway = None


def gateway():
    """Phase 9 gateway (real providers from ai_providers + SecretStore; Echo when nothing is configured). One per process."""
    global _gateway
    from ..ai.gateway import Gateway
    if _gateway is None or _gateway.engine is not engine():
        _gateway = Gateway(engine())
    return _gateway


class GatewayOrchestrator:
    """Drop-in for AIOrchestrator.run(task): routes through TaskRouter + Gateway, prepends site memory context."""

    def __init__(self, gw, memory):
        self.gw, self.memory = gw, memory
        from ..ai.gateway import TaskRouter
        self.router = TaskRouter(gw.engine, gw)

    def run(self, task, learn=None):
        from ..ai.gateway import CallMeta
        from ..ai.types import AITask
        msgs = list(self.memory.context_messages(task.site_id)) if self.memory else []
        t = AITask(**{**task.__dict__, "messages": msgs + list(task.messages)})
        d = self.router.resolve(task.kind.value if hasattr(task.kind, "value") else str(task.kind), task.site_id)
        res = self.gw.run(t, d.chain, CallMeta(site_id=task.site_id, run_id=task.run_id, route_reason=d.reason, prompt_refs={"agent": task.prompt_id or ""}))
        res.memory_used = bool(msgs)
        if res.ok and learn and self.memory is not None:
            self.memory.record_success(task.site_id, learn.get("pattern", ""), learn.get("evidence", ""), source=f"{task.kind.value}:{res.response.provider}/{res.response.model}", run_id=task.run_id)
        return res


@lru_cache(maxsize=1)
def _router() -> AIRouter:
    # Phase 1: only the offline EchoProvider is registered. Phase 9/10 load providers + routes from the DB.
    r = AIRouter(providers={})
    r.register(EchoProvider())
    r.default = [Route("echo", "echo-1")]
    for k in TaskKind:
        r.set_route(k, [Route("echo", "echo-1")])
    return r


def orchestrator(mem: SiteMemoryRepository = Depends(memory_repo), gw=Depends(gateway)):
    """Phase 9: gateway-backed orchestrator (same .run(task) contract as AIOrchestrator). `gw` is injected so
    dependency overrides (tests) never fall through to the live-DB gateway."""
    return GatewayOrchestrator(gw, MemoryService(mem))


def require_site(site_id: str = Path(...), repo: SitesRepository = Depends(sites_repo)):
    s = repo.get(site_id)
    if not s:
        raise HTTPException(404, f"unknown site_id '{site_id}'")
    return s


def require_token(x_api_token: str | None = Header(default=None)) -> None:
    """Local API token. If API_TOKEN is unset, the API is open on loopback (dev default);
    if set, every request must send `X-API-Token`. Setup will generate one for the frontend."""
    expected = env("API_TOKEN")
    if expected and not (x_api_token and secrets.compare_digest(x_api_token, expected)):
        raise HTTPException(401, "missing or invalid X-API-Token")
