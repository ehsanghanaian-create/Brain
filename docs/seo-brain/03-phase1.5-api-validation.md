# Phase 1.5 — live API validation report

Date: 2026-08-17T12:51:07+00:00 · Base: `http://127.0.0.1:8000` · Site: `emdadmodiran` · Temp site: `zz-validation-1fde0d` (created and force-deleted)

**Result: 47/47 checks passed**

| # | Check | Method | Path | Status | Expected | ms | OK | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | root | GET | `/` | 200 | 200 | 341 | ✅ |  |
| 2 | openapi | GET | `/api/openapi.json` | 200 | 200 | 239 | ✅ |  |
| 3 | docs | GET | `/api/docs` | 200 | 200 | 231 | ✅ |  |
| 4 | health | GET | `/api/v1/health` | 200 | 200 | 256 | ✅ |  |
| 5 | request-id header | GET | `/api/v1/health` | 200 | 200 | 236 | ✅ |  |
| 6 | request-id echoed | GET | `/api/v1/health` | 200 | 200 | 230 | ✅ |  |
| 7 | 404 envelope | GET | `/api/v1/sites/nope-nope` | 404 | 404 | 232 | ✅ |  |
| 8 | 422 envelope | POST | `/api/v1/sites` | 422 | 422 | 248 | ✅ |  |
| 9 | sites list | GET | `/api/v1/sites` | 200 | 200 | 225 | ✅ |  |
| 10 | site get | GET | `/api/v1/sites/emdadmodiran` | 200 | 200 | 277 | ✅ |  |
| 11 | site create | POST | `/api/v1/sites` | 201 | 201 | 270 | ✅ |  |
| 12 | site create duplicate → 409 | POST | `/api/v1/sites` | 409 | 409 | 273 | ✅ |  |
| 13 | site patch mode | PATCH | `/api/v1/sites/zz-validation-1fde0d` | 200 | 200 | 255 | ✅ |  |
| 14 | site patch invalid mode → 422 | PATCH | `/api/v1/sites/zz-validation-1fde0d` | 422 | 422 | 244 | ✅ |  |
| 15 | graph summary | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 281 | ✅ |  |
| 16 | graph nodes (types=PAGE,POST) | GET | `/api/v1/sites/emdadmodiran/graph/nodes?types=PAGE,POST&limit=5` | 200 | 200 | 235 | ✅ |  |
| 17 | graph node | GET | `/api/v1/sites/emdadmodiran/graph/node/page:https://emdadmodiran.com/` | 200 | 200 | 250 | ✅ |  |
| 18 | graph node 404 | GET | `/api/v1/sites/emdadmodiran/graph/node/nope:x` | 404 | 404 | 232 | ✅ |  |
| 19 | graph neighbors | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/` | 200 | 200 | 237 | ✅ |  |
| 20 | graph neighbors filtered | GET | `/api/v1/sites/emdadmodiran/graph/neighbors/page:https://emdadmodiran.com/?relation_types=LINKS_TO&direction=out` | 200 | 200 | 250 | ✅ |  |
| 21 | graph subgraph hops=2 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=2&max_nodes=100` | 200 | 200 | 242 | ✅ |  |
| 22 | graph subgraph bad hops → 422 | GET | `/api/v1/sites/emdadmodiran/graph/subgraph?center=site:emdadmodiran&hops=9` | 422 | 422 | 233 | ✅ |  |
| 23 | graph search | GET | `/api/v1/sites/emdadmodiran/graph/search?q=امداد` | 200 | 200 | 260 | ✅ |  |
| 24 | graph path | GET | `/api/v1/sites/emdadmodiran/graph/path?source=site:emdadmodiran&target=page:https://emdadmodiran.com/` | 200 | 200 | 240 | ✅ |  |
| 25 | graph orphans | GET | `/api/v1/sites/emdadmodiran/graph/orphans` | 200 | 200 | 232 | ✅ |  |
| 26 | graph on unknown site → 404 | GET | `/api/v1/sites/nope-nope/graph/summary` | 404 | 404 | 250 | ✅ |  |
| 27 | memory get (empty) | GET | `/api/v1/sites/zz-validation-1fde0d/memory` | 200 | 200 | 297 | ✅ |  |
| 28 | memory put | PUT | `/api/v1/sites/zz-validation-1fde0d/memory` | 200 | 200 | 250 | ✅ |  |
| 29 | memory context | GET | `/api/v1/sites/zz-validation-1fde0d/memory/context` | 200 | 200 | 230 | ✅ |  |
| 30 | memory get (real site, read-only) | GET | `/api/v1/sites/emdadmodiran/memory` | 200 | 200 | 272 | ✅ |  |
| 31 | ai routes | GET | `/api/v1/ai/routes` | 200 | 200 | 247 | ✅ |  |
| 32 | ai providers | GET | `/api/v1/ai/providers` | 200 | 200 | 250 | ✅ |  |
| 33 | ai run text | POST | `/api/v1/ai/sites/zz-validation-1fde0d/run` | 200 | 200 | 250 | ✅ |  |
| 34 | ai run json + learn | POST | `/api/v1/ai/sites/zz-validation-1fde0d/run` | 200 | 200 | 239 | ✅ |  |
| 35 | memory learned pattern | GET | `/api/v1/sites/zz-validation-1fde0d/memory` | 200 | 200 | 243 | ✅ |  |
| 36 | ai run unknown kind → 422 | POST | `/api/v1/ai/sites/zz-validation-1fde0d/run` | 422 | 422 | 230 | ✅ |  |
| 37 | job enqueue noop | POST | `/api/v1/jobs` | 202 | 202 | 251 | ✅ |  |
| 38 | job run finished | GET | `/api/v1/jobs/job-6d0c29a3a464` | 200 | 200 | 224 | ✅ |  |
| 39 | jobs list | GET | `/api/v1/jobs` | 200 | 200 | 241 | ✅ |  |
| 40 | job unknown type → 422 | POST | `/api/v1/jobs` | 422 | 422 | 252 | ✅ |  |
| 41 | job unknown run → 404 | GET | `/api/v1/jobs/none` | 404 | 404 | 246 | ✅ |  |
| 42 | legacy dashboard | GET | `/legacy/` | 200 | 200 | 290 | ✅ |  |
| 43 | legacy api | GET | `/legacy/api/sites` | 200 | 200 | 230 | ✅ |  |
| 44 | site delete refused (has memory) → 409 | DELETE | `/api/v1/sites/zz-validation-1fde0d` | 409 | 409 | 234 | ✅ |  |
| 45 | site delete force | DELETE | `/api/v1/sites/zz-validation-1fde0d?force=true` | 200 | 200 | 248 | ✅ |  |
| 46 | site gone → 404 | GET | `/api/v1/sites/zz-validation-1fde0d` | 404 | 404 | 229 | ✅ |  |
| 47 | real site untouched | GET | `/api/v1/sites/emdadmodiran/graph/summary` | 200 | 200 | 286 | ✅ |  |

## Coverage

* health / openapi / docs / request-id · error envelope (404, 409, 422) · sites CRUD (create, get, list, patch, delete-refuse, delete-force, 404 after) ·
  graph (summary, nodes, node, 404, neighbors, filtered neighbors, subgraph, 422, search, path, orphans, unknown site) ·
  memory (get, put, context, learned pattern) · AI orchestrator (routes, providers, text run, JSON run + learn, 422) · jobs (enqueue, poll, list, 422, 404) · legacy mount.
* All checks ran over real HTTP against uvicorn (not TestClient). Read-only on the real site; writes only on the temporary site.
