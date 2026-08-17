from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...ai import AIMessage, AIOrchestrator, AITask, TaskKind
from ..deps import _router, orchestrator, require_site
from ..schemas import AIRunRequest

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/routes")
def routes() -> dict:
    return _router().describe()


@router.get("/providers")
def providers() -> list[dict]:
    r = _router()
    return [{"name": p.name, "models": list(p.models), "test": p.test_connection()} for p in r.providers.values()]


@router.post("/sites/{site_id}/run", dependencies=[Depends(require_site)])
def run(site_id: str, body: AIRunRequest, orch: AIOrchestrator = Depends(orchestrator)) -> dict:
    """Run one task through the orchestrator (Task → Router → Provider → Validator → Memory).
    Phase 1: only the offline EchoProvider is routed, so this never spends tokens."""
    try:
        kind = TaskKind(body.kind)
    except ValueError:
        raise HTTPException(422, f"unknown task kind '{body.kind}'; one of {[k.value for k in TaskKind]}")
    messages = ([AIMessage("system", body.system)] if body.system else []) + [AIMessage("user", body.prompt)]
    schema = {"type": "object", "required": body.json_keys, "properties": {k: {} for k in body.json_keys}} if body.json_keys else None
    task = AITask(kind=kind, site_id=site_id, messages=messages, json_schema=schema)
    learn = {"pattern": body.learn_pattern, "evidence": body.learn_evidence or ""} if body.learn_pattern else None
    return orch.run(task, learn=learn).to_dict()
