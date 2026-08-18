# Phase 8.5 — Content Strategy Planner + Advanced Content Brain (implementation report)

Date: 2026-08-18 · Plan: `docs/content-strategy-planner-plan.md` (approved with 8 amendments) · Contract: `04-frontend-contract.md` §15 · OpenAPI: 158 paths (46 planner).

Flow delivered: **SEO Research → Keyword Database → Content Strategy Planner → Content Calendar → Content Brief → (AI production, prepared) → SEO Review → Internal Linking → Publishing (metadata only, human).**
Guardrails: everything additive; Phase 6 workflow/board unchanged (6 item statuses); WordPress read-only; publishing disabled (metadata only); AI generation only *prepared* (plan → generation job → content item → draft, executed later in AI Studio with human approval); recommendations are rule-based, permanent, versioned, and never applied automatically.

## 1. Migration report — `0009_content_planner.sql` (forward-only, additive)

| Table | Purpose |
|---|---|
| `content_categories` | `source` wordpress \| brain \| manual; WP id, parent, name/slug/url, `post_count`, `page_count`, `keyword_count`, `plan_count`, `coverage_score`, `intelligence` JSON (clusters, intents, top_keywords, gaps, entities, pages, graph_node_id), `synced_at` |
| `content_clusters` | editorial clusters (pillar plan + supporting) |
| `content_plans` | strategy row: title/url/slug, `intent`, **`serp_intent`**, `page_type`, **`funnel_stage`**, category (+ suggested + reason), primary keyword (+id), `secondary_keywords`, `heading_structure`, seo_title/meta, topic/cluster, `search_volume`, `keyword_difficulty`, priority + `priority_score` + **`ai_priority`** + **`business_value`**, **`traffic_opportunity`**, **`content_gap`**, **`cannibalization_risk`** + `cannibalization[]`, **`ranking_url`** + `ranking_position`, target audience, publish date/time, `status` (7), `existing_pages`, `link_targets`, `graph_connections`, `content_score`, `recommendation_id` + `recommendation` JSON copy, **`publishing`** JSON (metadata only), metadata/notes/source, 1:1 `content_item_id` |
| `content_plan_keywords` | keyword ↔ plan with role primary/secondary/supporting/question/gsc_query |
| `content_plan_events` | audit trail (created, updated, status_changed, analyzed, category_set, keywords_mapped, linked_content, links_prepared, brief_created, generation_prepared, publishing_meta, deleted) |
| `content_plan_imports` | import audit (file / google_sheet) |
| `content_plan_sources` | **Google Sheet** (public CSV export today; `google_sheets_api` reserved), csv_url; mapping, key columns, `auto_sync` reserved (never on) |
| `content_plan_recommendations` | **permanent Brain recommendations**: kind, action, title, page type, intent, priority(+score), confidence, reasons, payload, `version`, status new/accepted/dismissed/superseded/applied, engine `rules-v1`, decided_by/at |
| `content_plan_generation_jobs` | **future AI layer**: plan → job (`prepared`) → content item → draft; holds `generation_run_id`/`draft_id` when a human runs it in AI Studio |
| `link_suggestions.plan_id` | pre-writing suggestions (`scope='plan'`) |

Live DB: `0001…0009` applied. Rollback: drop the 9 tables (nullable `plan_id` stays harmless). Site force-delete cascades all planner tables.

## 2. Services — `backend/seo_brain/brain/planner/`

