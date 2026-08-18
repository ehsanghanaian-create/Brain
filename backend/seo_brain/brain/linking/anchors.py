"""Anchor suggestion: contextual, diverse, non-generic; with alternatives and a placement hint."""
from __future__ import annotations

from collections import Counter

from ...brain.keywords.normalize import normalize_keyword, tokenize
from .context import LinkContext, PageInfo


def anchor_distribution(ctx: LinkContext, target_id: str) -> Counter:
    return Counter(normalize_keyword(l["anchor"]) for l in ctx.inbound.get(target_id, []) if l["anchor"] and not l["nav"])


def suggest_anchor(ctx: LinkContext, s: PageInfo, t: PageInfo, matched: list[str]) -> tuple[str, list[str], str]:
    cands: list[tuple[float, str]] = []
    dist = anchor_distribution(ctx, t.node_id)
    total = sum(dist.values()) or 1
    seen: set[str] = set()
    pool = ([t.primary_keyword] if t.primary_keyword else []) + t.keywords[:4] + ([t.h1] if t.h1 else []) + list(t.entity_labels.values())[:3] + (t.gsc.get("top_queries", [])[:3] if t.gsc else [])
    # entity + service combos (e.g. «امداد خودرو تیگو ۷»)
    svc = [l for e, l in t.entity_labels.items() if t.entities.get(e) == "SERVICE"]
    mdl = [l for e, l in t.entity_labels.items() if t.entities.get(e) in ("MODEL", "BRAND")]
    for a in svc[:1]:
        for m in mdl[:2]:
            pool.append(f"{a} {m}")
    for ph in pool:
        n = normalize_keyword(ph or "")
        if not n or n in seen or n in ctx.generic_anchors:
            continue
        seen.add(n)
        toks = tokenize(ph)
        if not 1 <= len(toks) <= 6:
            continue
        sc = 0.5
        if ph in matched or n in {normalize_keyword(m) for m in matched}:
            sc += 0.35                                            # present in source text → contextual
        share = dist.get(n, 0) / total
        if share > 0.6:
            sc -= 0.3                                             # over-used exact anchor site-wide
        elif share == 0 and total >= 3:
            sc += 0.1                                             # diversity
        if t.primary_keyword and n == normalize_keyword(t.primary_keyword):
            sc += 0.1
        if 2 <= len(toks) <= 4:
            sc += 0.05
        specific = {normalize_keyword(l) for e, l in t.entity_labels.items() if t.entities.get(e) in ("MODEL", "BRAND", "LOCATION")}
        if specific and any(sp and (sp in n or n in sp) for sp in specific):
            sc += 0.15                                            # names the target's specific model/brand/location
        elif specific and len(toks) <= 2:
            sc -= 0.1                                             # too generic for a specific target
        for pat in (ctx.memory.get("successful_patterns") or []):
            if isinstance(pat, dict) and pat.get("source") == "internal_linking" and "anchor:entity" in str(pat.get("run_id", "")) and mdl and any(m.lower() in ph.lower() for m in mdl):
                sc += 0.05
        cands.append((sc, ph))
    if not cands:
        fallback = t.h1 or t.title
        return fallback, [], "افزودن یک جمله معرفی با این عبارت"
    cands.sort(key=lambda x: -x[0])
    best = cands[0][1]
    alts = [c[1] for c in cands[1:4]]
    hint = _placement(s, best)
    return best, alts, hint


def _placement(s: PageInfo, anchor: str) -> str:
    toks = set(tokenize(anchor))
    for i, h in enumerate(s.h2):
        if toks & set(tokenize(h)):
            return f"در بخش «{h}» (H2 شماره {i+1})"
    if toks & s.body_tokens:
        return "در پاراگرافی که این عبارت آمده است"
    return "افزودن یک جمله معرفی در بخش مرتبط (یا انتهای مقدمه)"
