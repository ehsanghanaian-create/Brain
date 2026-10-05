"""Cross-site work command center and team directory."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from ..deps import engine

router = APIRouter(prefix="/work", tags=["work-command-center"])
CLOSED = ("verified", "rejected", "deferred")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TeamIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    color: str = Field(default="#1abb9c", pattern=r"^#[0-9a-fA-F]{6}$")


class TeamPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    active: bool | None = None


@router.get("/teams")
def teams(eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        rows = cx.execute(text("""SELECT t.*, COUNT(DISTINCT u.id) AS members,
            COUNT(DISTINCT CASE WHEN w.status NOT IN ('verified','rejected','deferred') THEN w.id END) AS open_work
            FROM panel_teams t LEFT JOIN panel_users u ON u.team_id=t.id AND u.active=1
            LEFT JOIN work_items w ON w.team_id=t.id
            GROUP BY t.id ORDER BY t.active DESC, t.name""")).mappings().all()
    return [{**dict(row), "active": bool(row["active"])} for row in rows]


@router.post("/teams", status_code=201)
def create_team(body: TeamIn, request: Request, eng: Engine = Depends(engine)) -> dict:
    values = body.model_dump()
    values["name"] = values["name"].strip()
    if len(values["name"]) < 2:
        raise HTTPException(422, "team name is too short")
    try:
        with eng.begin() as cx:
            result = cx.execute(text("""INSERT INTO panel_teams(name,color,description,active,created_at,updated_at)
                VALUES (:name,:color,:description,1,:at,:at)"""), {**values, "at": now()})
            row = cx.execute(text("SELECT * FROM panel_teams WHERE id=:id"), {"id": result.lastrowid}).mappings().one()
    except IntegrityError as exc:
        raise HTTPException(409, "team name already exists") from exc
    request.state.audit_fields = list(body.model_fields_set)
    return dict(row)


@router.patch("/teams/{team_id}")
def update_team(team_id: int, body: TeamPatch, request: Request, eng: Engine = Depends(engine)) -> dict:
    values = body.model_dump(exclude_unset=True)
    if not values or any(value is None for value in values.values()):
        raise HTTPException(422, "team changes are required")
    if "name" in values:
        values["name"] = values["name"].strip()
        if len(values["name"]) < 2:
            raise HTTPException(422, "team name is too short")
    if "active" in values:
        values["active"] = int(values["active"])
    try:
        with eng.begin() as cx:
            if not cx.execute(text("SELECT 1 FROM panel_teams WHERE id=:id"), {"id": team_id}).first():
                raise HTTPException(404, "team not found")
            cx.execute(text("UPDATE panel_teams SET " + ",".join(f"{key}=:{key}" for key in values) +
                            ",updated_at=:at WHERE id=:id"), {**values, "id": team_id, "at": now()})
            row = cx.execute(text("SELECT * FROM panel_teams WHERE id=:id"), {"id": team_id}).mappings().one()
    except IntegrityError as exc:
        raise HTTPException(409, "team name already exists") from exc
    request.state.audit_fields = list(values)
    return {**dict(row), "active": bool(row["active"])}


@router.get("/overview")
def overview(site_id: str | None = None, owner_id: int | None = None, team_id: int | None = None,
             status: str | None = None, priority: str | None = None, q: str | None = None,
             limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0),
             eng: Engine = Depends(engine)) -> dict:
    clauses = ["1=1"]
    args: dict = {"now": now(), "lim": limit, "off": offset}
    for key, value in (("site_id", site_id), ("owner_id", owner_id), ("team_id", team_id),
                       ("status", status), ("priority", priority)):
        if value is not None and value != "":
            clauses.append(f"w.{key}=:{key}")
            args[key] = value
    if q:
        clauses.append("(w.title LIKE :q OR w.description LIKE :q OR w.url LIKE :q OR w.query LIKE :q)")
        args["q"] = "%" + q.strip() + "%"
    where = " AND ".join(clauses)
    base = f"FROM work_items w LEFT JOIN sites s ON s.site_id=w.site_id " \
           f"LEFT JOIN panel_users u ON u.id=w.owner_id LEFT JOIN panel_teams t ON t.id=w.team_id WHERE {where}"
    with eng.connect() as cx:
        summary = cx.execute(text(f"""SELECT COUNT(*) AS total,
            SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') THEN 1 ELSE 0 END) AS open,
            SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') AND w.due_at<:now THEN 1 ELSE 0 END) AS overdue,
            SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') AND w.owner_id IS NULL THEN 1 ELSE 0 END) AS unassigned,
            SUM(CASE WHEN w.status='blocked' THEN 1 ELSE 0 END) AS blocked,
            SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') AND w.due_at>=:now AND w.due_at<:week_end THEN 1 ELSE 0 END) AS due_week,
            COALESCE(SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') THEN w.estimated_hours ELSE 0 END),0) AS hours_open
            {base}"""), {**args, "week_end": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds")}).mappings().one()
        rows = cx.execute(text(f"""SELECT w.*, s.name AS site_name, u.full_name AS owner_name,
            t.name AS team_name, t.color AS team_color,
            (SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id) AS checklist_total,
            (SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id AND ci.done=1) AS checklist_done {base}
            ORDER BY CASE WHEN w.status='blocked' THEN 0 WHEN w.status NOT IN ('verified','rejected','deferred') AND w.due_at<:now THEN 1 ELSE 2 END,
            CASE w.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
            w.due_at, w.id DESC LIMIT :lim OFFSET :off"""), args).mappings().all()
        by_status = cx.execute(text(f"SELECT w.status AS key, COUNT(*) AS count {base} GROUP BY w.status"), args).mappings().all()
        by_site = cx.execute(text(f"""SELECT w.site_id AS key, s.name AS name, COUNT(*) AS total,
            SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') THEN 1 ELSE 0 END) AS open,
            SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') AND w.due_at<:now THEN 1 ELSE 0 END) AS overdue,
            SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') AND w.owner_id IS NULL THEN 1 ELSE 0 END) AS unassigned
            {base} GROUP BY w.site_id ORDER BY open DESC"""), args).mappings().all()
        by_owner = cx.execute(text(f"""SELECT w.owner_id AS key, COALESCE(u.full_name,'بی‌مسئول') AS name,
            COUNT(*) AS total, SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') THEN 1 ELSE 0 END) AS open,
            SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') AND w.due_at<:now THEN 1 ELSE 0 END) AS overdue,
            COALESCE(SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') THEN w.estimated_hours ELSE 0 END),0) AS hours_open
            {base} GROUP BY w.owner_id ORDER BY open DESC"""), args).mappings().all()
        by_team = cx.execute(text(f"""SELECT w.team_id AS key, COALESCE(t.name,'بدون تیم') AS name,
            COUNT(*) AS total, SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') THEN 1 ELSE 0 END) AS open,
            SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') AND w.due_at<:now THEN 1 ELSE 0 END) AS overdue
            {base} GROUP BY w.team_id ORDER BY open DESC"""), args).mappings().all()
        due_days = cx.execute(text(f"""SELECT substr(w.due_at,1,10) AS day, COUNT(*) AS count {base}
            AND w.status NOT IN ('verified','rejected','deferred') AND w.due_at>=:today AND w.due_at<:end
            GROUP BY substr(w.due_at,1,10) ORDER BY day"""), {**args, "today": datetime.now(timezone.utc).date().isoformat(),
              "end": (datetime.now(timezone.utc).date() + timedelta(days=21)).isoformat()}).mappings().all()
        recent = cx.execute(text("""SELECT e.id,e.site_id,e.work_item_id,e.event_type,e.note,e.actor_username,e.created_at,
            w.title, s.name AS site_name FROM work_item_events e
            JOIN work_items w ON w.id=e.work_item_id JOIN sites s ON s.site_id=e.site_id
            ORDER BY e.id DESC LIMIT 12""")).mappings().all()
    return {"summary": {k: (float(v or 0) if k == "hours_open" else int(v or 0)) for k, v in summary.items()},
            "items": [dict(row) for row in rows], "limit": limit, "offset": offset,
            "by_status": [dict(row) for row in by_status],
            "by_site": [{k: int(v or 0) if k in {"total", "open", "overdue", "unassigned"} else v for k, v in row.items()} for row in by_site],
            "by_owner": [{k: (float(v or 0) if k == "hours_open" else int(v or 0)) if k in {"total", "open", "overdue", "hours_open"} else v for k, v in row.items()} for row in by_owner],
            "by_team": [{k: int(v or 0) if k in {"total", "open", "overdue"} else v for k, v in row.items()} for row in by_team],
            "due_days": [dict(row) for row in due_days], "recent": [dict(row) for row in recent]}
