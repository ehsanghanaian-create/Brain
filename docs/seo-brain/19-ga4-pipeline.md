# GA4 Data Pipeline (first-class data source, GSC twin)

**Status:** done (2026-08-20). GA4 is now a first-class data source exactly like GSC — same architecture, no duplicates:
one shared Google OAuth token (now with `analytics.readonly`), the same JobQueue, the same `sync_runs` state pattern,
the same graph rebuild path, the same opportunity engine, the same content analytics snapshots.

```
Connect GA4 (Property ID, Phase 3 tester) ──success──▶ ga4_sync job (JobQueue, never inline)
    ├─ sync       ga4.sync.sync_ga4 — Data API v1beta runReport (date × pagePath + date × landingPage),
    │             metrics sessions/totalUsers/screenPageViews/engagementRate/averageSessionDuration/keyEvents
    │             (auto-fallback to legacy `conversions`), pagination, retry/backoff, raw cache data/raw/ga4/
    │             → ga4_daily upserts (idempotent) → history in sync_runs source='ga4'
    ├─ snapshot   ContentAnalytics.snapshot — GA4 columns on the SAME content_metrics rows (ga4_sessions/users/
    │             views/conversions/engagement_rate); items with only GA4 data now snapshot too
    └─ graph      wordpress orchestrator graph_only stage → ga4_* props on existing PAGE/POST nodes (crawled AND
                  uncrawled WP content) + run_analysis → GA4 opportunities in seo_opportunities
```

## Migration (the only one): `database/migrations/0010_ga4.sql`
- **`ga4_daily`** (style of `gsc_daily`): site_id · date · page_path (decoded) · sessions · total_users ·
  screen_page_views · engagement_rate · average_session_duration · conversions · source ('page'|'landing') ·
  sync_run_id · created_at; UNIQUE(site_id, date, page_path, source); indexes on site_id / (site_id,date) / (site_id,page_path).
- **`content_metrics`** + 5 columns: ga4_sessions, ga4_users, ga4_views, ga4_conversions, ga4_engagement_rate.
- No status table (state = `sync_runs`, sources `ga4` + `ga4_pipeline`), no GA4 graph-node types, no new OAuth.

## API
| Endpoint | Behaviour |
|---|---|
| `POST /sites/{id}/ga4/sync` | 202 `{status:"queued", job_id, run_id}` · body `{days}` 1–480 · 409 `ga4_not_configured` / `ga4_not_authorized` (missing analytics scope) · `already_running` guard |
| `GET /sites/{id}/ga4/sync/status` | run state + coverage `{date_from, date_to, rows, pages, sessions, users, conversions, content_snapshots, last_ga4_sync, top_pages[5]}` |
| `POST /sites/{id}/connections/ga4/test` | on success (and default `auto_sync:true`) queues the initial pipeline → `detail.sync_job` |
| `GET /sites/{id}/integrations` | GA4 block now carries the real sync state/coverage + `authorized` + actions |

## Graph (properties only — never nodes)
`PAGE`/`POST` nodes gain `ga4_sessions`, `ga4_users`, `ga4_conversions`, `ga4_engagement_rate`, `last_ga4_sync`
next to the existing `gsc_*` props. URL↔pagePath matched on decoded, slash-normalized paths; applies to crawled
pages and uncrawled WordPress content alike.

## Opportunity engine (existing `seo_opportunities`, rules in `analysis/seo.py`)
- `ga4_traffic_no_conversion` — ≥100 sessions با تبدیل ~صفر → «این صفحه ورودی زیادی دارد ولی تبدیل پایین است»
- `ga4_low_engagement` — ≥50 sessions با engagement < 35٪ → «صفحه نیاز به بهبود عنوان، محتوا یا UX دارد»
- `ga4_traffic_drop` — افت >40٪ در ۱۴ روز اخیر نسبت به دورهٔ قبل → «کاهش ترافیک GA4 نسبت به دوره قبل»

## UI
`Ga4IntegrationCard` (پیشین placeholder → کامل): وضعیت، property، بازه داده، آخرین sync، شمارنده‌ها
(Sessions / کاربران / تبدیل‌ها / صفحات دارای داده)، «پربازدیدترین صفحات»، دکمهٔ «همگام‌سازی»، مراحل progress،
خطاها — با همان `IntegrationCard`/`useIntegrationSyncStatus` مشترک مرکز اتصال‌ها.

## Security (verified)
Read-only scope; one shared token (`tokens/`, git-ignored) — no new OAuth; no service accounts; property id is the
only user input; credentials never in logs/status/API (log lines carry status codes only); scan clean.

## Scheduler
Manual + auto-after-connect for now, through the existing JobQueue — a future scheduler only needs to enqueue the
same `ga4_sync` job (same as `gsc_sync`/`wordpress_sync`; no new architecture required).

## Tests / validation
- `tests/api/test_ga4_pipeline.py` (7): client parsing/pagination + keyEvents→conversions fallback (fake service),
  full pipeline via job (202 → succeeded, coverage), snapshot columns on content_metrics, graph props + **no GA4
  node types**, GA4 opportunities, idempotent re-run (no duplicate rows/nodes, exactly one new table), 409 guards +
  permission failure → `not_authorized` (downstream skipped), connect-triggers-initial-sync (+opt-out).
- pytest **160** · vitest **28** (new `ga4-sync.test.ts`) · tsc clean · validate-api **215/215**.
- Live run (2026-08-20, `example-site`, property 123456789): 278 rows (182 page + 96 landing) · 55 pages ·
  521 sessions · 471 users → 34 PAGE/POST nodes with ga4 props → graph 418 nodes / 729 edges. Card shows all of it.
