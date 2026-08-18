"""ContentService — items + workflow + briefs + calendar + graph sync."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from urllib.parse import unquote

from sqlalchemy import Engine, text

from ...ai import AIOrchestrator
from ...brain.keywords import KeywordsRepository, normalize_keyword
from ...graph.model import GraphEdge, GraphNode
from ...graph.store import get_graph_store
from ...normalizer.url import normalize_url
from .briefs import BriefGenerator
from .repository import STATUS_FA, STATUSES, TRANSITIONS, ContentBrief, ContentItem, ContentRepository, WorkflowError


class ContentService:
    def __init__(self, engine: Engine, orchestrator: AIOrchestrator | None = None):
        self.engine = engine
        self.repo = ContentRepository(engine)
        self.kw = KeywordsRepository(engine)
        self.briefs = BriefGenerator(engine, orchestrator)

    # ---- enrichment
    def enrich(self, items: list[ContentItem]) -> list[dict[str, Any]]:
        out = []
        for it in items:
            d = it.to_dict()
            d["allowed_transitions"] = list(TRANSITIONS.get(it.status, ()))
            d["has_brief"] = bool(it.brief_id)
            out.append(d)
        return out

    def detail(self, site_id: str, cid: int) -> dict[str, Any] | None:
        it = self.repo.get(site_id, cid)
        if not it:
            return None
        d = self.enrich([it])[0]
        d["brief"] = self.repo.get_brief(site_id, it.brief_id).to_dict() if it.brief_id else None
        d["briefs"] = [{"id": b.id, "version": b.version, "created_at": b.created_at, "provenance": b.provenance} for b in self.repo.briefs(site_id, cid)]
        d["events"] = self.repo.events(site_id, cid)
        if it.target_keyword_id:
            k = self.kw.get(site_id, it.target_keyword_id)
            if k:
                g = self.kw.gsc_by_normalized(site_id).get(k.normalized)
                d["keyword"] = {**k.to_dict(), "gsc": g and {x: g[x] for x in ("clicks", "impressions", "ctr", "position")}}
        return d

    # ---- create helpers
    def create(self, site_id: str, title: str, **fields) -> ContentItem:
        kw_id = fields.get("target_keyword_id")
        kw_text = fields.get("target_keyword")
        k = self.kw.get(site_id, kw_id) if kw_id else (self.kw.get_by_normalized(site_id, normalize_keyword(kw_text)) if kw_text else None)
        if k:
            fields.setdefault("target_keyword_id", k.id); fields.setdefault("target_keyword", k.keyword)
            fields.setdefault("intent", k.intent); fields.setdefault("cluster_id", k.cluster_id); fields.setdefault("priority", k.priority)
            if not fields.get("topic"):
                fields["topic"] = k.topic or (next((c.topic or c.name for c in self.kw.list_clusters(site_id) if c.cluster_id == k.cluster_id), None) if k.cluster_id else None)
        item = ContentItem(site_id=site_id, title=title, **{f: v for f, v in fields.items() if f in ContentItem.__dataclass_fields__})
        return self.repo.create(item)

    def create_from_opportunity(self, site_id: str, oid: int) -> ContentItem:
        rows, _ = self.kw.list_opportunities(site_id, limit=100000)
        o = next((x for x in rows if x.id == oid), None)
        if not o:
            raise KeyError(oid)
        k = self.kw.get(site_id, o.keyword_id)
        title = {"create_content": f"{k.keyword if k else ''}", "improve_page": f"بازنویسی: {k.keyword if k else ''}", "update_title": f"عنوان/متا: {k.keyword if k else ''}",
                 "add_internal_links": f"لینک‌سازی: {k.keyword if k else ''}"}.get(o.kind, k.keyword if k else "محتوا")
        item = self.create(site_id, title, target_keyword_id=o.keyword_id, url=o.target_url if o.kind != "create_content" else None,
                           metadata={"opportunity_id": o.id, "opportunity_kind": o.kind, "reason": o.reason})
        self.kw.set_opportunity_status(site_id, oid, "accepted")
        return item

    # ---- briefs
    def generate_brief(self, site_id: str, cid: int, use_ai: bool = False, mark_ready: bool = False) -> ContentBrief:
        it = self.repo.get(site_id, cid)
        if not it:
            raise KeyError(cid)
        b = self.briefs.generate(it, use_ai=use_ai)
        saved = self.repo.add_brief(b)
        meta = dict(it.metadata or {}); meta.update(h1=saved.h1, seo_title=saved.seo_title, meta_description=saved.meta_description)
        self.repo.update(site_id, cid, metadata=meta, intent=it.intent or saved.intent)
        self.repo.add_note(site_id, cid, f"brief v{saved.version} generated ({'AI' if saved.provenance.get('ai_used') else 'rules'})", actor="system")
        if mark_ready and it.status == "planned":
            self.repo.transition(site_id, cid, "brief_ready", actor="system", note="auto after brief")
        return saved

    # ---- calendar / board
    def calendar(self, site_id: str, date_from: str, date_to: str) -> dict[str, Any]:
        items, _ = self.repo.list(site_id, date_from=date_from, date_to=date_to, sort="publish_date", order="asc", limit=1000)
        days: dict[str, list[dict]] = {}
        for d in self.enrich(items):
            days.setdefault(d["publish_date"], []).append(d)
        unscheduled, _ = self.repo.list(site_id, limit=200)
        return {"from": date_from, "to": date_to, "days": days, "unscheduled": [d for d in self.enrich([i for i in unscheduled if not i.publish_date])],
                "counts": self.repo.counts(site_id)}

    def board(self, site_id: str) -> dict[str, Any]:
        items = self.enrich(self.repo.all(site_id))
        cols = {s: [] for s in STATUSES}
        for d in items:
            cols.setdefault(d["status"], []).append(d)
        return {"columns": [{"status": s, "status_fa": STATUS_FA[s], "items": sorted(cols[s], key=lambda x: (x["publish_date"] or "9999", -(x["id"] or 0)))} for s in STATUSES],
                "counts": self.repo.counts(site_id)}

    # ---- graph
    def sync_graph(self, site_id: str) -> dict[str, Any]:
        store = get_graph_store(self.engine)
        items = self.repo.all(site_id)
        page_ids = {}
        with self.engine.connect() as cx:
            for nid, url in cx.execute(text("SELECT node_id, url FROM graph_nodes WHERE site_id=:s AND node_type IN ('PAGE','POST','CATEGORY') AND url IS NOT NULL"), {"s": site_id}).all():
                page_ids[normalize_url(unquote(url))] = nid
        nodes, edges = [], []
        for it in items:
            nid = f"content:{it.id}"
            nodes.append(GraphNode(nid, site_id, "CONTENT", {"label": it.title, "url": it.url, "props": {"status": it.status, "stage": it.status, "priority": it.priority, "publish_date": it.publish_date,
                                                                                                        "intent": it.intent, "topic": it.topic, "target_keyword": it.target_keyword, "ai_provider": it.ai_provider}}))
            if it.target_keyword_id:
                edges.append(GraphEdge(nid, f"keyword:{it.target_keyword_id}", "CONTENT_FOR", 1.0, {}, site_id))
            if it.cluster_id:
                edges.append(GraphEdge(nid, f"topic:{it.cluster_id}", "CLUSTERED_IN", 1.0, {}, site_id))
            if it.url:
                pid = page_ids.get(normalize_url(it.url))
                if pid:
                    edges.append(GraphEdge(nid, pid, "PUBLISHED_AS", 1.0, {"props": {"status": it.status}}, site_id))
        keep = {n.id for n in nodes}
        with self.engine.begin() as cx:
            cx.execute(text("DELETE FROM graph_edges WHERE site_id=:s AND source_id LIKE 'content:%'"), {"s": site_id})
            for (nid,) in cx.execute(text("SELECT node_id FROM graph_nodes WHERE site_id=:s AND node_type='CONTENT'"), {"s": site_id}).all():
                if nid not in keep:
                    cx.execute(text("DELETE FROM graph_nodes WHERE site_id=:s AND node_id=:n"), {"s": site_id, "n": nid})
        # only keep edges whose target exists (keyword/topic nodes may not be synced yet)
        existing = {n.id for n in store.list_nodes(site_id, ["KEYWORD", "TOPIC", "PAGE", "POST", "CATEGORY"], limit=100000)}
        edges = [e for e in edges if e.target in existing]
        return {"nodes": store.upsert_nodes(nodes), "edges": store.upsert_edges(edges), "items": len(items)}
