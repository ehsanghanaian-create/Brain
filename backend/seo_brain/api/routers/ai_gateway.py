"""Phase 9 — AI gateway endpoints: models catalog, estimate, health, usage/budget, prompt library, insights, routing preview."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from ...ai.config import ProviderConfigRepository
from ...ai.gateway import TASK_FA, TASK_KINDS_V2, Gateway, TaskRouter
from ...ai.gateway.routing import POLICY
from ...ai.memory_pack import MemoryPackBuilder
from ...ai.prompts import PromptError, PromptLibrary, render
from ...ai.types import AIMessage, AITask, TaskKind
from ...brain.generation.learning import FEEDBACK_TAGS, TAG_FA, AILearning
from ...db.repositories.base import utcnow
from ..deps import engine, gateway
from ..errors import ApiError

router = APIRouter(prefix="/ai", tags=["ai"])


class ModelUpdate(BaseModel):
    display: str | None = None
    tier: Literal["fast", "balanced", "quality", "reasoning"] | None = None
    tags: list[str] | None = None
    context_tokens: int | None = None
    price_in_per_m: float | None = None
    price_out_per_m: float | None = None
    enabled: bool | None = None


class EstimateBody(BaseModel):
    task_kind: str = "generic"
    site_id: str | None = None
    text: str = Field(min_length=1)
    max_tokens: int = 1500
    provider: str | None = None
    model: str | None = None


class PromptCreate(BaseModel):
    key: str
    scope: Literal["system", "site", "agent", "task"]
    title: str
    template: str
    site_id: str | None = None
    description: str | None = None
    model_hints: dict[str, Any] | None = None


class VersionCreate(BaseModel):
    template: str
    changelog: str | None = None
    model_hints: dict[str, Any] | None = None
    activate: bool = False


class VersionPatch(BaseModel):
    activate: bool | None = None
    approval: Literal["draft", "approved", "retired"] | None = None
    approved_by: str | None = None
    changelog: str | None = None


class PromptTestBody(BaseModel):
    site_id: str
    variables: dict[str, Any] = {}
    provider: str | None = None
    model: str | None = None
    task_kind: str = "generic"


class PromptTestRating(BaseModel):
    human_rating: int = Field(ge=1, le=5)
    notes: str | None = None


class InsightStatus(BaseModel):
    status: Literal["new", "accepted", "dismissed"]


def gw(g: Gateway = Depends(gateway)) -> Gateway:
    return g


@router.get("/task-kinds")
def task_kinds() -> list[dict]:
    return [{"kind": k, "fa": TASK_FA.get(k, k), "policy": POLICY.get(k, POLICY["generic"])} for k in TASK_KINDS_V2]


@router.get("/models")
def models(provider_id: int | None = None, g: Gateway = Depends(gw)) -> list[dict]:
    provs = {p.id: p for p in ProviderConfigRepository(g.engine).list()}
    return [{**m, "provider": provs[m["provider_id"]].name if m["provider_id"] in provs else None, "kind": provs[m["provider_id"]].kind if m["provider_id"] in provs else None} for m in g.models(provider_id)]


@router.post("/models/sync")
def sync_models(provider_id: int | None = None, discover: bool = True, g: Gateway = Depends(gw)) -> dict:
    """Seed catalog defaults per provider (idempotent) and optionally discover models from the provider (read-only)."""
    repo = ProviderConfigRepository(g.engine)
    out = {}
    for p in repo.list():
        if provider_id and p.id != provider_id:
            continue
        discovered: list[str] = []
        if discover:
            try:
                discovered = g.adapter(p.name).list_models() if p.name != "echo" else []
            except Exception as e:  # noqa: BLE001
                out[p.name] = {"error": str(e)}
        out[p.name] = {**out.get(p.name, {}), "added": g.seed_catalog(p.id, p.kind, discovered), "discovered": len(discovered)}
    return out


@router.patch("/models/{mid}")
def update_model(mid: int, body: ModelUpdate, g: Gateway = Depends(gw)) -> dict:
    m = g.update_model(mid, **body.model_dump(exclude_none=True))
    if not m:
        raise HTTPException(404, "model not found")
    return m


@router.get("/health")
def health(g: Gateway = Depends(gw)) -> dict:
    return {"providers": g.health(), "now": utcnow()}


@router.get("/usage")
def usage(site_id: str | None = None, date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"), group_by: str = "model", g: Gateway = Depends(gw)) -> dict:
    return g.usage(site_id, date_from, date_to, group_by)


@router.get("/budget")
def budget(site_id: str, g: Gateway = Depends(gw)) -> dict:
    return g.budget(site_id)


class BudgetSet(BaseModel):
    budget_usd_month: float = Field(gt=0, le=100000)


@router.put("/budget")
def set_budget(site_id: str, body: BudgetSet, g: Gateway = Depends(gw)) -> dict:
    """Human-set monthly budget per site (site_settings key `ai`). Thresholds stay 80/100/120 %."""
    from ...brain.content.drafts import DraftRepository
    repo = DraftRepository(g.engine)
    cur = repo.settings(site_id, "ai")
    repo.put_settings(site_id, "ai", {**cur, "budget_usd_month": float(body.budget_usd_month)})
    return g.budget(site_id)


@router.get("/routing/preview")
def routing_preview(task_kind: str, site_id: str | None = None, priority: str = "normal", provider: str | None = None, model: str | None = None, g: Gateway = Depends(gw)) -> dict:
    """Why would this task go to which model — no call is made."""
    if task_kind not in TASK_KINDS_V2:
        raise ApiError(422, f"نوع وظیفه ناشناخته: {task_kind}", code="validation_error", details={"allowed": list(TASK_KINDS_V2)})
    d = TaskRouter(g.engine, g).resolve(task_kind, site_id, priority, override={"provider": provider, "model": model} if provider and model else None)
    return d.to_dict()


@router.post("/estimate")
def estimate(body: EstimateBody, g: Gateway = Depends(gw)) -> dict:
    d = TaskRouter(g.engine, g).resolve(body.task_kind, body.site_id, override={"provider": body.provider, "model": body.model} if body.provider and body.model else None)
    task = AITask(kind=TaskKind.GENERIC, site_id=body.site_id or "*", messages=[AIMessage("user", body.text)], max_tokens=body.max_tokens)
    return {**g.estimate(task, d.chain), "route": d.to_dict()}


# ------------------------------------------------------------------ prompts
def lib(g: Gateway = Depends(gw)) -> PromptLibrary:
    p = PromptLibrary(g.engine); p.seed(); return p


@router.get("/prompts")
def list_prompts(site_id: str | None = None, scope: str | None = None, L: PromptLibrary = Depends(lib)) -> list[dict]:
    return L.list(site_id, scope)


@router.post("/prompts", status_code=201)
def create_prompt(body: PromptCreate, L: PromptLibrary = Depends(lib)) -> dict:
    try:
        return L.create_prompt(body.key, body.scope, body.title, body.template, body.site_id, body.description, body.model_hints)
    except PromptError as e:
        raise ApiError(422, str(e), code="validation_error")


@router.get("/prompts/{pid}")
def get_prompt(pid: int, L: PromptLibrary = Depends(lib)) -> dict:
    p = L.get(pid)
    if not p:
        raise HTTPException(404, "prompt not found")
    return {**p, "performance": L.performance(pid), "tests": L.tests(pid)[:50]}


@router.post("/prompts/{pid}/versions", status_code=201)
def add_version(pid: int, body: VersionCreate, L: PromptLibrary = Depends(lib)) -> dict:
    try:
        return L.add_version(pid, body.template, body.changelog, body.model_hints, activate=body.activate)
    except KeyError:
        raise HTTPException(404, "prompt not found")
    except PromptError as e:
        raise ApiError(422, str(e), code="validation_error")


@router.patch("/prompts/versions/{vid}")
def patch_version(vid: int, body: VersionPatch, L: PromptLibrary = Depends(lib)) -> dict:
    v = L.set_version(vid, body.activate, body.approval, body.approved_by, body.changelog)
    if not v:
        raise HTTPException(404, "version not found")
    return v


@router.post("/prompts/versions/{vid}/preview")
def preview_version(vid: int, body: PromptTestBody, L: PromptLibrary = Depends(lib), g: Gateway = Depends(gw)) -> dict:
    """Rendered prompt with the site's MemoryPack — nothing is sent to a provider."""
    v = L.version(vid)
    if not v:
        raise HTTPException(404, "version not found")
    snap = MemoryPackBuilder(g.engine).snapshot(body.site_id)
    try:
        text = render(v["template"], {**body.variables, "memory_pack": snap["rendered"]}, require_memory=v["scope"] in ("agent", "task"))
    except PromptError as e:
        raise ApiError(422, str(e), code="validation_error")
    return {"rendered": text, "memory_snapshot_id": snap["id"], "variables": v["variables"], "missing": [x for x in v["variables"] if x not in body.variables and x != "memory_pack"]}


