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

## 8. Phase 3 additions (2026-08-17, additive — no existing shape changed)

| Endpoint | Request | Response |
|---|---|---|
| `GET /sites/{id}/connections` | — | `{site_id, configured:{gsc,ga4,wordpress: string|null}, status:{[kind]: ConnectionResult}}` |
| `POST /sites/{id}/connections/{kind}/test` (`kind` ∈ `gsc|ga4|wordpress`) | `{property?: string}` (omit → use the site's stored value) | **ConnectionResult** `{kind, status: ok|not_configured|not_authorized|not_found|error, ok, message (fa), detail: object (never secrets), tested_at}`; on `ok` with an explicit `property` the value is stored on the site. Unknown kind → `404 not_found` |
| `GET /connections/gsc/properties` | — | `{status, message?, properties:[{property, permission}]}` |
| `POST /sites/{id}/initialize` | — | `{site_id, workspace:{path, created[], existed}, memory:{initialized, existed, updated_at}, graph:{site_node, existed, nodes, edges}}` — idempotent |
| `PUT /sites/{id}/memory` | `MemoryUpdate` now also: `audience:{segments[],pains[],intent_notes}`, `cta_rules[]`, `forbidden_claims[]` | **SiteMemory** with the same new fields |
| `POST /sites` / `PATCH /sites/{id}` | + `timezone` | Site + `timezone` |

UI rule for `ConnectionResult`: show `message` verbatim; badge by `status` (`ok`→success, `not_configured`→neutral, others→destructive); never render `detail` keys that look like tokens (the backend never sends them, but the UI must not either).

## 9. Phase 4 additions (2026-08-17, additive)

| Endpoint | Response |
|---|---|
| `GET /sites/{id}/graph/modes` | `[{key: seo|content|links, title_fa, description_fa, layout, group_by, node_types[], relation_types[]}]` |
| `GET /sites/{id}/graph/view?mode=&types=&relation_types=&limit=&include_isolated=` | `{mode: <GraphMode>, nodes: GraphNode[], edges: GraphEdge[], truncated, total_nodes, stats:{by_type, by_relation}}` — bad mode → 422 |
| `GET /sites/{id}/graph/node-details/{node_id}` | `{id, type, label, url, pagerank, community, props, degree, …one of: page{…}, keyword{…}, problem{…}, opportunity{…}, entity{…}, schema{…}, site{…}, neighbors[]}` — see `07-phase4-graph.md §1` for the per-kind fields; unknown → 404 |

Client rule: node ids go into the path as **one `encodeURIComponent` segment** (`/graph/node-details/page%3Ahttps%3A%2F%2F…`); Next.js collapses `//` inside multi-segment paths.

## 10. Phase 5 additions (2026-08-17, additive) — `/sites/{id}/keywords/*`

| Endpoint | Notes |
|---|---|
| `GET /keywords?q&status&intent&priority&cluster_id&topic&sort&order&limit&offset` | **paginated envelope** `{items, total, limit, offset, counts}`; item = keyword row + `gsc: {clicks, impressions, ctr, position, top_page, pages_count}|null` + `cluster: {cluster_id, name, topic}|null` |
| `POST /keywords` → 201 · `GET/PATCH/DELETE /keywords/{kid}` | 409 `conflict` on same normalized keyword; 422 on bad enums; detail adds `gsc_pages[]`, `opportunities[]` |
| `POST /keywords/import` (multipart: `file`, `dry_run`=true|false, `mapping` JSON) | `ImportResult {format, columns, mapping, unmapped_columns, rows_total, rows_valid, rows_imported, rows_updated, rows_skipped, errors[{row,error}], errors_count, preview[], import_id, dry_run}`; 400 empty/too large |
| `GET /keywords/template.csv` · `GET /keywords/imports` · `GET /keywords/meta` | |
| `POST /keywords/cluster?threshold&sync_graph` · `GET /keywords/clusters` · `PATCH /keywords/clusters/{cid}` · `GET /keywords/topic-map` | topic-map = `{clusters:[cluster + members[] + gsc{} + targets[] + volume], unclustered[], counts}` |
| `POST /keywords/analyze?min_impressions&sync_graph` · `GET /keywords/opportunities?kind&status&keyword_id&min_score` · `PATCH /keywords/opportunities/{oid}` `{status}` | opportunity = `{id, keyword_id, keyword, kind, kind_fa, target_url, score 0–1, reason (fa), evidence{}, status, run_id}` |
| `POST /keywords/sync-graph` | KEYWORD/TOPIC nodes + CLUSTERED_IN/KEYWORD_TARGETS edges |

Frontend: file uploads go through the proxy as `FormData` (the proxy forwards the raw body); never set `Content-Type` manually for multipart.

## 11. Phase 6 additions (2026-08-17, additive) — `/sites/{id}/content/*`, `/ai/provider-configs`, `/ai/task-routes`

| Endpoint | Notes |
|---|---|
| `GET /content?status&q&topic&cluster_id&priority&date_from&date_to&sort&order&limit&offset` | paginated envelope + `counts {total, by_status, scheduled}`; item adds `status_fa`, `allowed_transitions[]`, `has_brief` |
| `POST /content` → 201 · `GET/PATCH/DELETE /content/{cid}` | PATCH cannot change `status` (use transition); `clear_date: true` unschedules; detail adds `brief`, `briefs[]`, `events[]`, `keyword` |
| `POST /content/{cid}/transition {status, note?}` | 409 `invalid_transition` (+ `details.allowed`) when skipping stages, `brief_ready` without brief, `published` without url |
| `POST /content/{cid}/brief {use_ai, mark_ready}` · `GET /content/{cid}/briefs` · `GET /content/{cid}/events` | **ContentBrief** `{id, version, h1, seo_title, meta_description, intent, outline[{h2,h3[],why}], entities[], questions[{question,source}], internal_links[{url,anchor,reason,node_id}], sources{}, markdown, provenance{}}` |
| `GET /content/board` · `GET /content/calendar?from&to` · `POST /content/from-opportunity/{oid}` · `POST /content/sync-graph` · `GET /content/meta` | board = `{columns[{status,status_fa,items[]}], counts}`; calendar = `{from, to, days{YYYY-MM-DD: items[]}, unscheduled[], counts}` |
| `GET /ai/provider-kinds` · `GET/POST /ai/provider-configs` · `PATCH/DELETE /ai/provider-configs/{pid}` · `POST /ai/provider-configs/{pid}/test` | **ProviderConfig** never contains the key: `{id, name, kind, kind_label, base_url, default_model, models[], enabled, has_key, key_hint, last_test}`; `api_key` is write-only (POST/PATCH), `clear_key: true` removes it |
| `GET /ai/task-routes` · `PUT /ai/task-routes/{task_kind}` | 8 task kinds; route = `{task_kind, site_id, provider_id, model, fallback_provider_id, fallback_model, provider_name, fallback_provider_name}` |

UI rules: never render/log an API key; show `••••{key_hint}`; workflow buttons come from `allowed_transitions`; publishing is manual (URL + transition), no auto-publish anywhere.

## 12. Phase 7 additions (2026-08-18, additive) — content intelligence

| Endpoint | Notes |
|---|---|
| `GET/POST /content/{cid}/drafts` · `GET /content/{cid}/drafts/{did}` | POST always creates version N+1 (`revision_of` = previous, `change_summary` auto if omitted). List omits `body`; get includes it. Draft = `{id, content_id, version, title, meta_description, format, body, body_text, word_count, structure{h1[],h2[],h3[],headings[],paragraphs[],links[],images[],questions[],faq}, source, author, revision_of, change_summary, provenance{}, review_status, created_at}` |
| `POST /content/{cid}/score?draft_id` | **ContentScore** `{id, draft_id, version, total, dims{7}, dims_fa, findings[{rule,dim,passed,weight,evidence,fix_fa}], failed[], weights, engine_version, label ready|needs_work|weak, thresholds}`; 404 without a draft |
| `POST /content/{cid}/review {draft_id?, use_ai}` | **ContentReview** `{id, draft_id, version, review_status ready|changes_requested, score, findings[{code,severity,area,message_fa,evidence,suggestion_fa,auto_fixable,paragraph_index}], counts{high,medium,low}, summary_fa, provenance{engine, ai_used, note?, provider?, model?}, gate}` |
| `GET /content/{cid}/intelligence` | `{drafts[] (no body), scores[], reviews[]}` newest first |
| `POST /content/{cid}/transition` | additionally 409 `invalid_transition` when gate is `strict` and the latest draft is not `ready` (message says why) |
| `GET/PUT /content/settings/scoring` | `{weights{intent,keywords,entities,headings,links,cta,completeness}, thresholds{ready,needs_work}, min_words{}, min_internal_links, review_gate strict|advisory}` (PUT = partial merge) |
| `GET/PUT /content/analytics/settings` · `POST /content/analytics/snapshot` · `POST /content/analytics/learn?min_n` · `GET /content/analytics/overview` · `GET /content/{cid}/metrics?window` | overview = `{window, rows[{content_id,title,status,url,date,clicks,impressions,ctr,position,delta,top_queries}], totals, gates}` |
| `GET /content/insights?status` · `PATCH /content/insights/{iid} {status}` | insight = `{id, category, feature, value, metric ctr|position, effect, baseline, n, impressions, clicks, confidence, message_fa, evidence, status, memory_pattern_ref}`; `accepted` writes a Site Brain pattern (idempotent) |

UI rules: AI findings/suggestions are advisory — never auto-apply; show the gate reason on approval; scores/insights never change weights automatically.

## 13. Phase 8 additions (2026-08-18, additive) — `/sites/{id}/links/*`

| Endpoint | Notes |
|---|---|
| `GET /links/meta` | kinds, statuses, confidence levels (`low 0.45–0.60`, `recommended 0.60–0.80`, `high 0.80+`), flags, stages, journey order, scopes + future_scopes |
| `POST /links/analyze` | `200 {mode:"sync", run_id, pages, targets, suggestions, by_confidence, supports_edges, created, updated, kept, removed, graph{link_opportunity,supports}, stats{orphans,low_inbound,avg_health}}` when pages ≤ `sync_threshold_pages`; else `202 {mode:"job", run_id, type:"links_analyze", status…}` → poll `/jobs/{run_id}` |
| `GET /links/summary` | `{by_status, by_kind, by_confidence, pages, flags{orphan,nav_only_inbound,low_inbound,generic_anchors,over_optimized_anchor,single_source}, avg_health, settings}` |
| `GET /links/suggestions?kind&status&confidence&min_score&target&source&q&sort&limit&offset` | paginated; **LinkSuggestion** `{id, scope, kind, kind_fa, source_node_id/url/title/stage, target_node_id/url/title/stage, anchor, anchor_alternatives[], placement_hint, score, confidence, confidence_fa, score_breakdown{topic,entities,intent,authority,anchor,journey,pattern_boost,penalties,top}, reason_fa, evidence{}, status, content_task_id, run_id}` |
| `PATCH /links/suggestions/{sid} {status, anchor?}` | accept/done → `SUGGESTED_LINK` edge; dismiss → removes `LINK_OPPORTUNITY`; statuses survive re-analyze |
| `POST /links/suggestions/{sid}/content-task {title?, note?}` → 201 | creates a **planned** Content Brain item (`metadata.link_suggestion_id`), returns `{content_id, title, status, suggestion}` |
| `GET /links/pages?flag&sort&order&q` · `GET /links/pages/{node_id}` | **LinkPageStat** with `health_score` (0–100) + `health_breakdown{inbound_contextual,outbound_balance,anchor_diversity,orphan_risk,authority}`, `flags[]`, `anchor_distribution[]`; detail adds inbound/outbound/suggestions_to/suggestions_from |
| `GET /links/patterns?status` · `PATCH /links/patterns/{pid} {status}` | accepted → Site Brain `successful_patterns` (source `internal_linking`) |
| `GET/PUT /links/settings` · `GET /links/export.csv?status` | settings partial merge; CSV UTF-8 with BOM |

Graph: relation types `LINK_OPPORTUNITY`, `SUPPORTS` added; links map returns them; page node details include `link_health` and `link_suggestions`.
UI rules: always show the confidence label + score; suggestions are advisory (accept/dismiss/done are bookkeeping, nothing is written to WordPress); "Create Content Task" only on user click.

## 14. Phase 9 additions (2026-08-18, additive) — `/ai/*` gateway, `/sites/{id}/generation/*`

| Endpoint | Notes |
|---|---|
| `GET /ai/task-kinds` | `[{kind, fa, policy{tiers[], tags[]}}]` — 17 kinds |
| `GET /ai/models?provider_id` · `POST /ai/models/sync?provider_id&discover` · `PATCH /ai/models/{mid}` | **AiModel** `{id, provider_id, provider, kind, model_id, display, tier, tags[], context_tokens, price_in_per_m, price_out_per_m, enabled, source}`; PATCH fields tier/tags/prices/context/enabled/display |
| `GET /ai/health` | `{providers:[{provider, calls, failures, consecutive_failures, p50_ms, breaker_open_until, last_error, updated_at}], now}` |
| `GET /ai/usage?site_id&from&to&group_by=model|provider|task_kind|agent` | `{group_by, rows[{key, calls, ok, input_tokens, output_tokens, cost_usd, avg_latency_ms}], by_day[], budget}` |
| `GET /ai/budget?site_id` · `PUT /ai/budget?site_id {budget_usd_month>0}` | **Budget** `{month, limit_usd (default 20), spent_usd, ratio, state: ok|warning|soft_limit|hard_stop, thresholds{0.8,1.0,1.2}}` — human-set only |
| `GET /ai/routing/preview?task_kind&site_id&priority&provider&model` | **RoutingDecision** `{chain[{provider, model, reason}], reason, policy: explicit|auto|echo, candidates[]}`; 422 unknown kind |
| `PUT /ai/task-routes/{kind}` (extended) | body may add `policy` and `fallbacks:[{provider_id, model}]`; omitted → unchanged; response adds `policy`, `fallbacks[{…, provider_name}]` |
| `GET/POST /ai/prompts` · `GET /ai/prompts/{pid}` · `POST /ai/prompts/{pid}/versions {template, changelog?, activate?}` · `PATCH /ai/prompts/versions/{vid} {activate?, approval?, approved_by?}` · `POST …/versions/{vid}/preview {site_id, variables?}` · `POST …/versions/{vid}/test {site_id, provider?, model?}` · `PATCH /ai/prompts/tests/{tid} {human_rating, notes?}` | **Prompt** `{id, key, scope, site_id, title, description, tags[], active_version, versions[PromptVersion], performance[]?}`; **PromptVersion** `{id, version, template, variables[], model_hints, is_active, approval: draft|approved|rejected, approved_by, changelog}`; agent/task templates must contain `{{memory_pack}}` (422 otherwise); new versions are inactive until a human activates |
| `GET /ai/insights?site_id&status` · `POST /ai/insights/learn?site_id&min_n` · `PATCH /ai/insights/{iid} {status}` | **AiInsight** `{id, site_id, category, feature, value, metric, effect, baseline, n, confidence, message_fa, evidence, recommendation{action,…}, status: new|accepted|dismissed, memory_pattern_ref}` — recommendation only; `accepted` writes a Site Brain pattern, never routing/prompt changes |
| `GET /ai/feedback-tags` | the 6 tags with Persian labels |
| `GET /sites/{id}/generation/meta` | `{agents[{agent,fa}] (7), steps[], modes:[manual,assisted], reserved_modes:[autopilot], feedback_tags[]}` |
| `GET /sites/{id}/generation/memory-preview` | `{id, hash, pack, rendered}` (Memory Snapshot) |
| `POST /sites/{id}/content/{cid}/generate/estimate {models?, prompt_versions?}` | **GenEstimate** `{per_agent{agent:{provider, model, input_tokens, output_tokens, cost_usd, route[], reason, prompt, sections?}}, total{}, sections, budget, memory_snapshot_id}` |
| `POST /sites/{id}/content/{cid}/generate {mode?, models?, prompt_versions?}` → **202** | **GenerationRun** + `job_run_id`, `budget`; 409 `budget_exceeded` at hard stop; 422 for `autopilot`; 404 no content |
| `GET /sites/{id}/generation/runs?content_id` · `GET …/runs/{run_id}` | **GenerationRun** `{run_id, mode, status: queued|running|succeeded|failed|cancelled, step, step_fa, steps[{key, agent, status, artifact_id, provenance{provider,model,placeholder…}, words?, validation_ok?, fact_check?, error?}], models{agent→{provider,model}}, prompt_versions{agent→id}, memory_snapshot_id, estimate, actual{input_tokens,output_tokens,cost_usd}, draft_id, score, review_status, error, artifacts[{id, step, agent, version, payload, provenance}] (detail only)}` |
| `GET …/runs/{run_id}/stream` | `text/event-stream`; events `start, plan, step_start, step_done, done, failed, cancelled, keepalive` with JSON data `{type, run_id, step?, agent?, cost_usd?, …}` (backlog replayed on connect) |
| `POST …/runs/{run_id}/accept` · `POST …/runs/{run_id}/cancel` | accept (manual mode, human) → `{draft_id, version, score, review_status}` (idempotent `{already:true}`); the draft then follows the Phase-7 gate |
| `POST /sites/{id}/content/{cid}/agents/{agent}/run` | single-agent proposal (research/outline/seo/linking/reviewer) `{agent, ok, payload, provenance, placeholder, memory_snapshot_id}`; 404 otherwise |
| `POST /sites/{id}/content/{cid}/feedback {rating 1–5, tags?, draft_id?, run_id?, notes?}` → 201 · `GET …/feedback` | unknown tags dropped; `tags_fa` echoed |

UI rules: autopilot is shown greyed/reserved; Studio always shows the routing reason and budget state; generation output is only ever a draft version; publishing stays a human action outside this system.

## 15. Phase 8.5 additions (2026-08-18, additive) — `/sites/{id}/content-plans/*` (Content Strategy Planner)

| Endpoint | Notes |
|---|---|
| `GET /content-plans/meta` | `{statuses[{key,fa,item_status}] (7: planned, researching, brief_ready, writing, review, approved, published), transitions, page_types[], intents[], priorities[], funnel_stages[], content_gaps[], keyword_roles[], category_sources[], recommendation_kinds[], generation_job_kinds[], columns[{key,fa,group,editable,type,options?}], export_columns[], views:[table,kanban,graph], publishing{enabled:false,note}, ai_generation{enabled:false,note}}` |
| `GET /content-plans?status&category_id&page_type&intent&priority&cluster_id&content_cluster_id&q&from&to&has_item&unscheduled&sort&order&limit&offset` | `{items[ContentPlan], total, counts{total, by_status, by_priority, by_category, by_page_type, unscheduled}}` |
| `POST /content-plans` (201, `?analyze=true`) · `GET /{pid}` · `PUT|PATCH /{pid}` · `DELETE /{pid}?with_item` | **ContentPlan** `{id, content_item_id, title, url, slug, intent, serp_intent, page_type, funnel_stage, category_id, category_suggested_id, category_reason, primary_keyword_id, primary_keyword, secondary_keywords[], heading_structure[{level,text}], seo_title, meta_description, topic_id, cluster_id, content_cluster_id, search_volume, keyword_difficulty, priority, priority_score, ai_priority, business_value, traffic_opportunity, content_gap: none|partial|full, cannibalization_risk, cannibalization[], ranking_url, ranking_position, target_audience, publish_date, publish_time, status, status_fa, existing_pages[], link_targets[{direction,node_id,url,title,anchor,reason_fa,score}], graph_connections, content_score, recommendation_id, recommendation{engine,action,action_fa,title,page_type,intent,priority,priority_score,reasons_fa[],gaps_fa[],confidence}, publishing{}, metadata, notes, source, allowed_transitions[], category{id,name,source,parent_id}, parent_category, category_suggested{id,name,reason}, content_item{id,status,has_brief,url,latest_score,review_status,draft_count}, keywords[{id,keyword,role,volume,intent}]}`; detail adds `events[]`, `recommendations[]`, `generation_jobs[]`. Body accepts `category` (name → id) and `primary_keyword` (text → id) |
| `POST /content-plans/bulk {ids, patch}` · `POST /content-plans/bulk-delete {ids}` | bulk edits (status through the same rules) |
| `POST /{pid}/transition {status}` | planner workflow; mirrors to the content item (`researching` → item stays `planned`); 409 `invalid_transition` (incl. Phase-7 strict gate, no item for writing+) |
| `POST /{pid}/content-item {content_id?}` · `POST /{pid}/brief {use_ai?, mark_ready?}` | 1:1 content item (create or link); brief = Phase-6 brief + `plan_hints{heading_structure, secondary_keywords, internal_link_targets, external_references, cta}` |
| `POST /{pid}/analyze` · `POST /content-plans/analyze {ids?, link_prep?}` (200 sync / 202 job `planner_analyze` when > 200) · `POST /{pid}/link-prep` | recommendation engine rules-v1; link prep `{inbound[], outbound[], count}` |
| `GET|POST /{pid}/keywords` · `DELETE /{pid}/keywords/{kid}` · `GET /{pid}/events` · `GET /{pid}/recommendations` | keyword roles primary/secondary/supporting/question/gsc_query |
| `POST /{pid}/generation-jobs {kind: brief|outline|article|rewrite|title_meta, params}` (201) · `GET /content-plans/generation-jobs?plan_id` | **prepared only** `{id, plan_id, content_item_id, generation_run_id:null, draft_id:null, kind, status:'prepared', params, studio_url, note}` |
| `PUT /{pid}/publishing-metadata {target?, wp_status?, scheduled_at?, author?, checklist?, cta?, notes?, canonical?, og_title?}` | metadata only; response `publishing.publishing_enabled === false`; nothing is published |
| `GET /content-plans/calendar?from&to&category_id&status&priority` · `GET /content-plans/board?category_id` · `GET /content-plans/graph?plan_id|category_id` | calendar `{from,to,days{date:[card]},unscheduled[],counts,categories[]}` (cards with `kind:'content_item'` for items without a plan); board 7 columns; graph = planner subgraph (+`focus`) |
| `POST /content-plans/import` (multipart `file`, `dry_run`, `mapping` JSON, `key_columns`) · `GET /content-plans/import/template.csv` · `GET /content-plans/imports` · `GET /content-plans/export.csv|.xlsx?columns&filters` | **PlanImportResult** `{import_id, format, columns[], mapping{}, unmapped_columns[], rows, created, updated, skipped, errors[], preview[], dry_run, key_columns[]}`; Persian/English headers; upsert key url → primary_keyword → title |
| `GET|POST /content-plans/sources` · `PATCH|DELETE /sources/{sid}` · `POST /sources/{sid}/sync?dry_run` | **PlanSource** `{id, kind: google_sheet|csv_url|google_sheets_api(reserved), name, url, gid, mapping, key_columns, enabled, auto_sync:false, status, last_sync_at, last_result}`; sync fetches the public CSV export |
| `GET /content-plans/categories?tree&source` · `POST /categories/sync?brain&min_keywords` · `POST /categories/analyze` · `GET /categories/suggest?keyword|keyword_id|plan_id` · `POST /categories` (manual) · `GET|PATCH|DELETE /categories/{cid}` | **PlanCategory** `{id, source: wordpress|brain|manual, source_fa, wordpress_category_id, parent_id, name, slug, url, description, post_count, page_count, keyword_count, plan_count, coverage_score, intelligence{clusters, intents, top_keywords, gaps, entities, pages, graph_node_id}, metadata, synced_at, children?, plans?}`; sync = WP REST read-only (local-snapshot fallback) + brain topic categories; suggest `{keyword, suggested{id,name,source,score,reasons_fa[],components}, candidates[], confidence}`; WP categories delete → 409 `read_only` |
| `GET /content-plans/keyword-mapping?status=unmapped|mapped|all&q` · `POST /keyword-mapping/suggest {keyword_ids?, limit}` · `POST /keyword-mapping/apply {items:[{keyword_id, plan_id|'new', role?, recommendation_id?}]}` | overview `{status,total,items[keyword+mapped+plans+gsc+cluster_size],counts}`; suggest items `{keyword, recommendation{…, mapping{type:new|attach, plan_id, role}}, recommendation_id, category}` (persisted); apply `{created[], attached[], errors[]}` |
| `GET /content-plans/suggestions?status&kind` · `PATCH /suggestions/{rid} {status: accepted|dismissed}` | **PlanSuggestion** (permanent, versioned) `{id, plan_id, keyword_id, category_id, kind, kind_fa, action, title, page_type, intent, priority, priority_score, confidence, reasons[], payload, version, status: new|accepted|dismissed|superseded|applied, engine, computed_at, plan_title}`; accept may return `created_plan{id,title}` |
| `GET|POST /content-plans/clusters` · `PATCH|DELETE /clusters/{id}` | editorial clusters |
| `GET /content-plans/insights?status` · `POST /insights/learn?min_n` · `PATCH /insights/{iid} {status}` | planner learning (content_insights category `planner`); accept → Site Brain pattern (`content_planner`) |
| `POST /content-plans/backfill` · `POST /content-plans/sync-graph` · `POST /content-plans/sync-items` | maintenance |

Graph: node types `CONTENT_PLAN`, `CONTENT_CLUSTER`, `SEARCH_INTENT`, `FUNNEL_STAGE`; relations `CONNECTED_TO`, `CONTAINS`, `PLANNED_AS`, `HAS_INTENT`, `IN_STAGE`; mode `planner` in `/graph/modes` (now 4 modes) and `/graph/view?mode=planner`; node details for the new types and `planner_category` on CATEGORY.
UI rules: recommendations always show reasons; publishing controls are metadata only; generation buttons only prepare jobs and deep-link to AI Studio; WP categories are read-only.
