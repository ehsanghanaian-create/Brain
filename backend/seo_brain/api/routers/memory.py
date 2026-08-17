from __future__ import annotations

from fastapi import APIRouter, Depends

from ...ai import MemoryService
from ...db.repositories import SiteMemoryRepository
from ..deps import memory_repo, require_site
from ..schemas import MemoryUpdate

router = APIRouter(prefix="/sites/{site_id}/memory", tags=["memory"], dependencies=[Depends(require_site)])


@router.get("")
def get_memory(site_id: str, repo: SiteMemoryRepository = Depends(memory_repo)) -> dict:
    return repo.get(site_id).to_dict()


@router.put("")
def put_memory(site_id: str, body: MemoryUpdate, repo: SiteMemoryRepository = Depends(memory_repo)) -> dict:
    return MemoryService(repo).update(site_id, **body.model_dump(exclude_none=True)).to_dict()


@router.get("/context")
def context(site_id: str, repo: SiteMemoryRepository = Depends(memory_repo)) -> dict:
    msgs = MemoryService(repo).context_messages(site_id)
    return {"messages": [m.__dict__ for m in msgs]}
