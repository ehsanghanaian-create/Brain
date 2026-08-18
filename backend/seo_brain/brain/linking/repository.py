from __future__ import annotations

from typing import Any

from sqlalchemy import and_, delete, func, select, text

from ...db.repositories.base import Repository, dumps, loads, utcnow
from ...db.tables import link_page_stats, link_patterns, link_suggestions

STATUSES = ("new", "accepted", "dismissed", "done")
KINDS = ("contextual", "orphan_rescue", "hub_spoke", "supports", "anchor_fix", "content_outbound")
KIND_FA = {"contextual": "لینک متنی", "orphan_rescue": "نجات صفحه یتیم", "hub_spoke": "هاب → زیرمجموعه", "supports": "محتوای پشتیبان", "anchor_fix": "اصلاح انکر", "content_outbound": "لینک از محتوای برنامه‌ریزی‌شده"}
CONF_FA = {"low": "اطمینان کم", "recommended": "توصیه‌شده", "high": "اولویت بالا"}


def _sugg(m) -> dict[str, Any]:
    d = dict(m)
    for k in ("anchor_alternatives", "score_breakdown", "evidence"):
        d[k] = loads(d[k], [] if k == "anchor_alternatives" else {})
    d["kind_fa"] = KIND_FA.get(d["kind"], d["kind"]); d["confidence_fa"] = CONF_FA.get(d["confidence"], d["confidence"])
    return d


