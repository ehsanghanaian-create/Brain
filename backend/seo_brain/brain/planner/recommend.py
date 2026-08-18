"""Content Planning Intelligence Engine — rule-based, deterministic, explainable (rules-v1). No AI.

for_keyword(ctx, keyword)  → what to do with a keyword (create_new / optimize_existing / improve_page / add_to_cluster / merge)
for_plan(ctx, plan)        → the same + advanced SEO planning fields (content gap, cannibalisation, ranking URL, SERP intent,
                             traffic opportunity, priority score, funnel stage) and gap hints
Every output carries `reasons_fa` — the exact sentences shown in the UI."""
from __future__ import annotations

from typing import Any

from ...brain.keywords.normalize import normalize_keyword, tokenize
from ...brain.keywords.repository import Keyword
from .context import COMPARE_WORDS, LOCAL_WORDS, QUESTION_WORDS, PlannerContext
from .repository import ContentPlan

ENGINE = "rules-v1"
INTENT_WEIGHT = {"transactional": 1.0, "commercial": 0.85, "local": 0.8, "navigational": 0.3, "informational": 0.5}
CTR_BY_POS = {1: 0.28, 2: 0.15, 3: 0.11, 4: 0.08, 5: 0.07, 6: 0.05, 7: 0.04, 8: 0.035, 9: 0.03, 10: 0.025}


def _ctr(pos: float | None) -> float:
    if pos is None:
        return 0.0
    if pos <= 10:
        return CTR_BY_POS.get(max(1, int(round(pos))), 0.025)
    return 0.01 if pos <= 20 else 0.003


def page_type_for(kw: str, intent: str, entities: list[dict[str, Any]], cluster_size: int, is_cluster_head: bool) -> str:
    n = normalize_keyword(kw)
    toks = set(n.split())
    types = {e["type"] for e in entities}
    if any(w in n for w in COMPARE_WORDS) and len(toks) > 2:
        return "comparison"
    if any(w in n for w in QUESTION_WORDS):
        return "guide" if intent == "informational" and cluster_size >= 3 else "article"
    if is_cluster_head and cluster_size >= 5 and intent in ("informational", "commercial"):
        return "pillar"
    if intent in ("transactional", "commercial", "local"):
        if "LOCATION" in types or any(w in toks for w in LOCAL_WORDS):
            return "location_landing"
        if "SERVICE" in types or "MODEL" in types or "BRAND" in types:
            return "service_landing"
        return "service_landing"
    return "article"


def funnel_stage_for(intent: str | None, page_type: str | None) -> str:
    if page_type in ("service_landing", "location_landing", "product") or intent in ("transactional", "local"):
        return "decision"
    if page_type in ("comparison", "faq") or intent == "commercial":
        return "consideration"
    if page_type in ("news",):
        return "retention"
    return "awareness"


def title_for(kw: str, entities: list[dict[str, Any]], patterns: list[dict[str, Any]], intent: str) -> str:
    """Rule title: keyword + location if a successful pattern says location-in-title works (or intent is local) and none present."""
    n = normalize_keyword(kw)
    loc = next((e["label"] for e in entities if e["type"] == "LOCATION"), None)
    wants_loc = any("مکان" in str(p.get("pattern", "")) or "location" in str(p.get("pattern", "")).lower() for p in patterns) or intent in ("local", "transactional")
    t = kw.strip()
    if wants_loc and not loc and not any(w in n for w in LOCAL_WORDS):
        t = f"{t} تهران"
    if intent == "informational" and not any(w in n for w in QUESTION_WORDS):
        t = f"راهنمای {t}"
    return t


