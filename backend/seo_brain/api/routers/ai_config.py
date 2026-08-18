"""AI provider configuration endpoints (phase 6): /ai/provider-configs, /ai/task-routes. Keys are stored in the
SecretStore and never returned by any endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from ...ai.config import PROVIDER_KINDS, TASK_KINDS, ProviderConfigRepository, test_provider
from ..deps import engine
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
def test_provider_config(pid: int, repo: ProviderConfigRepository = Depends(cfg_repo)) -> dict:
    p = repo.get(pid)
    if not p:
        raise HTTPException(404, "provider not found")
    res = test_provider(p, repo.api_key(p))
    repo.record_test(pid, res)
    return res


@router.get("/task-routes")
def task_routes(site_id: str | None = None, repo: ProviderConfigRepository = Depends(cfg_repo)) -> dict:
    return {"task_kinds": list(TASK_KINDS), "routes": repo.routes(site_id)}


@router.put("/task-routes/{task_kind}")
def set_task_route(task_kind: str, body: RouteSet, repo: ProviderConfigRepository = Depends(cfg_repo)) -> dict:
    try:
        return repo.set_route(task_kind, body.provider_id, body.model, body.fallback_provider_id, body.fallback_model, body.site_id, policy=body.policy, fallbacks=body.fallbacks)
    except ValueError as e:
        raise ApiError(422, str(e), code="validation_error")
