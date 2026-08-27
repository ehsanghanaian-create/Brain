"""SEO Knowledge Graph — local, READ-ONLY MCP server (stdio) for Claude Desktop.

Launch (Claude Desktop does this via claude_desktop_config.json):
    <project>/.venv/Scripts/python.exe  <project>/mcp/server.py

Security:
- stdio transport only (no network port) -> inherently local
- every tool is a read-only query over the local SQLite database
- no filesystem tools, no credentials, no .env access, no WordPress write paths exist in the codebase
- all logging goes to stderr/file, never stdout (stdout is the MCP channel)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("SEO_KG_ROOT") or Path(__file__).resolve().parents[2])
BACKEND = Path(__file__).resolve().parents[1]
for _p in (str(BACKEND), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.chdir(ROOT)

from mcp.server.mcpserver import MCPServer  # noqa: E402  (mcp>=2.0 API, verified 2026-08-16)
from mcp.types import ToolAnnotations  # noqa: E402

from seo_brain.common.config import get_site, load_sites  # noqa: E402
from seo_brain.common.logging_setup import setup_logging  # noqa: E402
from seo_brain.database.db import connect  # noqa: E402
from seo_brain.graph import queries as Q  # noqa: E402

log = setup_logging("mcp", stream=sys.stderr)
RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

server = MCPServer(
    name="seo-knowledge-graph",
    instructions=(
        "Local read-only SEO knowledge graph for the configured WordPress site(s). All data comes from the local SQLite "
        "database (WordPress REST snapshot, crawler, cached Google Search Console). Nothing here can modify the website. "
        "URLs may be given decoded (Persian) or percent-encoded; labels/titles also work as node references. "
        "If GSC has not been synced, GSC tools return status NO_GSC_DATA — say so instead of guessing."
    ),
    version="0.1.0",
)


def _conn():
    return connect()


def _sid(site_id: str | None) -> str:
    if site_id:
        return get_site(site_id).site_id
    configured = os.environ.get("SEO_BRAIN_DEFAULT_SITE")
    if configured:
        return get_site(configured).site_id

    # With multiple sites, alphabetical/config order is not a meaningful MCP
    # default. Prefer a site that has completed the usable WP → crawl → graph
    # path, then choose the richest snapshot deterministically.
    conn = _conn()
    try:
        row = conn.execute(
            """
            SELECT s.site_id,
                   (SELECT COUNT(*) FROM pages p WHERE p.site_id=s.site_id AND p.crawl_status='ok') AS crawled,
                   (SELECT COUNT(*) FROM posts w WHERE w.site_id=s.site_id) AS content,
                   (SELECT COUNT(*) FROM graph_nodes g WHERE g.site_id=s.site_id) AS graph_nodes
              FROM sites s
             ORDER BY CASE WHEN crawled > 0 AND content > 0 AND graph_nodes > 0 THEN 1 ELSE 0 END DESC,
                      crawled DESC, content DESC, graph_nodes DESC, s.site_id
             LIMIT 1
            """
        ).fetchone()
        return row[0] if row else get_site().site_id
    finally:
        conn.close()


def _run(fn, *args, **kwargs):
    conn = _conn()
    try:
        return fn(conn, *args, **kwargs)
    finally:
        conn.close()


# --- graph tools ------------------------------------------------------------------
@server.tool(annotations=RO, description="Full-text search over graph nodes (pages, posts, categories, brands, models, services, locations, queries, problems). Returns matching nodes with type, label, url.")
def search_graph(query: str, node_type: str | None = None, limit: int = 20, site_id: str | None = None) -> list[dict]:
    return _run(Q.search_graph, _sid(site_id), query, node_type, limit)


@server.tool(annotations=RO, description="Get one graph node with all its outgoing and incoming edges. `ref` may be a node_id, a URL, or a label/title.")
def get_node(ref: str, site_id: str | None = None) -> dict:
    return _run(Q.get_node, _sid(site_id), ref) or {"error": f"node not found: {ref}"}


@server.tool(annotations=RO, description="N-hop neighborhood of a node (depth 1-4). Optional edge_types filter e.g. ['LINKS_TO'] or ['ABOUT','BELONGS_TO']; direction in|out|both.")
def get_neighbors(ref: str, depth: int = 1, edge_types: list[str] | None = None, direction: str = "both", limit: int = 100, site_id: str | None = None) -> dict:
    return _run(Q.get_neighbors, _sid(site_id), ref, depth, edge_types, direction, limit)


@server.tool(annotations=RO, description="Subgraph filtered by node types (e.g. ['PAGE','POST','CATEGORY']) and/or edge types (e.g. ['LINKS_TO']). Nodes ordered by PageRank.")
def get_subgraph(node_types: list[str] | None = None, edge_types: list[str] | None = None, limit: int = 300, site_id: str | None = None) -> dict:
    return _run(Q.get_subgraph, _sid(site_id), node_types, edge_types, limit)


@server.tool(annotations=RO, description="Find paths between two nodes (shortest + up to N simple paths). Use edge_types=['LINKS_TO'] for the pure internal-link path (click path); leave empty to include taxonomy/entity relations, e.g. how page X relates to car model Y.")
def find_path(source: str, target: str, edge_types: list[str] | None = None, max_paths: int = 3, max_depth: int = 6, site_id: str | None = None) -> dict:
    return _run(Q.find_path, _sid(site_id), source, target, edge_types, max_paths, max_depth)


# --- SEO tools --------------------------------------------------------------------
@server.tool(annotations=RO, description="Orphan pages: indexable pages with zero internal inbound links in the real crawled link graph. include_nav_only=true also lists pages that only receive navigation/footer links (no contextual links).")
def find_orphans(include_nav_only: bool = False, limit: int = 100, site_id: str | None = None) -> list[dict]:
    return _run(Q.find_orphans, _sid(site_id), include_nav_only, limit)


@server.tool(annotations=RO, description="Cannibalization CANDIDATES (not confirmed): queries where multiple pages rank with meaningful impressions, similar positions and similar titles. Requires GSC data.")
def find_cannibalization(min_confidence: float = 0.0, limit: int = 50, site_id: str | None = None) -> list[dict] | dict:
    sid = _sid(site_id)
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM gsc_query_page WHERE site_id=? LIMIT 1", (sid,)).fetchone():
            return {"status": "NO_GSC_DATA", "note": "Cannibalization analysis needs Google Search Console data; GSC has not been synced yet.", "candidates": []}
        return Q.find_cannibalization(conn, sid, min_confidence, limit)
    finally:
        conn.close()


@server.tool(annotations=RO, description="Internal linking opportunities: source page -> target page with potential anchor, reason, confidence and an explainable score. `page` filters by source page (or by target page when as_target=true).")
def find_internal_link_opportunities(page: str | None = None, as_target: bool = False, limit: int = 30, site_id: str | None = None) -> list[dict]:
    return _run(Q.find_internal_link_opportunities, _sid(site_id), page, as_target, limit)


@server.tool(annotations=RO, description="Cached GSC metrics per page (clicks, impressions, CTR, weighted position). Filter by position range (e.g. min_position=4,max_position=15) or min_impressions; order_by impressions|clicks|position|ctr.")
def get_gsc_page_data(page: str | None = None, min_position: float | None = None, max_position: float | None = None, min_impressions: int = 0,
                      order_by: str = "impressions", limit: int = 50, site_id: str | None = None) -> dict:
    return _run(Q.get_gsc_page_data, _sid(site_id), page, min_position, max_position, min_impressions, order_by, limit)


@server.tool(annotations=RO, description="Cached GSC metrics per query (optionally for one page). important_only=true limits to strategically important queries. Filter by position range / min_impressions.")
def get_gsc_query_data(query: str | None = None, page: str | None = None, min_impressions: int = 0, min_position: float | None = None,
                       max_position: float | None = None, important_only: bool = False, order_by: str = "impressions", limit: int = 50, site_id: str | None = None) -> dict:
    return _run(Q.get_gsc_query_data, _sid(site_id), query, page, min_impressions, min_position, max_position, important_only, order_by, limit)


@server.tool(annotations=RO, description="Everything known about one page: crawl data (title, H1s, canonical, robots, indexability, word count, schema), WordPress data, inbound/outbound links, entities, GSC metrics, problems and opportunities.")
def get_page_seo_data(page: str, site_id: str | None = None) -> dict:
    return _run(Q.get_page_seo_data, _sid(site_id), page) or {"error": f"page not found: {page}"}


@server.tool(annotations=RO, description="Site structure: pages, category tree with posts, custom post types, extracted entities (service, brands, models, locations) and counts.")
def get_site_structure(site_id: str | None = None) -> dict:
    return _run(Q.get_site_structure, _sid(site_id))


@server.tool(annotations=RO, description="List categories (name, slug, url, parent, post count, indexability).")
def get_categories(site_id: str | None = None) -> list[dict]:
    return _run(Q.get_categories, _sid(site_id))


@server.tool(annotations=RO, description="Car models extracted from the site (with parent brand, aliases, evidence and the pages about them).")
def get_models(site_id: str | None = None) -> list[dict]:
    return _run(Q.list_entities, _sid(site_id), "MODEL")


@server.tool(annotations=RO, description="Car brands extracted from the site (with hierarchy, aliases, evidence and the pages about them).")
def get_brands(site_id: str | None = None) -> list[dict]:
    return _run(Q.list_entities, _sid(site_id), "BRAND")


@server.tool(annotations=RO, description="Services extracted from the site (with evidence and pages).")
def get_services(site_id: str | None = None) -> list[dict]:
    return _run(Q.list_entities, _sid(site_id), "SERVICE")


@server.tool(annotations=RO, description="Locations extracted from the site (with evidence and pages).")
def get_locations(site_id: str | None = None) -> list[dict]:
    return _run(Q.list_entities, _sid(site_id), "LOCATION")


@server.tool(annotations=RO, description="Technical/on-page SEO problems (orphan, missing_h1, multiple_h1, duplicate_title, duplicate_h1, missing_canonical, important_non_indexable, thin_content, low_inbound_links, no_body_inbound_links, missing_meta_description, images_missing_alt, redirect_in_sitemap). Filter by type/severity/page.")
def get_seo_problems(problem_type: str | None = None, severity: str | None = None, page: str | None = None, limit: int = 100, site_id: str | None = None) -> dict:
    return _run(Q.get_seo_problems, _sid(site_id), problem_type, severity, page, limit)


@server.tool(annotations=RO, description="SEO opportunities with explainable scores: striking_distance (positions 4-15), ctr_opportunity (high impressions / low CTR), cannibalization_candidate, internal_link. Filter by type/page/min_score.")
def get_seo_opportunities(opp_type: str | None = None, page: str | None = None, min_score: float = 0.0, limit: int = 50, site_id: str | None = None) -> dict:
    return _run(Q.get_seo_opportunities, _sid(site_id), opp_type, page, min_score, limit)


@server.tool(annotations=RO, description="Site summary: counts (crawled/indexable URLs, WP pages/posts/CPTs, categories, tags, links, entities, GSC rows, problems, opportunities, graph nodes/edges), GSC status, last runs. Start here.")
def get_site_summary(site_id: str | None = None) -> dict:
    return _run(Q.get_site_summary, _sid(site_id))


@server.tool(annotations=RO, description="List configured sites (site_id, name, url).")
def list_sites() -> list[dict]:
    return [{"site_id": s.site_id, "name": s.name, "url": s.canonical_url, "language": s.language} for s in load_sites()]


if __name__ == "__main__":
    log.info(f"starting seo-knowledge-graph MCP server (stdio) root={ROOT}")
    server.run("stdio")
