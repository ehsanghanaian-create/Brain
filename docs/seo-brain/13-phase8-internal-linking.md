# SEO Brain — Phase 8: Internal Link Intelligence Engine

Date: 2026-08-18 · Approved decisions applied: min score 0.45 with **confidence levels** (0.45–0.60 اطمینان کم · 0.60–0.80 توصیه‌شده · 0.80+ اولویت بالا), **≤5 per target and ≤3 per source**, **SUPPORTS only when topical similarity ≥ 0.6 and the journey relationship is meaningful**, **"Create Content Task"** for accepted suggestions (never automatic), **sync ≤500 pages / job otherwise (existing JobQueue)**, **Journey Model**, **Link Health Score 0–100**, **patterns → human confirmation → Site Brain memory**, scope-aware design for future external/backlink/competitor scopes, **WordPress untouched** (analyze · suggest · approve · export).
Backend **76/76** · Live validation **116/116** · `tsc` clean · verified in the browser on the real site.

## 1. Migration report — `0007_internal_linking.sql`
| Table | Purpose |
|---|---|
| `link_suggestions` | scope (`internal` now; `external/backlink/competitor` reserved), kind, source/target (node, url, title, **stage**), anchor + alternatives + placement_hint, score, **confidence**, score_breakdown, reason_fa, evidence, status (`new/accepted/dismissed/done`), content_task_id, run_id · UNIQUE(site, scope, kind, source, target) |
| `link_page_stats` | per page: stage, inbound total/body/nav-only, unique sources, outbound body/total, anchor distribution, exact-match & generic ratios, flags, pagerank, **health_score 0–100 + breakdown** |
| `link_patterns` | pattern_key (journey / component / kind / anchor style), feature, accepted/dismissed/done, acceptance_rate, message_fa, status, memory_pattern_ref |
| `site_settings.linking` | weights, min_score 0.45, max_per_target 5, max_per_source 3, low_inbound_threshold 2, supports_min_topic 0.6, generic anchors, exclude patterns, sync_threshold_pages 500 |
Forward-only, additive; `DELETE /sites/{id}` clears the three tables. Applied live: migrations `0001…0007`, none pending.

## 2. Engine — `seo_brain/brain/linking/`
* **context.py** — one `LinkContext` per site from graph nodes/edges (PAGE/POST/CATEGORY + CONTENT items), crawl `pages`/`links`, entities (ABOUT/OFFERS), keyword clusters/topics (KEYWORD_TARGETS/RANKS_FOR → clusters), intent, GSC per page, keyword opportunities, drafts' text, Site Brain memory; IDF over page tokens.
* **journey.py** — stage classification `informational → commercial → service → conversion` (+`hub` for categories); `journey_score`: forward 1 step 1.0 / 2 steps 0.95 / 3 steps 0.85, hub→spoke 0.9, same level 0.55, spoke→hub 0.5, backwards 0.3; `is_meaningful` gates SUPPORTS.
* **scoring.py** — components (weights): **topic** 0.30 (shared cluster 1.0 · shared topic 0.9 · same category 0.6 · same community/text-IDF ≤ 0.5), **entities** 0.20 (type-weighted Jaccard, +0.3 for shared MODEL/SERVICE), **intent/journey** 0.20, **authority** 0.15 (PageRank percentile, outbound saturation penalty, non-indexable = 0), **anchor availability** 0.15 (target phrase present in source text); pairs with no topic *and* no entity relation are never suggested; existing links / self / non-indexable sources dropped; reciprocal-only −0.1; learned-pattern boost ≤ 0.1. `reason_fa` = top components + SEO evidence (inbound body count, GSC striking distance, keyword opportunities).
* **anchors.py** — candidates from target keyword/H1/top queries/entities/service+model combos; scored by presence in source text, site-wide anchor distribution (over-used −0.3, diversity +0.1), length, target-specific model/location (+0.15), Site Brain anchor patterns; returns anchor + alternatives + placement hint (H2 section / paragraph / "add a sentence").
* **audit.py** — flags `orphan, nav_only_inbound, low_inbound, single_source, generic_anchors, over_optimized_anchor, no_outbound_body, links_to_noindex, too_many_outbound, not_indexable`; **Health Score** = inbound contextual 35 + outbound balance 15 + anchor diversity 20 + orphan risk 15 + authority 15.
* **engine.py** — analyze: audit → targets (need × value × striking/opportunities) → pair scoring → caps (5/target, 3/source) → anchor_fix on generic/over-used existing anchors → upsert (user statuses preserved) → graph sync → pattern refresh; statuses (accept/done/dismiss) update graph; patterns aggregate by journey pair / top component / kind / anchor style (need ≥2 decisions); accepted patterns → `site_memory.successful_patterns` (source `internal_linking`) and bounded boosts; CSV export; page detail.
* Kinds: `contextual`, `orphan_rescue`, `hub_spoke`, `supports`, `anchor_fix`, `content_outbound` (planned Content Brain items as sources).

