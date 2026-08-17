from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from sqlalchemy import and_, delete, func, or_, select, text

from ...db.repositories.base import Repository, dumps, loads, utcnow
from ...db.tables import keyword_clusters, keyword_imports, keyword_opportunities, keywords
from .normalize import normalize_keyword

INTENTS = ("informational", "navigational", "commercial", "transactional", "local")
PRIORITIES = ("high", "medium", "low")
STATUSES = ("new", "planned", "in_progress", "published", "ignored")
OPP_KINDS = ("improve_page", "create_content", "update_title", "add_internal_links")
OPP_STATUSES = ("new", "accepted", "dismissed", "done")


@dataclass
class Keyword:
    site_id: str
    keyword: str
    normalized: str = ""
    id: int | None = None
    intent: str | None = None
    cluster_id: str | None = None
    topic: str | None = None
    volume: int | None = None
    difficulty: float | None = None
    priority: str | None = None
    target_url: str | None = None
    status: str = "new"
    source: str | None = None
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self):
        if not self.normalized:
            self.normalized = normalize_keyword(self.keyword)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KeywordCluster:
    site_id: str
    cluster_id: str
    name: str
    topic: str | None = None
    keywords_count: int = 0
    method: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KeywordOpportunity:
    site_id: str
    keyword_id: int
    kind: str
    score: float
    reason: str
    target_url: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    status: str = "new"
    run_id: str | None = None
    id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _kw(m) -> Keyword:
    return Keyword(**{k: m[k] for k in Keyword.__dataclass_fields__ if k in m})


def _opp(m) -> KeywordOpportunity:
    d = {k: m[k] for k in KeywordOpportunity.__dataclass_fields__ if k in m and k != "evidence"}
    return KeywordOpportunity(evidence=loads(m["evidence"], {}), **d)