* `repository.py` vocabulary (statuses, page types, intents, priorities, funnel stages, gaps, roles, sources, recommendation kinds) + grid **column model** (33 columns in 3 groups: پایه / هوش سئو / برنامه‌ریزی پیشرفته) + CRUD/list/bulk/counts/events, categories (tree), clusters, recommendations (versioning: unchanged payload → same row; changed → new version, previous `new` → `superseded`; human decisions kept), imports, sources, generation jobs.
* `context.py` one-shot PlannerContext (keywords, clusters, GSC aggregates, graph pages/entities/categories, content items, plans, memory).
* `categories.py` **CategoryIntelligence**: `sync_wordpress` (REST `/wp/v2/categories`, paged, read-only; mirrors into v0.1 `categories` so graph builder/link engine keep working) with **local-snapshot fallback** when REST is unreachable; `sync_brain` (topic categories from keyword clusters, linked to the best WP category); `analyze` (pages by BELONGS_TO / ranking, related keywords by name/slug/entity/cluster/GSC rules, coverage %, gaps → permanent `gap` recommendations, intents, entities); `suggest` (score = 0.35 keywords + 0.25 pages + 0.15 intent + 0.25 graph; reasons «N کلمه کلیدی مرتبط · N صفحه موجود · اینتنت مشابه · رابطه گراف قوی»).
* `recommend.py` **rules-v1** engine: action (optimize_existing ≤10 / improve_page 11–30 / merge / add_to_cluster / create_new), page type (comparison/guide/pillar/location_landing/service_landing/article), funnel stage, title proposal (Site Brain patterns), priority score (volume, intent, difficulty, GSC striking impressions, cluster size, gap, cannibalisation, human business value), content gap, cannibalisation risk + hits, ranking URL/position, SERP intent, traffic opportunity, existing pages, plan gap hints (missing meta/category/headings/links, scheduling density).
* `keyword_mapping.py` overview (unmapped/mapped), suggest (recommendation card + category + mapping proposal, persisted), apply (new plan / attach with role; `keywords.status='planned'`; recommendation → `applied`).
* `linking_prep.py` synthetic PageInfo for the plan → Phase-8 `score_pair` in both directions → inbound/outbound targets with journey reasons, stored on the plan and as `link_suggestions(scope='plan')`.
* `importer.py` CSV/TSV/XLSX + Persian/English header aliases, enum aliases, headings/tags parsers, dry-run, upsert key url → primary_keyword → title, CSV/XLSX export (RTL sheet), template, Google Sheet CSV-export URL builder.
* `graph_sync.py` nodes `plan:<id>` (CONTENT_PLAN), `ccluster:<id>` (CONTENT_CLUSTER), `category:brain|manual:<slug>` (CATEGORY), `intent:<x>` (SEARCH_INTENT), `stage:<x>` (FUNNEL_STAGE); edges TARGETS, BELONGS_TO, CONTAINS, CONNECTED_TO, SUPPORTS, PLANNED_AS, LINK_OPPORTUNITY, HAS_INTENT, IN_STAGE; idempotent; sets `graph_connections`.
* `learning.py` plan features (page type, funnel stage, category, location-in-title, FAQ, ≥5 links, ≥5 H2, intent) × Phase-7 GSC metrics → `content_insights` (category `planner`) → human accept → `site_memory.successful_patterns` (source `content_planner`).
* `service.py` **PlannerService**: create/update/bulk/delete with resolution (keyword text → id, category name → id, funnel stage), status mirroring (`researching` planner-only; other statuses via `ContentService.repo.transition` **through the Phase-7 strict gate**), `sync_from_item` (content → plan; content transition endpoint calls it), `ensure_item` (1:1 on demand), `brief` (Phase-6 generator + plan hints), `analyze_plan/all` (recommendation + category + link prep + advanced fields; fills blanks only), suggestions inbox decisions (accept → plan/category), calendar (plans + orphan content items), board, import/export/sources sync, `prepare_generation`, `set_publishing` (metadata, `publishing_enabled=false`), backfill, graph view focus.

## 3. Graph changes

`NODE_TYPES` += CONTENT_PLAN, CONTENT_CLUSTER, SEARCH_INTENT, FUNNEL_STAGE · `RELATION_TYPES` += CONNECTED_TO, CONTAINS, PLANNED_AS, HAS_INTENT, IN_STAGE · new mode **`planner`** («نقشه برنامه محتوا», layered) · node details for CONTENT_PLAN (plan card + related keywords/category/content/intent/stage/links), CONTENT_CLUSTER, SEARCH_INTENT, FUNNEL_STAGE; CATEGORY details gain `planner_category` intelligence + plans. Existing modes unchanged (`/graph/modes` now lists 4).

## 4. API (additive) — contract §15

`/sites/{id}/content-plans`: `meta`, list (filters/sort/pagination), `POST`, `GET/PUT/PATCH/DELETE /{pid}`, `bulk`, `bulk-delete`, `analyze` (sync ≤200 / job `planner_analyze`), `backfill`, `sync-graph`, `sync-items`, `calendar`, `board`, `graph`, `import` (+`/template.csv`, `imports`), `export.csv|xlsx`, `sources` CRUD + `/{sid}/sync`, `categories` (list/tree, `sync`, `analyze`, `suggest`, create, `/{cid}` detail/patch/delete — WP read-only 409), `keyword-mapping` (+`suggest`, `apply`), `suggestions` (+`PATCH /{rid}`), `clusters` CRUD, `insights` (+`learn`, `PATCH`), `generation-jobs`, `/{pid}/transition|content-item|brief|analyze|link-prep|keywords|events|recommendations|generation-jobs|publishing-metadata`.

