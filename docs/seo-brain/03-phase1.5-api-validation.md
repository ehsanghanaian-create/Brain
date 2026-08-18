# Phase 1.5 — live API validation report

Date: 2026-08-18T10:12:42+00:00 · Base: `http://127.0.0.1:8000` · Site: `emdadmodiran` · Temp site: `zz-validation-f38fcb` (created and force-deleted)

**Result: 116/116 checks passed**

| # | Check | Method | Path | Status | Expected | ms | OK | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | root | GET | `/` | 200 | 200 | 453 | ✅ |  |
| 2 | openapi | GET | `/api/openapi.json` | 200 | 200 | 242 | ✅ |  |
| 3 | docs | GET | `/api/docs` | 200 | 200 | 277 | ✅ |  |
| 4 | health | GET | `/api/v1/health` | 200 | 200 | 254 | ✅ |  |
| 5 | request-id header | GET | `/api/v1/health` | 200 | 200 | 313 | ✅ |  |
| 6 | request-id echoed | GET | `/api/v1/health` | 200 | 200 | 241 | ✅ |  |
| 7 | 404 envelope | GET | `/api/v1/sites/nope-nope` | 404 | 404 | 267 | ✅ |  |
| 8 | 422 envelope | POST | `/api/v1/sites` | 422 | 422 | 344 | ✅ |  |
| 9 | sites list | GET | `/api/v1/sites` | 200 | 200 | 279 | ✅ |  |
| 10 | site get | GET | `/api/v1/sites/emdadmodiran` | 200 | 200 | 451 | ✅ |  |
| 11 | site create | POST | `/api/v1/sites` | 201 | 201 | 538 | ✅ |  |
| 12 | site create duplicate → 409 | POST | `/api/v1/sites` | 409 | 409 | 570 | ✅ |  |
| 13 | site patch mode | PATCH | `/api/v1/sites/zz-validation-f38fcb` | 200 | 200 | 523 | ✅ |  |
| 14 | site patch invalid mode → 422 | PATCH | `/api/v1/sites/zz-validation-f38fcb` | 422 | 422 | 532 | ✅ |  |
| 15 | graph summary | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 559 | ✅ |  |
| 16 | graph nodes (types=PAGE,POST) | GET | `/api/v1/sites/emdadmodiran/graph/nodes?types=PAGE,POST&limit=5` | 200 | 200 | 874 | ✅ |  |
| 17 | graph node | GET | `/api/v1/sites/emdadmodiran/graph/node/page:https://emdadmodiran.com/` | 200 | 200 | 776 | ✅ |  |
| 18 | graph node 404 | GET | `/api/v1/sites/emdadmodiran/graph/node/nope:x` | 404 | 404 | 509 | ✅ |  |
| 19 | graph neighbors | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/` | 200 | 200 | 615 | ✅ |  |
| 20 | graph neighbors filtered | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/?relation_types=LINKS_TO&direction=out` | 200 | 200 | 557 | ✅ |  |
| 21 | graph subgraph hops=2 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=2&max_nodes=100` | 200 | 200 | 608 | ✅ |  |
| 22 | graph subgraph bad hops → 422 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=9` | 422 | 422 | 496 | ✅ |  |
| 23 | graph search | GET | `/api/v1/sites/emdadmodiran/graph/search?q=امداد` | 200 | 200 | 588 | ✅ |  |
| 24 | graph path | GET | `/api/v1/sites/emdadmodiran/graph/path?source=site:emdadmodiran&target=page:https://emdadmodiran.com/` | 200 | 200 | 511 | ✅ |  |
| 25 | graph orphans | GET | `/api/v1/sites/emdadmodiran/graph/orphans` | 200 | 200 | 461 | ✅ |  |
| 26 | graph on unknown site → 404 | GET | `/api/v1/sites/nope-nope/graph/summary` | 404 | 404 | 600 | ✅ |  |
| 27 | graph modes | GET | `/api/v1/sites/emdadmodiran/graph/modes` | 200 | 200 | 496 | ✅ |  |
| 28 | graph view seo | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=seo` | 200 | 200 | 605 | ✅ |  |
| 29 | graph view links (no isolated) | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=links&include_isolated=false` | 200 | 200 | 583 | ✅ |  |
| 30 | graph view content types filter | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=content&types=SCHEMA,PAGE` | 200 | 200 | 589 | ✅ |  |
| 31 | graph view bad mode → 422 | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=nope` | 422 | 422 | 547 | ✅ |  |
| 32 | node details (page) | GET | `/api/v1/sites/emdadmodiran/graph/node-details/page:https://emdadmodiran.com/` | 200 | 200 | 516 | ✅ |  |
| 33 | node details 404 | GET | `/api/v1/sites/emdadmodiran/graph/node-details/nope:x` | 404 | 404 | 638 | ✅ |  |
| 34 | memory get (empty) | GET | `/api/v1/sites/zz-validation-f38fcb/memory` | 200 | 200 | 853 | ✅ |  |
| 35 | memory put | PUT | `/api/v1/sites/zz-validation-f38fcb/memory` | 200 | 200 | 507 | ✅ |  |
| 36 | memory context | GET | `/api/v1/sites/zz-validation-f38fcb/memory/context` | 200 | 200 | 483 | ✅ |  |
| 37 | memory get (real site, read-only) | GET | `/api/v1/sites/emdadmodiran/memory` | 200 | 200 | 566 | ✅ |  |
| 38 | ai routes | GET | `/api/v1/ai/routes` | 200 | 200 | 693 | ✅ |  |
| 39 | ai providers | GET | `/api/v1/ai/providers` | 200 | 200 | 475 | ✅ |  |
| 40 | ai run text | POST | `/api/v1/ai/sites/zz-validation-f38fcb/run` | 200 | 200 | 542 | ✅ |  |
| 41 | ai run json + learn | POST | `/api/v1/ai/sites/zz-validation-f38fcb/run` | 200 | 200 | 538 | ✅ |  |
| 42 | memory learned pattern | GET | `/api/v1/sites/zz-validation-f38fcb/memory` | 200 | 200 | 586 | ✅ |  |
| 43 | ai run unknown kind → 422 | POST | `/api/v1/ai/sites/zz-validation-f38fcb/run` | 422 | 422 | 591 | ✅ |  |
| 44 | job enqueue noop | POST | `/api/v1/jobs` | 202 | 202 | 683 | ✅ |  |
| 45 | job run finished | GET | `/api/v1/jobs/job-4cef869f8ba6` | 200 | 200 | 543 | ✅ |  |
| 46 | jobs list | GET | `/api/v1/jobs` | 200 | 200 | 558 | ✅ |  |
| 47 | job unknown type → 422 | POST | `/api/v1/jobs` | 422 | 422 | 517 | ✅ |  |
| 48 | job unknown run → 404 | GET | `/api/v1/jobs/none` | 404 | 404 | 501 | ✅ |  |
| 49 | connections status (empty) | GET | `/api/v1/sites/zz-validation-f38fcb/connections` | 200 | 200 | 820 | ✅ |  |
| 50 | gsc test without property → not_configured | POST | `/api/v1/sites/zz-validation-f38fcb/connections/gsc/test` | 200 | 200 | 562 | ✅ |  |
| 51 | ga4 test bad id → not_configured | POST | `/api/v1/sites/zz-validation-f38fcb/connections/ga4/test` | 200 | 200 | 564 | ✅ |  |
| 52 | wordpress test (real site, read-only) | POST | `/api/v1/sites/zz-validation-f38fcb/connections/wordpress/test` | 200 | 200 | 6333 | ✅ |  |
| 53 | connections status (3 kinds) | GET | `/api/v1/sites/zz-validation-f38fcb/connections` | 200 | 200 | 658 | ✅ |  |
| 54 | gsc properties listing | GET | `/api/v1/connections/gsc/properties` | 200 | 200 | 1988 | ✅ |  |
| 55 | unknown connection kind → 404 | POST | `/api/v1/sites/zz-validation-f38fcb/connections/nope/test` | 404 | 404 | 570 | ✅ |  |
| 56 | initialize | POST | `/api/v1/sites/zz-validation-f38fcb/initialize` | 200 | 200 | 450 | ✅ |  |
| 57 | initialize idempotent | POST | `/api/v1/sites/zz-validation-f38fcb/initialize` | 200 | 200 | 548 | ✅ |  |
| 58 | site brain put (audience/cta/forbidden) | PUT | `/api/v1/sites/zz-validation-f38fcb/memory` | 200 | 200 | 453 | ✅ |  |
| 59 | site brain in AI context | GET | `/api/v1/sites/zz-validation-f38fcb/memory/context` | 200 | 200 | 433 | ✅ |  |
| 60 | keywords import dry-run | POST | `/api/v1/sites/zz-validation-f38fcb/keywords/import` | 200 | 200 | 514 | ✅ |  |
| 61 | keywords import commit | POST | `/api/v1/sites/zz-validation-f38fcb/keywords/import` | 200 | 200 | 431 | ✅ |  |
| 62 | keywords list | GET | `/api/v1/sites/zz-validation-f38fcb/keywords` | 200 | 200 | 540 | ✅ |  |
| 63 | keyword create | POST | `/api/v1/sites/zz-validation-f38fcb/keywords` | 201 | 201 | 465 | ✅ |  |
| 64 | keyword create duplicate → 409 | POST | `/api/v1/sites/zz-validation-f38fcb/keywords` | 409 | 409 | 403 | ✅ |  |
| 65 | keyword patch | PATCH | `/api/v1/sites/zz-validation-f38fcb/keywords/26` | 200 | 200 | 493 | ✅ |  |
| 66 | keyword detail | GET | `/api/v1/sites/zz-validation-f38fcb/keywords/26` | 200 | 200 | 424 | ✅ |  |
| 67 | keywords cluster | POST | `/api/v1/sites/zz-validation-f38fcb/keywords/cluster` | 200 | 200 | 597 | ✅ |  |
| 68 | keywords topic-map | GET | `/api/v1/sites/zz-validation-f38fcb/keywords/topic-map` | 200 | 200 | 633 | ✅ |  |
| 69 | keywords analyze | POST | `/api/v1/sites/zz-validation-f38fcb/keywords/analyze` | 200 | 200 | 564 | ✅ |  |
| 70 | keyword opportunities | GET | `/api/v1/sites/zz-validation-f38fcb/keywords/opportunities` | 200 | 200 | 497 | ✅ |  |
| 71 | keywords in graph view | GET | `/api/v1/sites/zz-validation-f38fcb/graph/view?mode=seo&types=KEYWORD,TOPIC` | 200 | 200 | 540 | ✅ |  |
| 72 | keyword delete | DELETE | `/api/v1/sites/zz-validation-f38fcb/keywords/26` | 200 | 200 | 595 | ✅ |  |
| 73 | keywords meta | GET | `/api/v1/sites/zz-validation-f38fcb/keywords/meta` | 200 | 200 | 554 | ✅ |  |
| 74 | content create | POST | `/api/v1/sites/zz-validation-f38fcb/content` | 201 | 201 | 439 | ✅ |  |
| 75 | content transition skip → 409 | POST | `/api/v1/sites/zz-validation-f38fcb/content/7/transition` | 409 | 409 | 484 | ✅ |  |
| 76 | content brief | POST | `/api/v1/sites/zz-validation-f38fcb/content/7/brief` | 200 | 200 | 549 | ✅ |  |
| 77 | content status brief_ready | GET | `/api/v1/sites/zz-validation-f38fcb/content/7` | 200 | 200 | 596 | ✅ |  |
| 78 | content transition writing | POST | `/api/v1/sites/zz-validation-f38fcb/content/7/transition` | 200 | 200 | 508 | ✅ |  |
| 79 | content board | GET | `/api/v1/sites/zz-validation-f38fcb/content/board` | 200 | 200 | 545 | ✅ |  |
| 80 | content calendar | GET | `/api/v1/sites/zz-validation-f38fcb/content/calendar?from=2026-09-01&to=2026-09-30` | 200 | 200 | 583 | ✅ |  |
| 81 | content sync graph | POST | `/api/v1/sites/zz-validation-f38fcb/content/sync-graph` | 200 | 200 | 535 | ✅ |  |
| 82 | content meta | GET | `/api/v1/sites/zz-validation-f38fcb/content/meta` | 200 | 200 | 581 | ✅ |  |
| 83 | draft create v1 | POST | `/api/v1/sites/zz-validation-f38fcb/content/7/drafts` | 201 | 201 | 496 | ✅ |  |
| 84 | draft create v2 keeps v1 | POST | `/api/v1/sites/zz-validation-f38fcb/content/7/drafts` | 201 | 201 | 593 | ✅ |  |
| 85 | drafts list | GET | `/api/v1/sites/zz-validation-f38fcb/content/7/drafts` | 200 | 200 | 507 | ✅ |  |
| 86 | score | POST | `/api/v1/sites/zz-validation-f38fcb/content/7/score` | 200 | 200 | 427 | ✅ |  |
| 87 | review (rules, advisory ai) | POST | `/api/v1/sites/zz-validation-f38fcb/content/7/review` | 200 | 200 | 490 | ✅ |  |
| 88 | intelligence history | GET | `/api/v1/sites/zz-validation-f38fcb/content/7/intelligence` | 200 | 200 | 453 | ✅ |  |
| 89 | scoring settings get | GET | `/api/v1/sites/zz-validation-f38fcb/content/settings/scoring` | 200 | 200 | 559 | ✅ |  |
| 90 | scoring settings put | PUT | `/api/v1/sites/zz-validation-f38fcb/content/settings/scoring` | 200 | 200 | 465 | ✅ |  |
| 91 | analytics settings | GET | `/api/v1/sites/zz-validation-f38fcb/content/analytics/settings` | 200 | 200 | 496 | ✅ |  |
| 92 | analytics snapshot (no urls) | POST | `/api/v1/sites/zz-validation-f38fcb/content/analytics/snapshot` | 200 | 200 | 396 | ✅ |  |
| 93 | analytics learn (no samples) | POST | `/api/v1/sites/zz-validation-f38fcb/content/analytics/learn` | 200 | 200 | 400 | ✅ |  |
| 94 | analytics overview | GET | `/api/v1/sites/zz-validation-f38fcb/content/analytics/overview` | 200 | 200 | 488 | ✅ |  |
| 95 | insights list | GET | `/api/v1/sites/zz-validation-f38fcb/content/insights` | 200 | 200 | 397 | ✅ |  |
| 96 | content delete | DELETE | `/api/v1/sites/zz-validation-f38fcb/content/7` | 200 | 200 | 455 | ✅ |  |
| 97 | ai provider kinds | GET | `/api/v1/ai/provider-kinds` | 200 | 200 | 468 | ✅ |  |
| 98 | ai provider create | POST | `/api/v1/ai/provider-configs` | 201 | 201 | 410 | ✅ |  |
| 99 | ai task routes | GET | `/api/v1/ai/task-routes` | 200 | 200 | 464 | ✅ |  |
| 100 | ai route set | PUT | `/api/v1/ai/task-routes/brief` | 200 | 200 | 420 | ✅ |  |
| 101 | ai route reset | PUT | `/api/v1/ai/task-routes/brief` | 200 | 200 | 433 | ✅ |  |
| 102 | ai provider delete | DELETE | `/api/v1/ai/provider-configs/7` | 200 | 200 | 520 | ✅ |  |
| 103 | links meta | GET | `/api/v1/sites/emdadmodiran/links/meta` | 200 | 200 | 442 | ✅ |  |
| 104 | links analyze (tmp site, sync) | POST | `/api/v1/sites/zz-validation-f38fcb/links/analyze` | 200 | 200 | 487 | ✅ |  |
| 105 | links summary (real site) | GET | `/api/v1/sites/emdadmodiran/links/summary` | 200 | 200 | 406 | ✅ |  |
| 106 | links suggestions (real site) | GET | `/api/v1/sites/emdadmodiran/links/suggestions?limit=5` | 200 | 200 | 446 | ✅ |  |
| 107 | links pages (real site) | GET | `/api/v1/sites/emdadmodiran/links/pages?limit=5` | 200 | 200 | 450 | ✅ |  |
| 108 | links patterns | GET | `/api/v1/sites/zz-validation-f38fcb/links/patterns` | 200 | 200 | 394 | ✅ |  |
| 109 | links settings | GET | `/api/v1/sites/zz-validation-f38fcb/links/settings` | 200 | 200 | 414 | ✅ |  |
| 110 | links export csv | GET | `/api/v1/sites/zz-validation-f38fcb/links/export.csv` | 200 | 200 | 500 | ✅ |  |
| 111 | legacy dashboard | GET | `/legacy/` | 200 | 200 | 500 | ✅ |  |
| 112 | legacy api | GET | `/legacy/api/sites` | 200 | 200 | 499 | ✅ |  |
| 113 | site delete refused (has data) → 409 | DELETE | `/api/v1/sites/zz-validation-f38fcb` | 409 | 409 | 390 | ✅ |  |
| 114 | site delete force | DELETE | `/api/v1/sites/zz-validation-f38fcb?force=true` | 200 | 200 | 456 | ✅ |  |
| 115 | site gone → 404 | GET | `/api/v1/sites/zz-validation-f38fcb` | 404 | 404 | 518 | ✅ |  |
| 116 | real site untouched | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 479 | ✅ |  |

## Coverage

* health / openapi / docs / request-id · error envelope (404, 409, 422) · sites CRUD (create, get, list, patch, delete-refuse, delete-force, 404 after) ·
  phase 3: connections status/tests (gsc/ga4/wordpress + 404 kind), gsc properties listing, initialize (idempotent), site brain fields + AI context ·
  phase 6: content create/transition guard/brief/board/calendar/graph sync/delete · ai provider config (masked key)/task routes ·
  phase 7: drafts v1/v2, score, review, intelligence history, scoring/analytics settings, snapshot/learn/overview/insights ·
  phase 8: links meta/analyze/summary/suggestions/pages/patterns/settings/export ·
  graph (summary, nodes, node, 404, neighbors, filtered neighbors, subgraph, 422, search, path, orphans, unknown site) ·
  memory (get, put, context, learned pattern) · AI orchestrator (routes, providers, text run, JSON run + learn, 422) · jobs (enqueue, poll, list, 422, 404) · legacy mount.
* All checks ran over real HTTP against uvicorn (not TestClient). Read-only on the real site; writes only on the temporary site.
