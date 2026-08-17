# SEO Brain — Phase 4: Knowledge Graph UI = SEO Command Center (React Flow)

Date: 2026-08-17 · Contracts unchanged (three additive endpoints) · Backend 57/57 · Frontend vitest 5/5 · Live validation 65/65 · verified in the browser on the real emdadmodiran graph.

## 1. Backend (additive)

| Endpoint | Purpose |
|---|---|
| `GET /sites/{id}/graph/modes` | the three modes with their node/relation types + layout hint |
| `GET /sites/{id}/graph/view?mode=seo\|content\|links&types=&relation_types=&limit=&include_isolated=` | mode-filtered slice: nodes (PageRank-ranked, capped) + edges among them, `stats.by_type/by_relation`, `truncated/total_nodes` |
| `GET /sites/{id}/graph/node-details/{node_id}` | SEO detail bundle per node kind (below) |

**Modes** (`seo_brain/graph/views.py`):
* **نقشه سئو** — SITE/PAGE/POST/CATEGORY/QUERY/KEYWORD/BRAND/MODEL/SERVICE/LOCATION/SEO_PROBLEM/SEO_OPPORTUNITY; HAS_*, RANKS_FOR, KEYWORD_TARGETS, TARGETS, ABOUT, OFFERS, HAS_PROBLEM, HAS_OPPORTUNITY.
* **نقشه محتوا** — SITE/PAGE/POST/CATEGORY/TAG/SCHEMA/TOPIC/CONTENT/KEYWORD; HAS_*, BELONGS_TO, HAS_SCHEMA, CLUSTERED_IN, CONTENT_FOR, PUBLISHED_AS.
* **نقشه لینک داخلی** — PAGE/POST/CATEGORY; LINKS_TO, SUGGESTED_LINK (option to hide unlinked nodes).

**Node details** (`seo_brain/graph/details.py`, combines GraphStore + v0.1 analytics, read-only):
* Page/Post/Category → title, H1, word count, indexability, canonical, status, **content status** (`ok | thin | non_indexable | needs_links | unknown`), links (inbound/body/outbound/external + sources/targets), GSC (clicks/impressions/CTR/position + top queries), problems **with Persian title + suggested action**, opportunities with action, entities, related queries.
* Query/Keyword → position, CTR, impressions, clicks, pages count, importance reason, per-page rows, related pages.
* Problem → issue, severity, count, **suggested action** (rule table for 13 problem types), affected pages.
* Opportunity → type, count, action, items (url/related/query/score/reason).
* Entity (brand/model/service/location) → aliases, evidence, pages about, children. Schema → pages. Site → summary. Others → neighbours.

## 2. Frontend — `/dashboard/graph` (`features/graph/`)

* **Toolbar**: site selector · mode tabs · search (highlights matches, Enter focuses first) · grouping (none / type / community) · layout direction (TB/LR/RL) · hide-isolated (links mode) · fit view · re-layout · node/edge counter with truncation notice · **type-family chips** (کلمه کلیدی · صفحه · موجودیت · برند · مکان · اسکیما · محتوا · مشکل/فرصت) and **relation chips** with live counts (toggle to hide).
* **Canvas** (React Flow 12): custom `SeoNode` (type colour, short glyph, label, per-type metric — position/impressions for keywords, inbound links/position for pages, count/severity for problems), styled/dashed edges per relation, MiniMap, zoom/pan Controls, drag (positions remembered until re-layout), **selection highlight** (neighbours stay lit, rest dimmed), pane click clears.
* **Layouts** (`layout.ts`, unit-tested): dagre layered (direction-aware) and grouped columns with React Flow group nodes (by type in mode order or by Louvain community).
* **Right detail panel**: per-kind sections in Persian (see §1); clicking a related node in the panel focuses it on the canvas.
* Types regenerated from `openapi.v1.json` (25 paths).

## 3. Verification

| Check | Result |
|---|---|
| Backend pytest | 57 passed (+1 modes/view/details test: modes list, seo view shape, links mode isolated filter, types filter, 422 mode, truncation flag, details for query/page/site, 404) |
| Frontend vitest | 5 passed (`layout.test.ts`: node/edge mapping + metrics, layered ordering, grouped parents, community buckets) |
| Live validation | 65/65 (+7 graph checks) |
| Browser (real data) | SEO map 84 nodes / 200 edges / 11 type groups; chips with counts; page click → details (status سالم, 18 inbound, GSC 14/2143 · 9.3, 8 top queries, 3 problems with actions, 11 opportunities); keyword details (position/CTR/impressions/related pages); problem details (شدت متوسط, 4 pages, action); links mode 19/88; content mode 27/82; search "mvm" → 5 highlighted; hiding اسکیما chip 27→20 nodes; neighbour dimming (40 dimmed) |
| tsc | 0 errors |

## 4. Notes
* Frontend routes with node ids: the id is sent as **one URL-encoded segment** (Next collapses `//` inside path segments) — client `nodeDetails()` handles this; the backend route is `{node_id:path}` and decodes it.
* Type-check on this workstation needed the dev server stopped once (C: is too full for the pagefile to grow → V8 "allocation failure"); functional, but keep in mind.
* Content Brain untouched. Next: **Phase 5 — Keyword management** (import CSV/XLSX/Sheet export, clusters, topic map; KEYWORD/TOPIC nodes already have a place in the SEO and content maps).
