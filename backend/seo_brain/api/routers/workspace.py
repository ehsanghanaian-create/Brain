"""Cross-site work command center and team directory."""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


def _checklists_for(cx, rows) -> dict[int, list[dict]]:
    """Fetch checklist previews for a board page with one query, not one per card."""
    result: dict[int, list[dict]] = {row["id"]: [] for row in rows}
    if not rows:
        return result
    identifiers = {f"item_{index}": row["id"] for index, row in enumerate(rows)}
    placeholders = ",".join(f":{key}" for key in identifiers)
    steps = cx.execute(text(f"""SELECT id,work_item_id,title,done FROM work_checklist_items
        WHERE work_item_id IN ({placeholders}) ORDER BY id"""), identifiers).mappings().all()
    for step in steps:
        result[step["work_item_id"]].append({"id": step["id"], "title": step["title"],
                                             "done": bool(step["done"])})
    legacy = cx.execute(text(f"""WITH RECURSIVE children(root_id,id,title,status,deleted_at) AS (
        SELECT parent_id,id,title,status,deleted_at FROM work_items
        WHERE parent_id IN ({placeholders})
        UNION ALL
        SELECT children.root_id,child.id,child.title,child.status,child.deleted_at
        FROM work_items child JOIN children ON child.parent_id=children.id
    ) SELECT root_id,id,title,status FROM children WHERE deleted_at IS NULL
        ORDER BY root_id,id"""), identifiers).mappings().all()
    for child in legacy:
        result[child["root_id"]].append({"id": -child["id"], "title": child["title"],
                                         "done": child["status"] == "verified", "legacy": True})
    return result


