"""Agents — each has a responsibility, an input builder, an output schema (validated) and provenance.
Agents never touch providers directly: they build an AITask from a versioned prompt + MemoryPack and hand it to the Gateway
through the TaskRouter. Echo provider → deterministic placeholder outputs (clearly marked), so the pipeline is testable offline.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ...ai.gateway import CallMeta, Gateway, RouteStep, TaskRouter
from ...ai.prompts import PromptLibrary, render
from ...ai.types import AIMessage, AITask, TaskKind
from ...brain.keywords.normalize import normalize_keyword, tokenize

AGENTS = ("research", "outline", "writer", "fact_check", "seo", "linking", "reviewer")
AGENT_FA = {"research": "عامل تحقیق", "outline": "عامل ساختار", "writer": "عامل نگارش", "fact_check": "عامل راستی‌آزمایی", "seo": "عامل سئو", "linking": "عامل لینک‌سازی", "reviewer": "عامل بازبینی"}
AGENT_TASK = {"research": "research", "outline": "outline", "writer": "article_section", "fact_check": "fact_check", "seo": "seo_review", "linking": "internal_linking", "reviewer": "seo_review"}
AGENT_PROMPT = {"research": "agent.research", "outline": "agent.outline", "writer": "agent.writer_section", "fact_check": "agent.fact_check", "seo": "agent.seo", "linking": "agent.linking", "reviewer": "agent.reviewer"}
SCHEMAS: dict[str, dict] = {
    "research": {"required": ["facts", "questions", "gaps", "entities_to_cover"], "properties": {"facts": {}, "questions": {}, "gaps": {}, "entities_to_cover": {}}},
    "outline": {"required": ["h1", "sections", "faq"], "properties": {"h1": {}, "sections": {}, "faq": {}, "schema_types": {}}},
    "writer": {"required": ["markdown", "word_count"], "properties": {"markdown": {}, "word_count": {}, "entities_used": {}, "links_used": {}}},
    "fact_check": {"required": ["verdict", "issues"], "properties": {"verdict": {}, "issues": {}, "safe_rewrite": {}}},
    "seo": {"required": ["title_options", "meta_options"], "properties": {"title_options": {}, "meta_options": {}, "keyword_coverage_fixes": {}, "schema_jsonld": {}}},
    "linking": {"required": ["links"], "properties": {"links": {}}},
    "reviewer": {"required": ["findings"], "properties": {"findings": {}, "rewrite_proposals": {}, "summary_fa": {}}},
}
_KIND = {"research": TaskKind.RESEARCH, "outline": TaskKind.CONTENT_WRITING, "writer": TaskKind.CONTENT_WRITING, "fact_check": TaskKind.SEO_ANALYSIS, "seo": TaskKind.SEO_ANALYSIS, "linking": TaskKind.INTERNAL_LINKING, "reviewer": TaskKind.SEO_ANALYSIS}


@dataclass
class AgentResult:
    agent: str
    ok: bool
    payload: dict[str, Any]
    provenance: dict[str, Any]
    error: str | None = None
    placeholder: bool = False        # True when produced by Echo (no real provider)


class AgentRunner:
    def __init__(self, gateway: Gateway, router: TaskRouter, prompts: PromptLibrary, memory_rendered: str, memory_snapshot_id: int, site_id: str, run_id: str, content_id: int | None,
                 model_overrides: dict[str, dict[str, str]] | None = None, prompt_overrides: dict[str, int] | None = None, mode: str = "assisted"):
        self.gw, self.router, self.prompts = gateway, router, prompts
        self.memory, self.snapshot_id, self.site_id, self.run_id, self.content_id = memory_rendered, memory_snapshot_id, site_id, run_id, content_id
        self.model_overrides = model_overrides or {}
        self.prompt_overrides = prompt_overrides or {}
        self.mode = mode
        self.system = (prompts.active_version("system.base") or {"template": ""})["template"]

    def prompt_for(self, agent: str) -> dict:
        vid = self.prompt_overrides.get(agent)
        v = self.prompts.version(vid) if vid else None
        return v or self.prompts.active_version(AGENT_PROMPT[agent], self.site_id) or {"template": "{{memory_pack}}\n{{input}}", "ref": "fallback@v0", "id": None, "model_hints": {}}

    def route(self, agent: str):
        return self.router.resolve(AGENT_TASK[agent], self.site_id, priority="high" if agent in ("writer", "fact_check") else "normal", override=self.model_overrides.get(agent))

    def estimate(self, agent: str, variables: dict[str, Any]) -> dict[str, Any]:
        pv = self.prompt_for(agent); dec = self.route(agent)
        task = self._task(agent, pv, variables)
        est = self.gw.estimate(task, dec.chain)
        return {**est, "route": dec.to_dict()["chain"][:1], "reason": dec.reason, "prompt": pv.get("ref")}

    def _task(self, agent: str, pv: dict, variables: dict[str, Any]) -> AITask:
        user = render(pv["template"], {**variables, "memory_pack": self.memory}, require_memory=True)
        hints = pv.get("model_hints") or {}
        return AITask(kind=_KIND[agent], site_id=self.site_id, messages=[AIMessage("system", self.system), AIMessage("user", user)], json_schema=SCHEMAS[agent],
                      max_tokens=int(hints.get("max_tokens", 1800)), temperature=float(hints.get("temperature", 0.3)), prompt_id=pv.get("key"), prompt_version=str(pv.get("version")), run_id=self.run_id)

    def run(self, agent: str, variables: dict[str, Any], placeholder_fn=None) -> AgentResult:
        pv = self.prompt_for(agent); dec = self.route(agent)
        task = self._task(agent, pv, variables)
        meta = CallMeta(site_id=self.site_id, run_id=self.run_id, content_id=self.content_id, agent=agent, prompt_refs={"system": "system.base", "agent": pv.get("ref", "")}, memory_snapshot_id=self.snapshot_id, route_reason=dec.reason)
        res = self.gw.run(task, dec.chain, meta)
        prov = {"agent": agent, "prompt_version_id": pv.get("id"), "prompt_ref": pv.get("ref"), "memory_snapshot_id": self.snapshot_id, "route": dec.to_dict()["chain"][:3], "route_reason": dec.reason,
                "attempts": [a.__dict__ for a in res.attempts]}
        if not res.ok or not res.response:
            return AgentResult(agent, False, {}, prov, error=(res.attempts[-1].error if res.attempts else "no response"))
        r = res.response
        prov.update(provider=r.provider, model=r.model, input_tokens=r.input_tokens, output_tokens=r.output_tokens, cost_usd=r.cost_usd or 0.0, latency_ms=r.latency_ms)
        payload = r.parsed if isinstance(r.parsed, dict) else {}
        placeholder = r.provider == "echo"
        if placeholder and placeholder_fn:
            payload = placeholder_fn(variables)          # deterministic offline artifact, clearly marked
            prov["placeholder"] = True
        return AgentResult(agent, True, payload, prov, placeholder=placeholder)


# --------------------------------------------------------------------------- deterministic placeholders (Echo / offline)
def ph_research(v: dict) -> dict:
    facts = [{"text": f"کلمه کلیدی هدف: {v.get('keyword')}", "source": "cluster"}] + [{"text": f"کوئری واقعی: {q}", "source": "gsc"} for q in (v.get("_gsc_list") or [])[:5]]
    return {"facts": facts, "questions": [q for q in (v.get("_gsc_list") or []) if any(m in q for m in ("چگونه", "چرا", "قیمت", "شماره", "؟"))][:5], "gaps": ["[نمایشی — بدون ارائه‌دهنده AI] پوشش سؤالات کاربر"],
            "entities_to_cover": (v.get("_entity_list") or [])[:6], "_placeholder": True}


def ph_outline(v: dict) -> dict:
    b = v.get("_brief") or {}
    secs = [{"h2": o.get("h2"), "h3": o.get("h3", []), "goal": o.get("why", ""), "target_words": 150, "entities": [], "keywords": []} for o in (b.get("outline") or [])][:8] or [{"h2": f"خدمات {v.get('keyword')}", "h3": [], "goal": "پاسخ به اینتنت", "target_words": 150, "entities": [], "keywords": []}]
    if not any("سؤال" in (s["h2"] or "") for s in secs):
        secs.append({"h2": "سؤالات متداول", "h3": [], "goal": "FAQ", "target_words": 120, "entities": [], "keywords": []})
    return {"h1": b.get("h1") or v.get("keyword"), "sections": secs, "faq": [{"question": q.get("question"), "answer_hint": ""} for q in (b.get("questions") or [])][:5], "schema_types": ["Article", "FAQPage"], "_placeholder": True}


def ph_writer(v: dict) -> dict:
    h2 = v.get("h2") or "بخش"
    md = f"## {h2}\n\n[نمایشی — بدون ارائه‌دهنده AI واقعی] این بخش درباره «{v.get('keyword')}» است و باید {v.get('target_words', 150)} کلمه با پوشش {', '.join(v.get('_entities_list') or []) or 'موجودیت‌های سایت'} نوشته شود. برای تولید واقعی، در «مدل‌های AI» یک ارائه‌دهنده با کلید ثبت کنید.\n"
    for h3 in v.get("_h3_list") or []:
        md += f"\n### {h3}\n\n[نمایشی] توضیح کوتاه درباره {h3}.\n"
    return {"markdown": md, "word_count": len(md.split()), "entities_used": [], "links_used": [], "_placeholder": True}


def ph_factcheck(v: dict) -> dict:
    return {"verdict": "pass", "issues": [], "safe_rewrite": "", "_placeholder": True}


def ph_seo(v: dict) -> dict:
    k = v.get("keyword") or ""
    return {"title_options": [f"{k} | راهنمای کامل", f"{k} — خدمات و شماره تماس", f"همه چیز درباره {k}"], "meta_options": [f"{k}: خدمات، هزینه و زمان رسیدن — تماس بگیرید."[:160]], "keyword_coverage_fixes": [], "schema_jsonld": {}, "_placeholder": True}


def ph_linking(v: dict) -> dict:
    return {"links": [{"anchor": l.get("anchor"), "url": l.get("url"), "section_h2": None, "sentence": None, "action": "insert"} for l in (v.get("_links_list") or [])[:3]], "_placeholder": True}


def ph_reviewer(v: dict) -> dict:
    return {"findings": [], "rewrite_proposals": [], "summary_fa": "[نمایشی] بازبینی AI اجرا نشد (فقط قواعد)", "_placeholder": True}


PLACEHOLDERS = {"research": ph_research, "outline": ph_outline, "writer": ph_writer, "fact_check": ph_factcheck, "seo": ph_seo, "linking": ph_linking, "reviewer": ph_reviewer}


# --------------------------------------------------------------------------- section validation (deterministic, no AI)
def validate_section(md: str, target_words: int, entities: list[str], forbidden: list[str], keyword: str | None) -> dict[str, Any]:
    text_ = re.sub(r"[#*_>\[\]()]", " ", md)
    words = len([w for w in text_.split() if w])
    tn = normalize_keyword(text_)
    forb = [c for c in forbidden if c and normalize_keyword(c) in tn]
    ents_missing = [e for e in entities if e and normalize_keyword(e) not in tn]
    issues = []
    if words < max(60, int(target_words * 0.6)):
        issues.append({"code": "too_short", "message_fa": f"بخش {words} کلمه دارد (هدف {target_words})"})
    if forb:
        issues.append({"code": "forbidden_claim", "message_fa": "ادعای ممنوع در متن: " + "، ".join(forb)})
    if entities and len(ents_missing) == len(entities):
        issues.append({"code": "entities_missing", "message_fa": "هیچ‌کدام از موجودیت‌های این بخش در متن نیامده: " + "، ".join(entities[:4])})
    if not md.strip().startswith("##"):
        issues.append({"code": "no_h2", "message_fa": "بخش با H2 شروع نمی‌شود"})
    boiler = [b for b in ("در این مقاله", "همان‌طور که می‌دانید", "با ما همراه باشید") if b in md]
    if boiler:
        issues.append({"code": "boilerplate", "message_fa": "عبارت کلیشه‌ای: " + "، ".join(boiler)})
    return {"ok": not any(i["code"] in ("forbidden_claim", "no_h2") for i in issues), "words": words, "issues": issues, "entities_missing": ents_missing, "forbidden_found": forb}
