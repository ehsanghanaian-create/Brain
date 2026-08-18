# Phase 1.5 — live API validation report

Date: 2026-08-18T09:16:30+00:00 · Base: `http://127.0.0.1:8000` · Site: `emdadmodiran` · Temp site: `zz-validation-da1149` (created and force-deleted)

**Result: 108/108 checks passed**

| # | Check | Method | Path | Status | Expected | ms | OK | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | root | GET | `/` | 200 | 200 | 378 | ✅ |  |
| 2 | openapi | GET | `/api/openapi.json` | 200 | 200 | 208 | ✅ |  |
| 3 | docs | GET | `/api/docs` | 200 | 200 | 222 | ✅ |  |
| 4 | health | GET | `/api/v1/health` | 200 | 200 | 211 | ✅ |  |
| 5 | request-id header | GET | `/api/v1/health` | 200 | 200 | 210 | ✅ |  |
| 6 | request-id echoed | GET | `/api/v1/health` | 200 | 200 | 215 | ✅ |  |
| 7 | 404 envelope | GET | `/api/v1/sites/nope-nope` | 404 | 404 | 219 | ✅ |  |
| 8 | 422 envelope | POST | `/api/v1/sites` | 422 | 422 | 222 | ✅ |  |
| 9 | sites list | GET | `/api/v1/sites` | 200 | 200 | 208 | ✅ |  |
| 10 | site get | GET | `/api/v1/sites/emdadmodiran` | 200 | 200 | 205 | ✅ |  |
| 11 | site create | POST | `/api/v1/sites` | 201 | 201 | 241 | ✅ |  |
| 12 | site create duplicate → 409 | POST | `/api/v1/sites` | 409 | 409 | 256 | ✅ |  |
| 13 | site patch mode | PATCH | `/api/v1/sites/zz-validation-da1149` | 200 | 200 | 486 | ✅ |  |
| 14 | site patch invalid mode → 422 | PATCH | `/api/v1/sites/zz-validation-da1149` | 422 | 422 | 391 | ✅ |  |
| 15 | graph summary | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 465 | ✅ |  |
| 16 | graph nodes (types=PAGE,POST) | GET | `/api/v1/sites/emdadmodiran/graph/nodes?types=PAGE,POST&limit=5` | 200 | 200 | 404 | ✅ |  |
| 17 | graph node | GET | `/api/v1/sites/emdadmodiran/graph/node/page:https://emdadmodiran.com/` | 200 | 200 | 399 | ✅ |  |
| 18 | graph node 404 | GET | `/api/v1/sites/emdadmodiran/graph/node/nope:x` | 404 | 404 | 472 | ✅ |  |
| 19 | graph neighbors | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/` | 200 | 200 | 417 | ✅ |  |
| 20 | graph neighbors filtered | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/?relation_types=LINKS_TO&direction=out` | 200 | 200 | 405 | ✅ |  |
| 21 | graph subgraph hops=2 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=2&max_nodes=100` | 200 | 200 | 497 | ✅ |  |
| 22 | graph subgraph bad hops → 422 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=9` | 422 | 422 | 445 | ✅ |  |
| 23 | graph search | GET | `/api/v1/sites/emdadmodiran/graph/search?q=امداد` | 200 | 200 | 500 | ✅ |  |
| 24 | graph path | GET | `/api/v1/sites/emdadmodiran/graph/path?source=site:emdadmodiran&target=page:https://emdadmodiran.com/` | 200 | 200 | 395 | ✅ |  |
| 25 | graph orphans | GET | `/api/v1/sites/emdadmodiran/graph/orphans` | 200 | 200 | 426 | ✅ |  |
| 26 | graph on unknown site → 404 | GET | `/api/v1/sites/nope-nope/graph/summary` | 404 | 404 | 451 | ✅ |  |
| 27 | graph modes | GET | `/api/v1/sites/emdadmodiran/graph/modes` | 200 | 200 | 409 | ✅ |  |
| 28 | graph view seo | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=seo` | 200 | 200 | 529 | ✅ |  |
| 29 | graph view links (no isolated) | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=links&include_isolated=false` | 200 | 200 | 409 | ✅ |  |
| 30 | graph view content types filter | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=content&types=SCHEMA,PAGE` | 200 | 200 | 458 | ✅ |  |
| 31 | graph view bad mode → 422 | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=nope` | 422 | 422 | 448 | ✅ |  |
| 32 | node details (page) | GET | `/api/v1/sites/emdadmodiran/graph/node-details/page:https://emdadmodiran.com/` | 200 | 200 | 401 | ✅ |  |
| 33 | node details 404 | GET | `/api/v1/sites/emdadmodiran/graph/node-details/nope:x` | 404 | 404 | 553 | ✅ |  |
| 34 | memory get (empty) | GET | `/api/v1/sites/zz-validation-da1149/memory` | 200 | 200 | 465 | ✅ |  |
| 35 | memory put | PUT | `/api/v1/sites/zz-validation-da1149/memory` | 200 | 200 | 432 | ✅ |  |
| 36 | memory context | GET | `/api/v1/sites/zz-validation-da1149/memory/context` | 200 | 200 | 521 | ✅ |  |
| 37 | memory get (real site, read-only) | GET | `/api/v1/sites/emdadmodiran/memory` | 200 | 200 | 374 | ✅ |  |
| 38 | ai routes | GET | `/api/v1/ai/routes` | 200 | 200 | 428 | ✅ |  |
| 39 | ai providers | GET | `/api/v1/ai/providers` | 200 | 200 | 474 | ✅ |  |
| 40 | ai run text | POST | `/api/v1/ai/sites/zz-validation-da1149/run` | 200 | 200 | 401 | ✅ |  |
| 41 | ai run json + learn | POST | `/api/v1/ai/sites/zz-validation-da1149/run` | 200 | 200 | 470 | ✅ |  |
| 42 | memory learned pattern | GET | `/api/v1/sites/zz-validation-da1149/memory` | 200 | 200 | 393 | ✅ |  |
| 43 | ai run unknown kind → 422 | POST | `/api/v1/ai/sites/zz-validation-da1149/run` | 422 | 422 | 396 | ✅ |  |
| 44 | job enqueue noop | POST | `/api/v1/jobs` | 202 | 202 | 481 | ✅ |  |
| 45 | job run finished | GET | `/api/v1/jobs/job-003ec03d1fb4` | 200 | 200 | 426 | ✅ |  |
| 46 | jobs list | GET | `/api/v1/jobs` | 200 | 200 | 424 | ✅ |  |
| 47 | job unknown type → 422 | POST | `/api/v1/jobs` | 422 | 422 | 369 | ✅ |  |
| 48 | job unknown run → 404 | GET | `/api/v1/jobs/none` | 404 | 404 | 495 | ✅ |  |
| 49 | connections status (empty) | GET | `/api/v1/sites/zz-validation-da1149/connections` | 200 | 200 | 416 | ✅ |  |
| 50 | gsc test without property → not_configured | POST | `/api/v1/sites/zz-validation-da1149/connections/gsc/test` | 200 | 200 | 396 | ✅ |  |
| 51 | ga4 test bad id → not_configured | POST | `/api/v1/sites/zz-validation-da1149/connections/ga4/test` | 200 | 200 | 507 | ✅ |  |
| 52 | wordpress test (real site, read-only) | POST | `/api/v1/sites/zz-validation-da1149/connections/wordpress/test` | 200 | 200 | 5898 | ✅ |  |
| 53 | connections status (3 kinds) | GET | `/api/v1/sites/zz-validation-da1149/connections` | 200 | 200 | 482 | ✅ |  |
| 54 | gsc properties listing | GET | `/api/v1/connections/gsc/properties` | 200 | 200 | 4810 | ✅ |  |
| 55 | unknown connection kind → 404 | POST | `/api/v1/sites/zz-validation-da1149/connections/nope/test` | 404 | 404 | 525 | ✅ |  |
| 56 | initialize | POST | `/api/v1/sites/zz-validation-da1149/initialize` | 200 | 200 | 515 | ✅ |  |
| 57 | initialize idempotent | POST | `/api/v1/sites/zz-validation-da1149/initialize` | 200 | 200 | 486 | ✅ |  |
| 58 | site brain put (audience/cta/forbidden) | PUT | `/api/v1/sites/zz-validation-da1149/memory` | 200 | 200 | 454 | ✅ |  |
| 59 | site brain in AI context | GET | `/api/v1/sites/zz-validation-da1149/memory/context` | 200 | 200 | 438 | ✅ |  |
| 60 | keywords import dry-run | POST | `/api/v1/sites/zz-validation-da1149/keywords/import` | 200 | 200 | 448 | ✅ |  |
| 61 | keywords import commit | POST | `/api/v1/sites/zz-validation-da1149/keywords/import` | 200 | 200 | 463 | ✅ |  |
| 62 | keywords list | GET | `/api/v1/sites/zz-validation-da1149/keywords` | 200 | 200 | 635 | ✅ |  |
| 63 | keyword create | POST | `/api/v1/sites/zz-validation-da1149/keywords` | 201 | 201 | 516 | ✅ |  |
| 64 | keyword create duplicate → 409 | POST | `/api/v1/sites/zz-validation-da1149/keywords` | 409 | 409 | 494 | ✅ |  |
| 65 | keyword patch | PATCH | `/api/v1/sites/zz-validation-da1149/keywords/20` | 200 | 200 | 472 | ✅ |  |
| 66 | keyword detail | GET | `/api/v1/sites/zz-validation-da1149/keywords/20` | 200 | 200 | 460 | ✅ |  |
| 67 | keywords cluster | POST | `/api/v1/sites/zz-validation-da1149/keywords/cluster` | 200 | 200 | 506 | ✅ |  |
| 68 | keywords topic-map | GET | `/api/v1/sites/zz-validation-da1149/keywords/topic-map` | 200 | 200 | 442 | ✅ |  |
| 69 | keywords analyze | POST | `/api/v1/sites/zz-validation-da1149/keywords/analyze` | 200 | 200 | 547 | ✅ |  |
| 70 | keyword opportunities | GET | `/api/v1/sites/zz-validation-da1149/keywords/opportunities` | 200 | 200 | 399 | ✅ |  |
| 71 | keywords in graph view | GET | `/api/v1/sites/zz-validation-da1149/graph/view?mode=seo&types=KEYWORD,TOPIC` | 200 | 200 | 487 | ✅ |  |
| 72 | keyword delete | DELETE | `/api/v1/sites/zz-validation-da1149/keywords/20` | 200 | 200 | 437 | ✅ |  |
| 73 | keywords meta | GET | `/api/v1/sites/zz-validation-da1149/keywords/meta` | 200 | 200 | 429 | ✅ |  |
| 74 | content create | POST | `/api/v1/sites/zz-validation-da1149/content` | 201 | 201 | 548 | ✅ |  |
| 75 | content transition skip → 409 | POST | `/api/v1/sites/zz-validation-da1149/content/5/transition` | 409 | 409 | 417 | ✅ |  |
| 76 | content brief | POST | `/api/v1/sites/zz-validation-da1149/content/5/brief` | 200 | 200 | 492 | ✅ |  |
| 77 | content status brief_ready | GET | `/api/v1/sites/zz-validation-da1149/content/5` | 200 | 200 | 441 | ✅ |  |
| 78 | content transition writing | POST | `/api/v1/sites/zz-validation-da1149/content/5/transition` | 200 | 200 | 507 | ✅ |  |
| 79 | content board | GET | `/api/v1/sites/zz-validation-da1149/content/board` | 200 | 200 | 491 | ✅ |  |
| 80 | content calendar | GET | `/api/v1/sites/zz-validation-da1149/content/calendar?from=2026-09-01&to=2026-09-30` | 200 | 200 | 472 | ✅ |  |
| 81 | content sync graph | POST | `/api/v1/sites/zz-validation-da1149/content/sync-graph` | 200 | 200 | 487 | ✅ |  |
| 82 | content meta | GET | `/api/v1/sites/zz-validation-da1149/content/meta` | 200 | 200 | 471 | ✅ |  |
| 83 | draft create v1 | POST | `/api/v1/sites/zz-validation-da1149/content/5/drafts` | 201 | 201 | 518 | ✅ |  |
| 84 | draft create v2 keeps v1 | POST | `/api/v1/sites/zz-validation-da1149/content/5/drafts` | 201 | 201 | 477 | ✅ |  |
| 85 | drafts list | GET | `/api/v1/sites/zz-validation-da1149/content/5/drafts` | 200 | 200 | 496 | ✅ |  |
| 86 | score | POST | `/api/v1/sites/zz-validation-da1149/content/5/score` | 200 | 200 | 529 | ✅ |  |
| 87 | review (rules, advisory ai) | POST | `/api/v1/sites/zz-validation-da1149/content/5/review` | 200 | 200 | 498 | ✅ |  |
| 88 | intelligence history | GET | `/api/v1/sites/zz-validation-da1149/content/5/intelligence` | 200 | 200 | 524 | ✅ |  |
| 89 | scoring settings get | GET | `/api/v1/sites/zz-validation-da1149/content/settings/scoring` | 200 | 200 | 434 | ✅ |  |
| 90 | scoring settings put | PUT | `/api/v1/sites/zz-validation-da1149/content/settings/scoring` | 200 | 200 | 459 | ✅ |  |
| 91 | analytics settings | GET | `/api/v1/sites/zz-validation-da1149/content/analytics/settings` | 200 | 200 | 481 | ✅ |  |
| 92 | analytics snapshot (no urls) | POST | `/api/v1/sites/zz-validation-da1149/content/analytics/snapshot` | 200 | 200 | 487 | ✅ |  |
| 93 | analytics learn (no samples) | POST | `/api/v1/sites/zz-validation-da1149/content/analytics/learn` | 200 | 200 | 481 | ✅ |  |
| 94 | analytics overview | GET | `/api/v1/sites/zz-validation-da1149/content/analytics/overview` | 200 | 200 | 492 | ✅ |  |
| 95 | insights list | GET | `/api/v1/sites/zz-validation-da1149/content/insights` | 200 | 200 | 435 | ✅ |  |
| 96 | content delete | DELETE | `/api/v1/sites/zz-validation-da1149/content/5` | 200 | 200 | 481 | ✅ |  |
| 97 | ai provider kinds | GET | `/api/v1/ai/provider-kinds` | 200 | 200 | 485 | ✅ |  |
| 98 | ai provider create | POST | `/api/v1/ai/provider-configs` | 201 | 201 | 511 | ✅ |  |
| 99 | ai task routes | GET | `/api/v1/ai/task-routes` | 200 | 200 | 417 | ✅ |  |
| 100 | ai route set | PUT | `/api/v1/ai/task-routes/brief` | 200 | 200 | 491 | ✅ |  |
| 101 | ai route reset | PUT | `/api/v1/ai/task-routes/brief` | 200 | 200 | 432 | ✅ |  |
| 102 | ai provider delete | DELETE | `/api/v1/ai/provider-configs/5` | 200 | 200 | 488 | ✅ |  |
| 103 | legacy dashboard | GET | `/legacy/` | 200 | 200 | 501 | ✅ |  |
| 104 | legacy api | GET | `/legacy/api/sites` | 200 | 200 | 420 | ✅ |  |
| 105 | site delete refused (has data) → 409 | DELETE | `/api/v1/sites/zz-validation-da1149` | 409 | 409 | 531 | ✅ |  |
| 106 | site delete force | DELETE | `/api/v1/sites/zz-validation-da1149?force=true` | 200 | 200 | 393 | ✅ |  |
| 107 | site gone → 404 | GET | `/api/v1/sites/zz-validation-da1149` | 404 | 404 | 430 | ✅ |  |
| 108 | real site untouched | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 481 | ✅ |  |

## Coverage

* health / openapi / docs / request-id · error envelope (404, 409, 422) · sites CRUD (create, get, list, patch, delete-refuse, delete-force, 404 after) ·
  phase 3: connections status/tests (gsc/ga4/wordpress + 404 kind), gsc properties listing, initialize (idempotent), site brain fields + AI context ·
  phase 6: content create/transition guard/brief/board/calendar/graph sync/delete · ai provider config (masked key)/task routes ·
  phase 7: drafts v1/v2, score, review, intelligence history, scoring/analytics settings, snapshot/learn/overview/insights ·
  graph (summary, nodes, node, 404, neighbors, filtered neighbors, subgraph, 422, search, path, orphans, unknown site) ·
  memory (get, put, context, learned pattern) · AI orchestrator (routes, providers, text run, JSON run + learn, 422) · jobs (enqueue, poll, list, 422, 404) · legacy mount.
* All checks ran over real HTTP against uvicorn (not TestClient). Read-only on the real site; writes only on the temporary site.
