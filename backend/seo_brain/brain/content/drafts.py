"""Versioned drafts: parse (Markdown / HTML / text) → structure; every modification is a new version with
previous content kept, change summary, author/source and AI provenance."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from typing import Any

from sqlalchemy import and_, func, select

from ...brain.keywords.normalize import normalize_keyword, tokenize
from ...db.repositories.base import Repository, dumps, loads, utcnow
from ...db.tables import content_drafts, content_items, site_settings

_QUESTION_MARKERS = ("چگونه", "چطور", "چرا", "چیست", "چیه", "کجا", "کدام", "آیا", "چند", "؟", "?", "how", "why", "what", "where", "which")


@dataclass
class DraftStructure:
    h1: list[str] = field(default_factory=list)
    h2: list[str] = field(default_factory=list)
    h3: list[str] = field(default_factory=list)
    headings: list[dict[str, Any]] = field(default_factory=list)      # ordered {level, text}
    paragraphs: list[str] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)          # {href, anchor}
    images: list[dict[str, Any]] = field(default_factory=list)         # {src, alt}
    questions: list[str] = field(default_factory=list)                 # question-like headings
    faq: bool = False
    word_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _HTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.st = DraftStructure()
        self._stack: list[str] = []
        self._buf: list[str] = []
        self._link: dict | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4", "p", "li"):
            self._stack.append(tag); self._buf = []
        elif tag == "a":
            self._link = {"href": a.get("href", ""), "anchor": ""}
        elif tag == "img":
            self.st.images.append({"src": a.get("src", ""), "alt": (a.get("alt") or "").strip()})
        elif tag == "br":
            self._buf.append(" ")

    def handle_endtag(self, tag):
        if tag == "a" and self._link is not None:
            self.st.links.append(self._link); self._link = None
        if self._stack and tag == self._stack[-1]:
            self._stack.pop()
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if text:
                _add_block(self.st, tag, text)
            self._buf = []

    def handle_data(self, data):
        self._text.append(data)
        if self._stack:
            self._buf.append(data)
        if self._link is not None:
            self._link["anchor"] += data


def _add_block(st: DraftStructure, tag: str, text: str) -> None:
    if tag in ("h1", "h2", "h3", "h4"):
        lvl = int(tag[1])
        st.headings.append({"level": lvl, "text": text})
        if lvl == 1: st.h1.append(text)
        elif lvl == 2: st.h2.append(text)
        elif lvl == 3: st.h3.append(text)
        if any(m in text for m in _QUESTION_MARKERS):
            st.questions.append(text)
    else:
        st.paragraphs.append(text)


_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)[^)]*\)")
_MD_IMG = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)")


def parse_markdown(md: str) -> DraftStructure:
    st = DraftStructure()
    para: list[str] = []
    def flush():
        if para:
            st.paragraphs.append(" ".join(para).strip()); para.clear()
    for raw in md.splitlines():
        line = raw.rstrip()
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush(); _add_block(st, f"h{len(m.group(1))}", m.group(2).strip()); continue
        if not line.strip():
            flush(); continue
        for im in _MD_IMG.finditer(line):
            st.images.append({"src": im.group(2), "alt": im.group(1).strip()})
        line_no_img = _MD_IMG.sub("", line)
        for lm in _MD_LINK.finditer(line_no_img):
            st.links.append({"href": lm.group(2), "anchor": lm.group(1)})
        para.append(re.sub(r"[*_`>#-]+", " ", _MD_LINK.sub(r"\1", line_no_img)).strip())
    flush()
    return st


def parse_draft(body: str, fmt: str = "markdown") -> tuple[DraftStructure, str]:
    """Returns (structure, plain_text)."""
    if fmt == "html" or (fmt != "markdown" and "<" in body and ">" in body and re.search(r"<(p|h[1-6]|div)\b", body, re.I)):
        p = _HTML(); p.feed(body); st = p.st
        text = re.sub(r"\s+", " ", "".join(p._text)).strip()
    elif fmt == "text":
        st = DraftStructure(); st.paragraphs = [x.strip() for x in re.split(r"\n\s*\n", body) if x.strip()]; text = re.sub(r"\s+", " ", body).strip()
    else:
        st = parse_markdown(body)
        text = " ".join([h["text"] for h in st.headings] + st.paragraphs)
    st.word_count = len([w for w in re.split(r"\s+", text) if w])
    faq_h = any(("سوال" in h["text"] or "سؤال" in h["text"] or "faq" in h["text"].lower() or "پرسش" in h["text"]) for h in st.headings)
    st.faq = faq_h or len(st.questions) >= 3
    return st, text


@dataclass
class Draft:
    site_id: str
    content_id: int
    body: str
    version: int = 1
    title: str | None = None
    meta_description: str | None = None
    format: str = "markdown"
    body_text: str | None = None
    word_count: int = 0
    structure: dict[str, Any] = field(default_factory=dict)
    source: str = "user"
    author: str | None = None
    revision_of: int | None = None
    change_summary: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    review_status: str = "none"
    id: int | None = None
    created_at: str | None = None

    def to_dict(self, with_body: bool = True) -> dict[str, Any]:
        d = asdict(self)
        if not with_body:
            d.pop("body", None); d.pop("body_text", None)
        return d


def _row(m) -> Draft:
    d = {k: m[k] for k in Draft.__dataclass_fields__ if k in m and k not in ("structure", "provenance")}
    return Draft(structure=loads(m["structure"], {}), provenance=loads(m["provenance"], {}), **d)


DEFAULT_SCORING = {
    "weights": {"intent": 20, "keywords": 15, "entities": 15, "headings": 15, "links": 15, "cta": 10, "completeness": 10},
    "thresholds": {"ready": 80, "needs_work": 60},
    "min_words": {"informational": 900, "commercial": 700, "transactional": 500, "local": 500, "navigational": 300, "default": 600},
    "min_internal_links": 3,
    "review_gate": "strict",          # strict | advisory  (assisted/autopilot modes are future publishing modes, not gates)
}
DEFAULT_ANALYTICS = {"min_impressions": 1000, "min_clicks": 30, "min_age_days": 28, "windows": ["7d", "28d"]}


class DraftRepository(Repository):
    # ---- settings
    def settings(self, site_id: str, key: str) -> dict[str, Any]:
        base = {"scoring": DEFAULT_SCORING, "analytics": DEFAULT_ANALYTICS}.get(key, {})
        with self.engine.connect() as cx:
            r = cx.execute(select(site_settings.c.value).where(and_(site_settings.c.site_id == site_id, site_settings.c.key == key))).first()
        merged = dict(base)
        if r:
            for k, v in loads(r[0], {}).items():
                merged[k] = {**base[k], **v} if isinstance(v, dict) and isinstance(base.get(k), dict) else v
        return merged

    def put_settings(self, site_id: str, key: str, value: dict[str, Any]) -> dict[str, Any]:
        with self.engine.begin() as cx:
            self.upsert(cx, site_settings, {"site_id": site_id, "key": key, "value": dumps(value), "updated_at": utcnow()}, conflict=["site_id", "key"])
        return self.settings(site_id, key)

    # ---- drafts
    def create(self, d: Draft) -> Draft:
        st, text = parse_draft(d.body, d.format)
        d.structure = st.to_dict(); d.body_text = text; d.word_count = st.word_count
        with self.engine.begin() as cx:
            v = cx.execute(select(func.max(content_drafts.c.version)).where(and_(content_drafts.c.site_id == d.site_id, content_drafts.c.content_id == d.content_id))).scalar() or 0
            prev = cx.execute(select(content_drafts.c.id).where(and_(content_drafts.c.site_id == d.site_id, content_drafts.c.content_id == d.content_id, content_drafts.c.version == v))).scalar() if v else None
            d.version = int(v) + 1
            if d.revision_of is None:
                d.revision_of = prev
            res = cx.execute(content_drafts.insert().values(site_id=d.site_id, content_id=d.content_id, version=d.version, title=d.title, meta_description=d.meta_description, format=d.format,
                                                            body=d.body, body_text=d.body_text, word_count=d.word_count, structure=dumps(d.structure), source=d.source, author=d.author,
                                                            revision_of=d.revision_of, change_summary=d.change_summary, provenance=dumps(d.provenance), review_status="none", created_at=utcnow()))
            did = int(res.inserted_primary_key[0])
            cx.execute(content_items.update().where(content_items.c.id == d.content_id).values(current_draft_id=did, review_status="none", updated_at=utcnow()))
        return self.get(d.site_id, did)  # type: ignore[return-value]

    def get(self, site_id: str, did: int) -> Draft | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(content_drafts).where(and_(content_drafts.c.site_id == site_id, content_drafts.c.id == did))).first()
        return _row(r._mapping) if r else None

    def latest(self, site_id: str, content_id: int) -> Draft | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(content_drafts).where(and_(content_drafts.c.site_id == site_id, content_drafts.c.content_id == content_id)).order_by(content_drafts.c.version.desc())).first()
        return _row(r._mapping) if r else None

    def list(self, site_id: str, content_id: int) -> list[Draft]:
        with self.engine.connect() as cx:
            return [_row(r._mapping) for r in cx.execute(select(content_drafts).where(and_(content_drafts.c.site_id == site_id, content_drafts.c.content_id == content_id)).order_by(content_drafts.c.version.desc()))]

    def set_review_status(self, site_id: str, did: int, status: str, score: float | None = None) -> None:
        with self.engine.begin() as cx:
            cx.execute(content_drafts.update().where(and_(content_drafts.c.site_id == site_id, content_drafts.c.id == did)).values(review_status=status))
            cid = cx.execute(select(content_drafts.c.content_id).where(content_drafts.c.id == did)).scalar()
            vals: dict[str, Any] = {"review_status": status, "updated_at": utcnow()}
            if score is not None:
                vals["latest_score"] = score
            cx.execute(content_items.update().where(content_items.c.id == cid).values(**vals))


def diff_summary(prev: Draft | None, cur: Draft) -> str:
    """Human-readable change summary between versions (structure-level, not a text diff)."""
    if not prev:
        return f"نسخه اول ({cur.word_count} کلمه، {len(cur.structure.get('h2', []))} H2)"
    parts = []
    dw = cur.word_count - prev.word_count
    if dw: parts.append(f"{'+' if dw > 0 else ''}{dw} کلمه")
    ph, ch = set(prev.structure.get("h2", [])), set(cur.structure.get("h2", []))
    if ch - ph: parts.append(f"H2 جدید: {', '.join(list(ch - ph)[:3])}")
    if ph - ch: parts.append(f"H2 حذف‌شده: {', '.join(list(ph - ch)[:3])}")
    dl = len(cur.structure.get("links", [])) - len(prev.structure.get("links", []))
    if dl: parts.append(f"{'+' if dl > 0 else ''}{dl} لینک")
    if (prev.title or "") != (cur.title or ""): parts.append("عنوان تغییر کرد")
    return "؛ ".join(parts) or "بدون تغییر ساختاری"
