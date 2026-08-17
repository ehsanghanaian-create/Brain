# SEO Brain — Phase 1 implementation report

Date: 2026-08-17 · Scope: restructure · migration system · SQLAlchemy Core repositories · GraphStore · AI orchestrator + memory · JobQueue · FastAPI skeleton · API tests · docs. **No frontend work** (per instruction).

## 1. Result

| Check | Result |
|---|---|
| Full test suite | **46 passed** (27 v0.1 tests unchanged in behaviour + 19 new: 4 migrations, 3 graph/memory/sites repos, 5 AI orchestrator/queue, 7 API) |
| Preflight | 24 PASS / 5 WARNING / 0 FAIL |
| MCP server (Claude Desktop) | still works from its new path; config re-registered (`backend/mcp_server/server.py`) |
| Real API boot | `python backend/cli/api.py --port 8011` → `/api/v1/health` OK, `/api/docs` 200, `/legacy/` 200, live graph summary 91 nodes / 356 edges |
| Live DB | adopted by the migration runner without changes: `schema_migrations` = 0001 (baseline), 0002 applied (site_memory, new `sites` columns, graph views) |

## 2. New repository layout (git history preserved with `git mv`)

```
seo-knowledge-graph/
├── backend/
│   ├── seo_brain/                    Python package (was src/)
│   │   ├── common/  crawler/  normalizer/  wordpress/  gsc/  analysis/  dashboard/   ← v0.1, imports rewritten
│   │   ├── database/                 v0.1 sqlite3 layer (init_db now delegates to db.migrate)
│   │   ├── db/                       NEW  engine.py · migrate.py · tables.py · repositories/{sites,graph,memory}.py
│   │   ├── graph/                    v0.1 builder/queries/obsidian_writer/vault + NEW model.py (Node/Edge) · store.py (GraphStore)
│   │   ├── ai/                       NEW  types · providers/base (AIProvider, EchoProvider) · router · validator · memory · orchestrator
│   │   ├── automation/               NEW  queue.py (JobQueue, InProcessJobQueue)
│   │   └── api/                      NEW  main.py · deps.py · schemas.py · routers/{health,sites,graph,memory,ai,jobs}.py
│   ├── mcp_server/server.py          (was mcp/server.py — renamed to avoid shadowing the `mcp` SDK package)
│   ├── cli/                          (was scripts/) + NEW api.py, migrate.py
│   ├── tests/                        unit/ integration/ e2e/ + NEW api/
│   └── pyproject.toml                package `seo-brain` 0.2.0 (+ sqlalchemy>=2)
├── database/migrations/              0001_init.sql (v0.1 schema, baseline) · 0002_site_memory_and_graph_views.sql
├── data/  config/  obsidian/  tokens/  .env   (unchanged locations; PROJECT_ROOT = repo root)
└── docs/seo-brain/                   01-architecture · 02-phase1-implementation (this) · phase2-prerequisites
```

Deviation from the design note: the temporary `src/` shim was **not needed** — every consumer (CLI, MCP, tests, dashboard) moved in the same commit and the suite proves it. `mcp/` became `mcp_server/` because a top-level `mcp` package would shadow the MCP SDK.

## 3. Components delivered

* **Migration system** — `seo_brain.db.migrate`: forward-only, numbered SQL files, `schema_migrations` table, idempotent (0001 is `IF NOT EXISTS`; `ALTER TABLE … ADD COLUMN` duplicates are tolerated), works on raw sqlite3 and SQLAlchemy engines (Postgres path splits statements and runs in one transaction). CLI: `backend/cli/migrate.py [--status]`. `init_db()` and the API startup both call it.
* **SQLAlchemy Core repositories** — `SitesRepository` (incl. `mode` guard), `GraphRepository`, `SiteMemoryRepository`, dialect-aware UPSERT (`sqlite`/`postgresql` `on_conflict_do_update`).
* **Graph model & store** — `GraphNode(id, site_id, type, metadata)`, `GraphEdge(source, target, relation_type, weight, metadata)`, `Subgraph`; `GraphStore` Protocol; `SqlGraphStore` (counts, get, list, search, neighbors, N-hop subgraph, upserts). Views `graph_nodes_v` / `graph_edges_v` in SQL for tooling.
* **AI orchestrator** — `AITask` → `AIRouter` (per-task / per-site chains, fallback) → `AIProvider.complete` → `Validator` (`NonEmpty`, `JsonKeys`, chain) → `MemoryService` (context injection; `record_success` only after validation, with provenance). `EchoProvider` = offline reference provider; result carries every attempt (provider, model, ok, error, latency).
* **Site memory** — table + service; injected as a `[site memory: <site>]` system message.
* **JobQueue** — Protocol + in-process threaded implementation; built-in job types `sync_wordpress`, `build_graph`, `noop` (mirror the CLI); Phase 8 persists runs and adds cron.
* **API (FastAPI, `/api/v1`)** — `GET /health` · `GET/POST /sites`, `GET/PATCH /sites/{id}` (creates `data/sites/<id>/{raw,exports,uploads,vault}`) · `/sites/{id}/graph/{summary,nodes,search,node/…,neighbors/…,subgraph,path,orphans}` · `/sites/{id}/memory` (`GET/PUT`, `/context`) · `/ai/{routes,providers}`, `POST /ai/sites/{id}/run` · `/jobs` (`GET`, `POST`, `GET /{run}`) · legacy dashboard at `/legacy` · OpenAPI at `/api/docs`. Auth: optional `API_TOKEN` (→ `X-API-Token`), CORS limited to `FRONTEND_ORIGIN` (default localhost:3000).

## 4. Guarantees kept

* Read-only: acceptance test 10 now scans everything except `seo_brain/api`, `seo_brain/dashboard` (our own server routes) and the future `seo_brain/integrations` writer module — no outbound HTTP write verbs anywhere else. WordPress publishing does not exist yet and every site defaults to `mode = manual`.
* Secrets: unchanged (`.env`, `tokens/` git-ignored; `API_TOKEN` optional).
* Obsidian vault + MCP tools: unchanged output (same DB, same builder).

## 5. Known tech debt (tracked, intentional)

1. `graph.queries` / `graph.builder` / ingestion still use `sqlite3` directly. Plan: move each function behind a repository when its phase touches it (graph analytics → Phase 4, opportunities → Phase 15). API graph endpoints already prefer `GraphStore`.
2. `SqlGraphStore.search` is substring-based; FTS5 search stays in `graph.queries.search_graph` (exposed side-by-side in `/graph/search`).
3. In-process job runs are not persisted (Phase 8).
4. Legacy dashboard links are absolute (`/pages` etc.), so under `/legacy` navigation links point at the root; it is still reachable stand-alone via `backend/cli/dashboard.py`. Removed at UI parity.

## 6. How to run

```powershell
.venv\Scripts\python -m pip install -e "backend[dev]"        # once
.venv\Scripts\python backend\cli\migrate.py --status
.venv\Scripts\python backend\cli\api.py                        # http://127.0.0.1:8000/api/docs
cd backend; ..\.venv\Scripts\python -m pytest -q               # 46 tests
```
All v0.1 commands moved from `scripts\` to `backend\cli\` (same names, same flags).

## 7. Next: Phase 2 (blocked until prerequisites are met)

See `phase2-prerequisites.md` — Node.js LTS is not installed and C: has < 1 GB free.
