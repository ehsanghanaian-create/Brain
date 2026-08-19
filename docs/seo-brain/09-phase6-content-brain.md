# SEO Brain — Phase 6: Content Brain foundation

Date: 2026-08-17 · Existing contracts unchanged (new `/content/*`, `/ai/provider-configs`, `/ai/task-routes`; migration 0005) · Backend **68/68** · Live validation **95/95** · `tsc` clean · verified in the browser on the real site (create → keyword picker → brief → workflow → Jalali calendar → AI provider with encrypted key).

**Not a generator.** Content is an *entity* linked to keywords, clusters/topics, GSC and the graph; briefs are assembled from those sources; humans move items through the workflow; nothing publishes anywhere.

## 1. Data model — migration `0005_content_brain.sql`
| Table | Purpose |
|---|---|
| `content_items` | title, slug, target_keyword(_id), topic, cluster_id, intent, **status** (`planned → brief_ready → writing → review → approved → published`), priority, publish_date/time, ai_provider/ai_model, url, wp_post_id, brief_id, metadata JSON, notes |
| `content_events` | every status transition / note with actor (`user`, `system`, `ai:<provider>`) — audit trail |
| `content_briefs` | versioned briefs: h1, seo_title, meta_description, intent, outline (H2/H3 + *why*), entities, questions, internal_links, sources, markdown, provenance |
| `ai_providers` | provider configs (name, kind, base_url, default_model, models, enabled, `secret_ref`, `key_hint`, last_test) — **no key in the DB** |
| `ai_routes` | task kind → provider/model + fallback (global `*` or per site) |

## 2. Workflow (human approval, enforced server-side)
`TRANSITIONS`: forward exactly one step, or back to an earlier stage. Guards: `brief_ready` needs a brief; `published` needs a URL (publishing is *marking*, never a WordPress write). Status cannot be PATCHed — only `POST /{cid}/transition` (409 `invalid_transition` with the allowed list). Every change → `content_events`.

## 3. Brief generator (`brain/content/briefs.py`) — sources are real and listed in `brief.sources`
keyword row · cluster siblings (→ H2s with volume) · GSC queries overlapping the keyword tokens (→ H2/H3 + questions with impressions) · existing ranking pages (GSC top pages / target) with **improve-vs-create** recommendation · graph entities BRAND/MODEL/SERVICE/LOCATION matched on label/aliases (→ entities + H3 list + H1 location) · internal links (pages `ABOUT`/`OFFERS` the entities, `internal_link` opportunities, top-PageRank hubs) · keyword opportunities · **competitors: reported "not available", never invented**. Output: H1, SEO title, meta, intent, outline, entities, questions, internal links, markdown, provenance. `use_ai=true` runs the orchestrator `BRIEF` task (JSON-validated); with only the Echo provider it keeps the rule brief and *says so* in provenance.

## 4. AI provider management (`ai/config.py`, `core/secrets.py`)
* Kinds: **Claude (Anthropic)**, **ChatGPT (OpenAI)**, **Gemini (Google)**, OpenRouter, **مدل محلی (Ollama)**, custom OpenAI-compatible.
* **SecretStore**: Windows DPAPI (current-user) → `data/secrets/<ref>.bin` (git-ignored); Fernet on other OSes; refuses plaintext. API returns only `has_key` + `key_hint`; keys never in logs.
* Connection test = read-only model-list probe per kind (verified live: invalid key → `not_authorized`, HTTP 401 shown).
* Task routes for 8 task kinds (content_writing, seo_analysis, research, brief, keyword_analysis, internal_linking, schema, generic) with fallback; deleting a provider clears routes pointing at it. Real completions arrive in Phase 9.

## 5. Graph integration
`POST /content/sync-graph` → **CONTENT** nodes (`content:<id>`, props: status/priority/date/intent/topic/target_keyword/ai_provider) + `CONTENT_FOR` → keyword, `CLUSTERED_IN` → topic, `PUBLISHED_AS` → page (URL match). Stale nodes removed. Content map shows them; node details for CONTENT/TOPIC added.

## 6. API (additive) — `/sites/{id}/content/*` and `/ai/*`
`GET /meta` · `GET ""` (paginated + counts, filters status/q/topic/cluster/priority/date range) · `POST ""` (keyword auto-fills intent/cluster/priority/topic) · `POST /from-opportunity/{oid}` (also marks the opportunity accepted) · `GET /board` · `GET /calendar?from&to` (days + unscheduled) · `POST /sync-graph` · `GET/PATCH/DELETE /{cid}` (PATCH `clear_date`) · `POST /{cid}/transition` · `POST /{cid}/brief {use_ai, mark_ready}` · `GET /{cid}/briefs` · `GET /{cid}/events`.
`GET /ai/provider-kinds` · `GET/POST /ai/provider-configs` · `PATCH/DELETE /ai/provider-configs/{pid}` (`api_key`, `clear_key`) · `POST /ai/provider-configs/{pid}/test` · `GET /ai/task-routes` · `PUT /ai/task-routes/{kind}`. `DELETE /sites/{id}` clears content tables. Contract §11; OpenAPI 56 paths.

