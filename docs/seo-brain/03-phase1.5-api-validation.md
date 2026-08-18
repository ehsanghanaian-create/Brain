# Phase 1.5 — live API validation report

Date: 2026-08-18T15:29:15+00:00 · Base: `http://127.0.0.1:8000` · Site: `emdadmodiran` · Temp site: `zz-validation-76bc88` (created and force-deleted)

**Result: 188/188 checks passed**

| # | Check | Method | Path | Status | Expected | ms | OK | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | root | GET | `/` | 200 | 200 | 356 | ✅ |  |
| 2 | openapi | GET | `/api/openapi.json` | 200 | 200 | 226 | ✅ |  |
| 3 | docs | GET | `/api/docs` | 200 | 200 | 218 | ✅ |  |
| 4 | health | GET | `/api/v1/health` | 200 | 200 | 278 | ✅ |  |
| 5 | request-id header | GET | `/api/v1/health` | 200 | 200 | 234 | ✅ |  |
| 6 | request-id echoed | GET | `/api/v1/health` | 200 | 200 | 214 | ✅ |  |
| 7 | 404 envelope | GET | `/api/v1/sites/nope-nope` | 404 | 404 | 208 | ✅ |  |
| 8 | 422 envelope | POST | `/api/v1/sites` | 422 | 422 | 223 | ✅ |  |
| 9 | sites list | GET | `/api/v1/sites` | 200 | 200 | 229 | ✅ |  |
| 10 | site get | GET | `/api/v1/sites/emdadmodiran` | 200 | 200 | 269 | ✅ |  |
| 11 | site create | POST | `/api/v1/sites` | 201 | 201 | 358 | ✅ |  |
| 12 | site create duplicate → 409 | POST | `/api/v1/sites` | 409 | 409 | 496 | ✅ |  |
| 13 | site patch mode | PATCH | `/api/v1/sites/zz-validation-76bc88` | 200 | 200 | 569 | ✅ |  |
| 14 | site patch invalid mode → 422 | PATCH | `/api/v1/sites/zz-validation-76bc88` | 422 | 422 | 641 | ✅ |  |
| 15 | graph summary | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 569 | ✅ |  |
| 16 | graph nodes (types=PAGE,POST) | GET | `/api/v1/sites/emdadmodiran/graph/nodes?types=PAGE,POST&limit=5` | 200 | 200 | 453 | ✅ |  |
| 17 | graph node | GET | `/api/v1/sites/emdadmodiran/graph/node/page:https://emdadmodiran.com/` | 200 | 200 | 672 | ✅ |  |
| 18 | graph node 404 | GET | `/api/v1/sites/emdadmodiran/graph/node/nope:x` | 404 | 404 | 508 | ✅ |  |
| 19 | graph neighbors | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/` | 200 | 200 | 707 | ✅ |  |
| 20 | graph neighbors filtered | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/?relation_types=LINKS_TO&direction=out` | 200 | 200 | 572 | ✅ |  |
| 21 | graph subgraph hops=2 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=2&max_nodes=100` | 200 | 200 | 614 | ✅ |  |
| 22 | graph subgraph bad hops → 422 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=9` | 422 | 422 | 501 | ✅ |  |
| 23 | graph search | GET | `/api/v1/sites/emdadmodiran/graph/search?q=امداد` | 200 | 200 | 564 | ✅ |  |
| 24 | graph path | GET | `/api/v1/sites/emdadmodiran/graph/path?source=site:emdadmodiran&target=page:https://emdadmodiran.com/` | 200 | 200 | 464 | ✅ |  |
| 25 | graph orphans | GET | `/api/v1/sites/emdadmodiran/graph/orphans` | 200 | 200 | 505 | ✅ |  |
| 26 | graph on unknown site → 404 | GET | `/api/v1/sites/nope-nope/graph/summary` | 404 | 404 | 597 | ✅ |  |
| 27 | graph modes | GET | `/api/v1/sites/emdadmodiran/graph/modes` | 200 | 200 | 481 | ✅ |  |
| 28 | graph view seo | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=seo` | 200 | 200 | 514 | ✅ |  |
| 29 | graph view links (no isolated) | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=links&include_isolated=false` | 200 | 200 | 601 | ✅ |  |
| 30 | graph view content types filter | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=content&types=SCHEMA,PAGE` | 200 | 200 | 522 | ✅ |  |
| 31 | graph view bad mode → 422 | GET | `/api/v1/sites/emdadmodiran/graph/view?mode=nope` | 422 | 422 | 533 | ✅ |  |
| 32 | node details (page) | GET | `/api/v1/sites/emdadmodiran/graph/node-details/page:https://emdadmodiran.com/` | 200 | 200 | 639 | ✅ |  |
| 33 | node details 404 | GET | `/api/v1/sites/emdadmodiran/graph/node-details/nope:x` | 404 | 404 | 605 | ✅ |  |
| 34 | memory get (empty) | GET | `/api/v1/sites/zz-validation-76bc88/memory` | 200 | 200 | 538 | ✅ |  |
| 35 | memory put | PUT | `/api/v1/sites/zz-validation-76bc88/memory` | 200 | 200 | 459 | ✅ |  |
| 36 | memory context | GET | `/api/v1/sites/zz-validation-76bc88/memory/context` | 200 | 200 | 475 | ✅ |  |
| 37 | memory get (real site, read-only) | GET | `/api/v1/sites/emdadmodiran/memory` | 200 | 200 | 528 | ✅ |  |
| 38 | ai routes | GET | `/api/v1/ai/routes` | 200 | 200 | 635 | ✅ |  |
| 39 | ai providers | GET | `/api/v1/ai/providers` | 200 | 200 | 473 | ✅ |  |
| 40 | ai run text | POST | `/api/v1/ai/sites/zz-validation-76bc88/run` | 200 | 200 | 693 | ✅ |  |
| 41 | ai run json + learn | POST | `/api/v1/ai/sites/zz-validation-76bc88/run` | 200 | 200 | 537 | ✅ |  |
| 42 | memory learned pattern | GET | `/api/v1/sites/zz-validation-76bc88/memory` | 200 | 200 | 504 | ✅ |  |
| 43 | ai run unknown kind → 422 | POST | `/api/v1/ai/sites/zz-validation-76bc88/run` | 422 | 422 | 484 | ✅ |  |
| 44 | job enqueue noop | POST | `/api/v1/jobs` | 202 | 202 | 493 | ✅ |  |
| 45 | job run finished | GET | `/api/v1/jobs/job-e5fac262852b` | 200 | 200 | 511 | ✅ |  |
| 46 | jobs list | GET | `/api/v1/jobs` | 200 | 200 | 585 | ✅ |  |
| 47 | job unknown type → 422 | POST | `/api/v1/jobs` | 422 | 422 | 503 | ✅ |  |
| 48 | job unknown run → 404 | GET | `/api/v1/jobs/none` | 404 | 404 | 542 | ✅ |  |
| 49 | connections status (empty) | GET | `/api/v1/sites/zz-validation-76bc88/connections` | 200 | 200 | 527 | ✅ |  |
| 50 | gsc test without property → not_configured | POST | `/api/v1/sites/zz-validation-76bc88/connections/gsc/test` | 200 | 200 | 670 | ✅ |  |
| 51 | ga4 test bad id → not_configured | POST | `/api/v1/sites/zz-validation-76bc88/connections/ga4/test` | 200 | 200 | 470 | ✅ |  |
| 52 | wordpress test (real site, read-only) | POST | `/api/v1/sites/zz-validation-76bc88/connections/wordpress/test` | 200 | 200 | 22394 | ✅ |  |
| 53 | connections status (3 kinds) | GET | `/api/v1/sites/zz-validation-76bc88/connections` | 200 | 200 | 595 | ✅ |  |
| 54 | gsc properties listing | GET | `/api/v1/connections/gsc/properties` | 200 | 200 | 2490 | ✅ |  |
| 55 | unknown connection kind → 404 | POST | `/api/v1/sites/zz-validation-76bc88/connections/nope/test` | 404 | 404 | 575 | ✅ |  |
| 56 | initialize | POST | `/api/v1/sites/zz-validation-76bc88/initialize` | 200 | 200 | 578 | ✅ |  |
| 57 | initialize idempotent | POST | `/api/v1/sites/zz-validation-76bc88/initialize` | 200 | 200 | 456 | ✅ |  |
| 58 | site brain put (audience/cta/forbidden) | PUT | `/api/v1/sites/zz-validation-76bc88/memory` | 200 | 200 | 455 | ✅ |  |
| 59 | site brain in AI context | GET | `/api/v1/sites/zz-validation-76bc88/memory/context` | 200 | 200 | 588 | ✅ |  |
| 60 | keywords import dry-run | POST | `/api/v1/sites/zz-validation-76bc88/keywords/import` | 200 | 200 | 464 | ✅ |  |
| 61 | keywords import commit | POST | `/api/v1/sites/zz-validation-76bc88/keywords/import` | 200 | 200 | 548 | ✅ |  |
| 62 | keywords list | GET | `/api/v1/sites/zz-validation-76bc88/keywords` | 200 | 200 | 560 | ✅ |  |
| 63 | keyword create | POST | `/api/v1/sites/zz-validation-76bc88/keywords` | 201 | 201 | 818 | ✅ |  |
| 64 | keyword create duplicate → 409 | POST | `/api/v1/sites/zz-validation-76bc88/keywords` | 409 | 409 | 590 | ✅ |  |
| 65 | keyword patch | PATCH | `/api/v1/sites/zz-validation-76bc88/keywords/41` | 200 | 200 | 622 | ✅ |  |
| 66 | keyword detail | GET | `/api/v1/sites/zz-validation-76bc88/keywords/41` | 200 | 200 | 489 | ✅ |  |
| 67 | keywords cluster | POST | `/api/v1/sites/zz-validation-76bc88/keywords/cluster` | 200 | 200 | 528 | ✅ |  |
| 68 | keywords topic-map | GET | `/api/v1/sites/zz-validation-76bc88/keywords/topic-map` | 200 | 200 | 430 | ✅ |  |
| 69 | keywords analyze | POST | `/api/v1/sites/zz-validation-76bc88/keywords/analyze` | 200 | 200 | 517 | ✅ |  |
| 70 | keyword opportunities | GET | `/api/v1/sites/zz-validation-76bc88/keywords/opportunities` | 200 | 200 | 473 | ✅ |  |
| 71 | keywords in graph view | GET | `/api/v1/sites/zz-validation-76bc88/graph/view?mode=seo&types=KEYWORD,TOPIC` | 200 | 200 | 518 | ✅ |  |
| 72 | keyword delete | DELETE | `/api/v1/sites/zz-validation-76bc88/keywords/41` | 200 | 200 | 543 | ✅ |  |
| 73 | keywords meta | GET | `/api/v1/sites/zz-validation-76bc88/keywords/meta` | 200 | 200 | 433 | ✅ |  |
| 74 | content create | POST | `/api/v1/sites/zz-validation-76bc88/content` | 201 | 201 | 890 | ✅ |  |
| 75 | content transition skip → 409 | POST | `/api/v1/sites/zz-validation-76bc88/content/19/transition` | 409 | 409 | 546 | ✅ |  |
| 76 | content brief | POST | `/api/v1/sites/zz-validation-76bc88/content/19/brief` | 200 | 200 | 590 | ✅ |  |
| 77 | content status brief_ready | GET | `/api/v1/sites/zz-validation-76bc88/content/19` | 200 | 200 | 507 | ✅ |  |
| 78 | content transition writing | POST | `/api/v1/sites/zz-validation-76bc88/content/19/transition` | 200 | 200 | 570 | ✅ |  |
| 79 | content board | GET | `/api/v1/sites/zz-validation-76bc88/content/board` | 200 | 200 | 482 | ✅ |  |
| 80 | content calendar | GET | `/api/v1/sites/zz-validation-76bc88/content/calendar?from=2026-09-01&to=2026-09-30` | 200 | 200 | 553 | ✅ |  |
| 81 | content sync graph | POST | `/api/v1/sites/zz-validation-76bc88/content/sync-graph` | 200 | 200 | 852 | ✅ |  |
| 82 | content meta | GET | `/api/v1/sites/zz-validation-76bc88/content/meta` | 200 | 200 | 464 | ✅ |  |
| 83 | draft create v1 | POST | `/api/v1/sites/zz-validation-76bc88/content/19/drafts` | 201 | 201 | 567 | ✅ |  |
| 84 | draft create v2 keeps v1 | POST | `/api/v1/sites/zz-validation-76bc88/content/19/drafts` | 201 | 201 | 573 | ✅ |  |
| 85 | drafts list | GET | `/api/v1/sites/zz-validation-76bc88/content/19/drafts` | 200 | 200 | 572 | ✅ |  |
| 86 | score | POST | `/api/v1/sites/zz-validation-76bc88/content/19/score` | 200 | 200 | 604 | ✅ |  |
| 87 | review (rules, advisory ai) | POST | `/api/v1/sites/zz-validation-76bc88/content/19/review` | 200 | 200 | 574 | ✅ |  |
| 88 | intelligence history | GET | `/api/v1/sites/zz-validation-76bc88/content/19/intelligence` | 200 | 200 | 761 | ✅ |  |
| 89 | scoring settings get | GET | `/api/v1/sites/zz-validation-76bc88/content/settings/scoring` | 200 | 200 | 532 | ✅ |  |
| 90 | scoring settings put | PUT | `/api/v1/sites/zz-validation-76bc88/content/settings/scoring` | 200 | 200 | 526 | ✅ |  |
| 91 | analytics settings | GET | `/api/v1/sites/zz-validation-76bc88/content/analytics/settings` | 200 | 200 | 501 | ✅ |  |
| 92 | analytics snapshot (no urls) | POST | `/api/v1/sites/zz-validation-76bc88/content/analytics/snapshot` | 200 | 200 | 564 | ✅ |  |
| 93 | analytics learn (no samples) | POST | `/api/v1/sites/zz-validation-76bc88/content/analytics/learn` | 200 | 200 | 733 | ✅ |  |
| 94 | analytics overview | GET | `/api/v1/sites/zz-validation-76bc88/content/analytics/overview` | 200 | 200 | 515 | ✅ |  |
| 95 | insights list | GET | `/api/v1/sites/zz-validation-76bc88/content/insights` | 200 | 200 | 481 | ✅ |  |
| 96 | content delete | DELETE | `/api/v1/sites/zz-validation-76bc88/content/19` | 200 | 200 | 619 | ✅ |  |
| 97 | ai provider kinds | GET | `/api/v1/ai/provider-kinds` | 200 | 200 | 544 | ✅ |  |
| 98 | ai provider create | POST | `/api/v1/ai/provider-configs` | 201 | 201 | 530 | ✅ |  |
| 99 | ai task routes | GET | `/api/v1/ai/task-routes` | 200 | 200 | 493 | ✅ |  |
| 100 | ai route set | PUT | `/api/v1/ai/task-routes/brief` | 200 | 200 | 555 | ✅ |  |
| 101 | ai route reset | PUT | `/api/v1/ai/task-routes/brief` | 200 | 200 | 490 | ✅ |  |
| 102 | ai provider delete | DELETE | `/api/v1/ai/provider-configs/12` | 200 | 200 | 570 | ✅ |  |
| 103 | links meta | GET | `/api/v1/sites/emdadmodiran/links/meta` | 200 | 200 | 406 | ✅ |  |
| 104 | links analyze (tmp site, sync) | POST | `/api/v1/sites/zz-validation-76bc88/links/analyze` | 200 | 200 | 1330 | ✅ |  |
| 105 | links summary (real site) | GET | `/api/v1/sites/emdadmodiran/links/summary` | 200 | 200 | 636 | ✅ |  |
| 106 | links suggestions (real site) | GET | `/api/v1/sites/emdadmodiran/links/suggestions?limit=5` | 200 | 200 | 753 | ✅ |  |
| 107 | links pages (real site) | GET | `/api/v1/sites/emdadmodiran/links/pages?limit=5` | 200 | 200 | 595 | ✅ |  |
| 108 | links patterns | GET | `/api/v1/sites/zz-validation-76bc88/links/patterns` | 200 | 200 | 473 | ✅ |  |
| 109 | links settings | GET | `/api/v1/sites/zz-validation-76bc88/links/settings` | 200 | 200 | 486 | ✅ |  |
| 110 | links export csv | GET | `/api/v1/sites/zz-validation-76bc88/links/export.csv` | 200 | 200 | 526 | ✅ |  |
| 111 | ai task kinds (17) | GET | `/api/v1/ai/task-kinds` | 200 | 200 | 456 | ✅ |  |
| 112 | ai models catalog | GET | `/api/v1/ai/models` | 200 | 200 | 538 | ✅ |  |
| 113 | ai health | GET | `/api/v1/ai/health` | 200 | 200 | 467 | ✅ |  |
| 114 | ai budget default 20 + thresholds | GET | `/api/v1/ai/budget?site_id=zz-validation-76bc88` | 200 | 200 | 667 | ✅ |  |
| 115 | ai budget set (human) | PUT | `/api/v1/ai/budget?site_id=zz-validation-76bc88` | 200 | 200 | 576 | ✅ |  |
| 116 | ai budget set invalid → 422 | PUT | `/api/v1/ai/budget?site_id=zz-validation-76bc88` | 422 | 422 | 488 | ✅ |  |
| 117 | ai usage | GET | `/api/v1/ai/usage?site_id=zz-validation-76bc88&group_by=model` | 200 | 200 | 562 | ✅ |  |
| 118 | ai routing preview (echo w/o provider) | GET | `/api/v1/ai/routing/preview?task_kind=article_section&site_id=zz-validation-76bc88` | 200 | 200 | 484 | ✅ |  |
| 119 | ai routing preview unknown kind → 422 | GET | `/api/v1/ai/routing/preview?task_kind=nope` | 422 | 422 | 516 | ✅ |  |
| 120 | ai route policy+fallbacks (additive) | PUT | `/api/v1/ai/task-routes/outline` | 200 | 200 | 491 | ✅ |  |
| 121 | ai prompts seeded (11, all with memory_pack) | GET | `/api/v1/ai/prompts` | 200 | 200 | 714 | ✅ |  |
| 122 | ai prompt get + performance | GET | `/api/v1/ai/prompts/5` | 200 | 200 | 527 | ✅ |  |
| 123 | ai prompt preview (memory injected) | POST | `/api/v1/ai/prompts/versions/5/preview` | 200 | 200 | 549 | ✅ |  |
| 124 | ai prompt new version w/o memory_pack → 422 | POST | `/api/v1/ai/prompts/5/versions` | 422 | 422 | 512 | ✅ |  |
| 125 | ai prompt new version (inactive) | POST | `/api/v1/ai/prompts/5/versions` | 201 | 201 | 612 | ✅ |  |
| 126 | ai prompt version approve (human) | PATCH | `/api/v1/ai/prompts/versions/16` | 200 | 200 | 490 | ✅ |  |
| 127 | ai feedback tags (6) | GET | `/api/v1/ai/feedback-tags` | 200 | 200 | 389 | ✅ |  |
| 128 | gen meta (7 agents, autopilot reserved) | GET | `/api/v1/sites/zz-validation-76bc88/generation/meta` | 200 | 200 | 570 | ✅ |  |
| 129 | gen memory preview | GET | `/api/v1/sites/zz-validation-76bc88/generation/memory-preview` | 200 | 200 | 592 | ✅ |  |
| 130 | content create for generation | POST | `/api/v1/sites/zz-validation-76bc88/content` | 201 | 201 | 531 | ✅ |  |
| 131 | content brief for generation | POST | `/api/v1/sites/zz-validation-76bc88/content/20/brief` | 200 | 200 | 534 | ✅ |  |
| 132 | gen estimate | POST | `/api/v1/sites/zz-validation-76bc88/content/20/generate/estimate` | 200 | 200 | 521 | ✅ |  |
| 133 | gen start invalid mode (autopilot) → 422 | POST | `/api/v1/sites/zz-validation-76bc88/content/20/generate` | 422 | 422 | 463 | ✅ |  |
| 134 | gen start (manual, 202) | POST | `/api/v1/sites/zz-validation-76bc88/content/20/generate` | 202 | 202 | 690 | ✅ |  |
| 135 | gen run detail (provenance) | GET | `/api/v1/sites/zz-validation-76bc88/generation/runs/gen-7ef9872799` | 200 | 200 | 512 | ✅ |  |
| 136 | gen run stream (SSE) | GET | `/api/v1/sites/zz-validation-76bc88/generation/runs/gen-7ef9872799/stream` | 200 | 200 | 569 | ✅ |  |
| 137 | gen runs list | GET | `/api/v1/sites/zz-validation-76bc88/generation/runs` | 200 | 200 | 651 | ✅ |  |
| 138 | gen accept (human) → draft | POST | `/api/v1/sites/zz-validation-76bc88/generation/runs/gen-7ef9872799/accept` | 200 | 200 | 693 | ✅ |  |
| 139 | gen accept idempotent | POST | `/api/v1/sites/zz-validation-76bc88/generation/runs/gen-7ef9872799/accept` | 200 | 200 | 727 | ✅ |  |
| 140 | gen run 404 | GET | `/api/v1/sites/zz-validation-76bc88/generation/runs/gen-nope` | 404 | 404 | 477 | ✅ |  |
| 141 | draft feedback (rating+tags) | POST | `/api/v1/sites/zz-validation-76bc88/content/20/feedback` | 201 | 201 | 519 | ✅ |  |
| 142 | draft feedback unknown tag filtered | POST | `/api/v1/sites/zz-validation-76bc88/content/20/feedback` | 201 | 201 | 475 | ✅ |  |
| 143 | draft feedback rating out of range → 422 | POST | `/api/v1/sites/zz-validation-76bc88/content/20/feedback` | 422 | 422 | 583 | ✅ |  |
| 144 | draft feedback list | GET | `/api/v1/sites/zz-validation-76bc88/content/20/feedback` | 200 | 200 | 460 | ✅ |  |
| 145 | agent single run (research, echo proposal) | POST | `/api/v1/sites/zz-validation-76bc88/content/20/agents/research/run` | 200 | 200 | 508 | ✅ |  |
| 146 | agent single run (fact_check needs section) → 404 | POST | `/api/v1/sites/zz-validation-76bc88/content/20/agents/fact_check/run` | 404 | 404 | 533 | ✅ |  |
| 147 | ai insights list | GET | `/api/v1/ai/insights?site_id=zz-validation-76bc88` | 200 | 200 | 474 | ✅ |  |
| 148 | ai insights learn (min_n=5 → advisory) | POST | `/api/v1/ai/insights/learn?site_id=zz-validation-76bc88` | 200 | 200 | 528 | ✅ |  |
| 149 | planner meta (7 statuses, 3 views, publishing disabled) | GET | `/api/v1/sites/zz-validation-76bc88/content-plans/meta` | 200 | 200 | 496 | ✅ |  |
| 150 | planner categories sync (brain; WP not configured on tmp) | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/categories/sync?min_keywords=1` | 200 | 200 | 719 | ✅ |  |
| 151 | planner category create (manual) | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/categories` | 201 | 201 | 570 | ✅ |  |
| 152 | planner categories tree | GET | `/api/v1/sites/zz-validation-76bc88/content-plans/categories?tree=true` | 200 | 200 | 552 | ✅ |  |
| 153 | planner plan create (+analyze, recommendation, advanced fields) | POST | `/api/v1/sites/zz-validation-76bc88/content-plans` | 201 | 201 | 530 | ✅ |  |
| 154 | planner plan PATCH (inline edit) | PATCH | `/api/v1/sites/zz-validation-76bc88/content-plans/7` | 200 | 200 | 656 | ✅ |  |
| 155 | planner transition researching (planner-only) | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/7/transition` | 200 | 200 | 524 | ✅ |  |
| 156 | planner transition writing without item → 409 | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/7/transition` | 409 | 409 | 543 | ✅ |  |
| 157 | planner brief → content item + brief_ready | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/7/brief` | 200 | 200 | 667 | ✅ |  |
| 158 | planner plan detail (mirrored) | GET | `/api/v1/sites/zz-validation-76bc88/content-plans/7` | 200 | 200 | 475 | ✅ |  |
| 159 | planner generation job prepared (no run) | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/7/generation-jobs` | 201 | 201 | 491 | ✅ |  |
| 160 | planner publishing metadata only | PUT | `/api/v1/sites/zz-validation-76bc88/content-plans/7/publishing-metadata` | 200 | 200 | 566 | ✅ |  |
| 161 | planner link prep | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/7/link-prep` | 200 | 200 | 543 | ✅ |  |
| 162 | planner recommendations stored | GET | `/api/v1/sites/zz-validation-76bc88/content-plans/7/recommendations` | 200 | 200 | 522 | ✅ |  |
| 163 | planner list + counts | GET | `/api/v1/sites/zz-validation-76bc88/content-plans?limit=50` | 200 | 200 | 505 | ✅ |  |
| 164 | planner board (7 columns) | GET | `/api/v1/sites/zz-validation-76bc88/content-plans/board` | 200 | 200 | 597 | ✅ |  |
| 165 | planner calendar | GET | `/api/v1/sites/zz-validation-76bc88/content-plans/calendar?from=2026-01-01&to=2026-12-31` | 200 | 200 | 490 | ✅ |  |
| 166 | planner import dry-run (Persian headers) | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/import` | 200 | 200 | 506 | ✅ |  |
| 167 | planner import apply | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/import` | 200 | 200 | 934 | ✅ |  |
| 168 | planner import upsert | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/import` | 200 | 200 | 713 | ✅ |  |
| 169 | planner export csv | GET | `/api/v1/sites/zz-validation-76bc88/content-plans/export.csv` | 200 | 200 | 526 | ✅ |  |
| 170 | planner export xlsx | GET | `/api/v1/sites/zz-validation-76bc88/content-plans/export.xlsx` | 200 | 200 | 507 | ✅ |  |
| 171 | planner import template | GET | `/api/v1/sites/zz-validation-76bc88/content-plans/import/template.csv` | 200 | 200 | 478 | ✅ |  |
| 172 | planner google-sheet source create | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/sources` | 201 | 201 | 514 | ✅ |  |
| 173 | planner keyword mapping overview | GET | `/api/v1/sites/zz-validation-76bc88/content-plans/keyword-mapping` | 200 | 200 | 476 | ✅ |  |
| 174 | planner keyword mapping suggest (persisted) | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/keyword-mapping/suggest` | 200 | 200 | 577 | ✅ |  |
| 175 | planner suggestions inbox | GET | `/api/v1/sites/zz-validation-76bc88/content-plans/suggestions` | 200 | 200 | 508 | ✅ |  |
| 176 | planner analyze all (sync) | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/analyze` | 200 | 200 | 612 | ✅ |  |
| 177 | planner graph mode | GET | `/api/v1/sites/zz-validation-76bc88/graph/view?mode=planner` | 200 | 200 | 502 | ✅ |  |
| 178 | planner graph focus | GET | `/api/v1/sites/zz-validation-76bc88/content-plans/graph?plan_id=7` | 200 | 200 | 454 | ✅ |  |
| 179 | planner node details | GET | `/api/v1/sites/zz-validation-76bc88/graph/node-details/plan:7` | 200 | 200 | 551 | ✅ |  |
| 180 | planner insights (advisory) | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/insights/learn` | 200 | 200 | 429 | ✅ |  |
| 181 | planner backfill | POST | `/api/v1/sites/zz-validation-76bc88/content-plans/backfill` | 200 | 200 | 643 | ✅ |  |
| 182 | planner plan 404 | GET | `/api/v1/sites/zz-validation-76bc88/content-plans/999999` | 404 | 404 | 424 | ✅ |  |
| 183 | legacy dashboard | GET | `/legacy/` | 200 | 200 | 517 | ✅ |  |
| 184 | legacy api | GET | `/legacy/api/sites` | 200 | 200 | 510 | ✅ |  |
| 185 | site delete refused (has data) → 409 | DELETE | `/api/v1/sites/zz-validation-76bc88` | 409 | 409 | 450 | ✅ |  |
| 186 | site delete force | DELETE | `/api/v1/sites/zz-validation-76bc88?force=true` | 200 | 200 | 720 | ✅ |  |
| 187 | site gone → 404 | GET | `/api/v1/sites/zz-validation-76bc88` | 404 | 404 | 464 | ✅ |  |
| 188 | real site untouched | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 614 | ✅ |  |