def priority_score(volume: int | None, intent: str, difficulty: float | None, gsc: dict[str, Any] | None, cluster_size: int, gap: str, cannibal: float, business_value: float | None) -> tuple[float, list[str]]:
    reasons = []
    vol = volume or 0
    s_vol = min(1.0, (vol / 1000) ** 0.5) if vol else (0.3 if gsc and gsc.get("impressions", 0) > 100 else 0.1)
    s_int = INTENT_WEIGHT.get(intent, 0.5)
    s_diff = 1.0 - (min(100.0, difficulty) / 100) if difficulty is not None else 0.6
    imp = (gsc or {}).get("impressions", 0) or 0; clk = (gsc or {}).get("clicks", 0) or 0
    s_gsc = min(1.0, imp / 2000) * (1.0 if imp and clk / max(1, imp) < 0.02 else 0.6)
    s_cl = min(1.0, cluster_size / 8)
    s_gap = {"full": 1.0, "partial": 0.6, "none": 0.2}.get(gap, 0.5)
    s_bv = (business_value or 0) / 100 if business_value is not None else None
    w = {"vol": 0.22, "int": 0.20, "diff": 0.10, "gsc": 0.15, "cl": 0.10, "gap": 0.13, "can": 0.10}
    raw = w["vol"] * s_vol + w["int"] * s_int + w["diff"] * s_diff + w["gsc"] * s_gsc + w["cl"] * s_cl + w["gap"] * s_gap + w["can"] * (1 - cannibal)
    if s_bv is not None:
        raw = 0.8 * raw + 0.2 * s_bv
    score = round(100 * raw, 1)
    if vol >= 500:
        reasons.append(f"حجم جستجوی بالا ({vol})")
    if s_int >= 0.8:
        reasons.append("اینتنت تجاری/تراکنشی قوی")
    if imp >= 300 and clk / max(1, imp) < 0.02:
        reasons.append(f"{imp} ایمپرشن با کلیک کم در Search Console")
    if cluster_size >= 5:
        reasons.append(f"خوشه کلمه کلیدی قوی ({cluster_size} کلمه)")
    if gap == "full":
        reasons.append("پوشش موضوعی وجود ندارد")
    if cannibal >= 0.5:
        reasons.append("هشدار: ریسک هم‌نوع‌خواری با محتوای موجود")
    if business_value is not None and business_value >= 70:
        reasons.append("ارزش کسب‌وکار بالا (تعیین‌شده توسط شما)")
    return score, reasons


def priority_label(score: float) -> str:
    return "high" if score >= 70 else ("medium" if score >= 40 else "low")


def _cannibalization(ctx: PlannerContext, k: Keyword | None, kw_norm: str, exclude_plan_id: int | None) -> tuple[float, list[dict[str, Any]]]:
    hits: list[dict[str, Any]] = []
    if k and k.id:
        for ref in ctx.plan_keywords.get(k.id, []):
            if ref["plan_id"] != exclude_plan_id:
                p = next((x for x in ctx.plans if x.id == ref["plan_id"]), None)
                hits.append({"kind": "plan", "id": ref["plan_id"], "title": p.title if p else None, "url": p.url if p else None, "keyword": k.keyword, "role": ref["role"]})
        for it in ctx.content_items:
            if it["target_keyword_id"] == k.id and it["status"] != "published":
                hits.append({"kind": "content", "id": it["id"], "title": it["title"], "url": it.get("url"), "keyword": k.keyword})
    for p in ctx.plans:
        if p.id != exclude_plan_id and p.primary_keyword and normalize_keyword(p.primary_keyword) == kw_norm and not any(h.get("id") == p.id and h["kind"] == "plan" for h in hits):
            hits.append({"kind": "plan", "id": p.id, "title": p.title, "url": p.url, "keyword": p.primary_keyword, "role": "primary"})
    pages = [pg for pg in ctx.ranking_pages(kw_norm) if (pg.get("position") or 99) <= 20]
    if len({pg.get("node_id") or pg["page"] for pg in pages}) >= 2:
        for pg in pages[:3]:
            hits.append({"kind": "page", "id": pg.get("node_id"), "url": pg["page"], "title": ctx.pages[pg["node_id"]].title if pg.get("node_id") in ctx.pages else pg["page"], "position": pg.get("position"), "keyword": kw_norm})
    risk = min(1.0, 0.5 * sum(1 for h in hits if h["kind"] in ("plan", "content")) + 0.25 * sum(1 for h in hits if h["kind"] == "page"))
    return round(risk, 2), hits