class KeywordsRepository(Repository):
    # ---------------------------------------------------------------- keywords
    def list(self, site_id: str, q: str | None = None, status: str | None = None, intent: str | None = None, cluster_id: str | None = None,
             topic: str | None = None, priority: str | None = None, sort: str = "updated_at", order: str = "desc",
             limit: int = 50, offset: int = 0) -> tuple[list[Keyword], int]:
        conds = [keywords.c.site_id == site_id]
        if q:
            nq = normalize_keyword(q)
            conds.append(or_(keywords.c.normalized.like(f"%{nq}%"), keywords.c.keyword.like(f"%{q}%"), keywords.c.target_url.like(f"%{q}%")))
        if status: conds.append(keywords.c.status == status)
        if intent: conds.append(keywords.c.intent == intent)
        if cluster_id: conds.append(keywords.c.cluster_id == cluster_id)
        if topic: conds.append(keywords.c.topic == topic)
        if priority: conds.append(keywords.c.priority == priority)
        col = getattr(keywords.c, sort, None) if sort in ("keyword", "volume", "difficulty", "priority", "status", "updated_at", "created_at", "intent", "topic") else keywords.c.updated_at
        ob = col.desc().nullslast() if order == "desc" else col.asc().nullsfirst()
        with self.engine.connect() as cx:
            total = cx.execute(select(func.count()).select_from(keywords).where(and_(*conds))).scalar() or 0
            rows = cx.execute(select(keywords).where(and_(*conds)).order_by(ob, keywords.c.id).limit(limit).offset(offset)).all()
        return [_kw(r._mapping) for r in rows], int(total)

    def all(self, site_id: str) -> list[Keyword]:
        with self.engine.connect() as cx:
            return [_kw(r._mapping) for r in cx.execute(select(keywords).where(keywords.c.site_id == site_id).order_by(keywords.c.id))]

    def get(self, site_id: str, kid: int) -> Keyword | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(keywords).where(and_(keywords.c.site_id == site_id, keywords.c.id == kid))).first()
        return _kw(r._mapping) if r else None

    def get_by_normalized(self, site_id: str, normalized: str) -> Keyword | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(keywords).where(and_(keywords.c.site_id == site_id, keywords.c.normalized == normalized))).first()
        return _kw(r._mapping) if r else None

    def upsert(self, kw: Keyword, update_fields: Iterable[str] | None = None) -> tuple[Keyword, bool]:
        """Insert or update by (site_id, normalized). Returns (row, created)."""
        existing = self.get_by_normalized(kw.site_id, kw.normalized)
        now = utcnow()
        if existing:
            fields = list(update_fields) if update_fields is not None else ["intent", "cluster_id", "topic", "volume", "difficulty", "priority", "target_url", "status", "source", "notes"]
            values = {f: getattr(kw, f) for f in fields if getattr(kw, f) is not None}
            values["updated_at"] = now
            with self.engine.begin() as cx:
                cx.execute(keywords.update().where(keywords.c.id == existing.id).values(**values))
            return self.get(kw.site_id, existing.id), False  # type: ignore[return-value]
        values = {k: v for k, v in kw.to_dict().items() if k not in ("id", "created_at", "updated_at")}
        values.update(created_at=now, updated_at=now)
        with self.engine.begin() as cx:
            res = cx.execute(keywords.insert().values(**values))
            new_id = res.inserted_primary_key[0]
        return self.get(kw.site_id, new_id), True  # type: ignore[return-value]

    def update(self, site_id: str, kid: int, **fields) -> Keyword | None:
        allowed = {k: v for k, v in fields.items() if k in ("keyword", "intent", "cluster_id", "topic", "volume", "difficulty", "priority", "target_url", "status", "notes")}
        if "keyword" in allowed:
            allowed["normalized"] = normalize_keyword(allowed["keyword"])
        if not allowed:
            return self.get(site_id, kid)
        allowed["updated_at"] = utcnow()
        with self.engine.begin() as cx:
            cx.execute(keywords.update().where(and_(keywords.c.site_id == site_id, keywords.c.id == kid)).values(**allowed))
        return self.get(site_id, kid)

    def delete(self, site_id: str, kid: int) -> bool:
        with self.engine.begin() as cx:
            cx.execute(delete(keyword_opportunities).where(and_(keyword_opportunities.c.site_id == site_id, keyword_opportunities.c.keyword_id == kid)))
            n = cx.execute(delete(keywords).where(and_(keywords.c.site_id == site_id, keywords.c.id == kid))).rowcount
        return bool(n)

    def set_clusters(self, site_id: str, assignment: dict[int, str | None]) -> None:
        with self.engine.begin() as cx:
            for kid, cid in assignment.items():
                cx.execute(keywords.update().where(and_(keywords.c.site_id == site_id, keywords.c.id == kid)).values(cluster_id=cid, updated_at=utcnow()))

    def counts(self, site_id: str) -> dict[str, Any]:
        with self.engine.connect() as cx:
            total = cx.execute(select(func.count()).select_from(keywords).where(keywords.c.site_id == site_id)).scalar() or 0
            by_status = dict(cx.execute(select(keywords.c.status, func.count()).where(keywords.c.site_id == site_id).group_by(keywords.c.status)).all())
            by_intent = dict(cx.execute(select(keywords.c.intent, func.count()).where(keywords.c.site_id == site_id).group_by(keywords.c.intent)).all())
            clusters = cx.execute(select(func.count()).select_from(keyword_clusters).where(keyword_clusters.c.site_id == site_id)).scalar() or 0
            with_target = cx.execute(select(func.count()).select_from(keywords).where(and_(keywords.c.site_id == site_id, keywords.c.target_url.isnot(None), keywords.c.target_url != ""))).scalar() or 0
            opps = dict(cx.execute(select(keyword_opportunities.c.kind, func.count()).where(and_(keyword_opportunities.c.site_id == site_id, keyword_opportunities.c.status == "new")).group_by(keyword_opportunities.c.kind)).all())
        return {"total": int(total), "by_status": {k or "—": v for k, v in by_status.items()}, "by_intent": {k or "—": v for k, v in by_intent.items()},
                "clusters": int(clusters), "with_target": int(with_target), "opportunities_new": {k: int(v) for k, v in opps.items()}}

    # ---------------------------------------------------------------- clusters
    def list_clusters(self, site_id: str) -> list[KeywordCluster]:
        with self.engine.connect() as cx:
            rows = cx.execute(select(keyword_clusters).where(keyword_clusters.c.site_id == site_id).order_by(keyword_clusters.c.keywords_count.desc())).all()
        return [KeywordCluster(**{k: r._mapping[k] for k in KeywordCluster.__dataclass_fields__}) for r in rows]

    def replace_clusters(self, site_id: str, clusters: list[KeywordCluster], keep_manual_topics: bool = True) -> None:
        old = {c.cluster_id: c for c in self.list_clusters(site_id)}
        now = utcnow()
        with self.engine.begin() as cx:
            cx.execute(delete(keyword_clusters).where(keyword_clusters.c.site_id == site_id))
            for c in clusters:
                topic, method = c.topic, c.method
                prev = old.get(c.cluster_id)
                if keep_manual_topics and prev and prev.topic and (prev.method or "").endswith("manual_topic"):
                    topic, method = prev.topic, f"{c.method}+manual_topic"     # user-set topic survives re-clustering
                cx.execute(keyword_clusters.insert().values(cluster_id=c.cluster_id, site_id=site_id, name=c.name, topic=topic, keywords_count=c.keywords_count,
                                                            method=method, created_at=prev.created_at if prev else now, updated_at=now))

    def update_cluster(self, site_id: str, cluster_id: str, **fields) -> KeywordCluster | None:
        allowed = {k: v for k, v in fields.items() if k in ("name", "topic")}
        if allowed:
            allowed["updated_at"] = utcnow()
            if "topic" in allowed:   # mark as user-set so re-clustering keeps it
                cur = next((c for c in self.list_clusters(site_id) if c.cluster_id == cluster_id), None)
                base = (cur.method or "token_jaccard").replace("+manual_topic", "") if cur else "token_jaccard"
                allowed["method"] = f"{base}+manual_topic"
            with self.engine.begin() as cx:
                cx.execute(keyword_clusters.update().where(and_(keyword_clusters.c.site_id == site_id, keyword_clusters.c.cluster_id == cluster_id)).values(**allowed))
                if "topic" in allowed:   # propagate topic label to member keywords
                    cx.execute(keywords.update().where(and_(keywords.c.site_id == site_id, keywords.c.cluster_id == cluster_id)).values(topic=allowed["topic"], updated_at=utcnow()))
        for c in self.list_clusters(site_id):
            if c.cluster_id == cluster_id:
                return c
        return None

    # ---------------------------------------------------------------- imports
    def record_import(self, site_id: str, filename: str | None, fmt: str, rows_total: int, imported: int, updated: int, skipped: int,
                      mapping: dict, errors: list[dict]) -> int:
        with self.engine.begin() as cx:
            res = cx.execute(keyword_imports.insert().values(site_id=site_id, filename=filename, format=fmt, rows_total=rows_total, rows_imported=imported,
                                                            rows_updated=updated, rows_skipped=skipped, mapping=dumps(mapping), errors=dumps(errors[:200]),
                                                            created_at=utcnow()))
            return int(res.inserted_primary_key[0])

    def list_imports(self, site_id: str, limit: int = 20) -> list[dict]:
        with self.engine.connect() as cx:
            rows = cx.execute(select(keyword_imports).where(keyword_imports.c.site_id == site_id).order_by(keyword_imports.c.id.desc()).limit(limit)).all()
        out = []
        for r in rows:
            m = dict(r._mapping); m["mapping"] = loads(m["mapping"], {}); m["errors"] = loads(m["errors"], []); out.append(m)
        return out

    # ---------------------------------------------------------------- opportunities
    def replace_opportunities(self, site_id: str, opps: list[KeywordOpportunity], run_id: str) -> dict[str, int]:
        """Upsert by (keyword_id, kind); keep user status for existing rows; delete rows not produced by this run (unless accepted/done)."""
        existing = {(o.keyword_id, o.kind): o for o in self.list_opportunities(site_id, limit=100000)[0]}
        now = utcnow(); created = updated = 0
        with self.engine.begin() as cx:
            seen = set()
            for o in opps:
                key = (o.keyword_id, o.kind); seen.add(key)
                if key in existing:
                    cx.execute(keyword_opportunities.update().where(keyword_opportunities.c.id == existing[key].id)
                               .values(target_url=o.target_url, score=o.score, reason=o.reason, evidence=dumps(o.evidence), run_id=run_id, updated_at=now))
                    updated += 1
                else:
                    cx.execute(keyword_opportunities.insert().values(site_id=site_id, keyword_id=o.keyword_id, kind=o.kind, target_url=o.target_url, score=o.score,
                                                                     reason=o.reason, evidence=dumps(o.evidence), status="new", run_id=run_id, created_at=now, updated_at=now))
                    created += 1
            stale = [e.id for k, e in existing.items() if k not in seen and e.status in ("new", "dismissed")]
            if stale:
                cx.execute(delete(keyword_opportunities).where(keyword_opportunities.c.id.in_(stale)))
        return {"created": created, "updated": updated, "removed": len(stale)}

    def list_opportunities(self, site_id: str, kind: str | None = None, status: str | None = None, keyword_id: int | None = None,
                           min_score: float = 0.0, limit: int = 100, offset: int = 0) -> tuple[list[KeywordOpportunity], int]:
        conds = [keyword_opportunities.c.site_id == site_id, keyword_opportunities.c.score >= min_score]
        if kind: conds.append(keyword_opportunities.c.kind == kind)
        if status: conds.append(keyword_opportunities.c.status == status)
        if keyword_id: conds.append(keyword_opportunities.c.keyword_id == keyword_id)
        with self.engine.connect() as cx:
            total = cx.execute(select(func.count()).select_from(keyword_opportunities).where(and_(*conds))).scalar() or 0
            rows = cx.execute(select(keyword_opportunities).where(and_(*conds)).order_by(keyword_opportunities.c.score.desc(), keyword_opportunities.c.id).limit(limit).offset(offset)).all()
        return [_opp(r._mapping) for r in rows], int(total)

    def set_opportunity_status(self, site_id: str, oid: int, status: str) -> KeywordOpportunity | None:
        if status not in OPP_STATUSES:
            raise ValueError(f"status must be one of {OPP_STATUSES}")
        with self.engine.begin() as cx:
            cx.execute(keyword_opportunities.update().where(and_(keyword_opportunities.c.site_id == site_id, keyword_opportunities.c.id == oid)).values(status=status, updated_at=utcnow()))
            r = cx.execute(select(keyword_opportunities).where(keyword_opportunities.c.id == oid)).first()
        return _opp(r._mapping) if r else None

    # ---------------------------------------------------------------- GSC join (read-only over v0.1 tables)
    def gsc_by_normalized(self, site_id: str) -> dict[str, dict[str, Any]]:
        """Aggregate gsc_query_page per normalized query: clicks, impressions, ctr, impression-weighted position, top page."""
        out: dict[str, dict[str, Any]] = {}
        with self.engine.connect() as cx:
            rows = cx.execute(text("SELECT query, page, clicks, impressions, position FROM gsc_query_page WHERE site_id=:s"), {"s": site_id}).all()
        for query, page, clicks, impressions, position in rows:
            key = normalize_keyword(query)
            a = out.setdefault(key, {"clicks": 0, "impressions": 0, "_pos_w": 0.0, "pages": []})
            a["clicks"] += clicks or 0; a["impressions"] += impressions or 0; a["_pos_w"] += (position or 0) * (impressions or 0)
            a["pages"].append({"page": page, "clicks": clicks, "impressions": impressions, "position": position})
        for key, a in out.items():
            imp = a["impressions"]
            a["position"] = round(a["_pos_w"] / imp, 1) if imp else None
            a["ctr"] = round(a["clicks"] / imp, 4) if imp else 0.0
            a["pages"].sort(key=lambda p: (-(p["impressions"] or 0), p["position"] or 99))
            a["top_page"] = a["pages"][0]["page"] if a["pages"] else None
            a["pages_count"] = len(a["pages"])
            del a["_pos_w"]
        return out
