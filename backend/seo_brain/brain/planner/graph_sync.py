"""Planner → Knowledge Graph sync (idempotent). Nodes: CONTENT_PLAN (plan:<id>), CONTENT_CLUSTER (ccluster:<id>), CATEGORY for
brain/manual categories (category:brain:<slug> / category:manual:<slug>), SEARCH_INTENT (intent:<x>), FUNNEL_STAGE (stage:<x>).
Edges: plan TARGETS keyword · plan BELONGS_TO category · plan CONNECTED_TO topic · plan SUPPORTS page · category CONTAINS content/plan ·
content_cluster CONTAINS plan · plan PLANNED_AS content · plan HAS_INTENT intent · plan IN_STAGE stage · plan LINK_OPPORTUNITY page (prep)."""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from sqlalchemy import Engine, text

from ...graph.model import GraphEdge, GraphNode
from ...graph.store import get_graph_store
from ...normalizer.url import normalize_url
from .repository import FUNNEL_FA, INTENT_FA, PlannerRepository

PLAN_PREFIXES = ("plan:", "ccluster:", "category:brain:", "category:manual:", "intent:", "stage:")


class PlannerGraphSync:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.repo = PlannerRepository(engine)

    def sync(self, site_id: str) -> dict[str, Any]:
        store = get_graph_store(self.engine)
        plans = self.repo.all_plans(site_id)
        cats = self.repo.list_categories(site_id)
        clusters = self.repo.list_clusters(site_id)
        with self.engine.connect() as cx:
            page_ids = {normalize_url(unquote(u)): nid for nid, u in cx.execute(text("SELECT node_id, url FROM graph_nodes WHERE site_id=:s AND node_type IN ('PAGE','POST','CATEGORY') AND url IS NOT NULL"), {"s": site_id}).all()}
            wp_cat_nodes = {}
            for nid, props in cx.execute(text("SELECT node_id, props FROM graph_nodes WHERE site_id=:s AND node_type='CATEGORY'"), {"s": site_id}).all():
                import json as _j
                wp = _j.loads(props or "{}").get("wp_id")
                if wp is not None:
                    wp_cat_nodes[int(wp)] = nid
            existing_types = {r[0]: r[1] for r in cx.execute(text("SELECT node_id, node_type FROM graph_nodes WHERE site_id=:s AND node_type IN ('KEYWORD','TOPIC','PAGE','POST','CATEGORY','CONTENT')"), {"s": site_id}).all()}
        nodes: list[GraphNode] = []; edges: list[GraphEdge] = []
        cat_node: dict[int, str] = {}
        for c in cats:
            if c["source"] == "wordpress" and c["wordpress_category_id"] in wp_cat_nodes:
                cat_node[c["id"]] = wp_cat_nodes[c["wordpress_category_id"]]
                continue
            nid = f"category:{c['source']}:{c['slug'] or c['id']}"
            cat_node[c["id"]] = nid
            nodes.append(GraphNode(nid, site_id, "CATEGORY", {"label": c["name"], "url": c.get("url"), "props": {"source": c["source"], "slug": c["slug"], "count": c["post_count"], "page_count": c["page_count"], "keyword_count": c["keyword_count"], "coverage": c["coverage_score"], "brain": True}}))
        for c in cats:
            if c["parent_id"] and c["id"] in cat_node and c["parent_id"] in cat_node and c["source"] != "wordpress":
                edges.append(GraphEdge(cat_node[c["id"]], cat_node[c["parent_id"]], "BELONGS_TO", 1.0, {}, site_id))
        for cl in clusters:
            nid = f"ccluster:{cl['id']}"
            nodes.append(GraphNode(nid, site_id, "CONTENT_CLUSTER", {"label": cl["name"], "props": {"topic": cl.get("topic"), "keyword_cluster_id": cl.get("keyword_cluster_id"), "pillar_plan_id": cl.get("pillar_plan_id")}}))
            if cl.get("category_id") in cat_node:
                edges.append(GraphEdge(nid, cat_node[cl["category_id"]], "BELONGS_TO", 1.0, {}, site_id))
        intents_used, stages_used = set(), set()
        for p in plans:
            nid = f"plan:{p.id}"
            nodes.append(GraphNode(nid, site_id, "CONTENT_PLAN", {"label": p.title, "url": p.url, "props": {"status": p.status, "stage": p.status, "priority": p.priority, "priority_score": p.priority_score, "page_type": p.page_type,
                                                                                                                 "intent": p.intent, "funnel_stage": p.funnel_stage, "publish_date": p.publish_date, "primary_keyword": p.primary_keyword,
                                                                                                                 "content_gap": p.content_gap, "cannibalization_risk": p.cannibalization_risk, "content_item_id": p.content_item_id, "category_id": p.category_id}}))
            if p.primary_keyword_id and f"keyword:{p.primary_keyword_id}" in existing_types:
                edges.append(GraphEdge(nid, f"keyword:{p.primary_keyword_id}", "TARGETS", 1.0, {"props": {"role": "primary"}}, site_id))
            for kw in self.repo.plan_keywords(site_id, p.id):
                if kw["role"] != "primary" and f"keyword:{kw['id']}" in existing_types:
                    edges.append(GraphEdge(nid, f"keyword:{kw['id']}", "TARGETS", 0.6, {"props": {"role": kw["role"]}}, site_id))
            if p.category_id in cat_node:
                edges.append(GraphEdge(nid, cat_node[p.category_id], "BELONGS_TO", 1.0, {}, site_id))
                edges.append(GraphEdge(cat_node[p.category_id], nid, "CONTAINS", 1.0, {}, site_id))
            if p.cluster_id and f"topic:{p.cluster_id}" in existing_types:
                edges.append(GraphEdge(nid, f"topic:{p.cluster_id}", "CONNECTED_TO", 1.0, {}, site_id))
            if p.content_cluster_id:
                edges.append(GraphEdge(f"ccluster:{p.content_cluster_id}", nid, "CONTAINS", 1.0, {}, site_id))
            if p.content_item_id and f"content:{p.content_item_id}" in existing_types:
                edges.append(GraphEdge(nid, f"content:{p.content_item_id}", "PLANNED_AS", 1.0, {}, site_id))
                if p.category_id in cat_node:
                    edges.append(GraphEdge(cat_node[p.category_id], f"content:{p.content_item_id}", "CONTAINS", 1.0, {}, site_id))
            for ep in (p.existing_pages or [])[:8]:
                pid = ep.get("node_id") or page_ids.get(normalize_url(unquote(ep.get("url") or "")))
                if pid and pid in existing_types:
                    edges.append(GraphEdge(nid, pid, "SUPPORTS", 0.7, {"props": {"relation": ep.get("relation"), "position": ep.get("position")}}, site_id))
            for lt in (p.link_targets or []):
                pid = lt.get("node_id")
                if pid and pid in existing_types:
                    src, tgt = (pid, nid) if lt.get("direction") == "from" else (nid, pid)
                    edges.append(GraphEdge(src, tgt, "LINK_OPPORTUNITY", float(lt.get("score") or 0.5), {"props": {"anchor": lt.get("anchor"), "reason": lt.get("reason_fa"), "scope": "plan"}}, site_id))
            if p.intent:
                intents_used.add(p.intent); edges.append(GraphEdge(nid, f"intent:{p.intent}", "HAS_INTENT", 1.0, {}, site_id))
            if p.funnel_stage:
                stages_used.add(p.funnel_stage); edges.append(GraphEdge(nid, f"stage:{p.funnel_stage}", "IN_STAGE", 1.0, {}, site_id))
        for i in intents_used:
            nodes.append(GraphNode(f"intent:{i}", site_id, "SEARCH_INTENT", {"label": INTENT_FA.get(i, i), "props": {"key": i}}))
        for s in stages_used:
            nodes.append(GraphNode(f"stage:{s}", site_id, "FUNNEL_STAGE", {"label": FUNNEL_FA.get(s, s), "props": {"key": s}}))
        keep = {n.id for n in nodes} | set(cat_node.values())
        with self.engine.begin() as cx:
            for pref in PLAN_PREFIXES:
                cx.execute(text("DELETE FROM graph_edges WHERE site_id=:s AND (source_id LIKE :p OR target_id LIKE :p)"), {"s": site_id, "p": pref + "%"})
                for (nid,) in cx.execute(text("SELECT node_id FROM graph_nodes WHERE site_id=:s AND node_id LIKE :p"), {"s": site_id, "p": pref + "%"}).all():
                    if nid not in keep:
                        cx.execute(text("DELETE FROM graph_nodes WHERE site_id=:s AND node_id=:n"), {"s": site_id, "n": nid})
            # CONTAINS edges from WP category nodes to content items were ours too
            cx.execute(text("DELETE FROM graph_edges WHERE site_id=:s AND edge_type='CONTAINS'"), {"s": site_id})
        n = store.upsert_nodes(nodes); e = store.upsert_edges(edges)
        # graph_connections on plans
        with self.engine.begin() as cx:
            for p in plans:
                deg = cx.execute(text("SELECT COUNT(*) FROM graph_edges WHERE site_id=:s AND (source_id=:n OR target_id=:n)"), {"s": site_id, "n": f"plan:{p.id}"}).scalar() or 0
                cx.execute(text("UPDATE content_plans SET graph_connections=:d WHERE id=:i"), {"d": int(deg), "i": p.id})
        return {"nodes": n, "edges": e, "plans": len(plans), "categories": len(cats), "clusters": len(clusters), "intents": len(intents_used), "stages": len(stages_used)}
