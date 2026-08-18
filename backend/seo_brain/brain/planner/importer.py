"""Content plan import/export: CSV / TSV / XLSX / Google Sheet (public CSV export URL) with Persian+English header aliases,
dry-run report, upsert by url → primary_keyword → title (configurable). Google Sheets is a *source* (content_plan_sources):
today it fetches the sheet's CSV export (read-only, no auth); a Sheets-API implementation can replace `fetch_sheet` later."""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Callable

import httpx

from ...brain.keywords.importer import _norm_header, parse_table
from ...brain.keywords.normalize import normalize_keyword
from .repository import (CONTENT_GAPS, FUNNEL_STAGES, INTENTS, PAGE_TYPES, PLAN_STATUSES, PRIORITIES, COLUMNS, ContentPlan)

FIELD_ALIASES: dict[str, list[str]] = {
    "title": ["title", "عنوان", "عنوان محتوا", "موضوع محتوا", "topic title", "h1"],
    "url": ["url", "آدرس", "لینک", "slug url", "آدرس صفحه"],
    "intent": ["intent", "اینتنت", "هدف جستجو", "search intent", "نیت"],
    "page_type": ["page type", "نوع صفحه", "type", "قالب"],
    "category": ["category", "دسته", "دسته‌بندی", "دسته بندی", "category name"],
    "parent_category": ["parent category", "دسته والد", "دسته مادر"],
    "primary_keyword": ["primary keyword", "کلمه کلیدی اصلی", "کلمه کلیدی", "keyword", "main keyword", "کلمه اصلی"],
    "secondary_keywords": ["secondary keywords", "کلمات کلیدی ثانویه", "کلمات ثانویه", "lsi", "related keywords", "کلمات مرتبط"],
    "heading_structure": ["heading structure", "ساختار سرفصل", "ساختار سرفصل‌ها", "headings", "h2", "outline"],
    "seo_title": ["seo title", "عنوان سئو", "title tag", "meta title"],
    "meta_description": ["meta description", "توضیحات متا", "description", "متا"],
    "publish_date": ["publish date", "تاریخ انتشار", "date", "تاریخ"],
    "status": ["status", "وضعیت"],
    "topic_id": ["topic", "موضوع", "topic id"],
    "cluster_id": ["cluster", "خوشه", "cluster id"],
    "search_volume": ["search volume", "حجم جستجو", "volume", "حجم"],
    "keyword_difficulty": ["keyword difficulty", "سختی کلمه", "kd", "difficulty", "سختی"],
    "priority": ["priority", "اولویت"],
    "target_audience": ["target audience", "مخاطب هدف", "audience", "مخاطب"],
    "business_value": ["business value", "ارزش کسب‌وکار", "ارزش کسب و کار", "value"],
    "serp_intent": ["serp intent", "اینتنت serp"],
    "funnel_stage": ["funnel stage", "مرحله قیف", "funnel"],
    "notes": ["notes", "یادداشت", "توضیحات", "note"],
}
ENUM_ALIASES = {
    "intent": {"اطلاعاتی": "informational", "ناوبری": "navigational", "تجاری": "commercial", "تراکنشی": "transactional", "محلی": "local", "info": "informational", "trans": "transactional"},
    "priority": {"بالا": "high", "متوسط": "medium", "پایین": "low", "زیاد": "high", "کم": "low"},
    "status": {"برنامه‌ریزی‌شده": "planned", "برنامه ریزی شده": "planned", "در حال تحقیق": "researching", "تحقیق": "researching", "بریف آماده": "brief_ready", "در حال نگارش": "writing", "نگارش": "writing", "بازبینی": "review", "تأییدشده": "approved", "تایید شده": "approved", "منتشرشده": "published", "منتشر شده": "published"},
    "page_type": {"لندینگ خدمت": "service_landing", "لندینگ مکان": "location_landing", "ستون": "pillar", "مقاله": "article", "راهنما": "guide", "مقایسه": "comparison", "پرسش": "faq", "محصول": "product", "صفحه دسته": "category_page", "خبر": "news", "landing": "service_landing", "service": "service_landing"},
    "funnel_stage": {"آگاهی": "awareness", "بررسی": "consideration", "تصمیم": "decision", "وفاداری": "retention"},
}
ALLOWED = {"intent": INTENTS, "priority": PRIORITIES, "status": PLAN_STATUSES, "page_type": PAGE_TYPES, "funnel_stage": FUNNEL_STAGES, "serp_intent": INTENTS, "content_gap": CONTENT_GAPS}
EXPORT_COLUMNS = ["id", "title", "url", "intent", "page_type", "category", "parent_category", "primary_keyword", "secondary_keywords", "heading_structure", "seo_title", "meta_description", "publish_date", "status",
                  "cluster_id", "topic_id", "search_volume", "keyword_difficulty", "priority", "priority_score", "target_audience", "existing_pages", "link_targets", "content_score", "graph_connections", "recommendation",
                  "content_gap", "cannibalization_risk", "ranking_url", "serp_intent", "traffic_opportunity", "business_value", "ai_priority", "funnel_stage", "notes"]
