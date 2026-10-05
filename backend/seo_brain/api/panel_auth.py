"""Panel accounts, opaque sessions, role checks and safe mutation audit."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets

from fastapi import HTTPException, Request
from sqlalchemy import Engine, text


SESSION_HOURS = 12


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$16384${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        scheme, cost, salt, expected = encoded.split("$", 3)
        if scheme != "scrypt" or int(cost) != 16384:
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(cx, user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    cx.execute(text("""INSERT INTO panel_sessions(token_hash,user_id,created_at,expires_at)
        VALUES (:hash,:user_id,:created,:expires)"""), {
        "hash": token_hash(token), "user_id": user_id, "created": utcnow(),
        "expires": (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")})
    return token


def session_user(cx, token: str) -> dict | None:
    if not token:
        return None
    row = cx.execute(text("""SELECT u.id,u.username,u.full_name,u.email,u.role,u.active,s.expires_at
        FROM panel_sessions s JOIN panel_users u ON u.id=s.user_id
        WHERE s.token_hash=:hash AND s.revoked_at IS NULL"""), {"hash": token_hash(token)}).mappings().first()
    if not row or not row["active"] or row["expires_at"] <= utcnow():
        return None
    return dict(row)


def role_allowed(role: str, path: str, method: str) -> bool:
    if role == "admin":
        return True
    if path.startswith("/api/v1/auth/"):
        return True
    if role == "call_center":
        if path.startswith("/api/v1/call-center/"):
            return not path.startswith("/api/v1/call-center/users") and not path.startswith("/api/v1/call-center/audit")
        if method == "GET" and path == "/api/v1/sites":
            return True
        return method == "GET" and path.endswith(("/traffic/overview", "/traffic/calls")) and path.startswith("/api/v1/sites/")
    if role == "analyst":
        if method != "GET":
            return False
        if path == "/api/v1/call-center/operators":
            return True
        allowed = ("/api/v1/portfolio", "/api/v1/sites", "/api/v1/reports", "/api/v1/traffic",
                   "/api/v1/graph", "/api/v1/keywords", "/api/v1/ads-data", "/api/v1/call-center/analytics")
        return any(path == item or path.startswith(item + "/") for item in allowed)
    return False


def require_panel(request: Request, eng: Engine, *, service_token_valid: bool = False) -> dict | None:
    """Service API token remains for internal automation; browser users use bearer sessions."""
    if service_token_valid:
        request.state.panel_user = None
        return None
    authorization = request.headers.get("authorization", "")
    token = authorization[7:] if authorization.lower().startswith("bearer ") else ""
    with eng.connect() as cx:
        configured = cx.execute(text("SELECT 1 FROM panel_users WHERE password_hash IS NOT NULL LIMIT 1")).first()
        if not configured:
            # Initial local setup remains available until the first admin is provisioned by CLI.
            request.state.panel_user = None
            return None
        user = session_user(cx, token)
    if not user:
        raise HTTPException(401, "ورود به حساب کاربری لازم است")
    if not role_allowed(user["role"], request.url.path, request.method):
        raise HTTPException(403, "دسترسی این نقش به این بخش مجاز نیست")
    request.state.panel_user = user
    return user


def audit_mutation(eng: Engine, request: Request, status_code: int, fields: list[str] | None = None) -> None:
    user = getattr(request.state, "panel_user", None)
    if not user or request.method not in ("POST", "PUT", "PATCH", "DELETE") or status_code >= 400:
        return
    allowed_fields = ["password_reset" if f in {"password", "password_hash"} else f for f in (fields or []) if f != "token"]
    with eng.begin() as cx:
        cx.execute(text("""INSERT INTO panel_audit_log(actor_id,actor_username,actor_role,method,path,status_code,changed_fields,request_id,created_at)
            VALUES (:actor_id,:username,:role,:method,:path,:status,:fields,:request_id,:created)"""), {
            "actor_id": user["id"], "username": user["username"], "role": user["role"],
            "method": request.method, "path": request.url.path, "status": status_code,
            "fields": json.dumps(allowed_fields), "request_id": getattr(request.state, "request_id", None), "created": utcnow()})
