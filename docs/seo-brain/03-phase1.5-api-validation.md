# Phase 1.5 — live API validation report

Date: 2026-08-17T16:40:09+00:00 · Base: `http://127.0.0.1:8000` · Site: `emdadmodiran` · Temp site: `zz-validation-263445` (created and force-deleted)

**Result: 79/79 checks passed**

| # | Check | Method | Path | Status | Expected | ms | OK | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | root | GET | `/` | 200 | 200 | 284 | ✅ |  |
| 2 | openapi | GET | `/api/openapi.json` | 200 | 200 | 199 | ✅ |  |
| 3 | docs | GET | `/api/docs` | 200 | 200 | 214 | ✅ |  |
| 4 | health | GET | `/api/v1/health` | 200 | 200 | 225 | ✅ |  |
| 5 | request-id header | GET | `/api/v1/health` | 200 | 200 | 203 | ✅ |  |
| 6 | request-id echoed | GET | `/api/v1/health` | 200 | 200 | 201 | ✅ |  |
| 7 | 404 envelope | GET | `/api/v1/sites/nope-nope` | 404 | 404 | 215 | ✅ |  |
| 8 | 422 envelope | POST | `/api/v1/sites` | 422 | 422 | 220 | ✅ |  |
| 9 | sites list | GET | `/api/v1/sites` | 200 | 200 | 208 | ✅ |  |
| 10 | site get | GET | `/api/v1/sites/emdadmodiran` | 200 | 200 | 204 | ✅ |  |
| 11 | site create | POST | `/api/v1/sites` | 201 | 201 | 213 | ✅ |  |
| 12 | site create duplicate → 409 | POST | `/api/v1/sites` | 409 | 409 | 214 | ✅ |  |
| 13 | site patch mode | PATCH | `/api/v1/sites/zz-validation-263445` | 200 | 200 | 222 | ✅ |  |
| 14 | site patch invalid mode → 422 | PATCH | `/api/v1/sites/zz-validation-263445` | 422 | 422 | 420 | ✅ |  |
| 15 | graph summary | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 390 | ✅ |  |
| 16 | graph nodes (types=PAGE,POST) | GET | `/api/v1/sites/emdadmodiran/graph/nodes?types=PAGE,POST&limit=5` | 200 | 200 | 381 | ✅ |  |
| 17 | graph node | GET | `/api/v1/sites/emdadmodiran/graph/node/page:https://emdadmodiran.com/` | 200 | 200 | 453 | ✅ |  |
| 18 | graph node 404 | GET | `/api/v1/sites/emdadmodiran/graph/node/nope:x` | 404 | 404 | 419 | ✅ |  |
| 19 | graph neighbors | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/` | 200 | 200 | 372 | ✅ |  |
| 20 | graph neighbors filtered | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/?relation_types=LINKS_TO&direction=out` | 200 | 200 | 376 | ✅ |  |
| 21 | graph subgraph hops=2 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=2&max_nodes=100` | 200 | 200 | 403 | ✅ |  |
| 22 | graph subgraph bad hops → 422 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=9` | 422 | 422 | 385 | ✅ |  |
| 23 | graph search | GET | `/api/v1/sites/emdadmodiran/graph/search?q=امداد` | 200 | 200 | 373 | ✅ |  |
| 24 | graph path | GET | `/api/v1/sites/emdadmodiran/graph/path?source=site:emdadmodiran&target=page:https://emdadmodiran.com/` | 200 | 200 | 374 | ✅ |  |
| 25 | graph orphans | GET | `/api/v1/sites/emdadmodiran/graph/orphans` | 200 | 200 | 381 | ✅ |  |
| 26 | graph on unknown site → 404 | GET | `/api/v1/sites/nope-nope/graph/summary` | 404 | 404 | 368 | ✅ |  |
| 27 | graph modes | GET | `/api/v1/sites/emdadmodiran/graph/modes` | 200 | 200 | 399 | ✅ |  |
| 28 | graph view seo | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=seo` | 200 | 200 | 404 | ✅ |  |
| 29 | graph view links (no isolated) | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=links&include_isolated=false` | 200 | 200 | 408 | ✅ |  |
| 30 | graph view content types filter | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=content&types=SCHEMA,PAGE` | 200 | 200 | 422 | ✅ |  |
| 31 | graph view bad mode → 422 | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=nope` | 422 | 422 | 361 | ✅ |  |
| 32 | node details (page) | GET | `/api/v1/sites/emdadmodiran/graph/node-details/page:https://emdadmodiran.com/` | 200 | 200 | 401 | ✅ |  |
| 33 | node details 404 | GET | `/api/v1/sites/emdadmodiran/graph/node-details/nope:x` | 404 | 404 | 443 | ✅ |  |
| 34 | memory get (empty) | GET | `/api/v1/sites/zz-validation-263445/memory` | 200 | 200 | 372 | ✅ |  |
| 35 | memory put | PUT | `/api/v1/sites/zz-validation-263445/memory` | 200 | 200 | 388 | ✅ |  |
| 36 | memory context | GET | `/api/v1/sites/zz-validation-263445/memory/context` | 200 | 200 | 463 | ✅ |  |
| 37 | memory get (real site, read-only) | GET | `/api/v1/sites/emdadmodiran/memory` | 200 | 200 | 443 | ✅ |  |
| 38 | ai routes | GET | `/api/v1/ai/routes` | 200 | 200 | 452 | ✅ |  |
| 39 | ai providers | GET | `/api/v1/ai/providers` | 200 | 200 | 412 | ✅ |  |
| 40 | ai run text | POST | `/api/v1/ai/sites/zz-validation-263445/run` | 200 | 200 | 384 | ✅ |  |
| 41 | ai run json + learn | POST | `/api/v1/ai/sites/zz-validation-263445/run` | 200 | 200 | 421 | ✅ |  |
| 42 | memory learned pattern | GET | `/api/v1/sites/zz-validation-263445/memory` | 200 | 200 | 352 | ✅ |  |
| 43 | ai run unknown kind → 422 | POST | `/api/v1/ai/sites/zz-validation-263445/run` | 422 | 422 | 405 | ✅ |  |
| 44 | job enqueue noop | POST | `/api/v1/jobs` | 202 | 202 | 446 | ✅ |  |
| 45 | job run finished | GET | `/api/v1/jobs/job-7c3b2750ac5e` | 200 | 200 | 370 | ✅ |  |
| 46 | jobs list | GET | `/api/v1/jobs` | 200 | 200 | 354 | ✅ |  |
| 47 | job unknown type → 422 | POST | `/api/v1/jobs` | 422 | 422 | 400 | ✅ |  |
| 48 | job unknown run → 404 | GET | `/api/v1/jobs/none` | 404 | 404 | 366 | ✅ |  |
| 49 | connections status (empty) | GET | `/api/v1/sites/zz-validation-263445/connections` | 200 | 200 | 361 | ✅ |  |
| 50 | gsc test without property → not_configured | POST | `/api/v1/sites/zz-validation-263445/connections/gsc/test` | 200 | 200 | 387 | ✅ |  |
| 51 | ga4 test bad id → not_configured | POST | `/api/v1/sites/zz-validation-263445/connections/ga4/test` | 200 | 200 | 382 | ✅ |  |
| 52 | wordpress test (real site, read-only) | POST | `/api/v1/sites/zz-validation-263445/connections/wordpress/test` | 200 | 200 | 3660 | ✅ |  |
| 53 | connections status (3 kinds) | GET | `/api/v1/sites/zz-validation-263445/connections` | 200 | 200 | 402 | ✅ |  |
| 54 | gsc properties listing | GET | `/api/v1/connections/gsc/properties` | 200 | 200 | 1762 | ✅ |  |
| 55 | unknown connection kind → 404 | POST | `/api/v1/sites/zz-validation-263445/connections/nope/test` | 404 | 404 | 364 | ✅ |  |
| 56 | initialize | POST | `/api/v1/sites/zz-validation-263445/initialize` | 200 | 200 | 429 | ✅ |  |
| 57 | initialize idempotent | POST | `/api/v1/sites/zz-validation-263445/initialize` | 200 | 200 | 451 | ✅ |  |
| 58 | site brain put (audience/cta/forbidden) | PUT | `/api/v1/sites/zz-validation-263445/memory` | 200 | 200 | 410 | ✅ |  |
| 59 | site brain in AI context | GET | `/api/v1/sites/zz-validation-263445/memory/context` | 200 | 200 | 403 | ✅ |  |
| 60 | keywords import dry-run | POST | `/api/v1/sites/zz-validation-263445/keywords/import` | 200 | 200 | 411 | ✅ |  |
| 61 | keywords import commit | POST | `/api/v1/sites/zz-validation-263445/keywords/import` | 200 | 200 | 412 | ✅ |  |
| 62 | keywords list | GET | `/api/v1/sites/zz-validation-263445/keywords` | 200 | 200 | 391 | ✅ |  |
| 63 | keyword create | POST | `/api/v1/sites/zz-validation-263445/keywords` | 201 | 201 | 387 | ✅ |  |
| 64 | keyword create duplicate → 409 | POST | `/api/v1/sites/zz-validation-263445/keywords` | 409 | 409 | 368 | ✅ |  |
| 65 | keyword patch | PATCH | `/api/v1/sites/zz-validation-263445/keywords/14` | 200 | 200 | 381 | ✅ |  |
| 66 | keyword detail | GET | `/api/v1/sites/zz-validation-263445/keywords/14` | 200 | 200 | 530 | ✅ |  |
| 67 | keywords cluster | POST | `/api/v1/sites/zz-validation-263445/keywords/cluster` | 200 | 200 | 445 | ✅ |  |
| 68 | keywords topic-map | GET | `/api/v1/sites/zz-validation-263445/keywords/topic-map` | 200 | 200 | 378 | ✅ |  |
| 69 | keywords analyze | POST | `/api/v1/sites/zz-validation-263445/keywords/analyze` | 200 | 200 | 404 | ✅ |  |
| 70 | keyword opportunities | GET | `/api/v1/sites/zz-validation-263445/keywords/opportunities` | 200 | 200 | 398 | ✅ |  |
| 71 | keywords in graph view | GET | `/api/v1/sites/zz-validation-263445/graph/view?mode=seo&types=KEYWORD,TOPIC` | 200 | 200 | 399 | ✅ |  |
| 72 | keyword delete | DELETE | `/api/v1/sites/zz-validation-263445/keywords/14` | 200 | 200 | 404 | ✅ |  |
| 73 | keywords meta | GET | `/api/v1/sites/zz-validation-263445/keywords/meta` | 200 | 200 | 374 | ✅ |  |
| 74 | legacy dashboard | GET | `/legacy/` | 200 | 200 | 409 | ✅ |  |
| 75 | legacy api | GET | `/legacy/api/sites` | 200 | 200 | 412 | ✅ |  |
| 76 | site delete refused (has data) → 409 | DELETE | `/api/v1/sites/zz-validation-263445` | 409 | 409 | 393 | ✅ |  |
| 77 | site delete force | DELETE | `/api/v1/sites/zz-validation-263445?force=true` | 200 | 200 | 394 | ✅ |  |
| 78 | site gone → 404 | GET | `/api/v1/sites/zz-validation-263445` | 404 | 404 | 439 | ✅ |  |
| 79 | real site untouched | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 385 | ✅ |  |

## Coverage

* health / openapi / docs / request-id · error envelope (404, 409, 422) · sites CRUD (create, get, list, patch, delete-refuse, delete-force, 404 after) ·
  phase 3: connections status/tests (gsc/ga4/wordpress + 404 kind), gsc properties listing, initialize (idempotent), site brain fields + AI context ·
  graph (summary, nodes, node, 404, neighbors, filtered neighbors, subgraph, 422, search, path, orphans, unknown site) ·
  memory (get, put, context, learned pattern) · AI orchestrator (routes, providers, text run, JSON run + learn, 422) · jobs (enqueue, poll, list, 422, 404) · legacy mount.
* All checks ran over real HTTP against uvicorn (not TestClient). Read-only on the real site; writes only on the temporary site.
