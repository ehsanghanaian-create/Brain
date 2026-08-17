# Backend ⇄ Frontend integration contract (API v1)

Status: **v1.0 — binding for Phase 2+** · Date: 2026-08-17 · Machine-readable source of truth: `docs/seo-brain/openapi.v1.json` (snapshot of `GET /api/openapi.json`; regenerate after every backend change: `curl http://127.0.0.1:8000/api/openapi.json > docs/seo-brain/openapi.v1.json`).
Validated live: `03-phase1.5-api-validation.md` (47/47).

## 1. Transport & environments

| | Local (now) | Server (Phase 19) |
|---|---|---|
| Backend base URL | `http://127.0.0.1:8000` | `https://<host>` (reverse proxy) |
| API prefix | `/api/v1` | same |
| OpenAPI | `/api/openapi.json` · Swagger UI `/api/docs` | same (may be disabled) |
| Legacy dashboard | `/legacy` (read-only, temporary) | removed |
| Frontend origin | `http://localhost:3000` (`FRONTEND_ORIGIN` env, comma-separated list) | configured |
| Content type | JSON UTF-8 both ways; Persian text is never escaped (`ensure_ascii=false`) | same |

Frontend client: TypeScript types + client are **generated** from the OpenAPI snapshot (`openapi-typescript` + a thin `fetch` wrapper in `frontend/lib/api/`). Hand-written types are not allowed for API payloads.

## 2. Authentication

* Header **`X-API-Token: <token>`** on every request except `GET /api/v1/health`.
* Backend: `API_TOKEN` in `.env`. If unset (dev default), the API is open on loopback — the frontend must still *send* the header when it has one.
* Frontend: the token lives **server-side** in `frontend/.env.local` (`SEO_BRAIN_API_TOKEN`) and is attached by a Next.js route-handler proxy `app/api/backend/[...path]/route.ts` that forwards `/api/backend/*` → `${SEO_BRAIN_API_URL}/api/v1/*`. The browser never sees the token. Server components may call the backend directly with the same env vars.
* Failure: `401 {"error":{"code":"unauthorized"}}` → the UI shows a "backend token missing/invalid" banner with the fix (`.env`), no login screen (single local user). Multi-user auth arrives with Phase 19 behind the same header/proxy without contract change.

## 3. Response formats

| Kind | Shape | Examples |
|---|---|---|
| Single resource | plain JSON object | `GET /sites/{id}` → `Site` |
| List (small, unpaginated) | plain JSON array | `GET /sites`, `GET /jobs`, `GET /ai/providers`, `graph/nodes` (uses `limit`/`offset` params) |
| Paginated list (**new endpoints from Phase 3 on**) | `{"items":[…],"total":n,"limit":l,"offset":o}` | keywords, content items, calendar entries |
| Action result | object describing what happened | `DELETE /sites/{id}` → `{deleted, related_rows_deleted, workspace_kept}` |
| Async job | `202` + `JobRun`; poll `GET /jobs/{run_id}` until `status ∈ {succeeded, failed}`; SSE stream `GET /jobs/{run_id}/stream` arrives in Phase 8 | `POST /jobs` |
| Timestamps | ISO-8601 UTC with `Z`, ms precision (`2026-08-17T12:50:19.500Z`) | `created_at`, `updated_at`, `queued_at` |
| Money / tokens | numbers (`cost_usd` float or null, `*_tokens` int) | AI results |
| Enumerations | lower-case snake strings (`mode`: `manual|assisted|autopilot`; task kinds; job status) | |
| Nullability | absent value = `null` (never omitted) for resource fields; optional request fields may be omitted | |

### 3.1 Core resource shapes (from `openapi.v1.json`)

