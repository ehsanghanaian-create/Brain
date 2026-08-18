"""Content Strategy Planner repository (phase 8.5) — SQLAlchemy Core over the 0009 tables.

Vocabulary (Persian labels live here so API + UI share one source):
  statuses   planned → researching → brief_ready → writing → review → approved → published
             (`researching` is planner-only; the linked content item stays `planned`)
  page types service_landing | location_landing | pillar | article | guide | comparison | faq | product | category_page | news
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from sqlalchemy import Engine, and_, delete, func, or_, select, text, update

from ...db.repositories.base import Repository, dumps, loads, utcnow
from ...db.tables import (content_categories, content_clusters, content_plan_events, content_plan_generation_jobs, content_plan_imports,
                          content_plan_keywords, content_plan_recommendations, content_plan_sources, content_plans)

PLAN_STATUSES = ("planned", "researching", "brief_ready", "writing", "review", "approved", "published")
STATUS_FA = {"planned": "برنامه‌ریزی‌شده", "researching": "در حال تحقیق", "brief_ready": "بریف آماده", "writing": "در حال نگارش", "review": "بازبینی", "approved": "تأییدشده", "published": "منتشرشده"}
# planner status → content item status (Phase 6 workflow untouched)
ITEM_STATUS_OF = {"planned": "planned", "researching": "planned", "brief_ready": "brief_ready", "writing": "writing", "review": "review", "approved": "approved", "published": "published"}
PLAN_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "planned": ("researching", "brief_ready"), "researching": ("planned", "brief_ready"), "brief_ready": ("writing", "researching", "planned"),
    "writing": ("review", "brief_ready"), "review": ("approved", "writing"), "approved": ("published", "review", "writing"), "published": ("approved",),
}
PAGE_TYPES = ("service_landing", "location_landing", "pillar", "article", "guide", "comparison", "faq", "product", "category_page", "news")
PAGE_TYPE_FA = {"service_landing": "لندینگ خدمت", "location_landing": "لندینگ مکان", "pillar": "صفحه ستون (Pillar)", "article": "مقاله", "guide": "راهنما", "comparison": "مقایسه",
                "faq": "پرسش‌های متداول", "product": "محصول", "category_page": "صفحه دسته", "news": "خبر"}
INTENTS = ("informational", "navigational", "commercial", "transactional", "local")
INTENT_FA = {"informational": "اطلاعاتی", "navigational": "ناوبری", "commercial": "تجاری", "transactional": "تراکنشی", "local": "محلی"}
PRIORITIES = ("high", "medium", "low")
PRIORITY_FA = {"high": "بالا", "medium": "متوسط", "low": "پایین"}
FUNNEL_STAGES = ("awareness", "consideration", "decision", "retention")
FUNNEL_FA = {"awareness": "آگاهی", "consideration": "بررسی", "decision": "تصمیم", "retention": "وفاداری"}
CONTENT_GAPS = ("none", "partial", "full")
GAP_FA = {"none": "بدون شکاف", "partial": "شکاف جزئی", "full": "شکاف کامل"}
KEYWORD_ROLES = ("primary", "secondary", "supporting", "question", "gsc_query")
ROLE_FA = {"primary": "اصلی", "secondary": "ثانویه", "supporting": "پشتیبان", "question": "پرسش", "gsc_query": "کوئری GSC"}
CATEGORY_SOURCES = ("wordpress", "brain", "manual")
CATEGORY_SOURCE_FA = {"wordpress": "وردپرس", "brain": "مغز (موضوعی)", "manual": "دستی"}
RECOMMENDATION_KINDS = ("create_new", "optimize_existing", "improve_page", "add_to_cluster", "merge", "category", "link_prep", "gap", "schedule")
RECOMMENDATION_FA = {"create_new": "ساخت محتوای جدید", "optimize_existing": "بهینه‌سازی صفحه موجود", "improve_page": "بهبود صفحه (جایگاه ۱۱–۳۰)", "add_to_cluster": "افزودن به خوشه موجود",
                     "merge": "ادغام با برنامه موجود", "category": "پیشنهاد دسته", "link_prep": "لینک‌های داخلی پیشنهادی", "gap": "شکاف محتوایی", "schedule": "زمان‌بندی"}
GEN_JOB_KINDS = ("brief", "outline", "article", "rewrite", "title_meta")

# grid column model: key, fa, group, editable, type
COLUMNS: list[dict[str, Any]] = [
    {"key": "title", "fa": "عنوان", "group": "basic", "editable": True, "type": "text"},
    {"key": "url", "fa": "URL", "group": "basic", "editable": True, "type": "url"},
    {"key": "intent", "fa": "اینتنت", "group": "basic", "editable": True, "type": "select", "options": INTENTS},
    {"key": "page_type", "fa": "نوع صفحه", "group": "basic", "editable": True, "type": "select", "options": PAGE_TYPES},
    {"key": "category_id", "fa": "دسته", "group": "basic", "editable": True, "type": "category"},
    {"key": "parent_category", "fa": "دسته والد", "group": "basic", "editable": False, "type": "text"},
    {"key": "primary_keyword", "fa": "کلمه کلیدی اصلی", "group": "basic", "editable": True, "type": "keyword"},
    {"key": "secondary_keywords", "fa": "کلمات کلیدی ثانویه", "group": "basic", "editable": True, "type": "tags"},
    {"key": "heading_structure", "fa": "ساختار سرفصل‌ها", "group": "basic", "editable": True, "type": "headings"},
    {"key": "seo_title", "fa": "عنوان سئو", "group": "basic", "editable": True, "type": "text"},
    {"key": "meta_description", "fa": "توضیحات متا", "group": "basic", "editable": True, "type": "text"},
    {"key": "publish_date", "fa": "تاریخ انتشار", "group": "basic", "editable": True, "type": "date"},
    {"key": "status", "fa": "وضعیت", "group": "basic", "editable": True, "type": "select", "options": PLAN_STATUSES},
    {"key": "cluster_id", "fa": "خوشه کلمه کلیدی", "group": "seo", "editable": False, "type": "text"},
    {"key": "topic_id", "fa": "موضوع", "group": "seo", "editable": True, "type": "text"},
    {"key": "search_volume", "fa": "حجم جستجو", "group": "seo", "editable": True, "type": "number"},
    {"key": "keyword_difficulty", "fa": "سختی کلمه", "group": "seo", "editable": True, "type": "number"},
    {"key": "priority", "fa": "اولویت", "group": "seo", "editable": True, "type": "select", "options": PRIORITIES},
    {"key": "priority_score", "fa": "امتیاز اولویت", "group": "seo", "editable": False, "type": "number"},
    {"key": "target_audience", "fa": "مخاطب هدف", "group": "seo", "editable": True, "type": "text"},
    {"key": "existing_pages", "fa": "صفحات مرتبط موجود", "group": "seo", "editable": False, "type": "list"},
    {"key": "link_targets", "fa": "اهداف لینک داخلی", "group": "seo", "editable": False, "type": "list"},
    {"key": "content_score", "fa": "امتیاز محتوا", "group": "seo", "editable": False, "type": "number"},
    {"key": "graph_connections", "fa": "ارتباطات گراف", "group": "seo", "editable": False, "type": "number"},
    {"key": "recommendation", "fa": "پیشنهاد مغز", "group": "seo", "editable": False, "type": "recommendation"},
    {"key": "content_gap", "fa": "شکاف محتوایی", "group": "advanced", "editable": False, "type": "select", "options": CONTENT_GAPS},
    {"key": "cannibalization_risk", "fa": "ریسک هم‌نوع‌خواری", "group": "advanced", "editable": False, "type": "number"},
    {"key": "ranking_url", "fa": "URL رتبه‌دار", "group": "advanced", "editable": False, "type": "url"},
    {"key": "serp_intent", "fa": "اینتنت SERP", "group": "advanced", "editable": True, "type": "select", "options": INTENTS},
    {"key": "traffic_opportunity", "fa": "فرصت ترافیک", "group": "advanced", "editable": False, "type": "number"},
    {"key": "business_value", "fa": "ارزش کسب‌وکار", "group": "advanced", "editable": True, "type": "number"},
    {"key": "ai_priority", "fa": "اولویت AI", "group": "advanced", "editable": False, "type": "number"},
    {"key": "funnel_stage", "fa": "مرحله قیف", "group": "advanced", "editable": True, "type": "select", "options": FUNNEL_STAGES},
]
EDITABLE = {c["key"] for c in COLUMNS if c["editable"]} | {"notes", "publish_time", "content_cluster_id", "target_audience", "slug", "metadata", "publishing"}
JSON_FIELDS = ("secondary_keywords", "heading_structure", "existing_pages", "link_targets", "cannibalization", "recommendation", "publishing", "metadata")


def slugify(title: str) -> str:
    s = re.sub(r"[^\w\s\-]", "", (title or "").strip().lower(), flags=re.UNICODE)
    return re.sub(r"[\s_]+", "-", s).strip("-")[:120]


@dataclass
class ContentPlan:
    site_id: str
    title: str
    id: int | None = None
    content_item_id: int | None = None
    url: str | None = None
    slug: str | None = None
    intent: str | None = None
    serp_intent: str | None = None
    page_type: str | None = None
    funnel_stage: str | None = None
    category_id: int | None = None
    category_suggested_id: int | None = None
    category_reason: str | None = None
    primary_keyword_id: int | None = None
    primary_keyword: str | None = None
    secondary_keywords: list[str] = field(default_factory=list)
    heading_structure: list[dict[str, Any]] = field(default_factory=list)
    seo_title: str | None = None
    meta_description: str | None = None
    topic_id: str | None = None
    cluster_id: str | None = None
    content_cluster_id: int | None = None
    search_volume: int | None = None
    keyword_difficulty: float | None = None
    priority: str | None = None
    priority_score: float | None = None
    ai_priority: float | None = None
    business_value: float | None = None
    traffic_opportunity: float | None = None
    content_gap: str | None = None
    cannibalization_risk: float | None = None
    cannibalization: list[dict[str, Any]] = field(default_factory=list)
    ranking_url: str | None = None
    ranking_position: float | None = None
    target_audience: str | None = None
    publish_date: str | None = None
    publish_time: str | None = None
    status: str = "planned"
    existing_pages: list[dict[str, Any]] = field(default_factory=list)
    link_targets: list[dict[str, Any]] = field(default_factory=list)
    graph_connections: int = 0
    content_score: float | None = None
    recommendation_id: int | None = None
    recommendation: dict[str, Any] = field(default_factory=dict)
    publishing: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None
    source: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status_fa"] = STATUS_FA.get(self.status, self.status)
        d["page_type_fa"] = PAGE_TYPE_FA.get(self.page_type or "", self.page_type)
        d["intent_fa"] = INTENT_FA.get(self.intent or "", self.intent)
        d["priority_fa"] = PRIORITY_FA.get(self.priority or "", self.priority)
        d["allowed_transitions"] = list(PLAN_TRANSITIONS.get(self.status, ()))
        return d


def _row_plan(m) -> ContentPlan:
    d = dict(m)
    for f in JSON_FIELDS:
        d[f] = loads(d.get(f), [] if f not in ("recommendation", "publishing", "metadata") else {})
    return ContentPlan(**{k: v for k, v in d.items() if k in ContentPlan.__dataclass_fields__})


class PlannerRepository(Repository):
    # ------------------------------------------------------------------ plans
    def _plan_values(self, p: ContentPlan) -> dict[str, Any]:
        d = asdict(p)
        for f in JSON_FIELDS:
            d[f] = dumps(d[f])
        d.pop("id", None)
        return d

    def create_plan(self, p: ContentPlan, actor: str = "user") -> ContentPlan:
        now = utcnow()
        p.created_at = p.created_at or now; p.updated_at = now
        p.slug = p.slug or slugify(p.title)
        with self.engine.begin() as cx:
            pid = int(cx.execute(content_plans.insert().values(**self._plan_values(p))).inserted_primary_key[0])
            cx.execute(content_plan_events.insert().values(site_id=p.site_id, content_plan_id=pid, event="created", actor=actor, to_value=p.status, payload=dumps({"title": p.title, "source": p.source}), created_at=now))
        p.id = pid
        return p

    def get_plan(self, site_id: str, pid: int) -> ContentPlan | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(content_plans).where(and_(content_plans.c.site_id == site_id, content_plans.c.id == pid))).first()
        return _row_plan(r._mapping) if r else None

    def get_plan_by_item(self, site_id: str, cid: int) -> ContentPlan | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(content_plans).where(and_(content_plans.c.site_id == site_id, content_plans.c.content_item_id == cid))).first()
        return _row_plan(r._mapping) if r else None

    def find_plan(self, site_id: str, url: str | None = None, primary_keyword: str | None = None, title: str | None = None, keys: Iterable[str] = ("url", "primary_keyword", "title")) -> ContentPlan | None:
        with self.engine.connect() as cx:
            for k in keys:
                v = {"url": url, "primary_keyword": primary_keyword, "title": title}.get(k)
                if not v:
                    continue
                r = cx.execute(select(content_plans).where(and_(content_plans.c.site_id == site_id, getattr(content_plans.c, k) == v))).first()
                if r:
                    return _row_plan(r._mapping)
        return None

    def list_plans(self, site_id: str, status: str | None = None, category_id: int | None = None, page_type: str | None = None, intent: str | None = None, priority: str | None = None,
                   cluster_id: str | None = None, content_cluster_id: int | None = None, q: str | None = None, date_from: str | None = None, date_to: str | None = None,
                   has_item: bool | None = None, unscheduled: bool | None = None, ids: Iterable[int] | None = None,
                   sort: str = "updated_at", order: str = "desc", limit: int = 200, offset: int = 0) -> tuple[list[ContentPlan], int]:
        c = content_plans.c
        conds = [c.site_id == site_id]
        if status:
            conds.append(c.status.in_([s for s in status.split(",") if s]))
        if category_id is not None:
            conds.append(c.category_id == category_id)
        if page_type:
            conds.append(c.page_type == page_type)
        if intent:
            conds.append(c.intent == intent)
        if priority:
            conds.append(c.priority == priority)
        if cluster_id:
            conds.append(c.cluster_id == cluster_id)
        if content_cluster_id is not None:
            conds.append(c.content_cluster_id == content_cluster_id)
        if q:
            like = f"%{q}%"
            conds.append(or_(c.title.like(like), c.primary_keyword.like(like), c.url.like(like), c.seo_title.like(like), c.secondary_keywords.like(like), c.notes.like(like)))
        if date_from:
            conds.append(c.publish_date >= date_from)
        if date_to:
            conds.append(c.publish_date <= date_to)
        if has_item is True:
            conds.append(c.content_item_id.isnot(None))
        elif has_item is False:
            conds.append(c.content_item_id.is_(None))
        if unscheduled:
            conds.append(c.publish_date.is_(None))
        if ids is not None:
            conds.append(c.id.in_(list(ids)))
        col = getattr(c, sort, None) if sort in content_plans.c else c.updated_at
        col = col if col is not None else c.updated_at
        stmt = select(content_plans).where(and_(*conds)).order_by(col.desc() if order == "desc" else col.asc(), c.id.desc()).limit(limit).offset(offset)
        with self.engine.connect() as cx:
            rows = [_row_plan(r._mapping) for r in cx.execute(stmt)]
            total = cx.execute(select(func.count()).select_from(content_plans).where(and_(*conds))).scalar() or 0
        return rows, int(total)

    def all_plans(self, site_id: str) -> list[ContentPlan]:
        return self.list_plans(site_id, limit=100000)[0]

    def update_plan(self, site_id: str, pid: int, actor: str = "user", event: str = "updated", **fields) -> ContentPlan | None:
        cur = self.get_plan(site_id, pid)
        if not cur:
            return None
        vals: dict[str, Any] = {}
        changes: dict[str, Any] = {}
        for k, v in fields.items():
            if k not in content_plans.c or k in ("id", "site_id", "created_at"):
                continue
            old = getattr(cur, k, None)
            if old == v:
                continue
            changes[k] = {"from": old, "to": v}
            vals[k] = dumps(v) if k in JSON_FIELDS else v
        if not vals:
            return cur
        vals["updated_at"] = utcnow()
        with self.engine.begin() as cx:
            cx.execute(update(content_plans).where(and_(content_plans.c.site_id == site_id, content_plans.c.id == pid)).values(**vals))
            if event:
                ev = "status_changed" if "status" in changes and len(changes) == 1 else event
                cx.execute(content_plan_events.insert().values(site_id=site_id, content_plan_id=pid, event=ev, actor=actor,
                                                               from_value=str(changes["status"]["from"]) if "status" in changes else None, to_value=str(changes["status"]["to"]) if "status" in changes else None,
                                                               payload=dumps({k: v for k, v in changes.items() if k not in JSON_FIELDS or k in ("secondary_keywords",)}), created_at=vals["updated_at"]))
        return self.get_plan(site_id, pid)

    def delete_plan(self, site_id: str, pid: int, actor: str = "user") -> bool:
        with self.engine.begin() as cx:
            cx.execute(delete(content_plan_keywords).where(content_plan_keywords.c.content_plan_id == pid))
            r = cx.execute(delete(content_plans).where(and_(content_plans.c.site_id == site_id, content_plans.c.id == pid)))
            cx.execute(update(content_plan_recommendations).where(and_(content_plan_recommendations.c.site_id == site_id, content_plan_recommendations.c.plan_id == pid, content_plan_recommendations.c.status == "new")).values(status="superseded"))
            cx.execute(content_plan_events.insert().values(site_id=site_id, content_plan_id=pid, event="deleted", actor=actor, payload="{}", created_at=utcnow()))
        return bool(r.rowcount)

    def counts(self, site_id: str) -> dict[str, Any]:
        c = content_plans.c
        with self.engine.connect() as cx:
            by_status = {s: 0 for s in PLAN_STATUSES}
            for st, n in cx.execute(select(c.status, func.count()).where(c.site_id == site_id).group_by(c.status)).all():
                by_status[st] = n
            by_priority = {r[0] or "none": r[1] for r in cx.execute(select(c.priority, func.count()).where(c.site_id == site_id).group_by(c.priority)).all()}
            by_category = {str(r[0]) if r[0] is not None else "none": r[1] for r in cx.execute(select(c.category_id, func.count()).where(c.site_id == site_id).group_by(c.category_id)).all()}
            by_page_type = {r[0] or "none": r[1] for r in cx.execute(select(c.page_type, func.count()).where(c.site_id == site_id).group_by(c.page_type)).all()}
            total = cx.execute(select(func.count()).select_from(content_plans).where(c.site_id == site_id)).scalar() or 0
            unscheduled = cx.execute(select(func.count()).select_from(content_plans).where(and_(c.site_id == site_id, c.publish_date.is_(None)))).scalar() or 0
        return {"total": int(total), "by_status": by_status, "by_priority": by_priority, "by_category": by_category, "by_page_type": by_page_type, "unscheduled": int(unscheduled)}

    def events(self, site_id: str, pid: int, limit: int = 100) -> list[dict[str, Any]]:
        with self.engine.connect() as cx:
            rows = cx.execute(select(content_plan_events).where(and_(content_plan_events.c.site_id == site_id, content_plan_events.c.content_plan_id == pid)).order_by(content_plan_events.c.id.desc()).limit(limit)).all()
        return [{**dict(r._mapping), "payload": loads(r._mapping["payload"], {})} for r in rows]

    def add_event(self, site_id: str, pid: int, event: str, actor: str = "system", payload: dict | None = None, from_value: str | None = None, to_value: str | None = None) -> None:
        with self.engine.begin() as cx:
            cx.execute(content_plan_events.insert().values(site_id=site_id, content_plan_id=pid, event=event, actor=actor, from_value=from_value, to_value=to_value, payload=dumps(payload or {}), created_at=utcnow()))

    # ------------------------------------------------------------------ plan keywords
    def set_keywords(self, site_id: str, pid: int, items: list[dict[str, Any]], replace_roles: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """items: [{keyword_id, role, source?, score?}]. `replace_roles` removes existing links of those roles first."""
        now = utcnow()
        with self.engine.begin() as cx:
            if replace_roles:
                cx.execute(delete(content_plan_keywords).where(and_(content_plan_keywords.c.content_plan_id == pid, content_plan_keywords.c.role.in_(list(replace_roles)))))
            for it in items:
                self.upsert(cx, content_plan_keywords, {"content_plan_id": pid, "keyword_id": int(it["keyword_id"]), "site_id": site_id, "role": it.get("role") or "secondary",
                                                        "source": it.get("source") or "manual", "score": it.get("score"), "created_at": now}, conflict=["content_plan_id", "keyword_id"])
        return self.plan_keywords(site_id, pid)

    def remove_keyword(self, site_id: str, pid: int, kid: int) -> None:
        with self.engine.begin() as cx:
            cx.execute(delete(content_plan_keywords).where(and_(content_plan_keywords.c.content_plan_id == pid, content_plan_keywords.c.keyword_id == kid)))

    def plan_keywords(self, site_id: str, pid: int) -> list[dict[str, Any]]:
        with self.engine.connect() as cx:
            rows = cx.execute(text("SELECT k.id, k.keyword, k.intent, k.volume, k.difficulty, k.cluster_id, k.topic, k.status, k.priority, pk.role, pk.source, pk.score FROM content_plan_keywords pk "
                                   "JOIN keywords k ON k.id = pk.keyword_id WHERE pk.content_plan_id=:p AND pk.site_id=:s ORDER BY CASE pk.role WHEN 'primary' THEN 0 WHEN 'secondary' THEN 1 ELSE 2 END, k.volume DESC"),
                              {"p": pid, "s": site_id}).mappings().all()
        return [dict(r) for r in rows]

    def keywords_map(self, site_id: str) -> dict[int, list[dict[str, Any]]]:
        """keyword_id → [{plan_id, role}] (which plans already target which keywords)."""
        with self.engine.connect() as cx:
            rows = cx.execute(select(content_plan_keywords.c.keyword_id, content_plan_keywords.c.content_plan_id, content_plan_keywords.c.role).where(content_plan_keywords.c.site_id == site_id)).all()
        out: dict[int, list[dict[str, Any]]] = {}
        for kid, pid, role in rows:
            out.setdefault(int(kid), []).append({"plan_id": int(pid), "role": role})
        return out

    # ------------------------------------------------------------------ categories
    def list_categories(self, site_id: str, source: str | None = None) -> list[dict[str, Any]]:
        conds = [content_categories.c.site_id == site_id]
        if source:
            conds.append(content_categories.c.source == source)
        with self.engine.connect() as cx:
            rows = [dict(r._mapping) for r in cx.execute(select(content_categories).where(and_(*conds)).order_by(content_categories.c.source, content_categories.c.name))]
        for r in rows:
            r["intelligence"] = loads(r["intelligence"], {}); r["metadata"] = loads(r["metadata"], {}); r["source_fa"] = CATEGORY_SOURCE_FA.get(r["source"], r["source"])
        return rows

    def get_category(self, site_id: str, cid: int) -> dict[str, Any] | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(content_categories).where(and_(content_categories.c.site_id == site_id, content_categories.c.id == cid))).first()
        if not r:
            return None
        d = dict(r._mapping); d["intelligence"] = loads(d["intelligence"], {}); d["metadata"] = loads(d["metadata"], {}); d["source_fa"] = CATEGORY_SOURCE_FA.get(d["source"], d["source"])
        return d

    def upsert_category(self, site_id: str, source: str, name: str, wordpress_category_id: int | None = None, slug: str | None = None, parent_id: int | None = None, **fields) -> dict[str, Any]:
        now = utcnow()
        slug = slug or slugify(name)
        with self.engine.begin() as cx:
            if wordpress_category_id is not None:
                r = cx.execute(select(content_categories.c.id).where(and_(content_categories.c.site_id == site_id, content_categories.c.wordpress_category_id == wordpress_category_id))).first()
            else:
                r = cx.execute(select(content_categories.c.id).where(and_(content_categories.c.site_id == site_id, content_categories.c.source == source, content_categories.c.slug == slug))).first()
            vals = {k: (dumps(v) if k in ("intelligence", "metadata") else v) for k, v in fields.items() if k in content_categories.c}
            if r:
                cx.execute(update(content_categories).where(content_categories.c.id == r[0]).values(name=name, slug=slug, parent_id=parent_id, updated_at=now, **vals))
                cid = int(r[0])
            else:
                cid = int(cx.execute(content_categories.insert().values(site_id=site_id, source=source, wordpress_category_id=wordpress_category_id, name=name, slug=slug, parent_id=parent_id,
                                                                        created_at=now, updated_at=now, **vals)).inserted_primary_key[0])
        return self.get_category(site_id, cid)  # type: ignore[return-value]

    def update_category(self, site_id: str, cid: int, **fields) -> dict[str, Any] | None:
        vals = {k: (dumps(v) if k in ("intelligence", "metadata") else v) for k, v in fields.items() if k in content_categories.c and k not in ("id", "site_id")}
        if vals:
            vals["updated_at"] = utcnow()
            with self.engine.begin() as cx:
                cx.execute(update(content_categories).where(and_(content_categories.c.site_id == site_id, content_categories.c.id == cid)).values(**vals))
        return self.get_category(site_id, cid)

    def delete_category(self, site_id: str, cid: int) -> bool:
        with self.engine.begin() as cx:
            cx.execute(update(content_plans).where(and_(content_plans.c.site_id == site_id, content_plans.c.category_id == cid)).values(category_id=None))
            cx.execute(update(content_categories).where(and_(content_categories.c.site_id == site_id, content_categories.c.parent_id == cid)).values(parent_id=None))
            r = cx.execute(delete(content_categories).where(and_(content_categories.c.site_id == site_id, content_categories.c.id == cid)))
        return bool(r.rowcount)

    def category_tree(self, site_id: str, source: str | None = None) -> list[dict[str, Any]]:
        cats = self.list_categories(site_id, source)
        by_id = {c["id"]: {**c, "children": []} for c in cats}
        roots = []
        for c in by_id.values():
            p = by_id.get(c["parent_id"]) if c["parent_id"] else None
            (p["children"] if p else roots).append(c)
        return roots

    # ------------------------------------------------------------------ clusters
    def list_clusters(self, site_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as cx:
            rows = [dict(r._mapping) for r in cx.execute(select(content_clusters).where(content_clusters.c.site_id == site_id).order_by(content_clusters.c.name))]
        for r in rows:
            r["metadata"] = loads(r["metadata"], {})
        return rows

    def upsert_cluster(self, site_id: str, name: str, cid: int | None = None, **fields) -> dict[str, Any]:
        now = utcnow()
        vals = {k: (dumps(v) if k == "metadata" else v) for k, v in fields.items() if k in content_clusters.c and k not in ("id", "site_id")}
        with self.engine.begin() as cx:
            if cid:
                cx.execute(update(content_clusters).where(and_(content_clusters.c.site_id == site_id, content_clusters.c.id == cid)).values(name=name, updated_at=now, **vals))
            else:
                cid = int(cx.execute(content_clusters.insert().values(site_id=site_id, name=name, slug=slugify(name), created_at=now, updated_at=now, **vals)).inserted_primary_key[0])
            r = cx.execute(select(content_clusters).where(content_clusters.c.id == cid)).first()
        d = dict(r._mapping); d["metadata"] = loads(d["metadata"], {})
        return d

    def delete_cluster(self, site_id: str, cid: int) -> bool:
        with self.engine.begin() as cx:
            cx.execute(update(content_plans).where(and_(content_plans.c.site_id == site_id, content_plans.c.content_cluster_id == cid)).values(content_cluster_id=None))
            r = cx.execute(delete(content_clusters).where(and_(content_clusters.c.site_id == site_id, content_clusters.c.id == cid)))
        return bool(r.rowcount)

    # ------------------------------------------------------------------ recommendations (permanent)
    def save_recommendation(self, site_id: str, kind: str, payload: dict[str, Any], plan_id: int | None = None, keyword_id: int | None = None, category_id: int | None = None,
                            engine: str = "rules-v1") -> dict[str, Any]:
        """New version; previous `new` rows for the same (plan|keyword|category, kind) become `superseded`. Human decisions are kept."""
        now = utcnow()
        with self.engine.begin() as cx:
            conds = [content_plan_recommendations.c.site_id == site_id, content_plan_recommendations.c.kind == kind]
            conds.append(content_plan_recommendations.c.plan_id == plan_id if plan_id is not None else content_plan_recommendations.c.plan_id.is_(None))
            conds.append(content_plan_recommendations.c.keyword_id == keyword_id if keyword_id is not None else content_plan_recommendations.c.keyword_id.is_(None))
            conds.append(content_plan_recommendations.c.category_id == category_id if category_id is not None else content_plan_recommendations.c.category_id.is_(None))
            prev = cx.execute(select(content_plan_recommendations).where(and_(*conds)).order_by(content_plan_recommendations.c.version.desc())).first()
            version = 1
            if prev:
                pm = prev._mapping
                same = loads(pm["payload"], {}) == payload and pm["status"] in ("new", "accepted", "dismissed", "applied")
                if same:
                    return self._rec_dict(pm)
                version = int(pm["version"]) + 1
                cx.execute(update(content_plan_recommendations).where(and_(*conds, content_plan_recommendations.c.status == "new")).values(status="superseded"))
            rid = int(cx.execute(content_plan_recommendations.insert().values(
                site_id=site_id, plan_id=plan_id, keyword_id=keyword_id, category_id=category_id, kind=kind, action=payload.get("action"), title=payload.get("title"),
                page_type=payload.get("page_type"), intent=payload.get("intent"), priority=payload.get("priority"), priority_score=payload.get("priority_score"),
                confidence=payload.get("confidence"), reasons=dumps(payload.get("reasons_fa") or payload.get("reasons") or []), payload=dumps(payload), version=version, status="new",
                engine=engine, computed_at=now)).inserted_primary_key[0])
            r = cx.execute(select(content_plan_recommendations).where(content_plan_recommendations.c.id == rid)).first()
        return self._rec_dict(r._mapping)

    @staticmethod
    def _rec_dict(m) -> dict[str, Any]:
        d = dict(m); d["reasons"] = loads(d["reasons"], []); d["payload"] = loads(d["payload"], {}); d["kind_fa"] = RECOMMENDATION_FA.get(d["kind"], d["kind"])
        return d

    def list_recommendations(self, site_id: str, status: str | None = "new", kind: str | None = None, plan_id: int | None = None, keyword_id: int | None = None, limit: int = 500) -> list[dict[str, Any]]:
        c = content_plan_recommendations.c
        conds = [c.site_id == site_id]
        if status:
            conds.append(c.status.in_(status.split(",")))
        if kind:
            conds.append(c.kind == kind)
        if plan_id is not None:
            conds.append(c.plan_id == plan_id)
        if keyword_id is not None:
            conds.append(c.keyword_id == keyword_id)
        with self.engine.connect() as cx:
            rows = cx.execute(select(content_plan_recommendations).where(and_(*conds)).order_by(c.priority_score.desc(), c.id.desc()).limit(limit)).all()
        return [self._rec_dict(r._mapping) for r in rows]

    def get_recommendation(self, site_id: str, rid: int) -> dict[str, Any] | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(content_plan_recommendations).where(and_(content_plan_recommendations.c.site_id == site_id, content_plan_recommendations.c.id == rid))).first()
        return self._rec_dict(r._mapping) if r else None

    def set_recommendation_status(self, site_id: str, rid: int, status: str, actor: str = "user", plan_id: int | None = None) -> dict[str, Any] | None:
        vals: dict[str, Any] = {"status": status, "decided_at": utcnow(), "decided_by": actor}
        if plan_id is not None:
            vals["plan_id"] = plan_id
        with self.engine.begin() as cx:
            cx.execute(update(content_plan_recommendations).where(and_(content_plan_recommendations.c.site_id == site_id, content_plan_recommendations.c.id == rid)).values(**vals))
        return self.get_recommendation(site_id, rid)

    # ------------------------------------------------------------------ imports / sources
    def record_import(self, site_id: str, source: str, filename: str | None, fmt: str | None, rows_total: int, created: int, updated: int, skipped: int, errors: list, mapping: dict, dry_run: bool, source_id: int | None = None) -> int:
        with self.engine.begin() as cx:
            return int(cx.execute(content_plan_imports.insert().values(site_id=site_id, source=source, source_id=source_id, filename=filename, format=fmt, rows_total=rows_total, rows_created=created, rows_updated=updated,
                                                                       rows_skipped=skipped, errors=dumps(errors[:100]), mapping=dumps(mapping), dry_run=int(dry_run), created_at=utcnow())).inserted_primary_key[0])

    def list_imports(self, site_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.engine.connect() as cx:
            rows = cx.execute(select(content_plan_imports).where(content_plan_imports.c.site_id == site_id).order_by(content_plan_imports.c.id.desc()).limit(limit)).all()
        return [{**dict(r._mapping), "errors": loads(r._mapping["errors"], []), "mapping": loads(r._mapping["mapping"], {})} for r in rows]

    def list_sources(self, site_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as cx:
            rows = cx.execute(select(content_plan_sources).where(content_plan_sources.c.site_id == site_id).order_by(content_plan_sources.c.id)).all()
        return [self._src(r._mapping) for r in rows]

    @staticmethod
    def _src(m) -> dict[str, Any]:
        d = dict(m); d["mapping"] = loads(d["mapping"], {}); d["key_columns"] = loads(d["key_columns"], []); d["last_result"] = loads(d["last_result"], {})
        d["enabled"] = bool(d["enabled"]); d["auto_sync"] = bool(d["auto_sync"])
        return d

    def get_source(self, site_id: str, sid: int) -> dict[str, Any] | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(content_plan_sources).where(and_(content_plan_sources.c.site_id == site_id, content_plan_sources.c.id == sid))).first()
        return self._src(r._mapping) if r else None

    def save_source(self, site_id: str, sid: int | None = None, **fields) -> dict[str, Any]:
        now = utcnow()
        vals = {k: (dumps(v) if k in ("mapping", "key_columns", "last_result") else (int(v) if k in ("enabled", "auto_sync") else v)) for k, v in fields.items() if k in content_plan_sources.c and k not in ("id", "site_id")}
        with self.engine.begin() as cx:
            if sid:
                cx.execute(update(content_plan_sources).where(and_(content_plan_sources.c.site_id == site_id, content_plan_sources.c.id == sid)).values(updated_at=now, **vals))
            else:
                sid = int(cx.execute(content_plan_sources.insert().values(site_id=site_id, created_at=now, updated_at=now, **vals)).inserted_primary_key[0])
        return self.get_source(site_id, sid)  # type: ignore[return-value]

    def delete_source(self, site_id: str, sid: int) -> bool:
        with self.engine.begin() as cx:
            r = cx.execute(delete(content_plan_sources).where(and_(content_plan_sources.c.site_id == site_id, content_plan_sources.c.id == sid)))
        return bool(r.rowcount)

    # ------------------------------------------------------------------ generation jobs (prepared only)
    def create_generation_job(self, site_id: str, plan_id: int, kind: str, content_item_id: int | None, params: dict[str, Any], requested_by: str | None) -> dict[str, Any]:
        now = utcnow()
        with self.engine.begin() as cx:
            jid = int(cx.execute(content_plan_generation_jobs.insert().values(site_id=site_id, plan_id=plan_id, content_item_id=content_item_id, kind=kind, status="prepared", params=dumps(params),
                                                                              requested_by=requested_by, created_at=now, updated_at=now)).inserted_primary_key[0])
        return self.get_generation_job(site_id, jid)  # type: ignore[return-value]

    def get_generation_job(self, site_id: str, jid: int) -> dict[str, Any] | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(content_plan_generation_jobs).where(and_(content_plan_generation_jobs.c.site_id == site_id, content_plan_generation_jobs.c.id == jid))).first()
        return {**dict(r._mapping), "params": loads(r._mapping["params"], {})} if r else None

    def list_generation_jobs(self, site_id: str, plan_id: int | None = None) -> list[dict[str, Any]]:
        conds = [content_plan_generation_jobs.c.site_id == site_id]
        if plan_id is not None:
            conds.append(content_plan_generation_jobs.c.plan_id == plan_id)
        with self.engine.connect() as cx:
            rows = cx.execute(select(content_plan_generation_jobs).where(and_(*conds)).order_by(content_plan_generation_jobs.c.id.desc())).all()
        return [{**dict(r._mapping), "params": loads(r._mapping["params"], {})} for r in rows]

    def update_generation_job(self, site_id: str, jid: int, **fields) -> dict[str, Any] | None:
        vals = {k: (dumps(v) if k == "params" else v) for k, v in fields.items() if k in content_plan_generation_jobs.c and k not in ("id", "site_id")}
        if vals:
            vals["updated_at"] = utcnow()
            with self.engine.begin() as cx:
                cx.execute(update(content_plan_generation_jobs).where(and_(content_plan_generation_jobs.c.site_id == site_id, content_plan_generation_jobs.c.id == jid)).values(**vals))
        return self.get_generation_job(site_id, jid)
