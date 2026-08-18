# Content Strategy Planner + Advanced Content Brain — architecture plan (Phase 10)

Status: **design only — awaiting approval** · Date: 2026-08-18 · Companion docs: `docs/seo-brain/09-phase6-content-brain.md`, `11-phase7-content-intelligence.md`, `13-phase8-internal-linking.md`, `15-phase9-ai-orchestration.md`, contract `04-frontend-contract.md`.

Target flow: **SEO Research → Keyword Database → Content Strategy Planner → Content Calendar → Content Brief → AI Content Production → SEO Review → Internal Linking → Publishing (human).**

## 0. What already exists (inspection summary) and how the planner sits on top of it

| Layer | Exists today | Planner relationship |
|---|---|---|
| DB | migrations `0001…0008`; `categories` (WP hierarchical terms: `wp_id`, `parent_wp_id`, `count`, `url`), `keywords`/`keyword_clusters`/`keyword_opportunities`, `content_items` (status workflow, brief, drafts, scores, reviews, generation runs), `link_suggestions`, `site_memory`, `site_settings`, `ai_*` | new tables `content_plans`, `content_categories`, `content_plan_keywords`, `content_plan_events`, `content_clusters` (§2); no existing column changes |
| Graph | node types incl. `CATEGORY`, `KEYWORD`, `TOPIC`, `CONTENT`, `PAGE/POST`; relations incl. `TARGETS`, `BELONGS_TO`, `SUPPORTS`, `CONTENT_FOR`, `KEYWORD_TARGETS`, `CLUSTERED_IN`, `LINK_OPPORTUNITY` | add `CONTENT_PLAN`, `CONTENT_CLUSTER` nodes; `CONNECTED_TO`, `CONTAINS`, `PLANNED_AS` relations; new graph mode `planner` (§3) |
| Keyword Intelligence | normalizer, importer (CSV/TSV/XLSX/Sheet), clustering → TOPIC nodes, GSC opportunity analysis (`improve_page / create_content / update_title / add_internal_links`) | planner reads keywords/clusters/opportunities; keyword mapping writes `content_plan_keywords` + sets `keywords.status=planned` (already a valid status) |
| Content Brain | `content_items` workflow `planned→brief_ready→writing→review→approved→published`, briefs (H1/title/meta/H2-H3/FAQ/entities/schema/internal_links), Jalali calendar (`/content/calendar`), Kanban, drafts/score/review (Phase 7), generation (Phase 9) | **each plan owns exactly one `content_item`** (created on demand); briefs, drafts, scoring, review, AI Studio and the calendar keep working unchanged |
| Internal Linking | `LinkEngine` (`brain/linking/engine.py`) with LinkContext, journey stages, `link_suggestions` (source/target/anchor/reason/score), `SUPPORTS` edges | planner asks the engine for *pre-writing* link targets for a plan (§6.4) and stores them in `content_plans.link_targets` + `PLAN_LINK` suggestions (scope `plan`) |
| Site Brain memory | `site_memory` (business rules, tone, forbidden claims, `successful_patterns`) + insights → human confirm | planner recommendations read successful patterns; planner learning writes new patterns only after human accept (§7) |
| AI providers | Phase 9 gateway/router/prompts/Studio | **not touched**; planner produces briefs the AI Writer already consumes (`content_briefs`), plan → Studio deep-link (§9) |
| Frontend | Next 16 App Router, TanStack Table/Query, dnd-kit, shadcn/base-ui, React Flow graph, `features/content` (board, calendar, editor), `features/keywords`, `features/linking`, `features/ai-studio` | new `features/content-planner` + `/dashboard/content-planner`; calendar page upgraded in place |
| WordPress | read-only client (`wordpress/client.py`), full sync CLI (`sync-wordpress.py` → `categories`, `posts`, `post_terms`), Phase-3 connection test (`site.wp_url`) | category sync reuses the client + upserts `categories` (so graph builder/linking still see them) and fills `content_categories` intelligence |

Design principle: **the plan is the strategic row; the content item is the production object.** Nothing that consumes `content_items` today (calendar, Kanban, briefs, drafts, scoring, review, Studio, link engine, graph sync) needs to change.