FA_OF = {c["key"]: c["fa"] for c in COLUMNS} | {"id": "شناسه", "category": "دسته", "notes": "یادداشت"}


def detect_mapping(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}; used: set[str] = set()
    for col in columns:
        h = _norm_header(col)
        for f, aliases in FIELD_ALIASES.items():
            if f not in used and h in {_norm_header(a) for a in aliases}:
                mapping[col] = f; used.add(f); break
    for col in columns:
        if col in mapping:
            continue
        h = _norm_header(col)
        for f, aliases in FIELD_ALIASES.items():
            if f not in used and any(_norm_header(a) and _norm_header(a) in h for a in aliases):
                mapping[col] = f; used.add(f); break
    return mapping


def _enum(v, field: str) -> str | None:
    if v in (None, ""):
        return None
    s = str(v).strip()
    al = ENUM_ALIASES.get(field, {})
    key = normalize_keyword(s)
    for a, val in al.items():
        if normalize_keyword(a) == key:
            return val
    s2 = s.lower().replace(" ", "_").replace("-", "_")
    return s2 if s2 in ALLOWED.get(field, ()) else None


def _list(v) -> list[str]:
    if v in (None, ""):
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v)
    if s.strip().startswith("["):
        try:
            return [str(x).strip() for x in json.loads(s) if str(x).strip()]
        except ValueError:
            pass
    return [x.strip() for x in re.split(r"[,\n;|،]+", s) if x.strip()]


def _headings(v) -> list[dict[str, Any]]:
    if v in (None, ""):
        return []
    if isinstance(v, list):
        return [x if isinstance(x, dict) else {"level": 2, "text": str(x)} for x in v]
    s = str(v).strip()
    if s.startswith("["):
        try:
            return [x if isinstance(x, dict) else {"level": 2, "text": str(x)} for x in json.loads(s)]
        except ValueError:
            pass
    out = []
    for line in re.split(r"[\n|;]+", s):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(h?)([23])[\.\):\-\s]+(.*)$", line, flags=re.I)
        if m:
            out.append({"level": int(m.group(2)), "text": m.group(3).strip()})
        elif line.startswith("###"):
            out.append({"level": 3, "text": line.lstrip("#").strip()})
        else:
            out.append({"level": 2, "text": line.lstrip("#").strip()})
    return out


def _num(v, kind=float):
    if v in (None, ""):
        return None
    try:
        return kind(str(v).replace("٬", "").replace(",", "").strip())
    except ValueError:
        return None


