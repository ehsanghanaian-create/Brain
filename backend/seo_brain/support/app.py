"""Private support sidecar. Only the authenticated frontend proxy supplies actors.

No SEO database, Google credentials or background scheduler is used here.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import unquote
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator

app = FastAPI(title="SEO Brain support", docs_url=None, redoc_url=None, openapi_url=None)

SCHEMA = """
CREATE TABLE IF NOT EXISTS support_tickets (
 id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, subject TEXT NOT NULL,
 category TEXT NOT NULL CHECK(category IN ('problem','question','idea')),
 site_id TEXT, context_path TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','waiting','closed')),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_support_owner_time ON support_tickets(owner,updated_at);
CREATE TABLE IF NOT EXISTS support_messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
 author TEXT NOT NULL, is_staff INTEGER NOT NULL DEFAULT 0 CHECK(is_staff IN (0,1)),
 body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_support_messages_ticket ON support_messages(ticket_id,id);
"""


@contextmanager
def database():
    path = Path(os.environ.get("SUPPORT_DB_PATH", "data/support.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(path, timeout=10)
    cx.row_factory = sqlite3.Row
    try:
        cx.execute("PRAGMA foreign_keys=ON")
        cx.execute("PRAGMA journal_mode=WAL")
        cx.executescript(SCHEMA)
        with cx:
            yield cx
    finally:
        cx.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def staff(actor: str) -> bool:
    return actor in {name.strip() for name in os.environ.get("SUPPORT_STAFF_ACCOUNTS", "").split(",") if name.strip()}


def actor(x_api_token: str | None = Header(None), x_seo_actor: str | None = Header(None)) -> str:
    expected = os.environ.get("SUPPORT_API_TOKEN", "")
    if not expected:
        raise HTTPException(503, "پشتیبانی هنوز پیکربندی نشده است")
    if not x_api_token or not secrets.compare_digest(x_api_token, expected):
        raise HTTPException(401, "دسترسی تأیید نشد")
    try:
        x_seo_actor = unquote(x_seo_actor or '', errors='strict')
    except UnicodeDecodeError:
        raise HTTPException(401, "حساب کاربری تأیید نشد")
    if not x_seo_actor or len(x_seo_actor) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in x_seo_actor):
        raise HTTPException(401, "حساب کاربری تأیید نشد؛ دوباره وارد شوید")
    return x_seo_actor


@app.exception_handler(HTTPException)
async def error(request: Request, exc: HTTPException):
    return JSONResponse({"error": {"code": f"support_{exc.status_code}", "message": exc.detail,
                                    "request_id": request.headers.get("x-request-id")}}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse({"error": {"code": "invalid_support_request", "message": "عنوان و توضیحات معتبر وارد کنید؛ توضیحات درخواست حداقل ۵ حرف است.", "request_id": request.headers.get("x-request-id")}}, status_code=422)


class TicketBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=5, max_length=5000)
    category: Literal["problem", "question", "idea"] = "problem"
    site_id: str | None = Field(None, max_length=80)
    context_path: str = Field("", max_length=500)

    @field_validator("context_path")
    @classmethod
    def path_only(cls, value: str) -> str:
        value = value.split("?", 1)[0].split("#", 1)[0]
        if value and not (value == "/ads-data" or value.startswith("/dashboard/")):
            raise ValueError("only a product page path is allowed")
        return value


class MessageBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=2, max_length=5000)
    as_support: bool = False


class StatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["open", "closed"]


def ticket(cx: sqlite3.Connection, ticket_id: int, who: str) -> dict:
    row = cx.execute("SELECT * FROM support_tickets WHERE id=?", (ticket_id,)).fetchone()
    if not row or (row["owner"] != who and not staff(who)):
        raise HTTPException(404, "درخواست پیدا نشد")
    return {**dict(row), "reference": f"SB-{row['id']:06d}"}


def detail(cx: sqlite3.Connection, ticket_id: int, who: str) -> dict:
    result = ticket(cx, ticket_id, who)
    result["messages"] = [dict(row) for row in cx.execute(
        "SELECT id,author,is_staff,body,created_at FROM support_messages WHERE ticket_id=? ORDER BY id", (ticket_id,))]
    return result


@app.get("/health")
def health():
    with database() as cx:
        cx.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/api/v1/support/tickets")
def list_tickets(status: Literal["all", "open", "waiting", "closed"] = "all", limit: int = Query(50, ge=1, le=100),
                 offset: int = Query(0, ge=0), who: str = Depends(actor)):
    is_staff = staff(who)
    params = {"actor": who, "staff": int(is_staff), "status": status, "limit": limit, "offset": offset}
    where = "WHERE (:staff=1 OR t.owner=:actor) AND (:status='all' OR t.status=:status)"
    with database() as cx:
        total = cx.execute("SELECT COUNT(*) FROM support_tickets t " + where, params).fetchone()[0]
        rows = cx.execute("SELECT t.*, (SELECT COUNT(*) FROM support_messages m WHERE m.ticket_id=t.id) message_count "
                          "FROM support_tickets t " + where + " ORDER BY t.updated_at DESC,t.id DESC LIMIT :limit OFFSET :offset", params)
        items = [{**dict(row), "reference": f"SB-{row['id']:06d}"} for row in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset, "is_staff": is_staff, "account": who}


@app.post("/api/v1/support/tickets", status_code=201)
def create_ticket(body: TicketBody, who: str = Depends(actor)):
    at = now()
    with database() as cx:
        row = cx.execute("INSERT INTO support_tickets(owner,subject,category,site_id,context_path,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                         (who, body.subject, body.category, body.site_id, body.context_path, at, at))
        ticket_id = row.lastrowid
        cx.execute("INSERT INTO support_messages(ticket_id,author,is_staff,body,created_at) VALUES(?,?,0,?,?)", (ticket_id, who, body.message, at))
        return detail(cx, ticket_id, who)


@app.get("/api/v1/support/tickets/{ticket_id}")
def get_ticket(ticket_id: int, who: str = Depends(actor)):
    with database() as cx:
        return detail(cx, ticket_id, who)


@app.post("/api/v1/support/tickets/{ticket_id}/messages", status_code=201)
def add_message(ticket_id: int, body: MessageBody, who: str = Depends(actor)):
    if body.as_support and not staff(who):
        raise HTTPException(403, "پاسخ پشتیبانی فقط برای مسئول رسیدگی فعال است")
    with database() as cx:
        ticket(cx, ticket_id, who)
        at = now()
        cx.execute("INSERT INTO support_messages(ticket_id,author,is_staff,body,created_at) VALUES(?,?,?,?,?)",
                   (ticket_id, who, int(body.as_support), body.message, at))
        cx.execute("UPDATE support_tickets SET status=?,updated_at=? WHERE id=?", ("waiting" if body.as_support else "open", at, ticket_id))
        return detail(cx, ticket_id, who)


@app.patch("/api/v1/support/tickets/{ticket_id}")
def set_status(ticket_id: int, body: StatusBody, who: str = Depends(actor)):
    with database() as cx:
        ticket(cx, ticket_id, who)
        cx.execute("UPDATE support_tickets SET status=?,updated_at=? WHERE id=?", (body.status, now(), ticket_id))
        return detail(cx, ticket_id, who)