## 1. Domain model

```
content_plans (strategy row, spreadsheet)  1 ──── 0..1  content_items (production, Phase 6–9)
      │ n..m via content_plan_keywords                    │ briefs / drafts / scores / reviews / generation_runs
      │ n..1 content_categories (WP or manual)            │
      │ n..1 content_clusters (editorial pillar/cluster)  │
      └── content_plan_events (audit)                     └── PUBLISHED_AS → PAGE/POST
```

* Plan status set (planner-level, 7 states): `planned → researching → brief_ready → writing → review → approved → published`.
  `researching` is **planner-only**: it maps to content item `planned` (the Phase-6 workflow, its 6-column board, tests and validate script stay unchanged). All other statuses are mirrored 1:1 with the linked content item; the mirror is one-directional per action (whichever side changes writes an event and updates the other through the existing `ContentService.transition` — no bypass of the strict gate: `approved` still requires the Phase-7 review gate, `published` is only set by the human/WP detection as today).
* Page types (enum, Persian labels): `service_landing`, `location_landing`, `pillar`, `article`, `guide`, `comparison`, `faq`, `product`, `category_page`, `news`.
* Intent (reuse keyword vocabulary): `informational | navigational | commercial | transactional | local`.
* Priority: `high | medium | low` (+ computed `priority_score` 0–100).

## 2. Database changes — migration `0009_content_planner.sql` (forward-only, additive)