## 7. UI (Persian)
* **مغز محتوا** `/dashboard/content`: KPIs; **Kanban** (6 status columns, drag between adjacent stages, guards surfaced as toasts) and **list** view; editor sheet: fields (title, keyword picker with live GSC position, topic, intent, priority, date/time, AI provider/model, URL, notes), transition buttons (only allowed ones), tabs **بریف** (structured view or Markdown, regenerate / regenerate-with-AI, versions) and **تاریخچه**; links to keywords/calendar/graph.
* **تقویم محتوایی** `/dashboard/calendar`: **Jalali** month grid (ICU, Saturday-first, Gregorian day shown small), items colored by status, drag between days / to "بدون تاریخ", month/list tabs, status legend with counts.
* **مدل‌های AI** `/dashboard/ai-models`: providers table (masked key, last test), add/edit dialog (kind, key write-only, base URL, default model), test / delete, **task routing** table (provider, model, fallback, fallback model).

## 8. Verification
| Check | Result |
|---|---|
| Backend pytest | 68 passed (+5 phase-6: workflow guards & events; brief sources (cluster sibling, GSC query, entity via alias, existing page recommendation, competitors=false, echo note); calendar/board/from-opportunity/graph sync/details/delete; provider secret store (encrypted file, masked, clear, routes, cascade); provider probe with fake HTTP) |
| Live validation | 95/95 (+16) |
| Browser (real site) | Kanban + editor; content created with keyword picker («امداد خودرو چری #3.7»), scheduled; brief generated (H1 «امداد خودرو چری در تهران», 12 outline items incl. cluster sibling with volume, status → بریف آماده, transitions → نگارش / ← برنامه‌ریزی); calendar مرداد/شهریور ۱۴۰۵ with the item on ۵ شهریور (08-27); AI models: 6 kinds, key masked ••••BCD9, real test → HTTP 401 message, 8 routes selectable |
| tsc | 0 errors |

## 9. Notes
* One sample content item («راهنمای امداد خودرو MVM در تهران», with a real brief) was left on example-site as an example.
* Automatic publishing is **not** enabled — no WordPress write path exists; `published` is a manual state requiring a URL.
* Next: **Phase 7 — Content Calendar import (Sheet/CSV) + week view + drag&drop refinements**, then AI providers become live in Phase 9.

## 10. Release verification (2026-08-18, final)

| Area | Check | Result |
|---|---|---|
| Tests | `pytest` (all phases) | **68 passed** |
| Live HTTP | `validate-api.py` on :8000 (95 checks incl. content CRUD, transition guard 409, brief v1 + `brief_ready`, board, calendar day bucket, graph sync, delete; provider create masked / routes set+reset / delete) | **95/95** |
| Artifacts | `openapi.v1.json` (56 paths) + `frontend/src/lib/api/schema.d.ts` regenerated; `tsc` clean | ✅ |
| Security | provider create → API responses (list, routes, openapi) never contain the key; DB row holds only `secret_ref` + `key_hint`; `.iterdump()` of the DB has no key; secret file is DPAPI-encrypted (plaintext absent) and round-trips only via `SecretStore` (`backend=dpapi`); `data/logs/**` contains no key; GSC refresh token / client secret absent from `/connections*` responses; `data/secrets/`, `tokens/`, `.env` git-ignored and untracked; secret file removed on provider delete | ✅ all |
| Database | migrations applied `0001…0005`, none pending; `schema_migrations` has 0005; `PRAGMA foreign_key_check` empty; `PRAGMA integrity_check` = ok; every content item has ≥1 event; no dangling `brief_id`; graph sync: CONTENT nodes == content items, no dangling content edges | ✅ |
| Rollback | migrations are forward-only SQL (additive tables/columns; 0005 adds 5 tables, alters nothing). Rollback = stop API, restore `data/seo.db` from backup, or `DROP TABLE content_items, content_events, content_briefs, ai_providers, ai_routes` + delete row `0005` from `schema_migrations` (no other table references them). Secrets in `data/secrets/` are independent of the DB. | documented |

### Known limitations
* AI providers are **configured and testable, not yet used for generation** (Phase 9 wires real completions into the orchestrator); `use_ai=true` on briefs falls back to the rule brief and says so.
* Brief "competitors" source is reported unavailable (no SERP/competitor collector yet).
* Publishing is manual (URL + transition); no WordPress writer exists by design.
* Kanban drag only moves one stage forward/back (workflow rule), no multi-select.
* Calendar week view + Sheet/CSV import of the calendar are Phase 7 items.