@router.post("/prompts/versions/{vid}/test")
def test_version(vid: int, body: PromptTestBody, L: PromptLibrary = Depends(lib), g: Gateway = Depends(gw)) -> dict:
    """Run the version once through the gateway (routed or overridden model), record tokens/cost/latency for comparison."""
    v = L.version(vid)
    if not v:
        raise HTTPException(404, "version not found")
    snap = MemoryPackBuilder(g.engine).snapshot(body.site_id)
    text = render(v["template"], {**body.variables, "memory_pack": snap["rendered"]}, require_memory=v["scope"] in ("agent", "task"))
    d = TaskRouter(g.engine, g).resolve(body.task_kind, body.site_id, override={"provider": body.provider, "model": body.model} if body.provider and body.model else None)
    task = AITask(kind=TaskKind.GENERIC, site_id=body.site_id, messages=[AIMessage("system", (L.active_version("system.base") or {"template": ""})["template"]), AIMessage("user", text)], max_tokens=int((v.get("model_hints") or {}).get("max_tokens", 1200)))
    from ...ai.gateway import CallMeta
    res = g.run(task, d.chain, CallMeta(site_id=body.site_id, agent="prompt_test", prompt_refs={"agent": v["ref"]}, memory_snapshot_id=snap["id"], route_reason=d.reason))
    r = res.response
    tid = L.record_test(vid, site_id=body.site_id, model=r.model if r else None, provider=r.provider if r else None, input_ref=str(body.variables)[:300], output=(r.text if r else None),
                        input_tokens=r.input_tokens if r else None, output_tokens=r.output_tokens if r else None, cost_usd=(r.cost_usd if r else None), latency_ms=(r.latency_ms if r else None))
    return {"test_id": tid, "ok": res.ok, "output": r.text if r else None, "provider": r.provider if r else None, "model": r.model if r else None, "input_tokens": r.input_tokens if r else 0, "output_tokens": r.output_tokens if r else 0,
            "cost_usd": r.cost_usd if r else 0, "latency_ms": r.latency_ms if r else 0, "attempts": [a.__dict__ for a in res.attempts], "route": d.to_dict()["chain"][:2], "placeholder": bool(r and r.provider == "echo")}


