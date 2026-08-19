"""AI Content Test Workspace — a single-step "writer" flow on top of the Phase-9 abstraction layer (Gateway + TaskRouter +
PromptLibrary + MemoryPack). It exists so content generation can be tested visually before the full agent pipeline is wired
into the Studio. Structure: `WorkspaceStep`s (today only `writer`; research / outline / seo / linking / reviewer plug into the same
runner later — see `STEP_ORDER`). Providers are never called directly: everything goes through `Gateway.run`."""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from sqlalchemy import Engine, text

from ...ai.config import GATEWAY_KINDS, KEYLESS_KINDS, ProviderConfigRepository
from ...ai.gateway import Gateway, TaskRouter
from ...ai.gateway.gateway import CallMeta, RouteStep
from ...ai.memory_pack import MemoryPackBuilder
from ...ai.prompts import PromptLibrary, render
from ...ai.types import AIMessage, AITask, TaskKind
from ...brain.content.drafts import Draft, parse_draft
from ...brain.content.scoring import score_draft
from ...brain.keywords.normalize import normalize_keyword, tokenize
from ...db.repositories.memory import SiteMemoryRepository

# future agents plug in here (order = pipeline order); only `writer` is implemented in the workspace today
STEP_ORDER = ("research", "outline", "writer", "fact_check", "seo", "linking", "reviewer")
STEP_FA = {"research": "تحقیق", "outline": "ساختار", "writer": "نگارش", "fact_check": "راستی‌آزمایی", "seo": "سئو", "linking": "لینک‌سازی", "reviewer": "بازبینی"}
CONTENT_TYPES = ("article", "guide", "service_landing", "location_landing", "comparison", "faq", "product", "news")
CONTENT_TYPE_FA = {"article": "مقاله", "guide": "راهنما", "service_landing": "لندینگ خدمت", "location_landing": "لندینگ مکان", "comparison": "مقایسه", "faq": "پرسش‌های متداول", "product": "محصول", "news": "خبر"}
TONES = ("formal", "friendly", "expert", "persuasive", "simple")
TONE_FA = {"formal": "رسمی", "friendly": "صمیمی", "expert": "تخصصی", "persuasive": "ترغیبی", "simple": "ساده"}
INTENTS = ("informational", "navigational", "commercial", "transactional", "local")
WRITER_SCHEMA = {"type": "object", "required": ["title", "sections"], "properties": {"title": {"type": "string"}, "meta_description": {"type": "string"}, "h1": {"type": "string"}, "sections": {"type": "array"}, "faq": {"type": "array"},
                                                                                       "internal_links": {"type": "array"}, "keywords_used": {"type": "array"}, "notes": {"type": "string"}}}


@dataclass
class ContentSpec:
    title: str
    keyword: str
    secondary_keywords: list[str] = field(default_factory=list)
    intent: str = "informational"
    content_type: str = "article"
    category: str | None = None
    audience: str | None = None
    tone: str = "formal"
    word_count: int = 1200
    instructions: str | None = None

    def variables(self) -> dict[str, Any]:
        return {"title": self.title, "keyword": self.keyword, "secondary_keywords": "، ".join(self.secondary_keywords) or "—", "intent": self.intent, "content_type": CONTENT_TYPE_FA.get(self.content_type, self.content_type),
                "category": self.category or "—", "audience": self.audience or "—", "tone": TONE_FA.get(self.tone, self.tone), "word_count": self.word_count, "instructions": self.instructions or "—"}


@dataclass
class WorkspaceStep:
    key: str
    task_kind: str
    prompt_key: str
    schema: dict[str, Any]
    placeholder: Callable[[ContentSpec], dict[str, Any]]