def normalize_row(raw: dict[str, Any], mapping: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    """Return (fields, warnings). `category` stays as text for the service to resolve."""
    f: dict[str, Any] = {}; warn: list[str] = []
    for col, field in mapping.items():
        v = raw.get(col)
        if v in (None, ""):
            continue
        if field in ("intent", "priority", "status", "page_type", "funnel_stage", "serp_intent"):
            e = _enum(v, field)
            if e is None:
                warn.append(f"مقدار نامعتبر برای {field}: {v}")
            else:
                f[field] = e
        elif field == "secondary_keywords":
            f[field] = _list(v)
        elif field == "heading_structure":
            f[field] = _headings(v)
        elif field in ("search_volume",):
            f[field] = _num(v, int)
        elif field in ("keyword_difficulty", "business_value"):
            f[field] = _num(v, float)
        elif field == "publish_date":
            s = str(v).strip()[:10]
            f[field] = s if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else None
            if f[field] is None:
                warn.append(f"تاریخ نامعتبر (YYYY-MM-DD لازم است): {v}")
        else:
            f[field] = str(v).strip()
    return f, warn


# ------------------------------------------------------------------------- Google Sheet (public CSV export) — future-compatible source
_SHEET_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")


def sheet_csv_url(url: str, gid: str | None = None) -> str:
    m = _SHEET_RE.search(url or "")
    if not m:
        return url
    g = gid
    if g is None:
        mg = re.search(r"[#&?]gid=(\d+)", url)
        g = mg.group(1) if mg else "0"
    return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv&gid={g}"


def fetch_sheet(url: str, gid: str | None = None, fetch: Callable[[str], bytes] | None = None) -> tuple[bytes, str]:
    csv_url = sheet_csv_url(url, gid)
    if fetch:
        return fetch(csv_url), csv_url
    r = httpx.get(csv_url, timeout=30, follow_redirects=True, headers={"User-Agent": "SEO-Brain-Planner/0.1"})
    r.raise_for_status()
    return r.content, csv_url


# ------------------------------------------------------------------------- export
def to_csv(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    cols = [c for c in (columns or EXPORT_COLUMNS) if c in EXPORT_COLUMNS or c in FA_OF]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([FA_OF.get(c, c) for c in cols])
    for r in rows:
        w.writerow([_cell(r.get(c)) for c in cols])
    return "﻿" + buf.getvalue()


def to_xlsx(rows: list[dict[str, Any]], columns: list[str] | None = None) -> bytes:
    import openpyxl  # lazy
    cols = [c for c in (columns or EXPORT_COLUMNS) if c in EXPORT_COLUMNS or c in FA_OF]
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "content-plans"
    ws.sheet_view.rightToLeft = True
    ws.append([FA_OF.get(c, c) for c in cols])
    for r in rows:
        ws.append([_cell(r.get(c)) for c in cols])
    out = io.BytesIO(); wb.save(out)
    return out.getvalue()


def _cell(v) -> Any:
    if v is None:
        return ""
    if isinstance(v, list):
        if v and isinstance(v[0], dict):
            if "text" in v[0]:
                return "\n".join(f"H{x.get('level', 2)}: {x.get('text', '')}" for x in v)
            return "\n".join(str(x.get("url") or x.get("title") or x.get("reason_fa") or json.dumps(x, ensure_ascii=False)) for x in v)
        return ", ".join(str(x) for x in v)
    if isinstance(v, dict):
        return v.get("action_fa") or v.get("action") or (json.dumps(v, ensure_ascii=False) if v else "")
    return v


def template_csv() -> str:
    cols = ["عنوان", "URL", "اینتنت", "نوع صفحه", "دسته", "کلمه کلیدی اصلی", "کلمات کلیدی ثانویه", "ساختار سرفصل‌ها", "عنوان سئو", "توضیحات متا", "تاریخ انتشار", "وضعیت", "حجم جستجو", "سختی کلمه", "اولویت", "مخاطب هدف", "ارزش کسب‌وکار", "یادداشت"]
    ex = ["امداد خودرو X22 تهران", "", "تراکنشی", "لندینگ خدمت", "MVM", "امداد خودرو x22", "امداد خودرو x22 تهران, یدک کش x22", "H2: هزینه امداد | H2: مناطق تحت پوشش | H3: غرب تهران", "امداد خودرو X22 تهران | ۲۴ ساعته", "", "2026-09-05", "برنامه‌ریزی‌شده", "880", "35", "بالا", "مالکان MVM X22", "80", ""]
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(cols); w.writerow(ex)
    return "﻿" + buf.getvalue()


__all__ = ["detect_mapping", "normalize_row", "parse_table", "sheet_csv_url", "fetch_sheet", "to_csv", "to_xlsx", "template_csv", "EXPORT_COLUMNS", "FIELD_ALIASES"]