def _existing_pages(ctx: PlannerContext, k: Keyword | None, kw_norm: str, entities: list[dict[str, Any]], category_id: int | None) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for pg in ctx.ranking_pages(kw_norm)[:5]:
        nid = pg.get("node_id")
        out[nid or pg["page"]] = {"node_id": nid, "url": pg["page"], "title": ctx.pages[nid].title if nid in ctx.pages else pg["page"], "position": pg.get("position"), "impressions": pg.get("impressions"), "relation": "ranks_for"}
    if k and k.cluster_id:
        for m in ctx.cluster_members(k.cluster_id)[:20]:
            for pg in ctx.ranking_pages(m.normalized)[:2]:
                nid = pg.get("node_id")
                if (nid or pg["page"]) not in out and (pg.get("position") or 99) <= 20:
                    out[nid or pg["page"]] = {"node_id": nid, "url": pg["page"], "title": ctx.pages[nid].title if nid in ctx.pages else pg["page"], "position": pg.get("position"), "relation": "cluster_ranks", "keyword": m.keyword}
    ent_ids = {e["node_id"] for e in entities}
    if ent_ids:
        for p in ctx.pages.values():
            if p.entities & ent_ids and (category_id is None or category_id in p.category_ids) and p.node_id not in out:
                out[p.node_id] = {"node_id": p.node_id, "url": p.url, "title": p.title, "relation": "same_entity"}
                if len(out) >= 12:
                    break
    return list(out.values())[:12]


def for_keyword(ctx: PlannerContext, k: Keyword | None, kw_text: str | None = None, category_hint: dict[str, Any] | None = None, exclude_plan_id: int | None = None,
                business_value: float | None = None) -> dict[str, Any]:
    kw = (k.keyword if k else kw_text) or ""
    kw_norm = normalize_keyword(kw)
    intent = (k.intent if k and k.intent else ctx.guess_intent(kw))
    ents = ctx.entities_in(kw)
    g = ctx.gsc.get(kw_norm)
    cluster_size = len(ctx.clusters.get(k.cluster_id, {}).get("members", [])) if k and k.cluster_id else 0
    is_head = bool(k and k.cluster_id and ctx.clusters.get(k.cluster_id, {}).get("name") == k.keyword)
    ptype = page_type_for(kw, intent, ents, cluster_size, is_head)
    stage = funnel_stage_for(intent, ptype)
    ranking = [pg for pg in ctx.ranking_pages(kw_norm) if pg.get("position") is not None]
    top = ranking[0] if ranking else None
    pos = top["position"] if top else None
    existing = _existing_pages(ctx, k, kw_norm, ents, category_hint["id"] if category_hint else None)
    cluster_planned = [p for p in ctx.plans if k and k.cluster_id and p.cluster_id == k.cluster_id and p.id != exclude_plan_id]
    can_risk, can_hits = _cannibalization(ctx, k, kw_norm, exclude_plan_id)
    # content gap
    if top and pos is not None and pos <= 10:
        gap = "none"
    elif top or any(e.get("relation") == "cluster_ranks" for e in existing):
        gap = "partial"
    else:
        gap = "full"
    reasons: list[str] = []
    if top and pos is not None and pos <= 10:
        action = "optimize_existing"; reasons.append(f"صفحه موجود در جایگاه {pos:.0f} رتبه دارد — بهینه‌سازی به‌جای محتوای جدید")
    elif top and pos is not None and pos <= 30:
        action = "improve_page"; reasons.append(f"صفحه‌ای در جایگاه {pos:.0f} وجود دارد (۱۱–۳۰) — بهبود محتوا/لینک داخلی")
    elif any(h["kind"] == "plan" and h.get("role") == "primary" for h in can_hits):
        action = "merge"; reasons.append("برنامه محتوایی دیگری همین کلمه را هدف گرفته — ادغام به‌عنوان کلمه ثانویه")
    elif cluster_planned:
        action = "add_to_cluster"; reasons.append(f"خوشه این کلمه قبلاً برنامه دارد ({cluster_planned[0].title}) — محتوای پشتیبان")
    else:
        action = "create_new"; reasons.append("هیچ صفحه رتبه‌داری برای این کلمه وجود ندارد")
        if k and k.cluster_id and cluster_size >= 3:
            reasons.append("خوشه مرتبط وجود دارد")
    if INTENT_WEIGHT.get(intent, 0) >= 0.8:
        reasons.append("اینتنت تجاری بالا")
    if gap == "full":
        reasons.append("پوشش موضوعی وجود ندارد")
    if category_hint and category_hint.get("reasons_fa"):
        reasons.append(f"دسته پیشنهادی «{category_hint['name']}»: " + " · ".join(category_hint["reasons_fa"]))
    score, prio_reasons = priority_score(k.volume if k else None, intent, k.difficulty if k else None, g, cluster_size, gap, can_risk, business_value)
    reasons += [r for r in prio_reasons if r not in reasons]
    # traffic opportunity: monthly clicks gain if we reach position 3 (or from volume when no GSC)
    vol = (k.volume if k and k.volume else None)
    if vol:
        traffic = round(vol * (0.11 - _ctr(pos)) , 1) if pos else round(vol * 0.11, 1)
    elif g and g.get("impressions"):
        traffic = round(g["impressions"] * (0.11 - _ctr(pos)) , 1)
    else:
        traffic = None
    serp_intent = intent
    if g and g.get("top_page") and g["top_page"] in ctx.page_by_url:
        pref = ctx.pages.get(ctx.page_by_url[g["top_page"]])
        if pref and any(t in pref.tokens for t in ("قیمت", "خرید", "تماس", "شماره")):
            serp_intent = "transactional" if intent == "informational" else intent
    title = title_for(kw, ents, ctx.memory.get("successful_patterns", []), intent) if action in ("create_new", "add_to_cluster") else (existing[0]["title"] if existing else kw)
    audience = ", ".join(ctx.memory.get("audience", {}).get("segments", [])[:2]) or None
    return {
        "engine": ENGINE, "action": action, "action_fa": {"create_new": "ساخت محتوای جدید", "optimize_existing": "بهینه‌سازی صفحه موجود", "improve_page": "بهبود صفحه موجود", "add_to_cluster": "افزودن به خوشه", "merge": "ادغام"}[action],
        "keyword": kw, "keyword_id": k.id if k else None, "title": title, "page_type": ptype, "intent": intent, "serp_intent": serp_intent, "funnel_stage": stage,
        "category": category_hint, "priority": priority_label(score), "priority_score": score, "content_gap": gap, "cannibalization_risk": can_risk, "cannibalization": can_hits[:6],
        "ranking_url": top["page"] if top else None, "ranking_position": pos, "traffic_opportunity": max(0.0, traffic) if traffic is not None else None,
        "existing_pages": existing, "cluster": {"id": k.cluster_id, "size": cluster_size, "topic": ctx.clusters.get(k.cluster_id, {}).get("topic")} if k and k.cluster_id else None,
        "entities": ents[:6], "target_audience": audience, "reasons_fa": reasons[:8], "confidence": round(min(1.0, 0.5 + 0.1 * len(reasons) + (0.15 if g else 0)), 2),
    }


