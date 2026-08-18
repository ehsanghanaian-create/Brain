"""Neo4j-compatible graph model used across the platform (API, GraphStore, future Neo4j adapter).

Node:  id, site_id, type, metadata
Edge:  source, target, relation_type, weight, metadata   (+ site_id for multi-site scoping)

Node ids are stable strings of the form `<kind>:<key>` (e.g. `page:https://…/`, `query:امداد خودرو`),
identical to the v0.1 `graph_nodes.node_id`, so nothing already built has to be re-keyed.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

NODE_TYPES = ("SITE", "PAGE", "POST", "CATEGORY", "TAG", "BRAND", "MODEL", "SERVICE", "LOCATION", "QUERY",
              "SCHEMA", "SEO_PROBLEM", "SEO_OPPORTUNITY",
              # SEO Brain additions (phases 5-7)
              "KEYWORD", "TOPIC", "CONTENT")
RELATION_TYPES = ("HAS_PAGE", "HAS_POST", "HAS_CATEGORY", "HAS_TAG", "BELONGS_TO", "LINKS_TO", "ABOUT", "OFFERS",
                  "TARGETS", "RANKS_FOR", "HAS_SCHEMA", "HAS_PROBLEM", "HAS_OPPORTUNITY",
                  # SEO Brain additions
                  "KEYWORD_TARGETS", "CLUSTERED_IN", "CONTENT_FOR", "SUGGESTED_LINK", "PUBLISHED_AS",
                  # phase 8 internal linking
                  "LINK_OPPORTUNITY", "SUPPORTS")


@dataclass
class GraphNode:
    id: str
    site_id: str
    type: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return str(self.metadata.get("label") or self.id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GraphEdge:
    source: str
    target: str
    relation_type: str
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    site_id: str = ""

    def default_id(self) -> str:
        h = hashlib.sha1(f"{self.source}|{self.relation_type}|{self.target}".encode("utf-8")).hexdigest()[:16]
        return f"{self.relation_type.lower()}:{h}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Subgraph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    center: str | None = None
    hops: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"center": self.center, "hops": self.hops, "nodes": [n.to_dict() for n in self.nodes],
                "edges": [e.to_dict() for e in self.edges]}