```sql
CREATE TABLE content_categories (              -- WP categories + manual/virtual ones, with intelligence
  id INTEGER PRIMARY KEY, site_id TEXT NOT NULL REFERENCES sites(site_id),
  source TEXT NOT NULL DEFAULT 'wordpress',    -- wordpress | manual
  wordpress_category_id INTEGER,               -- wp term id (NULL for manual)
  parent_id INTEGER REFERENCES content_categories(id),
  name TEXT NOT NULL, slug TEXT, url TEXT, description TEXT,
  post_count INTEGER DEFAULT 0,                -- from WP
  page_count INTEGER DEFAULT 0,                -- crawled pages/posts mapped (post_terms ∪ url prefix)
  keyword_count INTEGER DEFAULT 0,             -- keywords mapped by rule/graph
  plan_count INTEGER DEFAULT 0,
  coverage_score REAL,                         -- 0–100 (keywords covered by existing pages)
  intelligence TEXT NOT NULL DEFAULT '{}',     -- JSON: clusters[], intents{}, top_keywords[], gaps[], graph_node_id
  metadata TEXT NOT NULL DEFAULT '{}', synced_at TEXT, created_at TEXT, updated_at TEXT,
  UNIQUE(site_id, source, wordpress_category_id));
CREATE TABLE content_clusters (                -- editorial cluster (pillar + supporting content)
  id INTEGER PRIMARY KEY, site_id TEXT NOT NULL, name TEXT NOT NULL, slug TEXT,
  pillar_plan_id INTEGER, keyword_cluster_id TEXT, topic TEXT, category_id INTEGER,
  description TEXT, metadata TEXT DEFAULT '{}', created_at TEXT, updated_at TEXT);
CREATE TABLE content_plans (
  id INTEGER PRIMARY KEY, site_id TEXT NOT NULL REFERENCES sites(site_id),
  content_item_id INTEGER REFERENCES content_items(id),   -- 1:1, created on demand
  title TEXT NOT NULL, url TEXT, slug TEXT,
  intent TEXT, page_type TEXT,
  category_id INTEGER REFERENCES content_categories(id), category_suggested_id INTEGER, category_reason TEXT,
  primary_keyword_id INTEGER REFERENCES keywords(id), primary_keyword TEXT,
  secondary_keywords TEXT NOT NULL DEFAULT '[]',          -- JSON [string] (free text; mapped ones also in content_plan_keywords)
  heading_structure TEXT NOT NULL DEFAULT '[]',           -- JSON [{level:2|3, text}]
  seo_title TEXT, meta_description TEXT,
  topic_id TEXT, cluster_id TEXT,                         -- keyword topic / keyword cluster (keyword_clusters.cluster_id)
  content_cluster_id INTEGER REFERENCES content_clusters(id),
  search_volume INTEGER, keyword_difficulty REAL,
  priority TEXT, priority_score REAL,
  target_audience TEXT,
  publish_date TEXT, publish_time TEXT,
  status TEXT NOT NULL DEFAULT 'planned',                 -- planned|researching|brief_ready|writing|review|approved|published
  existing_pages TEXT NOT NULL DEFAULT '[]',              -- JSON [{node_id,url,title,position?,relation}]
  link_targets TEXT NOT NULL DEFAULT '[]',                -- JSON [{direction:'from'|'to', node_id, url, title, anchor, reason_fa, score}]
  graph_connections INTEGER DEFAULT 0,
  content_score REAL,                                     -- latest Phase-7 score of the linked item (denormalised)
  recommendation TEXT NOT NULL DEFAULT '{}',              -- JSON: {action, title, page_type, intent, category_id, priority, reasons_fa[], confidence, computed_at}
  metadata TEXT NOT NULL DEFAULT '{}', notes TEXT, source TEXT,   -- manual | import:<file> | keyword:<id> | opportunity:<id> | link:<sid>
  created_by TEXT, created_at TEXT, updated_at TEXT);
CREATE INDEX idx_content_plans_site_status ON content_plans(site_id, status);
CREATE INDEX idx_content_plans_site_date ON content_plans(site_id, publish_date);
CREATE TABLE content_plan_keywords (
  content_plan_id INTEGER NOT NULL REFERENCES content_plans(id), keyword_id INTEGER NOT NULL REFERENCES keywords(id),
  role TEXT NOT NULL DEFAULT 'secondary',                 -- primary | secondary | supporting | question | gsc_query
  source TEXT, score REAL, created_at TEXT, PRIMARY KEY(content_plan_id, keyword_id));
CREATE TABLE content_plan_events (
  id INTEGER PRIMARY KEY, site_id TEXT NOT NULL, content_plan_id INTEGER NOT NULL,
  event TEXT NOT NULL,                                    -- created|updated|status_changed|imported|analyzed|category_set|keywords_mapped|linked_content|links_prepared|deleted
  actor TEXT, from_value TEXT, to_value TEXT, payload TEXT DEFAULT '{}', created_at TEXT);
CREATE TABLE content_plan_imports (                       -- import audit (like keyword_imports)
  id INTEGER PRIMARY KEY, site_id TEXT NOT NULL, filename TEXT, format TEXT, rows_total INTEGER, rows_created INTEGER,
  rows_updated INTEGER, rows_skipped INTEGER, errors TEXT DEFAULT '[]', mapping TEXT DEFAULT '{}', dry_run INTEGER, created_at TEXT);
ALTER TABLE link_suggestions ADD COLUMN plan_id INTEGER;  -- pre-writing suggestions (scope='plan'), nullable
```

Migration strategy: `0009` applied by the existing runner (`schema_migrations`); `db/tables.py` gains the Table objects; `tests/unit/test_migrations.py` bumps to `0001…0009`; site force-delete cascade (`sites.py::_CHILD_TABLES`) extended with the 6 tables. Rollback = drop new tables + ignore the nullable `link_suggestions.plan_id`. Backfill (optional, idempotent, human-triggered `POST /content-plans/backfill`): create a plan row for every existing `content_item` so the planner shows the current pipeline; `categories` → `content_categories` for existing WP sites.

## 3. Graph changes (additive)

