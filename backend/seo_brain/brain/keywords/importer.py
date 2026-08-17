"""Keyword import: CSV / TSV / XLSX (Excel) / Google-Sheet export (CSV or XLSX download of the sheet).

Column mapping is auto-detected from header aliases (English + Persian); the caller may override with an
explicit `{source_column: field}` mapping. `dry_run=True` parses + validates and returns a preview without writing.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any

from .normalize import normalize_keyword
from .repository import INTENTS, PRIORITIES, STATUSES, Keyword, KeywordsRepository

KEYWORD_FIELDS = ("keyword", "intent", "cluster", "topic", "volume", "difficulty", "priority", "target_url", "status", "notes")

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "keyword": ("keyword", "keywords", "query", "term", "kw", "search term", "کلمه کلیدی", "کلمه‌کلیدی", "کلیدواژه", "عبارت", "کوئری", "کلمه"),
    "intent": ("intent", "search intent", "اینتنت", "نیت", "قصد", "هدف جستجو"),
    "cluster": ("cluster", "group", "خوشه", "گروه"),
    "topic": ("topic", "theme", "category", "موضوع", "دسته", "تم"),
    "volume": ("volume", "search volume", "sv", "avg. monthly searches", "monthly searches", "حجم", "حجم جستجو", "جستجو ماهانه"),
    "difficulty": ("difficulty", "kd", "keyword difficulty", "seo difficulty", "سختی", "دشواری"),
    "priority": ("priority", "prio", "اولویت"),
    "target_url": ("target_url", "target url", "url", "page", "landing page", "target", "آدرس", "صفحه هدف", "لینک", "صفحه"),
    "status": ("status", "state", "وضعیت"),
    "notes": ("notes", "note", "comment", "comments", "یادداشت", "توضیح", "توضیحات"),
}
_INTENT_ALIASES = {"info": "informational", "informational": "informational", "اطلاعاتی": "informational", "nav": "navigational", "navigational": "navigational", "ناوبری": "navigational",
                   "commercial": "commercial", "تجاری": "commercial", "trans": "transactional", "transactional": "transactional", "تراکنشی": "transactional", "خرید": "transactional",
                   "local": "local", "محلی": "local"}
_PRIO_ALIASES = {"high": "high", "h": "high", "بالا": "high", "زیاد": "high", "1": "high", "medium": "medium", "med": "medium", "m": "medium", "متوسط": "medium", "2": "medium",
                 "low": "low", "l": "low", "کم": "low", "پایین": "low", "3": "low"}
_STATUS_ALIASES = {"new": "new", "جدید": "new", "planned": "planned", "برنامه": "planned", "برنامه‌ریزی": "planned", "in_progress": "in_progress", "in progress": "in_progress",
                   "در حال انجام": "in_progress", "published": "published", "منتشر": "published", "منتشرشده": "published", "ignored": "ignored", "نادیده": "ignored", "رد": "ignored"}


@dataclass
class ImportResult:
    format: str
    columns: list[str]
    mapping: dict[str, str]              # source column → field
    unmapped_columns: list[str]
    rows_total: int = 0
    rows_valid: int = 0
    rows_imported: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    preview: list[dict[str, Any]] = field(default_factory=list)
    import_id: int | None = None
    dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"format": self.format, "columns": self.columns, "mapping": self.mapping, "unmapped_columns": self.unmapped_columns,
                "rows_total": self.rows_total, "rows_valid": self.rows_valid, "rows_imported": self.rows_imported, "rows_updated": self.rows_updated,
                "rows_skipped": self.rows_skipped, "errors": self.errors[:100], "errors_count": len(self.errors), "preview": self.preview[:50],
                "import_id": self.import_id, "dry_run": self.dry_run}


def _norm_header(h: str) -> str:
    return re.sub(r"[\s_\-]+", " ", normalize_keyword(str(h or ""))).strip()


def detect_mapping(columns: list[str]) -> dict[str, str]:
    """source column → field, first alias match wins; a field is mapped at most once."""
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for col in columns:
        h = _norm_header(col)
        for f, aliases in FIELD_ALIASES.items():
            if f in used:
                continue
            if h in {_norm_header(a) for a in aliases}:
                mapping[col] = f; used.add(f); break
    # relaxed pass: contains
    for col in columns:
        if col in mapping:
            continue
        h = _norm_header(col)
        for f, aliases in FIELD_ALIASES.items():
            if f in used:
                continue
            if any(_norm_header(a) and _norm_header(a) in h for a in aliases):
                mapping[col] = f; used.add(f); break
    return mapping


def parse_table(data: bytes, filename: str | None = None) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Return (format, columns, rows). XLSX by magic/extension, else CSV/TSV with sniffed delimiter."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")) or data[:4] == b"PK\x03\x04":
        import openpyxl  # lazy
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter, None) or ()
        cols = [str(c).strip() if c is not None else f"col{i+1}" for i, c in enumerate(header)]
        rows = []
        for r in rows_iter:
            if r is None or all(v in (None, "") for v in r):
                continue
            rows.append({cols[i]: r[i] for i in range(min(len(cols), len(r)))})
        return "xlsx", cols, rows
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        delim = dialect.delimiter
    except csv.Error:
        delim = "\t" if sample.count("\t") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    cols = [c.strip() for c in (reader.fieldnames or [])]
    rows = []
    for r in reader:
        if not any((v or "").strip() for v in r.values() if isinstance(v, str)):
            continue
        rows.append({k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items() if k is not None})
    fmt = "tsv" if delim == "\t" else ("sheet" if name.endswith(".csv") and "google" in name else "csv")
    return fmt, cols, rows


def _to_int(v) -> int | None:
    if v in (None, ""):
        return None
    s = normalize_keyword(str(v)).replace(",", "").replace(" ", "")
    m = re.match(r"^\d+(\.\d+)?", s)
    return int(float(m.group(0))) if m else None


def _to_float(v) -> float | None:
    if v in (None, ""):
        return None
    s = normalize_keyword(str(v)).replace(",", ".").replace(" ", "")
    m = re.match(r"^\d+(\.\d+)?", s)
    return float(m.group(0)) if m else None


def _enum(v, aliases: dict[str, str], allowed: tuple[str, ...]) -> str | None:
    if v in (None, ""):
        return None
    s = normalize_keyword(str(v))
    if s in allowed:
        return s
    return aliases.get(s) or aliases.get(str(v).strip().lower())


class KeywordImporter:
    def __init__(self, repo: KeywordsRepository):
        self.repo = repo

    def run(self, site_id: str, data: bytes, filename: str | None = None, mapping: dict[str, str] | None = None,
            dry_run: bool = True, source: str | None = None) -> ImportResult:
        fmt, cols, rows = parse_table(data, filename)
        mp = dict(mapping) if mapping else detect_mapping(cols)
        mp = {c: f for c, f in mp.items() if f in KEYWORD_FIELDS and c in cols}
        res = ImportResult(format=fmt, columns=cols, mapping=mp, unmapped_columns=[c for c in cols if c not in mp], rows_total=len(rows), dry_run=dry_run)
        if "keyword" not in mp.values():
            res.errors.append({"row": 0, "error": "ستون کلمه کلیدی پیدا نشد (keyword / کلمه کلیدی / query)"})
            return res
        inv = {f: c for c, f in mp.items()}
        seen: set[str] = set()
        parsed: list[Keyword] = []
        for i, r in enumerate(rows, start=2):   # 1-based + header
            raw_kw = r.get(inv["keyword"])
            kw = str(raw_kw).strip() if raw_kw is not None else ""
            if not kw:
                res.errors.append({"row": i, "error": "کلمه کلیدی خالی"}); res.rows_skipped += 1; continue
            norm = normalize_keyword(kw)
            if norm in seen:
                res.errors.append({"row": i, "error": f"تکراری در همین فایل: {kw}"}); res.rows_skipped += 1; continue
            seen.add(norm)
            k = Keyword(site_id=site_id, keyword=kw, normalized=norm, source=source or f"import:{filename or fmt}")
            if "intent" in inv: k.intent = _enum(r.get(inv["intent"]), _INTENT_ALIASES, INTENTS)
            if "cluster" in inv and r.get(inv["cluster"]) not in (None, ""): k.cluster_id = f"m-{normalize_keyword(str(r.get(inv['cluster']))).replace(' ', '-')[:40]}"
            if "topic" in inv and r.get(inv["topic"]) not in (None, ""): k.topic = str(r.get(inv["topic"])).strip()
            if "volume" in inv: k.volume = _to_int(r.get(inv["volume"]))
            if "difficulty" in inv: k.difficulty = _to_float(r.get(inv["difficulty"]))
            if "priority" in inv: k.priority = _enum(r.get(inv["priority"]), _PRIO_ALIASES, PRIORITIES)
            if "target_url" in inv and r.get(inv["target_url"]) not in (None, ""): k.target_url = str(r.get(inv["target_url"])).strip()
            if "status" in inv: k.status = _enum(r.get(inv["status"]), _STATUS_ALIASES, STATUSES) or "new"
            if "notes" in inv and r.get(inv["notes"]) not in (None, ""): k.notes = str(r.get(inv["notes"])).strip()
            parsed.append(k)
        res.rows_valid = len(parsed)
        res.preview = [k.to_dict() for k in parsed[:50]]
        if dry_run:
            return res
        # write: manual clusters get a cluster row too
        manual_clusters: dict[str, str] = {}
        for k in parsed:
            row, created = self.repo.upsert(k)
            if created: res.rows_imported += 1
            else: res.rows_updated += 1
            if k.cluster_id and k.cluster_id.startswith("m-"):
                manual_clusters.setdefault(k.cluster_id, k.topic or k.keyword)
        if manual_clusters:
            from .repository import KeywordCluster
            existing = {c.cluster_id: c for c in self.repo.list_clusters(site_id)}
            all_kw = self.repo.all(site_id)
            merged = list(existing.values())
            for cid, name in manual_clusters.items():
                cnt = sum(1 for x in all_kw if x.cluster_id == cid)
                if cid in existing:
                    existing[cid].keywords_count = cnt
                else:
                    merged.append(KeywordCluster(site_id=site_id, cluster_id=cid, name=name, topic=name, keywords_count=cnt, method="manual"))
            self.repo.replace_clusters(site_id, merged)
        res.import_id = self.repo.record_import(site_id, filename, fmt, res.rows_total, res.rows_imported, res.rows_updated, res.rows_skipped, mp, res.errors)
        return res


TEMPLATE_CSV = "keyword,intent,topic,volume,difficulty,priority,target_url,status,notes\n" \
               "امداد خودرو mvm,transactional,امداد MVM,1300,32,high,https://example.com/mvm/,planned,\n" \
               "شماره امداد خودرو تهران,transactional,امداد تهران,880,28,high,,new,\n"
