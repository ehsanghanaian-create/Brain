"""Keyword Intelligence connection: keyword → recommendation card + mapping proposals (new plan / attach to plan as secondary),
apply mapping (content_plan_keywords + keywords.status='planned' + target_url)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import Engine

from ...brain.keywords.repository import KeywordsRepository
from .categories import CategoryIntelligence
from .context import PlannerContext, build_planner_context
from .recommend import for_keyword
from .repository import PlannerRepository


class KeywordMapper:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.repo = PlannerRepository(engine)
        self.kw = KeywordsRepository(engine)
        self.cats = CategoryIntelligence(engine)

    def overview(self, site_id: str, status: str = "unmapped", q: str | None = None, limit: int = 300, ctx: PlannerContext | None = None) -> dict[str, Any]:
        ctx = ctx or build_planner_context(self.engine, site_id)
        rows = []
        for k in ctx.keywords.values():
            refs = ctx.plan_keywords.get(k.id, [])
            mapped = bool(refs) or any(it["target_keyword_id"] == k.id for it in ctx.content_items)
            if status == "unmapped" and mapped:
                continue
            if status == "mapped" and not mapped:
                continue
            if q and q not in k.keyword:
                continue
            g = ctx.gsc.get(k.normalized)
            rows.append({**k.to_dict(), "mapped": mapped, "plans": [{**r, "title": next((p.title for p in ctx.plans if p.id == r["plan_id"]), None)} for r in refs],
                         "gsc": {x: g[x] for x in ("clicks", "impressions", "position", "top_page")} if g else None,
                         "cluster_size": len(ctx.clusters.get(k.cluster_id, {}).get("members", [])) if k.cluster_id else 0})
        rows.sort(key=lambda r: (-(r["volume"] or 0), -(r["gsc"]["impressions"] if r["gsc"] else 0)))
        return {"status": status, "total": len(rows), "items": rows[:limit], "counts": {"keywords": len(ctx.keywords), "mapped": sum(1 for k in ctx.keywords.values() if ctx.plan_keywords.get(k.id)), "plans": len(ctx.plans)}}

    def suggest(self, site_id: str, keyword_ids: list[int] | None = None, limit: int = 100, ctx: PlannerContext | None = None, persist: bool = True) -> dict[str, Any]:
        """Recommendation card per keyword (+ category suggestion + mapping proposal). Persisted in content_plan_recommendations (kind = action)."""
        ctx = ctx or build_planner_context(self.engine, site_id)
        ids = keyword_ids or [k.id for k in sorted(ctx.keywords.values(), key=lambda k: -(k.volume or 0)) if not ctx.plan_keywords.get(k.id)][:limit]
        out = []
        for kid in ids:
            k = ctx.keywords.get(kid)
            if not k:
                continue
            cat = self.cats.suggest(site_id, keyword_id=kid, ctx=ctx)
            rec = for_keyword(ctx, k, None, cat["suggested"])
            proposal = self._proposal(ctx, k, rec)
            rec["mapping"] = proposal
            saved = self.repo.save_recommendation(site_id, rec["action"], rec, keyword_id=kid, category_id=(cat["suggested"] or {}).get("id")) if persist else None
            out.append({"keyword": k.to_dict(), "recommendation": rec, "recommendation_id": saved["id"] if saved else None, "recommendation_status": saved["status"] if saved else None, "category": cat})
        return {"items": out, "count": len(out)}

    @staticmethod
    def _proposal(ctx: PlannerContext, k, rec: dict[str, Any]) -> dict[str, Any]:
        if rec["action"] in ("merge", "add_to_cluster"):
            target = next((h for h in rec.get("cannibalization", []) if h["kind"] == "plan"), None)
            if not target:
                cand = [p for p in ctx.plans if k.cluster_id and p.cluster_id == k.cluster_id]
                target = {"id": cand[0].id, "title": cand[0].title} if cand else None
            if target:
                return {"type": "attach", "plan_id": target["id"], "plan_title": target.get("title"), "role": "secondary" if rec["action"] == "merge" else "supporting"}
        if rec["action"] in ("optimize_existing", "improve_page"):
            return {"type": "new", "role": "primary", "note": "برنامه از نوع بهینه‌سازی صفحه موجود", "url": rec.get("ranking_url")}
        return {"type": "new", "role": "primary"}

    def apply(self, site_id: str, items: list[dict[str, Any]], service, actor: str = "user") -> dict[str, Any]:
        """items: [{keyword_id, plan_id | 'new', role?, recommendation_id?}] — service = PlannerService (creates plans)."""
        ctx = build_planner_context(self.engine, site_id)
        created, attached, errors = [], [], []
        for it in items:
            kid = int(it["keyword_id"]); k = ctx.keywords.get(kid)
            if not k:
                errors.append({"keyword_id": kid, "error": "keyword not found"}); continue
            role = it.get("role") or "secondary"
            if it.get("plan_id") in (None, "new", "", 0):
                cat = self.cats.suggest(site_id, keyword_id=kid, ctx=ctx)
                rec = for_keyword(ctx, k, None, cat["suggested"])
                plan = service.create(site_id, {"title": rec["title"], "primary_keyword_id": kid, "primary_keyword": k.keyword, "intent": rec["intent"], "page_type": rec["page_type"],
                                                "category_id": (cat["suggested"] or {}).get("id"), "priority": rec["priority"], "source": f"keyword:{kid}", "url": rec.get("ranking_url") if rec["action"] in ("optimize_existing", "improve_page") else None},
                                      actor=actor, analyze=True)
                created.append({"keyword_id": kid, "plan_id": plan["id"], "title": plan["title"]})
                pid = plan["id"]
            else:
                pid = int(it["plan_id"])
                self.repo.set_keywords(site_id, pid, [{"keyword_id": kid, "role": role, "source": "mapping"}])
                self.repo.add_event(site_id, pid, "keywords_mapped", actor, {"keyword_id": kid, "role": role})
                if role == "primary":
                    self.repo.update_plan(site_id, pid, actor=actor, primary_keyword_id=kid, primary_keyword=k.keyword)
                attached.append({"keyword_id": kid, "plan_id": pid, "role": role})
            self.kw.update(site_id, kid, status="planned")
            if it.get("recommendation_id"):
                self.repo.set_recommendation_status(site_id, int(it["recommendation_id"]), "applied", actor, plan_id=pid)
        return {"created": created, "attached": attached, "errors": errors}