class LinkRepository(Repository):
    # ---- suggestions
    def replace_run(self, site_id: str, suggestions: list[dict[str, Any]], run_id: str, scope: str = "internal") -> dict[str, int]:
        """Upsert by (kind, source, target). Keeps user status (accepted/dismissed/done); refreshes score/reason for new ones;
        removes stale `new` rows not produced by this run."""
        with self.engine.connect() as cx:
            existing = {(r.kind, r.source_node_id, r.target_node_id): dict(r._mapping) for r in cx.execute(select(link_suggestions).where(and_(link_suggestions.c.site_id == site_id, link_suggestions.c.scope == scope)))}
        now = utcnow(); created = updated = kept = 0; seen = set()
        with self.engine.begin() as cx:
            for s in suggestions:
                key = (s["kind"], s["source_node_id"], s["target_node_id"]); seen.add(key)
                vals = {k: v for k, v in s.items() if k not in ("id", "status", "created_at", "updated_at", "content_task_id")}
                vals["anchor_alternatives"] = dumps(s.get("anchor_alternatives", [])); vals["score_breakdown"] = dumps(s.get("score_breakdown", {})); vals["evidence"] = dumps(s.get("evidence", {}))
                vals.update(site_id=site_id, scope=scope, run_id=run_id, updated_at=now)
                if key in existing:
                    ex = existing[key]
                    if ex["status"] == "new":
                        cx.execute(link_suggestions.update().where(link_suggestions.c.id == ex["id"]).values(**vals)); updated += 1
                    else:
                        cx.execute(link_suggestions.update().where(link_suggestions.c.id == ex["id"]).values(score=vals["score"], confidence=vals["confidence"], run_id=run_id, updated_at=now)); kept += 1
                else:
                    cx.execute(link_suggestions.insert().values(**vals, status="new", created_at=now)); created += 1
            stale = [ex["id"] for k, ex in existing.items() if k not in seen and ex["status"] == "new"]
            if stale:
                cx.execute(delete(link_suggestions).where(link_suggestions.c.id.in_(stale)))
        return {"created": created, "updated": updated, "kept": kept, "removed": len(stale)}

    def list(self, site_id: str, kind: str | None = None, status: str | None = None, min_score: float = 0.0, target: str | None = None, source: str | None = None,
             q: str | None = None, confidence: str | None = None, sort: str = "score", limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        conds = [link_suggestions.c.site_id == site_id, link_suggestions.c.score >= min_score]
        if kind: conds.append(link_suggestions.c.kind == kind)
        if status: conds.append(link_suggestions.c.status.in_(status.split(",")))
        if confidence: conds.append(link_suggestions.c.confidence == confidence)
        if target: conds.append(link_suggestions.c.target_node_id == target)
        if source: conds.append(link_suggestions.c.source_node_id == source)
        if q: conds.append(link_suggestions.c.source_title.like(f"%{q}%") | link_suggestions.c.target_title.like(f"%{q}%") | link_suggestions.c.anchor.like(f"%{q}%") | link_suggestions.c.target_url.like(f"%{q}%"))
        ob = link_suggestions.c.updated_at.desc() if sort == "updated_at" else link_suggestions.c.score.desc()
        with self.engine.connect() as cx:
            total = cx.execute(select(func.count()).select_from(link_suggestions).where(and_(*conds))).scalar() or 0
            rows = cx.execute(select(link_suggestions).where(and_(*conds)).order_by(ob, link_suggestions.c.id).limit(limit).offset(offset)).all()
        return [_sugg(r._mapping) for r in rows], int(total)

    def get(self, site_id: str, sid: int) -> dict | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(link_suggestions).where(and_(link_suggestions.c.site_id == site_id, link_suggestions.c.id == sid))).first()
        return _sugg(r._mapping) if r else None

    def set_status(self, site_id: str, sid: int, status: str, anchor: str | None = None, content_task_id: int | None = None) -> dict | None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        vals: dict[str, Any] = {"status": status, "updated_at": utcnow()}
        if anchor: vals["anchor"] = anchor
        if content_task_id: vals["content_task_id"] = content_task_id
        with self.engine.begin() as cx:
            cx.execute(link_suggestions.update().where(and_(link_suggestions.c.site_id == site_id, link_suggestions.c.id == sid)).values(**vals))
        return self.get(site_id, sid)

    def counts(self, site_id: str) -> dict[str, Any]:
        with self.engine.connect() as cx:
            by_status = dict(cx.execute(select(link_suggestions.c.status, func.count()).where(link_suggestions.c.site_id == site_id).group_by(link_suggestions.c.status)).all())
            by_kind = dict(cx.execute(select(link_suggestions.c.kind, func.count()).where(and_(link_suggestions.c.site_id == site_id, link_suggestions.c.status == "new")).group_by(link_suggestions.c.kind)).all())
            by_conf = dict(cx.execute(select(link_suggestions.c.confidence, func.count()).where(and_(link_suggestions.c.site_id == site_id, link_suggestions.c.status == "new")).group_by(link_suggestions.c.confidence)).all())
            stats = cx.execute(select(link_page_stats.c.flags, link_page_stats.c.health_score).where(link_page_stats.c.site_id == site_id)).all()
        flags = {"orphan": 0, "nav_only_inbound": 0, "low_inbound": 0, "generic_anchors": 0, "over_optimized_anchor": 0, "single_source": 0}
        hs = []
        for f, h in stats:
            for x in loads(f, []):
                if x in flags: flags[x] += 1
            hs.append(h or 0)
        return {"by_status": {s: int(by_status.get(s, 0)) for s in STATUSES}, "by_kind": {k: int(v) for k, v in by_kind.items()}, "by_confidence": {k: int(v) for k, v in by_conf.items()},
                "pages": len(stats), "flags": flags, "avg_health": round(sum(hs) / len(hs), 1) if hs else None}

    # ---- page stats
    def save_stats(self, site_id: str, stats: dict[str, dict[str, Any]]) -> int:
        now = utcnow()
        with self.engine.begin() as cx:
            cx.execute(delete(link_page_stats).where(link_page_stats.c.site_id == site_id))
            for nid, s in stats.items():
                cx.execute(link_page_stats.insert().values(site_id=site_id, node_id=nid, url=s["url"], title=s["title"], stage=s["stage"], inbound_total=s["inbound_total"], inbound_body=s["inbound_body"],
                                                           inbound_nav_only=s["inbound_nav_only"], unique_sources=s["unique_sources"], outbound_body=s["outbound_body"], outbound_total=s["outbound_total"],
                                                           anchor_distribution=dumps(s["anchor_distribution"]), exact_match_ratio=s["exact_match_ratio"], generic_ratio=s["generic_ratio"], flags=dumps(s["flags"]),
                                                           pagerank=s["pagerank"], health_score=s["health_score"], health_breakdown=dumps(s["health_breakdown"]), computed_at=now))
        return len(stats)

    def pages(self, site_id: str, flag: str | None = None, sort: str = "health_score", order: str = "asc", limit: int = 100, offset: int = 0, q: str | None = None) -> tuple[list[dict], int]:
        conds = [link_page_stats.c.site_id == site_id]
        if flag: conds.append(link_page_stats.c.flags.like(f'%"{flag}"%'))
        if q: conds.append(link_page_stats.c.title.like(f"%{q}%") | link_page_stats.c.url.like(f"%{q}%"))
        col = getattr(link_page_stats.c, sort) if sort in ("health_score", "inbound_body", "pagerank", "outbound_body", "title") else link_page_stats.c.health_score
        ob = col.asc() if order == "asc" else col.desc()
        with self.engine.connect() as cx:
            total = cx.execute(select(func.count()).select_from(link_page_stats).where(and_(*conds))).scalar() or 0
            rows = cx.execute(select(link_page_stats).where(and_(*conds)).order_by(ob, link_page_stats.c.node_id).limit(limit).offset(offset)).all()
        out = []
        for r in rows:
            d = dict(r._mapping); d["anchor_distribution"] = loads(d["anchor_distribution"], []); d["flags"] = loads(d["flags"], []); d["health_breakdown"] = loads(d["health_breakdown"], {}); out.append(d)
        return out, int(total)

    def page(self, site_id: str, node_id: str) -> dict | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(link_page_stats).where(and_(link_page_stats.c.site_id == site_id, link_page_stats.c.node_id == node_id))).first()
        if not r:
            return None
        d = dict(r._mapping); d["anchor_distribution"] = loads(d["anchor_distribution"], []); d["flags"] = loads(d["flags"], []); d["health_breakdown"] = loads(d["health_breakdown"], {})
        return d

    # ---- patterns
    def upsert_pattern(self, site_id: str, key: str, feature: dict, accepted: int, dismissed: int, done: int, message_fa: str) -> None:
        tot = accepted + dismissed
        rate = round(accepted / tot, 2) if tot else 0.0
        now = utcnow()
        with self.engine.begin() as cx:
            cx.execute(text("INSERT INTO link_patterns(site_id,pattern_key,feature,accepted,dismissed,done,acceptance_rate,message_fa,status,created_at,updated_at) VALUES(:s,:k,:f,:a,:d,:o,:r,:m,'new',:t,:t) "
                            "ON CONFLICT(site_id,pattern_key) DO UPDATE SET feature=excluded.feature, accepted=excluded.accepted, dismissed=excluded.dismissed, done=excluded.done, acceptance_rate=excluded.acceptance_rate, message_fa=excluded.message_fa, updated_at=excluded.updated_at"),
                       {"s": site_id, "k": key, "f": dumps(feature), "a": accepted, "d": dismissed, "o": done, "r": rate, "m": message_fa, "t": now})

    def patterns(self, site_id: str, status: str | None = None) -> list[dict]:
        conds = [link_patterns.c.site_id == site_id]
        if status: conds.append(link_patterns.c.status == status)
        with self.engine.connect() as cx:
            rows = cx.execute(select(link_patterns).where(and_(*conds)).order_by(link_patterns.c.acceptance_rate.desc(), link_patterns.c.accepted.desc())).all()
        out = []
        for r in rows:
            d = dict(r._mapping); d["feature"] = loads(d["feature"], {}); out.append(d)
        return out

    def set_pattern_status(self, site_id: str, pid: int, status: str, memory_ref: str | None = None) -> dict | None:
        vals: dict[str, Any] = {"status": status, "updated_at": utcnow()}
        if memory_ref: vals["memory_pattern_ref"] = memory_ref
        with self.engine.begin() as cx:
            cx.execute(link_patterns.update().where(and_(link_patterns.c.site_id == site_id, link_patterns.c.id == pid)).values(**vals))
        return next((p for p in self.patterns(site_id) if p["id"] == pid), None)
