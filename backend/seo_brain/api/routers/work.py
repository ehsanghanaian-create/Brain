"""Site-scoped action ledger for SEO work and its event history."""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timezone
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
    board_order: float | None = Field(default=None, ge=-1000000000, le=1000000000)


class ChecklistIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)


class ChecklistPatch(BaseModel):
    done: bool


class LabelIn(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    color: str = Field(default="#64748b", pattern=r"^#[0-9a-fA-F]{6}$")


class BulkWorkPatch(BaseModel):
    owner_id: int | None = Field(default=None, ge=1)
    due_at: datetime | None = None
    priority: Priority | None = None


class BulkWorkIn(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=100)
    patch: BulkWorkPatch


class CustomFieldIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    field_type: Literal["text", "number", "date", "select"]
    options: list[str] = Field(default_factory=list, max_length=50)


class CustomValueIn(BaseModel):
    value: str | float | int | None


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
            values["board_order"] = float(cx.execute(text("""SELECT COALESCE(MAX(board_order),0)+1024
                FROM work_items WHERE site_id=:site AND status=:status"""),
                {"site": site_id, "status": values["status"]}).scalar_one())
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


@router.post("/bulk")
def bulk_update_work(site_id: str, body: BulkWorkIn, request: Request,
                     eng: Engine = Depends(engine)) -> dict:
    if len(set(body.item_ids)) != len(body.item_ids) or any(item_id < 1 for item_id in body.item_ids):
        raise HTTPException(422, "item ids must be unique positive integers")
    patch = body.patch.model_dump(exclude_unset=True)
    if not patch or ("priority" in patch and patch["priority"] is None):
        raise HTTPException(422, "owner, due date or priority change is required")
    if "due_at" in patch:
        patch["due_at"] = _due_utc(patch["due_at"])
    with eng.begin() as cx:
        require_lead(cx, request, site_id)
        identifiers = {f"item_{index}": item_id for index, item_id in enumerate(body.item_ids)}
        placeholders = ",".join(f":{key}" for key in identifiers)
        rows = cx.execute(text(f"""SELECT * FROM work_items WHERE site_id=:site
            AND id IN ({placeholders})"""), {**identifiers, "site": site_id}).mappings().all()
        if len(rows) != len(body.item_ids):
            raise HTTPException(404, "one or more work items are outside this project")
        for row in rows:
            _validate(cx, site_id, {**dict(row), **patch}, row["id"],
                      strict_owner=getattr(request.state, "panel_user", None) is not None and "owner_id" in patch)
        stamp = now()
        for row in rows:
            before = dict(row)
            cx.execute(text("UPDATE work_items SET " + ",".join(f"{key}=:{key}" for key in patch) +
                            ",updated_at=:at WHERE site_id=:site AND id=:id"),
                       {**patch, "at": stamp, "site": site_id, "id": row["id"]})
            after = dict(cx.execute(text("SELECT * FROM work_items WHERE id=:id"),
                                    {"id": row["id"]}).mappings().one())
            _record(cx, site_id, row["id"], "bulk_updated", before, after, None,
                    getattr(request.state, "panel_user", None))
    request.state.audit_fields = list(patch)
    return {"updated": len(rows), "item_ids": body.item_ids}


@router.patch("/{item_id}")
def update_work(site_id: str, item_id: int, body: WorkPatch, request: Request, eng: Engine = Depends(engine)) -> dict:
    patch = body.model_dump(exclude_unset=True, exclude={"note"})
    if any(key in patch and patch[key] is None for key in ("title", "description", "status", "priority", "progress_percent", "board_order")):
        raise HTTPException(422, "required work fields cannot be null")
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
            allowed = {"status", "progress_percent", "blocked_reason", "note", "board_order"}
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


@router.get("/{item_id}/checklist")
def checklist(site_id: str, item_id: int, eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        if not cx.execute(text("SELECT 1 FROM work_items WHERE site_id=:site AND id=:item"),
                          {"site": site_id, "item": item_id}).first():
            raise HTTPException(404, "work item not found")
        rows = cx.execute(text("""SELECT id,site_id,work_item_id,title,done,actor_id,created_at,updated_at
            FROM work_checklist_items WHERE site_id=:site AND work_item_id=:item ORDER BY id"""),
            {"site": site_id, "item": item_id}).mappings().all()
    return [{**dict(row), "done": bool(row["done"])} for row in rows]


@router.post("/{item_id}/checklist", status_code=201)
def add_checklist_item(site_id: str, item_id: int, body: ChecklistIn, request: Request,
                       eng: Engine = Depends(engine)) -> dict:
    title = body.title.strip()
    if len(title) < 2:
        raise HTTPException(422, "checklist title is too short")
    with eng.begin() as cx:
        work = cx.execute(text("SELECT owner_id FROM work_items WHERE site_id=:site AND id=:item"),
                          {"site": site_id, "item": item_id}).mappings().first()
        if not work:
            raise HTTPException(404, "work item not found")
        require_assignee(cx, request, site_id, work["owner_id"])
        actor = getattr(request.state, "panel_user", None)
        result = cx.execute(text("""INSERT INTO work_checklist_items
            (site_id,work_item_id,title,done,actor_id,created_at,updated_at)
            VALUES (:site,:item,:title,0,:actor,:at,:at)"""),
            {"site": site_id, "item": item_id, "title": title,
             "actor": actor["id"] if actor else None, "at": now()})
        row = cx.execute(text("SELECT * FROM work_checklist_items WHERE id=:id"),
                         {"id": result.lastrowid}).mappings().one()
        _record(cx, site_id, item_id, "checklist_added", None, dict(row), None, actor)
    request.state.audit_fields = ["title"]
    return {**dict(row), "done": False}


@router.patch("/{item_id}/checklist/{checklist_id}")
def update_checklist_item(site_id: str, item_id: int, checklist_id: int, body: ChecklistPatch,
                          request: Request, eng: Engine = Depends(engine)) -> dict:
    with eng.begin() as cx:
        work = cx.execute(text("SELECT owner_id FROM work_items WHERE site_id=:site AND id=:item"),
                          {"site": site_id, "item": item_id}).mappings().first()
        if not work:
            raise HTTPException(404, "work item not found")
        require_assignee(cx, request, site_id, work["owner_id"])
        before = cx.execute(text("""SELECT * FROM work_checklist_items
            WHERE id=:id AND site_id=:site AND work_item_id=:item"""),
            {"id": checklist_id, "site": site_id, "item": item_id}).mappings().first()
        if not before:
            raise HTTPException(404, "checklist item not found")
        result = cx.execute(text("""UPDATE work_checklist_items SET done=:done,updated_at=:at
            WHERE id=:id AND site_id=:site AND work_item_id=:item"""),
            {"done": int(body.done), "at": now(), "id": checklist_id, "site": site_id, "item": item_id})
        if not result.rowcount:
            raise HTTPException(404, "checklist item not found")
        row = cx.execute(text("SELECT * FROM work_checklist_items WHERE id=:id"),
                         {"id": checklist_id}).mappings().one()
        _record(cx, site_id, item_id, "checklist_updated", dict(before), dict(row), None,
                getattr(request.state, "panel_user", None))
    request.state.audit_fields = ["done"]
    return {**dict(row), "done": bool(row["done"])}


@router.delete("/{item_id}/checklist/{checklist_id}", status_code=204)
def remove_checklist_item(site_id: str, item_id: int, checklist_id: int, request: Request,
                          eng: Engine = Depends(engine)) -> None:
    with eng.begin() as cx:
        require_lead(cx, request, site_id)
        before = cx.execute(text("""SELECT * FROM work_checklist_items
            WHERE id=:id AND site_id=:site AND work_item_id=:item"""),
            {"id": checklist_id, "site": site_id, "item": item_id}).mappings().first()
        if not before:
            raise HTTPException(404, "checklist item not found")
        result = cx.execute(text("""DELETE FROM work_checklist_items
            WHERE id=:id AND site_id=:site AND work_item_id=:item"""),
            {"id": checklist_id, "site": site_id, "item": item_id})
        if not result.rowcount:
            raise HTTPException(404, "checklist item not found")
        _record(cx, site_id, item_id, "checklist_removed", dict(before), {"id": checklist_id, "deleted": True},
                None, getattr(request.state, "panel_user", None))
    request.state.audit_fields = ["checklist_id"]


@router.get("/labels")
def project_labels(site_id: str, request: Request, eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        if project_responsibility(cx, request, site_id) == "none":
            raise HTTPException(403, "project membership is required")
        rows = cx.execute(text("SELECT id,site_id,name,color FROM work_labels WHERE site_id=:site ORDER BY name"),
                          {"site": site_id}).mappings().all()
    return [dict(row) for row in rows]


@router.post("/labels", status_code=201)
def create_project_label(site_id: str, body: LabelIn, request: Request, eng: Engine = Depends(engine)) -> dict:
    name = body.name.strip()
    if len(name) < 2:
        raise HTTPException(422, "label name is too short")
    try:
        with eng.begin() as cx:
            require_lead(cx, request, site_id)
            result = cx.execute(text("""INSERT INTO work_labels(site_id,name,color,created_at)
                VALUES (:site,:name,:color,:at)"""),
                {"site": site_id, "name": name, "color": body.color, "at": now()})
            row = cx.execute(text("SELECT id,site_id,name,color FROM work_labels WHERE id=:id"),
                             {"id": result.lastrowid}).mappings().one()
    except IntegrityError as exc:
        raise HTTPException(409, "label name already exists in this project") from exc
    request.state.audit_fields = ["name", "color"]
    return dict(row)


@router.delete("/labels/{label_id}", status_code=204)
def delete_project_label(site_id: str, label_id: int, request: Request, eng: Engine = Depends(engine)) -> None:
    with eng.begin() as cx:
        require_lead(cx, request, site_id)
        label = cx.execute(text("SELECT * FROM work_labels WHERE id=:id AND site_id=:site"),
                           {"id": label_id, "site": site_id}).mappings().first()
        if not label:
            raise HTTPException(404, "label not found")
        item_ids = [row[0] for row in cx.execute(text("""SELECT work_item_id FROM work_item_labels
            WHERE site_id=:site AND label_id=:id"""), {"site": site_id, "id": label_id}).all()]
        cx.execute(text("DELETE FROM work_item_labels WHERE site_id=:site AND label_id=:id"),
                   {"site": site_id, "id": label_id})
        cx.execute(text("DELETE FROM work_labels WHERE site_id=:site AND id=:id"),
                   {"site": site_id, "id": label_id})
        for item_id in item_ids:
            _record(cx, site_id, item_id, "label_removed", dict(label), {"deleted": True}, None,
                    getattr(request.state, "panel_user", None))
    request.state.audit_fields = ["label_id"]


@router.get("/{item_id}/labels")
def item_labels(site_id: str, item_id: int, request: Request, eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        if project_responsibility(cx, request, site_id) == "none":
            raise HTTPException(403, "project membership is required")
        if not cx.execute(text("SELECT 1 FROM work_items WHERE site_id=:site AND id=:item"),
                          {"site": site_id, "item": item_id}).first():
            raise HTTPException(404, "work item not found")
        rows = cx.execute(text("""SELECT l.id,l.site_id,l.name,l.color FROM work_item_labels il
            JOIN work_labels l ON l.id=il.label_id AND l.site_id=il.site_id
            WHERE il.site_id=:site AND il.work_item_id=:item ORDER BY l.name"""),
            {"site": site_id, "item": item_id}).mappings().all()
    return [dict(row) for row in rows]


@router.put("/{item_id}/labels/{label_id}")
def add_item_label(site_id: str, item_id: int, label_id: int, request: Request,
                   eng: Engine = Depends(engine)) -> dict:
    with eng.begin() as cx:
        work = cx.execute(text("SELECT owner_id FROM work_items WHERE site_id=:site AND id=:item"),
                          {"site": site_id, "item": item_id}).mappings().first()
        if not work:
            raise HTTPException(404, "work item not found")
        require_assignee(cx, request, site_id, work["owner_id"])
        label = cx.execute(text("SELECT id,site_id,name,color FROM work_labels WHERE site_id=:site AND id=:id"),
                           {"site": site_id, "id": label_id}).mappings().first()
        if not label:
            raise HTTPException(404, "label not found")
        exists = cx.execute(text("""SELECT 1 FROM work_item_labels WHERE site_id=:site
            AND work_item_id=:item AND label_id=:label"""),
            {"site": site_id, "item": item_id, "label": label_id}).first()
        if not exists:
            cx.execute(text("""INSERT INTO work_item_labels(site_id,work_item_id,label_id,created_at)
                VALUES (:site,:item,:label,:at)"""),
                {"site": site_id, "item": item_id, "label": label_id, "at": now()})
            _record(cx, site_id, item_id, "label_added", None, dict(label), None,
                    getattr(request.state, "panel_user", None))
    request.state.audit_fields = ["label_id"]
    return dict(label)


@router.delete("/{item_id}/labels/{label_id}", status_code=204)
def remove_item_label(site_id: str, item_id: int, label_id: int, request: Request,
                      eng: Engine = Depends(engine)) -> None:
    with eng.begin() as cx:
        work = cx.execute(text("SELECT owner_id FROM work_items WHERE site_id=:site AND id=:item"),
                          {"site": site_id, "item": item_id}).mappings().first()
        if not work:
            raise HTTPException(404, "work item not found")
        require_assignee(cx, request, site_id, work["owner_id"])
        label = cx.execute(text("SELECT id,site_id,name,color FROM work_labels WHERE site_id=:site AND id=:id"),
                           {"site": site_id, "id": label_id}).mappings().first()
        if not label:
            raise HTTPException(404, "label not found")
        result = cx.execute(text("""DELETE FROM work_item_labels WHERE site_id=:site
            AND work_item_id=:item AND label_id=:label"""),
            {"site": site_id, "item": item_id, "label": label_id})
        if not result.rowcount:
            raise HTTPException(404, "label is not on this work item")
        _record(cx, site_id, item_id, "label_removed", dict(label), {"removed": True}, None,
                getattr(request.state, "panel_user", None))
    request.state.audit_fields = ["label_id"]


def _custom_field(row) -> dict:
    return {"id": row["id"], "site_id": row["site_id"], "name": row["name"],
            "field_type": row["field_type"], "options": json.loads(row["options_json"])}


@router.get("/fields")
def project_fields(site_id: str, request: Request, eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        if project_responsibility(cx, request, site_id) == "none":
            raise HTTPException(403, "project membership is required")
        rows = cx.execute(text("""SELECT * FROM work_custom_fields
            WHERE site_id=:site ORDER BY id"""), {"site": site_id}).mappings().all()
    return [_custom_field(row) for row in rows]


@router.post("/fields", status_code=201)
def create_project_field(site_id: str, body: CustomFieldIn, request: Request,
                         eng: Engine = Depends(engine)) -> dict:
    name = body.name.strip()
    options = [option.strip() for option in body.options]
    if (len(name) < 2 or (body.field_type == "select" and not options) or
            (body.field_type != "select" and options) or any(not option or len(option) > 80 for option in options) or
            len(set(options)) != len(options)):
        raise HTTPException(422, "invalid custom field name or options")
    try:
        with eng.begin() as cx:
            require_lead(cx, request, site_id)
            result = cx.execute(text("""INSERT INTO work_custom_fields
                (site_id,name,field_type,options_json,created_at)
                VALUES (:site,:name,:kind,:options,:at)"""),
                {"site": site_id, "name": name, "kind": body.field_type,
                 "options": json.dumps(options, ensure_ascii=False), "at": now()})
            row = cx.execute(text("SELECT * FROM work_custom_fields WHERE id=:id"),
                             {"id": result.lastrowid}).mappings().one()
    except IntegrityError as exc:
        raise HTTPException(409, "custom field name already exists in this project") from exc
    request.state.audit_fields = ["name", "field_type", "options"]
    return _custom_field(row)


@router.delete("/fields/{field_id}", status_code=204)
def delete_project_field(site_id: str, field_id: int, request: Request,
                         eng: Engine = Depends(engine)) -> None:
    with eng.begin() as cx:
        require_lead(cx, request, site_id)
        field = cx.execute(text("SELECT * FROM work_custom_fields WHERE id=:id AND site_id=:site"),
                           {"id": field_id, "site": site_id}).mappings().first()
        if not field:
            raise HTTPException(404, "custom field not found")
        cx.execute(text("DELETE FROM work_custom_values WHERE site_id=:site AND field_id=:id"),
                   {"site": site_id, "id": field_id})
        cx.execute(text("DELETE FROM work_custom_fields WHERE site_id=:site AND id=:id"),
                   {"site": site_id, "id": field_id})
    request.state.audit_fields = ["field_id"]


@router.get("/{item_id}/fields")
def item_fields(site_id: str, item_id: int, request: Request, eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        if project_responsibility(cx, request, site_id) == "none":
            raise HTTPException(403, "project membership is required")
        if not cx.execute(text("SELECT 1 FROM work_items WHERE site_id=:site AND id=:item"),
                          {"site": site_id, "item": item_id}).first():
            raise HTTPException(404, "work item not found")
        rows = cx.execute(text("""SELECT f.*,v.value_json FROM work_custom_fields f
            LEFT JOIN work_custom_values v ON v.field_id=f.id AND v.work_item_id=:item AND v.site_id=:site
            WHERE f.site_id=:site ORDER BY f.id"""),
            {"site": site_id, "item": item_id}).mappings().all()
    return [{**_custom_field(row), "value": json.loads(row["value_json"]) if row["value_json"] is not None else None}
            for row in rows]


@router.put("/{item_id}/fields/{field_id}")
def set_item_field(site_id: str, item_id: int, field_id: int, body: CustomValueIn,
                   request: Request, eng: Engine = Depends(engine)) -> dict:
    with eng.begin() as cx:
        work = cx.execute(text("SELECT owner_id FROM work_items WHERE site_id=:site AND id=:item"),
                          {"site": site_id, "item": item_id}).mappings().first()
        if not work:
            raise HTTPException(404, "work item not found")
        require_assignee(cx, request, site_id, work["owner_id"])
        field = cx.execute(text("SELECT * FROM work_custom_fields WHERE site_id=:site AND id=:id"),
                           {"site": site_id, "id": field_id}).mappings().first()
        if not field:
            raise HTTPException(404, "custom field not found")
        value = body.value
        kind = field["field_type"]
        if value is not None:
            if kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float)) or
                                     not math.isfinite(value)):
                raise HTTPException(422, "number field requires a finite number")
            if kind == "date" and (not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)):
                raise HTTPException(422, "date field requires YYYY-MM-DD")
            if kind == "date":
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise HTTPException(422, "invalid calendar date") from exc
            if kind == "select" and value not in json.loads(field["options_json"]):
                raise HTTPException(422, "value is not a field option")
            if kind == "text" and (not isinstance(value, str) or len(value) > 2048):
                raise HTTPException(422, "text field requires up to 2048 characters")
        before_row = cx.execute(text("""SELECT value_json FROM work_custom_values
            WHERE site_id=:site AND work_item_id=:item AND field_id=:field"""),
            {"site": site_id, "item": item_id, "field": field_id}).first()
        before = json.loads(before_row[0]) if before_row else None
        if value is None:
            cx.execute(text("""DELETE FROM work_custom_values
                WHERE site_id=:site AND work_item_id=:item AND field_id=:field"""),
                {"site": site_id, "item": item_id, "field": field_id})
        else:
            cx.execute(text("""INSERT INTO work_custom_values
                (site_id,work_item_id,field_id,value_json,updated_at)
                VALUES (:site,:item,:field,:value,:at)
                ON CONFLICT(field_id,work_item_id) DO UPDATE SET value_json=excluded.value_json,
                    updated_at=excluded.updated_at"""),
                {"site": site_id, "item": item_id, "field": field_id,
                 "value": json.dumps(value, ensure_ascii=False), "at": now()})
        if before != value:
            _record(cx, site_id, item_id, "field_updated", {"field_id": field_id, "value": before},
                    {"field_id": field_id, "value": value}, None,
                    getattr(request.state, "panel_user", None))
    request.state.audit_fields = ["field_id", "value"]
    return {**_custom_field(field), "value": value}
