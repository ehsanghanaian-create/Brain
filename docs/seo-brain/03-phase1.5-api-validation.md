# Phase 1.5 — live API validation report

Date: 2026-08-17T15:16:42+00:00 · Base: `http://127.0.0.1:8000` · Site: `emdadmodiran` · Temp site: `zz-validation-e45414` (created and force-deleted)

**Result: 58/58 checks passed**

| # | Check | Method | Path | Status | Expected | ms | OK | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | root | GET | `/` | 200 | 200 | 437 | ✅ |  |
| 2 | openapi | GET | `/api/openapi.json` | 200 | 200 | 408 | ✅ |  |
| 3 | docs | GET | `/api/docs` | 200 | 200 | 349 | ✅ |  |
| 4 | health | GET | `/api/v1/health` | 200 | 200 | 250 | ✅ |  |
| 5 | request-id header | GET | `/api/v1/health` | 200 | 200 | 239 | ✅ |  |
| 6 | request-id echoed | GET | `/api/v1/health` | 200 | 200 | 261 | ✅ |  |
| 7 | 404 envelope | GET | `/api/v1/sites/nope-nope` | 404 | 404 | 279 | ✅ |  |
| 8 | 422 envelope | POST | `/api/v1/sites` | 422 | 422 | 231 | ✅ |  |
| 9 | sites list | GET | `/api/v1/sites` | 200 | 200 | 480 | ✅ |  |
| 10 | site get | GET | `/api/v1/sites/emdadmodiran` | 200 | 200 | 491 | ✅ |  |
| 11 | site create | POST | `/api/v1/sites` | 201 | 201 | 655 | ✅ |  |
| 12 | site create duplicate → 409 | POST | `/api/v1/sites` | 409 | 409 | 281 | ✅ |  |
| 13 | site patch mode | PATCH | `/api/v1/sites/zz-validation-e45414` | 200 | 200 | 354 | ✅ |  |
| 14 | site patch invalid mode → 422 | PATCH | `/api/v1/sites/zz-validation-e45414` | 422 | 422 | 271 | ✅ |  |
| 15 | graph summary | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 302 | ✅ |  |
| 16 | graph nodes (types=PAGE,POST) | GET | `/api/v1/sites/emdadmodiran/graph/nodes?types=PAGE,POST&limit=5` | 200 | 200 | 346 | ✅ |  |
| 17 | graph node | GET | `/api/v1/sites/emdadmodiran/graph/node/page:https://emdadmodiran.com/` | 200 | 200 | 248 | ✅ |  |
| 18 | graph node 404 | GET | `/api/v1/sites/emdadmodiran/graph/node/nope:x` | 404 | 404 | 272 | ✅ |  |
| 19 | graph neighbors | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/` | 200 | 200 | 249 | ✅ |  |
| 20 | graph neighbors filtered | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/?relation_types=LINKS_TO&direction=out` | 200 | 200 | 248 | ✅ |  |
| 21 | graph subgraph hops=2 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=2&max_nodes=100` | 200 | 200 | 303 | ✅ |  |
| 22 | graph subgraph bad hops → 422 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=9` | 422 | 422 | 266 | ✅ |  |
| 23 | graph search | GET | `/api/v1/sites/emdadmodiran/graph/search?q=امداد` | 200 | 200 | 292 | ✅ |  |
| 24 | graph path | GET | `/api/v1/sites/emdadmodiran/graph/path?source=site:emdadmodiran&target=page:https://emdadmodiran.com/` | 200 | 200 | 243 | ✅ |  |
| 25 | graph orphans | GET | `/api/v1/sites/emdadmodiran/graph/orphans` | 200 | 200 | 264 | ✅ |  |
| 26 | graph on unknown site → 404 | GET | `/api/v1/sites/nope-nope/graph/summary` | 404 | 404 | 244 | ✅ |  |
| 27 | memory get (empty) | GET | `/api/v1/sites/zz-validation-e45414/memory` | 200 | 200 | 234 | ✅ |  |
| 28 | memory put | PUT | `/api/v1/sites/zz-validation-e45414/memory` | 200 | 200 | 253 | ✅ |  |
| 29 | memory context | GET | `/api/v1/sites/zz-validation-e45414/memory/context` | 200 | 200 | 246 | ✅ |  |
| 30 | memory get (real site, read-only) | GET | `/api/v1/sites/emdadmodiran/memory` | 200 | 200 | 251 | ✅ |  |
| 31 | ai routes | GET | `/api/v1/ai/routes` | 200 | 200 | 247 | ✅ |  |
| 32 | ai providers | GET | `/api/v1/ai/providers` | 200 | 200 | 242 | ✅ |  |
| 33 | ai run text | POST | `/api/v1/ai/sites/zz-validation-e45414/run` | 200 | 200 | 261 | ✅ |  |
| 34 | ai run json + learn | POST | `/api/v1/ai/sites/zz-validation-e45414/run` | 200 | 200 | 340 | ✅ |  |
| 35 | memory learned pattern | GET | `/api/v1/sites/zz-validation-e45414/memory` | 200 | 200 | 258 | ✅ |  |
| 36 | ai run unknown kind → 422 | POST | `/api/v1/ai/sites/zz-validation-e45414/run` | 422 | 422 | 229 | ✅ |  |
| 37 | job enqueue noop | POST | `/api/v1/jobs` | 202 | 202 | 255 | ✅ |  |
| 38 | job run finished | GET | `/api/v1/jobs/job-53fa2c236b29` | 200 | 200 | 249 | ✅ |  |
| 39 | jobs list | GET | `/api/v1/jobs` | 200 | 200 | 267 | ✅ |  |
| 40 | job unknown type → 422 | POST | `/api/v1/jobs` | 422 | 422 | 281 | ✅ |  |
| 41 | job unknown run → 404 | GET | `/api/v1/jobs/none` | 404 | 404 | 276 | ✅ |  |
| 42 | connections status (empty) | GET | `/api/v1/sites/zz-validation-e45414/connections` | 200 | 200 | 266 | ✅ |  |
| 43 | gsc test without property → not_configured | POST | `/api/v1/sites/zz-validation-e45414/connections/gsc/test` | 200 | 200 | 242 | ✅ |  |
| 44 | ga4 test bad id → not_configured | POST | `/api/v1/sites/zz-validation-e45414/connections/ga4/test` | 200 | 200 | 269 | ✅ |  |
| 45 | wordpress test (real site, read-only) | POST | `/api/v1/sites/zz-validation-e45414/connections/wordpress/test` | 200 | 200 | 6183 | ✅ |  |
| 46 | connections status (3 kinds) | GET | `/api/v1/sites/zz-validation-e45414/connections` | 200 | 200 | 273 | ✅ |  |
| 47 | gsc properties listing | GET | `/api/v1/connections/gsc/properties` | 200 | 200 | 2278 | ✅ |  |
| 48 | unknown connection kind → 404 | POST | `/api/v1/sites/zz-validation-e45414/connections/nope/test` | 404 | 404 | 365 | ✅ |  |
| 49 | initialize | POST | `/api/v1/sites/zz-validation-e45414/initialize` | 200 | 200 | 721 | ✅ |  |
| 50 | initialize idempotent | POST | `/api/v1/sites/zz-validation-e45414/initialize` | 200 | 200 | 568 | ✅ |  |
| 51 | site brain put (audience/cta/forbidden) | PUT | `/api/v1/sites/zz-validation-e45414/memory` | 200 | 200 | 581 | ✅ |  |
| 52 | site brain in AI context | GET | `/api/v1/sites/zz-validation-e45414/memory/context` | 200 | 200 | 471 | ✅ |  |
| 53 | legacy dashboard | GET | `/legacy/` | 200 | 200 | 657 | ✅ |  |
| 54 | legacy api | GET | `/legacy/api/sites` | 200 | 200 | 449 | ✅ |  |
| 55 | site delete refused (has data) → 409 | DELETE | `/api/v1/sites/zz-validation-e45414` | 409 | 409 | 498 | ✅ |  |
| 56 | site delete force | DELETE | `/api/v1/sites/zz-validation-e45414?force=true` | 200 | 200 | 437 | ✅ |  |
| 57 | site gone → 404 | GET | `/api/v1/sites/zz-validation-e45414` | 404 | 404 | 499 | ✅ |  |
| 58 | real site untouched | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 484 | ✅ |  |

## Coverage

* health / openapi / docs / request-id · error envelope (404, 409, 422) · sites CRUD (create, get, list, patch, delete-refuse, delete-force, 404 after) ·
  phase 3: connections status/tests (gsc/ga4/wordpress + 404 kind), gsc properties listing, initialize (idempotent), site brain fields + AI context ·
  graph (summary, nodes, node, 404, neighbors, filtered neighbors, subgraph, 422, search, path, orphans, unknown site) ·
  memory (get, put, context, learned pattern) · AI orchestrator (routes, providers, text run, JSON run + learn, 422) · jobs (enqueue, poll, list, 422, 404) · legacy mount.
* All checks ran over real HTTP against uvicorn (not TestClient). Read-only on the real site; writes only on the temporary site.
