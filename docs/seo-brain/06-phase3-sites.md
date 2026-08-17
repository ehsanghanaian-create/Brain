# SEO Brain — Phase 3: Sites management (wizard · connections · workspace · Site Brain)

Date: 2026-08-17 · Existing API contracts unchanged (additive only) · Backend tests **56/56** · Live API validation **58/58** · `tsc` clean · verified end-to-end in the browser against real Google/WordPress services.

## 1. Backend (additive)

### Migration `0003_site_brain_and_connections.sql`
* `site_memory` + `audience` (JSON: `{segments[], pains[], intent_notes}`), `cta_rules` (JSON list), `forbidden_claims` (JSON list) → the full **Site Brain**: business_rules · tone · audience · cta_rules · content_rules · forbidden_claims · successful_patterns.
* `site_connections (site_id, kind, status, detail, tested_at)` — last known status per connection (`gsc | ga4 | wordpress`; `ok | not_configured | not_authorized | not_found | error`). `detail` never contains secrets.
* `sites.timezone`.

### New endpoints (see `04-frontend-contract.md §8`)
| Endpoint | Purpose |
|---|---|
| `GET /sites/{id}/connections` | `{configured:{gsc,ga4,wordpress}, status:{kind→ConnectionResult}}` |
| `POST /sites/{id}/connections/{gsc\|ga4\|wordpress}/test` body `{property?}` | read-only permission test; on success the property is stored on the site (targeted column update) |
| `GET /connections/gsc/properties` | properties visible to the connected Google account (wizard dropdown) |
| `POST /sites/{id}/initialize` | wizard step 3: workspace dirs + README, `site_memory` row, `SITE` graph node `site:<id>` — idempotent |
| `PUT /sites/{id}/memory` | now accepts the new Site Brain fields (partial update) |

`SiteCreate/SiteUpdate` gained `timezone`. `MemoryService.context_messages` now injects audience, CTA rules and a **"NEVER claim (forbidden)"** block into every AI task for the site.

### Services
* `seo_brain.connections.ConnectionsService` — GSC (uses the existing OAuth token; checks client config → token → scope → property resolution → permission level), GA4 (Analytics Data API probe; the current token only has `webmasters.readonly`, so it reports `not_authorized` with the required scope — honest, no guessing), WordPress (`GET /wp-json/`, read-only). Factories are injectable → tests run without network.
* `seo_brain.sites.SiteInitializer` — workspace (`data/sites/<id>/{raw,exports,uploads,vault,logs}` + README), memory row, graph namespace; `slugify_domain()` mirrors the frontend.
* `seo_brain.common.config.load_sites()` now also returns **DB-created sites** (wizard sites) with default crawler/GSC/graph settings, so `sync-*`/`build-graph` jobs work for them.
* `SitesRepository.set_fields()` — targeted `UPDATE`; found and fixed a real lost-update bug: three parallel connection tests each saved the whole row and the last one erased the GSC property (regression test added). `DELETE /sites` now also clears `site_connections`.

## 2. Frontend

* `/dashboard/sites` — "افزودن سایت" button, site names link to the detail page.
* `/dashboard/sites/new` — **3-step wizard** (`features/sites/components/site-wizard.tsx`):
  1. نام · دامنه · شناسه (auto-slug, editable) · حوزه کسب‌وکار (10 categories) · زبان · مکان/کشور (+ timezone) → `POST /sites` (409 = resume existing site).
  2. اتصال‌ها — `ConnectionTester` rows for GSC (dropdown of the account's real properties, or free text), GA4 property id, WordPress URL; each has "تست دسترسی" showing status badge + backend message; can be skipped.
  3. ایجاد فضای کاری → `POST /initialize` → checklist (workspace / memory / graph node) → links to the site page and Site Brain.
* `/dashboard/sites/[siteId]` — tabs **اطلاعات و اتصال‌ها** (specs, workspace, graph counts, publish mode selector `manual/assisted/autopilot` via `PATCH`, re-run initialize, connection re-tests with last status) and **مغز سایت** (`SiteBrainForm`: business rules · tone (voice/formality/person/language notes) · audience (segments/pains/intent) · CTA rules · content rules · forbidden claims · learned patterns read-only) → `PUT /memory`, toast + refresh.
* Types regenerated from `openapi.v1.json` (22 paths); the stale-type compile error before regeneration is the contract doing its job.

## 3. Verification

| Check | Result |
|---|---|
| pytest (backend) | 56 passed (+8 phase-3 tests: migration/memory fields, slugify, initialize idempotency, GSC flow with fake client, GA4 scope gate + ok, WordPress fake HTTP + 404 kind, concurrent-update regression, delete with connections) |
| Live validation (`validate-api.py`) | 58/58 incl. the new endpoints |
| Browser (Next.js → proxy → FastAPI) | Wizard step 1 created `wizard-test`; step 2 dropdown listed the **real** 21 GSC properties, GSC test → متصل (siteOwner), GA4 → بدون مجوز (scope), WordPress → متصل; step 3 initialize → 3 ✅; Site Brain saved and appeared in `/memory/context`; publish-mode select works; throwaway site force-deleted afterwards |
| tsc | 0 errors |

## 4. Not in scope (as instructed) / next
* Content Brain untouched. GA4 OAuth scope upgrade (`sync-ga4.py --auth-only`) is a small follow-up when GA4 data is needed (Phase 15/17).
* Next: **Phase 4 — Knowledge Graph UI (React Flow)**.
