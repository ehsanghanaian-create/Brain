"""Graph view modes for the SEO Command Center (phase 4).

A *mode* is a curated slice of the site graph: which node types and relation types are shown, and how the UI
should lay it out. Modes are additive over the same GraphStore — nothing is duplicated in the DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..db.repositories.graph import GraphRepository
from .model import GraphEdge, GraphNode


@dataclass(frozen=True)
class GraphMode:
    key: str
    title_fa: str
    description_fa: str
    node_types: tuple[str, ...]
    relation_types: tuple[str, ...]
    layout: str            # "force" | "layered" | "radial" (hint for the UI)
    group_by: str          # default grouping: "type" | "community" | "none"


MODES: dict[str, GraphMode] = {
    "seo": GraphMode(
        key="seo", title_fa="نقشه سئو",
        description_fa="صفحات، کوئری‌ها/کلمات کلیدی، موجودیت‌ها، مشکلات و فرصت‌ها — چه چیزی برای چه چیزی رتبه دارد و کجا مشکل است",
        node_types=("SITE", "PAGE", "POST", "CATEGORY", "QUERY", "KEYWORD", "TOPIC", "BRAND", "MODEL", "SERVICE", "LOCATION", "SEO_PROBLEM", "SEO_OPPORTUNITY"),
        relation_types=("HAS_PAGE", "HAS_POST", "HAS_CATEGORY", "RANKS_FOR", "KEYWORD_TARGETS", "CLUSTERED_IN", "TARGETS", "ABOUT", "OFFERS", "HAS_PROBLEM", "HAS_OPPORTUNITY"),
        layout="force", group_by="type"),
    "content": GraphMode(
        key="content", title_fa="نقشه محتوا",
        description_fa="ساختار محتوایی: دسته‌ها، صفحات و نوشته‌ها، اسکیما، موضوعات و آیتم‌های محتوا",
        node_types=("SITE", "PAGE", "POST", "CATEGORY", "TAG", "SCHEMA", "TOPIC", "CONTENT", "KEYWORD"),
        relation_types=("HAS_PAGE", "HAS_POST", "HAS_CATEGORY", "HAS_TAG", "BELONGS_TO", "HAS_SCHEMA", "CLUSTERED_IN", "CONTENT_FOR", "PUBLISHED_AS", "KEYWORD_TARGETS"),
        layout="layered", group_by="type"),
    "links": GraphMode(
        key="links", title_fa="نقشه لینک داخلی",
        description_fa="لینک‌های داخلی بین صفحات (بدنه و ناوبری) و پیشنهادهای لینک — صفحات یتیم و ضعیف را نشان می‌دهد",
        node_types=("PAGE", "POST", "CATEGORY"),
        relation_types=("LINKS_TO", "SUGGESTED_LINK"),
        layout="force", group_by="community"),
}


@dataclass
class GraphView:
    mode: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool = False
    total_nodes: int = 0
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        m = MODES[self.mode]
        return {"mode": {"key": m.key, "title_fa": m.title_fa, "description_fa": m.description_fa, "layout": m.layout,
                         "group_by": m.group_by, "node_types": list(m.node_types), "relation_types": list(m.relation_types)},
                "nodes": [n.to_dict() for n in self.nodes], "edges": [e.to_dict() for e in self.edges],
                "truncated": self.truncated, "total_nodes": self.total_nodes, "stats": self.stats}


def graph_view(repo: GraphRepository, site_id: str, mode: str, types: Iterable[str] | None = None,
               relation_types: Iterable[str] | None = None, limit: int = 400, include_isolated: bool = True) -> GraphView:
    """Nodes of the mode (optionally narrowed by `types`), ranked by PageRank, capped at `limit`;
    then every edge of the mode's relation types whose both ends are in the set."""
    m = MODES[mode]
    node_types = [t for t in (types or m.node_types) if t in m.node_types] or list(m.node_types)
    rel_types = [r for r in (relation_types or m.relation_types) if r in m.relation_types] or list(m.relation_types)
    total = sum(n for t, n in repo.counts(site_id)["by_node_type"].items() if t in node_types)
    nodes = repo.list_nodes(site_id, node_types, limit=limit)
    ids = {n.id for n in nodes}
    edges = [e for e in repo.edges_of(site_id, ids, rel_types, "both") if e.source in ids and e.target in ids]
    if not include_isolated and mode == "links":
        linked = {e.source for e in edges} | {e.target for e in edges}
        nodes = [n for n in nodes if n.id in linked]
    stats = {"by_type": {}, "by_relation": {}}
    for n in nodes:
        stats["by_type"][n.type] = stats["by_type"].get(n.type, 0) + 1
    for e in edges:
        stats["by_relation"][e.relation_type] = stats["by_relation"].get(e.relation_type, 0) + 1
    return GraphView(mode=mode, nodes=nodes, edges=edges, truncated=total > len(nodes), total_nodes=total, stats=stats)