def _placeholder_writer(spec: ContentSpec) -> dict[str, Any]:
    """Deterministic offline article (Echo / no provider) — clearly marked as demo."""
    kw = spec.keyword
    secs = [{"h2": f"{kw} چیست و چه زمانی به آن نیاز دارید؟", "h3": [], "paragraphs": [f"[نمایشی — بدون ارائه‌دهنده AI واقعی] این پاراگراف مقدمه درباره «{kw}» است و برای مخاطب «{spec.audience or 'عمومی'}» با لحن «{TONE_FA.get(spec.tone, spec.tone)}» نوشته می‌شود.", "برای تولید واقعی، در «مدل‌های AI» یک ارائه‌دهنده با کلید ثبت کنید و همین صفحه را دوباره اجرا کنید."]},
            {"h2": f"مراحل و هزینه {kw}", "h3": ["زمان پاسخ‌گویی", "عوامل مؤثر بر هزینه"], "paragraphs": [f"در این بخش مراحل خدمت «{kw}» و عوامل هزینه به‌صورت شفاف توضیح داده می‌شود؛ هیچ عدد یا ادعایی حدس زده نمی‌شود."]},
            {"h2": f"نکات مهم درباره {kw}", "h3": [], "paragraphs": ["نکات ایمنی و توصیه‌های کاربردی، مطابق قواعد کسب‌وکار در حافظه سایت."]}]
    for s in spec.secondary_keywords[:3]:
        secs.append({"h2": s, "h3": [], "paragraphs": [f"پوشش کلمه ثانویه «{s}» با پیوند طبیعی به موضوع اصلی."]})
    return {"title": spec.title or kw, "meta_description": f"{kw} — راهنمای کامل، مراحل، هزینه و پاسخ به سؤالات رایج. (نمایشی)"[:158], "h1": spec.title or kw, "sections": secs,
            "faq": [{"question": f"{kw} چقدر زمان می‌برد؟", "answer": "بسته به شرایط متفاوت است؛ در متن نهایی با داده واقعی سایت تکمیل شود."}, {"question": f"هزینه {kw} چگونه محاسبه می‌شود؟", "answer": "بر اساس عوامل ذکرشده در بخش هزینه."}, {"question": "چگونه درخواست ثبت کنم؟", "answer": "از طریق شماره تماس یا فرم سایت (CTA طبق قواعد حافظه سایت)."}],
            "internal_links": [{"anchor": kw, "target_topic": "صفحه خدمت اصلی"}, {"anchor": "سؤالات متداول", "target_topic": "صفحه پرسش‌های متداول"}] + [{"anchor": s, "target_topic": f"صفحه مرتبط با {s}"} for s in spec.secondary_keywords[:2]],
            "keywords_used": [kw, *spec.secondary_keywords[:3]], "notes": "خروجی نمایشی — Echo", "_placeholder": True}


STEPS: dict[str, WorkspaceStep] = {
    "writer": WorkspaceStep("writer", "article_long", "task.article_test", WRITER_SCHEMA, _placeholder_writer),
}


def assemble_markdown(payload: dict[str, Any]) -> str:
    out = [f"# {payload.get('h1') or payload.get('title') or ''}".rstrip(), ""]
    for s in payload.get("sections") or []:
        if not isinstance(s, dict):
            continue
        out.append(f"## {s.get('h2', '')}"); out.append("")
        for p in s.get("paragraphs") or []:
            out.append(str(p)); out.append("")
        for h3 in s.get("h3") or []:
            if isinstance(h3, dict):
                out.append(f"### {h3.get('text') or h3.get('h3', '')}"); out.append("")
                for p in h3.get("paragraphs") or []:
                    out.append(str(p)); out.append("")
            else:
                out.append(f"### {h3}"); out.append("")
    faq = payload.get("faq") or []
    if faq:
        out.append("## سؤالات متداول"); out.append("")
        for q in faq:
            if isinstance(q, dict):
                out.append(f"### {q.get('question', '')}"); out.append(""); out.append(str(q.get("answer", ""))); out.append("")
    return "\n".join(out).strip() + "\n"


