"""Content Analytics Feedback — learn which content patterns work, from GSC only, with conservative gates.

snapshot(): for every content item with a URL: 7d/28d clicks/impressions/CTR/position from gsc_daily (fallback: gsc_query_page
aggregate) + top queries → content_metrics, with deltas vs. the previous snapshot.
learn(): features per content (title pattern, H2 count band, FAQ, entity count band, CTA/phone in first paragraph, location in
title, word-count band, internal links band, intent) × 28d metrics → per feature-value effect vs. baseline. An insight is only
emitted when the sample passes ALL gates: n ≥ min_n, impressions ≥ 1000, clicks ≥ 30, content age ≥ 28 days. Nothing changes
scoring weights; accepted insights go to Site Brain memory (see ContentIntelligenceService.set_insight_status).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import unquote

from sqlalchemy import Engine, and_, select, text

from ...db.repositories.base import dumps, loads, utcnow
from ...db.tables import content_drafts, content_insights, content_items, content_metrics
from ...normalizer.url import normalize_url
from .drafts import DEFAULT_ANALYTICS, DraftRepository

_LOC = re.compile(r"تهران|کرج|اصفهان|شیراز|مشهد|تبریز|قم|اهواز|رشت")
_PHONE = re.compile(r"(?:\+98|0|۰)[\d۰-۹][\d۰-۹\s\-]{8,12}")
FEATURE_FA = {
    "title_pattern": "الگوی عنوان", "h2_band": "تعداد H2", "faq": "بخش FAQ", "entity_band": "پوشش موجودیت‌ها", "cta_first_paragraph": "CTA در پاراگراف اول",
    "location_in_title": "مکان در عنوان (سئوی محلی)", "words_band": "طول محتوا", "links_band": "لینک‌های داخلی", "intent": "اینتنت",
}
CATEGORY_OF = {"title_pattern": "title", "h2_band": "heading_structure", "faq": "faq", "entity_band": "entity_coverage", "cta_first_paragraph": "cta",
               "location_in_title": "local_seo", "words_band": "length", "links_band": "heading_structure", "intent": "title"}


class ContentAnalytics:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.settings = DraftRepository(engine)

    # ------------------------------------------------------------ snapshots
    def snapshot(self, site_id: str, today: date | None = None) -> dict[str, Any]:
        today = today or date.today()
        cfg = self.settings.settings(site_id, "analytics")
        with self.engine.connect() as cx:
            items = [dict(r._mapping) for r in cx.execute(select(content_items).where(and_(content_items.c.site_id == site_id, content_items.c.url.isnot(None), content_items.c.url != "")))]
            has_daily = cx.execute(text("SELECT count(*) FROM gsc_daily WHERE site_id=:s"), {"s": site_id}).scalar() or 0
        written = 0
        for it in items:
            url_n = normalize_url(it["url"])
            for win in cfg.get("windows", ["7d", "28d"]):
                days = int(win.rstrip("d"))
                start = (today - timedelta(days=days)).isoformat()
                m = self._metrics_for(site_id, url_n, start, today.isoformat(), bool(has_daily))
                ga = self._ga4_for(site_id, it["url"], start, today.isoformat())
                if m is None and ga is None:
                    continue
                m = m or {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": None, "top_queries": []}
                prev = self._prev(site_id, it["id"], win, today.isoformat())
                delta = {}
                if prev:
                    delta = {"clicks": m["clicks"] - prev["clicks"], "impressions": m["impressions"] - prev["impressions"], "ctr": round(m["ctr"] - prev["ctr"], 4),
                             "position": round((m["position"] or 0) - (prev["position"] or 0), 2) if m["position"] is not None and prev["position"] is not None else None, "prev_date": prev["date"]}
                with self.engine.begin() as cx:
                    cx.execute(text("INSERT INTO content_metrics(site_id,content_id,url,window,date,clicks,impressions,ctr,position,top_queries,delta,created_at,"
                                    "ga4_sessions,ga4_users,ga4_views,ga4_conversions,ga4_engagement_rate) "
                                    "VALUES(:s,:c,:u,:w,:d,:cl,:im,:ct,:po,:tq,:de,:ca,:gs,:gu,:gv,:gc,:ge) ON CONFLICT(site_id,content_id,window,date) DO UPDATE SET clicks=excluded.clicks, impressions=excluded.impressions, "
                                    "ctr=excluded.ctr, position=excluded.position, top_queries=excluded.top_queries, delta=excluded.delta, "
                                    "ga4_sessions=excluded.ga4_sessions, ga4_users=excluded.ga4_users, ga4_views=excluded.ga4_views, ga4_conversions=excluded.ga4_conversions, ga4_engagement_rate=excluded.ga4_engagement_rate"),
                               {"s": site_id, "c": it["id"], "u": it["url"], "w": win, "d": today.isoformat(), "cl": m["clicks"], "im": m["impressions"], "ct": m["ctr"], "po": m["position"],
                                "tq": dumps(m["top_queries"]), "de": dumps(delta), "ca": utcnow(),
                                "gs": ga and ga["sessions"], "gu": ga and ga["users"], "gv": ga and ga["views"],
                                "gc": ga and ga["conversions"], "ge": ga and ga["engagement_rate"]})
                written += 1
        with self.engine.connect() as cx:
            has_ga4 = cx.execute(text("SELECT count(*) FROM ga4_daily WHERE site_id=:s"), {"s": site_id}).scalar() or 0
        return {"date": today.isoformat(), "items": len(items), "snapshots": written,
                "source": ("gsc_daily" if has_daily else "gsc_query_page") + ("+ga4_daily" if has_ga4 else "")}

    def _metrics_for(self, site_id: str, url_n: str, start: str, end: str, daily: bool) -> dict[str, Any] | None:
        with self.engine.connect() as cx:
            if daily:
                rows = cx.execute(text("SELECT page, query, clicks, impressions, position FROM gsc_daily WHERE site_id=:s AND date>=:a AND date<=:b"), {"s": site_id, "a": start, "b": end}).all()
            else:
                rows = cx.execute(text("SELECT page, query, clicks, impressions, position FROM gsc_query_page WHERE site_id=:s"), {"s": site_id}).all()
        cl = im = 0; posw = 0.0; q: dict[str, int] = defaultdict(int)
        for page, query, c, i, p in rows:
            if normalize_url(unquote(page or "")) != url_n:
                continue
            cl += c or 0; im += i or 0; posw += (p or 0) * (i or 0); q[query] += i or 0
        if im == 0 and cl == 0:
            return None
        top = sorted(q.items(), key=lambda x: -x[1])[:10]
        return {"clicks": cl, "impressions": im, "ctr": round(cl / im, 4) if im else 0.0, "position": round(posw / im, 2) if im else None, "top_queries": [{"query": k, "impressions": v} for k, v in top]}

    def _ga4_for(self, site_id: str, url: str, start: str, end: str) -> dict | None:
        """GA4 window aggregate for one content URL (path match on existing ga4_daily; engagement weighted by sessions)."""
        from urllib.parse import urlsplit
        path = unquote(urlsplit(url).path or "/").rstrip("/") or "/"
        try:
            with self.engine.connect() as cx:
                r = cx.execute(text("SELECT SUM(sessions), SUM(total_users), SUM(screen_page_views), SUM(conversions), "
                                    "CASE WHEN SUM(sessions)>0 THEN SUM(engagement_rate*sessions)/SUM(sessions) END "
                                    "FROM ga4_daily WHERE site_id=:s AND source='page' AND date>=:a AND date<=:b "
                                    "AND (RTRIM(page_path,'/')=:p OR page_path=:p2)"),
                               {"s": site_id, "a": start, "b": end, "p": path, "p2": path + "/" if path != "/" else "/"}).first()
        except Exception:  # noqa: BLE001 — pre-0010 DB in old fixtures
            return None
        if not r or not r[0]:
            return None
        return {"sessions": int(r[0] or 0), "users": int(r[1] or 0), "views": int(r[2] or 0),
                "conversions": round(float(r[3] or 0), 1), "engagement_rate": round(float(r[4]), 3) if r[4] is not None else None}

    def _prev(self, site_id: str, cid: int, win: str, before: str) -> dict | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(content_metrics).where(and_(content_metrics.c.site_id == site_id, content_metrics.c.content_id == cid, content_metrics.c.window == win, content_metrics.c.date < before)).order_by(content_metrics.c.date.desc())).first()
        return dict(r._mapping) if r else None

    def metrics(self, site_id: str, cid: int | None = None, window: str = "28d", limit: int = 60) -> list[dict[str, Any]]:
        conds = [content_metrics.c.site_id == site_id, content_metrics.c.window == window]
        if cid:
            conds.append(content_metrics.c.content_id == cid)
        with self.engine.connect() as cx:
            rows = [dict(r._mapping) for r in cx.execute(select(content_metrics).where(and_(*conds)).order_by(content_metrics.c.date.desc(), content_metrics.c.impressions.desc()).limit(limit))]
        for r in rows:
            r["top_queries"] = loads(r["top_queries"], []); r["delta"] = loads(r["delta"], {})
        return rows

    def overview(self, site_id: str) -> dict[str, Any]:
        latest: dict[int, dict] = {}
        for r in self.metrics(site_id, None, "28d", 500):
            latest.setdefault(r["content_id"], r)
        with self.engine.connect() as cx:
            titles = {r[0]: (r[1], r[2], r[3]) for r in cx.execute(text("SELECT id, title, status, publish_date FROM content_items WHERE site_id=:s"), {"s": site_id}).all()}
        rows = []
        for cid, m in latest.items():
            t = titles.get(cid, ("?", "?", None))
            rows.append({"content_id": cid, "title": t[0], "status": t[1], "publish_date": t[2], "url": m["url"], "date": m["date"], "clicks": m["clicks"], "impressions": m["impressions"], "ctr": m["ctr"], "position": m["position"], "delta": m["delta"], "top_queries": m["top_queries"][:5]})
        rows.sort(key=lambda r: -r["impressions"])
        agg = {"contents": len(rows), "clicks": sum(r["clicks"] for r in rows), "impressions": sum(r["impressions"] for r in rows)}
        agg["ctr"] = round(agg["clicks"] / agg["impressions"], 4) if agg["impressions"] else 0.0
        return {"window": "28d", "rows": rows, "totals": agg, "gates": self.settings.settings(site_id, "analytics")}

    # ------------------------------------------------------------ learning
    def features(self, site_id: str, cid: int, title: str | None) -> dict[str, str] | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(content_drafts).where(and_(content_drafts.c.site_id == site_id, content_drafts.c.content_id == cid)).order_by(content_drafts.c.version.desc())).first()
            it = cx.execute(text("SELECT intent, target_keyword, brief_id FROM content_items WHERE id=:i"), {"i": cid}).first()
            ents = 0
            if it and it[2]:
                b = cx.execute(text("SELECT entities FROM content_briefs WHERE id=:i"), {"i": it[2]}).first()
                ents = len(json.loads(b[0] or "[]")) if b else 0
        if not r:
            return None
        st = loads(r._mapping["structure"], {}); t = r._mapping["title"] or title or ""
        paras = st.get("paragraphs", []); first = paras[0] if paras else ""
        h2 = len(st.get("h2", [])); words = int(r._mapping["word_count"] or 0); links = len(st.get("links", []))
        ent_present = 0
        if it and it[2]:
            with self.engine.connect() as cx:
                b = cx.execute(text("SELECT entities FROM content_briefs WHERE id=:i"), {"i": it[2]}).first()
            body = (r._mapping["body_text"] or "").lower()
            ent_present = sum(1 for e in json.loads(b[0] or "[]") if str(e.get("label", "")).lower() in body) if b else 0
        return {
            "title_pattern": "question" if ("؟" in t or "?" in t or any(w in t for w in ("چگونه", "چطور", "چرا", "چیست"))) else ("number" if re.search(r"\d|[۰-۹]", t) else ("brand_first" if it and it[1] and t.strip().startswith(str(it[1]).split()[0]) else "plain")),
            "h2_band": "0-2" if h2 <= 2 else ("3-5" if h2 <= 5 else "6+"),
            "faq": "yes" if st.get("faq") else "no",
            "entity_band": "none" if ents == 0 else ("all" if ent_present >= ents else ("most" if ent_present >= ents / 2 else "few")),
            "cta_first_paragraph": "yes" if (_PHONE.search(first) or "تماس" in first) else "no",
            "location_in_title": "yes" if _LOC.search(t) else "no",
            "words_band": "<500" if words < 500 else ("500-900" if words < 900 else ("900-1500" if words < 1500 else "1500+")),
            "links_band": "0-2" if links <= 2 else ("3-5" if links <= 5 else "6+"),
            "intent": (it[0] if it and it[0] else "unknown"),
        }

    def learn(self, site_id: str, today: date | None = None, min_n: int = 5) -> dict[str, Any]:
        today = today or date.today()
        cfg = self.settings.settings(site_id, "analytics")
        min_imp, min_clicks, min_age = int(cfg["min_impressions"]), int(cfg["min_clicks"]), int(cfg["min_age_days"])
        latest: dict[int, dict] = {}
        for r in self.metrics(site_id, None, "28d", 2000):
            latest.setdefault(r["content_id"], r)
        with self.engine.connect() as cx:
            info = {r[0]: {"title": r[1], "publish_date": r[2], "created_at": r[3]} for r in cx.execute(text("SELECT id, title, publish_date, created_at FROM content_items WHERE site_id=:s"), {"s": site_id}).all()}
        samples = []
        skipped = {"young": 0, "no_features": 0}
        for cid, m in latest.items():
            inf = info.get(cid, {})
            base_date = inf.get("publish_date") or (inf.get("created_at") or "")[:10]
            try:
                age = (today - date.fromisoformat(base_date)).days if base_date else 0
            except ValueError:
                age = 0
            if age < min_age:
                skipped["young"] += 1; continue
            f = self.features(site_id, cid, inf.get("title"))
            if not f:
                skipped["no_features"] += 1; continue
            samples.append({"cid": cid, "f": f, "ctr": m["ctr"], "position": m["position"], "clicks": m["clicks"], "impressions": m["impressions"]})
        produced = []
        if samples:
            base_ctr = sum(s["ctr"] * s["impressions"] for s in samples) / max(1, sum(s["impressions"] for s in samples))
            pos_s = [s for s in samples if s["position"] is not None]
            base_pos = sum(s["position"] * s["impressions"] for s in pos_s) / max(1, sum(s["impressions"] for s in pos_s)) if pos_s else None
            for feat in FEATURE_FA:
                groups: dict[str, list[dict]] = defaultdict(list)
                for s in samples:
                    groups[s["f"][feat]].append(s)
                for val, grp in groups.items():
                    n = len(grp); imp = sum(s["impressions"] for s in grp); clk = sum(s["clicks"] for s in grp)
                    if n < min_n or imp < min_imp or clk < min_clicks:
                        continue
                    ctr = clk / imp if imp else 0.0
                    eff = round(ctr - base_ctr, 4)
                    if abs(eff) >= 0.15 * base_ctr and base_ctr > 0:
                        produced.append(self._upsert_insight(site_id, feat, val, "ctr", eff, round(base_ctr, 4), n, imp, clk, grp))
                    gp = [s for s in grp if s["position"] is not None]
                    if base_pos is not None and gp:
                        gimp = sum(s["impressions"] for s in gp)
                        pos = sum(s["position"] * s["impressions"] for s in gp) / gimp if gimp else None
                        if pos is not None:
                            peff = round(base_pos - pos, 2)      # positive = better (closer to 1)
                            if abs(peff) >= 0.5:
                                produced.append(self._upsert_insight(site_id, feat, val, "position", peff, round(base_pos, 2), n, imp, clk, gp))
        return {"date": today.isoformat(), "samples": len(samples), "skipped": skipped, "gates": {"min_n": min_n, "min_impressions": min_imp, "min_clicks": min_clicks, "min_age_days": min_age},
                "insights": [p for p in produced if p]}

    def _upsert_insight(self, site_id: str, feat: str, val: str, metric: str, effect: float, baseline: float, n: int, imp: int, clk: int, grp: list[dict]) -> dict[str, Any]:
        direction = "بهتر" if effect > 0 else "بدتر"
        if metric == "ctr":
            msg = f"محتواهای با «{FEATURE_FA[feat]} = {val}» CTR {direction}ی دارند: {(baseline + effect) * 100:.1f}٪ در برابر {baseline * 100:.1f}٪ (n={n}, {imp} ایمپرشن)"
        else:
            msg = f"محتواهای با «{FEATURE_FA[feat]} = {val}» جایگاه {direction}ی دارند: {baseline - effect:.1f} در برابر {baseline:.1f} (n={n}, {imp} ایمپرشن)"
        conf = round(min(1.0, (n / 20) * 0.5 + min(1.0, imp / 10000) * 0.5), 2)
        ev = {"content_ids": [s["cid"] for s in grp][:50], "n": n, "impressions": imp, "clicks": clk}
        now = utcnow()
        with self.engine.begin() as cx:
            cx.execute(text("INSERT INTO content_insights(site_id,category,feature,value,metric,effect,baseline,n,impressions,clicks,confidence,message_fa,evidence,status,created_at,updated_at) "
                            "VALUES(:s,:c,:f,:v,:m,:e,:b,:n,:i,:k,:cf,:msg,:ev,'new',:t,:t) ON CONFLICT(site_id,category,feature,value,metric) DO UPDATE SET effect=excluded.effect, baseline=excluded.baseline, "
                            "n=excluded.n, impressions=excluded.impressions, clicks=excluded.clicks, confidence=excluded.confidence, message_fa=excluded.message_fa, evidence=excluded.evidence, updated_at=excluded.updated_at"),
                       {"s": site_id, "c": CATEGORY_OF[feat], "f": feat, "v": val, "m": metric, "e": effect, "b": baseline, "n": n, "i": imp, "k": clk, "cf": conf, "msg": msg, "ev": dumps(ev), "t": now})
            r = cx.execute(select(content_insights).where(and_(content_insights.c.site_id == site_id, content_insights.c.category == CATEGORY_OF[feat], content_insights.c.feature == feat, content_insights.c.value == val, content_insights.c.metric == metric))).first()
        d = dict(r._mapping); d["evidence"] = loads(d["evidence"], {})
        return d
