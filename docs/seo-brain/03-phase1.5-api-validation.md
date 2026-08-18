# Phase 1.5 — live API validation report

Date: 2026-08-18T12:47:58+00:00 · Base: `http://127.0.0.1:8000` · Site: `emdadmodiran` · Temp site: `zz-validation-4701b5` (created and force-deleted)

**Result: 154/154 checks passed**

| # | Check | Method | Path | Status | Expected | ms | OK | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | root | GET | `/` | 200 | 200 | 445 | ✅ |  |
| 2 | openapi | GET | `/api/openapi.json` | 200 | 200 | 1223 | ✅ |  |
| 3 | docs | GET | `/api/docs` | 200 | 200 | 271 | ✅ |  |
| 4 | health | GET | `/api/v1/health` | 200 | 200 | 226 | ✅ |  |
| 5 | request-id header | GET | `/api/v1/health` | 200 | 200 | 225 | ✅ |  |
| 6 | request-id echoed | GET | `/api/v1/health` | 200 | 200 | 231 | ✅ |  |
| 7 | 404 envelope | GET | `/api/v1/sites/nope-nope` | 404 | 404 | 518 | ✅ |  |
| 8 | 422 envelope | POST | `/api/v1/sites` | 422 | 422 | 510 | ✅ |  |
| 9 | sites list | GET | `/api/v1/sites` | 200 | 200 | 607 | ✅ |  |
| 10 | site get | GET | `/api/v1/sites/emdadmodiran` | 200 | 200 | 512 | ✅ |  |
| 11 | site create | POST | `/api/v1/sites` | 201 | 201 | 565 | ✅ |  |
| 12 | site create duplicate → 409 | POST | `/api/v1/sites` | 409 | 409 | 605 | ✅ |  |
| 13 | site patch mode | PATCH | `/api/v1/sites/zz-validation-4701b5` | 200 | 200 | 527 | ✅ |  |
| 14 | site patch invalid mode → 422 | PATCH | `/api/v1/sites/zz-validation-4701b5` | 422 | 422 | 537 | ✅ |  |
| 15 | graph summary | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 511 | ✅ |  |
| 16 | graph nodes (types=PAGE,POST) | GET | `/api/v1/sites/emdadmodiran/graph/nodes?types=PAGE,POST&limit=5` | 200 | 200 | 529 | ✅ |  |
| 17 | graph node | GET | `/api/v1/sites/emdadmodiran/graph/node/page:https://emdadmodiran.com/` | 200 | 200 | 475 | ✅ |  |
| 18 | graph node 404 | GET | `/api/v1/sites/emdadmodiran/graph/node/nope:x` | 404 | 404 | 801 | ✅ |  |
| 19 | graph neighbors | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/` | 200 | 200 | 697 | ✅ |  |
| 20 | graph neighbors filtered | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/?relation_types=LINKS_TO&direction=out` | 200 | 200 | 560 | ✅ |  |
| 21 | graph subgraph hops=2 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=2&max_nodes=100` | 200 | 200 | 495 | ✅ |  |
| 22 | graph subgraph bad hops → 422 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=9` | 422 | 422 | 466 | ✅ |  |
| 23 | graph search | GET | `/api/v1/sites/emdadmodiran/graph/search?q=امداد` | 200 | 200 | 476 | ✅ |  |
| 24 | graph path | GET | `/api/v1/sites/emdadmodiran/graph/path?source=site:emdadmodiran&target=page:https://emdadmodiran.com/` | 200 | 200 | 415 | ✅ |  |
| 25 | graph orphans | GET | `/api/v1/sites/emdadmodiran/graph/orphans` | 200 | 200 | 471 | ✅ |  |
| 26 | graph on unknown site → 404 | GET | `/api/v1/sites/nope-nope/graph/summary` | 404 | 404 | 455 | ✅ |  |
| 27 | graph modes | GET | `/api/v1/sites/emdadmodiran/graph/modes` | 200 | 200 | 441 | ✅ |  |
| 28 | graph view seo | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=seo` | 200 | 200 | 423 | ✅ |  |
| 29 | graph view links (no isolated) | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=links&include_isolated=false` | 200 | 200 | 449 | ✅ |  |
| 30 | graph view content types filter | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=content&types=SCHEMA,PAGE` | 200 | 200 | 586 | ✅ |  |
| 31 | graph view bad mode → 422 | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=nope` | 422 | 422 | 447 | ✅ |  |
| 32 | node details (page) | GET | `/api/v1/sites/emdadmodiran/graph/node-details/page:https://emdadmodiran.com/` | 200 | 200 | 489 | ✅ |  |
| 33 | node details 404 | GET | `/api/v1/sites/emdadmodiran/graph/node-details/nope:x` | 404 | 404 | 396 | ✅ |  |
| 34 | memory get (empty) | GET | `/api/v1/sites/zz-validation-4701b5/memory` | 200 | 200 | 484 | ✅ |  |
| 35 | memory put | PUT | `/api/v1/sites/zz-validation-4701b5/memory` | 200 | 200 | 480 | ✅ |  |
| 36 | memory context | GET | `/api/v1/sites/zz-validation-4701b5/memory/context` | 200 | 200 | 402 | ✅ |  |
| 37 | memory get (real site, read-only) | GET | `/api/v1/sites/emdadmodiran/memory` | 200 | 200 | 465 | ✅ |  |
| 38 | ai routes | GET | `/api/v1/ai/routes` | 200 | 200 | 415 | ✅ |  |
| 39 | ai providers | GET | `/api/v1/ai/providers` | 200 | 200 | 389 | ✅ |  |
| 40 | ai run text | POST | `/api/v1/ai/sites/zz-validation-4701b5/run` | 200 | 200 | 509 | ✅ |  |
| 41 | ai run json + learn | POST | `/api/v1/ai/sites/zz-validation-4701b5/run` | 200 | 200 | 438 | ✅ |  |
| 42 | memory learned pattern | GET | `/api/v1/sites/zz-validation-4701b5/memory` | 200 | 200 | 434 | ✅ |  |
| 43 | ai run unknown kind → 422 | POST | `/api/v1/ai/sites/zz-validation-4701b5/run` | 422 | 422 | 492 | ✅ |  |
| 44 | job enqueue noop | POST | `/api/v1/jobs` | 202 | 202 | 504 | ✅ |  |
| 45 | job run finished | GET | `/api/v1/jobs/job-4b59870e45af` | 200 | 200 | 404 | ✅ |  |
| 46 | jobs list | GET | `/api/v1/jobs` | 200 | 200 | 379 | ✅ |  |
| 47 | job unknown type → 422 | POST | `/api/v1/jobs` | 422 | 422 | 487 | ✅ |  |
| 48 | job unknown run → 404 | GET | `/api/v1/jobs/none` | 404 | 404 | 460 | ✅ |  |
| 49 | connections status (empty) | GET | `/api/v1/sites/zz-validation-4701b5/connections` | 200 | 200 | 472 | ✅ |  |
| 50 | gsc test without property → not_configured | POST | `/api/v1/sites/zz-validation-4701b5/connections/gsc/test` | 200 | 200 | 452 | ✅ |  |
| 51 | ga4 test bad id → not_configured | POST | `/api/v1/sites/zz-validation-4701b5/connections/ga4/test` | 200 | 200 | 381 | ✅ |  |
| 52 | wordpress test (real site, read-only) | POST | `/api/v1/sites/zz-validation-4701b5/connections/wordpress/test` | 200 | 200 | 22542 | ✅ |  |
| 53 | connections status (3 kinds) | GET | `/api/v1/sites/zz-validation-4701b5/connections` | 200 | 200 | 547 | ✅ |  |
| 54 | gsc properties listing | GET | `/api/v1/connections/gsc/properties` | 200 | 200 | 3799 | ✅ |  |
| 55 | unknown connection kind → 404 | POST | `/api/v1/sites/zz-validation-4701b5/connections/nope/test` | 404 | 404 | 419 | ✅ |  |
| 56 | initialize | POST | `/api/v1/sites/zz-validation-4701b5/initialize` | 200 | 200 | 519 | ✅ |  |
| 57 | initialize idempotent | POST | `/api/v1/sites/zz-validation-4701b5/initialize` | 200 | 200 | 437 | ✅ |  |
| 58 | site brain put (audience/cta/forbidden) | PUT | `/api/v1/sites/zz-validation-4701b5/memory` | 200 | 200 | 408 | ✅ |  |
| 59 | site brain in AI context | GET | `/api/v1/sites/zz-validation-4701b5/memory/context` | 200 | 200 | 477 | ✅ |  |
| 60 | keywords import dry-run | POST | `/api/v1/sites/zz-validation-4701b5/keywords/import` | 200 | 200 | 415 | ✅ |  |
| 61 | keywords import commit | POST | `/api/v1/sites/zz-validation-4701b5/keywords/import` | 200 | 200 | 515 | ✅ |  |
| 62 | keywords list | GET | `/api/v1/sites/zz-validation-4701b5/keywords` | 200 | 200 | 438 | ✅ |  |
| 63 | keyword create | POST | `/api/v1/sites/zz-validation-4701b5/keywords` | 201 | 201 | 435 | ✅ |  |
| 64 | keyword create duplicate → 409 | POST | `/api/v1/sites/zz-validation-4701b5/keywords` | 409 | 409 | 507 | ✅ |  |
| 65 | keyword patch | PATCH | `/api/v1/sites/zz-validation-4701b5/keywords/35` | 200 | 200 | 422 | ✅ |  |
| 66 | keyword detail | GET | `/api/v1/sites/zz-validation-4701b5/keywords/35` | 200 | 200 | 577 | ✅ |  |
| 67 | keywords cluster | POST | `/api/v1/sites/zz-validation-4701b5/keywords/cluster` | 200 | 200 | 472 | ✅ |  |
| 68 | keywords topic-map | GET | `/api/v1/sites/zz-validation-4701b5/keywords/topic-map` | 200 | 200 | 407 | ✅ |  |
| 69 | keywords analyze | POST | `/api/v1/sites/zz-validation-4701b5/keywords/analyze` | 200 | 200 | 477 | ✅ |  |
| 70 | keyword opportunities | GET | `/api/v1/sites/zz-validation-4701b5/keywords/opportunities` | 200 | 200 | 470 | ✅ |  |
| 71 | keywords in graph view | GET | `/api/v1/sites/zz-validation-4701b5/graph/view?mode=seo&types=KEYWORD,TOPIC` | 200 | 200 | 385 | ✅ |  |
| 72 | keyword delete | DELETE | `/api/v1/sites/zz-validation-4701b5/keywords/35` | 200 | 200 | 544 | ✅ |  |
| 73 | keywords meta | GET | `/api/v1/sites/zz-validation-4701b5/keywords/meta` | 200 | 200 | 465 | ✅ |  |
| 74 | content create | POST | `/api/v1/sites/zz-validation-4701b5/content` | 201 | 201 | 824 | ✅ |  |
| 75 | content transition skip → 409 | POST | `/api/v1/sites/zz-validation-4701b5/content/12/transition` | 409 | 409 | 499 | ✅ |  |
| 76 | content brief | POST | `/api/v1/sites/zz-validation-4701b5/content/12/brief` | 200 | 200 | 532 | ✅ |  |
| 77 | content status brief_ready | GET | `/api/v1/sites/zz-validation-4701b5/content/12` | 200 | 200 | 433 | ✅ |  |
| 78 | content transition writing | POST | `/api/v1/sites/zz-validation-4701b5/content/12/transition` | 200 | 200 | 496 | ✅ |  |
| 79 | content board | GET | `/api/v1/sites/zz-validation-4701b5/content/board` | 200 | 200 | 453 | ✅ |  |
| 80 | content calendar | GET | `/api/v1/sites/zz-validation-4701b5/content/calendar?from=2026-09-01&to=2026-09-30` | 200 | 200 | 554 | ✅ |  |
| 81 | content sync graph | POST | `/api/v1/sites/zz-validation-4701b5/content/sync-graph` | 200 | 200 | 531 | ✅ |  |
| 82 | content meta | GET | `/api/v1/sites/zz-validation-4701b5/content/meta` | 200 | 200 | 550 | ✅ |  |
| 83 | draft create v1 | POST | `/api/v1/sites/zz-validation-4701b5/content/12/drafts` | 201 | 201 | 517 | ✅ |  |
| 84 | draft create v2 keeps v1 | POST | `/api/v1/sites/zz-validation-4701b5/content/12/drafts` | 201 | 201 | 459 | ✅ |  |
| 85 | drafts list | GET | `/api/v1/sites/zz-validation-4701b5/content/12/drafts` | 200 | 200 | 558 | ✅ |  |
| 86 | score | POST | `/api/v1/sites/zz-validation-4701b5/content/12/score` | 200 | 200 | 440 | ✅ |  |
| 87 | review (rules, advisory ai) | POST | `/api/v1/sites/zz-validation-4701b5/content/12/review` | 200 | 200 | 584 | ✅ |  |
| 88 | intelligence history | GET | `/api/v1/sites/zz-validation-4701b5/content/12/intelligence` | 200 | 200 | 617 | ✅ |  |
| 89 | scoring settings get | GET | `/api/v1/sites/zz-validation-4701b5/content/settings/scoring` | 200 | 200 | 559 | ✅ |  |
| 90 | scoring settings put | PUT | `/api/v1/sites/zz-validation-4701b5/content/settings/scoring` | 200 | 200 | 525 | ✅ |  |
| 91 | analytics settings | GET | `/api/v1/sites/zz-validation-4701b5/content/analytics/settings` | 200 | 200 | 525 | ✅ |  |
| 92 | analytics snapshot (no urls) | POST | `/api/v1/sites/zz-validation-4701b5/content/analytics/snapshot` | 200 | 200 | 469 | ✅ |  |
| 93 | analytics learn (no samples) | POST | `/api/v1/sites/zz-validation-4701b5/content/analytics/learn` | 200 | 200 | 466 | ✅ |  |
| 94 | analytics overview | GET | `/api/v1/sites/zz-validation-4701b5/content/analytics/overview` | 200 | 200 | 493 | ✅ |  |
| 95 | insights list | GET | `/api/v1/sites/zz-validation-4701b5/content/insights` | 200 | 200 | 470 | ✅ |  |
| 96 | content delete | DELETE | `/api/v1/sites/zz-validation-4701b5/content/12` | 200 | 200 | 543 | ✅ |  |
| 97 | ai provider kinds | GET | `/api/v1/ai/provider-kinds` | 200 | 200 | 444 | ✅ |  |
| 98 | ai provider create | POST | `/api/v1/ai/provider-configs` | 201 | 201 | 505 | ✅ |  |
| 99 | ai task routes | GET | `/api/v1/ai/task-routes` | 200 | 200 | 541 | ✅ |  |
| 100 | ai route set | PUT | `/api/v1/ai/task-routes/brief` | 200 | 200 | 468 | ✅ |  |
| 101 | ai route reset | PUT | `/api/v1/ai/task-routes/brief` | 200 | 200 | 491 | ✅ |  |
| 102 | ai provider delete | DELETE | `/api/v1/ai/provider-configs/10` | 200 | 200 | 425 | ✅ |  |
| 103 | links meta | GET | `/api/v1/sites/emdadmodiran/links/meta` | 200 | 200 | 391 | ✅ |  |
| 104 | links analyze (tmp site, sync) | POST | `/api/v1/sites/zz-validation-4701b5/links/analyze` | 200 | 200 | 589 | ✅ |  |
| 105 | links summary (real site) | GET | `/api/v1/sites/emdadmodiran/links/summary` | 200 | 200 | 406 | ✅ |  |
| 106 | links suggestions (real site) | GET | `/api/v1/sites/emdadmodiran/links/suggestions?limit=5` | 200 | 200 | 518 | ✅ |  |
| 107 | links pages (real site) | GET | `/api/v1/sites/emdadmodiran/links/pages?limit=5` | 200 | 200 | 400 | ✅ |  |
| 108 | links patterns | GET | `/api/v1/sites/zz-validation-4701b5/links/patterns` | 200 | 200 | 406 | ✅ |  |
| 109 | links settings | GET | `/api/v1/sites/zz-validation-4701b5/links/settings` | 200 | 200 | 688 | ✅ |  |
| 110 | links export csv | GET | `/api/v1/sites/zz-validation-4701b5/links/export.csv` | 200 | 200 | 540 | ✅ |  |
| 111 | ai task kinds (17) | GET | `/api/v1/ai/task-kinds` | 200 | 200 | 486 | ✅ |  |
| 112 | ai models catalog | GET | `/api/v1/ai/models` | 200 | 200 | 501 | ✅ |  |
| 113 | ai health | GET | `/api/v1/ai/health` | 200 | 200 | 565 | ✅ |  |
| 114 | ai budget default 20 + thresholds | GET | `/api/v1/ai/budget?site_id=zz-validation-4701b5` | 200 | 200 | 498 | ✅ |  |
| 115 | ai budget set (human) | PUT | `/api/v1/ai/budget?site_id=zz-validation-4701b5` | 200 | 200 | 487 | ✅ |  |
| 116 | ai budget set invalid → 422 | PUT | `/api/v1/ai/budget?site_id=zz-validation-4701b5` | 422 | 422 | 524 | ✅ |  |
| 117 | ai usage | GET | `/api/v1/ai/usage?site_id=zz-validation-4701b5&group_by=model` | 200 | 200 | 557 | ✅ |  |
| 118 | ai routing preview (echo w/o provider) | GET | `/api/v1/ai/routing/preview?task_kind=article_section&site_id=zz-validation-4701b5` | 200 | 200 | 509 | ✅ |  |
| 119 | ai routing preview unknown kind → 422 | GET | `/api/v1/ai/routing/preview?task_kind=nope` | 422 | 422 | 503 | ✅ |  |
| 120 | ai route policy+fallbacks (additive) | PUT | `/api/v1/ai/task-routes/outline` | 200 | 200 | 558 | ✅ |  |
| 121 | ai prompts seeded (11, all with memory_pack) | GET | `/api/v1/ai/prompts` | 200 | 200 | 495 | ✅ |  |
| 122 | ai prompt get + performance | GET | `/api/v1/ai/prompts/5` | 200 | 200 | 560 | ✅ |  |
| 123 | ai prompt preview (memory injected) | POST | `/api/v1/ai/prompts/versions/5/preview` | 200 | 200 | 531 | ✅ |  |
| 124 | ai prompt new version w/o memory_pack → 422 | POST | `/api/v1/ai/prompts/5/versions` | 422 | 422 | 604 | ✅ |  |
| 125 | ai prompt new version (inactive) | POST | `/api/v1/ai/prompts/5/versions` | 201 | 201 | 687 | ✅ |  |
| 126 | ai prompt version approve (human) | PATCH | `/api/v1/ai/prompts/versions/14` | 200 | 200 | 646 | ✅ |  |
| 127 | ai feedback tags (6) | GET | `/api/v1/ai/feedback-tags` | 200 | 200 | 516 | ✅ |  |
| 128 | gen meta (7 agents, autopilot reserved) | GET | `/api/v1/sites/zz-validation-4701b5/generation/meta` | 200 | 200 | 697 | ✅ |  |
| 129 | gen memory preview | GET | `/api/v1/sites/zz-validation-4701b5/generation/memory-preview` | 200 | 200 | 486 | ✅ |  |
| 130 | content create for generation | POST | `/api/v1/sites/zz-validation-4701b5/content` | 201 | 201 | 619 | ✅ |  |
| 131 | content brief for generation | POST | `/api/v1/sites/zz-validation-4701b5/content/13/brief` | 200 | 200 | 497 | ✅ |  |
| 132 | gen estimate | POST | `/api/v1/sites/zz-validation-4701b5/content/13/generate/estimate` | 200 | 200 | 608 | ✅ |  |
| 133 | gen start invalid mode (autopilot) → 422 | POST | `/api/v1/sites/zz-validation-4701b5/content/13/generate` | 422 | 422 | 525 | ✅ |  |
| 134 | gen start (manual, 202) | POST | `/api/v1/sites/zz-validation-4701b5/content/13/generate` | 202 | 202 | 509 | ✅ |  |
| 135 | gen run detail (provenance) | GET | `/api/v1/sites/zz-validation-4701b5/generation/runs/gen-0d910e764a` | 200 | 200 | 442 | ✅ |  |
| 136 | gen run stream (SSE) | GET | `/api/v1/sites/zz-validation-4701b5/generation/runs/gen-0d910e764a/stream` | 200 | 200 | 535 | ✅ |  |
| 137 | gen runs list | GET | `/api/v1/sites/zz-validation-4701b5/generation/runs` | 200 | 200 | 468 | ✅ |  |
| 138 | gen accept (human) → draft | POST | `/api/v1/sites/zz-validation-4701b5/generation/runs/gen-0d910e764a/accept` | 200 | 200 | 518 | ✅ |  |
| 139 | gen accept idempotent | POST | `/api/v1/sites/zz-validation-4701b5/generation/runs/gen-0d910e764a/accept` | 200 | 200 | 493 | ✅ |  |
| 140 | gen run 404 | GET | `/api/v1/sites/zz-validation-4701b5/generation/runs/gen-nope` | 404 | 404 | 453 | ✅ |  |
| 141 | draft feedback (rating+tags) | POST | `/api/v1/sites/zz-validation-4701b5/content/13/feedback` | 201 | 201 | 524 | ✅ |  |
| 142 | draft feedback unknown tag filtered | POST | `/api/v1/sites/zz-validation-4701b5/content/13/feedback` | 201 | 201 | 469 | ✅ |  |
| 143 | draft feedback rating out of range → 422 | POST | `/api/v1/sites/zz-validation-4701b5/content/13/feedback` | 422 | 422 | 531 | ✅ |  |
| 144 | draft feedback list | GET | `/api/v1/sites/zz-validation-4701b5/content/13/feedback` | 200 | 200 | 522 | ✅ |  |
| 145 | agent single run (research, echo proposal) | POST | `/api/v1/sites/zz-validation-4701b5/content/13/agents/research/run` | 200 | 200 | 561 | ✅ |  |
| 146 | agent single run (fact_check needs section) → 404 | POST | `/api/v1/sites/zz-validation-4701b5/content/13/agents/fact_check/run` | 404 | 404 | 461 | ✅ |  |
| 147 | ai insights list | GET | `/api/v1/ai/insights?site_id=zz-validation-4701b5` | 200 | 200 | 445 | ✅ |  |
| 148 | ai insights learn (min_n=5 → advisory) | POST | `/api/v1/ai/insights/learn?site_id=zz-validation-4701b5` | 200 | 200 | 549 | ✅ |  |
| 149 | legacy dashboard | GET | `/legacy/` | 200 | 200 | 515 | ✅ |  |
| 150 | legacy api | GET | `/legacy/api/sites` | 200 | 200 | 545 | ✅ |  |
| 151 | site delete refused (has data) → 409 | DELETE | `/api/v1/sites/zz-validation-4701b5` | 409 | 409 | 521 | ✅ |  |
| 152 | site delete force | DELETE | `/api/v1/sites/zz-validation-4701b5?force=true` | 200 | 200 | 510 | ✅ |  |
| 153 | site gone → 404 | GET | `/api/v1/sites/zz-validation-4701b5` | 404 | 404 | 1268 | ✅ |  |
| 154 | real site untouched | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 481 | ✅ |  |