class ContentTestWorkspace:
    def __init__(self, engine: Engine, gateway: Gateway):
        self.engine, self.gw = engine, gateway
        self.router = TaskRouter(engine, gateway)
        self.prompts = PromptLibrary(engine)
        self.prompts.seed()
        self.mp = MemoryPackBuilder(engine)
        self.cfg = ProviderConfigRepository(engine)
        self.memory = SiteMemoryRepository(engine)

    # ------------------------------------------------------------------ options (providers/models available to the UI)
    def options(self, site_id: str) -> dict[str, Any]:
        provs = []
        health = {h["provider"]: h for h in self.gw.health()}
        models = self.gw.models(enabled_only=True)
        for p in self.cfg.list():
            configured = bool(p.enabled and (p.secret_ref or p.kind in KEYLESS_KINDS))
            pm = [{"model_id": m["model_id"], "display": m.get("display") or m["model_id"], "tier": m["tier"], "price_in_per_m": m["price_in_per_m"], "price_out_per_m": m["price_out_per_m"]} for m in models if m["provider_id"] == p.id] \
                or ([{"model_id": p.default_model, "display": p.default_model, "tier": "balanced", "price_in_per_m": 0, "price_out_per_m": 0}] if p.default_model else [])
            # default model first (Claude: Sonnet), then the rest in tier order balanced → quality → fast → reasoning
            order = {"balanced": 0, "quality": 1, "fast": 2, "reasoning": 3}
            pm.sort(key=lambda m: (0 if m["model_id"] == p.default_model else 1, order.get(m["tier"], 9), m["model_id"]))
            lt = p.last_test or {}
            status = "connected" if (configured and lt.get("ok")) else ("error" if (configured and lt and not lt.get("ok")) else ("untested" if configured else "missing_credentials"))
            provs.append({"name": p.name, "kind": p.kind, "kind_label": p.to_dict().get("kind_label"), "configured": configured, "route_kind": "gateway" if p.kind in GATEWAY_KINDS else "direct", "enabled": p.enabled, "has_key": bool(p.secret_ref), "default_model": p.default_model,
                          "status": status, "last_test": {"ok": lt.get("ok"), "message": lt.get("message"), "tested_at": lt.get("tested_at")} if lt else None, "models": pm,
                          "health": {k: (health.get(p.name) or {}).get(k) for k in ("calls", "failures", "consecutive_failures", "p50_ms", "breaker_open_until")}})
        # Echo stays available as an offline/development fallback — never the default when a real provider is configured
        provs.append({"name": "echo", "kind": "echo", "kind_label": "Echo (تست آفلاین، بدون فراخوانی خارجی)", "configured": True, "route_kind": "offline", "enabled": True, "has_key": False, "default_model": "echo-1", "status": "offline_fallback", "last_test": None,
                      "models": [{"model_id": "echo-1", "display": "Echo (dev)", "tier": "fast", "price_in_per_m": 0, "price_out_per_m": 0}], "health": {}})
        auto = self.router.resolve("article_long", site_id, priority="high").to_dict()
        default = next((p for p in provs if p["kind"] == "anthropic" and p["configured"]), None) or next((p for p in provs if p["configured"] and p["kind"] != "echo"), None) or provs[-1]
        dmodel = default.get("default_model") or (default["models"][0]["model_id"] if default["models"] else None)
        return {"providers": provs, "default": {"provider": default["name"], "model": dmodel, "kind": default["kind"]}, "auto_route": auto,
                "content_types": [{"key": k, "fa": CONTENT_TYPE_FA[k]} for k in CONTENT_TYPES], "tones": [{"key": k, "fa": TONE_FA[k]} for k in TONES],
                "intents": list(INTENTS), "steps": [{"key": k, "fa": STEP_FA[k], "implemented": k in STEPS} for k in STEP_ORDER], "budget": self.gw.budget(site_id),
                "prompt": (self.prompts.active_version("task.article_test") or {}).get("ref")}

    # ------------------------------------------------------------------ prompt/task
    def _prompt(self, site_id: str, spec: ContentSpec, step: WorkspaceStep) -> tuple[dict, str, str, dict]:
        pv = self.prompts.active_version(step.prompt_key, site_id) or {"template": "{{memory_pack}}\n{{title}}", "ref": "fallback@v0", "id": None, "model_hints": {}}
        snap = self.mp.snapshot(site_id)
        system = (self.prompts.active_version("system.base") or {"template": ""})["template"]
        user = render(pv["template"], {**spec.variables(), "memory_pack": snap["rendered"]}, require_memory=True)
        return pv, system, user, snap

    def _task(self, site_id: str, spec: ContentSpec, step: WorkspaceStep, pv: dict, system: str, user: str, run_id: str) -> AITask:
        hints = pv.get("model_hints") or {}
        max_tokens = max(800, min(8000, int(spec.word_count * 2.2) + 600))
        return AITask(kind=TaskKind.CONTENT_WRITING, site_id=site_id, messages=[AIMessage("system", system), AIMessage("user", user)],
                      json_schema=step.schema, max_tokens=int(hints.get("max_tokens", max_tokens)) if hints.get("max_tokens") and int(hints["max_tokens"]) >= max_tokens else max_tokens,
                      temperature=float(hints.get("temperature", 0.4)), prompt_id=pv.get("key"), prompt_version=str(pv.get("version")), run_id=run_id)

    def _chain(self, site_id: str, provider: str | None, model: str | None):
        if provider == "echo" or (provider and provider.lower() == "echo"):
            return [RouteStep("echo", "echo-1", "انتخاب دستی: Echo (تست آفلاین)")], "Echo — بدون فراخوانی خارجی", "echo"
        if provider and not model:      # provider chosen without a model → its default model
            p = self.cfg.get_by_name(provider)
            model = p.default_model if p else None
        dec = self.router.resolve("article_long", site_id, priority="high", override={"provider": provider, "model": model} if provider and model else None)
        return dec.chain, dec.reason, dec.policy

    def estimate(self, site_id: str, spec: ContentSpec, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
        step = STEPS["writer"]
        pv, system, user, snap = self._prompt(site_id, spec, step)
        chain, reason, policy = self._chain(site_id, provider, model)
        task = self._task(site_id, spec, step, pv, system, user, "estimate")
        est = self.gw.estimate(task, chain)
        return {**est, "route": [s.__dict__ for s in chain][:3], "reason": reason, "policy": policy, "prompt_ref": pv.get("ref"), "memory_snapshot_id": snap["id"], "max_tokens": task.max_tokens, "budget": self.gw.budget(site_id)}

    # ------------------------------------------------------------------ generate (single writer step)
    def generate(self, site_id: str, spec: ContentSpec, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
        step = STEPS["writer"]
        run_id = f"ws-{uuid.uuid4().hex[:10]}"
        pv, system, user, snap = self._prompt(site_id, spec, step)
        chain, reason, policy = self._chain(site_id, provider, model)
        task = self._task(site_id, spec, step, pv, system, user, run_id)
        meta = CallMeta(site_id=site_id, run_id=run_id, agent="workspace_writer", prompt_refs={"system": "system.base", "task": pv.get("ref", "")}, memory_snapshot_id=snap["id"], route_reason=reason)
        t0 = time.perf_counter()
        res = self.gw.run(task, chain, meta)
        elapsed = int((time.perf_counter() - t0) * 1000)
        attempts = [a.__dict__ for a in res.attempts]
        if not res.ok or not res.response:
            return {"ok": False, "run_id": run_id, "error": (res.attempts[-1].error if res.attempts else "no response"), "attempts": attempts, "prompt": {"system": system, "user": user, "ref": pv.get("ref")}, "route": [s.__dict__ for s in chain]}
        r = res.response
        payload = r.parsed if isinstance(r.parsed, dict) else self._loose_json(r.text)
        placeholder = r.provider == "echo"
        if placeholder or not payload.get("sections"):
            payload = step.placeholder(spec) if placeholder else {**payload, "sections": payload.get("sections") or [{"h2": spec.title, "h3": [], "paragraphs": [r.text]}]}
        markdown = assemble_markdown(payload)
        seo = self.analyze(site_id, spec, payload, markdown)
        return {"ok": True, "run_id": run_id, "step": step.key, "result": {**payload, "markdown": markdown, "word_count": seo["word_count"]}, "seo": seo,
                "prompt": {"system": system, "user": user, "ref": pv.get("ref"), "prompt_version_id": pv.get("id"), "memory_snapshot_id": snap["id"], "schema": step.schema},
                "meta": {"provider": r.provider, "provider_kind": (self.cfg.get_by_name(r.provider).kind if r.provider != "echo" and self.cfg.get_by_name(r.provider) else r.provider), "model": r.model,
                         "input_tokens": r.input_tokens, "output_tokens": r.output_tokens, "cost_usd": r.cost_usd or 0.0, "latency_ms": r.latency_ms, "elapsed_ms": elapsed,
                         "attempts": attempts, "route": [s.__dict__ for s in chain][:3], "route_reason": reason, "policy": policy, "placeholder": placeholder, "task_kind": step.task_kind, "run_id": run_id,
                         "prompt_version": pv.get("ref"), "prompt_version_id": pv.get("id"), "memory_snapshot_id": snap["id"], "stop_reason": (r.raw or {}).get("stop_reason") if isinstance(r.raw, dict) else None,
                         "streamed": bool((r.raw or {}).get("streamed")) if isinstance(r.raw, dict) else False,
                         "gateway_decision": (r.raw or {}).get("decision") if isinstance(r.raw, dict) else None, "served_model": (r.raw or {}).get("served_model") if isinstance(r.raw, dict) else None,
                         "budget": self.gw.budget(site_id), "raw_excerpt": (r.text or "")[:400] if not placeholder else None}}

    @staticmethod
    def _loose_json(txt: str) -> dict[str, Any]:
        if not txt:
            return {}
        m = re.search(r"\{.*\}", txt, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
        return {}

    # ------------------------------------------------------------------ SEO analysis (Phase-7 scoring engine on the generated markdown)
    def analyze(self, site_id: str, spec: ContentSpec, payload: dict[str, Any], markdown: str) -> dict[str, Any]:
        st, body_text = parse_draft(markdown, "markdown")
        d = Draft(site_id=site_id, content_id=0, body=markdown, title=payload.get("title"), meta_description=payload.get("meta_description"), body_text=body_text, word_count=st.word_count, structure=st.to_dict())
        mem = self.memory.get(site_id).to_dict()
        with self.engine.connect() as cx:
            r = cx.execute(text("SELECT canonical_url FROM sites WHERE site_id=:s"), {"s": site_id}).first()
            host = (urlparse(r[0]).hostname or "").replace("www.", "") if r else None
            hubs = {(unquote(u) or "").strip().lower().rstrip("/").replace("https://", "").replace("http://", "").replace("www.", "") for (u,) in cx.execute(text("SELECT url FROM graph_nodes WHERE site_id=:s AND node_type IN ('PAGE','CATEGORY') AND url IS NOT NULL ORDER BY pagerank DESC LIMIT 15"), {"s": site_id}).all()}
        kw = {"keyword": spec.keyword, "intent": spec.intent}
        try:
            sc = score_draft(d, None, kw, spec.secondary_keywords, mem, host, hubs, None).to_dict()
        except Exception as e:  # noqa: BLE001 — analysis must never block the result
            sc = {"total": None, "dims": {}, "failed": [], "error": str(e)}
        kn = normalize_keyword(spec.keyword); tn = normalize_keyword(body_text); title_n = normalize_keyword(payload.get("title") or "")
        first = normalize_keyword((st.paragraphs[0] if st.paragraphs else ""))
        h2s = [h["text"] for h in st.headings if h.get("level") == 2]
        checks = [
            {"key": "kw_in_title", "fa": "کلمه کلیدی در عنوان", "ok": kn in title_n},
            {"key": "kw_in_h1", "fa": "کلمه کلیدی در H1", "ok": kn in normalize_keyword((st.headings[0]["text"] if st.headings and st.headings[0].get("level") == 1 else payload.get("h1") or ""))},
            {"key": "kw_in_intro", "fa": "کلمه کلیدی در پاراگراف اول", "ok": kn in first},
            {"key": "kw_in_h2", "fa": "کلمه کلیدی در یک H2", "ok": any(kn in normalize_keyword(h) for h in h2s)},
            {"key": "h2_count", "fa": "۴ تا ۸ سرفصل H2", "ok": 4 <= len(h2s) <= 8, "value": len(h2s)},
            {"key": "faq", "fa": "بخش سؤالات متداول", "ok": bool(st.faq or payload.get("faq"))},
            {"key": "meta_len", "fa": "طول توضیحات متا ۱۲۰–۱۶۰", "ok": 120 <= len(payload.get("meta_description") or "") <= 160, "value": len(payload.get("meta_description") or "")},
            {"key": "word_count", "fa": f"حدود {spec.word_count} کلمه (±۲۵٪)", "ok": spec.word_count * 0.75 <= st.word_count <= spec.word_count * 1.25, "value": st.word_count},
            {"key": "internal_links", "fa": "پیشنهاد لینک داخلی", "ok": len(payload.get("internal_links") or []) >= 3, "value": len(payload.get("internal_links") or [])},
        ]
        secondary_hits = [{"keyword": s, "used": normalize_keyword(s) in tn} for s in spec.secondary_keywords]
        density = round(100 * tn.count(kn) * max(1, len(kn.split())) / max(1, len(tn.split())), 2) if kn else 0.0
        forbidden = [f for f in (mem.get("forbidden_claims") or []) if normalize_keyword(str(f)) and normalize_keyword(str(f)) in tn]
        return {"score": sc, "checks": checks, "passed": sum(1 for c in checks if c["ok"]), "total_checks": len(checks), "word_count": st.word_count, "h2": h2s, "h3_count": sum(1 for h in st.headings if h.get("level") == 3),
                "keyword_density": density, "secondary_keywords": secondary_hits, "forbidden_claims_found": forbidden, "questions": st.questions, "keywords_used": payload.get("keywords_used") or []}

    # ------------------------------------------------------------------ hand-off: save as a Phase-6/7 draft (human action)
    def save_draft(self, site_id: str, content_id: int, markdown: str, title: str | None, meta_description: str | None, meta: dict[str, Any] | None, actor: str = "user") -> dict[str, Any]:
        from ...brain.content import ContentIntelligenceService
        intel = ContentIntelligenceService(self.engine, None)
        d = intel.create_draft(site_id, content_id, markdown, "markdown", title=title, meta_description=meta_description, source=f"ai:{(meta or {}).get('provider') or 'workspace'}", author=actor,
                               change_summary="از فضای آزمایش تولید محتوا", provenance={"workspace_run_id": (meta or {}).get("run_id"), "provider": (meta or {}).get("provider"), "model": (meta or {}).get("model"), "placeholder": (meta or {}).get("placeholder")})
        return {"draft_id": d.id, "version": d.version, "content_id": content_id}

    def history(self, site_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.engine.connect() as cx:
            rows = cx.execute(text("SELECT run_id, provider, model, input_tokens, output_tokens, cost_usd, latency_ms, ok, error, created_at FROM ai_calls WHERE site_id=:s AND agent='workspace_writer' ORDER BY id DESC LIMIT :l"), {"s": site_id, "l": limit}).mappings().all()
        return [dict(r) for r in rows]
