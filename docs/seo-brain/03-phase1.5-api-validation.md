# Phase 1.5 — live API validation report

Date: 2026-08-18T08:18:13+00:00 · Base: `http://127.0.0.1:8000` · Site: `emdadmodiran` · Temp site: `zz-validation-9967eb` (created and force-deleted)

**Result: 95/95 checks passed**

| # | Check | Method | Path | Status | Expected | ms | OK | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | root | GET | `/` | 200 | 200 | 461 | ✅ |  |
| 2 | openapi | GET | `/api/openapi.json` | 200 | 200 | 472 | ✅ |  |
| 3 | docs | GET | `/api/docs` | 200 | 200 | 250 | ✅ |  |
| 4 | health | GET | `/api/v1/health` | 200 | 200 | 279 | ✅ |  |
| 5 | request-id header | GET | `/api/v1/health` | 200 | 200 | 259 | ✅ |  |
| 6 | request-id echoed | GET | `/api/v1/health` | 200 | 200 | 249 | ✅ |  |
| 7 | 404 envelope | GET | `/api/v1/sites/nope-nope` | 404 | 404 | 252 | ✅ |  |
| 8 | 422 envelope | POST | `/api/v1/sites` | 422 | 422 | 270 | ✅ |  |
| 9 | sites list | GET | `/api/v1/sites` | 200 | 200 | 394 | ✅ |  |
| 10 | site get | GET | `/api/v1/sites/emdadmodiran` | 200 | 200 | 449 | ✅ |  |
| 11 | site create | POST | `/api/v1/sites` | 201 | 201 | 510 | ✅ |  |
| 12 | site create duplicate → 409 | POST | `/api/v1/sites` | 409 | 409 | 422 | ✅ |  |
| 13 | site patch mode | PATCH | `/api/v1/sites/zz-validation-9967eb` | 200 | 200 | 439 | ✅ |  |
| 14 | site patch invalid mode → 422 | PATCH | `/api/v1/sites/zz-validation-9967eb` | 422 | 422 | 427 | ✅ |  |
| 15 | graph summary | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 516 | ✅ |  |
| 16 | graph nodes (types=PAGE,POST) | GET | `/api/v1/sites/emdadmodiran/graph/nodes?types=PAGE,POST&limit=5` | 200 | 200 | 560 | ✅ |  |
| 17 | graph node | GET | `/api/v1/sites/emdadmodiran/graph/node/page:https://emdadmodiran.com/` | 200 | 200 | 378 | ✅ |  |
| 18 | graph node 404 | GET | `/api/v1/sites/emdadmodiran/graph/node/nope:x` | 404 | 404 | 393 | ✅ |  |
| 19 | graph neighbors | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/` | 200 | 200 | 284 | ✅ |  |
| 20 | graph neighbors filtered | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/?relation_types=LINKS_TO&direction=out` | 200 | 200 | 300 | ✅ |  |
| 21 | graph subgraph hops=2 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=2&max_nodes=100` | 200 | 200 | 419 | ✅ |  |
| 22 | graph subgraph bad hops → 422 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=9` | 422 | 422 | 344 | ✅ |  |
| 23 | graph search | GET | `/api/v1/sites/emdadmodiran/graph/search?q=امداد` | 200 | 200 | 321 | ✅ |  |
| 24 | graph path | GET | `/api/v1/sites/emdadmodiran/graph/path?source=site:emdadmodiran&target=page:https://emdadmodiran.com/` | 200 | 200 | 355 | ✅ |  |
| 25 | graph orphans | GET | `/api/v1/sites/emdadmodiran/graph/orphans` | 200 | 200 | 438 | ✅ |  |
| 26 | graph on unknown site → 404 | GET | `/api/v1/sites/nope-nope/graph/summary` | 404 | 404 | 411 | ✅ |  |
| 27 | graph modes | GET | `/api/v1/sites/emdadmodiran/graph/modes` | 200 | 200 | 450 | ✅ |  |
| 28 | graph view seo | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=seo` | 200 | 200 | 434 | ✅ |  |
| 29 | graph view links (no isolated) | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=links&include_isolated=false` | 200 | 200 | 405 | ✅ |  |
| 30 | graph view content types filter | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=content&types=SCHEMA,PAGE` | 200 | 200 | 435 | ✅ |  |
| 31 | graph view bad mode → 422 | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=nope` | 422 | 422 | 417 | ✅ |  |
| 32 | node details (page) | GET | `/api/v1/sites/emdadmodiran/graph/node-details/page:https://emdadmodiran.com/` | 200 | 200 | 454 | ✅ |  |
| 33 | node details 404 | GET | `/api/v1/sites/emdadmodiran/graph/node-details/nope:x` | 404 | 404 | 430 | ✅ |  |
| 34 | memory get (empty) | GET | `/api/v1/sites/zz-validation-9967eb/memory` | 200 | 200 | 432 | ✅ |  |
| 35 | memory put | PUT | `/api/v1/sites/zz-validation-9967eb/memory` | 200 | 200 | 453 | ✅ |  |
| 36 | memory context | GET | `/api/v1/sites/zz-validation-9967eb/memory/context` | 200 | 200 | 411 | ✅ |  |
| 37 | memory get (real site, read-only) | GET | `/api/v1/sites/emdadmodiran/memory` | 200 | 200 | 423 | ✅ |  |
| 38 | ai routes | GET | `/api/v1/ai/routes` | 200 | 200 | 436 | ✅ |  |
| 39 | ai providers | GET | `/api/v1/ai/providers` | 200 | 200 | 407 | ✅ |  |
| 40 | ai run text | POST | `/api/v1/ai/sites/zz-validation-9967eb/run` | 200 | 200 | 433 | ✅ |  |
| 41 | ai run json + learn | POST | `/api/v1/ai/sites/zz-validation-9967eb/run` | 200 | 200 | 451 | ✅ |  |
| 42 | memory learned pattern | GET | `/api/v1/sites/zz-validation-9967eb/memory` | 200 | 200 | 398 | ✅ |  |
| 43 | ai run unknown kind → 422 | POST | `/api/v1/ai/sites/zz-validation-9967eb/run` | 422 | 422 | 448 | ✅ |  |
| 44 | job enqueue noop | POST | `/api/v1/jobs` | 202 | 202 | 423 | ✅ |  |
| 45 | job run finished | GET | `/api/v1/jobs/job-2ae9160bac81` | 200 | 200 | 450 | ✅ |  |
| 46 | jobs list | GET | `/api/v1/jobs` | 200 | 200 | 432 | ✅ |  |
| 47 | job unknown type → 422 | POST | `/api/v1/jobs` | 422 | 422 | 400 | ✅ |  |
| 48 | job unknown run → 404 | GET | `/api/v1/jobs/none` | 404 | 404 | 419 | ✅ |  |
| 49 | connections status (empty) | GET | `/api/v1/sites/zz-validation-9967eb/connections` | 200 | 200 | 433 | ✅ |  |
| 50 | gsc test without property → not_configured | POST | `/api/v1/sites/zz-validation-9967eb/connections/gsc/test` | 200 | 200 | 429 | ✅ |  |
| 51 | ga4 test bad id → not_configured | POST | `/api/v1/sites/zz-validation-9967eb/connections/ga4/test` | 200 | 200 | 437 | ✅ |  |
| 52 | wordpress test (real site, read-only) | POST | `/api/v1/sites/zz-validation-9967eb/connections/wordpress/test` | 200 | 200 | 7137 | ✅ |  |
| 53 | connections status (3 kinds) | GET | `/api/v1/sites/zz-validation-9967eb/connections` | 200 | 200 | 471 | ✅ |  |
| 54 | gsc properties listing | GET | `/api/v1/connections/gsc/properties` | 200 | 200 | 5085 | ✅ |  |
| 55 | unknown connection kind → 404 | POST | `/api/v1/sites/zz-validation-9967eb/connections/nope/test` | 404 | 404 | 474 | ✅ |  |
| 56 | initialize | POST | `/api/v1/sites/zz-validation-9967eb/initialize` | 200 | 200 | 495 | ✅ |  |
| 57 | initialize idempotent | POST | `/api/v1/sites/zz-validation-9967eb/initialize` | 200 | 200 | 505 | ✅ |  |
| 58 | site brain put (audience/cta/forbidden) | PUT | `/api/v1/sites/zz-validation-9967eb/memory` | 200 | 200 | 489 | ✅ |  |
| 59 | site brain in AI context | GET | `/api/v1/sites/zz-validation-9967eb/memory/context` | 200 | 200 | 437 | ✅ |  |
| 60 | keywords import dry-run | POST | `/api/v1/sites/zz-validation-9967eb/keywords/import` | 200 | 200 | 454 | ✅ |  |
| 61 | keywords import commit | POST | `/api/v1/sites/zz-validation-9967eb/keywords/import` | 200 | 200 | 502 | ✅ |  |
| 62 | keywords list | GET | `/api/v1/sites/zz-validation-9967eb/keywords` | 200 | 200 | 491 | ✅ |  |
| 63 | keyword create | POST | `/api/v1/sites/zz-validation-9967eb/keywords` | 201 | 201 | 424 | ✅ |  |
| 64 | keyword create duplicate → 409 | POST | `/api/v1/sites/zz-validation-9967eb/keywords` | 409 | 409 | 499 | ✅ |  |
| 65 | keyword patch | PATCH | `/api/v1/sites/zz-validation-9967eb/keywords/17` | 200 | 200 | 464 | ✅ |  |
| 66 | keyword detail | GET | `/api/v1/sites/zz-validation-9967eb/keywords/17` | 200 | 200 | 421 | ✅ |  |
| 67 | keywords cluster | POST | `/api/v1/sites/zz-validation-9967eb/keywords/cluster` | 200 | 200 | 425 | ✅ |  |
| 68 | keywords topic-map | GET | `/api/v1/sites/zz-validation-9967eb/keywords/topic-map` | 200 | 200 | 422 | ✅ |  |
| 69 | keywords analyze | POST | `/api/v1/sites/zz-validation-9967eb/keywords/analyze` | 200 | 200 | 418 | ✅ |  |
| 70 | keyword opportunities | GET | `/api/v1/sites/zz-validation-9967eb/keywords/opportunities` | 200 | 200 | 445 | ✅ |  |
| 71 | keywords in graph view | GET | `/api/v1/sites/zz-validation-9967eb/graph/view?mode=seo&types=KEYWORD,TOPIC` | 200 | 200 | 432 | ✅ |  |
| 72 | keyword delete | DELETE | `/api/v1/sites/zz-validation-9967eb/keywords/17` | 200 | 200 | 433 | ✅ |  |
| 73 | keywords meta | GET | `/api/v1/sites/zz-validation-9967eb/keywords/meta` | 200 | 200 | 432 | ✅ |  |
| 74 | content create | POST | `/api/v1/sites/zz-validation-9967eb/content` | 201 | 201 | 524 | ✅ |  |
| 75 | content transition skip → 409 | POST | `/api/v1/sites/zz-validation-9967eb/content/4/transition` | 409 | 409 | 509 | ✅ |  |
| 76 | content brief | POST | `/api/v1/sites/zz-validation-9967eb/content/4/brief` | 200 | 200 | 467 | ✅ |  |
| 77 | content status brief_ready | GET | `/api/v1/sites/zz-validation-9967eb/content/4` | 200 | 200 | 398 | ✅ |  |
| 78 | content transition writing | POST | `/api/v1/sites/zz-validation-9967eb/content/4/transition` | 200 | 200 | 406 | ✅ |  |
| 79 | content board | GET | `/api/v1/sites/zz-validation-9967eb/content/board` | 200 | 200 | 258 | ✅ |  |
| 80 | content calendar | GET | `/api/v1/sites/zz-validation-9967eb/content/calendar?from=2026-09-01&to=2026-09-30` | 200 | 200 | 356 | ✅ |  |
| 81 | content sync graph | POST | `/api/v1/sites/zz-validation-9967eb/content/sync-graph` | 200 | 200 | 487 | ✅ |  |
| 82 | content meta | GET | `/api/v1/sites/zz-validation-9967eb/content/meta` | 200 | 200 | 421 | ✅ |  |
| 83 | content delete | DELETE | `/api/v1/sites/zz-validation-9967eb/content/4` | 200 | 200 | 460 | ✅ |  |
| 84 | ai provider kinds | GET | `/api/v1/ai/provider-kinds` | 200 | 200 | 493 | ✅ |  |
| 85 | ai provider create | POST | `/api/v1/ai/provider-configs` | 201 | 201 | 444 | ✅ |  |
| 86 | ai task routes | GET | `/api/v1/ai/task-routes` | 200 | 200 | 447 | ✅ |  |
| 87 | ai route set | PUT | `/api/v1/ai/task-routes/brief` | 200 | 200 | 454 | ✅ |  |
| 88 | ai route reset | PUT | `/api/v1/ai/task-routes/brief` | 200 | 200 | 511 | ✅ |  |
| 89 | ai provider delete | DELETE | `/api/v1/ai/provider-configs/3` | 200 | 200 | 463 | ✅ |  |
| 90 | legacy dashboard | GET | `/legacy/` | 200 | 200 | 557 | ✅ |  |
| 91 | legacy api | GET | `/legacy/api/sites` | 200 | 200 | 519 | ✅ |  |
| 92 | site delete refused (has data) → 409 | DELETE | `/api/v1/sites/zz-validation-9967eb` | 409 | 409 | 486 | ✅ |  |
| 93 | site delete force | DELETE | `/api/v1/sites/zz-validation-9967eb?force=true` | 200 | 200 | 437 | ✅ |  |
| 94 | site gone → 404 | GET | `/api/v1/sites/zz-validation-9967eb` | 404 | 404 | 435 | ✅ |  |
| 95 | real site untouched | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 446 | ✅ |  |

## Coverage

* health / openapi / docs / request-id · error envelope (404, 409, 422) · sites CRUD (create, get, list, patch, delete-refuse, delete-force, 404 after) ·
  phase 3: connections status/tests (gsc/ga4/wordpress + 404 kind), gsc properties listing, initialize (idempotent), site brain fields + AI context ·
  phase 6: content create/transition guard/brief/board/calendar/graph sync/delete · ai provider config (masked key)/task routes ·
  graph (summary, nodes, node, 404, neighbors, filtered neighbors, subgraph, 422, search, path, orphans, unknown site) ·
  memory (get, put, context, learned pattern) · AI orchestrator (routes, providers, text run, JSON run + learn, 422) · jobs (enqueue, poll, list, 422, 404) · legacy mount.
* All checks ran over real HTTP against uvicorn (not TestClient). Read-only on the real site; writes only on the temporary site.