* `NODE_TYPES` += `CONTENT_PLAN` (`plan:<id>`), `CONTENT_CLUSTER` (`ccluster:<id>`). `CATEGORY` already exists (`category:<taxonomy>:<slug>`); manual categories become `category:manual:<slug>`.
* `RELATION_TYPES` += `CONNECTED_TO` (plan → TOPIC), `CONTAINS` (CATEGORY → CONTENT/CONTENT_PLAN, CONTENT_CLUSTER → CONTENT_PLAN), `PLANNED_AS` (CONTENT_PLAN → CONTENT). Reused: `TARGETS` (plan → KEYWORD, weight = role), `BELONGS_TO` (plan → CATEGORY), `SUPPORTS` (plan → PAGE existing related page), `LINK_OPPORTUNITY` (plan ↔ page from pre-writing linking).
* Sync: `PlannerService.sync_graph(site)` (mirrors `ContentService.sync_graph`, called after create/update/import/analyze; ≤ 500 plans sync, more → job) — idempotent upsert + removal of orphaned `plan:*` nodes.
* New view mode `planner` in `graph/views.py`: node types `CATEGORY, CONTENT_CLUSTER, CONTENT_PLAN, KEYWORD, TOPIC, CONTENT, PAGE, POST`; relations `CONTAINS, BELONGS_TO, TARGETS, CONNECTED_TO, SUPPORTS, PLANNED_AS, PUBLISHED_AS, LINK_OPPORTUNITY`; layout layered (category → plan → keyword/content). Existing modes untouched; `/graph/node-details/{id}` gains `CONTENT_PLAN`/`CONTENT_CLUSTER` handlers (plan card, keywords, category reason, link targets) and `CATEGORY` details gain the intelligence block.
* Frontend graph: node styles/legends for the two new types; toolbar mode «نقشه برنامه محتوا»; details panel sections. `GET /sites/{id}/graph/content-plans` = convenience alias returning the planner subgraph filtered by plan ids/category (for the planner "Graph Connections" tab).

## 4. Backend services — `backend/seo_brain/brain/planner/`

| Module | Responsibility |
|---|---|
| `repository.py` | `PlannerRepository` (SQLAlchemy Core): CRUD for plans/categories/clusters/keywords/events; list with filters (`status, category_id, page_type, intent, priority, cluster_id, q, date range, has_item, sort, order, limit, offset`) and column projection; bulk update; counts. |
| `service.py` | `PlannerService`: create/update/delete with events; **link/create content item** (`ensure_content_item(plan)` → `ContentService.create` + mirror fields; `transition(plan, status)` mirroring through `ContentService.transition` — `researching` local only); calendar (`/content-plans/calendar` merges plans by `publish_date`, includes unlinked plans, respects the existing `/content/calendar` shape); CSV/XLSX import/export (`importer.py`, reusing `keywords/importer.py` parsing + Persian header aliases; columns = the planner columns; upsert key: `url` or (`primary_keyword`) or `title`; dry-run report); brief handoff (`POST /content-plans/{pid}/brief` → ensures item, calls `BriefGenerator` with plan hints: heading structure, secondary keywords, category, link targets → returns the Phase-6 brief; the item moves to `brief_ready`, plan mirrors). |
| `categories.py` | `CategoryIntelligence`: `sync(site)` — WordPress REST `/wp-json/wp/v2/categories?per_page=100` (paged) via existing `WordPressClient` (site.wp_url from Phase 3; read-only) → upsert `categories` (existing table, so graph builder keeps working) **and** `content_categories` (hierarchy by `parent_wp_id`, `post_count`); `analyze(site)` — for each category: pages (from `post_terms` + `posts` + crawled `pages`), keywords (rules: keyword tokens ∩ category name/slug/entity aliases (brand/model nodes), GSC queries of category pages, cluster majority), coverage score, gaps; `suggest(site, keyword or plan)` → `{category_id, name, reasons_fa[]: "۱۵ کلمه کلیدی مرتبط", "۸ صفحه موجود", "اینتنت مشابه", "رابطه گراف قوی"; confidence}`; manual categories CRUD for non-WP sites. |
| `keyword_mapping.py` | `KeywordMapper`: given keyword ids or an import batch → suggest/apply mapping to plans (`primary/secondary/supporting/question/gsc_query`), pull cluster/topic/volume/difficulty/GSC (`gsc_query_page`), ranking pages (`RANKS_FOR`), and produce the per-keyword recommendation (§6.1). Sets `keywords.status='planned'` when a plan is created from it (existing status value; `keywords.target_url` filled when the plan has a URL). |
| `recommend.py` | rule-based **Content Planning Intelligence Engine** (§6). Deterministic, explainable, no AI. |
| `linking_prep.py` | pre-writing links: builds a synthetic `LinkContext` for the plan (topic, cluster, entities, intent → journey stage from page type) and calls the Phase-8 scoring (`LinkEngine.score_pair`-level function; if it is not exposed, a thin additive helper is added to `brain/linking/engine.py`) against existing pages → top N *inbound* candidates ("from existing page → new plan") and *outbound* targets ("new plan → existing page"), stored in `content_plans.link_targets` and as `link_suggestions` rows with `scope='plan'`, `plan_id`, `status='proposed'` (excluded from the Phase-8 UI counts by scope; visible in the planner). When the plan is published (`PUBLISHED_AS` exists) the engine's regular analyze picks them up. |
| `learning.py` | planner learning (§7) — reads `content_metrics` (Phase 7) + `content_plans` fields (page type, title has location, FAQ, links count, category) → insights (`content_insights` category `planner`) → human accept → `site_memory.successful_patterns` (source `content_planner`). |
| `graph_sync.py` | §3 sync. |

