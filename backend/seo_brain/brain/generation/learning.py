"""AI performance learning — which model / prompt / structure produced better content. Recommendation only.

Signals: generation_runs (models, prompt_versions, score, review_status, actual cost), draft_feedback (rating, tags),
content_scores/reviews (revision loops), Phase-7 content analytics when published (via content_id).
Gates: n ≥ min_n per group (default 5) — no insights from small samples. Accepting an insight writes a Site Brain pattern
and/or marks a route recommendation; routing itself is only changed by a human in AI Models.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import Engine, and_, select, text

from ...db.repositories.base import dumps, loads, utcnow
from ...db.repositories.memory import SiteMemoryRepository
from ...db.tables import ai_insights, draft_feedback, generation_runs

FEEDBACK_TAGS = ("good_structure", "weak_intro", "wrong_intent", "too_generic", "excellent_entities", "good_links")
TAG_FA = {"good_structure": "ساختار خوب", "weak_intro": "مقدمه ضعیف", "wrong_intent": "اینتنت اشتباه", "too_generic": "خیلی کلی", "excellent_entities": "پوشش عالی موجودیت‌ها", "good_links": "لینک‌های خوب"}


class AILearning:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.memory = SiteMemoryRepository(engine)

    # ---- feedback
    def add_feedback(self, site_id: str, rating: int, tags: list[str] | None = None, content_id: int | None = None, draft_id: int | None = None, run_id: str | None = None, notes: str | None = None, created_by: str | None = None) -> dict:
        if not 1 <= int(rating) <= 5:
            raise ValueError("rating must be 1–5")
        tags = [t for t in (tags or []) if t in FEEDBACK_TAGS]
        with self.engine.begin() as cx:
            fid = int(cx.execute(draft_feedback.insert().values(site_id=site_id, content_id=content_id, draft_id=draft_id, run_id=run_id, rating=int(rating), tags=dumps(tags), notes=notes, created_by=created_by, created_at=utcnow())).inserted_primary_key[0])
            r = cx.execute(select(draft_feedback).where(draft_feedback.c.id == fid)).first()
        d = dict(r._mapping); d["tags"] = loads(d["tags"], []); d["tags_fa"] = [TAG_FA[t] for t in d["tags"]]; return d

    def feedback(self, site_id: str, content_id: int | None = None, run_id: str | None = None) -> list[dict]:
        conds = [draft_feedback.c.site_id == site_id]
        if content_id: conds.append(draft_feedback.c.content_id == content_id)
        if run_id: conds.append(draft_feedback.c.run_id == run_id)
        with self.engine.connect() as cx:
            rows = [dict(r._mapping) for r in cx.execute(select(draft_feedback).where(and_(*conds)).order_by(draft_feedback.c.id.desc())).all()]
        for d in rows:
            d["tags"] = loads(d["tags"], []); d["tags_fa"] = [TAG_FA.get(t, t) for t in d["tags"]]
        return rows

    # ---- learn
    def learn(self, site_id: str | None = None, min_n: int = 5) -> dict[str, Any]:
        conds = [generation_runs.c.status == "succeeded"]
        if site_id: conds.append(generation_runs.c.site_id == site_id)
        with self.engine.connect() as cx:
            runs = [dict(r._mapping) for r in cx.execute(select(generation_runs).where(and_(*conds))).all()]
            fb = [dict(r._mapping) for r in cx.execute(select(draft_feedback).where(draft_feedback.c.site_id == site_id) if site_id else select(draft_feedback)).all()]
        rating_by_run: dict[str, list[int]] = defaultdict(list)
        for f in fb:
            if f.get("run_id"): rating_by_run[f["run_id"]].append(int(f["rating"]))
        samples = []
        for r in runs:
            models = loads(r["models"], {}); pv = loads(r["prompt_versions"], {}); actual = loads(r["actual"], {})
            writer = models.get("writer") or {}
            if not writer.get("model") or r.get("score") is None:
                continue
            steps = loads(r["steps"], [])
            n_sections = sum(1 for s in steps if str(s.get("key", "")).startswith("section:"))
            samples.append({"run_id": r["run_id"], "model": f"{writer.get('provider')}/{writer.get('model')}", "prompt_writer": str(pv.get("writer") or "-"), "score": float(r["score"]), "cost": float(actual.get("cost_usd") or 0),
                            "rating": (sum(rating_by_run[r["run_id"]]) / len(rating_by_run[r["run_id"]])) if rating_by_run.get(r["run_id"]) else None, "ready": r.get("review_status") == "ready",
                            "sections_band": "4-5" if n_sections <= 5 else ("6-7" if n_sections <= 7 else "8+")})
        produced = []
        if len(samples) >= min_n:
            base_score = sum(s["score"] for s in samples) / len(samples)
            base_cost = sum(s["cost"] for s in samples) / len(samples)
            for feat, cat in (("model", "model"), ("prompt_writer", "prompt"), ("sections_band", "structure")):
                groups: dict[str, list[dict]] = defaultdict(list)
                for s in samples: groups[s[feat]].append(s)
                for val, grp in groups.items():
                    if len(grp) < min_n:
                        continue
                    sc = sum(g["score"] for g in grp) / len(grp); cost = sum(g["cost"] for g in grp) / len(grp)
                    ready = sum(1 for g in grp if g["ready"]) / len(grp)
                    rats = [g["rating"] for g in grp if g["rating"] is not None]
                    eff = round(sc - base_score, 2)
                    if abs(eff) >= 3:
                        rec = {}
                        if cat == "model" and eff > 0:
                            prov, mdl = val.split("/", 1); rec = {"task_kind": "article_section", "provider": prov, "model": mdl, "note": "پیشنهاد مسیر — اعمال فقط با تأیید انسانی در «مدل‌های AI»"}
                        msg = f"{'مدل' if cat == 'model' else ('پرامپت نگارش' if cat == 'prompt' else 'تعداد بخش')} «{val}»: امتیاز میانگین {sc:.1f} در برابر {base_score:.1f} (n={len(grp)}؛ هزینه میانگین {cost:.3f}$؛ {ready:.0%} آماده" + (f"؛ امتیاز کاربر {sum(rats)/len(rats):.1f}/5" if rats else "") + ")"
                        produced.append(self._upsert(site_id, cat, feat, val, "score", eff, round(base_score, 2), len(grp), msg, {"runs": [g["run_id"] for g in grp][:30], "avg_cost": cost, "ready_rate": ready}, rec))
                    ceff = round(base_cost - cost, 4)
                    if base_cost and abs(ceff) / base_cost >= 0.25 and cat == "model":
                        msg = f"مدل «{val}» به‌طور میانگین {abs(ceff):.3f}$ {'ارزان‌تر' if ceff > 0 else 'گران‌تر'} از میانگین است (n={len(grp)}؛ امتیاز {sc:.1f})"
                        produced.append(self._upsert(site_id, cat, feat, val, "cost", ceff, round(base_cost, 4), len(grp), msg, {"runs": [g["run_id"] for g in grp][:30]}, {}))
        return {"samples": len(samples), "min_n": min_n, "insights": produced}

    def _upsert(self, site_id: str | None, category: str, feature: str, value: str, metric: str, effect: float, baseline: float, n: int, msg: str, evidence: dict, rec: dict) -> dict:
        now = utcnow()
        with self.engine.begin() as cx:
            cx.execute(text("INSERT INTO ai_insights(site_id,category,feature,value,metric,effect,baseline,n,confidence,message_fa,evidence,recommendation,status,created_at,updated_at) "
                            "VALUES(:s,:c,:f,:v,:m,:e,:b,:n,:cf,:msg,:ev,:rec,'new',:t,:t) ON CONFLICT(site_id,category,feature,value,metric) DO UPDATE SET effect=excluded.effect, baseline=excluded.baseline, n=excluded.n, "
                            "confidence=excluded.confidence, message_fa=excluded.message_fa, evidence=excluded.evidence, recommendation=excluded.recommendation, updated_at=excluded.updated_at"),
                       {"s": site_id, "c": category, "f": feature, "v": value, "m": metric, "e": effect, "b": baseline, "n": n, "cf": round(min(1.0, n / 20), 2), "msg": msg, "ev": dumps(evidence), "rec": dumps(rec), "t": now})
        return next(i for i in self.insights(site_id) if i["category"] == category and i["feature"] == feature and i["value"] == value and i["metric"] == metric)

    def insights(self, site_id: str | None = None, status: str | None = None) -> list[dict]:
        conds = []
        if site_id: conds.append(ai_insights.c.site_id == site_id)
        if status: conds.append(ai_insights.c.status == status)
        with self.engine.connect() as cx:
            rows = [dict(r._mapping) for r in cx.execute(select(ai_insights).where(and_(*conds)) if conds else select(ai_insights)).all()]
        for d in rows:
            d["evidence"] = loads(d["evidence"], {}); d["recommendation"] = loads(d["recommendation"], {})
        return sorted(rows, key=lambda d: -abs(d["effect"]))

    def set_status(self, iid: int, status: str) -> dict | None:
        ins = next((i for i in self.insights() if i["id"] == iid), None)
        if not ins:
            return None
        ref = ins.get("memory_pattern_ref")
        if status == "accepted" and not ref and ins.get("site_id"):
            ref = f"aiinsight:{iid}"
            self.memory.add_pattern(ins["site_id"], pattern=ins["message_fa"], evidence=f"{ins['metric']} effect {ins['effect']} vs {ins['baseline']} · n={ins['n']}", source="ai_performance", run_id=ref)
        with self.engine.begin() as cx:
            cx.execute(ai_insights.update().where(ai_insights.c.id == iid).values(status=status, memory_pattern_ref=ref if status == "accepted" else ins.get("memory_pattern_ref"), updated_at=utcnow()))
        return next((i for i in self.insights() if i["id"] == iid), None)