## Coverage

* health / openapi / docs / request-id · error envelope (404, 409, 422) · sites CRUD (create, get, list, patch, delete-refuse, delete-force, 404 after) ·
  phase 3: connections status/tests (gsc/ga4/wordpress + 404 kind), gsc properties listing, initialize (idempotent), site brain fields + AI context ·
  phase 6: content create/transition guard/brief/board/calendar/graph sync/delete · ai provider config (masked key)/task routes ·
  phase 7: drafts v1/v2, score, review, intelligence history, scoring/analytics settings, snapshot/learn/overview/insights ·
  phase 8: links meta/analyze/summary/suggestions/pages/patterns/settings/export ·
  phase 9: ai task-kinds/models/health/budget(get/put/422)/usage/routing preview/route policy+fallbacks/prompts (seeded, get, preview, version 422/create/approve)/feedback tags ·
  phase 9: generation meta/memory-preview/estimate/start (202, autopilot 422)/run detail+provenance/SSE/list/accept (+idempotent)/404/feedback (+422)/single agent/insights ·
  phase 8.5: planner meta/categories (sync brain, manual, tree)/plan create+PATCH+transitions (researching, 409 gate)/brief→item/generation job prepared/publishing metadata/link prep/recommendations/list/board/calendar/import (dry-run, apply, upsert)/export csv+xlsx/template/sheet source/keyword mapping+suggest/suggestions/analyze/graph mode+focus+details/insights/backfill/404 ·
  graph (summary, nodes, node, 404, neighbors, filtered neighbors, subgraph, 422, search, path, orphans, unknown site) ·
  memory (get, put, context, learned pattern) · AI orchestrator (routes, providers, text run, JSON run + learn, 422) · jobs (enqueue, poll, list, 422, 404) · legacy mount.
* All checks ran over real HTTP against uvicorn (not TestClient). Read-only on the real site; writes only on the temporary site.
