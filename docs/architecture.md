# Architecture

Local-first, read-only SEO knowledge graph. One runtime (Python 3.13), one database (SQLite), one vault (Obsidian), one AI interface (Claude Desktop via stdio MCP).

```
CLAUDE DESKTOP ──stdio──▶ mcp/server.py (MCPServer, read-only tools)
                               │ src/graph/queries.py (shared read-only query API)
                               ▼
                    data/seo.db (SQLite, WAL, FTS5)  ◀── src/database/schema.sql
                               ▲
      ┌──────────────┬─────────┴──────────┬────────────────┐
 src/wordpress/   src/crawler/         src/gsc/        src/analysis/ (entities, seo)
 REST GET only    robots-aware BFS     OAuth+cache     src/graph/builder.py (nodes/edges, PageRank, Louvain)
      └──────────────┴─────── src/normalizer/url.py (URL identity) ──────────┘
                               │
                    src/graph/obsidian_writer.py ──▶ obsidian/SEO-Knowledge-Graph/ (markdown + wikilinks)
                    src/dashboard/app.py ──▶ http://127.0.0.1:3000/
```

## Layers and responsibilities

| Layer | Module | Writes to | Notes |
|---|---|---|---|
| Config | `src/common/config.py` | — | `.env` (secrets) + `config/site.yaml` (per-site, `site_id`) |
| Logging | `src/common/logging_setup.py` | `data/logs/*.jsonl` | run IDs (`crawl-…`, `wp-…`, `gsc-…`, `graph-…`, `analysis-…`), secret masking |
| HTTP | `src/common/http.py` | — | GET-only client; retry, exponential backoff, rate limit |
| Normalizer | `src/normalizer/url.py` | — | single definition of URL identity |
| WordPress | `src/wordpress/` | `posts, categories, tags, taxonomies, post_terms, media, sync_runs` + `data/raw/wordpress` | dynamic discovery of post types/taxonomies; public endpoints; optional Application Password |
| Crawler | `src/crawler/` | `pages, links, schemas, crawl_runs` + `data/raw/crawler` | robots.txt (protego), sitemaps, same-site only, cap, concurrency 2, 1s delay |
| GSC | `src/gsc/` | `gsc_daily, gsc_query_page, queries, sync_runs` + `data/raw/gsc` | official client; refresh token in `tokens/`; Claude never calls GSC |
| Analysis | `src/analysis/` | `entities, entity_mentions, seo_problems, seo_opportunities` | rule-based, evidence recorded, explainable scores |
| Graph | `src/graph/builder.py` | `graph_nodes, graph_edges, graph_fts` | only real relationships become edges; PageRank (pure Python), Louvain (networkx) |
| Obsidian | `src/graph/obsidian_writer.py` | vault markdown | wikilinks == real edges; frontmatter == real data |
| MCP | `mcp/server.py` | — | 21 read-only tools, stdio |
| Dashboard | `src/dashboard/app.py` | — | FastAPI on 127.0.0.1:3000 |

## Data flow / run order

`sync-wordpress` → `crawl` → (`sync-gsc`) → `build-graph` (entities → analysis → graph → Obsidian) → MCP/dashboard read.

## Multi-site

Every table and node carries `site_id`; `config/site.yaml` holds a list of sites; scripts accept `--site`. Only `emdadmodiran` is configured in Phase 1.

## Future integration hooks (not implemented)

`src/gsc/` shows the connector pattern (client + sync + raw dir + sync_runs). GA4 / Google Ads / SERP / backlinks / PageSpeed / CWV connectors would follow the same shape and write their own tables; the graph builder would add edges from those tables. URL Inspection: would need a queue table + rate limiter + cache (see `docs/gsc.md`).

## Read-only guarantee

* WordPress: `ReadOnlyClient` exposes only `get()`; `WordPressClient` has no write method.
* MCP: tools are `get_*`, `find_*`, `search_*`, `list_*`; annotated `read_only_hint=True`; integration test asserts no forbidden names.
* No tool exposes files, `.env`, tokens or arbitrary SQL.
