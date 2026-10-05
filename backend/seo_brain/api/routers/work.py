"""Site-scoped action ledger for SEO work and its event history."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from ..deps import engine, require_site
from ..project_access import project_responsibility, require_assignee, require_lead

router = APIRouter(prefix="/sites/{site_id}/work", tags=["work"], dependencies=[Depends(require_site)])
Kind = Literal["manual", "issue", "opportunity", "content"]
Status = Literal["new", "triaged", "approved", "assigned", "in_progress", "review", "published",
                 "measurement_pending", "verified", "blocked", "rejected", "deferred"]
Priority = Literal["critical", "high", "normal", "low"]
ACTIVE = {"approved", "assigned", "in_progress", "review", "published", "measurement_pending", "verified", "blocked"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _due_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(422, "due date must include a timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _date_utc(value: datetime | None, label: str) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(422, f"{label} must include a timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


class WorkIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=5000)
    kind: Kind = "manual"
    source_id: int | None = Field(default=None, ge=1)
    url: str | None = Field(default=None, max_length=2048)
    query: str | None = Field(default=None, max_length=500)
    status: Status = "new"
    owner_id: int | None = Field(default=None, ge=1)
    team_id: int | None = Field(default=None, ge=1)
    priority: Priority = "normal"
    estimated_hours: float | None = Field(default=None, ge=0, le=1000)
    start_at: datetime | None = None
    progress_percent: int = Field(default=0, ge=0, le=100)
    parent_id: int | None = Field(default=None, ge=1)
    milestone_id: int | None = Field(default=None, ge=1)
    due_at: datetime | None = None
    blocked_reason: str | None = Field(default=None, max_length=1000)
    verification_note: str | None = Field(default=None, max_length=3000)
    note: str | None = Field(default=None, max_length=1000)


class WorkPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    url: str | None = Field(default=None, max_length=2048)
    query: str | None = Field(default=None, max_length=500)
    status: Status | None = None
    owner_id: int | None = Field(default=None, ge=1)
    team_id: int | None = Field(default=None, ge=1)
    priority: Priority | None = None
    estimated_hours: float | None = Field(default=None, ge=0, le=1000)
    start_at: datetime | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    parent_id: int | None = Field(default=None, ge=1)
    milestone_id: int | None = Field(default=None, ge=1)
    due_at: datetime | None = None
    blocked_reason: str | None = Field(default=None, max_length=1000)
    verification_note: str | None = Field(default=None, max_length=3000)
    note: str | None = Field(default=None, max_length=1000)


def _record(cx, site_id: str, item_id: int, event_type: str, before: dict | None,
            after: dict, note: str | None, actor: dict | None = None) -> None:
    cx.execute(text("""INSERT INTO work_item_events
        (site_id,work_item_id,event_type,before_json,after_json,note,actor_id,actor_username,created_at)
        VALUES (:s,:id,:event,:before,:after,:note,:actor_id,:actor_username,:at)"""),
        {"s": site_id, "id": item_id, "event": event_type,
         "before": json.dumps(before, ensure_ascii=False) if before else None,
         "after": json.dumps(after, ensure_ascii=False), "note": note,
         "actor_id": actor["id"] if actor else None, "actor_username": actor["username"] if actor else None,
         "at": now()})


def _validate(cx, site_id: str, values: dict, item_id: int | None = None,
              strict_owner: bool = False) -> None:
    if values.get("status") in ACTIVE and (not values.get("owner_id") or not values.get("due_at")):
        raise HTTPException(422, "active work requires an owner and due date")
    if values.get("status") == "blocked" and not values.get("blocked_reason"):
        raise HTTPException(422, "blocked work requires a reason")
    if values.get("status") == "verified" and not values.get("verification_note"):
        raise HTTPException(422, "verified work requires a verification note")
    if values.get("owner_id") is not None:
        owner = cx.execute(text("SELECT role FROM panel_users WHERE id=:id AND active=1"),
                           {"id": values["owner_id"]}).scalar_one_or_none()
        if not owner:
            raise HTTPException(422, "owner must be an active panel user")
        if strict_owner and owner == "call_center":
            raise HTTPException(422, "call center operators cannot own SEO project work")
        if strict_owner and owner != "admin" and not cx.execute(text("""SELECT 1 FROM site_assignments
            WHERE site_id=:site AND user_id=:user AND responsibility IN ('lead','contributor')"""),
            {"site": site_id, "user": values["owner_id"]}).first():
            raise HTTPException(422, "owner must be a lead or contributor in this project")
    if values.get("team_id") is not None:
        exists = cx.execute(text("SELECT 1 FROM panel_teams WHERE id=:id AND active=1"),
                            {"id": values["team_id"]}).first()
        if not exists:
            raise HTTPException(422, "team must be active")
    if values.get("start_at") and values.get("due_at") and values["start_at"] > values["due_at"]:
        raise HTTPException(422, "start date must be before due date")
    if values.get("parent_id") is not None:
        parent = cx.execute(text("SELECT id,parent_id FROM work_items WHERE id=:id AND site_id=:s"),
                            {"id": values["parent_id"], "s": site_id}).mappings().first()
        if not parent:
            raise HTTPException(422, "parent must belong to this site")
        seen = {item_id} if item_id else set()
        while parent:
            if parent["id"] in seen:
                raise HTTPException(422, "work hierarchy cannot contain a cycle")
            seen.add(parent["id"])
            parent = cx.execute(text("SELECT id,parent_id FROM work_items WHERE id=:id AND site_id=:s"),
                                {"id": parent["parent_id"], "s": site_id}).mappings().first() if parent["parent_id"] else None
    if values.get("milestone_id") is not None and not cx.execute(
        text("SELECT 1 FROM work_milestones WHERE id=:id AND site_id=:s"),
        {"id": values["milestone_id"], "s": site_id}).first():
        raise HTTPException(422, "milestone must belong to this site")
    kind, source_id = values.get("kind"), values.get("source_id")
    if kind == "manual" and source_id is not None:
        raise HTTPException(422, "manual work cannot reference a source id")
    if kind in ("issue", "opportunity", "content") and source_id is not None:
        table = {"issue": "seo_problems", "opportunity": "seo_opportunities", "content": "content_items"}[kind]
        if not cx.execute(text(f"SELECT 1 FROM {table} WHERE id=:id AND site_id=:s"),
                          {"id": source_id, "s": site_id}).first():
            raise HTTPException(422, "source does not belong to this site")


@router.get("")
def list_work(site_id: str, status: Status | None = None, owner_id: int | None = None,
              q: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
              eng: Engine = Depends(engine)) -> dict:
    clauses = ["w.site_id=:s"]
    args: dict = {"s": site_id, "lim": limit, "off": offset}
    if status:
        clauses.append("w.status=:status"); args["status"] = status
    if owner_id:
        clauses.append("w.owner_id=:owner"); args["owner"] = owner_id
    if q:
        clauses.append("(w.title LIKE :q OR w.url LIKE :q)"); args["q"] = "%" + q.strip() + "%"
    where = " AND ".join(clauses)
    with eng.connect() as cx:
        total = cx.execute(text(f"SELECT COUNT(*) FROM work_items w WHERE {where}"), args).scalar_one()
        rows = cx.execute(text(f"""SELECT w.*, u.full_name AS owner_name, t.name AS team_name FROM work_items w
            LEFT JOIN panel_users u ON u.id=w.owner_id
            LEFT JOIN panel_teams t ON t.id=w.team_id WHERE {where}
            ORDER BY CASE WHEN w.status='blocked' THEN 0 WHEN w.due_at IS NOT NULL AND w.due_at<:now THEN 1 ELSE 2 END,
                     w.due_at, w.id DESC LIMIT :lim OFFSET :off"""), {**args, "now": now()}).mappings().all()
        summary = cx.execute(text("""SELECT COUNT(*) AS total,
            SUM(CASE WHEN status='blocked' THEN 1 ELSE 0 END) AS blocked,
            SUM(CASE WHEN status NOT IN ('verified','rejected','deferred') AND due_at<:now THEN 1 ELSE 0 END) AS overdue,
            SUM(CASE WHEN status NOT IN ('verified','rejected','deferred') AND owner_id IS NULL THEN 1 ELSE 0 END) AS unassigned
            FROM work_items WHERE site_id=:s"""), {"s": site_id, "now": now()}).mappings().one()
    return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset,
            "summary": {k: int(v or 0) for k, v in summary.items()}}


@router.post("", status_code=201)
def create_work(site_id: str, body: WorkIn, request: Request, eng: Engine = Depends(engine)) -> dict:
    if body.status in ("rejected", "deferred") and not body.note:
        raise HTTPException(422, "rejected or deferred work requires a reason")
    values = body.model_dump(exclude={"note"})
    values["due_at"] = _due_utc(body.due_at)
    values["start_at"] = _date_utc(body.start_at, "start date")
    if values["status"] == "verified":
        values["progress_percent"] = 100
    values.update(site_id=site_id, created_at=now(), updated_at=now())
    try:
        with eng.begin() as cx:
            require_lead(cx, request, site_id)
            _validate(cx, site_id, values, strict_owner=getattr(request.state, "panel_user", None) is not None)
            cols = list(values)
            result = cx.execute(text(f"INSERT INTO work_items({','.join(cols)}) VALUES({','.join(':'+c for c in cols)})"), values)
            item_id = result.lastrowid
            row = dict(cx.execute(text("SELECT * FROM work_items WHERE site_id=:s AND id=:id"),
                                  {"s": site_id, "id": item_id}).mappings().one())
            _record(cx, site_id, item_id, "created", None, row, body.note, getattr(request.state, "panel_user", None))
    except IntegrityError as exc:
        raise HTTPException(409, "work already exists for this source") from exc
    request.state.audit_fields = list(body.model_fields_set)
    return row


@router.patch("/{item_id}")
def update_work(site_id: str, item_id: int, body: WorkPatch, request: Request, eng: Engine = Depends(engine)) -> dict:
    patch = body.model_dump(exclude_unset=True, exclude={"note"})
    if any(key in patch and patch[key] is None for key in ("title", "description", "status", "priority", "progress_percent")):
        raise HTTPException(422, "title, description and status cannot be null")
    if "due_at" in patch:
        patch["due_at"] = _due_utc(patch["due_at"])
    if "start_at" in patch:
        patch["start_at"] = _date_utc(patch["start_at"], "start date")
    if patch.get("status") == "verified":
        patch["progress_percent"] = 100
    with eng.begin() as cx:
        current = cx.execute(text("SELECT * FROM work_items WHERE site_id=:s AND id=:id"),
                             {"s": site_id, "id": item_id}).mappings().first()
        if not current:
            raise HTTPException(404, "work item not found")
        require_assignee(cx, request, site_id, current["owner_id"])
        if project_responsibility(cx, request, site_id) == "contributor":
            allowed = {"status", "progress_percent", "blocked_reason", "note"}
            if not body.model_fields_set <= allowed:
                raise HTTPException(403, "contributors may only update status, progress and blocker notes")
            if patch.get("status") in {"verified", "rejected", "deferred", "approved", "assigned"}:
                raise HTTPException(403, "project lead approval is required for this status")
        before = dict(current)
        merged = {**before, **patch}
        if patch.get("status") in ("rejected", "deferred") and patch["status"] != before["status"] and not body.note:
            raise HTTPException(422, "rejected or deferred work requires a reason")
        _validate(cx, site_id, merged, item_id,
                  strict_owner=getattr(request.state, "panel_user", None) is not None and "owner_id" in patch)
        if merged["status"] == "verified" and before["status"] != "verified":
            unfinished = cx.execute(text("""SELECT 1 FROM work_dependencies d
                JOIN work_items prerequisite ON prerequisite.id=d.depends_on_id
                WHERE d.work_item_id=:id AND prerequisite.status<>'verified' LIMIT 1"""), {"id": item_id}).first()
            if unfinished:
                raise HTTPException(422, "prerequisite work is not verified")
            unfinished_child = cx.execute(text("""SELECT 1 FROM work_items
                WHERE site_id=:s AND parent_id=:id AND status NOT IN ('verified','rejected','deferred') LIMIT 1"""),
                {"s": site_id, "id": item_id}).first()
            if unfinished_child:
                raise HTTPException(422, "child work is not complete")
        if merged == before and not body.note:
            return before
        if merged == before:
            _record(cx, site_id, item_id, "comment", before, before, body.note,
                    getattr(request.state, "panel_user", None))
            request.state.audit_fields = ["note"]
            return before
        patch["updated_at"] = now()
        cx.execute(text("UPDATE work_items SET " + ",".join(f"{key}=:{key}" for key in patch) +
                        " WHERE site_id=:s AND id=:id"), {**patch, "s": site_id, "id": item_id})
        after = dict(cx.execute(text("SELECT * FROM work_items WHERE site_id=:s AND id=:id"),
                                {"s": site_id, "id": item_id}).mappings().one())
        _record(cx, site_id, item_id, "updated", before, after, body.note, getattr(request.state, "panel_user", None))
    request.state.audit_fields = list(body.model_fields_set)
    return after


@router.get("/{item_id}/events")
def work_events(site_id: str, item_id: int, eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        if not cx.execute(text("SELECT 1 FROM work_items WHERE site_id=:s AND id=:id"),
                          {"s": site_id, "id": item_id}).first():
            raise HTTPException(404, "work item not found")
        rows = cx.execute(text("""SELECT id,event_type,before_json,after_json,note,actor_id,actor_username,created_at
            FROM work_item_events WHERE site_id=:s AND work_item_id=:id ORDER BY id"""),
            {"s": site_id, "id": item_id}).mappings().all()
    return [dict(row) for row in rows]
