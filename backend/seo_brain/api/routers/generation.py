"""Phase 9 — generation runs (site-scoped): estimate, start (job), status, SSE stream, accept (manual mode), cancel, single-agent runs, feedback."""
from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from ...ai.gateway import BudgetExceeded, Gateway
from ...ai.memory_pack import MemoryPackBuilder
from ...automation.events import get_event_bus
from ...automation.queue import Job, JobQueue
from ...brain.generation import AGENT_FA, AGENTS, GenerationPipeline, STEP_FA
from ...brain.generation.agents import PLACEHOLDERS, AgentRunner
from ...brain.generation.learning import FEEDBACK_TAGS, AILearning
from ...db.repositories.sites import SitesRepository
from ..deps import engine, gateway, job_queue, require_site, sites_repo
from ..errors import ApiError

router = APIRouter(prefix="/sites/{site_id}", tags=["generation"], dependencies=[Depends(require_site)])


class GenerateBody(BaseModel):
    mode: Literal["manual", "assisted"] | None = None       # default: site mode (autopilot → assisted, never autonomous)
    models: dict[str, dict[str, str]] | None = None          # {agent: {provider, model}}
    prompt_versions: dict[str, int] | None = None            # {agent: prompt_version_id}
    created_by: str | None = None


class FeedbackBody(BaseModel):
    rating: int = Field(ge=1, le=5)
    tags: list[str] = []
    draft_id: int | None = None
    run_id: str | None = None
    notes: str | None = None


def pipe(g: Gateway = Depends(gateway)) -> GenerationPipeline:
    return GenerationPipeline(g.engine, g, get_event_bus())


def _effective_mode(site_mode: str, requested: str | None) -> str:
    if requested:
        return requested
    return "manual" if site_mode == "manual" else "assisted"      # autopilot is reserved → behaves as assisted (no publishing anywhere)


@router.get("/generation/meta")
def meta() -> dict:
    return {"agents": [{"agent": a, "fa": AGENT_FA[a]} for a in AGENTS], "steps": [{"step": k, "fa": v} for k, v in STEP_FA.items()], "modes": ["manual", "assisted"], "reserved_modes": ["autopilot"], "feedback_tags": list(FEEDBACK_TAGS)}


@router.get("/generation/memory-preview")
def memory_preview(site_id: str, g: Gateway = Depends(gateway)) -> dict:
    return MemoryPackBuilder(g.engine).snapshot(site_id)


@router.post("/content/{cid}/generate/estimate")
def estimate(site_id: str, cid: int, body: GenerateBody | None = None, p: GenerationPipeline = Depends(pipe)) -> dict:
    body = body or GenerateBody()
    try:
        return p.estimate(site_id, cid, body.models, body.prompt_versions)
    except KeyError:
        raise HTTPException(404, "content not found")


@router.post("/content/{cid}/generate", status_code=202)
def generate(site_id: str, cid: int, body: GenerateBody | None = None, p: GenerationPipeline = Depends(pipe), q: JobQueue = Depends(job_queue), repo: SitesRepository = Depends(sites_repo)) -> dict:
    """Start a section-by-section generation run as a job. Returns the run (poll GET /generation/runs/{run_id} or stream)."""
    body = body or GenerateBody()
    site = repo.get(site_id)
    mode = _effective_mode(site.mode if site else "manual", body.mode)
    b = p.gw.budget(site_id)
    if b["state"] == "hard_stop":
        raise ApiError(409, f"بودجه ماهانه AI تمام شده ({b['spent_usd']:.2f}$ از {b['limit_usd']:.2f}$؛ حد سخت ۱۲۰٪) — بودجه را در تنظیمات افزایش دهید", code="budget_exceeded", details=b)
    try:
        run = p.create_run(site_id, cid, mode, body.models, body.prompt_versions, body.created_by)
    except KeyError:
        raise HTTPException(404, "content not found")
    except ValueError as e:
        raise ApiError(422, str(e), code="validation_error")
    job = q.enqueue(Job(type="generation_run", payload={"run_id": run["run_id"]}, site_id=site_id))
    return {**p.get_run(run["run_id"]), "job_run_id": job.run_id, "budget": b}


@router.get("/generation/runs")
def runs(site_id: str, content_id: int | None = None, limit: int = Query(50, ge=1, le=200), p: GenerationPipeline = Depends(pipe)) -> list[dict]:
    return p.list_runs(site_id, content_id, limit)


@router.get("/generation/runs/{run_id}")
def run(site_id: str, run_id: str, p: GenerationPipeline = Depends(pipe)) -> dict:
    r = p.get_run(run_id)
    if not r or r["site_id"] != site_id:
        raise HTTPException(404, "run not found")
    return r


