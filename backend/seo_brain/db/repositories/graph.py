"""Graph repository: reads/writes the graph tables in the Neo4j-compatible shape

    Node(id, site_id, type, metadata)   Edge(source, target, relation_type, weight, metadata)

while physically storing them in the v0.1 `graph_nodes` / `graph_edges` tables (label/url/pagerank/community/
vault_path are lifted into `metadata`, remaining props are merged in). This keeps the existing builder,
Obsidian writer, MCP tools and dashboard working unchanged, and lets a Neo4j GraphStore be dropped in later.
"""
from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import and_, func, or_, select

from ...graph.model import GraphEdge, GraphNode
from ..tables import graph_edges, graph_nodes
from .base import Repository, dumps, loads, utcnow

_NODE_META_COLS = ("label", "url", "pagerank", "community", "vault_path")


def _node_from_row(m) -> GraphNode:
    meta = {k: m[k] for k in _NODE_META_COLS}
    meta["props"] = loads(m["props"], {})
    return GraphNode(id=m["node_id"], site_id=m["site_id"], type=m["node_type"], metadata=meta)


def _edge_from_row(m) -> GraphEdge:
    return GraphEdge(source=m["source_id"], target=m["target_id"], relation_type=m["edge_type"], weight=m["weight"] or 1.0,
                     site_id=m["site_id"], metadata={"edge_id": m["edge_id"], "props": loads(m["props"], {})})


class GraphRepository(Repository):
    # ---- reads
    def counts(self, site_id: str) -> dict[str, Any]:
        with self.engine.connect() as cx:
            nodes = cx.execute(select(graph_nodes.c.node_type, func.count()).where(graph_nodes.c.site_id == site_id)
                               .group_by(graph_nodes.c.node_type)).all()
            edges = cx.execute(select(graph_edges.c.edge_type, func.count()).where(graph_edges.c.site_id == site_id)
                               .group_by(graph_edges.c.edge_type)).all()
        return {"nodes": sum(n for _, n in nodes), "edges": sum(n for _, n in edges),
                "by_node_type": {t: n for t, n in nodes}, "by_relation_type": {t: n for t, n in edges}}

    def get_node(self, site_id: str, node_id: str) -> GraphNode | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(graph_nodes).where(and_(graph_nodes.c.site_id == site_id, graph_nodes.c.node_id == node_id))).first()
        return _node_from_row(r._mapping) if r else None

    def list_nodes(self, site_id: str, types: Iterable[str] | None = None, limit: int = 500, offset: int = 0) -> list[GraphNode]:
        q = select(graph_nodes).where(graph_nodes.c.site_id == site_id)
        if types:
            q = q.where(graph_nodes.c.node_type.in_(list(types)))
        q = q.order_by(graph_nodes.c.pagerank.desc().nullslast(), graph_nodes.c.node_id).limit(limit).offset(offset)
        with self.engine.connect() as cx:
            return [_node_from_row(r._mapping) for r in cx.execute(q)]

    def edges_of(self, site_id: str, node_ids: Iterable[str], relation_types: Iterable[str] | None = None,
                 direction: str = "both") -> list[GraphEdge]:
        ids = list(node_ids)
        if not ids:
            return []
        conds = []
        if direction in ("out", "both"):
            conds.append(graph_edges.c.source_id.in_(ids))
        if direction in ("in", "both"):
            conds.append(graph_edges.c.target_id.in_(ids))
        q = select(graph_edges).where(and_(graph_edges.c.site_id == site_id, or_(*conds)))
        if relation_types:
            q = q.where(graph_edges.c.edge_type.in_(list(relation_types)))
        with self.engine.connect() as cx:
            return [_edge_from_row(r._mapping) for r in cx.execute(q)]

    def nodes_by_ids(self, site_id: str, node_ids: Iterable[str]) -> list[GraphNode]:
        ids = list(node_ids)
        if not ids:
            return []
        with self.engine.connect() as cx:
            rs = cx.execute(select(graph_nodes).where(and_(graph_nodes.c.site_id == site_id, graph_nodes.c.node_id.in_(ids))))
            return [_node_from_row(r._mapping) for r in rs]

    def search_labels(self, site_id: str, q: str, types: Iterable[str] | None = None, limit: int = 20) -> list[GraphNode]:
        """Substring search on label/url (FTS-backed search stays in graph.queries until it is migrated)."""
        like = f"%{q}%"
        stmt = select(graph_nodes).where(and_(graph_nodes.c.site_id == site_id,
                                              or_(graph_nodes.c.label.like(like), graph_nodes.c.url.like(like))))
        if types:
            stmt = stmt.where(graph_nodes.c.node_type.in_(list(types)))
        stmt = stmt.order_by(graph_nodes.c.pagerank.desc().nullslast()).limit(limit)
        with self.engine.connect() as cx:
            return [_node_from_row(r._mapping) for r in cx.execute(stmt)]

    # ---- writes (used by future builders / GraphStore; the v0.1 builder still writes via sqlite3)
    def upsert_nodes(self, nodes: Iterable[GraphNode]) -> int:
        n = 0
        with self.engine.begin() as cx:
            for node in nodes:
                meta = dict(node.metadata or {})
                props = meta.pop("props", {}) or {}
                values = {"site_id": node.site_id, "node_id": node.id, "node_type": node.type,
                          "label": meta.pop("label", None) or node.id, "url": meta.pop("url", None),
                          "pagerank": meta.pop("pagerank", None), "community": meta.pop("community", None),
                          "vault_path": meta.pop("vault_path", None), "props": dumps({**props, **meta}), "updated_at": utcnow()}
                self.upsert(cx, graph_nodes, values, conflict=["site_id", "node_id"])
                n += 1
        return n

    def upsert_edges(self, edges: Iterable[GraphEdge]) -> int:
        n = 0
        with self.engine.begin() as cx:
            for e in edges:
                meta = dict(e.metadata or {})
                edge_id = meta.pop("edge_id", None) or e.default_id()
                props = meta.pop("props", {}) or {}
                values = {"site_id": e.site_id, "edge_id": edge_id, "source_id": e.source, "target_id": e.target,
                          "edge_type": e.relation_type, "weight": e.weight, "props": dumps({**props, **meta})}
                self.upsert(cx, graph_edges, values, conflict=["site_id", "edge_id"])
                n += 1
        return n
