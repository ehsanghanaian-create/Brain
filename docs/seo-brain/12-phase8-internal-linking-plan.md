# SEO Brain — Phase 8 plan: Internal Link Intelligence Engine (DESIGN ONLY — awaiting approval)

Status: proposal · Date: 2026-08-18 · Builds on: graph (`LINKS_TO`, `ABOUT/OFFERS`, `RANKS_FOR`, `KEYWORD_TARGETS`, `CLUSTERED_IN`, `CONTENT_FOR`, PageRank, communities), `links`/`pages` crawl tables, keywords + clusters/topics + GSC, content items/drafts/briefs, `seo_opportunities` (`internal_link` rows from v0.1), Site Brain memory. **WordPress stays untouched — the engine only produces suggestions.**

Goal: not a link checker but an *intelligence layer*: for every valuable target page, find the source pages that are semantically related (topic, cluster, entities, intent, user journey), explain why, propose a contextual anchor, expose weak/orphan pages, learn from what you accept, and write learned patterns to Site Brain memory after human confirmation.

---

## 1. Inputs (all already in the DB) → one in-memory `LinkContext` per site

| Signal | Source | Used for |
|---|---|---|
| Page inventory | `graph_nodes` PAGE/POST/CATEGORY (+ props: title, H1, word_count, indexable, internal_links_in, pagerank, community) | targets/sources, authority, orphan/weak detection |
| Existing links | `links` (source_url, target_url, anchor_text, is_nav, is_internal) → `LINKS_TO` edges | "missing link" check, anchor distribution, nav-only inbound |
| Entities per page | `ABOUT` / `OFFERS` edges (+ `entity_mentions` scores) | entity overlap |
| Topic / cluster per page | `KEYWORD_TARGETS`, `RANKS_FOR` (query → cluster via `keywords`/`keyword_clusters`), `CLUSTERED_IN`, category `BELONGS_TO` | topic similarity, hub↔spoke |
| Intent | keyword.intent of the page's target keywords; fallback heuristics (URL/H1 patterns) | intent compatibility / journey |
| Text | title, H1, H2s, meta (crawl props) + draft `body_text` for Content Brain items | token-IDF cosine as *secondary* signal |
| Value | GSC impressions/position of the page's queries; keyword priority; `keyword_opportunities` (`improve_page`, `add_internal_links`); `seo_opportunities` (`striking_distance`, `internal_link`) | target priority |
| Content Brain | content items (planned/published), briefs' `internal_links`, latest draft links | suggestions from planned content, "SUPPORTS" |
| Site memory | `successful_patterns` (source `internal_linking`), CTA/business rules | bounded score boosts + anchor style |

## 2. Engine (`seo_brain/brain/linking/`)

### 2.1 Target selection (`targets.py`)
Score each page as a **target** (0–1): needs links (`inbound_body ≤ 2` → high; orphan → max), value (keyword priority high, GSC striking distance pos 4–20, `improve_page`/`add_internal_links` opportunities), authority gap (low PageRank but valuable), freshness (recently published content item). Threshold configurable; orphans always included.

### 2.2 Semantic relationship scoring (`scoring.py`) — for each (source, target) pair, explainable components (each 0–1, weights per site):
| Component (weight) | How |
|---|---|
| **topic** (0.30) | same keyword cluster/topic (via KEYWORD_TARGETS/RANKS_FOR → cluster) = 1; sibling clusters sharing tokens (IDF) = partial; same category (BELONGS_TO) = 0.6; same Louvain community = 0.4; text cosine (title/H1/H2 tokens, IDF) as fallback capped 0.5 |
| **entities** (0.20) | Jaccard over ABOUT/OFFERS entity sets, weighted by entity type (MODEL/SERVICE > BRAND > LOCATION); shared *specific* entity (model) → boost |
| **intent / journey** (0.20) | matrix: informational→commercial/transactional (blog supports service page) = 1.0; commercial→transactional = 0.9; same intent siblings = 0.6; transactional→informational = 0.3 (still useful for depth); hub (category) → spoke = 0.9; spoke → hub = 0.5 |
| **authority** (0.15) | source PageRank percentile × indexable × not-nav-only page; penalty if source already has > 40 outbound body links |
| **anchor availability** (0.15) | source text (H2s/paragraph tokens from crawl or draft) contains target primary keyword / entity tokens → a *contextual* place exists (1.0); only partial tokens (0.5); none (0.1 → suggestion becomes "add a sentence") |
Penalties: link already exists (drop), source == target, source non-indexable/redirect (drop), reciprocal-only pairs (−0.1), same-URL-family duplicates. **Learned-pattern boost**: +≤0.1 when the pair matches an accepted pattern (e.g. "blog:informational → service:transactional with entity anchor"), never more.
Result: `score = Σ wᵢ·cᵢ`, kept if ≥ 0.45 (configurable), plus `score_breakdown` and `reason_fa` assembled from the top 2–3 components with their evidence ("هر دو درباره «تیگو ۷»؛ کوئری‌های هم‌خوشه (امداد خودرو mvm تهران، #8.8، ۳۲۰ ایمپرشن)؛ صفحه هدف فقط ۱ لینک بدنه دارد").

