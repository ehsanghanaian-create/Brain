# SEO Brain (built on the SEO Knowledge Graph) — local-first, read-only by default

A local SEO knowledge graph for **emdadmodiran.com** (امداد مدیران), designed multi-site-ready (`site_id` everywhere).

| | |
|---|---|
| **What it does** | Snapshots WordPress (REST, read-only), crawls the site (robots-aware), caches Google Search Console, extracts entities (brands / models / services / locations) from real content, runs SEO analyses, materialises a graph in SQLite, writes an Obsidian vault, and exposes 21 read-only MCP tools to Claude Desktop plus a local dashboard. |
| **Guarantee** | The target website is never modified: the codebase contains no HTTP write verbs; MCP tools are read-only; acceptance test 10 checks both. |
| **Runtime** | Python 3.13 backend · Node 24 LTS + pnpm for `frontend/` (see `frontend/README.md`). SQLite (FTS5). Obsidian for humans, Claude Desktop (stdio MCP) for AI. |
| **Status** | v0.1 knowledge graph complete (`docs/final-report.md`, GSC live). **SEO Brain Phase 1 done** (`docs/seo-brain/`): restructured into `backend/` (FastAPI `/api/v1`, SQLAlchemy Core repositories, migrations, GraphStore, AI orchestrator + site memory, JobQueue). **Phase 1.5 + Phase 2 done**: API validated live (47/47), frontend contract, Next.js RTL/Persian dashboard foundation in `frontend/` (`docs/seo-brain/05-phase2-foundation.md`). **Phase 3 done**: sites wizard, connection tests, workspace init, Site Brain (`docs/seo-brain/06-phase3-sites.md`). **Phase 4 done**: React Flow SEO Command Center (`docs/seo-brain/07-phase4-graph.md`). **Phase 5 done**: Keyword Intelligence (`docs/seo-brain/08-phase5-keywords.md`). **Phase 6 done**: Content Brain foundation — workflow, briefs, Jalali calendar, AI providers with encrypted keys (`docs/seo-brain/09-phase6-content-brain.md`). **Phase 7 done**: Content Intelligence — scoring, review, revision loop with strict gate, analytics feedback → Site Brain memory (`docs/seo-brain/11-phase7-content-intelligence.md`). **Phase 8 done**: Internal Link Intelligence Engine — journey-aware explainable suggestions, health score, patterns → memory (`docs/seo-brain/13-phase8-internal-linking.md`). **Phase 9 done**: AI Content Generation & Agent Orchestration — provider gateway, task routing, versioned prompts, MemoryPack, 7-agent section-by-section pipeline with SSE, AI Studio, budget/learning; drafts only, no publishing (`docs/seo-brain/15-phase9-ai-orchestration.md`). Next: Phase 10. |

## Architecture

```
frontend/ (Next.js, RTL/fa) ─HTTP─▶ backend/seo_brain/api (FastAPI /api/v1) ─▶ services ─▶ repositories ─▶ data/seo.db (SQLite)
Claude Desktop ─stdio─▶ backend/mcp_server/server.py ─▶ seo_brain/graph/queries.py ─┘
                                                                   ▲
       WordPress REST (GET) ─┐                                     │
       Crawler (robots.txt)  ├─▶ seo_brain/normalizer ─▶ ingestion ──────┤
       GSC (OAuth, cached)  ─┘                                     │
                                          seo_brain/analysis (entities, SEO) ─┘
                                          seo_brain/graph/builder (nodes, edges, PageRank, communities)
                                          seo_brain/graph/obsidian_writer ─▶ obsidian/SEO-Knowledge-Graph/ (Graph View)
                                          seo_brain/dashboard ─▶ http://127.0.0.1:3000/
```
Full details: `docs/architecture.md` (v0.1) and `docs/seo-brain/01-architecture.md` (platform); audit & decisions: `docs/architecture-validation-report.md`.

## Installation

```powershell
cd seo-knowledge-graph
python -m venv .venv
.venv\Scripts\python -m pip install -e "backend[dev]"
.venv\Scripts\python backend\cli\setup.py --env --vault --db
notepad .env                        # WP app password (optional), Google OAuth client (for GSC) — never commit
.venv\Scripts\python backend\cli\preflight.py
```