@router.get("/generation/runs/{run_id}/stream")
def stream(site_id: str, run_id: str, p: GenerationPipeline = Depends(pipe)):
    """SSE progress: step_start / step_done / plan / done / failed / cancelled (+ keepalive). Backlog replayed for late subscribers."""
    r = p.get_run(run_id)
    if not r or r["site_id"] != site_id:
        raise HTTPException(404, "run not found")
    bus = get_event_bus()

    def gen():
        if r["status"] in ("succeeded", "failed", "cancelled"):
            for e in bus.history(f"gen:{run_id}"):
                yield f"event: {e.get('type','message')}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n"
            yield f"event: {r['status'] if r['status'] != 'succeeded' else 'done'}\ndata: {json.dumps({'type': 'done' if r['status'] == 'succeeded' else r['status'], 'run_id': run_id, 'replay': True}, ensure_ascii=False)}\n\n"
            return
        for e in bus.subscribe(f"gen:{run_id}", timeout=15.0):
            yield f"event: {e.get('type','message')}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/generation/runs/{run_id}/accept")
def accept(site_id: str, run_id: str, p: GenerationPipeline = Depends(pipe)) -> dict:
    """Manual mode: human promotes the assembled article to a draft version (+ score/review). Never automatic."""
    r = p.get_run(run_id)
    if not r or r["site_id"] != site_id:
        raise HTTPException(404, "run not found")
    try:
        return p.accept(run_id)
    except ValueError as e:
        raise ApiError(409, str(e), code="conflict")


@router.post("/generation/runs/{run_id}/cancel")
def cancel(site_id: str, run_id: str, p: GenerationPipeline = Depends(pipe)) -> dict:
    r = p.cancel(run_id)
    if not r or r["site_id"] != site_id:
        raise HTTPException(404, "run not found")
    return r


@router.post("/content/{cid}/agents/{agent}/run")
def run_agent(site_id: str, cid: int, agent: str, body: GenerateBody | None = None, p: GenerationPipeline = Depends(pipe)) -> dict:
    """Run a single agent (research/outline/seo/linking/reviewer) as a proposal — no draft is created."""
    if agent not in ("research", "outline", "seo", "linking", "reviewer"):
        raise HTTPException(404, "agent not available for single run")
    body = body or GenerateBody()
    ctx = p.context(site_id, cid)
    if not ctx["item"]:
        raise HTTPException(404, "content not found")
    snap = p.mp.snapshot(site_id)
    ar = AgentRunner(p.gw, p.router, p.prompts, snap["rendered"], snap["id"], site_id, f"single-{agent}", cid, body.models, body.prompt_versions)
    variables = {"research": p._research_vars(ctx), "outline": {"keyword": ctx["keyword"], "intent": ctx["intent"], "brief": json.dumps(ctx["brief"] or {}, ensure_ascii=False)[:4000], "research": "{}", "_brief": ctx["brief"]},
                 "seo": {"keyword": ctx["keyword"], "intent": ctx["intent"], "cluster_keywords": ", ".join(ctx["siblings"]) or "—", "outline_summary": "", "intro": ""},
                 "linking": {"markdown": "", "link_candidates": json.dumps(ctx["links"], ensure_ascii=False), "max_links": 5, "_links_list": ctx["links"]},
                 "reviewer": {"brief": json.dumps(ctx["brief"] or {}, ensure_ascii=False)[:3000], "rule_findings": "[]", "markdown": ""}}[agent]
    try:
        res = ar.run(agent, variables, PLACEHOLDERS[agent])
    except BudgetExceeded as e:
        raise ApiError(409, str(e), code="budget_exceeded")
    return {"agent": agent, "ok": res.ok, "payload": res.payload, "provenance": res.provenance, "placeholder": res.placeholder, "error": res.error, "memory_snapshot_id": snap["id"]}


@router.post("/content/{cid}/feedback", status_code=201)
def feedback(site_id: str, cid: int, body: FeedbackBody, g: Gateway = Depends(gateway)) -> dict:
    """Human rating 1–5 + tags on a draft/run (learning signal; never changes routing)."""
    try:
        return AILearning(g.engine).add_feedback(site_id, body.rating, body.tags, cid, body.draft_id, body.run_id, body.notes)
    except ValueError as e:
        raise ApiError(422, str(e), code="validation_error")


@router.get("/content/{cid}/feedback")
def list_feedback(site_id: str, cid: int, g: Gateway = Depends(gateway)) -> list[dict]:
    return AILearning(g.engine).feedback(site_id, cid)
