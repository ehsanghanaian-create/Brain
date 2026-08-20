# GSC production pipeline (integration of existing components)

**Status:** done (2026-08-20). No new GSC architecture: no tables, no migrations, no OAuth flow, no opportunity engine,
no graph nodes. This phase only *wires* what already existed into a product workflow.

```
Before:  python cli/sync-gsc.py   (manual terminal only; snapshot never ran; nothing after connect)

After:   Connect GSC (Phase 3 tester) ──success──▶ gsc_sync job (JobQueue, never inline)
             ├─ sync                    gsc.sync.sync_gsc — non-interactive, gsc_daily → aggregate → gsc_query_page + queries
             ├─ keyword_opportunities   brain.keywords.KeywordService.analyze (skipped: no keywords)
             ├─ snapshot                brain.content.analytics.ContentAnalytics.snapshot → content_metrics (skipped: no content with URL)
             └─ graph                   wordpress.orchestrator graph_only stage — the one existing rebuild path (QUERY nodes, RANKS_FOR)
         Keyword Brain → Content Brain → Graph → Opportunities all read the same tables as before.
```

## Components

| Piece | File | Notes |
|---|---|---|
| Pipeline | `backend/seo_brain/gsc/pipeline.py` | `GscPipeline(engine).run(site_id, run_id, days, job_id)`; per-site lock; state as JSON in the existing `sync_runs` table (`source='gsc_pipeline'`); `sync_gsc` keeps writing its historical `source='gsc'` rows. Steps + Persian labels in `STEPS`. Statuses: queued/running/succeeded/completed_with_errors/failed/**not_authorized**. |
| Job | `api/main.py::_register_builtin_jobs` → `gsc_sync` | Payload `{site_id, run_id, days, reason}`; the queue now injects `job_id` into every job payload at enqueue (`automation/queue.py`), removing the attach-race for both pipelines. |
| Trigger | `POST /sites/{id}/connections/gsc/test` | On success (and `auto_sync: true`, the existing default) the response carries `detail.sync_job = {status:"queued", job_id, run_id}`. |
| Manual | `POST /sites/{id}/gsc/sync` (202, body `{days}` 1–480) | 409 `gsc_not_configured` (no property) · 409 `gsc_not_authorized` (no Google token) · `{status:"already_running"}` guard. |
| Status | `GET /sites/{id}/gsc/sync/status` | `{property, authorized, status, step, step_fa, progress, steps[], items, errors, run_id, job_id, job, coverage{date_from,date_to,rows,queries,important_queries,pages,content_snapshots,keyword_opportunities,last_gsc_sync}, steps_fa}` — coverage read live from `gsc_daily`/`queries`/`gsc_query_page`/`content_metrics`. |
| UI | `frontend/src/features/sites/components/gsc-sync-card.tsx` (+ pure helpers `features/sites/gsc-sync.ts`) | Site detail → «اطلاعات و اتصال‌ها»: وضعیت (متصل/در حال اجرا/ناموفق/بدون مجوز Google), property, آخرین sync, بازه داده, counters (کوئری‌ها/کوئری‌های مهم/صفحات دارای داده/ردیف‌های خام), دکمه «همگام‌سازی», step progress, 2 s polling; the connection tester toasts the queued job. |

## No browser OAuth in the worker

`sync_gsc(..., interactive=False)`: with no valid token the job never opens a browser — the run ends as
`not_authorized` with the hint «sync-gsc.py --auth-only», downstream steps are skipped, and the endpoint refuses
upfront with 409 `gsc_not_authorized` when the token file is absent.

## Secret handling (audit result)

- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: `.env` stays primary; `gsc/client.py::_client_config` now **falls back
  to the SecretStore** (refs `google-client-id`, `google-client-secret`, DPAPI — the same store WordPress/AI use). Existing
  setups keep working unchanged; new setups may store the OAuth client in the SecretStore instead of `.env`.
- The Google **refresh token** stays at `tokens/gsc_token.json` (git-ignored): `google-auth` reads/writes it as a file
  and the CLI (`sync-gsc.py --auth-only`) must keep working — moving it into the SecretStore would break that flow, so
  it is documented as accepted. It never appears in logs, API responses, or the DB.

## Also fixed while validating live

- Graph node lookups are now encoding-tolerant (`db/repositories/graph.py::get_node` tries the exact id, then
  percent-decoded, then re-encoded): WordPress REST stores Persian URLs percent-encoded while the crawler stores them
  decoded, which 404'd `/graph/node|neighbors|subgraph|node-details` on WP-synced sites.
- `InProcessJobQueue.enqueue` injects `job_id` into the payload before the worker starts.

## Tests / validation

- `backend/tests/api/test_gsc_pipeline.py` (7) — job registered as builtin, 202 + status from `sync_runs`, 409
  not_configured / not_authorized / already_running, connect-triggers-initial-sync (+`auto_sync:false` opt-out),
  not_authorized skips downstream, re-run produces no duplicate graph nodes/rows, **no duplicate GSC tables**.
- `frontend/src/features/sites/__tests__/gsc-sync.test.ts` (6) — card states, button gating, counters, errors.
- pytest 151 · vitest 23 · tsc clean · validate-api **212/212** (new: gsc status never / 409 / real-site coverage).
- Live run (2026-08-20, `example-site`): 726 rows → 68 queries (46 important) → 9 keyword opportunities →
  snapshot skipped (`no_content_with_url`) → graph 120 nodes / 444 edges. Card renders all of it.
