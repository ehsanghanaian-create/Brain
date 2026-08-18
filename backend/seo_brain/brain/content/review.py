"""AI Content Review System — advisory findings before human approval.

rules pass (always): missing sections (brief outline vs. headings), missing entities, weak paragraphs, duplicate concepts
(paragraph shingling Jaccard), SEO issues (title/meta length, H1, alt, links to non-indexable/redirecting pages via graph).
ai pass (optional): orchestrator task SEO_ANALYSIS with a JSON schema; result validated; provenance stored; never applied.
Every finding: {code, severity high|medium|low, area, message_fa, evidence, suggestion_fa, auto_fixable}.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ...ai import AIMessage, AIOrchestrator, AITask, TaskKind
from ...brain.keywords.normalize import normalize_keyword, tokenize
from .drafts import Draft
from .scoring import ContentScore, _contains, _tokens_covered

_BOILER = ("همان‌طور که می‌دانید", "در این مقاله", "در ادامه", "لازم به ذکر است", "با ما همراه باشید", "as you know", "in this article")


@dataclass
class ReviewFinding:
    code: str
    severity: str
    area: str
    message_fa: str
    evidence: str = ""
    suggestion_fa: str = ""
    auto_fixable: bool = False
    paragraph_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _shingles(text: str, k: int = 3) -> set[str]:
    toks = tokenize(text)
    return {" ".join(toks[i:i + k]) for i in range(max(0, len(toks) - k + 1))}


def rules_review(draft: Draft, brief: dict[str, Any] | None, score: ContentScore | None, page_props_by_url: dict[str, dict] | None = None) -> list[ReviewFinding]:
    st = draft.structure or {}
    text = draft.body_text or ""
    tnorm = normalize_keyword(text)
    paras: list[str] = st.get("paragraphs", [])
    h_all = " ".join([h["text"] for h in st.get("headings", [])])
    out: list[ReviewFinding] = []
    # missing sections
    for o in (brief or {}).get("outline", []):
        h2 = o.get("h2", "")
        if h2 and not any(_tokens_covered(normalize_keyword(h["text"]), h2, 0.6) for h in st.get("headings", [])):
            out.append(ReviewFinding("missing_section", "medium", "structure", f"بخش پیشنهادی بریف پیدا نشد: «{h2}»", o.get("why", ""), f"یک H2 با عنوان «{h2}» و ۱–۲ پاراگراف اضافه کنید"))
    if (brief or {}).get("questions") and not st.get("faq"):
        out.append(ReviewFinding("missing_faq", "medium", "structure", "بخش سؤالات متداول وجود ندارد", f"{len(brief['questions'])} سؤال در بریف", "بخش FAQ با اسکیما FAQPage اضافه کنید", auto_fixable=False))
    # missing entities
    for e in (brief or {}).get("entities", []):
        if not _contains(text, e["label"]):
            out.append(ReviewFinding("missing_entity", "medium" if e["type"] in ("MODEL", "SERVICE", "LOCATION") else "low", "entities", f"موجودیت «{e['label']}» ({e['type']}) در متن نیامده", "", f"«{e['label']}» را در بخش مرتبط ذکر کنید"))
    # weak paragraphs
    kw_toks = set(tokenize((brief or {}).get("sources", {}).get("keyword", {}).get("keyword", "") or ""))
    ent_toks = {t for e in (brief or {}).get("entities", []) for t in tokenize(e["label"])}
    for i, p in enumerate(paras):
        toks = tokenize(p)
        if len(toks) < 25 and len(toks) > 0 and i not in (0,) and not any(w in p for w in ("تماس", "شماره", "۰۹", "09")):
            out.append(ReviewFinding("short_paragraph", "low", "quality", f"پاراگراف {i+1} خیلی کوتاه است ({len(toks)} واژه)", p[:80], "پاراگراف را با جزئیات/مثال کامل کنید", paragraph_index=i))
        elif toks and not (set(toks) & (kw_toks | ent_toks)) and len(toks) >= 40:
            out.append(ReviewFinding("off_topic_paragraph", "low", "quality", f"پاراگراف {i+1} هیچ کلمه کلیدی/موجودیتی ندارد", p[:80], "پاراگراف را به کلمه کلیدی یا موجودیت مرتبط گره بزنید", paragraph_index=i))
        if any(b in p for b in _BOILER):
            out.append(ReviewFinding("boilerplate", "low", "quality", f"عبارت کلیشه‌ای در پاراگراف {i+1}", next(b for b in _BOILER if b in p), "عبارت کلیشه‌ای را حذف و مستقیم شروع کنید", auto_fixable=True, paragraph_index=i))
    # duplicate concepts
    sh = [_shingles(p) for p in paras]
    for i in range(len(paras)):
        for j in range(i + 1, len(paras)):
            if sh[i] and sh[j]:
                jac = len(sh[i] & sh[j]) / len(sh[i] | sh[j])
                if jac >= 0.6:
                    out.append(ReviewFinding("duplicate_concept", "medium", "quality", f"پاراگراف‌های {i+1} و {j+1} تقریباً یکسان‌اند (شباهت {jac:.0%})", "", "یکی را حذف یا ادغام کنید", paragraph_index=i))
    h2n = [normalize_keyword(h) for h in st.get("h2", [])]
    if len(h2n) != len(set(h2n)):
        out.append(ReviewFinding("duplicate_heading", "medium", "structure", "سرفصل H2 تکراری", "", "سرفصل‌های تکراری را ادغام کنید"))
    # SEO issues
    title = draft.title or (st.get("h1") or [""])[0] or ""
    if not title:
        out.append(ReviewFinding("no_title", "high", "seo", "عنوان/H1 وجود ندارد", "", "یک H1 یکتا شامل کلمه کلیدی بنویسید"))
    elif len(title) > 65:
        out.append(ReviewFinding("title_too_long", "low", "seo", f"عنوان {len(title)} نویسه است", title, "عنوان را زیر ۶۰ نویسه کوتاه کنید", auto_fixable=True))
    if len(st.get("h1", [])) > 1:
        out.append(ReviewFinding("multiple_h1", "high", "seo", f"{len(st['h1'])} H1 در متن", "", "فقط یک H1 نگه دارید"))
    ml = len(draft.meta_description or "")
    if ml == 0:
        out.append(ReviewFinding("no_meta", "medium", "seo", "توضیحات متا ندارد", "", "توضیحات متا ۱۲۰–۱۶۰ نویسه با CTA بنویسید"))
    elif ml < 100 or ml > 165:
        out.append(ReviewFinding("meta_length", "low", "seo", f"طول توضیحات متا {ml}", "", "توضیحات متا را به ۱۲۰–۱۶۰ نویسه برسانید", auto_fixable=True))
    for img in st.get("images", []):
        if not img.get("alt"):
            out.append(ReviewFinding("image_no_alt", "low", "seo", "تصویر بدون alt", img.get("src", ""), "alt توصیفی شامل مدل/خدمت بنویسید", auto_fixable=True))
    for l in st.get("links", []):
        props = (page_props_by_url or {}).get(_n(l.get("href", "")))
        if props and props.get("indexable") in (False, 0):
            out.append(ReviewFinding("link_to_noindex", "medium", "seo", f"لینک به صفحه غیرقابل ایندکس: {l.get('href')}", str(props.get("indexability_reason", "")), "به نسخه قابل ایندکس لینک بدهید"))
        if props and props.get("status_code") in (301, 302, 404, 410):
            out.append(ReviewFinding("link_to_redirect", "medium", "seo", f"لینک به صفحه {props.get('status_code')}: {l.get('href')}", "", "به آدرس نهایی لینک بدهید", auto_fixable=True))
    if score:
        for f in score.findings:
            if not f.passed and f.dim in ("cta", "keywords") and f.rule in ("no_forbidden_claims", "kw_in_title", "cta_first_paragraph"):
                out.append(ReviewFinding(f"score_{f.rule}", "high" if f.rule == "no_forbidden_claims" else "medium", f.dim, f.evidence, "", f.fix_fa))
    return out


AI_SCHEMA = {"type": "object", "required": ["findings"], "properties": {"findings": {"type": "array"}, "summary_fa": {"type": "string"}}}


def ai_review(orch: AIOrchestrator, site_id: str, draft: Draft, brief: dict[str, Any] | None, rules: list[ReviewFinding]) -> tuple[list[ReviewFinding], dict[str, Any], str | None]:
    """Advisory AI pass. Returns (findings, provenance, summary). With only the Echo provider → no findings, says so."""
    body = (draft.body_text or "")[:12000]
    prompt = ("You are an SEO editor. Review this Persian draft against its brief. Return JSON {findings:[{code, severity(high|medium|low), area(structure|entities|quality|seo|intent), "
              "message_fa, evidence, suggestion_fa}], summary_fa}. Do not invent facts; do not rewrite; do not add claims.\n"
              f"BRIEF: h1={(brief or {}).get('h1')} outline={[o.get('h2') for o in (brief or {}).get('outline', [])]} entities={[e.get('label') for e in (brief or {}).get('entities', [])]} "
              f"questions={[q.get('question') for q in (brief or {}).get('questions', [])]}\nRULE FINDINGS ALREADY KNOWN: {[r.code for r in rules][:30]}\nDRAFT:\n{body}")
    task = AITask(kind=TaskKind.SEO_ANALYSIS, site_id=site_id, messages=[AIMessage("user", prompt)], json_schema=AI_SCHEMA)
    res = orch.run(task)
    prov: dict[str, Any] = {"ai_used": False, "attempts": [a.__dict__ for a in res.attempts]}
    if not (res.ok and res.response):
        prov["error"] = "orchestrator failed"
        return [], prov, None
    if res.response.provider == "echo":
        prov["note"] = "فقط EchoProvider در دسترس است؛ بازبینی AI انجام نشد (فقط قواعد)"
        return [], prov, None
    parsed = res.response.parsed if isinstance(res.response.parsed, dict) else {}
    out = []
    for f in parsed.get("findings", [])[:40]:
        if isinstance(f, dict) and f.get("message_fa"):
            out.append(ReviewFinding(code=str(f.get("code", "ai"))[:40], severity=f.get("severity") if f.get("severity") in ("high", "medium", "low") else "low",
                                     area=str(f.get("area", "quality"))[:20], message_fa=str(f["message_fa"])[:400], evidence=str(f.get("evidence", ""))[:300], suggestion_fa=str(f.get("suggestion_fa", ""))[:400]))
    prov.update(ai_used=True, provider=res.response.provider, model=res.response.model, cost_usd=res.response.cost_usd)
    return out, prov, (parsed.get("summary_fa") or None)


def _n(u: str) -> str:
    return (u or "").strip().lower().rstrip("/").replace("https://", "").replace("http://", "").replace("www.", "")


def counts(findings: list[ReviewFinding]) -> dict[str, int]:
    c = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        c[f.severity] = c.get(f.severity, 0) + 1
    return c


def review_status(score: ContentScore | None, findings: list[ReviewFinding], threshold: float) -> str:
    """ready when no high findings and score ≥ threshold; else changes_requested."""
    if score is None:
        return "changes_requested"
    if counts(findings)["high"] == 0 and score.total >= threshold:
        return "ready"
    return "changes_requested"
