"""Per-page audit (inbound/outbound/anchor distribution/flags) + Internal Link Health Score 0–100."""
from __future__ import annotations

from collections import Counter
from typing import Any

from ...brain.keywords.normalize import normalize_keyword
from .context import LinkContext, PageInfo

FLAG_FA = {"orphan": "یتیم (بدون لینک ورودی)", "nav_only_inbound": "فقط لینک ناوبری", "low_inbound": "لینک ورودی کم", "single_source": "فقط یک منبع",
           "generic_anchors": "انکرهای عمومی", "over_optimized_anchor": "انکر بیش‌ازحد تکراری", "no_outbound_body": "بدون لینک خروجی بدنه",
           "links_to_noindex": "لینک به صفحه غیرقابل ایندکس", "too_many_outbound": "لینک خروجی زیاد", "not_indexable": "غیرقابل ایندکس"}


def health_score(inbound_body: int, unique_sources: int, outbound_body: int, distinct_anchors: int, exact_ratio: float, generic_ratio: float,
                 is_orphan: bool, pr_percentile: float, low_threshold: int = 2) -> tuple[float, dict[str, float]]:
    """Weights: inbound contextual 35 · outbound balance 15 · anchor diversity 20 · orphan risk 15 · authority distribution 15."""
    inbound = min(1.0, inbound_body / max(1, low_threshold * 3)) * 0.7 + min(1.0, unique_sources / 3) * 0.3
    if outbound_body == 0:
        out_bal = 0.2
    elif outbound_body <= 30:
        out_bal = 1.0
    else:
        out_bal = max(0.2, 1.0 - (outbound_body - 30) / 40)
    if inbound_body == 0:
        diversity = 0.0
    else:
        diversity = min(1.0, distinct_anchors / max(1, min(inbound_body, 4))) * 0.6 + (1 - min(1.0, exact_ratio if exact_ratio > 0.6 else 0)) * 0.2 + (1 - generic_ratio) * 0.2
    orphan_risk = 0.0 if is_orphan else (0.5 if inbound_body < low_threshold else 1.0)
    authority = pr_percentile
    parts = {"inbound_contextual": round(inbound * 35, 1), "outbound_balance": round(out_bal * 15, 1), "anchor_diversity": round(diversity * 20, 1),
             "orphan_risk": round(orphan_risk * 15, 1), "authority": round(authority * 15, 1)}
    return round(sum(parts.values()), 1), parts


def audit_pages(ctx: LinkContext) -> dict[str, dict[str, Any]]:
    low = int(ctx.settings.get("low_inbound_threshold", 2))
    prs = sorted(p.pagerank for p in ctx.pages.values() if not p.is_content_item)
    out: dict[str, dict[str, Any]] = {}
    for nid, p in ctx.pages.items():
        if p.is_content_item and not p.published:
            continue
        inb = ctx.inbound.get(nid, []); outb = ctx.outbound.get(nid, [])
        body_in = [l for l in inb if not l["nav"]]
        nav_only = bool(inb) and not body_in
        srcs = {l["source_id"] for l in body_in}
        anchors = Counter(normalize_keyword(l["anchor"]) for l in body_in if l["anchor"])
        tot = sum(anchors.values())
        exact = 0.0
        if p.primary_keyword and tot:
            exact = anchors.get(normalize_keyword(p.primary_keyword), 0) / tot
        generic = (sum(c for a, c in anchors.items() if a in ctx.generic_anchors) / tot) if tot else 0.0
        out_body = [l for l in outb if not l["nav"]]
        flags = []
        if not inb: flags.append("orphan")
        elif nav_only: flags.append("nav_only_inbound")
        if 0 < len(body_in) < low: flags.append("low_inbound")
        if len(srcs) == 1 and len(body_in) >= 1: flags.append("single_source")
        if generic > 0.3 and tot >= 2: flags.append("generic_anchors")
        if exact > 0.6 and tot >= 3: flags.append("over_optimized_anchor")
        if not out_body and p.node_type != "CATEGORY": flags.append("no_outbound_body")
        if len(out_body) > 40: flags.append("too_many_outbound")
        if any(not ctx.pages[l["target_id"]].indexable for l in out_body if l["target_id"] in ctx.pages): flags.append("links_to_noindex")
        if not p.indexable: flags.append("not_indexable")
        pr_pct = (sum(1 for x in prs if x <= p.pagerank) / len(prs)) if prs else 0.0
        hs, hb = health_score(len(body_in), len(srcs), len(out_body), len(anchors), exact, generic, not inb, pr_pct, low)
        out[nid] = {"node_id": nid, "url": p.url, "title": p.title, "stage": p.stage, "inbound_total": len(inb), "inbound_body": len(body_in), "inbound_nav_only": len(inb) - len(body_in),
                    "unique_sources": len(srcs), "outbound_body": len(out_body), "outbound_total": len(outb),
                    "anchor_distribution": [{"anchor": a or "(خالی)", "count": c} for a, c in anchors.most_common(8)], "exact_match_ratio": round(exact, 2), "generic_ratio": round(generic, 2),
                    "flags": flags, "flags_fa": [FLAG_FA[f] for f in flags], "pagerank": round(p.pagerank, 5), "health_score": hs, "health_breakdown": hb, "value": round(p.value, 2)}
    return out