## 5. UI

* **`/dashboard/content-planner`** («برنامه‌ریز محتوا», nav group محتوا) — 7 tabs: **جدول برنامه‌ریزی** (TanStack Table: 33 columns in 3 groups, column chooser persisted per site, search + status/category/page-type/intent/priority filters, server sort/pagination, inline editing — double-click text/number/tags, selects for status/category/intent/page type/priority/funnel/date, quick-add row that triggers the Brain, row selection + bulk bar (status/priority/category/page type/date/analyze/brief/delete), import dialog (CSV/TSV/XLSX dry-run → apply, template, Google Sheet source add/preview/sync/delete), CSV/XLSX export of the current view, «تحلیل همه با مغز»); **کانبان** (7 status columns, drag = workflow transition with the same rules, priority bar, gap/cannibalisation badges, category filter); **تقویم** (month/week/list, drag & drop, category/status/priority filters); **دسته‌ها** (WP/brain/manual tree with posts/pages/keywords/plans/coverage, sync + analyze, detail: intents, gaps → «+ برنامه», top keywords, pages, plans, manual create/delete); **نگاشت کلمات کلیدی** (unmapped/mapped, Brain suggestion cards with reasons/existing page/category, create plan / attach with role / bulk apply); **پیشنهادهای مغز** (permanent inbox by status/kind, accept → plan/category, dismiss; planner learning insights accept → memory); **ارتباطات گراف** (React Flow command center in `planner` mode, focus on the selected plan).
* **Plan sheet** (from any view): workflow buttons, actions (تحلیل مغز, ساخت بریف, آماده‌سازی لینک داخلی, آماده‌سازی تولید AI, استودیوی AI, گراف), recommendation card (action, confidence, gap, cannibalisation, traffic opportunity, AI priority, funnel, reasons, gaps, suggested category accept), editable fields, keywords, existing pages, link targets, generation jobs, publishing metadata (disabled note), events.
* **`/dashboard/calendar`** upgraded in place (month/week/list, dnd, filters; content items without a plan still shown ◦). Content editor shows «برنامه محتوایی #id» link. Graph command center: new node styles/legends/relations + plan detail body.

Browser verification (dev server, real site data): table renders 3 plans with recommendations («افزودن به خوشه 57.6», gap «جزئی»); categories sync produced 5 WP categories (local snapshot fallback — REST handshake blocked from this box) with hierarchy امداد خودرو مدیران → امداد MVM / امداد چری and 1 brain category «تهران»; category detail shows intents, 6 gaps with «+ برنامه», top keywords, pages; kanban 7 columns with cards; keyword mapping produced cards e.g. «بهینه‌سازی صفحه موجود · لندینگ خدمت · تراکنشی · دسته: امداد MVM · pos 9 …»; plan sheet full; calendar month/week views with cards; graph planner mode: API 43 nodes / 101 edges (PL/I/F nodes rendered; edge SVG needs a visible pane). No console errors (besides HMR websocket noise). `tsc` clean; vitest 10/10.

## 6. Tests

* pytest **88 passed** (`tests/api/test_planner_phase85.py`: migration + categories sync (mock REST) + tree + read-only guard + suggest reasons; plan CRUD/PATCH/transitions (researching planner-only, 409 without item, strict gate 409, mirror both ways), brief → item, generation job prepared, publishing metadata, events, bulk, delete keeps item; import dry-run/apply/upsert/xlsx + exports + template + Google Sheet source sync (mocked httpx) + calendar/board; keyword mapping/suggest/apply/decisions + rules unit checks + graph mode/focus/details + insights + backfill + cascade; importer helpers; local-snapshot fallback).
* Live `validate-api.py` **188/188** (Phase 8.5 block: 33 checks).
* Frontend: vitest 10/10 (planner helpers: heading/tag parsers, filter/sort, calendar grouping/week), `tsc --noEmit` clean, browser verification above.

## 7. Notes & limitations

* WordPress REST was not reachable from this workstation (SSL handshake timeout) — the fallback used the v0.1 local snapshot; on a machine with access, «همگام‌سازی» reads live categories (still read-only).
* Google Sheet source uses the public CSV export URL (no auth); `google_sheets_api` kind is reserved.
* AI generation jobs are only *prepared*; running them stays in AI Studio (Phase 9) with human approval; `attach_generation_run` links a run/draft when that happens.
* Publishing: metadata only (`publishing_enabled=false` always); nothing is sent to WordPress.
* Grid virtualisation not added (server pagination 100/page); can be added later with `@tanstack/react-virtual`.
