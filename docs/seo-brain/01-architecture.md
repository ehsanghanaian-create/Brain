# SEO Brain Platform — Phase 1: Architecture Design

Status: **DRAFT for approval** · Date: 2026-08-17 · Basis: the working `seo-knowledge-graph` v0.1 (91 nodes / 356 edges, GSC live, 27/27 tests).

---

## 0. Ground rules carried over from v0.1 (non-negotiable)

1. **Nothing that works today breaks.** The migration is additive: v0.1 scripts, MCP server, Obsidian vault and tests keep passing at every commit.
2. **Read-only by default.** Today the codebase contains no HTTP write verbs (acceptance test 10). The Brain will need writes (WordPress publish, Phase 16). Writes are therefore isolated in ONE adapter module, disabled unless a site is explicitly put in *Assisted* or *Auto-Pilot* mode, and every write is audit-logged. Test 10 evolves to: "no write verbs outside `backend/app/integrations/wordpress/writer.py`".
3. **Real data only.** Every UI number traces to a table row; every graph edge to a real relationship; AI outputs are stored *as AI outputs* (provenance = model, prompt version, timestamp), never mixed into crawled/GSC facts.
4. **`site_id` on every row**, workspace-per-site on disk.
5. **Local-first, server-ready**: same code runs on this laptop (SQLite, in-process scheduler) and later in Docker (Postgres, Redis workers) by changing config only.

---

## 1. Environment facts that shape the design (verified today)

| Fact | Impact |
|---|---|
| Node.js / npm **not installed** | Phase 2 (Next.js) cannot start until Node LTS is installed (~120 MB) — needs your go-ahead (installer download). |
| **C: free space ≈ 675 MB** (fluctuating 82 MB–2.6 GB over the last day) | A Next.js app + `node_modules` needs **≥ 1.5 GB**; a comfortable dev setup ≥ 3–5 GB. **Blocking for Phase 2** — space must be freed (or the project moved to another drive) before UI work. |
| Python 3.13 venv, FastAPI/uvicorn already installed | Backend can be built immediately, no new runtime. |
| Windows 11, Claude Desktop registered to `mcp/server.py` by absolute path | If files move, the Claude Desktop config must be re-registered (`scripts/setup.py --claude-config` already does this). |
| Obsidian vault is generated from the DB | Vault stays a *view*; the UI becomes the second view. Neither is a source of truth. |

---

## 2. Target repository layout

