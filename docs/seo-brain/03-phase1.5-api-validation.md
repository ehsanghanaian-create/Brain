# Phase 1.5 — live API validation report

Date: 2026-08-17T15:51:16+00:00 · Base: `http://127.0.0.1:8000` · Site: `emdadmodiran` · Temp site: `zz-validation-744117` (created and force-deleted)

**Result: 65/65 checks passed**

| # | Check | Method | Path | Status | Expected | ms | OK | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | root | GET | `/` | 200 | 200 | 366 | ✅ |  |
| 2 | openapi | GET | `/api/openapi.json` | 200 | 200 | 431 | ✅ |  |
| 3 | docs | GET | `/api/docs` | 200 | 200 | 257 | ✅ |  |
| 4 | health | GET | `/api/v1/health` | 200 | 200 | 240 | ✅ |  |
| 5 | request-id header | GET | `/api/v1/health` | 200 | 200 | 228 | ✅ |  |
| 6 | request-id echoed | GET | `/api/v1/health` | 200 | 200 | 234 | ✅ |  |
| 7 | 404 envelope | GET | `/api/v1/sites/nope-nope` | 404 | 404 | 218 | ✅ |  |
| 8 | 422 envelope | POST | `/api/v1/sites` | 422 | 422 | 293 | ✅ |  |
| 9 | sites list | GET | `/api/v1/sites` | 200 | 200 | 254 | ✅ |  |
| 10 | site get | GET | `/api/v1/sites/emdadmodiran` | 200 | 200 | 285 | ✅ |  |
| 11 | site create | POST | `/api/v1/sites` | 201 | 201 | 532 | ✅ |  |
| 12 | site create duplicate → 409 | POST | `/api/v1/sites` | 409 | 409 | 442 | ✅ |  |
| 13 | site patch mode | PATCH | `/api/v1/sites/zz-validation-744117` | 200 | 200 | 463 | ✅ |  |
| 14 | site patch invalid mode → 422 | PATCH | `/api/v1/sites/zz-validation-744117` | 422 | 422 | 456 | ✅ |  |
| 15 | graph summary | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 474 | ✅ |  |
| 16 | graph nodes (types=PAGE,POST) | GET | `/api/v1/sites/emdadmodiran/graph/nodes?types=PAGE,POST&limit=5` | 200 | 200 | 451 | ✅ |  |
| 17 | graph node | GET | `/api/v1/sites/emdadmodiran/graph/node/page:https://emdadmodiran.com/` | 200 | 200 | 486 | ✅ |  |
| 18 | graph node 404 | GET | `/api/v1/sites/emdadmodiran/graph/node/nope:x` | 404 | 404 | 457 | ✅ |  |
| 19 | graph neighbors | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/` | 200 | 200 | 435 | ✅ |  |
| 20 | graph neighbors filtered | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/?relation_types=LINKS_TO&direction=out` | 200 | 200 | 444 | ✅ |  |
| 21 | graph subgraph hops=2 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=2&max_nodes=100` | 200 | 200 | 457 | ✅ |  |
| 22 | graph subgraph bad hops → 422 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=9` | 422 | 422 | 451 | ✅ |  |
| 23 | graph search | GET | `/api/v1/sites/emdadmodiran/graph/search?q=امداد` | 200 | 200 | 482 | ✅ |  |
| 24 | graph path | GET | `/api/v1/sites/emdadmodiran/graph/path?source=site:emdadmodiran&target=page:https://emdadmodiran.com/` | 200 | 200 | 482 | ✅ |  |
| 25 | graph orphans | GET | `/api/v1/sites/emdadmodiran/graph/orphans` | 200 | 200 | 465 | ✅ |  |
| 26 | graph on unknown site → 404 | GET | `/api/v1/sites/nope-nope/graph/summary` | 404 | 404 | 474 | ✅ |  |
| 27 | graph modes | GET | `/api/v1/sites/emdadmodiran/graph/modes` | 200 | 200 | 482 | ✅ |  |
| 28 | graph view seo | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=seo` | 200 | 200 | 477 | ✅ |  |
| 29 | graph view links (no isolated) | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=links&include_isolated=false` | 200 | 200 | 485 | ✅ |  |
| 30 | graph view content types filter | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=content&types=SCHEMA,PAGE` | 200 | 200 | 467 | ✅ |  |
| 31 | graph view bad mode → 422 | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=nope` | 422 | 422 | 465 | ✅ |  |
| 32 | node details (page) | GET | `/api/v1/sites/emdadmodiran/graph/node-details/page:https://emdadmodiran.com/` | 200 | 200 | 534 | ✅ |  |
| 33 | node details 404 | GET | `/api/v1/sites/emdadmodiran/graph/node-details/nope:x` | 404 | 404 | 472 | ✅ |  |
| 34 | memory get (empty) | GET | `/api/v1/sites/zz-validation-744117/memory` | 200 | 200 | 478 | ✅ |  |
| 35 | memory put | PUT | `/api/v1/sites/zz-validation-744117/memory` | 200 | 200 | 466 | ✅ |  |
| 36 | memory context | GET | `/api/v1/sites/zz-validation-744117/memory/context` | 200 | 200 | 484 | ✅ |  |
| 37 | memory get (real site, read-only) | GET | `/api/v1/sites/emdadmodiran/memory` | 200 | 200 | 485 | ✅ |  |
| 38 | ai routes | GET | `/api/v1/ai/routes` | 200 | 200 | 480 | ✅ |  |
| 39 | ai providers | GET | `/api/v1/ai/providers` | 200 | 200 | 549 | ✅ |  |
| 40 | ai run text | POST | `/api/v1/ai/sites/zz-validation-744117/run` | 200 | 200 | 507 | ✅ |  |
| 41 | ai run json + learn | POST | `/api/v1/ai/sites/zz-validation-744117/run` | 200 | 200 | 468 | ✅ |  |
| 42 | memory learned pattern | GET | `/api/v1/sites/zz-validation-744117/memory` | 200 | 200 | 458 | ✅ |  |
| 43 | ai run unknown kind → 422 | POST | `/api/v1/ai/sites/zz-validation-744117/run` | 422 | 422 | 469 | ✅ |  |
| 44 | job enqueue noop | POST | `/api/v1/jobs` | 202 | 202 | 458 | ✅ |  |
| 45 | job run finished | GET | `/api/v1/jobs/job-b8f19dc7b971` | 200 | 200 | 468 | ✅ |  |
| 46 | jobs list | GET | `/api/v1/jobs` | 200 | 200 | 482 | ✅ |  |
| 47 | job unknown type → 422 | POST | `/api/v1/jobs` | 422 | 422 | 481 | ✅ |  |
| 48 | job unknown run → 404 | GET | `/api/v1/jobs/none` | 404 | 404 | 468 | ✅ |  |
| 49 | connections status (empty) | GET | `/api/v1/sites/zz-validation-744117/connections` | 200 | 200 | 488 | ✅ |  |
| 50 | gsc test without property → not_configured | POST | `/api/v1/sites/zz-validation-744117/connections/gsc/test` | 200 | 200 | 482 | ✅ |  |
| 51 | ga4 test bad id → not_configured | POST | `/api/v1/sites/zz-validation-744117/connections/ga4/test` | 200 | 200 | 536 | ✅ |  |
| 52 | wordpress test (real site, read-only) | POST | `/api/v1/sites/zz-validation-744117/connections/wordpress/test` | 200 | 200 | 6379 | ✅ |  |
| 53 | connections status (3 kinds) | GET | `/api/v1/sites/zz-validation-744117/connections` | 200 | 200 | 513 | ✅ |  |
| 54 | gsc properties listing | GET | `/api/v1/connections/gsc/properties` | 200 | 200 | 5531 | ✅ |  |
| 55 | unknown connection kind → 404 | POST | `/api/v1/sites/zz-validation-744117/connections/nope/test` | 404 | 404 | 445 | ✅ |  |
| 56 | initialize | POST | `/api/v1/sites/zz-validation-744117/initialize` | 200 | 200 | 525 | ✅ |  |
| 57 | initialize idempotent | POST | `/api/v1/sites/zz-validation-744117/initialize` | 200 | 200 | 464 | ✅ |  |
| 58 | site brain put (audience/cta/forbidden) | PUT | `/api/v1/sites/zz-validation-744117/memory` | 200 | 200 | 464 | ✅ |  |
| 59 | site brain in AI context | GET | `/api/v1/sites/zz-validation-744117/memory/context` | 200 | 200 | 478 | ✅ |  |
| 60 | legacy dashboard | GET | `/legacy/` | 200 | 200 | 520 | ✅ |  |
| 61 | legacy api | GET | `/legacy/api/sites` | 200 | 200 | 458 | ✅ |  |
| 62 | site delete refused (has data) → 409 | DELETE | `/api/v1/sites/zz-validation-744117` | 409 | 409 | 499 | ✅ |  |
| 63 | site delete force | DELETE | `/api/v1/sites/zz-validation-744117?force=true` | 200 | 200 | 469 | ✅ |  |
| 64 | site gone → 404 | GET | `/api/v1/sites/zz-validation-744117` | 404 | 404 | 456 | ✅ |  |
| 65 | real site untouched | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 496 | ✅ |  |

## Coverage

* health / openapi / docs / request-id · error envelope (404, 409, 422) · sites CRUD (create, get, list, patch, delete-refuse, delete-force, 404 after) ·
  phase 3: connections status/tests (gsc/ga4/wordpress + 404 kind), gsc properties listing, initialize (idempotent), site brain fields + AI context ·
  graph (summary, nodes, node, 404, neighbors, filtered neighbors, subgraph, 422, search, path, orphans, unknown site) ·
  memory (get, put, context, learned pattern) · AI orchestrator (routes, providers, text run, JSON run + learn, 422) · jobs (enqueue, poll, list, 422, 404) · legacy mount.
* All checks ran over real HTTP against uvicorn (not TestClient). Read-only on the real site; writes only on the temporary site.