@router.get("/reports")
def work_report(period: Literal["week", "month"] = "week", anchor: date | None = None,
                site_id: str | None = None, user_id: int | None = None,
                start_day: date | None = None, end_day: date | None = None,
                eng: Engine = Depends(engine)) -> dict:
    """Period activity is derived from immutable task events, not mutable updated_at."""
    try:
        zone = ZoneInfo("Asia/Tehran")
    except ZoneInfoNotFoundError:
        # Windows test hosts may lack the optional tzdata package. Current Iranian time has no DST.
        zone = timezone(timedelta(hours=3, minutes=30))
    chosen = anchor or datetime.now(zone).date()
    if (start_day is None) != (end_day is None):
        raise HTTPException(422, "both report boundaries are required")
    if start_day is not None and end_day is not None:
        if not start_day <= chosen < end_day or not 1 <= (end_day - start_day).days <= 32:
            raise HTTPException(422, "invalid report boundaries")
    elif period == "week":
        start_day = chosen - timedelta(days=(chosen.weekday() + 2) % 7)  # Saturday
        end_day = start_day + timedelta(days=7)
    else:
        start_day = chosen.replace(day=1)
        end_day = date(start_day.year + (start_day.month == 12), start_day.month % 12 + 1, 1)
    start = datetime.combine(start_day, time.min, zone).astimezone(timezone.utc).isoformat(timespec="seconds")
    end = datetime.combine(end_day, time.min, zone).astimezone(timezone.utc).isoformat(timespec="seconds")
    args = {"start": start, "end": end, "site": site_id, "user": user_id,
            "start_day": start_day.isoformat(), "end_day": end_day.isoformat()}
    with eng.connect() as cx:
        if site_id and not cx.execute(text("SELECT 1 FROM sites WHERE site_id=:site"), args).first():
            raise HTTPException(404, "project not found")
        if user_id and not cx.execute(text("SELECT 1 FROM panel_users WHERE id=:user"), args).first():
            raise HTTPException(404, "user not found")
        events = cx.execute(text("""SELECT e.id,e.site_id,e.work_item_id,e.event_type,e.before_json,
            e.after_json,e.note,e.actor_id,e.actor_username,e.created_at,s.name AS site_name,
            u.full_name AS actor_name FROM work_item_events e
            JOIN sites s ON s.site_id=e.site_id
            LEFT JOIN panel_users u ON u.id=e.actor_id
            WHERE e.created_at>=:start AND e.created_at<:end
              AND (:site IS NULL OR e.site_id=:site) AND (:user IS NULL OR e.actor_id=:user)
            ORDER BY e.id"""), args).mappings().all()
        time_rows = cx.execute(text("""SELECT t.user_id,t.minutes,t.work_date,t.site_id,t.work_item_id,
            u.full_name AS user_name,s.name AS site_name FROM work_time_entries t
            JOIN sites s ON s.site_id=t.site_id LEFT JOIN panel_users u ON u.id=t.user_id
            WHERE t.work_date>=:start_day AND t.work_date<:end_day
              AND (:site IS NULL OR t.site_id=:site) AND (:user IS NULL OR t.user_id=:user)"""), args).mappings().all()
        open_rows = cx.execute(text("""SELECT w.owner_id,w.site_id,s.name AS site_name,
            u.full_name AS owner_name,COUNT(*) AS count FROM work_items w
            JOIN sites s ON s.site_id=w.site_id LEFT JOIN panel_users u ON u.id=w.owner_id
            WHERE w.deleted_at IS NULL AND w.parent_id IS NULL AND w.status NOT IN ('verified','rejected','deferred')
              AND (:site IS NULL OR w.site_id=:site) AND (:user IS NULL OR w.owner_id=:user)
            GROUP BY w.owner_id,w.site_id"""), args).mappings().all()
        people = cx.execute(text("SELECT id,full_name FROM panel_users WHERE active=1 ORDER BY full_name")).mappings().all()
    by_person: dict[int, dict] = {}
    by_project: dict[str, dict] = {}
    daily: dict[str, dict] = {}
    completed_tasks: list[dict] = []
    totals = {key: 0 for key in ("created", "completed", "handoffs", "comments", "updates", "minutes", "open_now")}
    for event in events:
        before = json.loads(event["before_json"]) if event["before_json"] else {}
        after = json.loads(event["after_json"]) if event["after_json"] else {}
        metric = ("created" if event["event_type"] == "created" else
                  "completed" if before.get("status") != "verified" and after.get("status") == "verified" else
                  "handoffs" if event["event_type"] == "handoff" else
                  "comments" if event["event_type"] == "comment" else
                  "updates" if event["event_type"] in {"updated", "bulk_updated"} else None)
        if not metric:
            continue
        day = datetime.fromisoformat(event["created_at"]).astimezone(zone).date().isoformat()
        person_id = event["actor_id"] or 0
        person = by_person.setdefault(person_id, {"user_id": event["actor_id"],
            "name": event["actor_name"] or event["actor_username"] or "سیستم",
            **{key: 0 for key in totals}})
        project = by_project.setdefault(event["site_id"], {"site_id": event["site_id"],
            "name": event["site_name"], **{key: 0 for key in totals}})
        bucket = daily.setdefault(day, {"day": day, "created": 0, "completed": 0, "minutes": 0})
        for target in (totals, person, project):
            target[metric] += 1
        if metric in bucket:
            bucket[metric] += 1
        if metric == "completed":
            completed_tasks.append({"id": event["work_item_id"], "site_id": event["site_id"],
                "site_name": event["site_name"], "title": after.get("title", ""),
                "actor_name": person["name"], "completed_at": event["created_at"]})
    for row in time_rows:
        person = by_person.setdefault(row["user_id"], {"user_id": row["user_id"],
            "name": row["user_name"] or "کاربر حذف‌شده", **{key: 0 for key in totals}})
        project = by_project.setdefault(row["site_id"], {"site_id": row["site_id"],
            "name": row["site_name"], **{key: 0 for key in totals}})
        bucket = daily.setdefault(row["work_date"], {"day": row["work_date"],
            "created": 0, "completed": 0, "minutes": 0})
        for target in (totals, person, project, bucket):
            target["minutes"] += row["minutes"]
    for row in open_rows:
        totals["open_now"] += row["count"]
        person = by_person.setdefault(row["owner_id"] or 0, {"user_id": row["owner_id"],
            "name": row["owner_name"] or "بی‌مسئول", **{key: 0 for key in totals}})
        project = by_project.setdefault(row["site_id"], {"site_id": row["site_id"],
            "name": row["site_name"], **{key: 0 for key in totals}})
        person["open_now"] += row["count"]
        project["open_now"] += row["count"]
    return {"period": period, "start_day": start_day.isoformat(), "end_day": end_day.isoformat(),
            "totals": totals, "by_person": sorted(by_person.values(), key=lambda entry: (-entry["completed"], -entry["minutes"], entry["name"])),
            "by_project": sorted(by_project.values(), key=lambda entry: (-entry["completed"], entry["name"])),
            "daily": [daily[key] for key in sorted(daily)], "completed_tasks": completed_tasks[-100:][::-1],
            "people": [dict(row) for row in people]}


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
            LEFT JOIN work_items w ON w.team_id=t.id AND w.deleted_at IS NULL AND w.parent_id IS NULL
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


