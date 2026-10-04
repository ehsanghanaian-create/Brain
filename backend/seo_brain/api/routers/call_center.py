"""Call-center ledger and operator directory, guarded by the normal API token.

Attribution is an operator decision with a recorded basis. A tel: click is never
silently counted as a completed phone call.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text

from ..deps import engine
from ..errors import ApiError

router = APIRouter(prefix="/call-center", tags=["call-center"])
Source = Literal["seo", "ads", "direct", "referral", "unknown"]
Basis = Literal["manual", "customer", "gclid", "utm", "import"]
Status = Literal["new", "follow_up", "resolved", "cancelled", "unreviewed"]
Role = Literal["admin", "analyst", "call_center"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def utc_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone(timedelta(hours=3, minutes=30)))
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def clean_phone(value: str) -> str:
    digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return "".join(c for c in value.translate(digits) if c.isdigit() or c == "+")[:30]


class UserIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    role: Role = "call_center"
    active: bool = True


class UserPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    role: Role | None = None
    active: bool | None = None


class CallIn(BaseModel):
    site_id: str | None = Field(default=None, max_length=120)
    occurred_at: datetime | None = None
    customer_name: str = Field(default="", max_length=160)
    phone: str = Field(default="", max_length=30)
    warranty: bool = False
    brand: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=100)
    region: str = Field(default="", max_length=120)
    issue: str = Field(default="", max_length=2000)
    source: Source = "unknown"
    source_basis: Basis = "manual"
    source_note: str = Field(default="", max_length=500)
    campaign: str = Field(default="", max_length=120)
    status: Status = "new"
    operator_id: int | None = None
    import_key: str | None = Field(default=None, max_length=160)


class CallPatch(BaseModel):
    site_id: str | None = Field(default=None, max_length=120)
    occurred_at: datetime | None = None
    customer_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=30)
    warranty: bool | None = None
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=120)
    issue: str | None = Field(default=None, max_length=2000)
    source: Source | None = None
    source_basis: Basis | None = None
    source_note: str | None = Field(default=None, max_length=500)
    campaign: str | None = Field(default=None, max_length=120)
    status: Status | None = None
    operator_id: int | None = None


def _call_row(row) -> dict:
    out = dict(row)
    out["warranty"] = bool(out["warranty"])
    return out


def _user_row(row) -> dict:
    out = dict(row)
    out["active"] = bool(out["active"])
    return out


@router.get("/users")
def users(eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        rows = cx.execute(text("SELECT * FROM panel_users ORDER BY active DESC, full_name")).mappings().all()
    return [_user_row(row) for row in rows]


@router.post("/users", status_code=201)
def create_user(body: UserIn, eng: Engine = Depends(engine)) -> dict:
    values = body.model_dump()
    values["email"] = values["email"].strip().lower()
    values["full_name"] = values["full_name"].strip()
    if len(values["full_name"]) < 2 or "@" not in values["email"]:
        raise ApiError(422, "نام یا ایمیل معتبر نیست", code="validation_error")
    values["active"] = int(values["active"])
    values["at"] = now()
    with eng.begin() as cx:
        if cx.execute(text("SELECT 1 FROM panel_users WHERE email=:email"), values).first():
            raise ApiError(409, "این ایمیل قبلاً ثبت شده است", code="conflict")
        uid = cx.execute(text("""INSERT INTO panel_users(full_name,email,role,active,created_at,updated_at)
            VALUES (:full_name,:email,:role,:active,:at,:at)"""), values).lastrowid
        row = cx.execute(text("SELECT * FROM panel_users WHERE id=:id"), {"id": uid}).mappings().one()
    return _user_row(row)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, eng: Engine = Depends(engine)) -> dict:
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise ApiError(400, "تغییری ارسال نشده است", code="bad_request")
    if any(value is None for value in values.values()):
        raise ApiError(422, "فیلدهای کاربر نمی‌توانند خالی باشند", code="validation_error")
    if "email" in values and values["email"] is not None:
        values["email"] = values["email"].strip().lower()
    if "full_name" in values and values["full_name"] is not None:
        values["full_name"] = values["full_name"].strip()
    if ("full_name" in values and len(values["full_name"]) < 2) or ("email" in values and "@" not in values["email"]):
        raise ApiError(422, "نام یا ایمیل معتبر نیست", code="validation_error")
    if "active" in values:
        values["active"] = int(values["active"])
    with eng.begin() as cx:
        if not cx.execute(text("SELECT 1 FROM panel_users WHERE id=:id"), {"id": user_id}).first():
            raise ApiError(404, "کاربر پیدا نشد", code="not_found")
        if "email" in values and cx.execute(text("SELECT 1 FROM panel_users WHERE email=:email AND id<>:id"), {"email": values["email"], "id": user_id}).first():
            raise ApiError(409, "این ایمیل قبلاً ثبت شده است", code="conflict")
        cx.execute(text("UPDATE panel_users SET " + ", ".join(f"{key}=:{key}" for key in values) + ", updated_at=:at WHERE id=:id"), {**values, "at": now(), "id": user_id})
        row = cx.execute(text("SELECT * FROM panel_users WHERE id=:id"), {"id": user_id}).mappings().one()
    return _user_row(row)


@router.get("/calls")
def calls(source: Source | None = None, status: Status | None = None, site_id: str | None = None,
          q: str = Query("", max_length=100), limit: int = Query(100, ge=1, le=500),
          offset: int = Query(0, ge=0),
          eng: Engine = Depends(engine)) -> dict:
    where = ["1=1"]
    args: dict = {"limit": limit, "offset": offset}
    for key, value in (("source", source), ("status", status), ("site_id", site_id)):
        if value:
            where.append(f"c.{key}=:{key}")
            args[key] = value
    if q.strip():
        where.append("(c.customer_name LIKE :q OR c.phone LIKE :q OR c.brand LIKE :q OR c.model LIKE :q OR c.region LIKE :q)")
        args["q"] = "%" + q.strip() + "%"
    with eng.connect() as cx:
        total = cx.execute(text("SELECT COUNT(*) FROM call_center_calls c WHERE " + " AND ".join(where)), args).scalar_one()
        rows = cx.execute(text("""SELECT c.*, u.full_name AS operator_name FROM call_center_calls c
            LEFT JOIN panel_users u ON u.id=c.operator_id WHERE """ + " AND ".join(where) +
            " ORDER BY c.occurred_at IS NULL, c.occurred_at DESC, c.id DESC LIMIT :limit OFFSET :offset"), args).mappings().all()
    return {"items": [_call_row(row) for row in rows], "limit": limit, "offset": offset, "total": total}


@router.post("/calls", status_code=201)
def create_call(body: CallIn, eng: Engine = Depends(engine)) -> dict:
    values = body.model_dump()
    values["occurred_at"] = utc_time(body.occurred_at or datetime.now(timezone.utc))
    values["phone"] = clean_phone(body.phone)
    values["warranty"] = int(body.warranty)
    values["site_id"] = values["site_id"] or None
    values["at"] = now()
    if values["source"] == "ads" and values["source_basis"] in ("gclid", "utm") and not (values["source_note"] or values["campaign"]):
        raise ApiError(422, "برای منبع ادز، شناسه یا توضیح شواهد را ثبت کنید", code="validation_error")
    columns = ("site_id", "occurred_at", "customer_name", "phone", "warranty", "brand", "model", "region", "issue", "source", "source_basis", "source_note", "campaign", "status", "operator_id", "import_key")
    with eng.begin() as cx:
        if values["import_key"] and cx.execute(text("SELECT 1 FROM call_center_calls WHERE import_key=:import_key"), values).first():
            raise ApiError(409, "این ردیف قبلاً وارد شده است", code="conflict")
        if values["operator_id"] and not cx.execute(text("SELECT 1 FROM panel_users WHERE id=:operator_id AND active=1"), values).first():
            raise ApiError(422, "اپراتور فعال پیدا نشد", code="validation_error")
        result = cx.execute(text("INSERT INTO call_center_calls(" + ",".join(columns) + ",created_at,updated_at) VALUES (" + ",".join(":" + c for c in columns) + ",:at,:at)"), values)
        row = cx.execute(text("SELECT c.*, u.full_name AS operator_name FROM call_center_calls c LEFT JOIN panel_users u ON u.id=c.operator_id WHERE c.id=:id"), {"id": result.lastrowid}).mappings().one()
    return _call_row(row)


@router.patch("/calls/{call_id}")
def update_call(call_id: int, body: CallPatch, eng: Engine = Depends(engine)) -> dict:
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise ApiError(400, "تغییری ارسال نشده است", code="bad_request")
    if any(value is None for key, value in values.items() if key not in ("site_id", "operator_id", "occurred_at")):
        raise ApiError(422, "این فیلد تماس نمی‌تواند خالی باشد", code="validation_error")
    if isinstance(values.get("occurred_at"), datetime):
        values["occurred_at"] = utc_time(values["occurred_at"])
    if "phone" in values and values["phone"] is not None:
        values["phone"] = clean_phone(values["phone"])
    if "warranty" in values:
        values["warranty"] = int(values["warranty"])
    values["at"] = now()
    values["id"] = call_id
    with eng.begin() as cx:
        if not cx.execute(text("SELECT 1 FROM call_center_calls WHERE id=:id"), values).first():
            raise ApiError(404, "تماس پیدا نشد", code="not_found")
        if values.get("operator_id") is not None and not cx.execute(text("SELECT 1 FROM panel_users WHERE id=:operator_id AND active=1"), values).first():
            raise ApiError(422, "اپراتور فعال پیدا نشد", code="validation_error")
        cx.execute(text("UPDATE call_center_calls SET " + ", ".join(f"{key}=:{key}" for key in values if key not in ("id", "at")) + ", updated_at=:at WHERE id=:id"), values)
        row = cx.execute(text("SELECT c.*, u.full_name AS operator_name FROM call_center_calls c LEFT JOIN panel_users u ON u.id=c.operator_id WHERE c.id=:id"), values).mappings().one()
    return _call_row(row)


@router.get("/analytics")
def analytics(days: int = Query(30, ge=1, le=366), site_id: str | None = None,
              eng: Engine = Depends(engine)) -> dict:
    current = datetime.now(timezone.utc)
    where = "occurred_at >= :since AND occurred_at <= :now" + (" AND site_id=:site_id" if site_id else "")
    args = {"since": (current - timedelta(days=days)).isoformat(timespec="seconds"), "now": current.isoformat(timespec="seconds")}
    if site_id:
        args["site_id"] = site_id
    with eng.connect() as cx:
        records = cx.execute(text("SELECT occurred_at, source, warranty, brand, model, region, status FROM call_center_calls WHERE " + where), args).mappings().all()
        undated_where = "occurred_at IS NULL" + (" AND site_id=:site_id" if site_id else "")
        undated = cx.execute(text("SELECT COUNT(*) FROM call_center_calls WHERE " + undated_where), args).scalar_one()
        future_where = "occurred_at > :now" + (" AND site_id=:site_id" if site_id else "")
        future = cx.execute(text("SELECT COUNT(*) FROM call_center_calls WHERE " + future_where), args).scalar_one()
    from collections import Counter
    by_source = Counter(row["source"] for row in records)
    by_brand = Counter(row["brand"] for row in records if row["brand"])
    by_model = Counter(row["model"] for row in records if row["model"])
    by_region = Counter(row["region"] for row in records if row["region"])
    by_status = Counter(row["status"] for row in records)
    by_day_source = Counter((row["occurred_at"][:10], row["source"]) for row in records)
    days_series = sorted({day for day, _ in by_day_source})
    return {
        "total": len(records), "by_source": {source: by_source[source] for source in ("seo", "ads", "direct", "referral", "unknown")}, "by_brand": by_brand.most_common(10),
        "by_model": by_model.most_common(10), "by_region": by_region.most_common(10),
        "by_status": {status: by_status[status] for status in ("new", "follow_up", "resolved", "cancelled", "unreviewed")}, "warranty": sum(bool(row["warranty"]) for row in records),
        "daily": [{"date": day, **{source: by_day_source[(day, source)] for source in ("seo", "ads", "direct", "referral", "unknown")}} for day in days_series],
        "days": days, "undated": undated, "future": future, "generated_at": now(),
    }