```
seo-knowledge-graph/                 (repo name unchanged; product name "SEO Brain")
├── frontend/                        Next.js 15 · TypeScript · Tailwind · shadcn/ui · React Flow (Phase 2+)
│   ├── app/(dashboard)/…            one route group per menu item
│   ├── components/                  ui/ (shadcn), graph/, calendar/, kanban/, forms/
│   ├── lib/api/                     generated TS client from backend OpenAPI (openapi-typescript)
│   ├── lib/i18n/fa.ts               Persian strings; RTL via <html dir="rtl">
│   └── messages/, styles/
├── backend/                         Python (the existing code moves here, package `seo_brain`)
│   ├── seo_brain/
│   │   ├── core/                    ← src/common (config, http, logging) + settings/secrets
│   │   ├── db/                      ← src/database (connection, migrations runner, repositories/)
│   │   ├── ingestion/               ← src/wordpress (read), src/crawler, src/normalizer, src/gsc, + ga4/
│   │   ├── graph/                   ← src/graph (builder, queries, obsidian_writer, vault) + GraphStore interface
│   │   ├── analysis/                ← src/analysis (entities, seo) + opportunities/, linking/ (Phase 13-15)
│   │   ├── brain/                   NEW: keywords/, content/, calendar/, briefs/ (Phase 5-7, 12)
│   │   ├── ai/                      NEW: providers/, router.py, prompts/, usage log (Phase 9-11)
│   │   ├── automation/              NEW: scheduler.py (APScheduler now), jobs/, pipeline.py (Phase 8)
│   │   ├── integrations/wordpress/  NEW: writer.py — the ONLY module allowed to POST/PUT (Phase 16)
│   │   ├── reports/                 NEW: builders (md/pdf) (Phase 17)
│   │   └── api/                     FastAPI app: main.py, deps.py, routers/<menu>.py, schemas/ (Pydantic)
│   ├── mcp/server.py                ← mcp/ (unchanged behaviour; imports seo_brain.graph.queries)
│   ├── cli/                         ← scripts/ (thin wrappers; also exposed as `seo-brain <cmd>`)
│   ├── tests/                       ← tests/ (+ api tests)
│   └── pyproject.toml               ← moved; package name `seo-brain`
├── database/
│   ├── migrations/0001_init.sql …   numbered, forward-only SQL (SQLite dialect kept Postgres-compatible)
│   ├── schema.sql                   generated snapshot (for docs/reference)
│   └── seeds/                       optional demo data (never real secrets)
├── data/                            runtime, git-ignored
│   ├── seo.db                       (single DB, all sites, `site_id` scoped)
│   ├── sites/<domain>/              workspace: raw/, exports/, vault/ (Obsidian), uploads/
│   ├── logs/                        structured jsonl
│   └── secrets/                     encrypted store (see §7)
├── docs/                            existing docs + docs/seo-brain/<phase>.md + user help (fa)
├── config/                          site.yaml (per-site defaults) — later superseded by DB `sites` rows
├── obsidian/                        → becomes a symlink/pointer to data/sites/<domain>/vault (kept for compatibility)
├── docker/                          compose.yaml, Dockerfile.backend, Dockerfile.frontend, Dockerfile.worker (Phase 19)
└── Makefile / justfile              dev shortcuts
```

**Migration mechanics (Phase 1 implementation, after approval):** `git mv src → backend/seo_brain/*` with `git mv` so history survives; a compatibility shim package `src/` re-exporting from `seo_brain` for one release, so `scripts/*.py`, `mcp/server.py` and tests keep working, then scripts are moved and the shim removed. Re-register the Claude Desktop MCP path. Run the full test suite after each step.

---

## 3. Layered architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│ FRONTEND  Next.js (RTL, fa, dark)  ── React Query ── generated TS client   │
└──────────────────────────────┬─────────────────────────────────────────────┘
                               │ HTTP JSON  http://127.0.0.1:8000/api/v1  (+ SSE for job progress)
┌──────────────────────────────▼─────────────────────────────────────────────┐
│ API LAYER  FastAPI · routers per domain · Pydantic schemas · auth token     │
│   /sites /graph /keywords /content /calendar /ai /links /opportunities      │
│   /reports /jobs /settings /help                                            │
├────────────────────────────────────────────────────────────────────────────┤
│ SERVICE / DOMAIN LAYER  (pure Python, no HTTP)                              │
│   ingestion · graph · analysis · brain · ai · automation · integrations     │
│   Interfaces:  GraphStore · AIProvider · Scheduler/JobQueue · SecretStore   │
├────────────────────────────────────────────────────────────────────────────┤
│ DATA LAYER  repositories/ (SQL kept in one place per aggregate)             │
│   now: SQLite + FTS5 · later: PostgreSQL (+ pgvector) · Neo4j via GraphStore│
└────────────────────────────────────────────────────────────────────────────┘
        ▲                         ▲                          ▲
   MCP server (Claude)      CLI (cron/Task Scheduler)   Obsidian vault writer
   (same service layer)      (same service layer)        (view, regenerated)
