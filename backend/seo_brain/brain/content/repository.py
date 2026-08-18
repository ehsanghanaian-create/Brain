from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import and_, delete, func, or_, select

from ...db.repositories.base import Repository, dumps, loads, utcnow
from ...db.tables import content_briefs, content_events, content_items

STATUSES = ("planned", "brief_ready", "writing", "review", "approved", "published")
STATUS_FA = {"planned": "برنامه‌ریزی‌شده", "brief_ready": "بریف آماده", "writing": "در حال نگارش", "review": "بازبینی", "approved": "تأییدشده", "published": "منتشرشده"}
# Human-approval workflow: forward one step, or back to any earlier stage. Nothing here publishes anything.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "planned": ("brief_ready",),
    "brief_ready": ("writing", "planned"),
    "writing": ("review", "brief_ready", "planned"),
    "review": ("approved", "writing", "brief_ready"),
    "approved": ("published", "review", "writing"),
    "published": ("approved",),
}
PRIORITIES = ("high", "medium", "low")


class WorkflowError(ValueError):
    pass


def slugify(title: str) -> str:
    s = re.sub(r"[^\w\s\-]", "", title.strip().lower(), flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-")[:120]


@dataclass
class ContentItem:
    site_id: str
    title: str
    id: int | None = None
    slug: str | None = None
    target_keyword_id: int | None = None
    target_keyword: str | None = None
    topic: str | None = None
    cluster_id: str | None = None
    intent: str | None = None
    status: str = "planned"
    priority: str | None = None
    publish_date: str | None = None
    publish_time: str | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    url: str | None = None
    wp_post_id: int | None = None
    brief_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    current_draft_id: int | None = None
    latest_score: float | None = None
    review_status: str = "none"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self); d["status_fa"] = STATUS_FA.get(self.status, self.status); return d


@dataclass
class ContentBrief:
    site_id: str
    content_id: int
    version: int = 1
    h1: str | None = None
    seo_title: str | None = None
    meta_description: str | None = None
    intent: str | None = None
    outline: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)
    internal_links: list[dict[str, Any]] = field(default_factory=list)
    sources: dict[str, Any] = field(default_factory=dict)
    markdown: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _item(m) -> ContentItem:
    d = {k: m[k] for k in ContentItem.__dataclass_fields__ if k in m and k != "metadata"}
    return ContentItem(metadata=loads(m["metadata"], {}), **d)


def _brief(m) -> ContentBrief:
    d = {k: m[k] for k in ContentBrief.__dataclass_fields__ if k in m and k not in ("outline", "entities", "questions", "internal_links", "sources", "provenance")}
    return ContentBrief(outline=loads(m["outline"], []), entities=loads(m["entities"], []), questions=loads(m["questions"], []), internal_links=loads(m["internal_links"], []),
                        sources=loads(m["sources"], {}), provenance=loads(m["provenance"], {}), **d)


