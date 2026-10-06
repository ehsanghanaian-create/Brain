"""Individual panel login and administrator audit viewer."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text

from ..deps import engine
from ..panel_auth import create_session, hash_password, session_user, token_hash, utcnow, verify_password

router = APIRouter(prefix="/auth", tags=["panel-auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=1, max_length=256)


@router.get("/status")
def status(eng: Engine = Depends(engine)) -> dict:
    with eng.connect() as cx:
        configured = bool(cx.execute(text("SELECT 1 FROM panel_users WHERE password_hash IS NOT NULL LIMIT 1")).first())
    return {"configured": configured}


@router.post("/login")
def login(body: LoginIn, request: Request, eng: Engine = Depends(engine)) -> dict:
    from ..panel_auth import verify_password

    username = body.username.strip().lower()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(timespec="seconds")
    row = None
    token = None
    with eng.begin() as cx:
        cx.execute(text("DELETE FROM panel_login_attempts WHERE attempted_at < :cutoff"), {"cutoff": cutoff})
        attempts = cx.execute(text("SELECT COUNT(*) FROM panel_login_attempts WHERE username=:username"),
                              {"username": username}).scalar_one()
        if attempts < 5:
            row = cx.execute(text("SELECT id,username,full_name,email,role,date_calendar,active,password_hash FROM panel_users WHERE username=:username"),
                             {"username": username}).mappings().first()
            if not row or not row["active"] or not verify_password(body.password, row["password_hash"]):
                cx.execute(text("INSERT INTO panel_login_attempts(username,attempted_at) VALUES (:username,:at)"),
                           {"username": username, "at": utcnow()})
                row = None
            else:
                cx.execute(text("DELETE FROM panel_login_attempts WHERE username=:username"), {"username": username})
                token = create_session(cx, row["id"])
                cx.execute(text("""INSERT INTO panel_audit_log(actor_id,actor_username,actor_role,method,path,status_code,changed_fields,request_id,created_at)
                    VALUES (:id,:username,:role,'POST','/api/v1/auth/login',200,'[]',:request_id,:at)"""),
                    {"id": row["id"], "username": row["username"], "role": row["role"],
                     "request_id": getattr(request.state, "request_id", None), "at": utcnow()})
    if attempts >= 5:
        raise HTTPException(429, "تلاش‌های ورود بیش از حد مجاز است؛ ۱۵ دقیقه بعد دوباره تلاش کنید")
    if not row:
        raise HTTPException(401, "نام کاربری یا گذرواژه نادرست است")
    return {"token": token, "user": {key: row[key] for key in ("id", "username", "full_name", "email", "role", "date_calendar")}}



def current_user(authorization: str | None = Header(default=None), eng: Engine = Depends(engine)) -> dict:
    token = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else ""
    with eng.connect() as cx:
        user = session_user(cx, token)
    if not user:
        raise HTTPException(401, "نشست معتبر نیست")
    return {key: user[key] for key in ("id", "username", "full_name", "email", "role", "date_calendar")}


@router.get("/me")
def me(user: dict = Depends(current_user)) -> dict:
    return user


class ProfilePatch(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    email: str | None = Field(default=None, max_length=255)
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str | None = Field(default=None, min_length=8, max_length=256)


@router.patch("/me")
def update_profile(body: ProfilePatch, request: Request, user: dict = Depends(current_user),
                   eng: Engine = Depends(engine)) -> dict:
    values = body.model_dump(exclude_unset=True, exclude={"current_password", "new_password"})
    if not values and not body.new_password:
        raise HTTPException(422, "profile changes are required")
    if "username" in values:
        values["username"] = values["username"].strip().lower()
    if "full_name" in values:
        values["full_name"] = values["full_name"].strip()
        if len(values["full_name"]) < 2:
            raise HTTPException(422, "full name is too short")
    with eng.begin() as cx:
        current = cx.execute(text("SELECT password_hash FROM panel_users WHERE id=:id"),
                             {"id": user["id"]}).scalar_one()
        if not verify_password(body.current_password, current):
            raise HTTPException(403, "current password is incorrect")
        if body.new_password:
            values["password_hash"] = hash_password(body.new_password)
        if "username" in values and cx.execute(text("SELECT 1 FROM panel_users WHERE username=:name AND id<>:id"),
                                                 {"name": values["username"], "id": user["id"]}).first():
            raise HTTPException(409, "username already exists")
        cx.execute(text("UPDATE panel_users SET " + ",".join(f"{key}=:{key}" for key in values) +
                        " WHERE id=:id"), {**values, "id": user["id"]})
        if body.new_password:
            token = request.headers.get("authorization", "")[7:]
            cx.execute(text("UPDATE panel_sessions SET revoked_at=:at WHERE user_id=:id AND token_hash<>:hash"),
                       {"at": utcnow(), "id": user["id"], "hash": token_hash(token)})
        row = cx.execute(text("SELECT id,username,full_name,email,role,date_calendar FROM panel_users WHERE id=:id"),
                         {"id": user["id"]}).mappings().one()
    request.state.audit_fields = ["password_reset" if key == "password_hash" else key for key in values]
    return dict(row)


class DatePreferencePatch(BaseModel):
    date_calendar: Literal["jalali", "gregorian"]


@router.patch("/me/preferences")
def update_preferences(body: DatePreferencePatch, request: Request,
                       user: dict = Depends(current_user), eng: Engine = Depends(engine)) -> dict:
    with eng.begin() as cx:
        cx.execute(text("UPDATE panel_users SET date_calendar=:calendar WHERE id=:id"),
                   {"calendar": body.date_calendar, "id": user["id"]})
    request.state.audit_fields = ["date_calendar"]
    return {"date_calendar": body.date_calendar}


@router.get("/notifications")
def notifications(view: Literal["active", "archived"] = "active",
                  audience: Literal["all", "assigned", "delegated", "discussion", "updates"] = "all",
                  limit: int = Query(100, ge=1, le=200),
                  user: dict = Depends(current_user), eng: Engine = Depends(engine)) -> dict:
    with eng.connect() as cx:
        rows = cx.execute(text("""SELECT n.id,n.work_item_id,n.kind,n.audience,n.title,n.body,n.created_at,n.read_at,n.archived_at,
            w.site_id FROM panel_notifications n LEFT JOIN work_items w ON w.id=n.work_item_id
            WHERE n.user_id=:user AND ((:view='active' AND n.archived_at IS NULL) OR
                (:view='archived' AND n.archived_at IS NOT NULL))
                AND (:audience='all' OR n.audience=:audience)
            ORDER BY n.id DESC LIMIT :limit"""),
            {"user": user["id"], "view": view, "audience": audience, "limit": limit}).mappings().all()
        unread = cx.execute(text("SELECT COUNT(*) FROM panel_notifications WHERE user_id=:user AND read_at IS NULL AND archived_at IS NULL"),
                            {"user": user["id"]}).scalar_one()
        archived = cx.execute(text("SELECT COUNT(*) FROM panel_notifications WHERE user_id=:user AND archived_at IS NOT NULL"),
                              {"user": user["id"]}).scalar_one()
    return {"items": [dict(row) for row in rows], "unread": unread, "archived": archived}


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: int, request: Request, user: dict = Depends(current_user),
                      eng: Engine = Depends(engine)) -> dict:
    with eng.begin() as cx:
        result = cx.execute(text("""UPDATE panel_notifications SET read_at=COALESCE(read_at,:at)
            WHERE id=:id AND user_id=:user"""), {"at": utcnow(), "id": notification_id, "user": user["id"]})
        if not result.rowcount:
            raise HTTPException(404, "notification not found")
    request.state.audit_fields = ["read_at"]
    return {"ok": True}


@router.post("/notifications/{notification_id}/archive")
def archive_notification(notification_id: int, request: Request, user: dict = Depends(current_user),
                         eng: Engine = Depends(engine)) -> dict:
    with eng.begin() as cx:
        result = cx.execute(text("""UPDATE panel_notifications SET archived_at=COALESCE(archived_at,:at),
            read_at=COALESCE(read_at,:at) WHERE id=:id AND user_id=:user"""),
            {"at": utcnow(), "id": notification_id, "user": user["id"]})
        if not result.rowcount:
            raise HTTPException(404, "notification not found")
    request.state.audit_fields = ["archived_at", "read_at"]
    return {"ok": True}


@router.post("/notifications/{notification_id}/restore")
def restore_notification(notification_id: int, request: Request, user: dict = Depends(current_user),
                         eng: Engine = Depends(engine)) -> dict:
    with eng.begin() as cx:
        result = cx.execute(text("""UPDATE panel_notifications SET archived_at=NULL
            WHERE id=:id AND user_id=:user"""), {"id": notification_id, "user": user["id"]})
        if not result.rowcount:
            raise HTTPException(404, "notification not found")
    request.state.audit_fields = ["archived_at"]
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, authorization: str | None = Header(default=None), eng: Engine = Depends(engine)) -> dict:
    token = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else ""
    if token:
        with eng.begin() as cx:
            user = session_user(cx, token)
            cx.execute(text("UPDATE panel_sessions SET revoked_at=:at WHERE token_hash=:hash"),
                       {"at": utcnow(), "hash": token_hash(token)})
            if user:
                cx.execute(text("""INSERT INTO panel_audit_log(actor_id,actor_username,actor_role,method,path,status_code,changed_fields,request_id,created_at)
                    VALUES (:id,:username,:role,'POST','/api/v1/auth/logout',200,'[]',:request_id,:at)"""),
                    {"id": user["id"], "username": user["username"], "role": user["role"],
                     "request_id": getattr(request.state, "request_id", None), "at": utcnow()})
    return {"ok": True}


@router.get("/audit")
def audit(limit: int = 100, offset: int = 0, user: dict = Depends(current_user), eng: Engine = Depends(engine)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "فقط مدیر به گزارش فعالیت‌ها دسترسی دارد")
    with eng.connect() as cx:
        total = cx.execute(text("SELECT COUNT(*) FROM panel_audit_log")).scalar_one()
        rows = cx.execute(text("SELECT * FROM panel_audit_log ORDER BY id DESC LIMIT :limit OFFSET :offset"),
                          {"limit": max(1, min(limit, 500)), "offset": max(0, offset)}).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total}