### 2.3 Anchor suggestion (`anchors.py`)
Candidates: target's primary keyword, target H1, top GSC query of the target, matched entity label + service; ranked by (a) present in source text (exact/partial), (b) not already the site-wide over-used anchor (distribution), (c) length 2–6 words, (d) not generic ("اینجا", "کلیک کنید"), (e) Site Brain anchor style pattern. Output: `anchor` + `anchor_alternatives[]` + `placement_hint` (the H2/paragraph index where the tokens occur, or "add sentence in section X").

### 2.4 Weak-link & anchor-distribution audit (`audit.py`) — per page
inbound total / body / nav-only; unique sources; anchor distribution (top anchors with counts, exact-match ratio, generic ratio); outbound counts; flags: `orphan`, `nav_only_inbound`, `low_inbound`, `single_source`, `generic_anchors`, `over_optimized_anchor` (one exact anchor > 60 %), `no_outbound_body`, `links_to_noindex`. Persisted to `link_page_stats` (recomputed each analyze run).

### 2.5 Kinds of suggestions
`contextual` (source ↔ target semantic match), `orphan_rescue` (target orphan; best 3 sources), `hub_spoke` (category/service hub ↔ spoke pages), `supports` (informational content → commercial target; also from *planned* Content Brain items: "when this content is published, link it to X / from Y"), `anchor_fix` (existing link with generic/over-used anchor → proposed anchor), `content_outbound` (draft/brief internal links not yet in the draft body).

### 2.6 Learning (`patterns.py`)
From `accepted`/`done` vs `dismissed`: aggregate by (source page type × target page type, intent pair, top component, anchor style, entity type). Produce `link_patterns` rows with counts, acceptance rate, `message_fa` (e.g. "لینک از مقالات اطلاعاتی به صفحات خدمت با انکر مدل خودرو ۸۰٪ پذیرفته شده"). **Human confirms** → written to `site_memory.successful_patterns` (source `internal_linking`) and used as bounded boosts. Dismissals reduce weight of that pattern for future runs (also bounded, never below 0).

## 3. Graph integration (additive)
* `LINK_OPPORTUNITY` (source → target, props: score, breakdown, anchor, kind, suggestion_id, status=new) — created by analyze; removed when dismissed.
* `SUGGESTED_LINK` (source → target) — set when the user **accepts** (planned link) — already in the vocabulary; `done` keeps SUGGESTED_LINK with props.done=true until the next crawl shows a real `LINKS_TO`, then the analyzer drops it.
* `SUPPORTS` (page/content → page) — semantic support relation (informational supports commercial/transactional target; hub supports spoke), independent of link status; drives the links map view mode («نقشه لینک داخلی» gains these relation chips).
* CONTENT nodes participate (planned content as future source/target).

