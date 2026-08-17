from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...automation import Job, JobQueue
from ..deps import job_queue
from ..schemas import JobEnqueue

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_runs(limit: int = 50, q: JobQueue = Depends(job_queue)) -> list[dict]:
    return [r.to_dict() for r in q.list(limit)]


@router.get("/{run_id}")
def get_run(run_id: str, q: JobQueue = Depends(job_queue)) -> dict:
    r = q.get(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return r.to_dict()


@router.post("", status_code=202)
def enqueue(body: JobEnqueue, q: JobQueue = Depends(job_queue)) -> dict:
    try:
        return q.enqueue(Job(type=body.type, payload=body.payload, site_id=body.payload.get("site_id"))).to_dict()
    except KeyError as e:
        raise HTTPException(422, str(e))