Jobs: `planner_import` (large files), `planner_analyze` (site-wide recommend + category analyze), `planner_graph_sync` (>500 plans) — registered on the existing `InProcessJobQueue`.

## 5. API design (additive; contract §15) — prefix `/api/v1/sites/{id}/content-plans`

| Endpoint | Notes |
|---|---|
| `GET /content-plans/meta` | statuses (7, fa), page types, intents, priorities, columns (key, fa, group basic/seo, editable, type), import header aliases, feature flags |
| `GET /content-plans?…filters…&columns=` | `{items[ContentPlan], total, counts{by_status, by_priority, by_category}}` — server-side sort/filter/search/pagination (grid) |
| `POST /content-plans` (201) · `GET /content-plans/{pid}` · `PUT /content-plans/{pid}` (full) · `PATCH /content-plans/{pid}` (partial — inline cell edits) · `DELETE /content-plans/{pid}` (plan only; linked content item kept unless `?with_item=true`) | **ContentPlan** = all §2 columns + `content_item{id,status,status_fa,has_brief,latest_score,review_status,draft_count,url}`, `category{…}`, `keywords[{id,keyword,role,volume,intent}]`, `recommendation`, `link_targets`, `existing_pages`, `graph{connections, node_id}`, `events_count` |
| `POST /content-plans/bulk {ids[], patch{status?, priority?, category_id?, publish_date?, page_type?, …}}` · `POST /content-plans/bulk-delete {ids[]}` | bulk actions; status via the same mirror rules |
| `POST /content-plans/{pid}/transition {status}` | mirrors to the content item (strict gate preserved) |
| `POST /content-plans/{pid}/content-item` | ensure/link content item (`{content_id}`), also accepts `{content_id}` to link an existing item |
| `POST /content-plans/{pid}/brief {use_ai?, mark_ready?}` | brief via Phase-6 generator with plan hints → returns brief; 409 if no primary keyword |
| `POST /content-plans/{pid}/analyze` · `POST /content-plans/analyze {ids?|all}` | recompute recommendation, category suggestion, existing pages, link targets, keyword enrichment; site-wide → job when > 200 |
| `POST /content-plans/{pid}/link-prep` | (also part of analyze) returns and stores link targets |
| `POST /content-plans/import` (multipart `file`, `dry_run`, `mapping`) · `GET /content-plans/import/template.csv` · `GET /content-plans/export.csv|.xlsx?…filters…&columns=` | Persian/English header aliases; report `{format, columns, mapped, rows, created, updated, skipped, errors[]}`; xlsx via openpyxl |
| `GET /content-plans/calendar?from&to&category_id&status&priority` | `{days{date:[plan cards]}, unscheduled[], counts}` (plans + linked item status; the existing `/content/calendar` stays) · `PATCH` publish_date via `/content-plans/{pid}` (drag & drop) |
| `GET /content-plans/categories?tree=1` · `POST /content-plans/categories/sync` · `POST /content-plans/categories/analyze` · `POST /content-plans/categories` (manual) · `PATCH/DELETE /content-plans/categories/{cid}` · `GET /content-plans/categories/{cid}` (pages, keywords, plans, gaps) · `GET /content-plans/categories/suggest?keyword=&plan_id=` | WP sync read-only; 409 `wordpress_not_configured` |
| `GET /content-plans/keyword-mapping?status=unmapped|mapped&q` · `POST /content-plans/keyword-mapping/suggest {keyword_ids[]|all}` · `POST /content-plans/keyword-mapping/apply {items:[{keyword_id, plan_id|new, role}]}` | keyword → plan proposals with the §6.1 recommendation card |
| `GET /content-plans/suggestions?status` · `PATCH /content-plans/suggestions/{sid} {status: accepted|dismissed}` | Brain suggestions inbox (create-content recommendations from keywords/opportunities/category gaps not yet planned); accept → creates a plan |
| `GET /content-plans/clusters` · `POST/PATCH/DELETE …/clusters/{id}` | editorial clusters (pillar + supporting) |
| `GET /content-plans/insights` · `POST /content-plans/insights/learn` · `PATCH /content-plans/insights/{iid}` | §7 |
| `GET /content-plans/graph` (alias `GET /sites/{id}/graph/content-plans`) | planner subgraph `{nodes, edges}` in the Phase-4 view shape |
| `POST /content-plans/sync-graph` · `POST /content-plans/backfill` | maintenance |

