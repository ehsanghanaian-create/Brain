"""Pre-writing internal-link preparation: reuse Phase-8 pair scoring against a synthetic PageInfo built from the plan.
Outputs inbound candidates (existing page → new plan) and outbound targets (plan → existing page), stores them on the plan
(`link_targets`) and as `link_suggestions` rows with scope='plan' (kept apart from the Phase-8 UI counts)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Engine, text

from ...brain.keywords.normalize import tokenize
from ...brain.linking.context import PageInfo, build_context
from ...brain.linking.journey import is_meaningful, journey_score
from ...brain.linking.scoring import score_pair
from ...db.repositories.base import dumps, utcnow
from ...db.repositories.memory import SiteMemoryRepository
from .context import PlannerContext
from .repository import ContentPlan

STAGE_OF_FUNNEL = {"awareness": "informational", "consideration": "commercial", "decision": "conversion", "retention": "informational"}
STAGE_OF_PAGE_TYPE = {"service_landing": "service", "location_landing": "conversion", "product": "conversion", "pillar": "hub", "category_page": "hub", "comparison": "commercial", "faq": "informational",
                      "article": "informational", "guide": "informational", "news": "informational"}


def _plan_page(ctx: PlannerContext, p: ContentPlan, lctx) -> PageInfo:
    toks = set(tokenize(" ".join([p.title or "", p.primary_keyword or "", p.seo_title or "", " ".join(p.secondary_keywords or []), " ".join(h.get("text", "") for h in p.heading_structure or [])])))
    ents = {e["node_id"]: e["type"] for e in ctx.entities_in(f"{p.title} {p.primary_keyword or ''}")}
    k = ctx.keyword_of(p.primary_keyword_id) if p.primary_keyword_id else ctx.keyword_of(p.primary_keyword)
    clusters = {k.cluster_id} if k and k.cluster_id else ({p.cluster_id} if p.cluster_id else set())
    topics = {lctx.cluster_topic.get(c, c) for c in clusters}
    stage = STAGE_OF_PAGE_TYPE.get(p.page_type or "", STAGE_OF_FUNNEL.get(p.funnel_stage or "", "informational"))
    return PageInfo(node_id=f"plan:{p.id}", node_type="CONTENT", url=p.url or f"plan://{p.id}", url_n=p.url or f"plan://{p.id}", title=p.title, h1=p.seo_title or p.title,
                    h2=[h.get("text", "") for h in p.heading_structure or []], text_tokens=toks, word_count=0, indexable=True, status_code=200, pagerank=0.0,
                    entities=ents, entity_labels={nid: ctx.entities[nid]["label"] for nid in ents if nid in ctx.entities}, clusters=clusters, topics=topics,
                    keywords=[x for x in [p.primary_keyword, *(p.secondary_keywords or [])] if x], primary_keyword=p.primary_keyword, intent=p.intent, stage=stage,
                    category_ids=set(), is_content_item=True, content_id=p.content_item_id, published=False)


class LinkPrep:
    def __init__(self, engine: Engine):
        self.engine = engine

    def prepare(self, ctx: PlannerContext, p: ContentPlan, max_out: int = 5, max_in: int = 5, min_score: float = 0.45) -> dict[str, Any]:
        mem = SiteMemoryRepository(self.engine).get(ctx.site_id).to_dict()
        lctx = build_context(self.engine, ctx.site_id, None, mem)
        me = _plan_page(ctx, p, lctx)
        prs = sorted(x.pagerank for x in lctx.pages.values() if not x.is_content_item)
        outbound, inbound = [], []
        for nid, page in lctx.pages.items():
            if page.is_content_item and not page.published:
                continue
            r_out = score_pair(lctx, me, page, prs)          # plan → existing page (source=me must be "indexable": we set True)
            if r_out and r_out["score"] >= min_score:
                js, jw = journey_score(me.stage, page.stage)
                outbound.append({"direction": "to", "node_id": nid, "url": page.url, "title": page.title, "anchor": (r_out.get("matched_phrases") or [page.primary_keyword or page.title])[0],
                                 "score": r_out["score"], "reason_fa": _reason(r_out, me.stage, page.stage), "journey": jw})
            r_in = score_pair(lctx, page, me, prs)           # existing page → plan
            if r_in and r_in["score"] >= min_score:
                inbound.append({"direction": "from", "node_id": nid, "url": page.url, "title": page.title, "anchor": p.primary_keyword or p.title,
                                "score": r_in["score"], "reason_fa": _reason(r_in, page.stage, me.stage), "journey": journey_score(page.stage, me.stage)[1]})
        outbound.sort(key=lambda x: -x["score"]); inbound.sort(key=lambda x: -x["score"])
        # caps: max 3 from the same source (inbound) — different sources are distinct pages anyway; keep totals
        targets = inbound[:max_in] + outbound[:max_out]
        self._store(ctx.site_id, p, targets)
        return {"plan_id": p.id, "inbound": inbound[:max_in], "outbound": outbound[:max_out], "count": len(targets)}

    def _store(self, site_id: str, p: ContentPlan, targets: list[dict[str, Any]]) -> None:
        run_id = f"planlinks-{uuid.uuid4().hex[:8]}"
        now = utcnow()
        with self.engine.begin() as cx:
            cx.execute(text("DELETE FROM link_suggestions WHERE site_id=:s AND scope='plan' AND plan_id=:p AND status='proposed'"), {"s": site_id, "p": p.id})
            for t in targets:
                src, tgt = (t["node_id"], f"plan:{p.id}") if t["direction"] == "from" else (f"plan:{p.id}", t["node_id"])
                src_url, tgt_url = (t["url"], p.url) if t["direction"] == "from" else (p.url, t["url"])
                src_title, tgt_title = (t["title"], p.title) if t["direction"] == "from" else (p.title, t["title"])
                cx.execute(text("INSERT INTO link_suggestions(site_id, scope, kind, source_node_id, source_url, source_title, target_node_id, target_url, target_title, anchor, anchor_alternatives, placement_hint, "
                                "score, confidence, score_breakdown, reason_fa, evidence, status, run_id, plan_id, created_at, updated_at) VALUES(:s,'plan','plan_link',:sn,:su,:st,:tn,:tu,:tt,:a,'[]',:ph,:sc,:cf,'{}',:r,:ev,'proposed',:run,:p,:t,:t)"),
                           {"s": site_id, "sn": src, "su": src_url, "st": src_title, "tn": tgt, "tu": tgt_url, "tt": tgt_title, "a": t["anchor"], "ph": "در بدنه متن، پاراگراف مرتبط",
                            "sc": t["score"], "cf": "high" if t["score"] >= 0.8 else ("recommended" if t["score"] >= 0.6 else "low"), "r": t["reason_fa"], "ev": dumps({"journey": t.get("journey")}), "run": run_id, "p": p.id, "t": now})


def _reason(r: dict[str, Any], s_stage: str, t_stage: str) -> str:
    parts = []
    c = r.get("components", {})
    if c.get("topic", 0) >= 0.5:
        parts.append("هم‌خوشه / موضوع مشترک")
    if c.get("entities", 0) >= 0.5:
        parts.append("موجودیت مشترک")
    ok, why = is_meaningful(s_stage, t_stage), journey_score(s_stage, t_stage)[1]
    parts.append(why if ok else "مرحله متفاوت قیف")
    return " · ".join(parts) or "ارتباط معنایی"
