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


@lru_cache(maxsize=1)
def _router() -> AIRouter:
    # Phase 1: only the offline EchoProvider is registered. Phase 9/10 load providers + routes from the DB.
    r = AIRouter(providers={})
    r.register(EchoProvider())
    r.default = [Route("echo", "echo-1")]
    for k in TaskKind:
        r.set_route(k, [Route("echo", "echo-1")])
    return r


def orchestrator(mem: SiteMemoryRepository = Depends(memory_repo)) -> AIOrchestrator:
    return AIOrchestrator(_router(), MemoryService(mem))


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
