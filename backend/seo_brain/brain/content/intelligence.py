"""ContentIntelligenceService — drafts (versioned), scoring, review (rules + advisory AI), gate, insights → Site Brain memory."""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlparse

from sqlalchemy import Engine, and_, select, text

from ...ai import AIOrchestrator
from ...ai.memory import MemoryService
from ...brain.keywords import KeywordsRepository
from ...db.repositories.base import dumps, loads, utcnow
from ...db.repositories.memory import SiteMemoryRepository
from ...db.tables import content_insights, content_reviews, content_scores
from ...normalizer.url import normalize_url
from .drafts import Draft, DraftRepository, diff_summary
from .repository import ContentRepository, WorkflowError
from .review import ReviewFinding, ai_review, counts, review_status, rules_review
from .scoring import ContentScore, score_draft


class ContentIntelligenceService:
    def __init__(self, engine: Engine, orchestrator: AIOrchestrator | None = None):
        self.engine = engine
        self.orch = orchestrator
        self.drafts = DraftRepository(engine)
        self.content = ContentRepository(engine)
        self.kw = KeywordsRepository(engine)
        self.memory = SiteMemoryRepository(engine)

    # ------------------------------------------------------------ drafts
    def create_draft(self, site_id: str, cid: int, body: str, fmt: str = "markdown", title: str | None = None, meta_description: str | None = None,
                     source: str = "user", author: str | None = None, change_summary: str | None = None, provenance: dict | None = None) -> Draft:
        item = self.content.get(site_id, cid)
        if not item:
            raise KeyError(cid)
        prev = self.drafts.latest(site_id, cid)
        d = Draft(site_id=site_id, content_id=cid, body=body, format=fmt, title=title or item.title, meta_description=meta_description or (item.metadata or {}).get("meta_description"),
                  source=source, author=author, provenance=provenance or {}, change_summary=change_summary)
        saved = self.drafts.create(d)
        if not saved.change_summary:
            saved.change_summary = diff_summary(prev, saved)
            with self.engine.begin() as cx:
                cx.execute(text("UPDATE content_drafts SET change_summary=:c WHERE id=:i"), {"c": saved.change_summary, "i": saved.id})
        self.content.add_note(site_id, cid, f"draft v{saved.version} ({source}): {saved.change_summary}", actor=author or ("system" if source.startswith("ai:") else "user"))
        return saved

    # ------------------------------------------------------------ context
    def _context(self, site_id: str, cid: int) -> dict[str, Any]:
        item = self.content.get(site_id, cid)
        brief = self.content.get_brief(site_id, item.brief_id).to_dict() if item and item.brief_id else None
        keyword = None; siblings: list[str] = []
        if item and item.target_keyword_id:
            k = self.kw.get(site_id, item.target_keyword_id)
            if k:
                keyword = k.to_dict()
                if k.cluster_id:
                    rows, _ = self.kw.list(site_id, cluster_id=k.cluster_id, limit=50)
                    siblings = [r.keyword for r in rows if r.id != k.id]
        mem = self.memory.get(site_id).to_dict()
        with self.engine.connect() as cx:
            r = cx.execute(text("SELECT canonical_url FROM sites WHERE site_id=:s"), {"s": site_id}).first()
            host = (urlparse(r[0]).hostname or "").replace("www.", "") if r else None
            hubs = {self._n(unquote(u)) for (u,) in cx.execute(text("SELECT url FROM graph_nodes WHERE site_id=:s AND node_type IN ('PAGE','CATEGORY') AND url IS NOT NULL ORDER BY pagerank DESC LIMIT 15"), {"s": site_id}).all()}
            props = {}
            try:
                import json
                for u, p in cx.execute(text("SELECT url, props FROM graph_nodes WHERE site_id=:s AND node_type IN ('PAGE','POST','CATEGORY') AND url IS NOT NULL"), {"s": site_id}).all():
                    pp = json.loads(p or "{}"); props[self._n(unquote(u))] = {"indexable": pp.get("indexable"), "status_code": pp.get("status_code"), "indexability_reason": pp.get("indexability_reason")}
            except Exception:  # noqa: BLE001
                pass
        return {"item": item, "brief": brief, "keyword": keyword, "siblings": siblings, "memory": mem, "host": host, "hubs": hubs, "page_props": props,
                "settings": self.drafts.settings(site_id, "scoring")}

    @staticmethod
    def _n(u: str) -> str:
        return (u or "").strip().lower().rstrip("/").replace("https://", "").replace("http://", "").replace("www.", "")

    # ------------------------------------------------------------ score
    def score(self, site_id: str, cid: int, draft_id: int | None = None) -> dict[str, Any]:
        d = self.drafts.get(site_id, draft_id) if draft_id else self.drafts.latest(site_id, cid)
        if not d:
            raise KeyError("draft")
        ctx = self._context(site_id, cid)
        sc = score_draft(d, ctx["brief"], ctx["keyword"], ctx["siblings"], ctx["memory"], ctx["host"], ctx["hubs"], ctx["settings"])
        with self.engine.begin() as cx:
            res = cx.execute(content_scores.insert().values(site_id=site_id, content_id=cid, draft_id=d.id, total=sc.total, dims=dumps(sc.dims), findings=dumps([f.to_dict() for f in sc.findings]),
                                                            weights=dumps(sc.weights), engine_version=sc.engine_version, created_at=utcnow()))
            sid = int(res.inserted_primary_key[0])
            cx.execute(text("UPDATE content_items SET latest_score=:t, updated_at=:u WHERE id=:i"), {"t": sc.total, "u": utcnow(), "i": cid})
        return {"id": sid, "draft_id": d.id, "version": d.version, **sc.to_dict(), "thresholds": ctx["settings"]["thresholds"]}

    # ------------------------------------------------------------ review
    def review(self, site_id: str, cid: int, draft_id: int | None = None, use_ai: bool = False) -> dict[str, Any]:
        d = self.drafts.get(site_id, draft_id) if draft_id else self.drafts.latest(site_id, cid)
        if not d:
            raise KeyError("draft")
        ctx = self._context(site_id, cid)
        sc = score_draft(d, ctx["brief"], ctx["keyword"], ctx["siblings"], ctx["memory"], ctx["host"], ctx["hubs"], ctx["settings"])
        rules = rules_review(d, ctx["brief"], sc, ctx["page_props"])
        ai_f: list[ReviewFinding] = []; ai_prov: dict[str, Any] = {}; summary = None
        if use_ai and self.orch is not None:
            ai_f, ai_prov, summary = ai_review(self.orch, site_id, d, ctx["brief"], rules)
        allf = rules + ai_f
        status = review_status(sc, allf, ctx["settings"]["thresholds"]["ready"])
        with self.engine.begin() as cx:
            cx.execute(content_scores.insert().values(site_id=site_id, content_id=cid, draft_id=d.id, total=sc.total, dims=dumps(sc.dims), findings=dumps([f.to_dict() for f in sc.findings]),
                                                      weights=dumps(sc.weights), engine_version=sc.engine_version, created_at=utcnow()))
            rid = int(cx.execute(content_reviews.insert().values(site_id=site_id, content_id=cid, draft_id=d.id, kind="rules+ai" if ai_prov.get("ai_used") else "rules",
                                                                findings=dumps([f.to_dict() for f in allf]), summary_fa=summary or self._summary(sc, allf), counts=dumps(counts(allf)),
                                                                provenance=dumps({"engine": "review-v1", **ai_prov}), created_at=utcnow())).inserted_primary_key[0])
        self.drafts.set_review_status(site_id, d.id, status, sc.total)
        self.content.add_note(site_id, cid, f"review v{d.version}: {status} · score {sc.total} · {counts(allf)}", actor="system")
        return {"id": rid, "draft_id": d.id, "version": d.version, "review_status": status, "score": sc.to_dict(), "findings": [f.to_dict() for f in allf], "counts": counts(allf),
                "summary_fa": summary or self._summary(sc, allf), "provenance": {"engine": "review-v1", **ai_prov}, "gate": ctx["settings"].get("review_gate", "strict")}

    @staticmethod
    def _summary(sc: ContentScore, fs: list[ReviewFinding]) -> str:
        c = counts(fs)
        return f"امتیاز {sc.total} ({sc.label}) — {c['high']} یافته مهم، {c['medium']} متوسط، {c['low']} جزئی"

    def history(self, site_id: str, cid: int) -> dict[str, Any]:
        with self.engine.connect() as cx:
            scores = [dict(r._mapping) for r in cx.execute(select(content_scores).where(and_(content_scores.c.site_id == site_id, content_scores.c.content_id == cid)).order_by(content_scores.c.id.desc()).limit(50))]
            reviews = [dict(r._mapping) for r in cx.execute(select(content_reviews).where(and_(content_reviews.c.site_id == site_id, content_reviews.c.content_id == cid)).order_by(content_reviews.c.id.desc()).limit(50))]
        for s in scores:
            s["dims"] = loads(s["dims"], {}); s["findings"] = loads(s["findings"], []); s["weights"] = loads(s["weights"], {})
        for r in reviews:
            r["findings"] = loads(r["findings"], []); r["counts"] = loads(r["counts"], {}); r["provenance"] = loads(r["provenance"], {})
        return {"drafts": [d.to_dict(with_body=False) for d in self.drafts.list(site_id, cid)], "scores": scores, "reviews": reviews}

    # ------------------------------------------------------------ gate (called by the workflow)
    def check_gate(self, site_id: str, cid: int, to_status: str) -> None:
        """Strict gate: review → approved requires latest draft review_status == ready. Advisory: no block."""
        if to_status != "approved":
            return
        gate = self.drafts.settings(site_id, "scoring").get("review_gate", "strict")
        d = self.drafts.latest(site_id, cid)
        if gate == "strict":
            if not d:
                raise WorkflowError("پیش‌نویسی ثبت نشده — برای تأیید، پیش‌نویس را ثبت و بازبینی کنید (حالت سخت‌گیرانه)")
            if d.review_status != "ready":
                raise WorkflowError(f"آخرین پیش‌نویس (v{d.version}) هنوز «آماده» نیست ({d.review_status or 'بازبینی نشده'}) — بازبینی را اجرا و یافته‌های مهم را برطرف کنید")

    # ------------------------------------------------------------ insights → Site Brain memory (human confirmed)
    def list_insights(self, site_id: str, status: str | None = None) -> list[dict[str, Any]]:
        conds = [content_insights.c.site_id == site_id]
        if status:
            conds.append(content_insights.c.status == status)
        with self.engine.connect() as cx:
            rows = [dict(r._mapping) for r in cx.execute(select(content_insights).where(and_(*conds)).order_by(content_insights.c.effect.desc()))]
        for r in rows:
            r["evidence"] = loads(r["evidence"], {})
        return rows

    def set_insight_status(self, site_id: str, iid: int, status: str) -> dict[str, Any] | None:
        if status not in ("new", "accepted", "dismissed"):
            raise ValueError("bad status")
        with self.engine.connect() as cx:
            r = cx.execute(select(content_insights).where(and_(content_insights.c.site_id == site_id, content_insights.c.id == iid))).first()
        if not r:
            return None
        m = dict(r._mapping)
        ref = m.get("memory_pattern_ref")
        if status == "accepted" and not ref:
            ref = f"insight:{iid}"
            self.memory.add_pattern(site_id, pattern=m["message_fa"], evidence=f"{m['metric']} effect {m['effect']:+.3f} vs baseline {m['baseline']} · n={m['n']} · {m['impressions']} imp · {m['clicks']} clk",
                                    source="content_analytics", run_id=ref)
        with self.engine.begin() as cx:
            cx.execute(content_insights.update().where(content_insights.c.id == iid).values(status=status, memory_pattern_ref=ref if status == "accepted" else m.get("memory_pattern_ref"), updated_at=utcnow()))
        return next((x for x in self.list_insights(site_id) if x["id"] == iid), None)