## 3. Graph changes
* Relation vocabulary + `LINK_OPPORTUNITY` (new suggestion, props anchor/kind/confidence/reason), `SUPPORTS` (topical ≥ 0.6 **and** meaningful journey; weight = topical similarity), existing `SUGGESTED_LINK` now = accepted/done (props anchor/done/suggestion_id).
* Links map («نقشه لینک داخلی») shows LINKS_TO · SUGGESTED_LINK · LINK_OPPORTUNITY · SUPPORTS with relation chips and includes CONTENT nodes; node details for pages gain **`link_health`** (score, breakdown, flags) and `link_suggestions` (to/from/supports).
* Live: 23 LINK_OPPORTUNITY + 5 SUPPORTS edges on example-site; no edges for same-level or backwards pairs (tested).

## 4. API changes — `/api/v1/sites/{id}/links/*` (contract §13, OpenAPI 81 paths)
`GET /meta` · `POST /analyze` (200 sync ≤ threshold, **202 job** `links_analyze` otherwise) · `GET /summary` · `GET /suggestions?kind&status&confidence&min_score&target&source&q&sort` · `GET/PATCH /suggestions/{sid}` (`{status, anchor?}`) · `POST /suggestions/{sid}/content-task` (planned Content Brain item, links back via `content_task_id`) · `GET /pages?flag&sort&order&q` · `GET /pages/{node_id}` · `GET/PATCH /patterns` · `GET/PUT /settings` · `GET /export.csv?status`. Job handler registered in the app; `DELETE /sites/{id}` cascades.

## 5. UI — `/dashboard/internal-linking`
Header: site · **تحلیل لینک‌های داخلی** · CSV export · graph link · "وردپرس تغییر نمی‌کند" note; KPIs (پیشنهادهای جدید by confidence, صفحات یتیم, لینک ورودی ضعیف, انکرهای ضعیف, میانگین سلامت لینک, پذیرفته/انجام‌شده); confidence legend.
Tabs: **پیشنهادهای لینک‌سازی** (filters status/confidence/kind/search; cards with confidence badge + score, kind, stage journey, از → به with URLs, editable anchor + alternatives + placement hint, دلیل, component bars topic/entities/intent/authority/anchor, evidence; actions **پذیرش / رد / انجام شد / بازگردانی / ایجاد کار محتوایی**) · **صفحات بدون لینک** (flag selector; table with stage, **health score chip**, inbound body/nav, sources, outbound, flags, inline top-3 sources with پذیرش) · **لینک‌های ضعیف** (nav-only/single-source/generic/over-optimized/noindex/no-outbound pages + anchor distribution) · **الگوهای یادگیری‌شده** (acceptance rate, n, **تأیید و ذخیره در حافظه** / رد).

## 6. Test results
| Check | Result |
|---|---|
| pytest | **76 passed** (+3 phase-8: journey/confidence/health unit; analyze on a seeded site — informational→service supports suggestion with entity anchor «ساندرو», existing link dropped, backwards ranked lower, orphan rescue, caps 5/3, anchor_fix for «اینجا», Persian reasons, LINK_OPPORTUNITY/SUPPORTS edges only meaningful, audit/health/node details, determinism; statuses → graph edges, re-analyze keeps statuses, patterns → memory, content task, CSV export, settings, **202 job mode**, no WordPress write paths) |
| Live validation | **116/116** (+8) |
| Browser (real site) | 23 suggestions (11 توصیه‌شده / 12 اطمینان کم), 5 orphans, avg health 60; accept with edited anchor → KPI 21 new / 1 accepted; orphan tab with inline sources; patterns after decisions (3) |
| tsc | 0 errors |

## 7. Documentation & notes
* Contract §13, this report, phase log, README updated. Plan: `12-phase8-internal-linking-plan.md`.
* Future scopes (external / backlink / competitor) only need a new context builder + candidate source; `scope` column and `future_scopes` in `/meta` reserve the space.
* WordPress: no write path exists (acceptance test 10 still enforces it); output = suggestions + CSV.