@router.get("/team-management")
def team_management(request: Request, user_id: int | None = None, eng: Engine = Depends(engine)) -> dict:
    """Administrator's live roster, workload and task activity across projects."""
    actor = getattr(request.state, "panel_user", None)
    if not actor or actor["role"] != "admin" or not actor["is_superadmin"]:
        raise HTTPException(403, "فقط مدیر کل به مدیریت تیم دسترسی دارد")
    stamp = datetime.now(timezone.utc)
    args = {"now": stamp.isoformat(timespec="seconds"),
            "week_end": (stamp + timedelta(days=7)).isoformat(timespec="seconds"),
            "week_start": (stamp - timedelta(days=7)).isoformat(timespec="seconds"),
            "selected_user": user_id}
    with eng.connect() as cx:
        people = cx.execute(text("""SELECT u.id,u.username,u.full_name,u.role,u.active,u.team_id,
            t.name AS team_name,COUNT(w.id) AS total_tasks,
            SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') THEN 1 ELSE 0 END) AS open_tasks,
            SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') AND w.due_at<:now THEN 1 ELSE 0 END) AS overdue_tasks,
            SUM(CASE WHEN w.status='blocked' THEN 1 ELSE 0 END) AS blocked_tasks,
            SUM(CASE WHEN w.status='review' THEN 1 ELSE 0 END) AS review_tasks,
            SUM(CASE WHEN w.status NOT IN ('verified','rejected','deferred') AND w.due_at>=:now
                AND w.due_at<:week_end THEN 1 ELSE 0 END) AS due_week_tasks,
            SUM(CASE WHEN w.status='verified' THEN 1 ELSE 0 END) AS completed_tasks
            FROM panel_users u LEFT JOIN panel_teams t ON t.id=u.team_id
            LEFT JOIN work_items w ON w.owner_id=u.id AND w.deleted_at IS NULL AND w.parent_id IS NULL
            GROUP BY u.id ORDER BY u.active DESC,u.full_name"""), args).mappings().all()
        assignments = cx.execute(text("""SELECT a.user_id,a.site_id,a.responsibility,s.name
            FROM site_assignments a JOIN sites s ON s.site_id=a.site_id
            ORDER BY s.name""")).mappings().all()
        activity = cx.execute(text("""SELECT actor_id,COUNT(*) AS events_week,MAX(created_at) AS last_task_activity_at
            FROM work_item_events WHERE actor_id IS NOT NULL GROUP BY actor_id""")).mappings().all()
        week_activity = cx.execute(text("""SELECT actor_id,COUNT(*) AS events_week
            FROM work_item_events WHERE actor_id IS NOT NULL AND created_at>=:week_start
            GROUP BY actor_id"""), args).mappings().all()
        summary = cx.execute(text("""SELECT COUNT(*) AS total_tasks,
            SUM(CASE WHEN status NOT IN ('verified','rejected','deferred') THEN 1 ELSE 0 END) AS open_tasks,
            SUM(CASE WHEN status NOT IN ('verified','rejected','deferred') AND due_at<:now THEN 1 ELSE 0 END) AS overdue_tasks,
            SUM(CASE WHEN status='blocked' THEN 1 ELSE 0 END) AS blocked_tasks,
            SUM(CASE WHEN status='review' THEN 1 ELSE 0 END) AS review_tasks,
            SUM(CASE WHEN status NOT IN ('verified','rejected','deferred') AND owner_id IS NULL THEN 1 ELSE 0 END) AS unassigned_tasks
            FROM work_items WHERE deleted_at IS NULL AND parent_id IS NULL"""), args).mappings().one()
        recent = cx.execute(text("""SELECT e.id,e.actor_id,e.actor_username,e.event_type,e.created_at,
            e.work_item_id,e.site_id,w.title AS task_title,s.name AS project_name
            FROM work_item_events e JOIN work_items w ON w.id=e.work_item_id
            JOIN sites s ON s.site_id=e.site_id
            WHERE (:selected_user IS NULL OR e.actor_id=:selected_user)
            ORDER BY e.id DESC LIMIT 30"""), args).mappings().all()
    projects_by_user: dict[int, list[dict]] = {}
    for row in assignments:
        projects_by_user.setdefault(row["user_id"], []).append({
            "site_id": row["site_id"], "name": row["name"], "responsibility": row["responsibility"]})
    last_by_user = {row["actor_id"]: row["last_task_activity_at"] for row in activity}
    week_by_user = {row["actor_id"]: row["events_week"] for row in week_activity}
    count_keys = ("total_tasks", "open_tasks", "overdue_tasks", "blocked_tasks", "review_tasks", "due_week_tasks", "completed_tasks")
    return {"summary": {**{key: int(summary[key] or 0) for key in summary},
                        "active_people": sum(bool(row["active"]) for row in people)},
            "people": [{**dict(row), **{key: int(row[key] or 0) for key in count_keys},
                        "active": bool(row["active"]), "projects": projects_by_user.get(row["id"], []),
                        "events_week": int(week_by_user.get(row["id"], 0)),
                        "last_task_activity_at": last_by_user.get(row["id"])} for row in people],
            "recent": [dict(row) for row in recent]}


