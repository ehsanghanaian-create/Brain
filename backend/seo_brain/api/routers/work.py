"""Site-scoped action ledger for SEO work; individual API authentication is a later gate."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from ..deps import engine, require_site

router = APIRouter(prefix="/sites/{site_id}/work", tags=["work"], dependencies=[Depends(require_site)])
Kind = Literal["manual", "issue", "opportunity", "content"]
Status = Literal["new", "triaged", "approved", "assigned", "in_progress", "review", "published",
                 "measurement_pending", "verified", "blocked", "rejected", "deferred"]
ACTIVE = {"approved", "assigned", "in_progress", "review", "published", "measurement_pending", "verified", "blocked"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _due_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(422, "due date must include a timezone")
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
    due_at: datetime | None = None
    blocked_reason: str | None = Field(default=None, max_length=1000)
    verification_note: str | None = Field(default=None, max_length=3000)
    note: str | None = Field(default=None, max_length=1000)


def _record(cx, site_id: str, item_id: int, event_type: str, before: dict | None,
            after: dict, note: str | None) -> None:
    cx.execute(text("""INSERT INTO work_item_events
        (site_id,work_item_id,event_type,before_json,after_json,note,created_at)
        VALUES (:s,:id,:event,:before,:after,:note,:at)"""),
        {"s": site_id, "id": item_id, "event": event_type,
         "before": json.dumps(before, ensure_ascii=False) if before else None,
         "after": json.dumps(after, ensure_ascii=False), "note": note, "at": now()})


def _validate(cx, site_id: str, values: dict) -> None:
    if values.get("status") in ACTIVE and (not values.get("owner_id") or not values.get("due_at")):
        raise HTTPException(422, "active work requires an owner and due date")
    if values.get("status") == "blocked" and not values.get("blocked_reason"):
        raise HTTPException(422, "blocked work requires a reason")
    if values.get("status") == "verified" and not values.get("verification_note"):
        raise HTTPException(422, "verified work requires a verification note")
    if values.get("owner_id") is not None:
        exists = cx.execute(text("SELECT 1 FROM panel_users WHERE id=:id AND active=1"),
                            {"id": values["owner_id"]}).first()
        if not exists:
            raise HTTPException(422, "owner must be an active panel user")
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
        rows = cx.execute(text(f"""SELECT w.*, u.full_name AS owner_name FROM work_items w
            LEFT JOIN panel_users u ON u.id=w.owner_id WHERE {where}
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
def create_work(site_id: str, body: WorkIn, eng: Engine = Depends(engine)) -> dict:
    if body.status in ("rejected", "deferred") and not body.note:
        raise HTTPException(422, "rejected or deferred work requires a reason")
    values = body.model_dump(exclude={"note"})
    values["due_at"] = _due_utc(body.due_at)
    values.update(site_id=site_id, created_at=now(), updated_at=now())
    try:
        with eng.begin() as cx:
            _validate(cx, site_id, values)
            cols = list(values)
            result = cx.execute(text(f"INSERT INTO work_items({','.join(cols)}) VALUES({','.join(':'+c for c in cols)})"), values)
            item_id = result.lastrowid
            row = dict(cx.execute(text("SELECT * FROM work_items WHERE site_id=:s AND id=:id"),
                                  {"s": site_id, "id": item_id}).mappings().one())
            _record(cx, site_id, item_id, "created", None, row, body.note)
    except IntegrityError as exc:
        raise HTTPException(409, "work already exists for this source") from exc
    return row


@router.patch("/{item_id}")
def update_work(site_id: str, item_id: int, body: WorkPatch, eng: Engine = Depends(engine)) -> dict:
    patch = body.model_dump(exclude_unset=True, exclude={"note"})
    if any(key in patch and patch[key] is None for key in ("title", "description", "status")):
        raise HTTPException(422, "title, description and status cannot be null")
    if "due_at" in patch:
        patch["due_at"] = _due_utc(patch["due_at"])
    with eng.begin() as cx:
        current = cx.execute(text("SELECT * FROM work_items WHERE site_id=:s AND id=:id"),
                             {"s": site_id, "id": item_id}).mappings().first()
        if not current:
            raise HTTPException(404, "work item not found")
        before = dict(current)
        merged = {**before, **patch}
        if patch.get("status") in ("rejected", "deferred") and patch["status"] != before["status"] and not body.note:
            raise HTTPException(422, "rejected or deferred work requires a reason")
        _validate(cx, site_id, merged)
        if merged == before:
            return before
        patch["updated_at"] = now()
        cx.execute(text("UPDATE work_items SET " + ",".join(f"{key}=:{key}" for key in patch) +
                        " WHERE site_id=:s AND id=:id"), {**patch, "s": site_id, "id": item_id})
        after = dict(cx.execute(text("SELECT * FROM work_items WHERE site_id=:s AND id=:id"),
                                {"s": site_id, "id": item_id}).mappings().one())
        _record(cx, site_id, item_id, "updated", before, after, body.note)
    return after


@router.get("/{item_id}/events")
def work_events(site_id: str, item_id: int, eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        if not cx.execute(text("SELECT 1 FROM work_items WHERE site_id=:s AND id=:id"),
                          {"s": site_id, "id": item_id}).first():
            raise HTTPException(404, "work item not found")
        rows = cx.execute(text("""SELECT id,event_type,before_json,after_json,note,created_at
            FROM work_item_events WHERE site_id=:s AND work_item_id=:id ORDER BY id"""),
            {"s": site_id, "id": item_id}).mappings().all()
    return [dict(row) for row in rows]