Errors follow the envelope; validation 422; workflow 409 `invalid_transition`; all endpoints under `X-API-Token` via the Next proxy. OpenAPI/`schema.d.ts` regenerated; contract §15 documents shapes.

## 6. Content Planning Intelligence Engine (rule-based, explainable)

6.1 **Keyword → recommendation** (`recommend.for_keyword`): inputs keyword row (intent, volume, difficulty, cluster, topic), GSC (`gsc_query_page`: ranking page & position, impressions/clicks), graph (`RANKS_FOR`, `ABOUT` entities: brand/model/service/location), existing content items/plans targeting the keyword or cluster, category suggestion, link opportunities.
Rules (ordered, each contributes a reason string in Persian and a score):
* ranking page exists with position ≤ 10 → `optimize_existing` (link plan to page, `existing_pages`, priority low/medium); position 11–30 → `improve_page` (Phase-5 opportunity kind reused); no ranking page and no content item for the cluster → `create_new`; cluster already has a plan → `add_to_cluster` (supporting article) or `merge`;
* page type from intent + entities: transactional/commercial + service/model entity → `service_landing`; + location → `location_landing`; informational + question words («چگونه/چرا/مشکل/علائم») → `guide/article`; comparison words («یا/مقایسه/بهتر») → `comparison`; cluster head with ≥ 5 keywords → `pillar`;
* priority score = w·volume rank + w·intent (transactional > commercial > local > informational) + w·(1 − difficulty) + w·GSC impressions without clicks + w·cluster size + w·category gap − w·cannibalisation risk (existing item same cluster) → high ≥ 70, medium ≥ 40;
* title proposal: `{service} {model} {location?}` from entities and Site Brain patterns (e.g. "location in title" pattern boosts adding «تهران»); target audience from Site Brain `audience`.
Output: `{action, title, page_type, intent, category{id,name,reasons_fa[]}, priority, priority_score, reasons_fa[], existing_pages[], cluster, confidence}` — displayed as the "Brain Recommendation" column and in the Keyword Mapping tab.

6.2 **Plan → recommendation** (`recommend.for_plan`): same rules with the plan's fields; adds gaps: missing meta/title, keyword not clustered, no category, missing heading structure, no internal link targets, cannibalisation warning (another plan/page targets the same keyword), scheduling hints (category with many plans in the same week).

6.3 **Category suggestion** (`categories.suggest`): score per category = keywords in category ∩ keyword cluster (0.35) + existing pages in category ranking for cluster keywords (0.25) + intent match of category pages (0.15) + graph proximity (shortest path plan-entities ↔ category ≤ 2 hops, 0.25); reasons rendered exactly like the example («۱۵ کلمه کلیدی مرتبط · ۸ صفحه موجود · اینتنت مشابه · رابطه گراف قوی»).