@router.get("/team-management/tasks")
def team_management_tasks(request: Request, site_id: str | None = None,
                          owner_id: int | None = None, team_id: int | None = None,
                          priority: Literal["critical", "high", "normal", "low"] | None = None,
                          status: str | None = None,
                          focus: Literal["open", "all", "review", "overdue", "due_week", "blocked",
                                         "unassigned", "unscheduled", "completed"] = "open",
                          q: str | None = None, limit: int = Query(50, ge=1, le=100),
                          offset: int = Query(0, ge=0), eng: Engine = Depends(engine)) -> dict:
    """One filtered, paginated task ledger and matching portfolio aggregates for the manager."""
    actor = getattr(request.state, "panel_user", None)
    if not actor or actor["role"] != "admin" or not actor["is_superadmin"]:
        raise HTTPException(403, "فقط مدیر کل به مدیریت تیم دسترسی دارد")
    if status and status not in {"new", "triaged", "approved", "assigned", "in_progress",
                                 "review", "published", "measurement_pending", "verified",
                                 "blocked", "rejected", "deferred"}:
        raise HTTPException(422, "invalid work status")
    stamp = datetime.now(timezone.utc)
    args = {"now": stamp.isoformat(timespec="seconds"),
            "week_end": (stamp + timedelta(days=7)).isoformat(timespec="seconds"),
            "month_end": (stamp + timedelta(days=30)).isoformat(timespec="seconds"),
            "today": stamp.date().isoformat(),
            "timeline_end": (stamp.date() + timedelta(days=91)).isoformat(),
            "site": site_id, "owner": owner_id, "team": team_id, "priority": priority,
            "status": status,
            "lim": limit, "off": offset}
    clauses = ["w.deleted_at IS NULL", "w.parent_id IS NULL"]
    if site_id:
        clauses.append("w.site_id=:site")
    if owner_id is not None:
        clauses.append("w.owner_id=:owner")
    if team_id is not None:
        clauses.append("COALESCE(w.team_id,u.team_id)=:team")
    if priority:
        clauses.append("w.priority=:priority")
    if status:
        clauses.append("w.status=:status")
    if q and q.strip():
        clauses.append("(w.title LIKE :q OR w.description LIKE :q OR s.name LIKE :q OR u.full_name LIKE :q)")
        args["q"] = "%" + q.strip()[:100] + "%"
    base = " FROM work_items w JOIN sites s ON s.site_id=w.site_id " \
           "LEFT JOIN panel_users u ON u.id=w.owner_id WHERE " + " AND ".join(clauses)
    open_clause = "w.status NOT IN ('verified','rejected','deferred')"
    focus_clause = {
        "open": open_clause, "all": "1=1", "review": "w.status='review'",
        "overdue": f"{open_clause} AND w.due_at<:now",
        "due_week": f"{open_clause} AND w.due_at>=:now AND w.due_at<:week_end",
        "blocked": "w.status='blocked'", "unassigned": f"{open_clause} AND w.owner_id IS NULL",
        "unscheduled": f"{open_clause} AND w.due_at IS NULL",
        "completed": "w.status='verified'",
    }[focus]
    focused = base + " AND " + focus_clause
    with eng.connect() as cx:
        total = cx.execute(text("SELECT COUNT(*)" + focused), args).scalar_one()
        rows = cx.execute(text("""SELECT w.id,w.site_id,s.name AS site_name,w.title,w.description,w.verification_note,
            w.status,w.priority,
            w.owner_id,u.full_name AS owner_name,w.team_id,w.created_by_id,
            creator.full_name AS created_by_name,w.parent_id,w.start_at,w.due_at,w.progress_percent,
            w.estimated_hours,w.created_at,w.updated_at,w.blocked_reason,
            ((SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id) +
             (SELECT COUNT(*) FROM work_items child WHERE child.parent_id=w.id AND child.deleted_at IS NULL)) AS checklist_total,
            ((SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id AND ci.done=1) +
             (SELECT COUNT(*) FROM work_items child WHERE child.parent_id=w.id AND child.deleted_at IS NULL AND child.status='verified')) AS checklist_done,
            (SELECT COUNT(*) FROM work_items child WHERE child.parent_id=w.id AND child.deleted_at IS NULL) AS subtasks
            FROM work_items w JOIN sites s ON s.site_id=w.site_id
            LEFT JOIN panel_users u ON u.id=w.owner_id
            LEFT JOIN panel_users creator ON creator.id=w.created_by_id
            WHERE """ + " AND ".join(clauses) + " AND " + focus_clause + """
            ORDER BY CASE WHEN w.status NOT IN ('verified','rejected','deferred') AND w.due_at<:now THEN 0
                          WHEN w.status='blocked' THEN 1 WHEN w.due_at IS NULL THEN 3 ELSE 2 END,
                     CASE w.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                     w.due_at, w.id DESC LIMIT :lim OFFSET :off"""), args).mappings().all()
        stages = cx.execute(text("SELECT w.status AS key,COUNT(*) AS count" + base +
                                 " GROUP BY w.status"), args).mappings().all()
        schedule = cx.execute(text(f"""SELECT
            SUM(CASE WHEN {open_clause} AND w.due_at<:now THEN 1 ELSE 0 END) AS overdue,
            SUM(CASE WHEN {open_clause} AND w.due_at>=:now AND w.due_at<:week_end THEN 1 ELSE 0 END) AS due_week,
            SUM(CASE WHEN {open_clause} AND w.due_at>=:week_end AND w.due_at<:month_end THEN 1 ELSE 0 END) AS due_month,
            SUM(CASE WHEN {open_clause} AND w.due_at>=:month_end THEN 1 ELSE 0 END) AS later,
            SUM(CASE WHEN {open_clause} AND w.due_at IS NULL THEN 1 ELSE 0 END) AS unscheduled
            {base}"""), args).mappings().one()
        workload = cx.execute(text(f"""SELECT w.owner_id AS user_id,COALESCE(u.full_name,'بی‌مسئول') AS name,
            COUNT(*) AS total,
            SUM(CASE WHEN {open_clause} THEN 1 ELSE 0 END) AS open,
            SUM(CASE WHEN {open_clause} AND w.due_at<:now THEN 1 ELSE 0 END) AS overdue,
            SUM(CASE WHEN w.status='blocked' THEN 1 ELSE 0 END) AS blocked,
            SUM(CASE WHEN {open_clause} AND w.due_at IS NULL THEN 1 ELSE 0 END) AS unscheduled,
            SUM(CASE WHEN w.status='verified' THEN 1 ELSE 0 END) AS completed
            {base} GROUP BY w.owner_id ORDER BY open DESC,name"""), args).mappings().all()
        timeline = cx.execute(text(f"""SELECT w.owner_id AS user_id,w.site_id,
            CASE WHEN w.due_at IS NULL THEN -2 WHEN w.due_at<:now THEN -1
                ELSE CAST((julianday(substr(w.due_at,1,10))-julianday(:today))/7 AS INTEGER)
            END AS week_index,
            COUNT(*) AS count {base} AND {open_clause}
            AND (w.due_at IS NULL OR w.due_at<:now OR w.due_at<:timeline_end)
            GROUP BY w.owner_id,w.site_id,week_index ORDER BY week_index,w.owner_id,w.site_id"""), args).mappings().all()
    return {"items": [dict(row) for row in rows], "total": int(total),
            "limit": limit, "offset": offset,
            "stages": [dict(row) for row in stages],
            "schedule": {key: int(value or 0) for key, value in schedule.items()},
            "timeline": [dict(row) for row in timeline],
            "workload": [{**dict(row), **{key: int(row[key] or 0) for key in
                ("total", "open", "overdue", "blocked", "unscheduled", "completed")}}
                for row in workload]}


