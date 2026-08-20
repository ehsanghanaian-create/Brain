"""GraphStore abstraction.

`GraphStore` is the contract every graph backend implements. `SqlGraphStore` (this file) is backed by the
SQL repository (SQLite now, PostgreSQL later); a `Neo4jGraphStore` can implement the same Protocol without
touching services, API or MCP. Analytics that need the whole graph in memory (PageRank, Louvain, paths) still
use networkx via `graph.queries` / `graph.builder` and will move behind this interface incrementally.
"""
from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable

from sqlalchemy import Engine

from ..db.repositories.graph import GraphRepository
from .model import GraphEdge, GraphNode, Subgraph


@runtime_checkable
class GraphStore(Protocol):
    def counts(self, site_id: str) -> dict: ...
    def get_node(self, site_id: str, node_id: str) -> GraphNode | None: ...
    def list_nodes(self, site_id: str, types: Iterable[str] | None = None, limit: int = 500, offset: int = 0) -> list[GraphNode]: ...
    def search(self, site_id: str, q: str, types: Iterable[str] | None = None, limit: int = 20) -> list[GraphNode]: ...
    def neighbors(self, site_id: str, node_id: str, relation_types: Iterable[str] | None = None,
                  direction: str = "both") -> Subgraph: ...
    def subgraph(self, site_id: str, center: str, hops: int = 1, relation_types: Iterable[str] | None = None,
                 max_nodes: int = 300) -> Subgraph: ...
    def upsert_nodes(self, nodes: Iterable[GraphNode]) -> int: ...
    def upsert_edges(self, edges: Iterable[GraphEdge]) -> int: ...


class SqlGraphStore:
    def __init__(self, engine: Engine):
        self.repo = GraphRepository(engine)

    def counts(self, site_id: str) -> dict:
        return self.repo.counts(site_id)

    def get_node(self, site_id: str, node_id: str) -> GraphNode | None:
        return self.repo.get_node(site_id, node_id)      # repo lookup is encoding-tolerant (WP encoded vs crawler decoded URLs)

    def list_nodes(self, site_id: str, types: Iterable[str] | None = None, limit: int = 500, offset: int = 0) -> list[GraphNode]:
        return self.repo.list_nodes(site_id, types, limit, offset)

    def search(self, site_id: str, q: str, types: Iterable[str] | None = None, limit: int = 20) -> list[GraphNode]:
        return self.repo.search_labels(site_id, q, types, limit)

    def neighbors(self, site_id: str, node_id: str, relation_types: Iterable[str] | None = None,
                  direction: str = "both") -> Subgraph:
        edges = self.repo.edges_of(site_id, [node_id], relation_types, direction)
        ids = {node_id} | {e.source for e in edges} | {e.target for e in edges}
        return Subgraph(nodes=self.repo.nodes_by_ids(site_id, ids), edges=edges, center=node_id, hops=1)

    def subgraph(self, site_id: str, center: str, hops: int = 1, relation_types: Iterable[str] | None = None,
                 max_nodes: int = 300) -> Subgraph:
        seen, frontier, edges = {center}, {center}, {}
        for _ in range(max(0, hops)):
            if not frontier or len(seen) >= max_nodes:
                break
            new_edges = self.repo.edges_of(site_id, frontier, relation_types, "both")
            frontier = set()
            for e in new_edges:
                key = (e.source, e.relation_type, e.target)
                if key in edges:
                    continue
                edges[key] = e
                for n in (e.source, e.target):
                    if n not in seen and len(seen) < max_nodes:
                        seen.add(n); frontier.add(n)
        # keep only edges whose both ends were admitted
        kept = [e for e in edges.values() if e.source in seen and e.target in seen]
        return Subgraph(nodes=self.repo.nodes_by_ids(site_id, seen), edges=kept, center=center, hops=hops)

    def upsert_nodes(self, nodes: Iterable[GraphNode]) -> int:
        return self.repo.upsert_nodes(nodes)

    def upsert_edges(self, edges: Iterable[GraphEdge]) -> int:
        return self.repo.upsert_edges(edges)


def get_graph_store(engine: Engine) -> GraphStore:
    """Factory: GRAPH_STORE=sql (default). Future: neo4j."""
    return SqlGraphStore(engine)
