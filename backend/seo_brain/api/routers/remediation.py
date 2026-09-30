"""Per-issue SEO remediation proposals and controlled execution for connected sites."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from ...automation import Job, JobQueue, get_job_queue
from ...remediation.service import RemediationError, RemediationService, _hash, public_run
from ...remediation.playbooks import ROADMAPS
from ..deps import engine, gateway, job_queue, require_site
from ..errors import ApiError

router = APIRouter(prefix="/sites/{site_id}/remediation", tags=["remediation"], dependencies=[Depends(require_site)])


def service(eng: Engine = Depends(engine), gw=Depends(gateway)) -> RemediationService:
    return RemediationService(eng, gw)


def _call(fn):
    try:
        return fn()
    except RemediationError as exc:
        raise ApiError(exc.status, str(exc), code=exc.code) from exc


class StartRun(BaseModel):
    proposal_id: str
    method_id: str
    evidence_hash: str
    idempotency_key: str = Field(min_length=8, max_length=100)
    uncertain_confirmed: bool = False


class RemediationIssueOut(BaseModel):
    issue_key: str
    problem_type: str
    severity: str
    url: str
    related_url: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None


class RemediationTypeCountOut(BaseModel):
    problem_type: str
    count: int


class RemediationGroupOut(BaseModel):
    category: str
    count: int
    types: list[RemediationTypeCountOut]


class RemediationIssuesOut(BaseModel):
    total: int
    items: list[RemediationIssueOut]
    groups: list[RemediationGroupOut]
    playbook_version: int
    coverage: dict[str, Any] | None = None


class RemediationMethodOut(BaseModel):
    id: str
    title: str
    kind: str
    owner: str
    value: str | list[dict[str, Any]]
    source_url: str | None = None
    affected_urls: list[str]
    impact_unknown: bool
    confidence: str
    uncertain: bool
    uncertainty_reason: str
    reason: str
    verify: str
    available: bool
    status: str
    rollback: bool
    access: dict[str, str]


class RemediationProposalOut(BaseModel):
    id: str
    site_id: str
    issue_key: str
    problem_type: str
    url: str
    related_url: str
    evidence_hash: str
    methods: list[RemediationMethodOut]
    status: str
    created_at: str
    expires_at: str
    roadmap: list[str]


class RemediationVerificationOut(BaseModel):
    ok: bool | None = None
    reason: str | None = None
    crawl_run_id: str | None = None
    analysis_run_id: str | None = None


class RemediationRunOut(BaseModel):
    id: str
    proposal_id: str
    site_id: str
    issue_key: str
    method_id: str
    status: str
    job_id: str | None = None
    error: str | None = None
    created_at: str
    updated_at: str
    verification: RemediationVerificationOut | None = None


@router.get("/problems", response_model=RemediationIssuesOut)
def problems(site_id: str, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
             problem_type: str | None = None, category: str | None = None,
             svc: RemediationService = Depends(service)) -> dict:
    return _call(lambda: svc.list_issues(site_id, limit, offset, problem_type, category))


@router.post("/problems/{issue_key}/proposals", response_model=RemediationProposalOut)
def propose(site_id: str, issue_key: str, svc: RemediationService = Depends(service)) -> dict:
    return _call(lambda: svc.propose(site_id, issue_key))


@router.post("/problems/{issue_key}/proposal-jobs", status_code=202)
def start_proposal_job(site_id: str, issue_key: str, svc: RemediationService = Depends(service),
                       q: JobQueue = Depends(job_queue)) -> dict:
    issue = _call(lambda: svc._issue(site_id, issue_key))
    previous = [run for run in q.list(200) if run.job.type == "seo_proposal" and run.job.site_id == site_id
                and run.job.payload.get("issue_key") == issue_key]
    for run in previous:
        if run.status in ("queued", "running"):
            return run.to_dict()
    # Reopening an issue within the proposal lifetime should not spend another
    # slow Atria call. Only reuse it if the live evidence still matches.
    current_hash = None
    for run in previous:
        proposal = run.result if run.status == "succeeded" and isinstance(run.result, dict) else None
        if not proposal:
            continue
        try:
            expires = datetime.fromisoformat(proposal["expires_at"])
            if expires <= datetime.now(timezone.utc):
                continue
            if current_hash is None:
                current_hash = _hash(svc._evidence(site_id, issue))
            if proposal.get("evidence_hash") == current_hash:
                return run.to_dict()
        except (KeyError, TypeError, ValueError, RemediationError):
            continue
    return q.enqueue(Job(type="seo_proposal", payload={"site_id": site_id, "issue_key": issue_key}, site_id=site_id)).to_dict()


@router.get("/problems/{issue_key}/runs", response_model=list[RemediationRunOut])
def run_history(site_id: str, issue_key: str, limit: int = Query(5, ge=1, le=20), svc: RemediationService = Depends(service)) -> list[dict]:
    return _call(lambda: svc.run_history(site_id, issue_key, limit))


@router.get("/proposals/{proposal_id}", response_model=RemediationProposalOut)
def get_proposal(site_id: str, proposal_id: str, svc: RemediationService = Depends(service)) -> dict:
    proposal = _call(lambda: svc.proposal(site_id, proposal_id))
    return {**{k: v for k, v in proposal.items() if k != "evidence"}, "roadmap": ROADMAPS[proposal["problem_type"]]}


@router.post("/runs", status_code=202, response_model=RemediationRunOut)
def start_run(site_id: str, body: StartRun, svc: RemediationService = Depends(service)) -> dict:
    run = _call(lambda: svc.create_run(site_id, body.proposal_id, body.method_id, body.evidence_hash,
                                        body.idempotency_key, body.uncertain_confirmed))
    if run["status"] == "queued" and run.get("_created"):
        job = get_job_queue().enqueue(Job(type="seo_remediation", site_id=site_id, payload={"site_id": site_id, "run_id": run["id"]}))
        svc.update_run(run["id"], job_id=job.run_id)
    return public_run(svc.get_run(site_id, run["id"]))


@router.get("/runs/{run_id}", response_model=RemediationRunOut)
def get_run(site_id: str, run_id: str, svc: RemediationService = Depends(service)) -> dict:
    return public_run(_call(lambda: svc.get_run(site_id, run_id)))


@router.post("/runs/{run_id}/resume", status_code=202, response_model=RemediationRunOut)
def resume(site_id: str, run_id: str, svc: RemediationService = Depends(service)) -> dict:
    run = _call(lambda: svc.resume_run(site_id, run_id))
    job = get_job_queue().enqueue(Job(type="seo_remediation", site_id=site_id, payload={"site_id": site_id, "run_id": run_id}))
    svc.update_run(run_id, job_id=job.run_id)
    return public_run(svc.get_run(site_id, run_id))


@router.post("/runs/{run_id}/rollback", response_model=RemediationRunOut)
def rollback(site_id: str, run_id: str, svc: RemediationService = Depends(service)) -> dict:
    return public_run(_call(lambda: svc.rollback(site_id, run_id)))


@router.post("/runs/{run_id}/verify", response_model=RemediationRunOut)
def verify(site_id: str, run_id: str, svc: RemediationService = Depends(service)) -> dict:
    return public_run(_call(lambda: svc.verify_run(site_id, run_id)))