@router.get("/team-management/tasks/{item_id}")
def team_management_task(item_id: int, request: Request, eng: Engine = Depends(engine)) -> dict:
    """Fresh task details for the manager's in-place review and discussion panel."""
    actor = getattr(request.state, "panel_user", None)
    if not actor or actor["role"] != "admin" or not actor["is_superadmin"]:
        raise HTTPException(403, "فقط مدیر کل به مدیریت تیم دسترسی دارد")
    with eng.connect() as cx:
        row = cx.execute(text("""SELECT w.id,w.site_id,s.name AS site_name,w.title,w.description,
            w.verification_note,w.status,w.priority,w.owner_id,u.full_name AS owner_name,
            w.team_id,w.created_by_id,creator.full_name AS created_by_name,w.parent_id,
            w.start_at,w.due_at,w.progress_percent,w.estimated_hours,w.created_at,w.updated_at,
            w.blocked_reason,
            ((SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id) +
             (SELECT COUNT(*) FROM work_items child WHERE child.parent_id=w.id AND child.deleted_at IS NULL)) AS checklist_total,
            ((SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id AND ci.done=1) +
             (SELECT COUNT(*) FROM work_items child WHERE child.parent_id=w.id AND child.deleted_at IS NULL AND child.status='verified')) AS checklist_done,
            (SELECT COUNT(*) FROM work_items child WHERE child.parent_id=w.id AND child.deleted_at IS NULL) AS subtasks
            FROM work_items w JOIN sites s ON s.site_id=w.site_id
            LEFT JOIN panel_users u ON u.id=w.owner_id
            LEFT JOIN panel_users creator ON creator.id=w.created_by_id
            WHERE w.id=:id AND w.deleted_at IS NULL"""), {"id": item_id}).mappings().first()
    if not row:
        raise HTTPException(404, "work item not found")
    return dict(row)


