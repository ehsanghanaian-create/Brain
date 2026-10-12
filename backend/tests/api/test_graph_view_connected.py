"""The default bounded graph should show actual relationships."""
from seo_brain.graph.model import GraphEdge, GraphNode
from seo_brain.graph.views import graph_view


def test_limited_graph_keeps_connected_cross_type_nodes():
    pages = [GraphNode(f"p:{i}", "one", "PAGE", {"label": f"Page {i}", "pagerank": 100 - i}) for i in range(70)]
    site = GraphNode("site:one", "one", "SITE", {"label": "Site", "pagerank": None})
    queries = [GraphNode(f"q:{i}", "one", "QUERY", {"label": f"Query {i}", "pagerank": None}) for i in range(10)]
    all_nodes = pages + [site] + queries
    all_edges = [GraphEdge("site:one", page.id, "HAS_PAGE", site_id="one") for page in pages]
    all_edges += [GraphEdge(page.id, queries[i % 10].id, "RANKS_FOR", site_id="one") for i, page in enumerate(pages)]

    class Repo:
        def counts(self, _):
            return {"by_node_type": {"SITE": 1, "PAGE": len(pages), "QUERY": len(queries)}}

        def list_nodes(self, _, types, limit):
            return sorted((node for node in all_nodes if node.type in types),
                          key=lambda node: (-(node.metadata.get("pagerank") or -1), node.id))[:limit]

        def edges_of(self, _, node_ids, relation_types, __):
            return [edge for edge in all_edges if edge.relation_type in relation_types and
                    (edge.source in node_ids or edge.target in node_ids)]

        def nodes_by_ids(self, _, ids):
            return [node for node in all_nodes if node.id in ids]

    view = graph_view(Repo(), "one", "seo", limit=30)
    ids = {node.id for node in view.nodes}
    assert len(ids) <= 30
    assert "site:one" in ids
    assert any(node.type == "QUERY" for node in view.nodes)
    assert view.edges and all(edge.source in ids and edge.target in ids for edge in view.edges)
    assert view.truncated and view.stats["sampled"] is True
