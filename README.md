# SEO Knowledge Graph — local-first, read-only

A local SEO knowledge graph for **emdadmodiran.com** (امداد مدیران), designed multi-site-ready (`site_id` everywhere).

| | |
|---|---|
| **What it does** | Snapshots WordPress (REST, read-only), crawls the site (robots-aware), caches Google Search Console, extracts entities (brands / models / services / locations) from real content, runs SEO analyses, materialises a graph in SQLite, writes an Obsidian vault, and exposes 21 read-only MCP tools to Claude Desktop plus a local dashboard. |
| **Guarantee** | The target website is never modified: the codebase contains no HTTP write verbs; MCP tools are read-only; acceptance test 10 checks both. |
| **Runtime** | Python 3.13 (single runtime; Node.js not needed). SQLite (FTS5). Obsidian for humans, Claude Desktop (stdio MCP) for AI. |
| **Status** | See `docs/phase-log.md` and `docs/final-report.md`. GSC live sync is **blocked** until you supply Google OAuth credentials (`docs/gsc.md`). |

## Architecture

```
Claude Desktop ─stdio─▶ mcp/server.py ─▶ src/graph/queries.py ─▶ data/seo.db (SQLite)
                                                                   ▲
       WordPress REST (GET) ─┐                                     │
       Crawler (robots.txt)  ├─▶ src/normalizer ─▶ ingestion ──────┤
       GSC (OAuth, cached)  ─┘                                     │
                                          src/analysis (entities, SEO) ─┘
                                          src/graph/builder (nodes, edges, PageRank, communities)
                                          src/graph/obsidian_writer ─▶ obsidian/SEO-Knowledge-Graph/ (Graph View)
                                          src/dashboard ─▶ http://127.0.0.1:3000/
```
Full details: `docs/architecture.md`; audit & decisions: `docs/architecture-validation-report.md`.

## Installation

```powershell
cd seo-knowledge-graph
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python scripts\setup.py --env --vault --db
notepad .env                        # WP app password (optional), Google OAuth client (for GSC) — never commit
.venv\Scripts\python scripts\preflight.py
```

## Configuration

* `.env` — secrets and paths (`.env.example` lists every key).
* `config/site.yaml` — per-site settings: crawler cap/concurrency/delay/robots, GSC lookback and dimensions, graph thresholds.
* `config/entities.yaml` (optional) — human overrides for entity aliases/types.

## Running

```powershell
.venv\Scripts\python scripts\sync-wordpress.py                 # WordPress → SQLite (+ data/raw/wordpress)
.venv\Scripts\python scripts\crawl.py --max-urls 20            # validation crawl, then:  --full
.venv\Scripts\python scripts\sync-gsc.py --auth-only           # once; then --days 1, then --days 30
.venv\Scripts\python scripts\build-graph.py --limit-pages 15   # first graph, then without the flag
.venv\Scripts\python scripts\setup.py --claude-config          # register the MCP server (backs up the config)
.venv\Scripts\python scripts\dashboard.py                      # http://127.0.0.1:3000/
```

## Components

* **WordPress** — `docs/wordpress.md`. Dynamic discovery of post types & taxonomies; Yoast metadata captured; GET only.
* **Crawler** — robots.txt via `protego`, sitemap-index seeding, BFS over same-site links, cap + concurrency 2 + 1 s delay; per URL: status, redirect chain, title, meta description, H1/H2, canonical, robots meta, X-Robots-Tag, indexability, word count, language, images/alt, internal/external links (nav vs body), ld+json schema, content hash, response time.
* **URL normalizer** — `src/normalizer/url.py` (+ tests): scheme/host/trailing slash/fragments/duplicate slashes/percent-encoding (Persian slugs)/tracking params.
* **GSC** — `docs/gsc.md`. Official client, refresh token in `tokens/`, 1-day → 30-day lookback, incremental upserts, aggregation, importance flag; Claude never calls GSC.
* **Graph** — `docs/graph-schema.md`. Node/edge types per spec; only real relationships; PageRank + Louvain; FTS5 search.
* **Obsidian** — `docs/obsidian.md`. Vault layout `00-Sites … 99-Reports`; wikilinks == real edges; frontmatter == real data.
* **MCP** — `docs/mcp.md`. `mcp` SDK 2.0, stdio, 21 read-only tools, Claude Desktop config format verified.
* **SEO analysis** — orphans / zero & low inbound / high outbound / positions 4–15 / high-impression-low-CTR / duplicate titles & H1 / missing & multiple H1 / missing canonical / important non-indexable / thin content / cannibalization candidates / internal-link opportunities — each with an explainable `detail` or `score_breakdown`.
* **Dashboard** — Overview, Pages, Categories, Graph, GSC, Internal Links, SEO Problems, SEO Opportunities, Entities, JSON API (`/api/docs`).

## Testing

```powershell
.venv\Scripts\python -m pytest -q tests\unit          # normalizer, parser, GSC storage/aggregation
.venv\Scripts\python -m pytest -q tests\integration   # MCP server over stdio (tool list, read-only annotations, no secrets)
.venv\Scripts\python -m pytest -q tests\e2e           # acceptance tests 1-10 (spec §65)
```

## Troubleshooting

`docs/troubleshooting.md`. Logs: `data/logs/*.jsonl` (structured, run IDs, secrets masked); Claude Desktop MCP logs: `%APPDATA%\Claude\logs\`.

## Security summary

`.env`, `tokens/`, `*.db`, `data/raw/`, generated vault notes are git-ignored · secrets masked in logs · MCP: stdio, localhost-only by construction, no file/SQL/credential tools · WordPress: GET only · dashboard binds 127.0.0.1.