@router.get("/overview")
def overview(site_id: str | None = None, owner_id: int | None = None, team_id: int | None = None,
             status: str | None = None, priority: str | None = None, q: str | None = None,
             created_by_id: int | None = None,
             limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0),
             eng: Engine = Depends(engine)) -> dict:
    clauses = ["w.deleted_at IS NULL", "w.parent_id IS NULL"]
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
            ((SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id) +
             (SELECT COUNT(*) FROM work_items child WHERE child.parent_id=w.id AND child.deleted_at IS NULL)) AS checklist_total,
            ((SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id AND ci.done=1) +
             (SELECT COUNT(*) FROM work_items child WHERE child.parent_id=w.id AND child.deleted_at IS NULL AND child.status='verified')) AS checklist_done
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
        checklists_by_item = _checklists_for(cx, rows)
        if rows:
            identifiers = {f"item_{index}": row["id"] for index, row in enumerate(rows)}
            placeholders = ",".join(f":{key}" for key in identifiers)
            label_rows = cx.execute(text(f"""SELECT il.work_item_id,l.id,l.name,l.color
                FROM work_item_labels il JOIN work_labels l ON l.id=il.label_id AND l.site_id=il.site_id
                WHERE il.work_item_id IN ({placeholders}) ORDER BY l.name"""), identifiers).mappings().all()
            for label in label_rows:
                labels_by_item[label["work_item_id"]].append({"id": label["id"], "name": label["name"], "color": label["color"]})
    return {"summary": {k: (float(v or 0) if k == "hours_open" else int(v or 0)) for k, v in summary.items()},
            "items": [{**dict(row), "labels": labels_by_item[row["id"]],
                       "checklist": checklists_by_item[row["id"]],
                       "checklist_total": len(checklists_by_item[row["id"]]),
                       "checklist_done": sum(step["done"] for step in checklists_by_item[row["id"]])} for row in rows], "limit": limit, "offset": offset,
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
            WHERE {condition} AND w.parent_id IS NULL AND (:site IS NULL OR w.site_id=:site)
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
            WHERE w.owner_id=:owner AND w.parent_id IS NULL AND w.deleted_at IS NULL AND w.status NOT IN ('verified','rejected','deferred')
            AND w.id>:after ORDER BY w.id LIMIT :limit"""),
            {"owner": actor["id"], "after": after_id, "limit": limit + 1}).mappings().all()
        page = rows[:limit]
        checklists = _checklists_for(cx, page)
    return {"items": [{**dict(row), "labels": [], "custom_fields": [],
                       "checklist": checklists[row["id"]],
                       "checklist_total": len(checklists[row["id"]]),
                       "checklist_done": sum(step["done"] for step in checklists[row["id"]])} for row in page],
            "next_after_id": page[-1]["id"] if len(rows) > limit else None}


def _creator_board(request: Request, after_id: int, limit: int, eng: Engine,
                   delegated_only: bool) -> dict:
    actor = getattr(request.state, "panel_user", None)
    if not actor:
        raise HTTPException(401, "sign in to view tasks you created")
    delegation_clause = "AND w.owner_id IS NOT NULL AND w.owner_id<>:creator" if delegated_only else ""
    authorship_clause = """(w.created_by_id=:creator OR EXISTS (
        SELECT 1 FROM work_item_events event WHERE event.work_item_id=w.id
        AND event.event_type='handoff' AND event.actor_id=:creator
        AND event.id=(SELECT MAX(latest.id) FROM work_item_events latest
            WHERE latest.work_item_id=w.id AND latest.event_type='handoff')
    ))""" if delegated_only else "w.created_by_id=:creator"
    with eng.connect() as cx:
        rows = cx.execute(text(f"""SELECT w.*,s.name AS site_name,u.full_name AS owner_name,
            creator.full_name AS created_by_name,t.name AS team_name,t.color AS team_color,
            0 AS checklist_total,0 AS checklist_done FROM work_items w
            JOIN sites s ON s.site_id=w.site_id LEFT JOIN panel_users u ON u.id=w.owner_id
            LEFT JOIN panel_users creator ON creator.id=w.created_by_id
            LEFT JOIN panel_teams t ON t.id=w.team_id
            WHERE {authorship_clause} AND w.parent_id IS NULL AND w.deleted_at IS NULL
            AND w.status NOT IN ('verified','rejected','deferred')
            {delegation_clause} AND w.id>:after ORDER BY w.id LIMIT :limit"""),
            {"creator": actor["id"], "after": after_id, "limit": limit + 1}).mappings().all()
        page = rows[:limit]
        checklists = _checklists_for(cx, page)
    return {"items": [{**dict(row), "labels": [], "custom_fields": [],
                       "checklist": checklists[row["id"]],
                       "checklist_total": len(checklists[row["id"]]),
                       "checklist_done": sum(step["done"] for step in checklists[row["id"]])} for row in page],
            "next_after_id": page[-1]["id"] if len(rows) > limit else None}


@router.get("/board/created")
def created_board(request: Request, after_id: int = Query(0, ge=0),
                  limit: int = Query(200, ge=1, le=500), eng: Engine = Depends(engine)) -> dict:
    return _creator_board(request, after_id, limit, eng, delegated_only=False)


@router.get("/board/delegated")
def delegated_board(request: Request, after_id: int = Query(0, ge=0),
                    limit: int = Query(200, ge=1, le=500), eng: Engine = Depends(engine)) -> dict:
    """Work authored by the signed-in user and currently assigned to someone else."""
    return _creator_board(request, after_id, limit, eng, delegated_only=True)


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
            ((SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id) +
             (SELECT COUNT(*) FROM work_items child WHERE child.parent_id=w.id AND child.deleted_at IS NULL)) AS checklist_total,
            ((SELECT COUNT(*) FROM work_checklist_items ci WHERE ci.work_item_id=w.id AND ci.done=1) +
             (SELECT COUNT(*) FROM work_items child WHERE child.parent_id=w.id AND child.deleted_at IS NULL AND child.status='verified')) AS checklist_done
            FROM work_items w JOIN sites s ON s.site_id=w.site_id
            LEFT JOIN panel_users u ON u.id=w.owner_id LEFT JOIN panel_users creator ON creator.id=w.created_by_id
            LEFT JOIN panel_teams t ON t.id=w.team_id
            WHERE w.site_id=:site AND w.parent_id IS NULL AND w.deleted_at IS NULL AND w.id>:after ORDER BY w.id LIMIT :limit"""),
            {"site": site_id, "after": after_id, "limit": limit + 1}).mappings().all()
        page = rows[:limit]
        checklists_by_item = _checklists_for(cx, page)
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
                        "checklist": checklists_by_item[row["id"]],
                        "checklist_total": len(checklists_by_item[row["id"]]),
                        "checklist_done": sum(step["done"] for step in checklists_by_item[row["id"]]),
                        "custom_fields": fields_by_item[row["id"]]} for row in page],
            "next_after_id": page[-1]["id"] if len(rows) > limit else None}