def for_plan(ctx: PlannerContext, p: ContentPlan, category_hint: dict[str, Any] | None = None) -> dict[str, Any]:
    k = ctx.keyword_of(p.primary_keyword_id) if p.primary_keyword_id else ctx.keyword_of(p.primary_keyword)
    rec = for_keyword(ctx, k, p.primary_keyword or p.title, category_hint, exclude_plan_id=p.id, business_value=p.business_value)
    gaps: list[str] = []
    if not p.primary_keyword and not p.primary_keyword_id:
        gaps.append("کلمه کلیدی اصلی تعیین نشده")
    if not p.seo_title:
        gaps.append("عنوان سئو خالی است")
    if not p.meta_description:
        gaps.append("توضیحات متا خالی است")
    if not p.category_id:
        gaps.append("دسته انتخاب نشده" + (f" — پیشنهاد: {category_hint['name']}" if category_hint else ""))
    if not p.heading_structure:
        gaps.append("ساختار سرفصل‌ها تعریف نشده")
    if not p.link_targets:
        gaps.append("هدف لینک داخلی ندارد — «آماده‌سازی لینک» را اجرا کنید")
    if k and not k.cluster_id:
        gaps.append("کلمه کلیدی خوشه‌بندی نشده")
    if p.publish_date:
        same_week = [x for x in ctx.plans if x.id != p.id and x.category_id and x.category_id == p.category_id and x.publish_date and abs((_d(x.publish_date) - _d(p.publish_date)).days) <= 3]
        if len(same_week) >= 3:
            gaps.append(f"{len(same_week)} برنامه دیگر از همین دسته در همان هفته — زمان‌بندی را پخش کنید")
    rec["gaps_fa"] = gaps
    if p.intent and p.intent != rec["intent"]:
        rec["reasons_fa"].append(f"اینتنت انتخابی شما ({p.intent}) با تشخیص قوانین ({rec['intent']}) متفاوت است")
    return rec


def _d(s: str):
    from datetime import date
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return date(1970, 1, 1)
