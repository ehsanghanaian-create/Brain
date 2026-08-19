# WordPress → Sync → Graph pipeline (integration of existing components)

**Status:** done (2026-08-19). No new WordPress architecture — this phase only *wires* components that already existed
(Phase 0.1 `wordpress/sync.py`, `crawler`, `graph/builder.py`, Phase 8.5 `brain/planner/categories.py`, the JobQueue and
the `sync_runs` table) into one production workflow:

```
WordPress connect (Phase 3) ──success──▶ wordpress_sync job (JobQueue, never inline)
                                            ├─ resolve       canonical WordPress base (common/urls.py::resolve_wordpress_base)
                                            ├─ categories    wp/v2/categories              ┐
                                            ├─ pages         wp/v2/pages                   │ wordpress.sync.sync_wordpress(progress=…)
                                            ├─ posts         wp/v2/posts (+ post_terms)    │ read-only REST, SecretStore creds
                                            ├─ taxonomies    other taxonomies + media      ┘
                                            ├─ category_intelligence  content_categories from the fresh snapshot (planner)
                                            ├─ crawl         enrichment only (links, headings, metrics) — optional, capped
                                            └─ build_graph   GraphBuild + keyword/content/planner graph syncs
```

## Components

| Piece | File | Notes |
|---|---|---|
| Orchestrator | `backend/seo_brain/wordpress/orchestrator.py` | `WordPressSyncOrchestrator(engine).run(site_id, run_id, stage, crawl, max_urls, job_id)`; per-site lock; state persisted as JSON in `sync_runs.notes` (`source='wordpress_pipeline'`) so status survives restarts. Steps + Persian labels in `STEPS`. |
| Job | `api/main.py::_register_builtin_jobs` → `wordpress_sync` | Payload `{site_id, run_id, stage: full|graph_only, crawl, max_urls, reason}`. |
| Trigger | `POST /sites/{id}/connections/wordpress/test` | On success (and `auto_sync: true`, the default) the response carries `detail.sync_job = {status:"queued", job_id, run_id, stage}` (or `already_running` / `not_queued`). |
| Manual | `POST /sites/{id}/wordpress/sync` (202, body `{crawl, max_urls}`), `POST /sites/{id}/graph/rebuild` (202, `stage=graph_only`) | 409 `wordpress_not_configured` when the site has no `wp_url`; a second start while running returns `{status:"already_running"}`. |
| Status | `GET /sites/{id}/wordpress/sync/status` | `{status: never|queued|running|succeeded|completed_with_errors|failed, step, step_fa, progress, stage, started_at, finished_at, items, errors, steps[], run_id, job_id, job, counts{categories,pages,posts,crawled,graph_nodes,graph_edges,graph_by_type}, steps_fa}`. |
| Canonical URL | `common/urls.py::resolve_wordpress_base` | One resolver for sync, crawl and graph: `normalize_wordpress_url` + http→https upgrade when `https://…/wp-json/` answers; the resolved base is stored back on `sites.wp_url` and is the only URL passed to `SiteConfig`. |
| Graph | `graph/builder.py` | WordPress pages/posts are the **source of truth** for `PAGE`/`POST` nodes (created even without a crawl, `crawled=false`); crawl rows only enrich. Relations: `SITE HAS_CATEGORY CATEGORY`, `CATEGORY BELONGS_TO CATEGORY` (tree), `SITE HAS_PAGE/HAS_POST`, `POST BELONGS_TO CATEGORY`, `LINKS_TO` from crawl; keyword/content/planner layers re-synced after each build. |
| Category sync reporting | `POST /sites/{id}/content-plans/categories/sync` | Never silent: `wordpress = {source:"wordpress_rest", status:"ok"|"failed"|"not_configured", reason?}` and, on failure, `wordpress_snapshot = {source:"snapshot", status:"ok"|"empty"}`. |
| UI | `frontend/src/features/sites/components/wordpress-sync-card.tsx` (+ pure helpers `features/sites/wp-sync.ts`) | Site detail → «اطلاعات و اتصال‌ها»: status badge, last sync date, counters (دسته‌بندی‌ها / صفحات / نوشته‌ها / گره‌های گراف), «شروع همگام‌سازی», «بازسازی گراف», 2 s polling while running, per-step progress (در حال دریافت دسته‌بندی‌ها / صفحات / نوشته‌ها / استخراج لینک‌ها / ساخت گراف), error list. Connection tester toasts the queued job. |

## Guarantees

* WordPress stays **read-only** (GET only); credentials resolved per site from the SecretStore (`wp-auth-{site_id}`) or `.env`,
  never written to status/notes/logs/API responses (tested).
* Everything runs through the JobQueue; API handlers only enqueue and read status. SQLite busy timeout raised to 30 s on
  the SQLAlchemy engine (`db/engine.py`) so API writes during a long sync wait instead of failing with `database is locked`.
* Status is idempotent/additive: no existing contract changed; `ConnectionTestRequest.auto_sync` (default `true`) is new.
* The job thread may persist before the API attaches the job id — `_persist` never overwrites a stored `job_id` with `None`.

## Tests / validation

* `backend/tests/api/test_wordpress_pipeline.py` — connection queues job + pipeline runs (steps, items, graph node/edge types),
  canonical URL (http→https, same base reaches sync & graph), manual start/status/rebuild/409/already_running/auto_sync=false,
  failed REST reporting + no credential leak + planner category sync reporting, job_id persistence race.
* `frontend/src/features/sites/__tests__/wp-sync.test.ts` — button state, progress/step label, counters, queue toasts, step rows.
* `cli/validate-api.py` — status (never) · start without wp_url → 409 · graph rebuild 202 → job succeeded · real-site counters (209/209).
* Live run on a real site (2026-08-19): categories 2 · pages 15 · posts 307 · media 788 · crawled 40 · graph 356 nodes / 1 615 edges.
