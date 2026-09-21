"""Editor assistant: chat with the configured writer about ONE article (SEO review, rewrite, shorten, expand, FAQ, free
questions). Same Gateway / TaskRouter / PromptLibrary / MemoryPack stack as the workspace writer; the article text comes
from the editor (unsaved edits included) and a complete revised Markdown comes back for the user to accept — nothing
is saved here."""
from __future__ import annotations

import re
import time
import uuid
from typing import Any

from sqlalchemy import Engine

from ...ai.config import ProviderConfigRepository
from ...ai.gateway import Gateway, TaskRouter
from ...ai.gateway.gateway import CallMeta
from ...ai.memory_pack import MemoryPackBuilder
from ...ai.prompts import PromptLibrary, render
from ...ai.types import AIMessage, AITask, TaskKind
from .workspace import ContentTestWorkspace

# mode → (task kind used for routing, preset instruction; "" = the user's own message)
MODES: dict[str, tuple[str, str]] = {
    "seo": ("seo_review", "این مقاله را برای سئو بازبینی و بهبود بده: جایگاه و چگالی طبیعی کلمهٔ کلیدی اصلی و ثانویه، ساختار h2/h3، عنوان و متا، خوانایی، جای لینک داخلی و دعوت به اقدام. نسخهٔ کامل بهبودیافته را برگردان و در reply فهرست تغییرات را بنویس."),
    "rewrite": ("article_section", "کل مقاله را با حفظ ساختار، سرفصل‌ها و همهٔ اطلاعات، روان‌تر و حرفه‌ای‌تر بازنویسی کن."),
    "shorten": ("article_section", "مقاله را حدود ۳۰٪ کوتاه‌تر کن؛ سرفصل‌ها و نکات کلیدی حفظ شوند و فقط حشو و تکرار حذف شود."),
    "expand": ("article_section", "مقاله را با جزئیات کاربردی بیشتر (مثال، مراحل، نکات عملی) حدود ۳۰٪ گسترش بده — بدون هیچ عدد، قیمت یا ادعای ساختگی."),
    "faq": ("article_section", "یک بخش «سؤالات متداول» با ۵ پرسش واقعی کاربران و پاسخ‌های کوتاه به انتهای مقاله اضافه کن (اگر از قبل هست، بهترش کن)."),
    "chat": ("rewrite", ""),
}
ASSIST_SCHEMA = {"type": "object", "required": ["reply"], "properties": {"reply": {"type": "string"}, "revised_markdown": {"type": "string"}}}


class EditorAssistant:
    def __init__(self, engine: Engine, gateway: Gateway):
        self.engine, self.gw = engine, gateway
        self.router = TaskRouter(engine, gateway)
        self.prompts = PromptLibrary(engine)
        self.prompts.seed()
        self.mp = MemoryPackBuilder(engine)
        self.cfg = ProviderConfigRepository(engine)

    def run(self, site_id: str, *, markdown: str, message: str = "", mode: str = "chat", title: str = "", keyword: str = "",
            history: list[dict[str, Any]] | None = None, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
        kind, preset = MODES.get(mode, MODES["chat"])
        instruction = (message or "").strip() or preset or "دربارهٔ این مقاله چه پیشنهادی داری؟"
        pv = self.prompts.active_version("task.editor_assist", site_id) or {"template": "{{memory_pack}}\n{{instruction}}\n{{article}}", "ref": "fallback@v0", "id": None, "model_hints": {}, "key": "task.editor_assist", "version": 0}
        snap = self.mp.snapshot(site_id)
        system = (self.prompts.active_version("system.base") or {"template": ""})["template"]
        hist = "\n".join(f"{'کاربر' if h.get('role') == 'user' else 'دستیار'}: {str(h.get('content', ''))[:600]}" for h in (history or [])[-8:]) or "—"
        user = render(pv["template"], {"memory_pack": snap["rendered"], "title": title or "—", "keyword": keyword or "—", "history": hist,
                                        "instruction": instruction, "article": markdown or "(خالی)"}, require_memory=True)
        hints = pv.get("model_hints") or {}
        words = len(re.findall(r"\S+", markdown or ""))
        max_tokens = max(1500, min(16000, int(words * 4.5) + 1000))    # Persian ≈ 3–4 tokens/word + JSON wrapper
        run_id = f"as-{uuid.uuid4().hex[:10]}"
        task = AITask(kind=TaskKind.CONTENT_WRITING, site_id=site_id, messages=[AIMessage("system", system), AIMessage("user", user)], json_schema=ASSIST_SCHEMA,
                      max_tokens=max_tokens, temperature=float(hints.get("temperature", 0.3)), prompt_id=pv.get("key"), prompt_version=str(pv.get("version")), run_id=run_id)
        if provider and not model:
            p = self.cfg.get_by_name(provider)
            model = p.default_model if p else None
        dec = self.router.resolve(kind, site_id, priority="high", override={"provider": provider, "model": model} if provider and model else None)
        meta = CallMeta(site_id=site_id, run_id=run_id, agent="editor_assistant", prompt_refs={"system": "system.base", "task": pv.get("ref", "")},
                        memory_snapshot_id=snap["id"], route_reason=dec.reason)
        t0 = time.perf_counter()
        res = self.gw.run(task, dec.chain, meta)
        if not res.ok or not res.response:
            return {"ok": False, "run_id": run_id, "error": res.error_summary}
        r = res.response
        payload = r.parsed if isinstance(r.parsed, dict) else ContentTestWorkspace._loose_json(r.text)
        reply = str(payload.get("reply") or r.text or "").strip()
        revised = payload.get("revised_markdown")
        revised = revised.strip() if isinstance(revised, str) and revised.strip() else None
        return {"ok": True, "run_id": run_id, "mode": mode, "reply": reply, "revised_markdown": revised,
                "meta": {"provider": r.provider, "model": r.model, "input_tokens": r.input_tokens, "output_tokens": r.output_tokens, "cost_usd": r.cost_usd or 0.0,
                         "latency_ms": r.latency_ms, "elapsed_ms": int((time.perf_counter() - t0) * 1000), "route": [s.__dict__ for s in dec.chain][:3], "policy": dec.policy}}
