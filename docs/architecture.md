# Architecture

Local-first, read-only SEO knowledge graph. One runtime (Python 3.13), one database (SQLite), one vault (Obsidian), one AI interface (Claude Desktop via stdio MCP).

```
CLAUDE DESKTOP ──stdio──▶ backend/mcp_server/server.py (MCPServer, read-only tools)
                               │ backend/seo_brain/graph/queries.py (shared read-only query API)
                               ▼
                    data/seo.db (SQLite, WAL, FTS5)  ◀── backend/seo_brain/database/schema.sql
                               ▲
      ┌──────────────┬─────────┴──────────┬────────────────┐
 backend/seo_brain/wordpress/   backend/seo_brain/crawler/         backend/seo_brain/gsc/        backend/seo_brain/analysis/ (entities, seo)
 REST GET only    robots-aware BFS     OAuth+cache     backend/seo_brain/graph/builder.py (nodes/edges, PageRank, Louvain)
      └──────────────┴─────── backend/seo_brain/normalizer/url.py (URL identity) ──────────┘
                               │
                    backend/seo_brain/graph/obsidian_writer.py ──▶ obsidian/SEO-Knowledge-Graph/ (markdown + wikilinks)
                    backend/seo_brain/dashboard/app.py ──▶ http://127.0.0.1:3000/
```

## Layers and responsibilities

| Layer | Module | Writes to | Notes |
|---|---|---|---|
| Config | `backend/seo_brain/common/config.py` | — | `.env` (secrets) + `config/site.yaml` (per-site, `site_id`) |
| Logging | `backend/seo_brain/common/logging_setup.py` | `data/logs/*.jsonl` | run IDs (`crawl-…`, `wp-…`, `gsc-…`, `graph-…`, `analysis-…`), secret masking |
| HTTP | `backend/seo_brain/common/http.py` | — | GET-only client; retry, exponential backoff, rate limit |
| Normalizer | `backend/seo_brain/normalizer/url.py` | — | single definition of URL identity |
| WordPress | `backend/seo_brain/wordpress/` | `posts, categories, tags, taxonomies, post_terms, media, sync_runs` + `data/raw/wordpress` | dynamic discovery of post types/taxonomies; public endpoints; optional Application Password |
| Crawler | `backend/seo_brain/crawler/` | `pages, links, schemas, crawl_runs` + `data/raw/crawler` | robots.txt (protego), sitemaps, same-site only, cap, concurrency 2, 1s delay |
| GSC | `backend/seo_brain/gsc/` | `gsc_daily, gsc_query_page, queries, sync_runs` + `data/raw/gsc` | official client; refresh token in `tokens/`; Claude never calls GSC |
| Analysis | `backend/seo_brain/analysis/` | `entities, entity_mentions, seo_problems, seo_opportunities` | rule-based, evidence recorded, explainable scores |
| Graph | `backend/seo_brain/graph/builder.py` | `graph_nodes, graph_edges, graph_fts` | only real relationships become edges; PageRank (pure Python), Louvain (networkx) |
| Obsidian | `backend/seo_brain/graph/obsidian_writer.py` | vault markdown | wikilinks == real edges; frontmatter == real data |
| MCP | `backend/mcp_server/server.py` | — | 21 read-only tools, stdio |
| Dashboard | `backend/seo_brain/dashboard/app.py` | — | FastAPI on 127.0.0.1:3000 |

## Data flow / run order

`sync-wordpress` → `crawl` → (`sync-gsc`) → `build-graph` (entities → analysis → graph → Obsidian) → MCP/dashboard read.

## Multi-site

Every table and node carries `site_id`; `config/site.yaml` holds a list of sites; scripts accept `--site`. Only `emdadmodiran` is configured in Phase 1.

## Future integration hooks (not implemented)

`backend/seo_brain/gsc/` shows the connector pattern (client + sync + raw dir + sync_runs). GA4 / Google Ads / SERP / backlinks / PageSpeed / CWV connectors would follow the same shape and write their own tables; the graph builder would add edges from those tables. URL Inspection: would need a queue table + rate limiter + cache (see `docs/gsc.md`).

## Read-only guarantee

* WordPress: `ReadOnlyClient` exposes only `get()`; `WordPressClient` has no write method.
* MCP: tools are `get_*`, `find_*`, `search_*`, `list_*`; annotated `read_only_hint=True`; integration test asserts no forbidden names.
* No tool exposes files, `.env`, tokens or arbitrary SQL.