## Coverage

* health / openapi / docs / request-id · error envelope (404, 409, 422) · sites CRUD (create, get, list, patch, delete-refuse, delete-force, 404 after) ·
  phase 3: connections status/tests (gsc/ga4/wordpress + 404 kind), gsc properties listing, initialize (idempotent), site brain fields + AI context ·
  phase 6: content create/transition guard/brief/board/calendar/graph sync/delete · ai provider config (masked key)/task routes ·
  phase 7: drafts v1/v2, score, review, intelligence history, scoring/analytics settings, snapshot/learn/overview/insights ·
  phase 8: links meta/analyze/summary/suggestions/pages/patterns/settings/export ·
  phase 9: ai task-kinds/models/health/budget(get/put/422)/usage/routing preview/route policy+fallbacks/prompts (seeded, get, preview, version 422/create/approve)/feedback tags ·
  phase 9: generation meta/memory-preview/estimate/start (202, autopilot 422)/run detail+provenance/SSE/list/accept (+idempotent)/404/feedback (+422)/single agent/insights ·
  graph (summary, nodes, node, 404, neighbors, filtered neighbors, subgraph, 422, search, path, orphans, unknown site) ·
  memory (get, put, context, learned pattern) · AI orchestrator (routes, providers, text run, JSON run + learn, 422) · jobs (enqueue, poll, list, 422, 404) · legacy mount.
* All checks ran over real HTTP against uvicorn (not TestClient). Read-only on the real site; writes only on the temporary site.
