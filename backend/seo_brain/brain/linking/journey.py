"""Internal Linking Journey Model.

Stages:  informational → commercial → service → conversion   (+ hub = category/listing pages)
A link that moves the reader one step *forward* along the journey (e.g. «مشکلات گیربکس ساندرو» → «امداد خودرو ساندرو») is
worth more than a same-level link, and much more than a step backwards to generic informational pages («تاریخچه رنو»).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ...brain.keywords.normalize import normalize_keyword

if TYPE_CHECKING:
    from .context import PageInfo

STAGES = ("informational", "commercial", "service", "conversion", "hub")
STAGE_FA = {"informational": "اطلاعاتی", "commercial": "تجاری", "service": "خدمت", "conversion": "تبدیل", "hub": "هاب", "unknown": "نامشخص"}
_ORDER = {"informational": 0, "commercial": 1, "service": 2, "conversion": 3}

_CONV = ("تماس", "شماره", "درخواست", "سفارش", "رزرو", "فرم", "contact", "order", "book", "call")
_SERVICE = ("امداد", "خدمات", "خدمت", "تعمیر", "یدک", "سرویس", "نصب", "service", "repair", "towing")
_COMMERCIAL = ("قیمت", "هزینه", "بهترین", "مقایسه", "خرید", "تعرفه", "price", "cost", "best", "compare", "buy")
_INFO = ("چیست", "چگونه", "چطور", "راهنما", "آموزش", "مشکلات", "علت", "دلایل", "نکات", "تاریخچه", "معرفی", "how", "why", "what", "guide", "tips", "history")


def classify_stage(p: "PageInfo") -> str:
    if p.node_type == "CATEGORY":
        return "hub"
    text = normalize_keyword(" ".join([p.title, p.h1, p.url]))
    path = p.url_n.lower()
    if p.intent == "transactional" or any(w in text for w in _CONV) and ("contact" in path or "تماس" in text or "شماره" in text):
        return "conversion" if ("contact" in path or "تماس" in path or "شماره" in text[:40]) else "service"
    if p.intent == "local" or any(w in text for w in _SERVICE):
        return "service"
    if p.intent == "commercial" or any(w in text for w in _COMMERCIAL):
        return "commercial"
    if p.intent == "informational" or "/blog/" in path or "/blog" in path or "/مقالات" in path or any(w in text for w in _INFO) or p.node_type == "POST":
        return "informational"
    if p.pagerank and p.pagerank > 0.05 and p.node_type == "PAGE":
        return "hub"
    return "unknown"


def journey_score(src_stage: str, tgt_stage: str) -> tuple[float, str]:
    """0–1 + Persian explanation. Forward: one step 1.0, two 0.95, three 0.85; hub→spoke 0.9; same level 0.55; backwards 0.3; unknown 0.4."""
    if src_stage == "hub" and tgt_stage != "hub":
        return 0.9, "از صفحه هاب به صفحه زیرمجموعه (hub → spoke)"
    if tgt_stage == "hub":
        return 0.5, "به صفحه هاب/دسته (spoke → hub)"
    if src_stage in _ORDER and tgt_stage in _ORDER:
        d = _ORDER[tgt_stage] - _ORDER[src_stage]
        if d == 1:
            return 1.0, f"یک گام جلو در سفر کاربر ({STAGE_FA[src_stage]} → {STAGE_FA[tgt_stage]})"
        if d == 2:
            return 0.95, f"رو به جلو در سفر کاربر ({STAGE_FA[src_stage]} → {STAGE_FA[tgt_stage]})"
        if d >= 3:
            return 0.85, f"مستقیم به تبدیل ({STAGE_FA[src_stage]} → {STAGE_FA[tgt_stage]})"
        if d == 0:
            return 0.55, f"هم‌سطح ({STAGE_FA[src_stage]}) — ارزش کمتر از حرکت رو به جلو"
        return 0.3, f"حرکت رو به عقب ({STAGE_FA[src_stage]} → {STAGE_FA[tgt_stage]}) — فقط برای عمق موضوعی"
    return 0.4, "مرحله سفر نامشخص"


def is_meaningful(src_stage: str, tgt_stage: str) -> bool:
    """SUPPORTS edges only for meaningful relationships: forward moves, hub→spoke; never backwards/unknown."""
    if src_stage == "hub" and tgt_stage not in ("hub", "unknown"):
        return True
    if src_stage in _ORDER and tgt_stage in _ORDER:
        return _ORDER[tgt_stage] - _ORDER[src_stage] >= 1
    return False
