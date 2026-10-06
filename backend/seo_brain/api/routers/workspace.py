"""Cross-site work command center and team directory."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from ..deps import engine
from ..project_access import project_responsibility

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


class SavedViewConfig(BaseModel):
    query: str = Field(default="", max_length=200)
    owner_filter: str = Field(default="", max_length=20)
    priority_filter: Literal["", "critical", "high", "normal", "low"] = ""
    label_id: int | None = Field(default=None, ge=1)
    mine: bool = False
    group_by: Literal["status", "owner", "priority"] = "status"


class SavedViewIn(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    config: SavedViewConfig


def _view_actor(cx, request: Request, site_id: str) -> int:
    actor = getattr(request.state, "panel_user", None)
    if not actor:
        raise HTTPException(401, "sign in to manage saved views")
    if project_responsibility(cx, request, site_id) == "none":
        raise HTTPException(403, "project membership is required")
    if not cx.execute(text("SELECT 1 FROM sites WHERE site_id=:site"), {"site": site_id}).first():
        raise HTTPException(404, "site not found")
    return actor["id"]


@router.get("/views/{site_id}")
def saved_views(site_id: str, request: Request, eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        user_id = _view_actor(cx, request, site_id)
        rows = cx.execute(text("""SELECT id,site_id,name,config_json,created_at,updated_at
            FROM work_saved_views WHERE user_id=:user AND site_id=:site ORDER BY name"""),
            {"user": user_id, "site": site_id}).mappings().all()
    return [{**{key: value for key, value in row.items() if key != "config_json"},
             "config": json.loads(row["config_json"])} for row in rows]


@router.post("/views/{site_id}", status_code=201)
def create_saved_view(site_id: str, body: SavedViewIn, request: Request,
                      eng: Engine = Depends(engine)) -> dict:
    name = body.name.strip()
    if len(name) < 2:
        raise HTTPException(422, "view name is too short")
    try:
        with eng.begin() as cx:
            user_id = _view_actor(cx, request, site_id)
            if body.config.label_id is not None and not cx.execute(text("""SELECT 1 FROM work_labels
                WHERE site_id=:site AND id=:id"""), {"site": site_id, "id": body.config.label_id}).first():
                raise HTTPException(422, "label does not belong to this project")
            result = cx.execute(text("""INSERT INTO work_saved_views
                (user_id,site_id,name,config_json,created_at,updated_at)
                VALUES (:user,:site,:name,:config,:at,:at)"""),
                {"user": user_id, "site": site_id, "name": name,
                 "config": body.config.model_dump_json(), "at": now()})
            row = cx.execute(text("SELECT * FROM work_saved_views WHERE id=:id"),
                             {"id": result.lastrowid}).mappings().one()
    except IntegrityError as exc:
        raise HTTPException(409, "view name already exists for this project") from exc
    request.state.audit_fields = ["name", "config"]
    return {"id": row["id"], "site_id": site_id, "name": name,
            "config": body.config.model_dump(), "created_at": row["created_at"], "updated_at": row["updated_at"]}


@router.delete("/views/{site_id}/{view_id}", status_code=204)
def delete_saved_view(site_id: str, view_id: int, request: Request,
                      eng: Engine = Depends(engine)) -> None:
    with eng.begin() as cx:
        user_id = _view_actor(cx, request, site_id)
        result = cx.execute(text("""DELETE FROM work_saved_views
            WHERE id=:id AND user_id=:user AND site_id=:site"""),
            {"id": view_id, "user": user_id, "site": site_id})
        if not result.rowcount:
            raise HTTPException(404, "saved view not found")
    request.state.audit_fields = ["view_id"]


@router.get("/teams")
def teams(eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        rows = cx.execute(text("""SELECT t.*, COUNT(DISTINCT u.id) AS members,
            COUNT(DISTINCT CASE WHEN w.status NOT IN ('verified','rejected','deferred') THEN w.id END) AS open_work
            FROM panel_teams t LEFT JOIN panel_users u ON u.team_id=t.id AND u.active=1
            LEFT JOIN work_items w ON w.team_id=t.id AND w.deleted_at IS NULL
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
             created_by_id: int | None = None,
             limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0),
             eng: Engine = Depends(engine)) -> dict:
    clauses = ["w.deleted_at IS NULL"]
    args: dict = {"now": now(), "lim": limit, "off": offset}
    for key, value in (("site_id", site_id), ("owner_id", owner_id), ("team_id", team_id),
                       ("status", status), ("priority", priority)):
        if value is not None and value != "":
            clauses.append(f"w.{key}=:{key}")
            args[key] = value
    if q:
        clauses.append("(w.title LIKE :q OR w.description LIKE :q OR w.url LIKE :q OR w.query LIKE :q)")
        args["q"] = "%" + q.strip() + "%"
    if created_by_id is not None:
        clauses.append("w.created_by_id=:created_by_id")
        args["created_by_id"] = created_by_id
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
            creator.full_name AS created_by_name,
            t.name AS team_name, t.color AS team_color,
            (SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id) AS checklist_total,
            (SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id AND ci.done=1) AS checklist_done
            FROM work_items w LEFT JOIN sites s ON s.site_id=w.site_id
            LEFT JOIN panel_users u ON u.id=w.owner_id LEFT JOIN panel_users creator ON creator.id=w.created_by_id
            LEFT JOIN panel_teams t ON t.id=w.team_id WHERE {where}
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
            WHERE w.deleted_at IS NULL
            ORDER BY e.id DESC LIMIT 12""")).mappings().all()
        labels_by_item: dict[int, list[dict]] = {row["id"]: [] for row in rows}
        if rows:
            identifiers = {f"item_{index}": row["id"] for index, row in enumerate(rows)}
            placeholders = ",".join(f":{key}" for key in identifiers)
            label_rows = cx.execute(text(f"""SELECT il.work_item_id,l.id,l.name,l.color
                FROM work_item_labels il JOIN work_labels l ON l.id=il.label_id AND l.site_id=il.site_id
                WHERE il.work_item_id IN ({placeholders}) ORDER BY l.name"""), identifiers).mappings().all()
            for label in label_rows:
                labels_by_item[label["work_item_id"]].append({"id": label["id"], "name": label["name"], "color": label["color"]})
    return {"summary": {k: (float(v or 0) if k == "hours_open" else int(v or 0)) for k, v in summary.items()},
            "items": [{**dict(row), "labels": labels_by_item[row["id"]]} for row in rows], "limit": limit, "offset": offset,
            "by_status": [dict(row) for row in by_status],
            "by_site": [{k: int(v or 0) if k in {"total", "open", "overdue", "unassigned"} else v for k, v in row.items()} for row in by_site],
            "by_owner": [{k: (float(v or 0) if k == "hours_open" else int(v or 0)) if k in {"total", "open", "overdue", "hours_open"} else v for k, v in row.items()} for row in by_owner],
            "by_team": [{k: int(v or 0) if k in {"total", "open", "overdue"} else v for k, v in row.items()} for row in by_team],
            "due_days": [dict(row) for row in due_days], "recent": [dict(row) for row in recent]}


@router.get("/archive")
def archive(kind: Literal["completed", "deleted"], site_id: str | None = None,
            limit: int = Query(200, ge=1, le=500), eng: Engine = Depends(engine)) -> list[dict]:
    condition = "w.deleted_at IS NOT NULL" if kind == "deleted" else "w.deleted_at IS NULL AND w.status='verified'"
    with eng.connect() as cx:
        rows = cx.execute(text(f"""SELECT w.*,s.name AS site_name,u.full_name AS owner_name,
            creator.full_name AS created_by_name FROM work_items w
            JOIN sites s ON s.site_id=w.site_id LEFT JOIN panel_users u ON u.id=w.owner_id
            LEFT JOIN panel_users creator ON creator.id=w.created_by_id
            WHERE {condition} AND (:site IS NULL OR w.site_id=:site)
            ORDER BY COALESCE(w.deleted_at,w.updated_at) DESC LIMIT :limit"""),
            {"site": site_id, "limit": limit}).mappings().all()
    return [dict(row) for row in rows]


@router.get("/board/all")
def personal_board(request: Request, after_id: int = Query(0, ge=0),
                   limit: int = Query(200, ge=1, le=500), eng: Engine = Depends(engine)) -> dict:
    actor = getattr(request.state, "panel_user", None)
    if not actor:
        raise HTTPException(401, "sign in to view assigned tasks")
    with eng.connect() as cx:
        rows = cx.execute(text("""SELECT w.*,s.name AS site_name,u.full_name AS owner_name,
            creator.full_name AS created_by_name,t.name AS team_name,t.color AS team_color,
            0 AS checklist_total,0 AS checklist_done FROM work_items w
            JOIN sites s ON s.site_id=w.site_id LEFT JOIN panel_users u ON u.id=w.owner_id
            LEFT JOIN panel_users creator ON creator.id=w.created_by_id
            LEFT JOIN panel_teams t ON t.id=w.team_id
            WHERE w.owner_id=:owner AND w.deleted_at IS NULL AND w.status NOT IN ('verified','rejected','deferred')
            AND w.id>:after ORDER BY w.id LIMIT :limit"""),
            {"owner": actor["id"], "after": after_id, "limit": limit + 1}).mappings().all()
    page = rows[:limit]
    return {"items": [{**dict(row), "labels": [], "custom_fields": []} for row in page],
            "next_after_id": page[-1]["id"] if len(rows) > limit else None}


@router.get("/board/created")
def created_board(request: Request, after_id: int = Query(0, ge=0),
                  limit: int = Query(200, ge=1, le=500), eng: Engine = Depends(engine)) -> dict:
    actor = getattr(request.state, "panel_user", None)
    if not actor:
        raise HTTPException(401, "sign in to view tasks you created")
    with eng.connect() as cx:
        rows = cx.execute(text("""SELECT w.*,s.name AS site_name,u.full_name AS owner_name,
            creator.full_name AS created_by_name,t.name AS team_name,t.color AS team_color,
            0 AS checklist_total,0 AS checklist_done FROM work_items w
            JOIN sites s ON s.site_id=w.site_id LEFT JOIN panel_users u ON u.id=w.owner_id
            LEFT JOIN panel_users creator ON creator.id=w.created_by_id
            LEFT JOIN panel_teams t ON t.id=w.team_id
            WHERE w.created_by_id=:creator AND w.deleted_at IS NULL
            AND w.status NOT IN ('verified','rejected','deferred')
            AND w.id>:after ORDER BY w.id LIMIT :limit"""),
            {"creator": actor["id"], "after": after_id, "limit": limit + 1}).mappings().all()
    page = rows[:limit]
    return {"items": [{**dict(row), "labels": [], "custom_fields": []} for row in page],
            "next_after_id": page[-1]["id"] if len(rows) > limit else None}


@router.get("/board/{site_id}")
def project_board(site_id: str, request: Request, after_id: int = Query(0, ge=0),
                  limit: int = Query(200, ge=1, le=500), eng: Engine = Depends(engine)) -> dict:
    """Complete project board via keyset pages; avoids the overview's 500-row cap."""
    with eng.connect() as cx:
        if not cx.execute(text("SELECT 1 FROM sites WHERE site_id=:site"), {"site": site_id}).first():
            raise HTTPException(404, "site not found")
        if project_responsibility(cx, request, site_id) == "none":
            raise HTTPException(403, "project membership is required")
        rows = cx.execute(text("""SELECT w.*,s.name AS site_name,u.full_name AS owner_name,
            creator.full_name AS created_by_name,
            t.name AS team_name,t.color AS team_color,
            (SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id) AS checklist_total,
            (SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id AND ci.done=1) AS checklist_done
            FROM work_items w JOIN sites s ON s.site_id=w.site_id
            LEFT JOIN panel_users u ON u.id=w.owner_id LEFT JOIN panel_users creator ON creator.id=w.created_by_id
            LEFT JOIN panel_teams t ON t.id=w.team_id
            WHERE w.site_id=:site AND w.deleted_at IS NULL AND w.id>:after ORDER BY w.id LIMIT :limit"""),
            {"site": site_id, "after": after_id, "limit": limit + 1}).mappings().all()
        page = rows[:limit]
        labels_by_item: dict[int, list[dict]] = {row["id"]: [] for row in page}
        fields_by_item: dict[int, list[dict]] = {row["id"]: [] for row in page}
        if page:
            identifiers = {f"item_{index}": row["id"] for index, row in enumerate(page)}
            placeholders = ",".join(f":{key}" for key in identifiers)
            label_rows = cx.execute(text(f"""SELECT il.work_item_id,l.id,l.name,l.color
                FROM work_item_labels il JOIN work_labels l ON l.id=il.label_id AND l.site_id=il.site_id
                WHERE il.site_id=:site AND il.work_item_id IN ({placeholders}) ORDER BY l.name"""),
                {**identifiers, "site": site_id}).mappings().all()
            for label in label_rows:
                labels_by_item[label["work_item_id"]].append({"id": label["id"], "name": label["name"], "color": label["color"]})
            field_rows = cx.execute(text(f"""SELECT v.work_item_id,f.id,f.name,f.field_type,v.value_json
                FROM work_custom_values v JOIN work_custom_fields f ON f.id=v.field_id AND f.site_id=v.site_id
                WHERE v.site_id=:site AND v.work_item_id IN ({placeholders}) ORDER BY f.id"""),
                {**identifiers, "site": site_id}).mappings().all()
            for field in field_rows:
                fields_by_item[field["work_item_id"]].append({"id": field["id"], "name": field["name"],
                    "field_type": field["field_type"], "value": json.loads(field["value_json"])})
    return {"items": [{**dict(row), "labels": labels_by_item[row["id"]],
                        "custom_fields": fields_by_item[row["id"]]} for row in page],
            "next_after_id": page[-1]["id"] if len(rows) > limit else None}