6.4 **Pre-writing internal links** (`linking_prep`): reuse Phase-8 semantics (topic similarity, entity overlap, intent/journey stage difference, authority) between the plan and existing pages; keep caps (5 targets, 3 per source); reasons: «هم‌خوشه · مرحله متفاوت قیف»; stored, advisory, exported into the brief's `internal_links` and later validated by the Phase-9 linking agent.

6.5 **Existing pages / graph connections**: `existing_pages` = pages ranking for plan keywords + pages in the category with the same entities; `graph_connections` = degree of `plan:<id>`.

## 7. Learning system (planner scope, human-gated)

Data: `content_metrics` (Phase 7 GSC snapshots ≥ 1000 impressions / ≥ 30 clicks / ≥ 28 days) joined with plans (page type, category, title features: location/brand/model/number/question, heading count, FAQ present, internal links ≥ 5, word count) — features extracted from the linked draft structure. Method: same as Phase 7 (`ContentAnalytics.learn` style: effect vs. baseline, n ≥ 5, confidence) → `content_insights` (category `planner`, message like «مقاله‌های با مکان در عنوان + FAQ + ≥۵ لینک داخلی CTR بالاتری دارند») → human accept → `site_memory.successful_patterns` (source `content_planner`) → consumed by 6.1 title/priority rules and by the Phase-9 MemoryPack automatically. Never changes rules or weights automatically.

## 8. Frontend design — `features/content-planner/*`, route `/dashboard/content-planner`

Nav: «برنامه‌ریز محتوا» in the "محتوا" group (before «مغز محتوا»). Page = site selector + 6 tabs:

1. **جدول برنامه‌ریزی (Planning Table)** — TanStack Table v8 (already installed) + `@tanstack/react-virtual` (new small dep) for 1000+ rows; sticky header, RTL; column groups «پایه» / «هوش سئو»; inline editing per cell type (text, select, date (Jalali picker), multi-tag keywords, JSON heading editor in a popover); optimistic `PATCH`; row selection + bulk bar (status, priority, category, date, delete, «ساخت بریف», «ارسال به استودیو»); toolbar: search, filters (status/category/page type/intent/priority/date), sort, column visibility/order (persisted in `localStorage` per site), density; import dialog (drag file → dry-run report → apply; template download) and export (CSV/XLSX, current filter/columns). Row expander/side sheet with the recommendation card, keywords, link targets, events, and links to Content Brain / AI Studio. Grid choice: TanStack (headless, RTL-safe, already used) rather than AG Grid (bundle size, licence, RTL quirks); Google-Sheet feel via keyboard nav (arrows/Enter/Tab, Esc), copy/paste of a cell, fill-down on selection (v1 basic).
2. **تقویم (Calendar)** — upgrade `features/content/components/calendar-page.tsx` in place: month (existing Jalali grid) + **week** + **list** views; dnd-kit drag of cards between days (`PATCH publish_date`), priority colour bar, status chip, filters (category, status, priority), unscheduled tray. Data source: `/content-plans/calendar` merged with `/content/calendar` (items without a plan still appear).
3. **دسته‌ها (Categories)** — tree with counts (posts/pages/keywords/plans/coverage), sync button (WP; disabled with reason if not connected), analyze, manual category create/edit, category detail drawer (pages, keywords, plans, gaps, «ساخت برنامه از شکاف»).
4. **نگاشت کلمات کلیدی (Keyword Mapping)** — unmapped keywords table with the recommendation card (intent, page type, category, existing page, action, reasons); actions: create plan / attach as secondary to plan / ignore; import hook: after keyword import, banner «N کلمه جدید — پیشنهاد نگاشت».
5. **پیشنهادهای مغز (Brain Suggestions)** — inbox of create/improve suggestions (from keyword gaps, opportunities, category gaps, link prep) with reasons; accept → plan; dismiss.
6. **ارتباطات گراف (Graph Connections)** — embedded React Flow (existing graph feature components) in `planner` mode filtered to the selected plan/category; click → details panel; button «باز کردن در گراف دانش».

Content Brain integration: content editor shows «برنامه محتوایی» chip → planner row; planner row shows content status/score; Studio deep-link `?site&content` (existing).

