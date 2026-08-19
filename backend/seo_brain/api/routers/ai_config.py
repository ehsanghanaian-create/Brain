"""AI provider configuration endpoints (phase 6): /ai/provider-configs, /ai/task-routes. Keys are stored in the
SecretStore and never returned by any endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from ...ai.config import PROVIDER_KINDS, TASK_KINDS, ProviderConfigRepository, test_provider
from ...db.repositories.base import utcnow
from ..deps import engine, gateway
from ..errors import ApiError

router = APIRouter(prefix="/ai", tags=["ai"])


class ProviderCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    kind: str
    api_key: str | None = Field(default=None, min_length=4)
    base_url: str | None = None
    default_model: str | None = None
    models: list[str] | None = None
    enabled: bool = True


class ProviderUpdate(BaseModel):
    name: str | None = None
    api_key: str | None = Field(default=None, min_length=4)
    base_url: str | None = None
    default_model: str | None = None
    models: list[str] | None = None
    enabled: bool | None = None
    clear_key: bool = False


class RouteSet(BaseModel):
    provider_id: int | None = None
    model: str | None = None
    fallback_provider_id: int | None = None
    fallback_model: str | None = None
    site_id: str = "*"
    policy: str | None = None                      # phase 9: explicit | auto | echo (None keeps current)
    fallbacks: list[dict] | None = None            # phase 9: [{provider_id, model}, ...] ordered fallback chain


def cfg_repo(eng: Engine = Depends(engine)) -> ProviderConfigRepository:
    return ProviderConfigRepository(eng)


@router.get("/provider-kinds")
def provider_kinds() -> list[dict]:
    return [{"kind": k, **v} for k, v in PROVIDER_KINDS.items()]


@router.get("/provider-configs")
def list_provider_configs(repo: ProviderConfigRepository = Depends(cfg_repo)) -> list[dict]:
    """Configured providers — keys are never returned (only has_key + key_hint)."""
    return [p.to_dict() for p in repo.list()]


@router.post("/provider-configs", status_code=201)
def create_provider_config(body: ProviderCreate, repo: ProviderConfigRepository = Depends(cfg_repo)) -> dict:
    try:
        p = repo.create(body.name, body.kind, body.api_key, body.base_url, body.default_model, body.models, body.enabled)
        try:
            from ..deps import gateway as _gw
            _gw().seed_catalog(p.id, p.kind); _gw().invalidate()
        except Exception:  # noqa: BLE001
            pass
    except ValueError as e:
        exists = "exists" in str(e)
        raise ApiError(409 if exists else 422, str(e), code="conflict" if exists else "validation_error")
    return p.to_dict()


@router.patch("/provider-configs/{pid}")
def update_provider_config(pid: int, body: ProviderUpdate, repo: ProviderConfigRepository = Depends(cfg_repo)) -> dict:
    if not repo.get(pid):
        raise HTTPException(404, "provider not found")
    if body.clear_key:
        repo.clear_key(pid)
    p = repo.update(pid, **body.model_dump(exclude_none=True, exclude={"clear_key"}))
    try:
        from ..deps import gateway as _gw
        _gw().invalidate()
    except Exception:  # noqa: BLE001
        pass
    return p.to_dict()  # type: ignore[union-attr]


@router.delete("/provider-configs/{pid}")
def delete_provider_config(pid: int, repo: ProviderConfigRepository = Depends(cfg_repo)) -> dict:
    if not repo.delete(pid):
        raise HTTPException(404, "provider not found")
    return {"deleted": pid}


@router.post("/provider-configs/{pid}/test")
def test_provider_config(pid: int, repo: ProviderConfigRepository = Depends(cfg_repo), g=Depends(gateway)) -> dict:
    """Read-only connection probe (model list) through the Gateway adapter — same transport/keys as real calls; never sends a prompt."""
    p = repo.get(pid)
    if not p:
        raise HTTPException(404, "provider not found")
    key = repo.api_key(p)
    if PROVIDER_KINDS.get(p.kind, {}).get("needs_key") and not key:
        res = {"ok": False, "status": "not_configured", "message": "کلید API ثبت نشده است", "tested_at": utcnow()}
    else:
        try:
            g.invalidate(p.name)
            r = g.adapter(p.name).test_connection()
            models = [m for m in (r.get("models") or []) if m]
            res = ({"ok": True, "status": "ok", "message": f"اتصال برقرار است — {len(models)} مدل در دسترس", "models_found": models[:50], "tested_at": utcnow()} if r.get("ok")
                   else {"ok": False, "status": "not_authorized" if "unauthorized" in str(r.get("error", "")) else "error", "message": f"اتصال ناموفق: {r.get('error')}", "tested_at": utcnow()})
        except Exception:  # noqa: BLE001 — fall back to the phase-6 probe
            res = test_provider(p, key)
    repo.record_test(pid, res)
    return res


@router.get("/provider-configs/{pid}/recommended-routes")
def recommended_routes(pid: int, repo: ProviderConfigRepository = Depends(cfg_repo)) -> dict:
    """Curated route table for this provider kind (Claude: Sonnet balanced / Opus quality / Haiku fast). Read-only — nothing changes."""
    p = repo.get(pid)
    if not p:
        raise HTTPException(404, "provider not found")
    return {"provider_id": pid, "kind": p.kind, "routes": repo.recommended_routes(p)}


class ApplyRoutes(BaseModel):
    site_id: str = "*"
    overwrite: bool = True


@router.post("/provider-configs/{pid}/recommended-routes")
def apply_recommended_routes(pid: int, body: ApplyRoutes | None = None, repo: ProviderConfigRepository = Depends(cfg_repo)) -> dict:
    """Human action: apply the curated routes as explicit ai_routes (routing never changes automatically)."""
    body = body or ApplyRoutes()
    try:
        applied = repo.apply_recommended_routes(pid, body.site_id, body.overwrite)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"provider_id": pid, "applied": len(applied), "routes": applied}


@router.get("/provider-configs/{pid}/gateway-status")
def gateway_status(pid: int, repo: ProviderConfigRepository = Depends(cfg_repo), g=Depends(gateway)) -> dict:
    """Connection / routing / fallback status of a provider (rich for gateway kinds such as OmniRoute). Read-only, no prompt sent."""
    from sqlalchemy import select as _select
    from ...db.tables import ai_calls
    p = repo.get(pid)
    if not p:
        raise HTTPException(404, "provider not found")
    d = p.to_dict()
    health = next((h for h in g.health() if h["provider"] == p.name), None)
    caps: dict = {}; last_decision = None; adapter_health = None
    try:
        a = g.adapter(p.name)
        caps = a.capabilities() if hasattr(a, "capabilities") else {}
        last_decision = getattr(a, "last_decision", None); adapter_health = getattr(a, "last_health", None)
    except Exception as e:  # noqa: BLE001 — not configured/enabled
        caps = {"error": str(e)}
    routes = repo.routes(None)
    primary = [r["task_kind"] for r in routes if r.get("provider_id") == pid]
    fallback_for = [r["task_kind"] for r in routes if r.get("fallback_provider_id") == pid or any(fb.get("provider_id") == pid for fb in (r.get("fallbacks") or []))]
    with g.engine.connect() as cx:
        recent = [dict(r._mapping) for r in cx.execute(_select(ai_calls.c.id, ai_calls.c.model, ai_calls.c.ok, ai_calls.c.latency_ms, ai_calls.c.cost_usd, ai_calls.c.task_kind, ai_calls.c.created_at, ai_calls.c.error)
                                                       .where(ai_calls.c.provider == p.name).order_by(ai_calls.c.id.desc()).limit(8)).all()]
    models = g.models(pid, enabled_only=True)
    breaker_open = bool(health and health.get("breaker_open_until") and health["breaker_open_until"] > utcnow())
    status = "missing_credentials" if not d["configured"] else ("error" if (p.last_test and not p.last_test.get("ok")) or breaker_open else ("connected" if p.last_test and p.last_test.get("ok") else "untested"))
    return {"provider_id": pid, "name": p.name, "kind": p.kind, "is_gateway": d["is_gateway"], "endpoint_url": d["endpoint_url"], "status": status, "has_key": d["has_key"], "last_test": p.last_test,
            "health": health, "breaker_open": breaker_open, "capabilities": caps, "adapter_health": adapter_health,
            "routing": {"last_decision": last_decision, "primary_for": primary, "auto_models": caps.get("auto_models") or [], "models_available": len(models),
                        "models": [m["model_id"] for m in models][:50]},
            "fallback": {"fallback_for": fallback_for, "chain_fallback": "SEO Brain Gateway: retry once → next RouteStep → Echo only if chain empty", "upstream": caps.get("fallback")},
            "recent_calls": recent}


@router.get("/task-routes")
def task_routes(site_id: str | None = None, repo: ProviderConfigRepository = Depends(cfg_repo)) -> dict:
    return {"task_kinds": list(TASK_KINDS), "routes": repo.routes(site_id)}


@router.put("/task-routes/{task_kind}")
def set_task_route(task_kind: str, body: RouteSet, repo: ProviderConfigRepository = Depends(cfg_repo)) -> dict:
    try:
        return repo.set_route(task_kind, body.provider_id, body.model, body.fallback_provider_id, body.fallback_model, body.site_id, policy=body.policy, fallbacks=body.fallbacks)
    except ValueError as e:
        raise ApiError(422, str(e), code="validation_error")
