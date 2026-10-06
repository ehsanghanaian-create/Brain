"""Call-center ledger and operator directory, guarded by the normal API token.

Attribution is an operator decision with a recorded basis. A tel: click is never
silently counted as a completed phone call.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import csv
import hashlib
import io
import json
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, Request
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text

from ...call_center.sheet_import import import_workbook
from ...call_center.attribution import suggest
from ..panel_auth import hash_password
from ..deps import engine
from ..errors import ApiError

router = APIRouter(prefix="/call-center", tags=["call-center"])
Source = Literal["seo", "ads", "direct", "referral", "unknown"]
Basis = Literal["manual", "customer", "gclid", "utm", "import"]
Status = Literal["new", "follow_up", "resolved", "cancelled", "unreviewed"]
Outcome = Literal["pending", "qualified", "unqualified", "order", "lost"]
Confidence = Literal["confirmed", "probable", "unknown"]
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


IMPORT_COLUMNS = {
    "occurred_at": ("occurred_at", "زمان تماس", "تاریخ تماس", "date", "تاریخ"),
    "customer_name": ("customer_name", "نام تماس‌گیرنده", "نام مشتری", "نام"),
    "phone": ("phone", "شماره تماس", "تلفن", "موبایل"),
    "warranty": ("warranty", "گارانتی"),
    "brand": ("brand", "برند"), "model": ("model", "مدل"),
    "region": ("region", "منطقه", "شهر"), "issue": ("issue", "مشکل", "شرح مشکل"),
    "source": ("source", "منبع", "کانال ورودی"),
    "source_note": ("source_note", "توضیح منبع"),
    "campaign": ("campaign", "کمپین"),
    "status": ("status", "وضعیت"), "outcome": ("outcome", "نتیجه"),
    "order_value": ("order_value", "ارزش سفارش"),
    "follow_up_at": ("follow_up_at", "زمان پیگیری"),
    "site_id": ("site_id", "سایت"),
}


def _import_time(value: str) -> str | None:
    if not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("تاریخ باید میلادی و به شکل ISO باشد") from exc
    return utc_time(parsed)


@router.post("/calls/import-workbook")
async def import_call_workbook(file: UploadFile = File(...), dry_run: bool = Form(True),
                               site_id: str | None = Form(None), eng: Engine = Depends(engine)) -> dict:
    data = await file.read(5_000_001)
    try:
        return import_workbook(data, eng, apply=not dry_run, site_id=site_id)
    except ValueError as exc:
        raise ApiError(422, str(exc), code="invalid_workbook") from exc


@router.post("/calls/import")
async def import_calls(file: UploadFile = File(...), dry_run: bool = Form(True),
                       mapping: str | None = Form(None), default_site_id: str | None = Form(None),
                       eng: Engine = Depends(engine)) -> dict:
    raw = await file.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ApiError(413, "فایل CSV باید حداکثر ۲ مگابایت باشد", code="file_too_large")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            decoded = raw.decode("cp1256")
        except UnicodeDecodeError as exc:
            raise ApiError(422, "کدگذاری فایل خوانده نشد", code="invalid_csv") from exc
    try:
        dialect = csv.Sniffer().sniff(decoded[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)
    columns = [str(value).strip() for value in (reader.fieldnames or [])]
    if not columns or len(columns) != len(set(columns)) or any(not value for value in columns):
        raise ApiError(422, "ستون‌های CSV خالی یا تکراری هستند", code="invalid_csv")
    reader.fieldnames = columns
    try:
        overrides = json.loads(mapping) if mapping else {}
    except (TypeError, ValueError) as exc:
        raise ApiError(422, "نگاشت ستون‌ها JSON معتبر نیست", code="invalid_mapping") from exc
    if not isinstance(overrides, dict) or any(key not in IMPORT_COLUMNS or value not in columns for key, value in overrides.items()):
        raise ApiError(422, "نگاشت ستون‌ها معتبر نیست", code="invalid_mapping")
    lookup = {column.casefold(): column for column in columns}
    resolved = {field: overrides.get(field) or next((lookup[alias.casefold()] for alias in aliases if alias.casefold() in lookup), None)
                for field, aliases in IMPORT_COLUMNS.items()}
    rows = list(reader)
    if len(rows) > 1000:
        raise ApiError(413, "هر بار حداکثر ۱۰۰۰ ردیف وارد کنید", code="too_many_rows")
    if not rows:
        raise ApiError(422, "فایل CSV ردیفی ندارد", code="invalid_csv")
    if not resolved["phone"]:
        raise ApiError(422, "ستون شماره تماس را نگاشت کنید", code="invalid_mapping")
    errors: list[dict] = []
    preview: list[dict] = []
    imported = skipped = valid = 0
    seen_keys: set[str] = set()
    at = now()
    known_sources = {"seo": "seo", "سئو": "seo", "google": "seo", "گوگل": "seo", "organic": "seo",
                     "ads": "ads", "ادز": "ads", "google ads": "ads", "تبلیغات": "ads",
                     "direct": "direct", "مستقیم": "direct", "referral": "referral", "ارجاع": "referral"}
    with eng.begin() as cx:
        site_ids = {str(row[0]) for row in cx.execute(text("""SELECT site_id FROM sites
            WHERE site_id NOT IN (SELECT site_id FROM manual_projects)""")).all()}
        if default_site_id and default_site_id not in site_ids:
            raise ApiError(422, "سایت پیش‌فرض پیدا نشد", code="validation_error")
        for index, row in enumerate(rows, start=2):
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("تعداد سلول‌ها با سرستون برابر نیست")
                get = lambda field: str(row.get(resolved[field]) or "").strip() if resolved[field] else ""
                name, phone = get("customer_name")[:160], clean_phone(get("phone"))
                if not any(char.isdigit() for char in phone):
                    raise ValueError("شماره تماس الزامی است")
                site_id = get("site_id") or default_site_id or None
                if site_id and site_id not in site_ids:
                    raise ValueError("شناسه سایت پیدا نشد")
                raw_source = get("source")
                source = known_sources.get(raw_source.casefold(), "unknown")
                note = get("source_note")
                if raw_source and source == "unknown":
                    note = (f"منبع اصلی: {raw_source}; " + note)[:500]
                raw_outcome = get("outcome")
                outcome = {"سفارش": "order", "واجدکیفیت": "qualified", "فاقدکیفیت": "unqualified",
                           "از دست‌رفته": "lost", "در انتظار نتیجه": "pending"}.get(raw_outcome, raw_outcome or "pending")
                if outcome not in ("pending", "qualified", "unqualified", "order", "lost"):
                    raise ValueError("نتیجه تماس نامعتبر است")
                raw_status = get("status")
                status = {"جدید": "new", "پیگیری": "follow_up", "انجام‌شده": "resolved",
                          "کنسل‌شده": "cancelled", "بازبینی نشده": "unreviewed"}.get(raw_status, raw_status or "unreviewed")
                if status not in ("new", "follow_up", "resolved", "cancelled", "unreviewed"):
                    raise ValueError("وضعیت تماس نامعتبر است")
                raw_value = get("order_value").replace(",", "")
                order_value = int(raw_value) if raw_value else None
                if order_value is not None and (order_value < 0 or outcome != "order"):
                    raise ValueError("ارزش سفارش فقط برای نتیجه سفارش و به‌صورت عدد مثبت پذیرفته می‌شود")
                values = {"site_id": site_id, "occurred_at": _import_time(get("occurred_at")), "customer_name": name,
                          "phone": phone, "warranty": int(get("warranty").casefold() in ("1", "true", "yes", "بله")),
                          "brand": get("brand")[:100], "model": get("model")[:100], "region": get("region")[:120],
                          "issue": get("issue")[:2000], "source": source, "source_basis": "import",
                          "source_note": note[:500], "campaign": get("campaign")[:120], "status": status,
                          "outcome": outcome, "order_value": order_value, "follow_up_at": _import_time(get("follow_up_at")),
                          "source_confidence": "unknown", "operator_id": None, "at": at}
                fingerprint = json.dumps({key: (value or "").strip() for key, value in sorted(row.items())}, ensure_ascii=False, sort_keys=True)
                values["import_key"] = "csv:" + hashlib.sha256(fingerprint.encode()).hexdigest()
                valid += 1
                if len(preview) < 5:
                    preview.append({key: values[key] for key in ("customer_name", "phone", "occurred_at", "source", "site_id", "region", "outcome")})
                if values["import_key"] in seen_keys or cx.execute(text("SELECT 1 FROM call_center_calls WHERE import_key=:import_key"), values).first():
                    skipped += 1
                    continue
                seen_keys.add(values["import_key"])
                if not dry_run:
                    columns_to_insert = [key for key in values if key != "at"]
                    cx.execute(text("INSERT INTO call_center_calls(" + ",".join(columns_to_insert) +
                                    ",created_at,updated_at) VALUES (" + ",".join(":" + key for key in columns_to_insert) +
                                    ",:at,:at)"), values)
                    imported += 1
            except (ValueError, TypeError) as exc:
                errors.append({"row": index, "error": str(exc)})
    return {"columns": columns, "mapping": resolved, "rows_total": len(rows), "rows_valid": valid,
            "rows_imported": imported, "rows_skipped": skipped, "errors_count": len(errors), "errors": errors[:30],
            "preview": preview, "dry_run": dry_run}


class UserIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z][a-zA-Z0-9_.-]*$")
    password: str = Field(min_length=12, max_length=256)
    role: Role = "call_center"
    team_id: int | None = Field(default=None, ge=1)
    active: bool = True


class UserPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    username: str | None = Field(default=None, min_length=3, max_length=40, pattern=r"^[a-zA-Z][a-zA-Z0-9_.-]*$")
    password: str | None = Field(default=None, min_length=12, max_length=256)
    role: Role | None = None
    team_id: int | None = Field(default=None, ge=1)
    active: bool | None = None


class CallIn(BaseModel):
    site_id: str | None = Field(default=None, max_length=120)
    occurred_at: datetime | None = None
    customer_name: str = Field(default="", max_length=160)
    phone: str = Field(min_length=1, max_length=30)
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
    outcome: Outcome = "pending"
    order_value: int | None = Field(default=None, ge=0)
    follow_up_at: datetime | None = None
    source_confidence: Confidence = "unknown"
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
    outcome: Outcome | None = None
    order_value: int | None = Field(default=None, ge=0)
    follow_up_at: datetime | None = None
    source_confidence: Confidence | None = None
    operator_id: int | None = None


def _call_row(row) -> dict:
    out = dict(row)
    out["warranty"] = bool(out["warranty"])
    return out


def _user_row(row) -> dict:
    out = dict(row)
    out["has_password"] = bool(out.get("password_hash"))
    out.pop("password_hash", None)
    out["active"] = bool(out["active"])
    return out


@router.get("/users")
def users(eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        rows = cx.execute(text("SELECT * FROM panel_users ORDER BY active DESC, full_name")).mappings().all()
    return [_user_row(row) for row in rows]


@router.get("/operators")
def operators(eng: Engine = Depends(engine)) -> list[dict]:
    with eng.connect() as cx:
        rows = cx.execute(text("SELECT id, full_name, active, team_id, role FROM panel_users ORDER BY active DESC, full_name")).mappings().all()
    return [dict(row) for row in rows]


@router.post("/users", status_code=201)
def create_user(body: UserIn, request: Request, eng: Engine = Depends(engine)) -> dict:
    values = body.model_dump()
    values["username"] = values["username"].strip().lower()
    values["password_hash"] = hash_password(values.pop("password"))
    values["email"] = values["email"].strip().lower()
    values["full_name"] = values["full_name"].strip()
    if len(values["full_name"]) < 2 or "@" not in values["email"]:
        raise ApiError(422, "نام یا ایمیل معتبر نیست", code="validation_error")
    values["active"] = int(values["active"])
    values["at"] = now()
    with eng.begin() as cx:
        if getattr(request.state, "panel_user", None) and request.state.panel_user["role"] != "admin":
            raise ApiError(403, "فقط مدیر می‌تواند کاربر بسازد", code="forbidden")
        if cx.execute(text("SELECT 1 FROM panel_users WHERE username=:username"), values).first():
            raise ApiError(409, "این نام کاربری قبلاً ثبت شده است", code="conflict")
        if cx.execute(text("SELECT 1 FROM panel_users WHERE email=:email"), values).first():
            raise ApiError(409, "این ایمیل قبلاً ثبت شده است", code="conflict")
        if values["team_id"] is not None and not cx.execute(text("SELECT 1 FROM panel_teams WHERE id=:id AND active=1"), {"id": values["team_id"]}).first():
            raise ApiError(422, "تیم فعال پیدا نشد", code="validation_error")
        uid = cx.execute(text("""INSERT INTO panel_users(full_name,email,username,password_hash,role,team_id,active,created_at,updated_at)
            VALUES (:full_name,:email,:username,:password_hash,:role,:team_id,:active,:at,:at)"""), values).lastrowid
        row = cx.execute(text("SELECT * FROM panel_users WHERE id=:id"), {"id": uid}).mappings().one()
    request.state.audit_fields = ["full_name", "email", "username", "role", "team_id", "active"]
    return _user_row(row)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, request: Request, eng: Engine = Depends(engine)) -> dict:
    values = body.model_dump(exclude_unset=True)
    if getattr(request.state, "panel_user", None) and request.state.panel_user["role"] != "admin":
        raise ApiError(403, "فقط مدیر می‌تواند کاربر را تغییر دهد", code="forbidden")
    if not values:
        raise ApiError(400, "تغییری ارسال نشده است", code="bad_request")
    if any(value is None for key, value in values.items() if key != "team_id"):
        raise ApiError(422, "فیلدهای کاربر نمی‌توانند خالی باشند", code="validation_error")
    if "email" in values and values["email"] is not None:
        values["email"] = values["email"].strip().lower()
    if "username" in values and values["username"] is not None:
        values["username"] = values["username"].strip().lower()
    if "password" in values:
        values["password_hash"] = hash_password(values.pop("password"))
    request.state.audit_fields = ["password" if key == "password_hash" else key for key in values]
    if "full_name" in values and values["full_name"] is not None:
        values["full_name"] = values["full_name"].strip()
    if ("full_name" in values and len(values["full_name"]) < 2) or ("email" in values and "@" not in values["email"]):
        raise ApiError(422, "نام یا ایمیل معتبر نیست", code="validation_error")
    if "active" in values:
        values["active"] = int(values["active"])
    with eng.begin() as cx:
        current_user = cx.execute(text("SELECT id,role,active FROM panel_users WHERE id=:id"), {"id": user_id}).mappings().first()
        if not current_user:
            raise ApiError(404, "کاربر پیدا نشد", code="not_found")
        if current_user["role"] == "admin" and current_user["active"] and (values.get("role", "admin") != "admin" or values.get("active", 1) == 0):
            if cx.execute(text("SELECT COUNT(*) FROM panel_users WHERE role='admin' AND active=1")).scalar_one() <= 1:
                raise ApiError(422, "آخرین مدیر فعال را نمی‌توان غیرفعال کرد", code="validation_error")
        if "username" in values and cx.execute(text("SELECT 1 FROM panel_users WHERE username=:username AND id<>:id"), {"username": values["username"], "id": user_id}).first():
            raise ApiError(409, "این نام کاربری قبلاً ثبت شده است", code="conflict")
        if "email" in values and cx.execute(text("SELECT 1 FROM panel_users WHERE email=:email AND id<>:id"), {"email": values["email"], "id": user_id}).first():
            raise ApiError(409, "این ایمیل قبلاً ثبت شده است", code="conflict")
        if values.get("team_id") is not None and not cx.execute(text("SELECT 1 FROM panel_teams WHERE id=:id AND active=1"), {"id": values["team_id"]}).first():
            raise ApiError(422, "تیم فعال پیدا نشد", code="validation_error")
        cx.execute(text("UPDATE panel_users SET " + ", ".join(f"{key}=:{key}" for key in values) + ", updated_at=:at WHERE id=:id"), {**values, "at": now(), "id": user_id})
        if "username" in values or "password_hash" in values or "role" in values or values.get("active") == 0:
            cx.execute(text("UPDATE panel_sessions SET revoked_at=:at WHERE user_id=:id AND revoked_at IS NULL"), {"at": now(), "id": user_id})
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
def create_call(body: CallIn, request: Request, eng: Engine = Depends(engine)) -> dict:
    values = body.model_dump()
    values["occurred_at"] = utc_time(body.occurred_at or datetime.now(timezone.utc))
    values["follow_up_at"] = utc_time(body.follow_up_at) if body.follow_up_at else None
    values["phone"] = clean_phone(body.phone)
    if not any(char.isdigit() for char in values["phone"]):
        raise ApiError(422, "شماره تماس الزامی است", code="validation_error")
    values["warranty"] = int(body.warranty)
    values["site_id"] = values["site_id"] or None
    values["at"] = now()
    if values["source"] == "ads" and values["source_basis"] in ("gclid", "utm") and not (values["source_note"] or values["campaign"]):
        raise ApiError(422, "برای منبع ادز، شناسه یا توضیح شواهد را ثبت کنید", code="validation_error")
    if values["outcome"] != "order" and values["order_value"] is not None:
        raise ApiError(422, "ارزش سفارش فقط برای نتیجهٔ سفارش ثبت می‌شود", code="validation_error")
    columns = ("site_id", "occurred_at", "customer_name", "phone", "warranty", "brand", "model", "region", "issue", "source", "source_basis", "source_note", "campaign", "status", "outcome", "order_value", "follow_up_at", "source_confidence", "operator_id", "import_key")
    with eng.begin() as cx:
        if values["import_key"] and cx.execute(text("SELECT 1 FROM call_center_calls WHERE import_key=:import_key"), values).first():
            raise ApiError(409, "این ردیف قبلاً وارد شده است", code="conflict")
        if values["operator_id"] and not cx.execute(text("SELECT 1 FROM panel_users WHERE id=:operator_id AND active=1"), values).first():
            raise ApiError(422, "اپراتور فعال پیدا نشد", code="validation_error")
        attribution = suggest(cx, values["site_id"], values["occurred_at"]) if values["source"] == "unknown" else {}
        if attribution.get("auto_attributed"):
            values.update({key: attribution[key] for key in ("source", "source_confidence", "source_basis")})
        values["attribution_event"] = attribution.get("attribution_event")
        values["attribution_checked_at"] = attribution.get("attribution_checked_at")
        values["auto_attributed"] = attribution.get("auto_attributed", 0)
        values["attribution_locked"] = int(values["source"] != "unknown" and not values["auto_attributed"])
        columns += ("attribution_event", "attribution_checked_at", "auto_attributed", "attribution_locked")
        result = cx.execute(text("INSERT INTO call_center_calls(" + ",".join(columns) + ",created_at,updated_at) VALUES (" + ",".join(":" + c for c in columns) + ",:at,:at)"), values)
        row = cx.execute(text("SELECT c.*, u.full_name AS operator_name FROM call_center_calls c LEFT JOIN panel_users u ON u.id=c.operator_id WHERE c.id=:id"), {"id": result.lastrowid}).mappings().one()
    request.state.audit_fields = list(body.model_fields_set)
    return _call_row(row)


@router.patch("/calls/{call_id}")
def update_call(call_id: int, body: CallPatch, request: Request, eng: Engine = Depends(engine)) -> dict:
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise ApiError(400, "تغییری ارسال نشده است", code="bad_request")
    if any(value is None for key, value in values.items() if key not in ("site_id", "operator_id", "occurred_at", "order_value", "follow_up_at")):
        raise ApiError(422, "این فیلد تماس نمی‌تواند خالی باشد", code="validation_error")
    if isinstance(values.get("occurred_at"), datetime):
        values["occurred_at"] = utc_time(values["occurred_at"])
    if isinstance(values.get("follow_up_at"), datetime):
        values["follow_up_at"] = utc_time(values["follow_up_at"])
    if "phone" in values and values["phone"] is not None:
        values["phone"] = clean_phone(values["phone"])
        if not any(char.isdigit() for char in values["phone"]):
            raise ApiError(422, "شماره تماس الزامی است", code="validation_error")
    if "warranty" in values:
        values["warranty"] = int(values["warranty"])
    values["at"] = now()
    values["id"] = call_id
    with eng.begin() as cx:
        current = cx.execute(text("SELECT outcome, order_value, site_id, occurred_at, source, auto_attributed FROM call_center_calls WHERE id=:id"), values).mappings().first()
        if not current:
            raise ApiError(404, "تماس پیدا نشد", code="not_found")
        resulting_outcome = values.get("outcome", current["outcome"])
        resulting_value = values.get("order_value", current["order_value"])
        if resulting_outcome != "order" and resulting_value is not None:
            raise ApiError(422, "ارزش سفارش فقط برای نتیجهٔ سفارش ثبت می‌شود", code="validation_error")
        if values.get("operator_id") is not None and not cx.execute(text("SELECT 1 FROM panel_users WHERE id=:operator_id AND active=1"), values).first():
            raise ApiError(422, "اپراتور فعال پیدا نشد", code="validation_error")
        if "source" in values:
            values.update(auto_attributed=0, attribution_event=None, attribution_locked=1, source_confidence="unknown")
        elif ("site_id" in values or "occurred_at" in values) and (current["source"] == "unknown" or current["auto_attributed"]):
            attribution = suggest(cx, values.get("site_id", current["site_id"]), values.get("occurred_at", current["occurred_at"]), call_id)
            values.update(attribution)
        cx.execute(text("UPDATE call_center_calls SET " + ", ".join(f"{key}=:{key}" for key in values if key not in ("id", "at")) + ", updated_at=:at WHERE id=:id"), values)
        row = cx.execute(text("SELECT c.*, u.full_name AS operator_name FROM call_center_calls c LEFT JOIN panel_users u ON u.id=c.operator_id WHERE c.id=:id"), values).mappings().one()
    request.state.audit_fields = list(body.model_fields_set)
    return _call_row(row)


@router.post("/reconcile")
def reconcile_calls(site_id: str | None = None, limit: int = Query(500, ge=1, le=2000), force: bool = True,
                    eng: Engine = Depends(engine)) -> dict:
    """Recheck late-entered calls after web click logs arrive; manual decisions are preserved."""
    checked = changed = 0
    with eng.begin() as cx:
        rows = cx.execute(text("""SELECT id, site_id, occurred_at, source, auto_attributed
            FROM call_center_calls WHERE attribution_locked=0 AND (source='unknown' OR auto_attributed=1)
              AND (:site_id IS NULL OR site_id=:site_id)
              AND site_id IS NOT NULL AND occurred_at IS NOT NULL
              AND (:force=1 OR attribution_checked_at IS NULL OR attribution_checked_at < :retry_before)
            ORDER BY attribution_checked_at IS NOT NULL, attribution_checked_at, id DESC LIMIT :limit"""),
            {"site_id": site_id, "limit": limit, "force": int(force),
             "retry_before": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="seconds")}).mappings().all()
        for row in rows:
            result = suggest(cx, row["site_id"], row["occurred_at"], row["id"])
            checked += 1
            if result["source"] != row["source"]:
                changed += 1
            cx.execute(text("""UPDATE call_center_calls SET source=:source, source_basis=:source_basis,
                source_confidence=:source_confidence, attribution_event=:attribution_event,
                attribution_checked_at=:attribution_checked_at, auto_attributed=:auto_attributed,
                updated_at=:updated_at WHERE id=:id"""), {**result, "id": row["id"], "updated_at": now()})
    return {"checked": checked, "changed": changed}


@router.get("/analytics")
def analytics(days: int = Query(30, ge=1, le=366), site_id: str | None = None, source: Source | None = None,
              eng: Engine = Depends(engine)) -> dict:
    current = datetime.now(timezone.utc)
    scope = (" AND site_id=:site_id" if site_id else "") + (" AND source=:source" if source else "")
    where = "occurred_at >= :since AND occurred_at <= :now" + scope
    args = {"since": (current - timedelta(days=days)).isoformat(timespec="seconds"), "now": current.isoformat(timespec="seconds")}
    if site_id:
        args["site_id"] = site_id
    if source:
        args["source"] = source
    with eng.connect() as cx:
        records = cx.execute(text("SELECT occurred_at, source, warranty, brand, model, region, status, outcome, order_value, source_confidence FROM call_center_calls WHERE " + where), args).mappings().all()
        undated_where = "occurred_at IS NULL" + scope
        undated = cx.execute(text("SELECT COUNT(*) FROM call_center_calls WHERE " + undated_where), args).scalar_one()
        future_where = "occurred_at > :now" + scope
        future = cx.execute(text("SELECT COUNT(*) FROM call_center_calls WHERE " + future_where), args).scalar_one()
    from collections import Counter
    by_source = Counter(row["source"] for row in records)
    by_brand = Counter(row["brand"] for row in records if row["brand"])
    by_model = Counter(row["model"] for row in records if row["model"])
    by_region = Counter(row["region"] for row in records if row["region"])
    by_status = Counter(row["status"] for row in records)
    by_outcome = Counter(row["outcome"] for row in records)
    by_source_outcome = {key: {"total": 0, "qualified": 0, "orders": 0, "order_value": 0, "unknown_confidence": 0}
                         for key in ("seo", "ads", "direct", "referral", "unknown")}
    for row in records:
        bucket = by_source_outcome[row["source"]]
        bucket["total"] += 1
        bucket["qualified"] += row["outcome"] in ("qualified", "order")
        bucket["orders"] += row["outcome"] == "order"
        bucket["order_value"] += int(row["order_value"] or 0) if row["outcome"] == "order" else 0
        bucket["unknown_confidence"] += row["source_confidence"] == "unknown"
    by_day_source = Counter((row["occurred_at"][:10], row["source"]) for row in records)
    days_series = sorted({day for day, _ in by_day_source})
    return {
        "total": len(records), "by_source": {source: by_source[source] for source in ("seo", "ads", "direct", "referral", "unknown")}, "by_brand": by_brand.most_common(10),
        "by_model": by_model.most_common(10), "by_region": by_region.most_common(10),
        "by_status": {status: by_status[status] for status in ("new", "follow_up", "resolved", "cancelled", "unreviewed")}, "warranty": sum(bool(row["warranty"]) for row in records),
        "by_outcome": {key: by_outcome[key] for key in ("pending", "qualified", "unqualified", "order", "lost")},
        "by_source_outcome": by_source_outcome,
        "daily": [{"date": day, **{source: by_day_source[(day, source)] for source in ("seo", "ads", "direct", "referral", "unknown")}} for day in days_series],
        "days": days, "undated": undated, "future": future, "generated_at": now(),
    }