## 9. Integration with AI production (preparation only)

No new AI code. The brief produced from a plan is the Phase-6 `content_briefs` row (H1, SEO title, meta, H2/H3, entities, FAQ, internal links, schema, CTA from Site Brain, external references field added to `brief.metadata.external_references[]` — additive) → AI Studio (Phase 9) already consumes it. Model/task selection, cost/token/performance storage exist (`ai_models`, `ai_calls`, prompt performance). Planner adds only `metadata.plan_id` on the brief and the deep-link.

## 10. Migration & rollout strategy

1. `0009_content_planner.sql` + tables + cascade + migration test → 2. services (repository, categories sync/analyze, keyword mapping, recommend, linking prep, graph sync) with unit tests → 3. API routers `content_plans.py` (+ graph mode) → 4. OpenAPI/types refresh → 5. planner UI (table first) → 6. calendar upgrade → 7. categories & keyword mapping tabs → 8. suggestions/graph tabs → 9. validate-api block, docs (`docs/seo-brain/16-phase10-content-planner.md`, contract §15, phase log, README) → commit per major step («Phase 10a migration+services», «10b API+graph», «10c UI», «Complete Phase 10»).
Backward compatibility: no existing endpoint/shape changes; new nav item; existing calendar page keeps its URL/behaviour with added views; content items without plans keep working; sites without WordPress get manual categories.

## 11. Testing strategy

Backend (`tests/api/test_planner_phase10.py`, `tests/unit/test_planner_rules.py`): migration 0009 present/idempotent; plan CRUD + PATCH + bulk + events; status mirroring incl. `researching` (item stays `planned`), strict-gate 409 preserved; import CSV/XLSX (Persian headers, dry-run, upsert, errors) + export round-trip; category sync via `httpx.MockTransport` WP fixture (hierarchy, counts, upsert into `categories` and `content_categories`), analyze/coverage, suggest reasons; keyword mapping (roles, `keywords.status=planned`, recommendation actions for ranking/no-ranking cases); recommend rules (page type/intent/priority/title, cannibalisation); linking prep (caps, reasons, `scope='plan'` isolation from Phase-8 counts); graph sync (nodes/edges/planner mode/details, orphan removal); calendar merge; site force-delete cascade; existing suites stay green (Phase 6 board 6 columns, validate script). Live: validate-api Phase 10 block.
Frontend: vitest (existing) unit tests for column model, filter/sort helpers, import mapping, calendar week/month grouping; `tsc`; browser verification of table render/filter/inline edit, calendar drag, categories tree, graph mode (documented with screenshots/text proof).

## 12. Decisions requested

1. **Plan ↔ content item = 1:1, item created on demand** (brief/production or explicit button) — vs. always create the item with the plan (simpler calendar, more Kanban noise). Recommendation: on demand + «backfill» to create plans for existing items.
2. `researching` status stays planner-only (mapped to item `planned`) — vs. adding it to the Content Brain workflow (touches Phase-6 board/tests/UI). Recommendation: planner-only.
3. Category sync writes both `categories` (existing) and `content_categories` (new) — keeps graph builder/link engine unchanged. Manual categories allowed for non-WP sites.
4. Grid: TanStack Table + virtualizer (no AG Grid). Inline editing v1: text/select/date/tags/heading popover; keyboard navigation basic.
5. Pre-writing link suggestions stored as `link_suggestions` with `scope='plan'` (+ nullable `plan_id`) — vs. planner-only JSON. Recommendation: both (JSON on the plan for the grid, rows for the engine).
6. Recommendation engine thresholds: priority high ≥ 70 / medium ≥ 40; ranking ≤ 10 → optimise, 11–30 → improve, else create; category suggestion confidence shown always; all advisory.
7. Learning writes only `content_insights` (category `planner`) → human accept → `successful_patterns` (source `content_planner`); min n = 5, Phase-7 thresholds.
8. Import upsert key order: `url` → `primary_keyword` → `title` (configurable in the mapping dialog).

Once approved, implementation follows the order in §10 with tests, docs and a commit after each major step.
