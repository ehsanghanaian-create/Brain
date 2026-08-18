"""Content Quality Scoring Engine (score-v1) — deterministic, explainable.

score(draft, context) → ContentScore{total 0–100, dims{7}, findings[{rule, dim, passed, weight, evidence, fix_fa}]}
Context = brief (outline/entities/questions/internal_links), keyword (+cluster siblings), Site Brain memory
(cta_rules, forbidden_claims, content_rules), graph hub pages. No network, no AI.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

from ...brain.keywords.normalize import normalize_keyword, tokenize
from .drafts import DEFAULT_SCORING, Draft

DIMS = ("intent", "keywords", "entities", "headings", "links", "cta", "completeness")
DIM_FA = {"intent": "تطابق با اینتنت", "keywords": "پوشش کلمات کلیدی", "entities": "پوشش موجودیت‌ها", "headings": "ساختار سرفصل‌ها", "links": "کیفیت لینک داخلی", "cta": "کیفیت CTA", "completeness": "کامل بودن محتوا"}
_CTA_WORDS = ("تماس", "شماره", "سفارش", "درخواست", "کلیک", "همین حالا", "رایگان", "مشاوره", "call", "contact", "order", "book", "whatsapp", "واتساپ", "تلگرام", "۰۹", "09", "021", "۰۲۱")
_PHONE = re.compile(r"(?:\+98|0|۰)[\d۰-۹][\d۰-۹\s\-]{8,12}")
_INFO_WORDS = ("چیست", "چگونه", "چطور", "راهنما", "مراحل", "نکات", "آموزش", "دلایل", "چرا", "what", "how", "guide", "steps", "tips")


@dataclass
class Finding:
    rule: str
    dim: str
    passed: bool
    weight: float                 # share inside its dimension (sums to 1 per dim)
    evidence: str
    fix_fa: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContentScore:
    total: float
    dims: dict[str, float]        # 0–100 each
    findings: list[Finding]
    weights: dict[str, float]
    engine_version: str = "score-v1"
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"total": self.total, "dims": self.dims, "dims_fa": DIM_FA, "findings": [f.to_dict() for f in self.findings], "weights": self.weights,
                "engine_version": self.engine_version, "label": self.label,
                "failed": [f.to_dict() for f in self.findings if not f.passed]}


def _contains(hay: str, needle: str) -> bool:
    return bool(needle) and normalize_keyword(needle) in normalize_keyword(hay)


def _tokens_covered(text_norm: str, phrase: str, min_ratio: float = 0.7) -> bool:
    toks = tokenize(phrase)
    if not toks:
        return False
    hit = sum(1 for t in toks if t in text_norm)
    return hit / len(toks) >= min_ratio


def score_draft(draft: Draft, brief: dict[str, Any] | None, keyword: dict[str, Any] | None, siblings: list[str], memory: dict[str, Any],
                site_host: str | None, hub_urls: set[str], settings: dict[str, Any] | None = None) -> ContentScore:
    cfg = settings or DEFAULT_SCORING
    W = cfg["weights"]
    st = draft.structure or {}
    text = draft.body_text or ""
    tnorm = normalize_keyword(text)
    title = draft.title or (st.get("h1") or [""])[0] or ""
    kw = (keyword or {}).get("keyword") or (brief or {}).get("sources", {}).get("keyword", {}).get("keyword") or ""
    kw_norm = normalize_keyword(kw)
    intent = (keyword or {}).get("intent") or (brief or {}).get("intent") or "commercial"
    h1s, h2s, h3s = st.get("h1", []), st.get("h2", []), st.get("h3", [])
    paras = st.get("paragraphs", [])
    first = normalize_keyword(" ".join(paras[:2]))[:600]
    F: list[Finding] = []

    # ---- intent
    if intent in ("transactional", "local", "commercial"):
        F.append(Finding("cta_present", "intent", any(w in text for w in _CTA_WORDS) or bool(_PHONE.search(text)), 0.35, "وجود دعوت به اقدام/شماره تماس در متن", "شماره تماس یا CTA واضح اضافه کنید"))
        F.append(Finding("service_words_early", "intent", any(t in first for t in tokenize(kw)), 0.35, "کلمه کلیدی خدماتی در ۲ پاراگراف اول", "کلمه کلیدی را در پاراگراف اول بیاورید"))
        F.append(Finding("location_present", "intent", intent != "local" or any(e["type"] == "LOCATION" and _contains(text, e["label"]) for e in (brief or {}).get("entities", [])) or bool(re.search(r"تهران|کرج|اصفهان|شیراز|مشهد|تبریز", text)), 0.30, "اشاره به مکان برای اینتنت محلی", "شهر/منطقه خدمات را در H1 و متن ذکر کنید"))
    else:
        F.append(Finding("question_headings", "intent", len(st.get("questions", [])) >= 2 or any(w in " ".join(h2s) for w in _INFO_WORDS), 0.4, "سرفصل‌های پرسشی/آموزشی برای اینتنت اطلاعاتی", "H2ها را به شکل سؤال یا مرحله بنویسید"))
        F.append(Finding("definition_early", "intent", _contains(" ".join(paras[:2]), "است") or _contains(" ".join(paras[:2]), "یعنی"), 0.3, "تعریف/پاسخ مستقیم در ابتدای متن", "پاراگراف اول باید پاسخ مستقیم بدهد"))
        F.append(Finding("length_for_info", "intent", draft.word_count >= 700, 0.3, f"{draft.word_count} کلمه برای محتوای اطلاعاتی", "محتوا را گسترش دهید (≥۷۰۰ کلمه)"))

    # ---- keywords
    F.append(Finding("kw_in_title", "keywords", _contains(title, kw), 0.3, f"«{kw}» در عنوان/H1", "کلمه کلیدی هدف را در عنوان بیاورید"))
    F.append(Finding("kw_in_first_paragraph", "keywords", _tokens_covered(first, kw), 0.2, "کلمه کلیدی در پاراگراف اول", "کلمه کلیدی را در ۱۰۰ کلمه اول بیاورید"))
    F.append(Finding("kw_in_meta", "keywords", _contains(draft.meta_description or "", kw), 0.15, "کلمه کلیدی در توضیحات متا", "توضیحات متا شامل کلمه کلیدی بنویسید"))
    covered = [s for s in siblings if _tokens_covered(tnorm, s)]
    F.append(Finding("siblings_covered", "keywords", (len(covered) / len(siblings) >= 0.5) if siblings else True, 0.25, f"{len(covered)}/{len(siblings)} کلمه هم‌خوشه پوشش داده شده", "کلمات هم‌خوشه را در H2/متن پوشش دهید"))
    kw_count = tnorm.count(kw_norm) if kw_norm else 0
    density = (kw_count * max(1, len(kw_norm.split())) / max(1, draft.word_count)) if draft.word_count else 0
    F.append(Finding("density_band", "keywords", (0.003 <= density <= 0.03) if kw_norm else True, 0.10, f"چگالی {density*100:.1f}٪ ({kw_count} بار)", "چگالی کلمه کلیدی را بین ۰.۵ تا ۲.۵٪ نگه دارید"))

    # ---- entities
    ents = (brief or {}).get("entities", [])
    if ents:
        present = [e["label"] for e in ents if _contains(text, e["label"])]
        F.append(Finding("entities_covered", "entities", len(present) / len(ents) >= 0.6, 0.7, f"{len(present)}/{len(ents)} موجودیت حاضر: {', '.join(present[:5])}", "موجودیت‌های غایب را اضافه کنید: " + ", ".join([e["label"] for e in ents if e["label"] not in present][:5])))
        F.append(Finding("entity_in_headings", "entities", any(_contains(" ".join(h2s + h3s), e["label"]) for e in ents), 0.3, "حداقل یک موجودیت در سرفصل‌ها", "نام مدل/خدمت/مکان را در یک H2/H3 بیاورید"))
    else:
        F.append(Finding("entities_unknown", "entities", True, 1.0, "بریف موجودیتی ندارد", ""))

    # ---- headings
    F.append(Finding("single_h1", "headings", len(h1s) == 1 or (len(h1s) == 0 and bool(draft.title)), 0.25, f"{len(h1s)} H1", "دقیقاً یک H1 داشته باشید"))
    outline = [o["h2"] for o in (brief or {}).get("outline", [])]
    if outline:
        cov = sum(1 for o in outline if any(_tokens_covered(normalize_keyword(h), o, 0.6) for h in h2s + h3s))
        F.append(Finding("outline_coverage", "headings", cov / len(outline) >= 0.6, 0.35, f"{cov}/{len(outline)} سرفصل بریف پوشش داده شده", "سرفصل‌های پیشنهادی بریف را اضافه کنید"))
    else:
        F.append(Finding("h2_count", "headings", len(h2s) >= 3, 0.35, f"{len(h2s)} H2", "حداقل ۳ H2 داشته باشید"))
    levels = [h["level"] for h in st.get("headings", [])]
    skipped = any(b - a > 1 for a, b in zip(levels, levels[1:]))
    F.append(Finding("no_skipped_levels", "headings", not skipped, 0.15, "ترتیب سطوح سرفصل", "از H2 به H4 نپرید"))
    F.append(Finding("faq_when_questions", "headings", st.get("faq") or not (brief or {}).get("questions"), 0.25, "بخش سؤالات متداول", "بخش FAQ با اسکیما FAQPage اضافه کنید"))

    # ---- links
    links = st.get("links", [])
    internal = [l for l in links if _is_internal(l.get("href", ""), site_host)]
    F.append(Finding("min_internal_links", "links", len(internal) >= cfg.get("min_internal_links", 3), 0.35, f"{len(internal)} لینک داخلی", f"حداقل {cfg.get('min_internal_links', 3)} لینک داخلی اضافه کنید"))
    targets = {_norm_url(l["url"]) for l in (brief or {}).get("internal_links", [])}
    hit_targets = sum(1 for l in internal if _norm_url(l.get("href", "")) in targets)
    F.append(Finding("brief_link_targets", "links", (hit_targets >= 1) if targets else True, 0.25, f"{hit_targets}/{len(targets)} مقصد پیشنهادی بریف لینک شده", "به صفحات پیشنهادی بریف لینک بدهید"))
    bad_anchor = [l for l in internal if normalize_keyword(l.get("anchor", "")) in ("اینجا", "کلیک کنید", "این لینک", "here", "click here", "")]
    F.append(Finding("descriptive_anchors", "links", not bad_anchor, 0.2, f"{len(bad_anchor)} انکر غیرتوصیفی", "انکرتکست‌ها را توصیفی کنید"))
    dup = len(internal) - len({_norm_url(l.get("href", "")) for l in internal})
    F.append(Finding("no_duplicate_links", "links", dup == 0, 0.1, f"{dup} لینک تکراری", "لینک‌های تکراری را حذف کنید"))
    F.append(Finding("hub_linked", "links", any(_norm_url(l.get("href", "")) in hub_urls for l in internal) if hub_urls else True, 0.1, "لینک به صفحه هاب", "به یک صفحه هاب/دسته اصلی لینک بدهید"))

    # ---- cta
    cta_rules = memory.get("cta_rules") or []
    if cta_rules:
        F.append(Finding("cta_first_paragraph", "cta", bool(_PHONE.search(" ".join(paras[:1]))) or any(w in " ".join(paras[:1]) for w in _CTA_WORDS), 0.5, "CTA/شماره در پاراگراف اول (قاعده سایت)", "طبق قواعد CTA سایت، شماره تماس را در پاراگراف اول بیاورید"))
    F.append(Finding("cta_count", "cta", sum(1 for p in paras if any(w in p for w in _CTA_WORDS)) >= (2 if intent in ("transactional", "local") else 1), 0.5 if cta_rules else 0.7, "تعداد CTA کافی", "در پایان بخش‌های اصلی CTA بگذارید"))
    forb = [c for c in (memory.get("forbidden_claims") or []) if _contains(text, c)]
    F.append(Finding("no_forbidden_claims", "cta", not forb, 0.3 if not cta_rules else 0.0, f"ادعای ممنوع: {', '.join(forb)}" if forb else "بدون ادعای ممنوع", "ادعاهای ممنوع را حذف کنید"))
    if cta_rules:   # forbidden claims still matter: fold into cta with small weight by re-normalizing below
        F[-1].weight = 0.2; F[-2].weight = 0.4; F[-3].weight = 0.4

    # ---- completeness
    minw = cfg["min_words"].get(intent, cfg["min_words"]["default"])
    F.append(Finding("min_words", "completeness", draft.word_count >= minw, 0.35, f"{draft.word_count} کلمه (حداقل {minw})", f"محتوا را تا حداقل {minw} کلمه گسترش دهید"))
    qs = [q["question"] for q in (brief or {}).get("questions", [])]
    answered = sum(1 for q in qs if _tokens_covered(tnorm, q, 0.6))
    F.append(Finding("questions_answered", "completeness", (answered / len(qs) >= 0.5) if qs else True, 0.25, f"{answered}/{len(qs)} سؤال بریف پاسخ داده شده", "به سؤالات بریف پاسخ دهید"))
    imgs = st.get("images", [])
    F.append(Finding("images_alt", "completeness", all(i.get("alt") for i in imgs) if imgs else True, 0.15, f"{sum(1 for i in imgs if not i.get('alt'))} تصویر بدون alt", "برای همه تصاویر alt بنویسید"))
    ml = len(draft.meta_description or "")
    F.append(Finding("meta_length", "completeness", 100 <= ml <= 165, 0.15, f"طول متا {ml}", "توضیحات متا ۱۲۰–۱۶۰ نویسه"))
    F.append(Finding("title_length", "completeness", 20 <= len(title) <= 65, 0.10, f"طول عنوان {len(title)}", "عنوان ۲۰–۶۰ نویسه"))

    dims: dict[str, float] = {}
    for d in DIMS:
        fs = [f for f in F if f.dim == d]
        tw = sum(f.weight for f in fs) or 1.0
        dims[d] = round(100 * sum(f.weight for f in fs if f.passed) / tw, 1)
    total_w = sum(W.get(d, 0) for d in DIMS) or 1
    total = round(sum(dims[d] * W.get(d, 0) for d in DIMS) / total_w, 1)
    th = cfg["thresholds"]
    label = "ready" if total >= th["ready"] else ("needs_work" if total >= th["needs_work"] else "weak")
    return ContentScore(total=total, dims=dims, findings=F, weights={d: W.get(d, 0) for d in DIMS}, label=label)


def _is_internal(href: str, host: str | None) -> bool:
    if not href:
        return False
    if href.startswith("/") or href.startswith("#"):
        return not href.startswith("#")
    try:
        h = urlparse(href).hostname or ""
    except ValueError:
        return False
    return bool(host) and (h == host or h == f"www.{host}" or host == f"www.{h}")


def _norm_url(u: str) -> str:
    return (u or "").strip().lower().rstrip("/").replace("https://", "").replace("http://", "").replace("www.", "")