**Site** `{site_id, name, canonical_url, wp_url, language, gsc_property, business_type, country, mode, ga4_property, workspace_path, created_at, updated_at}`
**SiteMemory** `{site_id, business_rules: string[], tone: object, content_rules: string[], successful_patterns: {pattern, evidence, source, run_id, created_at}[], updated_at}`
**GraphNode** `{id, site_id, type, metadata}` — `metadata` always contains `label`, `url|null`, `pagerank|null`, `community|null`, `vault_path|null`, `props: object` (crawl/WP/GSC facts). Node `type` ∈ `SITE PAGE POST CATEGORY TAG BRAND MODEL SERVICE LOCATION QUERY SCHEMA SEO_PROBLEM SEO_OPPORTUNITY KEYWORD TOPIC CONTENT`.
**GraphEdge** `{source, target, relation_type, weight, metadata: {edge_id, props}, site_id}`; `relation_type` ∈ `HAS_PAGE HAS_POST HAS_CATEGORY HAS_TAG BELONGS_TO LINKS_TO ABOUT OFFERS TARGETS RANKS_FOR HAS_SCHEMA HAS_PROBLEM HAS_OPPORTUNITY KEYWORD_TARGETS CLUSTERED_IN CONTENT_FOR SUGGESTED_LINK PUBLISHED_AS`.
**Subgraph** `{center, hops, nodes: GraphNode[], edges: GraphEdge[]}` — React Flow maps `nodes[].id`→node id, `edges[].source/target`→edge ends directly.
**GraphSummary** `{site_id, nodes, edges, by_node_type: {TYPE: n}, by_relation_type: {REL: n}, site: <legacy summary counts>}`
**OrchestrationResult** `{ok, route_used: {provider, model}|null, memory_used, attempts: {provider, model, ok, error, latency_ms}[], response: {text, parsed, model, provider, input_tokens, output_tokens, cost_usd, latency_ms}|null}`
**JobRun** `{run_id, type, site_id, status: queued|running|succeeded|failed, queued_at, started_at, finished_at, result, error}`
**Health** `{status, version, database, migrations: {applied: string[], pending: string[]}}`

Node ids may contain `:` `/` and Persian characters; always **URL-encode path segments** (`encodeURIComponent`) — the routes are declared `{node_id:path}`.

## 4. Error handling format

Every non-2xx response:
```json
{"error": {"code": "not_found", "message": "unknown site_id 'nope'", "details": null, "request_id": "9f1c…"}}
```
| HTTP | `code` | `details` | Frontend behaviour |
|---|---|---|---|
| 400 | `bad_request` | any | toast with message |
| 401 | `unauthorized` | null | token banner (see §2) |
| 404 | `not_found` | null | empty-state / redirect to list |
| 409 | `conflict` (create duplicate) · `site_has_data` (delete without force → `details` = `{table: rowcount}`) | object | confirm dialog ("delete N rows too?") then retry with `?force=true` |
| 422 | `validation_error` | `[{loc: [...], msg, type}]` (FastAPI/Pydantic) | map `loc[-1]` to the form field; show `msg` inline |
| 429 | `rate_limited` | — | reserved (AI providers, Phase 9) |
| 500 | `internal_error` | `{type}` | generic error card showing `request_id` for log lookup |

Every response carries **`X-Request-ID`** (echoed if sent) — the frontend generates one per user action and shows it in error cards; the backend logs it (`data/logs/api.jsonl`). CORS exposes the header.

## 5. Conventions for the endpoints that Phase 3+ will add (binding)

* Route shape: `/api/v1/sites/{site_id}/<resource>` for site-scoped data; global resources (`/ai/*`, `/jobs`, `/settings`) unscoped.
* Filtering by query string (`?status=&q=&types=a,b`), pagination `limit` (default 50, max 500) + `offset`, sorting `?sort=field&order=asc|desc`.
* Writes: `POST` create → `201` + resource; `PATCH` partial update → `200` + resource; `PUT` full replace (memory) → `200`; `DELETE` → `200` + action result (never `204`, so the UI always gets a body).
* Long operations never block a request: they enqueue a job (`202 JobRun`) and the UI polls / streams.
* Anything that leaves the machine (WordPress publish, AI calls to paid providers) is guarded by the site `mode` and returns `409 {"code":"mode_blocked"}` when not allowed — the UI must show *what would happen* in `manual` mode instead of failing silently.
* AI results are always returned with provenance (`OrchestrationResult`) and stored rows carry `provenance` JSON.

## 6. Frontend project conventions tied to this contract

* `frontend/lib/api/client.ts` — generated types + `api.get/post/patch/put/delete` wrappers that: attach `X-Request-ID`, unwrap the error envelope into a typed `ApiError {status, code, message, details, requestId}`, and never throw raw `fetch` errors to components.
* React Query keys mirror routes: `['sites']`, `['site', id]`, `['graph', id, 'subgraph', params]`, `['memory', id]`, `['jobs']`.
* All strings from the API are rendered as-is (RTL text is native); numbers formatted with `fa-IR` locale, dates from the `Z` timestamps.

## 7. Change control

Breaking changes to any shape above require a new prefix (`/api/v2`) or an additive field. `openapi.v1.json` is committed with every backend change and CI (later) diffs it; the frontend regenerates its client from it.
