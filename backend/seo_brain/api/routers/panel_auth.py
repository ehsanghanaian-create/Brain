"""Individual panel login and administrator audit viewer."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text

from ..deps import engine
from ..panel_auth import create_session, session_user, token_hash, utcnow

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
            row = cx.execute(text("SELECT id,username,full_name,email,role,active,password_hash FROM panel_users WHERE username=:username"),
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
    return {"token": token, "user": {key: row[key] for key in ("id", "username", "full_name", "email", "role")}}



def current_user(authorization: str | None = Header(default=None), eng: Engine = Depends(engine)) -> dict:
    token = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else ""
    with eng.connect() as cx:
        user = session_user(cx, token)
    if not user:
        raise HTTPException(401, "نشست معتبر نیست")
    return {key: user[key] for key in ("id", "username", "full_name", "email", "role")}


@router.get("/me")
def me(user: dict = Depends(current_user)) -> dict:
    return user


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
