"""Site project assignments, milestones, dependencies and time evidence."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from ..deps import engine
from ..project_access import require_assignee, require_lead
from .work import _date_utc, now

router = APIRouter(prefix="/work/projects", tags=["project-execution"])


def _site(cx, site_id: str) -> None:
    if not cx.execute(text("SELECT 1 FROM sites WHERE site_id=:s"), {"s": site_id}).first():
        raise HTTPException(404, "site project not found")


def _item(cx, site_id: str, item_id: int) -> dict:
    row = cx.execute(text("SELECT * FROM work_items WHERE site_id=:s AND id=:id"),
                     {"s": site_id, "id": item_id}).mappings().first()
    if not row:
        raise HTTPException(404, "work item not found in this project")
    return dict(row)


class AssignmentIn(BaseModel):
    user_id: int = Field(ge=1)
    responsibility: Literal["lead", "contributor", "viewer"] = "contributor"


class MilestoneIn(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=3000)
    due_at: datetime | None = None


class MilestonePatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=3000)
    due_at: datetime | None = None


class DependencyIn(BaseModel):
    depends_on_id: int = Field(ge=1)


class TimeIn(BaseModel):
    user_id: int = Field(ge=1)
    minutes: int = Field(ge=1, le=1440)
    work_date: date
    note: str = Field(default="", max_length=1000)


@router.get("")
def list_projects(request: Request, eng: Engine = Depends(engine)) -> list[dict]:
    """Progress counts leaf work once and uses saved progress, never synthetic traffic metrics."""
    with eng.connect() as cx:
        rows = cx.execute(text("""SELECT s.site_id,s.name,s.canonical_url,
            COUNT(DISTINCT a.user_id) AS members,
            COUNT(DISTINCT w.id) AS tasks,
            COUNT(DISTINCT CASE WHEN w.status NOT IN ('verified','rejected','deferred') THEN w.id END) AS open_tasks,
            COUNT(DISTINCT CASE WHEN w.status='blocked' THEN w.id END) AS blocked_tasks,
            COUNT(DISTINCT CASE WHEN w.status NOT IN ('verified','rejected','deferred') AND w.owner_id IS NULL THEN w.id END) AS unassigned_tasks,
            COUNT(DISTINCT CASE WHEN w.status NOT IN ('verified','rejected','deferred') AND w.due_at<:at THEN w.id END) AS overdue_tasks
            FROM sites s LEFT JOIN site_assignments a ON a.site_id=s.site_id
            LEFT JOIN work_items w ON w.site_id=s.site_id
            GROUP BY s.site_id ORDER BY s.name"""), {"at": now()}).mappings().all()
        progress = cx.execute(text("""SELECT w.site_id,
            COALESCE(SUM(CASE WHEN w.status='verified' THEN 100 ELSE w.progress_percent END *
                CASE WHEN w.estimated_hours>0 THEN w.estimated_hours ELSE 1 END) /
                NULLIF(SUM(CASE WHEN w.estimated_hours>0 THEN w.estimated_hours ELSE 1 END),0),0) AS progress_percent,
            COALESCE(SUM(w.estimated_hours),0) AS estimated_hours
            FROM work_items w WHERE w.status NOT IN ('rejected','deferred')
                AND NOT EXISTS (SELECT 1 FROM work_items child WHERE child.parent_id=w.id)
            GROUP BY w.site_id""")).mappings().all()
        spent = cx.execute(text("SELECT site_id,COALESCE(SUM(minutes),0) AS minutes FROM work_time_entries GROUP BY site_id")).mappings().all()
        milestones = cx.execute(text("SELECT site_id,COUNT(*) AS count FROM work_milestones GROUP BY site_id")).mappings().all()
        actor = getattr(request.state, "panel_user", None)
        assignments = cx.execute(text("SELECT site_id,responsibility FROM site_assignments WHERE user_id=:id"),
                                 {"id": actor["id"]}).mappings().all() if actor else []
    by_progress = {row["site_id"]: row for row in progress}
    by_spent = {row["site_id"]: row["minutes"] for row in spent}
    by_milestone = {row["site_id"]: row["count"] for row in milestones}
    my_roles = {row["site_id"]: row["responsibility"] for row in assignments}
    return [{**dict(row), "progress_percent": round(float(by_progress[row["site_id"]]["progress_percent"] or 0), 1) if row["site_id"] in by_progress else 0,
             "estimated_hours": float(by_progress[row["site_id"]]["estimated_hours"] or 0) if row["site_id"] in by_progress else 0,
             "spent_hours": round(by_spent.get(row["site_id"], 0) / 60, 2),
             "milestones": by_milestone.get(row["site_id"], 0),
             "my_responsibility": "admin" if not actor or actor["role"] == "admin" else my_roles.get(row["site_id"])} for row in rows]


@router.get("/{site_id}/members")
def members(site_id: str, eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        _site(cx, site_id)
        rows = cx.execute(text("""SELECT a.site_id,a.user_id,a.responsibility,a.created_at,
            u.full_name,u.username,u.role,u.active FROM site_assignments a
            JOIN panel_users u ON u.id=a.user_id WHERE a.site_id=:s ORDER BY a.responsibility,u.full_name"""),
            {"s": site_id}).mappings().all()
    return [dict(row) for row in rows]


@router.put("/{site_id}/members/{user_id}")
def assign_member(site_id: str, user_id: int, body: AssignmentIn, request: Request,
                  eng: Engine = Depends(engine)) -> dict:
    if body.user_id != user_id:
        raise HTTPException(422, "user id mismatch")
    with eng.begin() as cx:
        _site(cx, site_id)
        member_role = cx.execute(text("SELECT role FROM panel_users WHERE id=:id AND active=1"),
                                 {"id": user_id}).scalar_one_or_none()
        if not member_role:
            raise HTTPException(422, "member must be an active panel user")
        if member_role == "call_center" and body.responsibility != "viewer":
            raise HTTPException(422, "call center operators cannot execute SEO project work")
        cx.execute(text("""INSERT INTO site_assignments(site_id,user_id,responsibility,created_at)
            VALUES (:s,:id,:role,:at) ON CONFLICT(site_id,user_id)
            DO UPDATE SET responsibility=excluded.responsibility"""),
            {"s": site_id, "id": user_id, "role": body.responsibility, "at": now()})
        row = cx.execute(text("SELECT * FROM site_assignments WHERE site_id=:s AND user_id=:id"),
                         {"s": site_id, "id": user_id}).mappings().one()
    request.state.audit_fields = ["site_id", "user_id", "responsibility"]
    return dict(row)


@router.delete("/{site_id}/members/{user_id}", status_code=204)
def remove_member(site_id: str, user_id: int, request: Request, eng: Engine = Depends(engine)) -> None:
    with eng.begin() as cx:
        result = cx.execute(text("DELETE FROM site_assignments WHERE site_id=:s AND user_id=:id"),
                            {"s": site_id, "id": user_id})
        if result.rowcount == 0:
            raise HTTPException(404, "project member not found")
    request.state.audit_fields = ["site_id", "user_id"]


@router.get("/{site_id}/milestones")
def list_milestones(site_id: str, eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        _site(cx, site_id)
        rows = cx.execute(text("""SELECT m.*,COUNT(w.id) AS tasks,
            SUM(CASE WHEN w.status='verified' THEN 1 ELSE 0 END) AS verified_tasks
            FROM work_milestones m LEFT JOIN work_items w ON w.milestone_id=m.id
            WHERE m.site_id=:s GROUP BY m.id ORDER BY m.due_at,m.id"""), {"s": site_id}).mappings().all()
    return [{**dict(row), "verified_tasks": int(row["verified_tasks"] or 0)} for row in rows]


@router.post("/{site_id}/milestones", status_code=201)
def create_milestone(site_id: str, body: MilestoneIn, request: Request, eng: Engine = Depends(engine)) -> dict:
    values = body.model_dump()
    values["title"] = values["title"].strip()
    if len(values["title"]) < 2:
        raise HTTPException(422, "milestone title is too short")
    values["due_at"] = _date_utc(body.due_at, "milestone due date")
    with eng.begin() as cx:
        _site(cx, site_id)
        require_lead(cx, request, site_id)
        result = cx.execute(text("""INSERT INTO work_milestones(site_id,title,description,due_at,created_at,updated_at)
            VALUES (:s,:title,:description,:due_at,:at,:at)"""), {**values, "s": site_id, "at": now()})
        row = cx.execute(text("SELECT * FROM work_milestones WHERE id=:id"), {"id": result.lastrowid}).mappings().one()
    request.state.audit_fields = list(body.model_fields_set)
    return dict(row)


@router.patch("/{site_id}/milestones/{milestone_id}")
def update_milestone(site_id: str, milestone_id: int, body: MilestonePatch, request: Request,
                     eng: Engine = Depends(engine)) -> dict:
    values = body.model_dump(exclude_unset=True)
    if not values or any(value is None for key, value in values.items() if key != "due_at"):
        raise HTTPException(422, "milestone changes are required")
    if "title" in values:
        values["title"] = values["title"].strip()
        if len(values["title"]) < 2:
            raise HTTPException(422, "milestone title is too short")
    if "due_at" in values:
        values["due_at"] = _date_utc(body.due_at, "milestone due date")
    with eng.begin() as cx:
        require_lead(cx, request, site_id)
        if not cx.execute(text("SELECT 1 FROM work_milestones WHERE id=:id AND site_id=:s"),
                          {"id": milestone_id, "s": site_id}).first():
            raise HTTPException(404, "milestone not found")
        cx.execute(text("UPDATE work_milestones SET " + ",".join(f"{key}=:{key}" for key in values) +
                        ",updated_at=:at WHERE id=:id AND site_id=:s"),
                   {**values, "at": now(), "id": milestone_id, "s": site_id})
        row = cx.execute(text("SELECT * FROM work_milestones WHERE id=:id"), {"id": milestone_id}).mappings().one()
    request.state.audit_fields = list(values)
    return dict(row)


@router.get("/{site_id}/tasks/{item_id}/dependencies")
def dependencies(site_id: str, item_id: int, eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        _item(cx, site_id, item_id)
        rows = cx.execute(text("""SELECT d.depends_on_id,w.title,w.status,d.created_at
            FROM work_dependencies d JOIN work_items w ON w.id=d.depends_on_id
            WHERE d.work_item_id=:id ORDER BY d.created_at"""), {"id": item_id}).mappings().all()
    return [dict(row) for row in rows]


@router.post("/{site_id}/tasks/{item_id}/dependencies", status_code=201)
def add_dependency(site_id: str, item_id: int, body: DependencyIn, request: Request,
                   eng: Engine = Depends(engine)) -> dict:
    with eng.begin() as cx:
        _item(cx, site_id, item_id)
        require_lead(cx, request, site_id)
        _item(cx, site_id, body.depends_on_id)
        if item_id == body.depends_on_id:
            raise HTTPException(422, "work cannot depend on itself")
        cycle = cx.execute(text("""WITH RECURSIVE chain(id) AS (
            SELECT :dependency UNION SELECT d.depends_on_id FROM work_dependencies d
            JOIN chain c ON d.work_item_id=c.id)
            SELECT 1 FROM chain WHERE id=:item LIMIT 1"""),
            {"dependency": body.depends_on_id, "item": item_id}).first()
        if cycle:
            raise HTTPException(422, "dependency would create a cycle")
        try:
            cx.execute(text("""INSERT INTO work_dependencies(work_item_id,depends_on_id,created_at)
                VALUES (:item,:dependency,:at)"""),
                {"item": item_id, "dependency": body.depends_on_id, "at": now()})
        except IntegrityError as exc:
            raise HTTPException(409, "dependency already exists") from exc
    request.state.audit_fields = ["depends_on_id"]
    return {"work_item_id": item_id, "depends_on_id": body.depends_on_id}


@router.delete("/{site_id}/tasks/{item_id}/dependencies/{depends_on_id}", status_code=204)
def remove_dependency(site_id: str, item_id: int, depends_on_id: int, request: Request,
                      eng: Engine = Depends(engine)) -> None:
    with eng.begin() as cx:
        _item(cx, site_id, item_id)
        require_lead(cx, request, site_id)
        result = cx.execute(text("DELETE FROM work_dependencies WHERE work_item_id=:id AND depends_on_id=:dep"),
                            {"id": item_id, "dep": depends_on_id})
        if result.rowcount == 0:
            raise HTTPException(404, "dependency not found")
    request.state.audit_fields = ["depends_on_id"]


@router.get("/{site_id}/tasks/{item_id}/time")
def time_entries(site_id: str, item_id: int, eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        _item(cx, site_id, item_id)
        rows = cx.execute(text("""SELECT e.*,u.full_name AS user_name FROM work_time_entries e
            JOIN panel_users u ON u.id=e.user_id WHERE e.site_id=:s AND e.work_item_id=:id
            ORDER BY e.work_date DESC,e.id DESC"""), {"s": site_id, "id": item_id}).mappings().all()
    return [dict(row) for row in rows]


@router.post("/{site_id}/tasks/{item_id}/time", status_code=201)
def log_time(site_id: str, item_id: int, body: TimeIn, request: Request,
             eng: Engine = Depends(engine)) -> dict:
    with eng.begin() as cx:
        item = _item(cx, site_id, item_id)
        require_assignee(cx, request, site_id, item["owner_id"])
        actor = getattr(request.state, "panel_user", None)
        if actor and actor["role"] != "admin" and body.user_id != actor["id"]:
            raise HTTPException(403, "time can only be logged for the signed-in user")
        if not cx.execute(text("SELECT 1 FROM panel_users WHERE id=:id AND active=1"), {"id": body.user_id}).first():
            raise HTTPException(422, "time owner must be active")
        values = {**body.model_dump(), "work_date": body.work_date.isoformat(), "s": site_id,
                  "item": item_id, "actor": actor["id"] if actor else None, "at": now()}
        result = cx.execute(text("""INSERT INTO work_time_entries(site_id,work_item_id,user_id,minutes,work_date,note,actor_id,created_at)
            VALUES (:s,:item,:user_id,:minutes,:work_date,:note,:actor,:at)"""), values)
        row = cx.execute(text("SELECT * FROM work_time_entries WHERE id=:id"), {"id": result.lastrowid}).mappings().one()
    request.state.audit_fields = ["user_id", "minutes", "work_date", "note"]
    return dict(row)
