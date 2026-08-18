"""GenerationPipeline — section-by-section content generation with checkpoints, artifacts, provenance and events.

Flow: Brief → Research → Outline → (per section: Writer → Section validation → Fact Check → optional single retry) → Assembly
      → SEO → Linking → Reviewer → draft version (assisted) or artifact-only (manual) → Phase-7 score → review → human approval.
Every run stores: memory_snapshot_id, prompt_versions per agent, chosen models per agent, every agent output (artifacts).
AI never publishes. Runs are jobs (JobQueue) and publish events to the EventBus topic `gen:<run_id>` (SSE).
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Callable

from sqlalchemy import Engine, and_, select, text

from ...ai.gateway import BudgetExceeded, Gateway, TaskRouter
from ...ai.memory_pack import MemoryPackBuilder
from ...ai.prompts import PromptLibrary
from ...automation.events import EventBus, get_event_bus
from ...brain.content import ContentIntelligenceService, ContentRepository, ContentService
from ...brain.keywords import KeywordsRepository
from ...db.repositories.base import dumps, loads, utcnow
from ...db.repositories.memory import SiteMemoryRepository
from ...db.tables import generation_artifacts, generation_runs
from .agents import AGENT_FA, AGENTS, PLACEHOLDERS, AgentResult, AgentRunner, validate_section

STEP_FA = {"plan": "برنامه‌ریزی", "research": "تحقیق", "outline": "ساختار", "sections": "نگارش بخش‌ها", "fact_check": "راستی‌آزمایی", "assembly": "مونتاژ مقاله", "seo": "سئو", "linking": "لینک‌سازی", "review": "بازبینی", "draft": "ثبت پیش‌نویس", "score": "امتیازدهی"}


class GenerationPipeline:
    def __init__(self, engine: Engine, gateway: Gateway | None = None, bus: EventBus | None = None):
        self.engine = engine
        self.gw = gateway or Gateway(engine)
        self.router = TaskRouter(engine, self.gw)
        self.prompts = PromptLibrary(engine); self.prompts.seed()
        self.mp = MemoryPackBuilder(engine)
        self.bus = bus or get_event_bus()
        self.content = ContentRepository(engine)
        self.kw = KeywordsRepository(engine)
        self.memory = SiteMemoryRepository(engine)

    # ------------------------------------------------------------------ run records
    def create_run(self, site_id: str, content_id: int, mode: str, models: dict | None = None, prompt_versions: dict | None = None, created_by: str | None = None) -> dict:
        item = self.content.get(site_id, content_id)
        if not item:
            raise KeyError(content_id)
        if mode not in ("manual", "assisted"):
            raise ValueError("mode must be manual or assisted (autopilot is reserved and disabled)")
        run_id = f"gen-{uuid.uuid4().hex[:10]}"
        snap = self.mp.snapshot(site_id)
        est = self.estimate(site_id, content_id, models, prompt_versions)
        with self.engine.begin() as cx:
            cx.execute(generation_runs.insert().values(run_id=run_id, site_id=site_id, content_id=content_id, mode=mode, status="queued", step="plan", steps=dumps([]), models=dumps(models or {}),
                                                       prompt_versions=dumps(prompt_versions or {}), memory_snapshot_id=snap["id"], estimate=dumps(est), actual=dumps({}), created_by=created_by, created_at=utcnow(), updated_at=utcnow()))
        return self.get_run(run_id)  # type: ignore[return-value]

    def get_run(self, run_id: str) -> dict | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(generation_runs).where(generation_runs.c.run_id == run_id)).first()
            arts = [dict(a._mapping) for a in cx.execute(select(generation_artifacts).where(generation_artifacts.c.run_id == run_id).order_by(generation_artifacts.c.id)).all()] if r else []
        if not r:
            return None
        d = dict(r._mapping)
        for k in ("steps", "models", "prompt_versions", "estimate", "actual"):
            d[k] = loads(d[k], [] if k == "steps" else {})
        d["artifacts"] = [{**a, "payload": loads(a["payload"], {}), "provenance": loads(a["provenance"], {})} for a in arts]
        d["step_fa"] = STEP_FA.get(d.get("step") or "", d.get("step"))
        return d

    def list_runs(self, site_id: str, content_id: int | None = None, limit: int = 50) -> list[dict]:
        conds = [generation_runs.c.site_id == site_id]
        if content_id: conds.append(generation_runs.c.content_id == content_id)
        with self.engine.connect() as cx:
            rows = [dict(r._mapping) for r in cx.execute(select(generation_runs).where(and_(*conds)).order_by(generation_runs.c.id.desc()).limit(limit)).all()]
        for d in rows:
            for k in ("steps", "models", "prompt_versions", "estimate", "actual"):
                d[k] = loads(d[k], [] if k == "steps" else {})
        return rows

    def _update(self, run_id: str, **vals) -> None:
        for k in ("steps", "estimate", "actual", "models", "prompt_versions"):
            if k in vals and not isinstance(vals[k], str):
                vals[k] = dumps(vals[k])
        with self.engine.begin() as cx:
            cx.execute(generation_runs.update().where(generation_runs.c.run_id == run_id).values(updated_at=utcnow(), **vals))

    def _artifact(self, run_id: str, step: str, agent: str, payload: dict, provenance: dict) -> int:
        with self.engine.begin() as cx:
            v = (cx.execute(text("SELECT max(version) FROM generation_artifacts WHERE run_id=:r AND step=:s"), {"r": run_id, "s": step}).scalar() or 0) + 1
            return int(cx.execute(generation_artifacts.insert().values(run_id=run_id, step=step, agent=agent, version=v, schema_key=agent, payload=dumps(payload), provenance=dumps(provenance), created_at=utcnow())).inserted_primary_key[0])

    def _emit(self, run_id: str, typ: str, **data) -> None:
        self.bus.publish(f"gen:{run_id}", {"type": typ, "run_id": run_id, **data})

    # ------------------------------------------------------------------ context
    def context(self, site_id: str, content_id: int) -> dict[str, Any]:
        item = self.content.get(site_id, content_id)
        brief = self.content.get_brief(site_id, item.brief_id).to_dict() if item and item.brief_id else None
        kw = self.kw.get(site_id, item.target_keyword_id) if item and item.target_keyword_id else None
        siblings = []
        if kw and kw.cluster_id:
            rows, _ = self.kw.list(site_id, cluster_id=kw.cluster_id, limit=30); siblings = [r.keyword for r in rows if r.id != kw.id]
        gsc = self.kw.gsc_by_normalized(site_id)
        kn = kw.normalized if kw else None
        toks = set(kw.keyword.split()) if kw else set((item.target_keyword or item.title).split())
        gsc_list = sorted([(q, g["impressions"], g["position"]) for q, g in gsc.items() if len(set(q.split()) & toks) >= max(1, len(toks) // 2)], key=lambda x: -x[1])[:12]
        entities = [e.get("label") for e in (brief or {}).get("entities", [])] if brief else []
        links = (brief or {}).get("internal_links", []) if brief else []
        # + phase 8 content_outbound suggestions for this planned content, if any
        try:
            with self.engine.connect() as cx:
                for a, u, why in cx.execute(text("SELECT anchor, target_url, reason_fa FROM link_suggestions WHERE site_id=:s AND source_node_id=:n AND status IN ('new','accepted') ORDER BY score DESC LIMIT 6"), {"s": site_id, "n": f"content:{content_id}"}).all():
                    links.append({"anchor": a, "url": u, "reason": why})
        except Exception:  # noqa: BLE001
            pass
        mem = self.memory.get(site_id).to_dict()
        return {"item": item, "brief": brief, "keyword": kw.keyword if kw else (item.target_keyword or item.title), "intent": (kw.intent if kw else None) or (item.intent if item else None) or (brief or {}).get("intent") or "commercial",
                "siblings": siblings, "gsc_list": [f"{q} (جایگاه {p}, {i} ایمپرشن)" for q, i, p in gsc_list], "gsc_raw": [q for q, _, _ in gsc_list], "entities": entities, "links": links,
                "existing_pages": [p.get("url") for p in (brief or {}).get("sources", {}).get("existing_pages", [])] if brief else [], "forbidden": mem.get("forbidden_claims") or [], "memory": mem}

    # ------------------------------------------------------------------ estimate
    def estimate(self, site_id: str, content_id: int, models: dict | None = None, prompt_versions: dict | None = None) -> dict[str, Any]:
        ctx = self.context(site_id, content_id)
        snap = self.mp.snapshot(site_id)
        ar = AgentRunner(self.gw, self.router, self.prompts, snap["rendered"], snap["id"], site_id, "estimate", content_id, models, prompt_versions)
        n_sections = max(4, min(9, len((ctx["brief"] or {}).get("outline") or []) or 6))
        per: dict[str, Any] = {}
        per["research"] = ar.estimate("research", self._research_vars(ctx))
        per["outline"] = ar.estimate("outline", {"keyword": ctx["keyword"], "intent": ctx["intent"], "brief": json.dumps(ctx["brief"] or {}, ensure_ascii=False)[:3000], "research": "{}"})
        w = ar.estimate("writer", {"h1": ctx["keyword"], "keyword": ctx["keyword"], "intent": ctx["intent"], "outline_summary": "…", "h2": "…", "goal": "…", "h3": "", "entities": "", "keywords": "", "facts": "", "internal_links": "", "target_words": 180})
        per["writer"] = {**w, "cost_usd": round(w["cost_usd"] * n_sections, 5), "input_tokens": w["input_tokens"] * n_sections, "output_tokens": w["output_tokens"] * n_sections, "sections": n_sections}
        f = ar.estimate("fact_check", {"facts": "", "entities": "", "markdown": "…" * 200})
        per["fact_check"] = {**f, "cost_usd": round(f["cost_usd"] * n_sections, 5), "input_tokens": f["input_tokens"] * n_sections, "output_tokens": f["output_tokens"] * n_sections}
        per["seo"] = ar.estimate("seo", {"keyword": ctx["keyword"], "intent": ctx["intent"], "cluster_keywords": ", ".join(ctx["siblings"]), "outline_summary": "…", "intro": "…"})
        per["linking"] = ar.estimate("linking", {"markdown": "…" * 500, "link_candidates": json.dumps(ctx["links"], ensure_ascii=False), "max_links": 5})
        per["reviewer"] = ar.estimate("reviewer", {"brief": "…", "rule_findings": "[]", "markdown": "…" * 800})
        tot = {"input_tokens": sum(p["input_tokens"] for p in per.values()), "output_tokens": sum(p["output_tokens"] for p in per.values()), "cost_usd": round(sum(p["cost_usd"] for p in per.values()), 4)}
        return {"per_agent": per, "total": tot, "sections": n_sections, "budget": self.gw.budget(site_id), "memory_snapshot_id": snap["id"]}

    @staticmethod
    def _research_vars(ctx: dict) -> dict:
        return {"keyword": ctx["keyword"], "intent": ctx["intent"], "cluster_keywords": ", ".join(ctx["siblings"]) or "—", "gsc_queries": "؛ ".join(ctx["gsc_list"]) or "—", "existing_pages": ", ".join(ctx["existing_pages"]) or "—",
                "entities": ", ".join(ctx["entities"]) or "—", "competitors": "در دسترس نیست (منبع رقبا هنوز جمع‌آوری نمی‌شود)", "_gsc_list": ctx["gsc_raw"], "_entity_list": ctx["entities"]}

    # ------------------------------------------------------------------ execute (job handler)
    def execute(self, run_id: str, cancel_check: Callable[[], bool] | None = None) -> dict[str, Any]:
        run = self.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        site_id, cid, mode = run["site_id"], run["content_id"], run["mode"]
        ctx = self.context(site_id, cid)
        snap = self.mp.get_snapshot(run["memory_snapshot_id"]) or self.mp.snapshot(site_id)
        ar = AgentRunner(self.gw, self.router, self.prompts, snap["rendered"], snap["id"], site_id, run_id, cid, run["models"], run["prompt_versions"], mode)
        steps: list[dict] = []; actual = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "latency_ms": 0}
        used_models: dict[str, Any] = {}; used_prompts: dict[str, Any] = {}

        def bump(res: AgentResult):
            p = res.provenance
            actual["input_tokens"] += p.get("input_tokens", 0); actual["output_tokens"] += p.get("output_tokens", 0); actual["cost_usd"] = round(actual["cost_usd"] + p.get("cost_usd", 0.0), 5); actual["latency_ms"] += p.get("latency_ms", 0)
            used_models[res.agent] = {"provider": p.get("provider"), "model": p.get("model")}; used_prompts[res.agent] = p.get("prompt_version_id")

        def step_start(key: str, agent: str):
            steps.append({"key": key, "agent": agent, "status": "running", "started_at": utcnow()})
            self._update(run_id, status="running", step=key, steps=steps); self._emit(run_id, "step_start", step=key, step_fa=STEP_FA.get(key.split(":")[0], key), agent=agent)

        def step_done(key: str, artifact_id: int | None, res: AgentResult | None, extra: dict | None = None):
            s = next(x for x in reversed(steps) if x["key"] == key)
            s.update(status="succeeded" if (res is None or res.ok) else "failed", finished_at=utcnow(), artifact_id=artifact_id, provenance=(res.provenance if res else {}), error=(res.error if res else None), **(extra or {}))
            self._update(run_id, steps=steps, actual=actual, models=used_models or run["models"], prompt_versions=used_prompts or run["prompt_versions"])
            self._emit(run_id, "step_done", step=key, ok=s["status"] == "succeeded", cost_usd=actual["cost_usd"], tokens=actual["input_tokens"] + actual["output_tokens"], **(extra or {}))

        def cancelled() -> bool:
            if cancel_check and cancel_check():
                return True
            with self.engine.connect() as cx:
                st = cx.execute(select(generation_runs.c.status).where(generation_runs.c.run_id == run_id)).scalar()
            return st == "cancelled"

        try:
            self._emit(run_id, "start", mode=mode, keyword=ctx["keyword"], sections_planned=None)
            # research
            step_start("research", "research"); res = ar.run("research", self._research_vars(ctx), PLACEHOLDERS["research"]); bump(res)
            if not res.ok: raise RuntimeError(f"research failed: {res.error}")
            research = res.payload; step_done("research", self._artifact(run_id, "research", "research", research, res.provenance), res)
            if cancelled(): return self._finish(run_id, "cancelled", steps, actual)
            # outline
            step_start("outline", "outline")
            res = ar.run("outline", {"keyword": ctx["keyword"], "intent": ctx["intent"], "brief": json.dumps(ctx["brief"] or {}, ensure_ascii=False)[:4000], "research": json.dumps(research, ensure_ascii=False)[:3000], "_brief": ctx["brief"]}, PLACEHOLDERS["outline"]); bump(res)
            if not res.ok: raise RuntimeError(f"outline failed: {res.error}")
            outline = res.payload; sections = [s for s in (outline.get("sections") or []) if isinstance(s, dict) and s.get("h2")][:9]
            if not sections:      # model returned an unusable outline → fall back to the brief's outline (deterministic), never an empty article
                fb = PLACEHOLDERS["outline"]({"keyword": ctx["keyword"], "_brief": ctx["brief"]})
                sections = fb["sections"]; outline = {**outline, "sections": sections, "h1": outline.get("h1") or fb["h1"], "faq": outline.get("faq") or fb["faq"], "_fallback": "brief_outline"}
                if not sections:
                    raise RuntimeError("outline produced no sections and no brief outline is available — generate a brief first")
            step_done("outline", self._artifact(run_id, "outline", "outline", outline, res.provenance), res, {"sections": len(sections), "fallback": outline.get("_fallback")})
            self._emit(run_id, "plan", sections=[s["h2"] for s in sections], h1=outline.get("h1"))
            # sections
            facts = [f.get("text") if isinstance(f, dict) else str(f) for f in research.get("facts", [])]
            outline_summary = " | ".join(s["h2"] for s in sections)
            written: list[dict] = []
            for i, sec in enumerate(sections, start=1):
                if cancelled(): return self._finish(run_id, "cancelled", steps, actual)
                key = f"section:{i}"; step_start(key, "writer")
                vars_ = {"h1": outline.get("h1") or ctx["keyword"], "keyword": ctx["keyword"], "intent": ctx["intent"], "outline_summary": outline_summary, "h2": sec["h2"], "goal": sec.get("goal", ""), "h3": ", ".join(sec.get("h3") or []),
                         "entities": ", ".join(sec.get("entities") or ctx["entities"][:3]), "keywords": ", ".join(sec.get("keywords") or ctx["siblings"][:3]), "facts": "؛ ".join(facts[:12]) or "—",
                         "internal_links": json.dumps(ctx["links"][:6], ensure_ascii=False), "target_words": int(sec.get("target_words") or 150), "_h3_list": sec.get("h3") or [], "_entities_list": sec.get("entities") or ctx["entities"][:3]}
                res = ar.run("writer", vars_, PLACEHOLDERS["writer"]); bump(res)
                if not res.ok:
                    step_done(key, None, res); raise RuntimeError(f"section {i} failed: {res.error}")
                md = str(res.payload.get("markdown") or "")
                val = validate_section(md, vars_["target_words"], vars_["_entities_list"], ctx["forbidden"], ctx["keyword"])
                # fact check (per section)
                fc = ar.run("fact_check", {"facts": "؛ ".join(facts[:15]) or "—", "entities": ", ".join(ctx["entities"]) or "—", "markdown": md}, PLACEHOLDERS["fact_check"]); bump(fc)
                fc_payload = fc.payload if fc.ok else {"verdict": "unknown", "issues": [], "error": fc.error}
                if fc.ok and fc_payload.get("verdict") == "revise" and fc_payload.get("safe_rewrite"):
                    md = str(fc_payload["safe_rewrite"]); val = validate_section(md, vars_["target_words"], vars_["_entities_list"], ctx["forbidden"], ctx["keyword"])
                # one retry when validation hard-fails and a real provider answered
                if not val["ok"] and not res.placeholder:
                    res2 = ar.run("writer", {**vars_, "goal": vars_["goal"] + " — توجه: " + "؛ ".join(i["message_fa"] for i in val["issues"])}, PLACEHOLDERS["writer"]); bump(res2)
                    if res2.ok:
                        md2 = str(res2.payload.get("markdown") or ""); val2 = validate_section(md2, vars_["target_words"], vars_["_entities_list"], ctx["forbidden"], ctx["keyword"])
                        if len(val2["issues"]) <= len(val["issues"]): md, val, res = md2, val2, res2
                aid = self._artifact(run_id, key, "writer", {"h2": sec["h2"], "markdown": md, "validation": val, "fact_check": fc_payload}, {**res.provenance, "fact_check": fc.provenance})
                written.append({"h2": sec["h2"], "markdown": md, "validation": val, "fact_check": fc_payload})
                step_done(key, aid, res, {"words": val["words"], "validation_ok": val["ok"], "fact_check": fc_payload.get("verdict")})
            # assembly
            step_start("assembly", "writer")
            h1 = outline.get("h1") or ctx["keyword"]
            body = f"# {h1}\n\n" + "\n\n".join(w["markdown"].strip() for w in written)
            faq = outline.get("faq") or []
            if faq and not any("سؤال" in w["h2"] for w in written):
                body += "\n\n## سؤالات متداول\n" + "\n".join(f"\n### {q.get('question')}\n{q.get('answer_hint') or ''}" for q in faq if isinstance(q, dict) and q.get("question"))
            aid = self._artifact(run_id, "assembly", "writer", {"h1": h1, "markdown": body, "sections": len(written), "words": len(body.split())}, {"agent": "assembly"})
            step_done("assembly", aid, None, {"words": len(body.split())})
            # seo
            step_start("seo", "seo")
            intro = written[0]["markdown"][:800] if written else ""
            res = ar.run("seo", {"keyword": ctx["keyword"], "intent": ctx["intent"], "cluster_keywords": ", ".join(ctx["siblings"]) or "—", "outline_summary": outline_summary, "intro": intro}, PLACEHOLDERS["seo"]); bump(res)
            seo = res.payload if res.ok else {}
            step_done("seo", self._artifact(run_id, "seo", "seo", seo, res.provenance) if res.ok else None, res)
            # linking
            step_start("linking", "linking")
            res = ar.run("linking", {"markdown": body[:12000], "link_candidates": json.dumps(ctx["links"], ensure_ascii=False), "max_links": 5, "_links_list": ctx["links"]}, PLACEHOLDERS["linking"]); bump(res)
            linking = res.payload if res.ok else {"links": []}
            step_done("linking", self._artifact(run_id, "linking", "linking", linking, res.provenance) if res.ok else None, res)
            # reviewer (AI, advisory)
            step_start("review", "reviewer")
            res = ar.run("reviewer", {"brief": json.dumps(ctx["brief"] or {}, ensure_ascii=False)[:3000], "rule_findings": "[]", "markdown": body[:14000]}, PLACEHOLDERS["reviewer"]); bump(res)
            review_ai = res.payload if res.ok else {"findings": []}
            step_done("review", self._artifact(run_id, "review", "reviewer", review_ai, res.provenance) if res.ok else None, res)
            # draft (assisted) + score/review via Phase 7
            result: dict[str, Any] = {"h1": h1, "markdown": body, "seo": seo, "linking": linking, "review_ai": review_ai, "sections": len(written)}
            if mode == "assisted":
                step_start("draft", "system")
                d = self._promote(run_id, site_id, cid, body, h1, seo, used_models, used_prompts, snap["id"])
                step_done("draft", None, None, {"draft_id": d["draft_id"], "version": d["version"], "score": d["score"], "review_status": d["review_status"]})
                result.update(d)
            self._update(run_id, status="succeeded", step="done", steps=steps, actual=actual)
            self._emit(run_id, "done", ok=True, cost_usd=actual["cost_usd"], **({"draft_id": result.get("draft_id"), "score": result.get("score"), "review_status": result.get("review_status")}))
            return {"status": "succeeded", "run_id": run_id, "actual": actual, **{k: v for k, v in result.items() if k != "markdown"}}
        except BudgetExceeded as e:
            self._update(run_id, status="failed", steps=steps, actual=actual, error=str(e)); self._emit(run_id, "failed", error=str(e), code="budget_exceeded"); return {"status": "failed", "error": str(e), "code": "budget_exceeded"}
        except Exception as e:  # noqa: BLE001
            self._update(run_id, status="failed", steps=steps, actual=actual, error=str(e)); self._emit(run_id, "failed", error=str(e)); return {"status": "failed", "error": str(e)}

    def _finish(self, run_id: str, status: str, steps: list, actual: dict) -> dict:
        self._update(run_id, status=status, steps=steps, actual=actual); self._emit(run_id, status); return {"status": status, "run_id": run_id, "actual": actual}

    def _promote(self, run_id: str, site_id: str, cid: int, body: str, h1: str, seo: dict, models: dict, prompts: dict, snapshot_id: int) -> dict[str, Any]:
        """Create a draft version from the assembled article + run Phase-7 score/review. Human approval remains the workflow."""
        intel = ContentIntelligenceService(self.engine, None)
        prov_model = models.get("writer") or {}
        meta = (seo.get("meta_options") or [None])[0] if isinstance(seo, dict) else None
        d = intel.create_draft(site_id, cid, body, "markdown", title=(seo.get("title_options") or [h1])[0] if isinstance(seo, dict) and seo.get("title_options") else h1, meta_description=meta,
                               source=f"ai:{prov_model.get('provider') or 'echo'}", author="ai-pipeline", change_summary=f"تولید AI (run {run_id})",
                               provenance={"run_id": run_id, "models": models, "prompt_versions": prompts, "memory_snapshot_id": snapshot_id, "provider": prov_model.get("provider"), "model": prov_model.get("model")})
        rev = intel.review(site_id, cid, d.id, use_ai=False)
        self._update(run_id, draft_id=d.id, score=rev["score"]["total"], review_status=rev["review_status"])
        # advisory provenance chip on the content item (Kanban/list). Never touches status/publishing.
        with self.engine.begin() as cx:
            cx.execute(text("UPDATE content_items SET ai_provider=:p, ai_model=:m, updated_at=:t WHERE site_id=:s AND id=:c"),
                       {"p": prov_model.get("provider") or "echo", "m": prov_model.get("model") or "echo", "t": utcnow(), "s": site_id, "c": cid})
        return {"draft_id": d.id, "version": d.version, "score": rev["score"]["total"], "review_status": rev["review_status"]}

    def accept(self, run_id: str) -> dict[str, Any]:
        """Manual mode: human clicks «ساخت پیش‌نویس» → promote the assembled artifact to a draft version (+ score/review)."""
        run = self.get_run(run_id)
        if not run or run["status"] != "succeeded":
            raise ValueError("run not finished")
        if run.get("draft_id"):
            return {"draft_id": run["draft_id"], "already": True}
        asm = next((a for a in run["artifacts"] if a["step"] == "assembly"), None)
        seo = next((a["payload"] for a in run["artifacts"] if a["step"] == "seo"), {})
        if not asm:
            raise ValueError("no assembled article in this run")
        return self._promote(run_id, run["site_id"], run["content_id"], asm["payload"]["markdown"], asm["payload"]["h1"], seo, run["models"], run["prompt_versions"], run["memory_snapshot_id"])

    def cancel(self, run_id: str) -> dict | None:
        self._update(run_id, status="cancelled"); self._emit(run_id, "cancelled"); return self.get_run(run_id)