class ContentRepository(Repository):
    # ---- items
    def list(self, site_id: str, status: str | None = None, q: str | None = None, topic: str | None = None, cluster_id: str | None = None, priority: str | None = None,
             date_from: str | None = None, date_to: str | None = None, sort: str = "updated_at", order: str = "desc", limit: int = 50, offset: int = 0) -> tuple[list[ContentItem], int]:
        conds = [content_items.c.site_id == site_id]
        if status: conds.append(content_items.c.status.in_(status.split(",")))
        if q: conds.append(or_(content_items.c.title.like(f"%{q}%"), content_items.c.target_keyword.like(f"%{q}%"), content_items.c.url.like(f"%{q}%")))
        if topic: conds.append(content_items.c.topic == topic)
        if cluster_id: conds.append(content_items.c.cluster_id == cluster_id)
        if priority: conds.append(content_items.c.priority == priority)
        if date_from: conds.append(content_items.c.publish_date >= date_from)
        if date_to: conds.append(content_items.c.publish_date <= date_to)
        col = getattr(content_items.c, sort) if sort in ("title", "status", "priority", "publish_date", "updated_at", "created_at", "topic") else content_items.c.updated_at
        ob = col.desc().nullslast() if order == "desc" else col.asc().nullsfirst()
        with self.engine.connect() as cx:
            total = cx.execute(select(func.count()).select_from(content_items).where(and_(*conds))).scalar() or 0
            rows = cx.execute(select(content_items).where(and_(*conds)).order_by(ob, content_items.c.id).limit(limit).offset(offset)).all()
        return [_item(r._mapping) for r in rows], int(total)

    def all(self, site_id: str) -> list[ContentItem]:
        with self.engine.connect() as cx:
            return [_item(r._mapping) for r in cx.execute(select(content_items).where(content_items.c.site_id == site_id).order_by(content_items.c.id))]

    def get(self, site_id: str, cid: int) -> ContentItem | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(content_items).where(and_(content_items.c.site_id == site_id, content_items.c.id == cid))).first()
        return _item(r._mapping) if r else None

    def create(self, item: ContentItem, actor: str = "user") -> ContentItem:
        if item.status not in STATUSES:
            raise WorkflowError(f"invalid status {item.status}")
        now = utcnow()
        values = {k: v for k, v in item.to_dict().items() if k in content_items.c.keys() and k not in ("id", "created_at", "updated_at")}
        values["metadata"] = dumps(item.metadata or {}); values["slug"] = item.slug or slugify(item.title); values.update(created_at=now, updated_at=now)
        with self.engine.begin() as cx:
            res = cx.execute(content_items.insert().values(**values))
            cid = int(res.inserted_primary_key[0])
            cx.execute(content_events.insert().values(site_id=item.site_id, content_id=cid, from_status=None, to_status=item.status, actor=actor, note="created", created_at=now))
        return self.get(item.site_id, cid)  # type: ignore[return-value]

    def update(self, site_id: str, cid: int, **fields) -> ContentItem | None:
        if "status" in fields:
            raise WorkflowError("use transition() to change status")
        allowed = {k: v for k, v in fields.items() if k in content_items.c.keys() and k not in ("id", "site_id", "status", "created_at", "updated_at")}
        if "metadata" in allowed:
            allowed["metadata"] = dumps(allowed["metadata"] or {})
        if not allowed:
            return self.get(site_id, cid)
        allowed["updated_at"] = utcnow()
        with self.engine.begin() as cx:
            cx.execute(content_items.update().where(and_(content_items.c.site_id == site_id, content_items.c.id == cid)).values(**allowed))
        return self.get(site_id, cid)

    def transition(self, site_id: str, cid: int, to_status: str, actor: str = "user", note: str | None = None, force: bool = False) -> ContentItem:
        item = self.get(site_id, cid)
        if not item:
            raise KeyError(cid)
        if to_status not in STATUSES:
            raise WorkflowError(f"invalid status '{to_status}'")
        if to_status == item.status:
            return item
        if not force and to_status not in TRANSITIONS[item.status]:
            raise WorkflowError(f"cannot move from '{item.status}' to '{to_status}' — allowed: {', '.join(TRANSITIONS[item.status])}")
        if to_status == "brief_ready" and not item.brief_id and not force:
            raise WorkflowError("a brief must be generated before 'brief_ready'")
        if to_status == "published" and not item.url:
            raise WorkflowError("published content needs a URL — set the URL first (publishing is manual in this phase)")
        now = utcnow()
        with self.engine.begin() as cx:
            cx.execute(content_items.update().where(content_items.c.id == cid).values(status=to_status, updated_at=now))
            cx.execute(content_events.insert().values(site_id=site_id, content_id=cid, from_status=item.status, to_status=to_status, actor=actor, note=note, created_at=now))
        return self.get(site_id, cid)  # type: ignore[return-value]

    def add_note(self, site_id: str, cid: int, note: str, actor: str = "user") -> None:
        with self.engine.begin() as cx:
            cx.execute(content_events.insert().values(site_id=site_id, content_id=cid, from_status=None, to_status=None, actor=actor, note=note, created_at=utcnow()))

    def events(self, site_id: str, cid: int) -> list[dict[str, Any]]:
        with self.engine.connect() as cx:
            return [dict(r._mapping) for r in cx.execute(select(content_events).where(and_(content_events.c.site_id == site_id, content_events.c.content_id == cid)).order_by(content_events.c.id.desc()))]

    def delete(self, site_id: str, cid: int) -> bool:
        from ...db.tables import content_drafts, content_reviews, content_scores  # phase 7 tables
        with self.engine.begin() as cx:
            for t in (content_scores, content_reviews, content_drafts):
                cx.execute(delete(t).where(and_(t.c.site_id == site_id, t.c.content_id == cid)))
            cx.execute(delete(content_briefs).where(and_(content_briefs.c.site_id == site_id, content_briefs.c.content_id == cid)))
            cx.execute(delete(content_events).where(and_(content_events.c.site_id == site_id, content_events.c.content_id == cid)))
            n = cx.execute(delete(content_items).where(and_(content_items.c.site_id == site_id, content_items.c.id == cid))).rowcount
        return bool(n)

    def counts(self, site_id: str) -> dict[str, Any]:
        with self.engine.connect() as cx:
            by_status = dict(cx.execute(select(content_items.c.status, func.count()).where(content_items.c.site_id == site_id).group_by(content_items.c.status)).all())
            total = cx.execute(select(func.count()).select_from(content_items).where(content_items.c.site_id == site_id)).scalar() or 0
            scheduled = cx.execute(select(func.count()).select_from(content_items).where(and_(content_items.c.site_id == site_id, content_items.c.publish_date.isnot(None)))).scalar() or 0
        return {"total": int(total), "by_status": {s: int(by_status.get(s, 0)) for s in STATUSES}, "scheduled": int(scheduled)}

    # ---- briefs
    def add_brief(self, b: ContentBrief) -> ContentBrief:
        with self.engine.begin() as cx:
            v = cx.execute(select(func.max(content_briefs.c.version)).where(and_(content_briefs.c.site_id == b.site_id, content_briefs.c.content_id == b.content_id))).scalar() or 0
            res = cx.execute(content_briefs.insert().values(site_id=b.site_id, content_id=b.content_id, version=int(v) + 1, h1=b.h1, seo_title=b.seo_title, meta_description=b.meta_description,
                                                            intent=b.intent, outline=dumps(b.outline), entities=dumps(b.entities), questions=dumps(b.questions), internal_links=dumps(b.internal_links),
                                                            sources=dumps(b.sources), markdown=b.markdown, provenance=dumps(b.provenance), created_at=utcnow()))
            bid = int(res.inserted_primary_key[0])
            cx.execute(content_items.update().where(content_items.c.id == b.content_id).values(brief_id=bid, updated_at=utcnow()))
        return self.get_brief(b.site_id, bid)  # type: ignore[return-value]

    def get_brief(self, site_id: str, bid: int) -> ContentBrief | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(content_briefs).where(and_(content_briefs.c.site_id == site_id, content_briefs.c.id == bid))).first()
        return _brief(r._mapping) if r else None

    def briefs(self, site_id: str, cid: int) -> list[ContentBrief]:
        with self.engine.connect() as cx:
            return [_brief(r._mapping) for r in cx.execute(select(content_briefs).where(and_(content_briefs.c.site_id == site_id, content_briefs.c.content_id == cid)).order_by(content_briefs.c.version.desc()))]
