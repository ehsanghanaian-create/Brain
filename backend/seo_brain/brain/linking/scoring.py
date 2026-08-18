"""Semantic relationship scoring for a (source → target) pair. Explainable: every component returns value + evidence."""
from __future__ import annotations

import math
from typing import Any

from ...brain.keywords.normalize import tokenize
from .context import LinkContext, PageInfo
from .journey import journey_score

_ENT_W = {"MODEL": 1.0, "SERVICE": 1.0, "BRAND": 0.6, "LOCATION": 0.5}


def confidence_of(score: float) -> str:
    return "high" if score >= 0.80 else ("recommended" if score >= 0.60 else "low")


def _cosine(a: set[str], b: set[str], idf: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    inter = sum(idf.get(t, 1.0) ** 2 for t in a & b)
    na = math.sqrt(sum(idf.get(t, 1.0) ** 2 for t in a)); nb = math.sqrt(sum(idf.get(t, 1.0) ** 2 for t in b))
    return inter / (na * nb) if na and nb else 0.0


def topic_component(ctx: LinkContext, s: PageInfo, t: PageInfo) -> tuple[float, str, dict]:
    ev: dict[str, Any] = {}
    shared_cl = s.clusters & t.clusters
    if shared_cl:
        names = [ctx.cluster_topic.get(c, c) for c in list(shared_cl)[:2]]
        ev["shared_clusters"] = names
        return 1.0, f"هم‌خوشه در کلمات کلیدی ({'، '.join(names)})", ev
    shared_topics = s.topics & t.topics
    if shared_topics:
        ev["shared_topics"] = list(shared_topics)[:2]
        return 0.9, f"موضوع مشترک ({'، '.join(list(shared_topics)[:2])})", ev
    if s.category_ids & t.category_ids or t.node_id in s.category_ids or s.node_id in t.category_ids:
        ev["same_category"] = True
        return 0.6, "در یک دسته‌بندی", ev
    cos = _cosine(s.text_tokens, t.text_tokens, ctx.idf)
    if s.community is not None and s.community == t.community:
        ev["same_community"] = s.community
        return max(0.4, min(0.5, cos)), f"در یک جامعه گراف (community {s.community})" + (f"؛ شباهت متنی {cos:.0%}" if cos else ""), ev
    if cos >= 0.15:
        shared = sorted(s.text_tokens & t.text_tokens, key=lambda x: -ctx.idf.get(x, 0))[:3]
        ev["shared_tokens"] = shared
        return min(0.5, cos), f"شباهت متنی عنوان/سرفصل‌ها ({'، '.join(shared)})", ev
    return 0.0, "", ev


def entity_component(s: PageInfo, t: PageInfo) -> tuple[float, str, dict]:
    if not s.entities or not t.entities:
        return 0.0, "", {}
    shared = set(s.entities) & set(t.entities)
    if not shared:
        return 0.0, "", {}
    w_shared = sum(_ENT_W.get(s.entities[e], 0.5) for e in shared)
    w_union = sum(_ENT_W.get(s.entities.get(e) or t.entities.get(e), 0.5) for e in set(s.entities) | set(t.entities))
    jac = w_shared / w_union if w_union else 0.0
    specific = any(s.entities[e] in ("MODEL", "SERVICE") for e in shared)
    val = min(1.0, jac + (0.3 if specific else 0.0))
    labels = [t.entity_labels.get(e) or s.entity_labels.get(e) or e for e in list(shared)[:3]]
    return val, f"موجودیت‌های مشترک: {'، '.join(labels)}", {"shared_entities": labels}


def intent_component(s: PageInfo, t: PageInfo) -> tuple[float, str, dict]:
    js, why = journey_score(s.stage, t.stage)
    return js, why, {"source_stage": s.stage, "target_stage": t.stage}


def authority_component(ctx: LinkContext, s: PageInfo, prs: list[float]) -> tuple[float, str, dict]:
    if not s.indexable or (s.status_code or 200) >= 300:
        return 0.0, "منبع غیرقابل ایندکس/ریدایرکت", {"indexable": False}
    rank = sum(1 for p in prs if p <= s.pagerank) / max(1, len(prs))      # percentile
    out_body = sum(1 for l in ctx.outbound.get(s.node_id, []) if not l["nav"])
    pen = 0.3 if out_body > 40 else (0.15 if out_body > 25 else 0.0)
    val = max(0.0, rank - pen)
    return val, f"اعتبار منبع: PageRank صدک {rank:.0%}" + (f"؛ {out_body} لینک خروجی بدنه" if pen else ""), {"pagerank": round(s.pagerank, 4), "percentile": round(rank, 2), "outbound_body": out_body}


def anchor_component(s: PageInfo, t: PageInfo) -> tuple[float, str, dict, list[str]]:
    """Is there a contextual place in the source for the target's keyword/entity? Returns value, why, evidence, matched phrases."""
    phrases = [t.primary_keyword] + t.keywords[:3] + list(t.entity_labels.values())[:3]
    phrases = [p for p in phrases if p]
    src_tokens = s.text_tokens | s.body_tokens
    best, matched = 0.0, []
    for ph in phrases:
        toks = tokenize(ph)
        if not toks:
            continue
        r = sum(1 for x in toks if x in src_tokens) / len(toks)
        if r > best:
            best = r
        if r >= 0.7:
            matched.append(ph)
    if best >= 0.9:
        return 1.0, f"عبارت «{matched[0]}» در متن منبع وجود دارد", {"matched": matched[:3]}, matched
    if best >= 0.5:
        return 0.5, "بخشی از عبارت هدف در متن منبع هست", {"matched": matched[:3], "ratio": round(best, 2)}, matched
    return 0.1, "جایگاه متنی آماده نیست — یک جمله اضافه شود", {"ratio": round(best, 2)}, matched


def score_pair(ctx: LinkContext, s: PageInfo, t: PageInfo, prs: list[float], pattern_boost: float = 0.0) -> dict[str, Any] | None:
    """Full pair evaluation. Returns None when the pair must be dropped (existing link, self, non-indexable source)."""
    if s.node_id == t.node_id or (s.node_id, t.node_id) in ctx.links:
        return None
    if not s.indexable or (s.status_code or 200) >= 300:
        return None
    if s.is_content_item and not s.published and t.is_content_item and not t.published:
        return None
    w = ctx.settings["weights"]
    top, top_why, top_ev = topic_component(ctx, s, t)
    ent, ent_why, ent_ev = entity_component(s, t)
    itn, itn_why, itn_ev = intent_component(s, t)
    aut, aut_why, aut_ev = authority_component(ctx, s, prs)
    anc, anc_why, anc_ev, matched = anchor_component(s, t)
    comps = {"topic": top, "entities": ent, "intent": itn, "authority": aut, "anchor": anc}
    penalties = {}
    if (t.node_id, s.node_id) in ctx.links:
        penalties["reciprocal_only"] = -0.1
    if top == 0 and ent == 0:
        return None            # no semantic relationship at all — never suggest on authority/anchor alone
    raw = sum(w[k] * comps[k] for k in comps) + sum(penalties.values()) + min(0.1, max(0.0, pattern_boost))
    score = round(max(0.0, min(1.0, raw)), 3)
    ranked = sorted([(k, comps[k] * w[k]) for k in comps], key=lambda x: -x[1])
    whys = {"topic": top_why, "entities": ent_why, "intent": itn_why, "authority": aut_why, "anchor": anc_why}
    reason_parts = [whys[k] for k, v in ranked[:3] if v > 0 and whys[k]]
    return {"score": score, "confidence": confidence_of(score), "components": comps, "penalties": penalties, "pattern_boost": round(min(0.1, max(0.0, pattern_boost)), 3),
            "reason_parts": reason_parts, "evidence": {**top_ev, **ent_ev, **itn_ev, **aut_ev, **anc_ev}, "matched_phrases": matched,
            "journey": {"source_stage": s.stage, "target_stage": t.stage, "score": itn, "why": itn_why}}
