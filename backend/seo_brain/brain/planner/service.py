"""PlannerService — orchestrates plans ↔ content items (1:1, on demand), status mirroring through the Phase-6 workflow,
analysis (recommendation + category + existing pages + link prep + advanced fields), import/export (+Google Sheet source),
calendar, brief hand-off, generation-job preparation (no AI run), publishing metadata (publishing itself disabled)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import Engine, text

from ...brain.content import ContentService, WorkflowError
from ...brain.content.repository import ContentItem
from ...db.repositories.base import utcnow
from ...db.repositories.sites import SitesRepository
from .categories import CategoryIntelligence
from .context import PlannerContext, build_planner_context
from .graph_sync import PlannerGraphSync
from .importer import detect_mapping, fetch_sheet, normalize_row, parse_table, to_csv, to_xlsx, template_csv, EXPORT_COLUMNS
from .keyword_mapping import KeywordMapper
from .linking_prep import LinkPrep
from .recommend import for_plan, funnel_stage_for
from .repository import (COLUMNS, EDITABLE, GEN_JOB_KINDS, ITEM_STATUS_OF, PLAN_STATUSES, PLAN_TRANSITIONS, STATUS_FA, ContentPlan, PlannerRepository, slugify,
                         CATEGORY_SOURCES, PAGE_TYPES, INTENTS, PRIORITIES, FUNNEL_STAGES, KEYWORD_ROLES, RECOMMENDATION_KINDS, PAGE_TYPE_FA, INTENT_FA, PRIORITY_FA, FUNNEL_FA, GAP_FA, ROLE_FA,
                         CATEGORY_SOURCE_FA, RECOMMENDATION_FA, CONTENT_GAPS)

# reverse map: content item status → planner status (researching is preserved when the item is still planned)
PLAN_STATUS_OF_ITEM = {"planned": "planned", "brief_ready": "brief_ready", "writing": "writing", "review": "review", "approved": "approved", "published": "published"}
GRAPH_SYNC_THRESHOLD = 500


class PlannerError(ValueError):
    pass


class PlannerService:
    def __init__(self, engine: Engine, content: ContentService | None = None, category_fetch=None):
        self.engine = engine
        self.repo = PlannerRepository(engine)
        self.content = content or ContentService(engine)
        self.cats = CategoryIntelligence(engine, category_fetch)
        self.mapper = KeywordMapper(engine)
        self.links = LinkPrep(engine)
        self.graph = PlannerGraphSync(engine)
        self.sites = SitesRepository(engine)

    # ------------------------------------------------------------------ meta
    def meta(self) -> dict[str, Any]:
        return {"statuses": [{"key": s, "fa": STATUS_FA[s], "item_status": ITEM_STATUS_OF[s]} for s in PLAN_STATUSES], "transitions": PLAN_TRANSITIONS,
                "page_types": [{"key": k, "fa": PAGE_TYPE_FA[k]} for k in PAGE_TYPES], "intents": [{"key": k, "fa": INTENT_FA[k]} for k in INTENTS],
                "priorities": [{"key": k, "fa": PRIORITY_FA[k]} for k in PRIORITIES], "funnel_stages": [{"key": k, "fa": FUNNEL_FA[k]} for k in FUNNEL_STAGES],
                "content_gaps": [{"key": k, "fa": GAP_FA[k]} for k in CONTENT_GAPS], "keyword_roles": [{"key": k, "fa": ROLE_FA[k]} for k in KEYWORD_ROLES],
                "category_sources": [{"key": k, "fa": CATEGORY_SOURCE_FA[k]} for k in CATEGORY_SOURCES], "recommendation_kinds": [{"key": k, "fa": RECOMMENDATION_FA[k]} for k in RECOMMENDATION_KINDS],
                "generation_job_kinds": list(GEN_JOB_KINDS), "columns": COLUMNS, "export_columns": EXPORT_COLUMNS, "views": ["table", "kanban", "graph"],
                "publishing": {"enabled": False, "note": "انتشار غیرفعال است — فقط متادیتای انتشار آماده می‌شود؛ انتشار واقعی توسط انسان در وردپرس انجام می‌شود"},
                "ai_generation": {"enabled": False, "note": "لایه تولید AI فقط آماده‌سازی می‌شود: برنامه → کار تولید → آیتم محتوا → پیش‌نویس (اجرا در استودیوی AI با تأیید انسانی)"}}

    # ------------------------------------------------------------------ enrichment
    def enrich(self, plans: list[ContentPlan], ctx: PlannerContext | None = None) -> list[dict[str, Any]]:
        if not plans:
            return []
        site_id = plans[0].site_id
        cats = {c["id"]: c for c in self.repo.list_categories(site_id)}
        item_ids = [p.content_item_id for p in plans if p.content_item_id]
        items: dict[int, dict] = {}
        if item_ids:
            with self.engine.connect() as cx:
                for r in cx.execute(text("SELECT id, status, url, brief_id, publish_date FROM content_items WHERE site_id=:s"), {"s": site_id}).mappings().all():
                    if r["id"] in item_ids:
                        items[r["id"]] = dict(r)
                scores = {r[0]: (r[1], r[2]) for r in cx.execute(text("SELECT content_id, total, created_at FROM content_scores WHERE site_id=:s ORDER BY created_at ASC"), {"s": site_id}).all()}
                reviews = {r[0]: r[1] for r in cx.execute(text("SELECT content_id, review_status FROM content_drafts WHERE site_id=:s ORDER BY version ASC"), {"s": site_id}).all()}
                drafts = {r[0]: r[1] for r in cx.execute(text("SELECT content_id, COUNT(*) FROM content_drafts WHERE site_id=:s GROUP BY content_id"), {"s": site_id}).all()}
        else:
            scores, reviews, drafts = {}, {}, {}
        kwmap: dict[int, list[dict]] = {}
        with self.engine.connect() as cx:
            for r in cx.execute(text("SELECT pk.content_plan_id, k.id, k.keyword, pk.role, k.volume, k.intent FROM content_plan_keywords pk JOIN keywords k ON k.id=pk.keyword_id WHERE pk.site_id=:s"), {"s": site_id}).all():
                kwmap.setdefault(r[0], []).append({"id": r[1], "keyword": r[2], "role": r[3], "volume": r[4], "intent": r[5]})
        out = []
        for p in plans:
            d = p.to_dict()
            c = cats.get(p.category_id) if p.category_id else None
            d["category"] = {"id": c["id"], "name": c["name"], "source": c["source"], "parent_id": c["parent_id"]} if c else None
            d["parent_category"] = cats[c["parent_id"]]["name"] if c and c["parent_id"] in cats else None
            d["category_suggested"] = ({"id": p.category_suggested_id, "name": cats[p.category_suggested_id]["name"], "reason": p.category_reason} if p.category_suggested_id in cats else None)
            it = items.get(p.content_item_id) if p.content_item_id else None
            d["content_item"] = ({"id": it["id"], "status": it["status"], "has_brief": bool(it["brief_id"]), "url": it["url"], "latest_score": (scores.get(it["id"]) or (None,))[0],
                                  "review_status": reviews.get(it["id"], "none"), "draft_count": drafts.get(it["id"], 0)} if it else None)
            d["keywords"] = kwmap.get(p.id, [])
            out.append(d)
        return out

    def detail(self, site_id: str, pid: int) -> dict[str, Any] | None:
        p = self.repo.get_plan(site_id, pid)
        if not p:
            return None
        d = self.enrich([p])[0]
        d["events"] = self.repo.events(site_id, pid)
        d["recommendations"] = self.repo.list_recommendations(site_id, status=None, plan_id=pid, limit=20)
        d["generation_jobs"] = self.repo.list_generation_jobs(site_id, pid)
        return d

    # ------------------------------------------------------------------ CRUD
    def create(self, site_id: str, fields: dict[str, Any], actor: str = "user", analyze: bool = True) -> dict[str, Any]:
        title = (fields.get("title") or fields.get("primary_keyword") or "").strip()
        if not title:
            raise PlannerError("عنوان یا کلمه کلیدی اصلی لازم است")
        fields = self._resolve_fields(site_id, dict(fields))
        p = ContentPlan(site_id=site_id, title=title, **{k: v for k, v in fields.items() if k in ContentPlan.__dataclass_fields__ and k not in ("site_id", "title", "id")})
        p.status = p.status if p.status in PLAN_STATUSES else "planned"
        p.slug = p.slug or slugify(title)
        p.source = p.source or "manual"
        p.created_by = actor
        p = self.repo.create_plan(p, actor)
        if p.primary_keyword_id:
            self.repo.set_keywords(site_id, p.id, [{"keyword_id": p.primary_keyword_id, "role": "primary", "source": "manual"}])
        if analyze:
            self.analyze_plan(site_id, p.id, actor="system")
        self._maybe_sync_graph(site_id)
        return self.detail(site_id, p.id)  # type: ignore[return-value]

    def _resolve_fields(self, site_id: str, f: dict[str, Any]) -> dict[str, Any]:
        """Resolve primary keyword text → id, category name → id, derive funnel stage."""
        from ...brain.keywords.repository import KeywordsRepository
        from ...brain.keywords.normalize import normalize_keyword
        kw = KeywordsRepository(self.engine)
        if f.get("primary_keyword_id") and not f.get("primary_keyword"):
            k = kw.get(site_id, int(f["primary_keyword_id"]))
            if k:
                f["primary_keyword"] = k.keyword
        elif f.get("primary_keyword") and not f.get("primary_keyword_id"):
            k = kw.get_by_normalized(site_id, normalize_keyword(f["primary_keyword"]))
            if k:
                f["primary_keyword_id"] = k.id
                for a, b in (("search_volume", "volume"), ("keyword_difficulty", "difficulty"), ("intent", "intent"), ("cluster_id", "cluster_id"), ("topic_id", "topic")):
                    if f.get(a) in (None, "") and getattr(k, b, None) not in (None, ""):
                        f[a] = getattr(k, b)
        if f.get("category") and not f.get("category_id"):
            name = str(f.pop("category")).strip()
            cats = self.repo.list_categories(site_id)
            m = next((c for c in cats if c["name"] == name or c["slug"] == name), None)
            if not m and name:
                m = self.repo.upsert_category(site_id, "manual", name)
            f["category_id"] = m["id"] if m else None
        f.pop("category", None); f.pop("parent_category", None)
        if not f.get("funnel_stage") and (f.get("intent") or f.get("page_type")):
            f["funnel_stage"] = funnel_stage_for(f.get("intent"), f.get("page_type"))
        return f

    def update(self, site_id: str, pid: int, fields: dict[str, Any], actor: str = "user") -> dict[str, Any] | None:
        cur = self.repo.get_plan(site_id, pid)
        if not cur:
            return None
        fields = {k: v for k, v in fields.items() if k in EDITABLE or k in ("category",)}
        if "status" in fields and fields["status"] != cur.status:
            self.transition(site_id, pid, fields.pop("status"), actor)
            cur = self.repo.get_plan(site_id, pid)
        fields = self._resolve_fields(site_id, fields)
        if fields:
            self.repo.update_plan(site_id, pid, actor=actor, **fields)
            # mirror lightweight fields to the linked item
            if cur and cur.content_item_id:
                mirror = {k: fields[k] for k in ("title", "publish_date", "publish_time", "url", "priority", "intent") if k in fields}
                if "primary_keyword_id" in fields:
                    mirror["target_keyword_id"] = fields["primary_keyword_id"]; mirror["target_keyword"] = fields.get("primary_keyword")
                if mirror:
                    self.content.repo.update(site_id, cur.content_item_id, **mirror)
            if "primary_keyword_id" in fields and fields["primary_keyword_id"]:
                self.repo.set_keywords(site_id, pid, [{"keyword_id": fields["primary_keyword_id"], "role": "primary", "source": "manual"}], replace_roles=["primary"])
        self._maybe_sync_graph(site_id)
        return self.detail(site_id, pid)

    def bulk(self, site_id: str, ids: list[int], patch: dict[str, Any], actor: str = "user") -> dict[str, Any]:
        done, errors = [], []
        for pid in ids:
            try:
                if self.update(site_id, pid, dict(patch), actor):
                    done.append(pid)
                else:
                    errors.append({"id": pid, "error": "not found"})
            except (PlannerError, WorkflowError) as e:
                errors.append({"id": pid, "error": str(e)})
        return {"updated": done, "errors": errors}

    def delete(self, site_id: str, pid: int, with_item: bool = False, actor: str = "user") -> bool:
        p = self.repo.get_plan(site_id, pid)
        if not p:
            return False
        if with_item and p.content_item_id:
            self.content.repo.delete(site_id, p.content_item_id)
        ok = self.repo.delete_plan(site_id, pid, actor)
        with self.engine.begin() as cx:
            cx.execute(text("DELETE FROM link_suggestions WHERE site_id=:s AND scope='plan' AND plan_id=:p"), {"s": site_id, "p": pid})
        self._maybe_sync_graph(site_id)
        return ok

    # ------------------------------------------------------------------ status mirroring
    def transition(self, site_id: str, pid: int, to_status: str, actor: str = "user", note: str | None = None) -> dict[str, Any]:
        p = self.repo.get_plan(site_id, pid)
        if not p:
            raise PlannerError("plan not found")
        if to_status not in PLAN_STATUSES:
            raise PlannerError(f"وضعیت نامعتبر: {to_status}")
        if to_status not in PLAN_TRANSITIONS.get(p.status, ()) and to_status != p.status:
            raise WorkflowError(f"گذار از «{STATUS_FA[p.status]}» به «{STATUS_FA[to_status]}» مجاز نیست")
        item_target = ITEM_STATUS_OF[to_status]
        if p.content_item_id:
            it = self.content.repo.get(site_id, p.content_item_id)
            if it and it.status != item_target:
                from ...brain.content import ContentIntelligenceService
                ContentIntelligenceService(self.engine, None).check_gate(site_id, p.content_item_id, item_target)   # Phase-7 strict gate (review → approved)
                self.content.repo.transition(site_id, p.content_item_id, item_target, actor=actor, note=note or f"از برنامه‌ریز محتوا (#{pid})")
        elif to_status in ("writing", "review", "approved", "published"):
            raise WorkflowError("برای این وضعیت ابتدا آیتم محتوا ساخته شود (بریف/تولید)")
        self.repo.update_plan(site_id, pid, actor=actor, status=to_status)
        return self.detail(site_id, pid)  # type: ignore[return-value]

    def sync_from_item(self, site_id: str, cid: int) -> dict[str, Any] | None:
        """Called when the content item changed (status/score) — mirror back to the plan (planner-only `researching` survives)."""
        p = self.repo.get_plan_by_item(site_id, cid)
        if not p:
            return None
        it = self.content.repo.get(site_id, cid)
        if not it:
            return None
        new = PLAN_STATUS_OF_ITEM.get(it.status, p.status)
        if it.status == "planned" and p.status == "researching":
            new = "researching"
        fields: dict[str, Any] = {}
        if new != p.status:
            fields["status"] = new
        with self.engine.connect() as cx:
            sc = cx.execute(text("SELECT total FROM content_scores WHERE site_id=:s AND content_id=:c ORDER BY id DESC LIMIT 1"), {"s": site_id, "c": cid}).first()
        if sc and sc[0] != p.content_score:
            fields["content_score"] = sc[0]
        if it.url and it.url != p.url and not p.url:
            fields["url"] = it.url
        if fields:
            self.repo.update_plan(site_id, p.id, actor="system", event="linked_content", **fields)
        return self.detail(site_id, p.id)

    def sync_all_from_items(self, site_id: str) -> int:
        n = 0
        for p in self.repo.all_plans(site_id):
            if p.content_item_id and self.sync_from_item(site_id, p.content_item_id):
                n += 1
        return n

    # ------------------------------------------------------------------ content item link (1:1)
    def ensure_item(self, site_id: str, pid: int, actor: str = "user", content_id: int | None = None) -> dict[str, Any]:
        p = self.repo.get_plan(site_id, pid)
        if not p:
            raise PlannerError("plan not found")
        if p.content_item_id:
            return {"content_id": p.content_item_id, "created": False}
        if content_id:
            it = self.content.repo.get(site_id, content_id)
            if not it:
                raise PlannerError("content item not found")
            if self.repo.get_plan_by_item(site_id, content_id):
                raise PlannerError("این آیتم محتوا قبلاً به برنامه دیگری متصل است")
            created = False
        else:
            it = self.content.create(site_id, p.title, target_keyword_id=p.primary_keyword_id, target_keyword=p.primary_keyword, intent=p.intent, cluster_id=p.cluster_id, topic=p.topic_id,
                                     priority=p.priority, publish_date=p.publish_date, publish_time=p.publish_time, url=p.url,
                                     metadata={"plan_id": pid, "page_type": p.page_type, "seo_title": p.seo_title, "meta_description": p.meta_description, "source": "content_planner"})
            created = True
        self.repo.update_plan(site_id, pid, actor=actor, event="linked_content", content_item_id=it.id)
        # align statuses (item may already be further along)
        self.sync_from_item(site_id, it.id)
        self._maybe_sync_graph(site_id)
        return {"content_id": it.id, "created": created}

    def brief(self, site_id: str, pid: int, use_ai: bool = False, mark_ready: bool = True, actor: str = "user") -> dict[str, Any]:
        p = self.repo.get_plan(site_id, pid)
        if not p:
            raise PlannerError("plan not found")
        if not (p.primary_keyword or p.primary_keyword_id):
            raise PlannerError("برای ساخت بریف، کلمه کلیدی اصلی لازم است")
        cid = self.ensure_item(site_id, pid, actor)["content_id"]
        it = self.content.repo.get(site_id, cid)
        # plan hints travel with the item metadata → BriefGenerator output is enriched below (additive)
        self.content.repo.update(site_id, cid, metadata={**(it.metadata or {}), "plan_id": pid, "plan_hints": {"heading_structure": p.heading_structure, "secondary_keywords": p.secondary_keywords,
                                                                                                          "seo_title": p.seo_title, "meta_description": p.meta_description, "page_type": p.page_type, "target_audience": p.target_audience,
                                                                                                          "link_targets": p.link_targets[:8], "category_id": p.category_id}})
        b = self.content.generate_brief(site_id, cid, use_ai=use_ai, mark_ready=mark_ready)
        d = b.to_dict()
        d["plan_hints"] = {"heading_structure": p.heading_structure, "secondary_keywords": p.secondary_keywords, "internal_link_targets": p.link_targets[:8], "external_references": (p.metadata or {}).get("external_references", []),
                           "cta": (p.publishing or {}).get("cta")}
        self.sync_from_item(site_id, cid)
        self.repo.add_event(site_id, pid, "brief_created", actor, {"brief_id": b.id, "version": b.version, "content_id": cid})
        return d

    # ------------------------------------------------------------------ analysis (recommendation engine)
    def analyze_plan(self, site_id: str, pid: int, ctx: PlannerContext | None = None, actor: str = "user", link_prep: bool = True) -> dict[str, Any] | None:
        p = self.repo.get_plan(site_id, pid)
        if not p:
            return None
        ctx = ctx or build_planner_context(self.engine, site_id)
        cat = self.cats.suggest(site_id, keyword=p.primary_keyword or p.title, keyword_id=p.primary_keyword_id, plan_id=pid, ctx=ctx)
        rec = for_plan(ctx, p, cat["suggested"])
        saved = self.repo.save_recommendation(site_id, rec["action"], rec, plan_id=pid, keyword_id=p.primary_keyword_id, category_id=(cat["suggested"] or {}).get("id"))
        if cat["suggested"]:
            self.repo.save_recommendation(site_id, "category", {"action": "set_category", "category_id": cat["suggested"]["id"], "category": cat["suggested"]["name"], "reasons_fa": cat["suggested"]["reasons_fa"], "confidence": cat["confidence"], "candidates": cat["candidates"]}, plan_id=pid)
        fields: dict[str, Any] = {"recommendation": {k: rec[k] for k in ("engine", "action", "action_fa", "title", "page_type", "intent", "priority", "priority_score", "reasons_fa", "gaps_fa", "confidence") if k in rec},
                                  "recommendation_id": saved["id"], "existing_pages": rec["existing_pages"], "content_gap": rec["content_gap"], "cannibalization_risk": rec["cannibalization_risk"],
                                  "cannibalization": rec["cannibalization"], "ranking_url": rec["ranking_url"], "ranking_position": rec["ranking_position"], "traffic_opportunity": rec["traffic_opportunity"],
                                  "priority_score": rec["priority_score"], "serp_intent": p.serp_intent or rec["serp_intent"], "funnel_stage": p.funnel_stage or rec["funnel_stage"],
                                  "category_suggested_id": (cat["suggested"] or {}).get("id"), "category_reason": " · ".join((cat["suggested"] or {}).get("reasons_fa", [])) or None}
        # fill blanks (never overwrite human choices)
        for k in ("intent", "page_type", "priority", "target_audience"):
            if not getattr(p, k) and rec.get(k):
                fields[k] = rec[k]
        k = ctx.keyword_of(p.primary_keyword_id) if p.primary_keyword_id else ctx.keyword_of(p.primary_keyword)
        if k:
            if not p.primary_keyword_id:
                fields["primary_keyword_id"] = k.id
            for a, b in (("search_volume", "volume"), ("keyword_difficulty", "difficulty"), ("cluster_id", "cluster_id"), ("topic_id", "topic")):
                if getattr(p, a) in (None, "") and getattr(k, b) not in (None, ""):
                    fields[a] = getattr(k, b)
        # ai_priority placeholder: same scale, reserved for the learning layer — today = rules score adjusted by accepted planner patterns count
        fields["ai_priority"] = round(min(100.0, rec["priority_score"] + 2 * len([x for x in ctx.memory.get("successful_patterns", []) if x.get("source") == "content_planner"])), 1)
        self.repo.update_plan(site_id, pid, actor=actor, event="analyzed", **fields)
        if fields.get("primary_keyword_id"):
            self.repo.set_keywords(site_id, pid, [{"keyword_id": fields["primary_keyword_id"], "role": "primary", "source": "brain"}], replace_roles=["primary"])
        # secondary keyword text → ids (mapping)
        sec = []
        for s in p.secondary_keywords or []:
            kk = ctx.keyword_of(s)
            if kk and kk.id != (fields.get("primary_keyword_id") or p.primary_keyword_id):
                sec.append({"keyword_id": kk.id, "role": "secondary", "source": "brain"})
        if sec:
            self.repo.set_keywords(site_id, pid, sec)
        links = None
        if link_prep:
            try:
                p2 = self.repo.get_plan(site_id, pid)
                links = self.links.prepare(ctx, p2)  # type: ignore[arg-type]
                self.repo.update_plan(site_id, pid, actor="system", event="links_prepared", link_targets=links["inbound"] + links["outbound"])
                if links["count"]:
                    self.repo.save_recommendation(site_id, "link_prep", {"action": "prepare_links", "count": links["count"], "inbound": links["inbound"][:5], "outbound": links["outbound"][:5],
                                                                          "reasons_fa": [f"{len(links['inbound'])} لینک ورودی و {len(links['outbound'])} لینک خروجی پیشنهادی از موتور لینک داخلی"]}, plan_id=pid)
            except Exception as e:  # noqa: BLE001 — link prep is advisory; never block analysis
                links = {"error": str(e)}
        return {"plan": self.detail(site_id, pid), "recommendation": rec, "category": cat, "links": links}

    def analyze_all(self, site_id: str, ids: list[int] | None = None, link_prep: bool = True) -> dict[str, Any]:
        ctx = build_planner_context(self.engine, site_id)
        plans = [p for p in ctx.plans if not ids or p.id in ids]
        cats = self.cats.analyze(site_id, ctx)
        n = 0
        for p in plans:
            self.analyze_plan(site_id, p.id, ctx, actor="system", link_prep=link_prep); n += 1
        self.graph.sync(site_id)
        return {"analyzed": n, "categories": cats["analyzed"]}

    # ------------------------------------------------------------------ suggestions inbox
    def suggestions(self, site_id: str, status: str = "new", kind: str | None = None) -> list[dict[str, Any]]:
        rows = self.repo.list_recommendations(site_id, status=status, kind=kind)
        plans = {p.id: p.title for p in self.repo.all_plans(site_id)}
        for r in rows:
            r["plan_title"] = plans.get(r["plan_id"]) if r["plan_id"] else None
        return rows

    def decide_suggestion(self, site_id: str, rid: int, status: str, actor: str = "user") -> dict[str, Any] | None:
        rec = self.repo.get_recommendation(site_id, rid)
        if not rec:
            return None
        if status not in ("accepted", "dismissed"):
            raise PlannerError("status must be accepted|dismissed")
        created = None
        if status == "accepted":
            pl = rec["payload"]
            if rec["kind"] in ("create_new", "gap", "add_to_cluster", "improve_page", "optimize_existing", "merge") and not rec["plan_id"]:
                created = self.create(site_id, {"title": pl.get("title") or pl.get("keyword"), "primary_keyword_id": rec.get("keyword_id"), "primary_keyword": pl.get("keyword"), "intent": pl.get("intent"),
                                                "page_type": pl.get("page_type"), "category_id": (pl.get("category") or {}).get("id") if isinstance(pl.get("category"), dict) else pl.get("category_id"),
                                                "priority": pl.get("priority"), "url": pl.get("ranking_url"), "source": f"suggestion:{rid}"}, actor=actor)
                if rec.get("keyword_id"):
                    self.mapper.kw.update(site_id, rec["keyword_id"], status="planned")
            elif rec["kind"] == "category" and rec["plan_id"] and pl.get("category_id"):
                self.repo.update_plan(site_id, rec["plan_id"], actor=actor, event="category_set", category_id=pl["category_id"])
        out = self.repo.set_recommendation_status(site_id, rid, "applied" if created else status, actor, plan_id=created["id"] if created else None)
        if created:
            out["created_plan"] = {"id": created["id"], "title": created["title"]}
        return out

    # ------------------------------------------------------------------ calendar
    def calendar(self, site_id: str, date_from: str | None, date_to: str | None, category_id: int | None = None, status: str | None = None, priority: str | None = None) -> dict[str, Any]:
        today = date.today()
        f = date_from or (today.replace(day=1) - timedelta(days=7)).isoformat()
        t = date_to or (today + timedelta(days=45)).isoformat()
        plans, _ = self.repo.list_plans(site_id, status=status, category_id=category_id, priority=priority, date_from=f, date_to=t, sort="publish_date", order="asc", limit=2000)
        days: dict[str, list[dict]] = {}
        for d in self.enrich(plans):
            days.setdefault(d["publish_date"], []).append(d)
        unscheduled, _ = self.repo.list_plans(site_id, status=status, category_id=category_id, priority=priority, unscheduled=True, limit=300)
        # content items without a plan (still shown so the old calendar keeps its items)
        with self.engine.connect() as cx:
            orphan = [dict(r) for r in cx.execute(text("SELECT ci.id, ci.title, ci.status, ci.publish_date, ci.priority, ci.target_keyword FROM content_items ci LEFT JOIN content_plans cp ON cp.content_item_id=ci.id AND cp.site_id=ci.site_id "
                                                       "WHERE ci.site_id=:s AND cp.id IS NULL AND ci.publish_date BETWEEN :f AND :t"), {"s": site_id, "f": f, "t": t}).mappings().all()]
        for o in orphan:
            days.setdefault(o["publish_date"], []).append({**o, "kind": "content_item", "status_fa": STATUS_FA.get(o["status"], o["status"])})
        return {"from": f, "to": t, "days": days, "unscheduled": self.enrich(unscheduled), "counts": self.repo.counts(site_id), "categories": [{"id": c["id"], "name": c["name"], "source": c["source"]} for c in self.repo.list_categories(site_id)]}

    def board(self, site_id: str, category_id: int | None = None) -> dict[str, Any]:
        plans, _ = self.repo.list_plans(site_id, category_id=category_id, limit=5000)
        cols = {s: [] for s in PLAN_STATUSES}
        for d in self.enrich(plans):
            cols[d["status"]].append(d)
        return {"columns": [{"status": s, "status_fa": STATUS_FA[s], "items": cols[s]} for s in PLAN_STATUSES], "counts": self.repo.counts(site_id)}

    # ------------------------------------------------------------------ import / export / sources
    def import_table(self, site_id: str, data: bytes, filename: str | None, mapping: dict[str, str] | None = None, dry_run: bool = False, key_columns: list[str] | None = None,
                     source: str = "file", source_id: int | None = None, actor: str = "user") -> dict[str, Any]:
        fmt, cols, rows = parse_table(data, filename)
        mp = mapping or detect_mapping(cols)
        keys = key_columns or ["url", "primary_keyword", "title"]
        created = updated = skipped = 0
        errors: list[dict] = []; preview: list[dict] = []; touched: list[int] = []
        for i, raw in enumerate(rows, start=2):
            f, warn = normalize_row(raw, mp)
            if not (f.get("title") or f.get("primary_keyword")):
                skipped += 1; errors.append({"row": i, "error": "عنوان یا کلمه کلیدی اصلی ندارد", "warnings": warn}); continue
            f.setdefault("title", f.get("primary_keyword"))
            existing = self.repo.find_plan(site_id, f.get("url"), f.get("primary_keyword"), f.get("title"), keys)
            if dry_run:
                preview.append({"row": i, "action": "update" if existing else "create", "fields": f, "warnings": warn, "existing_id": existing.id if existing else None})
                created += 0 if existing else 1; updated += 1 if existing else 0
                continue
            try:
                if existing:
                    self.update(site_id, existing.id, f, actor=actor); updated += 1; touched.append(existing.id)
                else:
                    d = self.create(site_id, {**f, "source": f"{'sheet' if source == 'google_sheet' else 'import'}:{filename or source_id or 'upload'}"}, actor=actor, analyze=False); created += 1; touched.append(d["id"])
                if warn:
                    errors.append({"row": i, "warnings": warn})
            except Exception as e:  # noqa: BLE001
                skipped += 1; errors.append({"row": i, "error": str(e)})
        if not dry_run and touched:
            ctx = build_planner_context(self.engine, site_id)
            for pid in touched[:300]:
                self.analyze_plan(site_id, pid, ctx, actor="system", link_prep=len(touched) <= 50)
            self.graph.sync(site_id)
        iid = self.repo.record_import(site_id, source, filename, fmt, len(rows), created, updated, skipped, errors, mp, dry_run, source_id)
        return {"import_id": iid, "format": fmt, "columns": cols, "mapping": mp, "unmapped_columns": [c for c in cols if c not in mp], "rows": len(rows), "created": created, "updated": updated, "skipped": skipped,
                "errors": errors[:50], "preview": preview[:50], "dry_run": dry_run, "key_columns": keys}

    def sync_source(self, site_id: str, sid: int, dry_run: bool = False, fetch=None, actor: str = "user") -> dict[str, Any]:
        src = self.repo.get_source(site_id, sid)
        if not src:
            raise PlannerError("source not found")
        if not src["enabled"]:
            raise PlannerError("این منبع غیرفعال است")
        if src["kind"] not in ("google_sheet", "csv_url"):
            raise PlannerError(f"نوع منبع «{src['kind']}» هنوز پشتیبانی نمی‌شود (آماده برای آینده)")
        try:
            data, url = fetch_sheet(src["url"], src.get("gid"), fetch) if src["kind"] == "google_sheet" else (fetch(src["url"]) if fetch else __import__("httpx").get(src["url"], timeout=30, follow_redirects=True).content, src["url"])
        except Exception as e:  # noqa: BLE001
            self.repo.save_source(site_id, sid, status="error", last_result={"error": str(e), "at": utcnow()})
            raise PlannerError(f"دریافت منبع ناموفق بود: {e.__class__.__name__}")
        res = self.import_table(site_id, data, f"{src['name']}.csv", src.get("mapping") or None, dry_run, src.get("key_columns") or None, source="google_sheet", source_id=sid, actor=actor)
        if not dry_run:
            self.repo.save_source(site_id, sid, status="ok", last_sync_at=utcnow(), last_result={k: res[k] for k in ("rows", "created", "updated", "skipped", "import_id")})
        return {**res, "source": src["name"], "url": url}

    def export(self, site_id: str, fmt: str = "csv", columns: list[str] | None = None, **filters) -> tuple[bytes, str, str]:
        plans, _ = self.repo.list_plans(site_id, limit=100000, **filters)
        rows = self.enrich(plans)
        for r in rows:
            r["category"] = (r.get("category") or {}).get("name")
        if fmt == "xlsx":
            return to_xlsx(rows, columns), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "content-plans.xlsx"
        return to_csv(rows, columns).encode("utf-8"), "text/csv; charset=utf-8", "content-plans.csv"

    @staticmethod
    def template() -> str:
        return template_csv()

    # ------------------------------------------------------------------ generation jobs (prepared only) + publishing metadata
    def prepare_generation(self, site_id: str, pid: int, kind: str = "article", params: dict[str, Any] | None = None, actor: str = "user") -> dict[str, Any]:
        if kind not in GEN_JOB_KINDS:
            raise PlannerError(f"نوع کار نامعتبر: {kind}")
        p = self.repo.get_plan(site_id, pid)
        if not p:
            raise PlannerError("plan not found")
        cid = self.ensure_item(site_id, pid, actor)["content_id"]
        job = self.repo.create_generation_job(site_id, pid, kind, cid, {**(params or {}), "mode": (params or {}).get("mode", "manual"), "prepared_by": actor}, actor)
        self.repo.add_event(site_id, pid, "generation_prepared", actor, {"job_id": job["id"], "kind": kind, "content_id": cid})
        job["studio_url"] = f"/dashboard/ai-studio?site={site_id}&content={cid}"
        job["note"] = "کار تولید فقط آماده شد — اجرا در استودیوی AI با تأیید انسانی؛ خروجی همیشه پیش‌نویس است"
        return job

    def attach_generation_run(self, site_id: str, jid: int, run_id: str, draft_id: int | None = None) -> dict[str, Any] | None:
        return self.repo.update_generation_job(site_id, jid, generation_run_id=run_id, draft_id=draft_id, status="done" if draft_id else "running")

    def set_publishing(self, site_id: str, pid: int, meta: dict[str, Any], actor: str = "user") -> dict[str, Any] | None:
        p = self.repo.get_plan(site_id, pid)
        if not p:
            return None
        allowed = {k: meta[k] for k in ("target", "wp_status", "scheduled_at", "author", "checklist", "cta", "notes", "canonical", "og_title") if k in meta}
        allowed["publishing_enabled"] = False
        allowed["updated_at"] = utcnow()
        self.repo.update_plan(site_id, pid, actor=actor, event="publishing_meta", publishing={**(p.publishing or {}), **allowed})
        return self.detail(site_id, pid)

    # ------------------------------------------------------------------ backfill + graph
    def backfill(self, site_id: str, actor: str = "system") -> dict[str, Any]:
        n = 0
        for it in self.content.repo.all(site_id):
            if self.repo.get_plan_by_item(site_id, it.id):
                continue
            p = ContentPlan(site_id=site_id, title=it.title, content_item_id=it.id, url=it.url, intent=it.intent, primary_keyword_id=it.target_keyword_id, primary_keyword=it.target_keyword,
                            cluster_id=it.cluster_id, topic_id=it.topic, priority=it.priority, publish_date=it.publish_date, publish_time=it.publish_time,
                            status=PLAN_STATUS_OF_ITEM.get(it.status, "planned"), source="backfill", created_by=actor, page_type=(it.metadata or {}).get("page_type"))
            p = self.repo.create_plan(p, actor)
            if p.primary_keyword_id:
                self.repo.set_keywords(site_id, p.id, [{"keyword_id": p.primary_keyword_id, "role": "primary", "source": "backfill"}])
            n += 1
        if n:
            self.analyze_all(site_id, link_prep=False)
        return {"created": n}

    def _maybe_sync_graph(self, site_id: str) -> None:
        with self.engine.connect() as cx:
            n = cx.execute(text("SELECT COUNT(*) FROM content_plans WHERE site_id=:s"), {"s": site_id}).scalar() or 0
        if n <= GRAPH_SYNC_THRESHOLD:
            self.graph.sync(site_id)

    def graph_view(self, site_id: str, plan_id: int | None = None, category_id: int | None = None) -> dict[str, Any]:
        """Planner subgraph in the Phase-4 view shape, optionally focused on one plan / category (2 hops)."""
        from ...db.repositories.graph import GraphRepository
        from ...graph.views import graph_view
        repo = GraphRepository(self.engine)
        v = graph_view(repo, site_id, "planner", None, None, 600, True)
        d = v.to_dict()
        focus = f"plan:{plan_id}" if plan_id else None
        if category_id:
            cats = {c["id"]: c for c in self.repo.list_categories(site_id)}
            c = cats.get(category_id)
            if c:
                focus = (c.get("intelligence") or {}).get("graph_node_id") or next((n["id"] for n in d["nodes"] if n["type"] == "CATEGORY" and n["metadata"].get("label") == c["name"]), None)
        if focus:
            keep = {focus}
            for _ in range(2):
                for e in d["edges"]:
                    if e["source"] in keep or e["target"] in keep:
                        keep.add(e["source"]); keep.add(e["target"])
            d["nodes"] = [n for n in d["nodes"] if n["id"] in keep]
            d["edges"] = [e for e in d["edges"] if e["source"] in keep and e["target"] in keep]
            d["focus"] = focus
        return d