```

Rules: routers never touch SQL; services never import FastAPI; the MCP server and CLI call the same services as the API (single implementation of every capability).

### 3.1 Interfaces that make "future server" a config change

| Interface | Local implementation (now) | Server implementation (later) |
|---|---|---|
| `GraphStore` (`upsert_nodes/edges`, `neighbors`, `subgraph`, `path`, `pagerank`) | SQLite tables + networkx in-process | Neo4j driver |
| `JobQueue` / `Scheduler` | APScheduler inside the API process, jobs table in SQLite | Redis + RQ/arq workers, same jobs table in Postgres |
| `SecretStore` | Windows DPAPI-encrypted file `data/secrets/*.bin` | env/secret manager (Docker secrets, Vault) |
| `Database` | `sqlite3` with WAL, migrations runner | `psycopg` — same SQL (ANSI subset; FTS5 → `tsvector` behind the repository) |
| `AIProvider` | Claude / OpenAI / Gemini / OpenRouter / Ollama / Custom via one `complete()` contract | identical |
| `Publisher` | WordPress REST writer (modes) | identical |

---

## 4. Domain model (additions to the 21 existing tables)

All new tables carry `site_id`, `created_at`, `updated_at`; AI-generated rows carry `provenance` JSON (`provider, model, prompt_id, prompt_version, run_id, tokens, cost`).

| Area (Phase) | Tables | Notes |
|---|---|---|
| Sites (3) | `sites` (extend: business_type, language, country, mode = manual/assisted/autopilot, gsc_property, ga4_property, workspace_path), `site_connections` (kind, status, last_ok_at) | wizard writes here; secrets NOT here |
| Keywords (5) | `keywords` (keyword, intent, volume, difficulty, priority, target_url, status, source), `keyword_clusters`, `keyword_cluster_members`, `keyword_relations` (type, weight), `imports` (file, mapping, rows, errors) | CSV/XLSX/Sheet-export importer with column mapping UI |
| Content Brain (6) | `content_items` (title, slug, stage: idea→published, keyword_id, brief_id, assignee, due_at, wp_post_id), `content_versions` (markdown, source: ai/human, provenance), `content_events` (stage transitions) | Kanban = `content_items` grouped by stage |
| Calendar (7) | `calendar_entries` (date, time, site_id, keyword_id, content_item_id, title, h1, h2 JSON, priority, status) | drag&drop = update date/time |
| Automation (8) | `jobs` (type, payload, schedule cron, enabled), `job_runs` (status, log_path, started/finished, result JSON), `pipeline_steps` | SSE stream of `job_runs` to UI |
| AI (9-11) | `ai_providers` (kind, base_url, secret_ref, enabled), `ai_models` (provider_id, model, capabilities, cost), `ai_routes` (task → model, fallback chain), `prompts`, `prompt_versions` (template, variables[]), `ai_calls` (usage/cost log) | secret_ref points into SecretStore |
| Briefs (12) | `content_briefs` (seo_title, meta, h1, h2/h3 JSON, faq JSON, entities[], schema JSON, internal_links[], intent, markdown) | markdown export |
| Linking (13-14) | `link_suggestions` (source, target, anchor, reason, score, status accepted/rejected/applied), `link_patterns` (source_type → target_type, support, confidence, examples[]) | patterns learned from `links` + `graph_edges` |
| Opportunities (15) | extend `seo_opportunities` with `action` (create_content / add_link / update_page), `status`, `content_item_id` | already partly there |
| Publishing (16) | `publish_log` (content_item_id, mode, request JSON (masked), response, wp_post_id, status) | the audit trail |
| Reports (17) | `reports` (type, period, path_md, path_pdf, params) | |
| Settings/Help (18) | `settings` (key, value JSON, scope global/site), `help_articles` (slug, title_fa, body_md) | |

Graph node types added: `KEYWORD` (from `keywords`, distinct from GSC `QUERY`), `CONTENT` (content_items), `TOPIC` (clusters). Edges: `KEYWORD_TARGETS`, `CLUSTERED_IN`, `CONTENT_FOR`, `SUGGESTED_LINK`, `PUBLISHED_AS`.

---

## 5. API surface (v1) — one router per menu item

| Router | Key endpoints (all `GET` unless noted) |
|---|---|
| `/sites` | list, `POST` create (wizard), `GET/PATCH /{id}`, `POST /{id}/connections/gsc|ga4/test`, `POST /{id}/sync/{wordpress|crawl|gsc}` (enqueue job) |
| `/graph` | `/{site}/summary`, `/subgraph?center&hops&types`, `/search?q`, `/node/{id}`, `/path?a&b` (wraps existing `queries.py`) |
| `/keywords` | CRUD, `POST /import` (multipart + mapping), `POST /cluster`, `/topic-map` |
| `/content` | CRUD, `PATCH /{id}/stage`, versions, `POST /{id}/brief` (AI), `POST /{id}/generate` (AI), `POST /{id}/publish` (mode-guarded) |
| `/calendar` | range query, `POST /import`, `PATCH /{id}` (move) |
| `/ai` | providers CRUD, `POST /providers/{id}/test`, models, routes, prompts (+versions), `POST /prompts/{id}/render`, usage |
| `/links` | suggestions (filter/status), `POST /analyze/{site}`, patterns |
| `/opportunities` | list/filter, `POST /{id}/action` (creates content item / link suggestion) |
| `/reports` | list, `POST /generate`, download |
| `/jobs` | list, runs, `POST /{id}/run-now`, `GET /runs/{id}/stream` (SSE) |
| `/settings`, `/help` | key/value; help articles (fa) |

Auth: single local API token (generated at setup, stored in SecretStore, sent by the frontend from `.env.local`); CORS restricted to `http://localhost:3000`; both servers bind `127.0.0.1` locally. Multi-user auth is a server-phase concern (Phase 19), designed as a pluggable dependency in `deps.py`.

---

## 6. AI layer design (Phases 9-12)

```
Task (e.g. "content_writing", "seo_analysis", "research", "brief", "linking", "schema")
   └─ AIRouter.resolve(task, site) → [primary model, fallback…]  (from ai_routes)
        └─ AIProvider.complete(messages, tools?, json_schema?, max_tokens) → AIResponse(text, usage, cost, raw)
             providers: anthropic (Claude), openai, google (Gemini), openrouter, ollama, custom (OpenAI-compatible base_url)
PromptLibrary.render(prompt_id, version, variables={{keyword}},{{intent}},{{entities}},{{brand}}, …) → messages
Every call → ai_calls (usage/cost/latency, prompt version, output hash) → visible in UI "AI Models → Usage".
```
Guardrails: strict JSON-schema outputs for briefs/schema; retries with fallback on provider error; per-site monthly budget; no secret ever leaves SecretStore except in the outbound Authorization header.

---

## 7. Security & write policy

* Secrets (WP app passwords, AI keys, Google client secret/token) → `SecretStore` (DPAPI-encrypted per user on Windows; `.env` remains only for bootstrap and is read into the store on first run). UI shows only `****last4`.
* Site **mode** gates every outbound write: `manual` (nothing leaves; UI shows what *would* happen), `assisted` (writes require a human click per item; drafts only unless approved), `autopilot` (scheduler may publish within configured limits: days, hours, max articles/day, categories). Mode changes are audit-logged.
* WordPress writer supports: create draft, publish, set category/tag, featured image, Yoast/RankMath meta, schema — all through the official REST API with an Application Password; never the admin password.
* Existing guarantee kept: crawler/GSC/WP-reader modules remain GET-only and are covered by the evolved acceptance test 10.

---

## 8. Automation (Phase 8) — one pipeline definition, two runtimes

`pipeline.py` defines steps as pure functions: `find_next_content → generate_brief → generate_content → seo_review → insert_links → publish`. Each step reads/writes DB rows and returns a `StepResult`; the runner (APScheduler now, RQ later) persists progress in `job_runs` and streams it via SSE. Failures stop the pipeline for that item and surface in *Content Brain* as a red badge with the log.

---

## 9. Frontend architecture (Phase 2 onward)

* Base: `Kiranism/next-shadcn-dashboard-starter` (Next.js App Router, shadcn/ui, Tailwind, Zustand, TanStack Table). We strip Clerk auth (local token instead) and its demo pages, keep layout/sidebar/theme.
* RTL + Persian: `dir="rtl"`, Vazirmatn font (bundled locally — no external requests), all strings in `lib/i18n/fa.ts`; logical CSS properties (`ps/pe/ms/me`).
* Data: TanStack Query hooks over the generated OpenAPI client; SSE hook for jobs.
* Graph page: React Flow + dagre/elk layout, node colours = the same palette as the Obsidian graph, sidebar on node click (keyword: position/CTR/impressions/clicks/intent/target page/related content).
* Kanban: dnd-kit; Calendar: FullCalendar (month/week, drag & drop) or custom on dnd-kit — decided in Phase 7.

---

## 10. Phase → module map & risks

| Phase | Where it lands | Main risk / prerequisite |
|---|---|---|
| 1 | this doc + repo restructure + `backend/api` skeleton with `/sites`, `/graph` wrapping existing queries | import-path migration (mitigated by shim + tests) |
| 2 | `frontend/` from starter | **Node.js install + ≥ 3 GB free disk** |
| 3 | `sites` extension, wizard, workspace dirs, GSC/GA4 test endpoints | GA4 needs Analytics Data API enable + scope; per-site OAuth tokens |
| 4 | `/graph/subgraph`, React Flow | 91 nodes fine; >2k nodes needs server-side layout/pagination |
| 5 | keywords + importer + clustering (rapidfuzz/embeddings via AI layer) | Persian normalisation (ي/ی, ك/ک, ZWNJ) — reuse normalizer |
| 6-7 | content_items, kanban, calendar | — |
| 8 | scheduler + pipeline | needs AI layer (9-12) first → build order 9→11→12→8 |
| 9-11 | ai/ | provider SDK versions; cost logging |
| 12 | briefs (uses graph entities + GSC + AI) | — |
| 13-15 | analysis/linking, opportunities actions | already partly exists (86 link opportunities) |
| 16 | integrations/wordpress/writer | **first write capability** — mode gate + audit + explicit approval from you before enabling on the live site |
| 17 | reports (md → pdf via WeasyPrint or Playwright-Chromium) | pdf engine footprint on this disk |
| 18 | help articles (fa) + tooltips | — |
| 19 | docker/, Postgres/Redis/Neo4j adapters | — |

Recommended execution order: **1 → 2 → 3 → 4 → 5 → 9 → 10 → 11 → 12 → 6 → 7 → 13 → 14 → 15 → 8 → 16 → 17 → 18 → 19** (AI layer before Content Brain so the Brain is usable from day one; automation after both).

---

## 11. Decisions I need from you before Phase 1 implementation

1. **Restructure now** (move `src/`→`backend/seo_brain/`, `scripts/`→`backend/cli/`, `mcp/`→`backend/mcp/`, keep a temporary `src/` shim, re-register the MCP path)? — *Recommended: yes.*
2. **Legacy Jinja dashboard** (`src/dashboard`, port 3000): keep running as `/legacy` inside the new FastAPI app until the Next.js UI reaches parity, then delete? — *Recommended: yes.*
3. **Node.js**: allow me to download & install Node LTS (official installer, hash-verified like Obsidian) when Phase 2 starts? — and **disk**: can you free ≥ 3 GB on C:, or should the project move to another drive (e.g. `D:\Plan`)? Phase 2 is blocked until one of these happens.
4. **Ports**: backend `127.0.0.1:8000`, frontend `127.0.0.1:3000` (legacy dashboard moves to `/legacy` on 8000). OK?
5. **Write policy**: agree that WordPress writes are shipped disabled (`manual` mode) and only enabled per site by you in the UI?
6. **DB tech**: stay on raw SQL + repositories (consistent with v0.1, Postgres-compatible) instead of introducing an ORM? — *Recommended: yes.*

On approval I will implement Phase 1: restructure with shim, migrations runner (`database/migrations/0001_init.sql` = current schema), FastAPI `api/` skeleton (`/health`, `/sites`, `/graph/*` wrapping existing queries, OpenAPI at `/docs`), API tests, docs, commit — with all 27 existing tests still green.