@router.patch("/prompts/tests/{tid}")
def rate_test(tid: int, body: PromptTestRating, g: Gateway = Depends(gw)) -> dict:
    from sqlalchemy import text as _t
    with g.engine.begin() as cx:
        cx.execute(_t("UPDATE prompt_tests SET human_rating=:r, notes=:n WHERE id=:i"), {"r": body.human_rating, "n": body.notes, "i": tid})
    return {"id": tid, "human_rating": body.human_rating}


# ------------------------------------------------------------------ insights (learning) + feedback meta
@router.get("/insights")
def insights(site_id: str | None = None, status: str | None = None, g: Gateway = Depends(gw)) -> list[dict]:
    return AILearning(g.engine).insights(site_id, status)


@router.post("/insights/learn")
def learn(site_id: str | None = None, min_n: int = Query(5, ge=2), g: Gateway = Depends(gw)) -> dict:
    return AILearning(g.engine).learn(site_id, min_n)


@router.patch("/insights/{iid}")
def set_insight(iid: int, body: InsightStatus, g: Gateway = Depends(gw)) -> dict:
    r = AILearning(g.engine).set_status(iid, body.status)
    if not r:
        raise HTTPException(404, "insight not found")
    return r


@router.get("/feedback-tags")
def feedback_tags() -> list[dict]:
    return [{"tag": t, "fa": TAG_FA[t]} for t in FEEDBACK_TAGS]
