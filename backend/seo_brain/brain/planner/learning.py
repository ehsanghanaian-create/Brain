"""Planner learning (human-gated): plan-level features (page type, category, funnel stage, title has location, FAQ, ≥5 links, headings)
× Phase-7 content metrics (GSC ≥ thresholds) → content_insights (category `planner`) → human accept → site_memory.successful_patterns
(source `content_planner`). Never changes rules or weights automatically."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import Engine, and_, select, text

from ...brain.content.analytics import ContentAnalytics
from ...brain.content.drafts import DraftRepository
from ...brain.keywords.normalize import normalize_keyword
from ...db.repositories.base import dumps, loads, utcnow
from ...db.repositories.memory import SiteMemoryRepository
from ...db.tables import content_insights
from .context import LOCAL_WORDS
from .repository import PAGE_TYPE_FA, PlannerRepository, FUNNEL_FA

FEATURES = {"page_type": "نوع صفحه", "funnel_stage": "مرحله قیف", "category": "دسته", "title_has_location": "مکان در عنوان", "has_faq": "بخش FAQ", "links_5plus": "≥۵ لینک داخلی", "headings_5plus": "≥۵ سرفصل H2", "intent": "اینتنت"}


class PlannerLearning:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.repo = PlannerRepository(engine)
        self.analytics = ContentAnalytics(engine)
        self.memory = SiteMemoryRepository(engine)

    def features(self, site_id: str, p, draft_struct: dict | None) -> dict[str, str]:
        t = normalize_keyword(p.seo_title or p.title or "")
        st = draft_struct or {}
        cats = {c["id"]: c["name"] for c in self.repo.list_categories(site_id)}
        return {"page_type": PAGE_TYPE_FA.get(p.page_type or "", p.page_type or "—"), "funnel_stage": FUNNEL_FA.get(p.funnel_stage or "", p.funnel_stage or "—"), "category": cats.get(p.category_id, "—"),
                "title_has_location": "بله" if any(w in t for w in LOCAL_WORDS) else "خیر", "has_faq": "بله" if st.get("faq") else "خیر",
                "links_5plus": "بله" if len(st.get("links", [])) >= 5 else "خیر", "headings_5plus": "بله" if len(st.get("h2", [])) >= 5 else "خیر", "intent": p.intent or "—"}

    def learn(self, site_id: str, today: date | None = None, min_n: int = 5) -> dict[str, Any]:
        today = today or date.today()
        cfg = self.analytics.settings.settings(site_id, "analytics")
        min_imp, min_clicks, min_age = int(cfg["min_impressions"]), int(cfg["min_clicks"]), int(cfg["min_age_days"])
        latest: dict[int, dict] = {}
        for r in self.analytics.metrics(site_id, None, "28d", 2000):
            latest.setdefault(r["content_id"], r)
        plans = {p.content_item_id: p for p in self.repo.all_plans(site_id) if p.content_item_id}
        drafts = DraftRepository(self.engine)
        samples = []
        skipped = {"young": 0, "no_plan": 0}
        for cid, m in latest.items():
            p = plans.get(cid)
            if not p:
                skipped["no_plan"] += 1; continue
            base_date = p.publish_date or (p.created_at or "")[:10]
            try:
                age = (today - date.fromisoformat(base_date)).days if base_date else 0
            except ValueError:
                age = 0
            if age < min_age:
                skipped["young"] += 1; continue
            with self.engine.connect() as cx:
                dr = cx.execute(text("SELECT structure FROM content_drafts WHERE site_id=:s AND content_id=:c ORDER BY version DESC LIMIT 1"), {"s": site_id, "c": cid}).first()
            samples.append({"cid": cid, "plan_id": p.id, "f": self.features(site_id, p, loads(dr[0], {}) if dr else None), "ctr": m["ctr"], "position": m["position"], "clicks": m["clicks"], "impressions": m["impressions"]})
        produced = []
        if samples:
            base_ctr = sum(s["ctr"] * s["impressions"] for s in samples) / max(1, sum(s["impressions"] for s in samples))
            for feat in FEATURES:
                groups: dict[str, list[dict]] = defaultdict(list)
                for s in samples:
                    groups[s["f"][feat]].append(s)
                for val, grp in groups.items():
                    n = len(grp); imp = sum(s["impressions"] for s in grp); clk = sum(s["clicks"] for s in grp)
                    if n < min_n or imp < min_imp or clk < min_clicks:
                        continue
                    ctr = clk / imp if imp else 0.0
                    eff = round(ctr - base_ctr, 4)
                    if base_ctr > 0 and abs(eff) >= 0.15 * base_ctr:
                        produced.append(self._upsert(site_id, feat, val, eff, round(base_ctr, 4), n, imp, clk, grp))
        return {"date": today.isoformat(), "samples": len(samples), "skipped": skipped, "gates": {"min_n": min_n, "min_impressions": min_imp, "min_clicks": min_clicks, "min_age_days": min_age}, "insights": produced}

    def _upsert(self, site_id: str, feat: str, val: str, effect: float, baseline: float, n: int, imp: int, clk: int, grp: list[dict]) -> dict[str, Any]:
        direction = "بهتر" if effect > 0 else "بدتر"
        msg = f"برنامه‌های محتوایی با «{FEATURES[feat]} = {val}» CTR {direction}ی دارند: {(baseline + effect) * 100:.1f}٪ در برابر {baseline * 100:.1f}٪ (n={n}, {imp} ایمپرشن)"
        conf = round(min(1.0, (n / 20) * 0.5 + min(1.0, imp / 10000) * 0.5), 2)
        now = utcnow()
        with self.engine.begin() as cx:
            cx.execute(text("INSERT INTO content_insights(site_id,category,feature,value,metric,effect,baseline,n,impressions,clicks,confidence,message_fa,evidence,status,created_at,updated_at) "
                            "VALUES(:s,'planner',:f,:v,'ctr',:e,:b,:n,:i,:k,:cf,:msg,:ev,'new',:t,:t) ON CONFLICT(site_id,category,feature,value,metric) DO UPDATE SET effect=excluded.effect, baseline=excluded.baseline, "
                            "n=excluded.n, impressions=excluded.impressions, clicks=excluded.clicks, confidence=excluded.confidence, message_fa=excluded.message_fa, evidence=excluded.evidence, updated_at=excluded.updated_at"),
                       {"s": site_id, "f": feat, "v": val, "e": effect, "b": baseline, "n": n, "i": imp, "k": clk, "cf": conf, "msg": msg, "ev": dumps({"plan_ids": [s["plan_id"] for s in grp][:50], "n": n, "impressions": imp, "clicks": clk}), "t": now})
            r = cx.execute(select(content_insights).where(and_(content_insights.c.site_id == site_id, content_insights.c.category == "planner", content_insights.c.feature == feat, content_insights.c.value == val, content_insights.c.metric == "ctr"))).first()
        d = dict(r._mapping); d["evidence"] = loads(d["evidence"], {})
        return d

    def list(self, site_id: str, status: str | None = None) -> list[dict[str, Any]]:
        conds = [content_insights.c.site_id == site_id, content_insights.c.category == "planner"]
        if status:
            conds.append(content_insights.c.status == status)
        with self.engine.connect() as cx:
            rows = [dict(r._mapping) for r in cx.execute(select(content_insights).where(and_(*conds)).order_by(content_insights.c.effect.desc()))]
        for r in rows:
            r["evidence"] = loads(r["evidence"], {})
        return rows

    def set_status(self, site_id: str, iid: int, status: str) -> dict[str, Any] | None:
        if status not in ("new", "accepted", "dismissed"):
            raise ValueError("bad status")
        with self.engine.connect() as cx:
            r = cx.execute(select(content_insights).where(and_(content_insights.c.site_id == site_id, content_insights.c.id == iid, content_insights.c.category == "planner"))).first()
        if not r:
            return None
        m = dict(r._mapping); ref = m.get("memory_pattern_ref")
        if status == "accepted" and not ref:
            ref = f"planner-insight:{iid}"
            self.memory.add_pattern(site_id, pattern=m["message_fa"], evidence=f"ctr effect {m['effect']:+.3f} vs {m['baseline']} · n={m['n']} · {m['impressions']} imp", source="content_planner", run_id=ref)
        with self.engine.begin() as cx:
            cx.execute(content_insights.update().where(content_insights.c.id == iid).values(status=status, memory_pattern_ref=ref if status == "accepted" else m.get("memory_pattern_ref"), updated_at=utcnow()))
        d = {**m, "status": status, "memory_pattern_ref": ref if status == "accepted" else m.get("memory_pattern_ref")}; d["evidence"] = loads(d["evidence"], {})
        return d