## Configuration

* `.env` — secrets and paths (`.env.example` lists every key).
* `config/site.yaml` — per-site settings: crawler cap/concurrency/delay/robots, GSC lookback and dimensions, graph thresholds.
* `config/entities.yaml` (optional) — human overrides for entity aliases/types.

## Running

```powershell
.venv\Scripts\python backend\cli\sync-wordpress.py                 # WordPress → SQLite (+ data/raw/wordpress)
.venv\Scripts\python backend\cli\crawl.py --max-urls 20            # validation crawl, then:  --full
.venv\Scripts\python backend\cli\sync-gsc.py --auth-only           # once; then --days 1, then --days 30
.venv\Scripts\python backend\cli\build-graph.py --limit-pages 15   # first graph, then without the flag
.venv\Scripts\python backend\cli\setup.py --claude-config          # register the MCP server (backs up the config)
.venv\Scripts\python backend\cli\api.py                            # SEO Brain API http://127.0.0.1:8000/api/docs (legacy dashboard at /legacy)
.venv\Scripts\python backend\cli\migrate.py --status               # database migrations
```

## Components

* **WordPress** — `docs/wordpress.md`. Dynamic discovery of post types & taxonomies; Yoast metadata captured; GET only.
* **Crawler** — robots.txt via `protego`, sitemap-index seeding, BFS over same-site links, cap + concurrency 2 + 1 s delay; per URL: status, redirect chain, title, meta description, H1/H2, canonical, robots meta, X-Robots-Tag, indexability, word count, language, images/alt, internal/external links (nav vs body), ld+json schema, content hash, response time.
* **URL normalizer** — `backend/seo_brain/normalizer/url.py` (+ tests): scheme/host/trailing slash/fragments/duplicate slashes/percent-encoding (Persian slugs)/tracking params.
* **GSC** — `docs/gsc.md`. Official client, refresh token in `tokens/`, 1-day → 30-day lookback, incremental upserts, aggregation, importance flag; Claude never calls GSC.
* **Graph** — `docs/graph-schema.md`. Node/edge types per spec; only real relationships; PageRank + Louvain; FTS5 search.
* **Obsidian** — `docs/obsidian.md`. Vault layout `00-Sites … 99-Reports`; wikilinks == real edges; frontmatter == real data.
* **MCP** — `docs/mcp.md`. `mcp` SDK 2.0, stdio, 21 read-only tools, Claude Desktop config format verified.
* **SEO analysis** — orphans / zero & low inbound / high outbound / positions 4–15 / high-impression-low-CTR / duplicate titles & H1 / missing & multiple H1 / missing canonical / important non-indexable / thin content / cannibalization candidates / internal-link opportunities — each with an explainable `detail` or `score_breakdown`.
* **API (SEO Brain)** — `docs/seo-brain/02-phase1-implementation.md`: `/api/v1/{health,sites,sites/{id}/graph/*,sites/{id}/memory,ai/*,jobs}`; OpenAPI at `/api/docs`.
* **Legacy dashboard** — mounted at `/legacy` (also `backend/cli/dashboard.py`): Overview, Pages, Categories, Graph, GSC, Internal Links, SEO Problems, SEO Opportunities, Entities.

## Testing

```powershell
cd backend
..\.venv\Scripts\python -m pytest -q      # 46 tests: unit (normalizer, parser, GSC, migrations, graph store, AI orchestrator),
                                           # api (FastAPI v1), integration (MCP stdio), e2e (acceptance tests 1-10)
```

## Troubleshooting

`docs/troubleshooting.md`. Logs: `data/logs/*.jsonl` (structured, run IDs, secrets masked); Claude Desktop MCP logs: `%APPDATA%\Claude\logs\`.

## Security summary

`.env`, `tokens/`, `*.db`, `data/raw/`, generated vault notes are git-ignored · secrets masked in logs · MCP: stdio, localhost-only by construction, no file/SQL/credential tools · WordPress: GET only · dashboard binds 127.0.0.1.