## 4. Database — migration `0007_internal_linking.sql` (additive)
| Table | Key columns |
|---|---|
| `link_suggestions` | id, site_id, kind, source_node_id, source_url, source_title, target_node_id, target_url, target_title, anchor, anchor_alternatives JSON, placement_hint, score, score_breakdown JSON, reason_fa, evidence JSON, status (`new/accepted/dismissed/done`), run_id, created_at, updated_at, UNIQUE(site_id, source_node_id, target_node_id, kind) |
| `link_page_stats` | site_id, node_id, url, inbound_total, inbound_body, inbound_nav_only, unique_sources, outbound_body, outbound_total, anchor_distribution JSON, exact_match_ratio, generic_ratio, flags JSON, pagerank, computed_at, PK(site_id,node_id) |
| `link_patterns` | id, site_id, pattern_key, feature JSON, accepted, dismissed, done, acceptance_rate, message_fa, status (`new/accepted/dismissed`), memory_pattern_ref, updated_at, UNIQUE(site_id, pattern_key) |
| `site_settings` key `linking` | weights, min_score, low_inbound_threshold (2), max_suggestions_per_target (5), generic_anchors list, exclude_url_patterns |

## 5. API (additive) — `/api/v1/sites/{id}/links/...`
`POST /analyze` (run engine: audit → targets → pairs → suggestions → graph sync; returns counts; also `202` job variant for large sites) · `GET /summary` (counts by kind/status, orphans, weak pages, top targets) · `GET /suggestions?kind&status&min_score&target&source&q&limit&offset` (paginated) · `PATCH /suggestions/{sid} {status, anchor?}` (accept/dismiss/done; accept updates graph SUGGESTED_LINK) · `GET /pages?flag=orphan|nav_only_inbound|low_inbound|generic_anchors…&sort` (audit) · `GET /pages/{node_id}` (page detail: inbound sources with anchors, outbound, distribution, suggestions for/from it) · `GET /patterns?status` · `PATCH /patterns/{pid} {status}` (accept → Site Brain memory) · `GET/PUT /settings` · `POST /sync-graph`. `DELETE /sites/{id}` clears the tables. Contract §13.

## 6. UI — `/dashboard/internal-linking` (replaces the roadmap page; Persian)
Header: site selector · «تحلیل لینک‌ها» (run) · KPIs (پیشنهادهای جدید، صفحات یتیم، صفحات با لینک ضعیف، لینک‌های پذیرفته/انجام‌شده) · link to graph (links map, filter LINK_OPPORTUNITY/SUPPORTS).
Tabs:
1. **پیشنهادهای لینک‌سازی** — table/cards: از (source title+URL) → به (target) · انکر پیشنهادی (editable, alternatives) · امتیاز + breakdown bars (topic/entities/intent/authority/anchor) · دلیل (Persian) · شواهد (cluster/query/entities/GSC) · kind badge · actions **پذیرش / رد / انجام شد**; filters kind/status/min score/target search; bulk accept for a target.
2. **صفحات بدون لینک** — orphans and low-inbound pages: inbound body/nav counts, PageRank, value (keyword/GSC), «۳ منبع پیشنهادی» inline (accept from here).
3. **لینک‌های ضعیف** — pages with nav-only inbound, single source, generic/over-optimized anchors, links to noindex; anchor distribution chart per page; `anchor_fix` suggestions.
4. **الگوهای یادگیری‌شده** — pattern cards (message, acceptance rate, n) with «تأیید و ذخیره در حافظه» / رد; list of what's already in Site Brain memory.
Editor integration: page detail sheet (inbound/outbound/anchors/suggestions); Content Brain editor gets a «لینک‌های داخلی» hint (brief links not yet in draft) reusing `content_outbound` suggestions.

## 7. Tests & docs
Unit: scoring components on a synthetic graph (topic/entity/intent/authority/anchor), anchor ranking, audit flags, pattern aggregation & bounded boosts, determinism. API: analyze on seeded site → suggestions with reasons, accept → SUGGESTED_LINK edge + pattern counts, dismiss → LINK_OPPORTUNITY removed, done, pages/orphans, patterns accept → Site Brain memory, settings, delete cascade. Live validation additions. Docs: `13-phase8-internal-linking.md`, contract §13, phase log.

## 8. Open decisions (defaults proposed)
1. Minimum score 0.45 and max 5 suggestions per target — OK?
2. `SUPPORTS` edges: create for all semantically related pairs above 0.6 topic+intent (not just suggested links) — OK, or only for suggested pairs?
3. Should accepted suggestions also create a Content Brain task ("add link on page X") in the Kanban (status planned) so the work is trackable, or stay in the linking dashboard only? (Proposal: optional button "ایجاد کار در مغز محتوا".)
4. Analyze run: synchronous for ≤ 500 pages, `202` job otherwise — OK?
