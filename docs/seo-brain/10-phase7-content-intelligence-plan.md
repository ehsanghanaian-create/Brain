# SEO Brain — Phase 7 plan: Content Intelligence Layer (DESIGN ONLY — awaiting approval)

Status: proposal · Date: 2026-08-18 · Builds on Phase 6 (`content_items`, `content_briefs`, workflow, `ai_routes`) and Phase 5 (keywords, GSC join, opportunities). Nothing here is implemented yet.

Goal: turn the Content Brain from "plan + brief" into a **closed loop** — score a draft against what the Brain knows, review it (rules first, AI when a provider is configured), drive an explicit revision loop before human approval, and learn from GSC what actually works so scoring and briefs improve over time. Human approval and no-auto-publish stay unchanged.

---

## A. Content Quality Scoring Engine (`seo_brain/brain/content/scoring/`)

Input: a **draft** (see DB: `content_drafts` — HTML/Markdown body + title/meta) + its brief + keyword/cluster/GSC/graph context (already produced by `BriefGenerator`).
Output: `ContentScore` = total 0–100 + 7 dimension scores + explainable findings; stored per draft version.

| Dimension | Weight (default, per-site editable) | Deterministic signals (no AI needed) | Optional AI signal (Phase 9 provider) |
|---|---|---|---|
| **Search intent match** | 20 | keyword intent vs. page pattern: transactional/local → CTA + phone/address blocks + service words in H1/first 100 words; informational → question H2s, definitions, steps; navigational → brand entity present | "does this page satisfy intent X? (yes/partial/no + why)" |
| **Keyword coverage** | 15 | target keyword in title/H1/first paragraph/URL slug/meta; cluster siblings covered (normalized token match); density sanity band (0.5–2.5 %); over-optimization flag | semantic coverage of sibling intents |
| **Entity coverage** | 15 | brief.entities (BRAND/MODEL/SERVICE/LOCATION) present in body; alias-aware; missing entities listed | suggested extra entities |
| **Heading structure** | 15 | exactly one H1; H2 count vs. brief outline coverage (%); no skipped levels; heading lengths; FAQ section present when brief has questions | — |
| **Internal linking quality** | 15 | ≥ N internal links (per-site rule); links to brief.internal_links targets; anchor text ≠ "اینجا"; no orphaning (page linked *from* ≥1 hub — from graph); no self/duplicate links | anchor relevance |
| **CTA quality** | 10 | Site Brain `cta_rules` satisfied (e.g. phone in first paragraph), CTA count/position, forbidden claims absent (`forbidden_claims`) | tone match with Site Brain `tone` |
| **Content completeness** | 10 | word count vs. per-intent minimum (Site Brain `content_rules`), brief questions answered (question tokens near an answer paragraph), images with alt, meta length, schema hint present | missing sections vs. top-ranking pages *only if a competitor source exists* |

Score algorithm: each dimension → 0–1 from weighted rules; total = Σ weight·score; every rule emits `{rule, passed, weight, evidence, fix_fa}`. Thresholds: ≥ 80 "آماده", 60–79 "نیاز به بهبود", < 60 "ضعیف". Deterministic → identical input, identical score (testable).

## B. AI Content Review System (`seo_brain/brain/content/review/`)

`ContentReview` = structured findings before `review → approved`:
* **rule pass (always)**: reuses the scoring findings + adds: missing sections (brief.outline H2 not found), missing entities, weak paragraphs (< 40 words / no keyword or entity / boilerplate ratio), duplicate concepts (paragraph shingling: Jaccard ≥ 0.6 between paragraphs), SEO issues (title > 60, meta outside 120–160, no H1, image alt, links to non-indexable/redirecting pages via graph `props`).
* **AI pass (optional, task kind `seo_analysis` via `ai_routes`)**: JSON-validated prompt with the draft, brief and Site Brain memory → `{missing_sections[], weak_paragraphs[{index, why, rewrite_hint}], duplicate_concepts[], seo_issues[], suggestions[]}`; validated by the orchestrator (forbidden claims, JSON schema); provenance stored. If no real provider: review is rules-only and says so.
* Every finding: `{code, severity (high|medium|low), area, message_fa, evidence, suggestion_fa, auto_fixable}`; findings are versioned per draft.

## C. Content Revision Loop

Workflow inside the existing `writing → review → approved` stages (no new top-level status; sub-state lives on the draft):

```
Draft (content_drafts v1)
  ↓ POST /content/{cid}/drafts/{v}/review     (rules + optional AI)
AI Review → content_reviews (findings, score)
  ↓ findings.high > 0 or score < threshold  → "Issues Found"  (item stays `review`, draft.review_status = changes_requested)
Suggested Improvements → shown per finding (fix_fa / rewrite_hint), user edits or asks AI to rewrite a paragraph (task `content_writing`, returns a *proposal*, never applied silently)
  ↓ user saves → new draft version (v+1) with `revision_of` link and change summary
Revision → re-review (loop) — history kept per version
  ↓ score ≥ threshold and no high findings → draft.review_status = ready
Final Approval → existing human transition `review → approved` (guard: latest draft must be `ready`, or user overrides with a note → recorded in content_events)
```
Guards are configurable per site (`review_gate: strict|advisory`); default **advisory** in Phase 7 (warn), strict opt-in.

## D. Content Analytics Feedback (`seo_brain/brain/content/analytics/`)

Purpose: learn *which content patterns, titles and structures perform*, feed results back into (1) Site Brain `successful_patterns`, (2) scoring weights, (3) brief templates. Uses only data we have: GSC (`gsc_query_page`, `gsc_daily`), content items with `url` + `published` date, drafts' structural features.
* **Snapshots**: nightly job `content_performance_snapshot` per published content: clicks, impressions, CTR, avg position (7/28-day windows), top queries — stored in `content_metrics`.
* **Deltas**: position/CTR change vs. previous snapshot and vs. pre-publish baseline of the target keyword → `content_metrics.delta_*`.
* **Pattern learning (transparent statistics, no black box)**: features per content = {title pattern (question/number/brand-first/location-in-title), H2 count, FAQ present, word-count band, entity count, internal links count, intent}. Aggregate: mean CTR uplift / position gain per feature value with sample size; only report when n ≥ 5 and effect ≥ 0.5 pos or ≥ 15 % CTR. Output `content_insights` rows: `{feature, value, metric, effect, n, confidence, message_fa}` → surfaced in UI and written to Site Brain `successful_patterns` (source `analytics`) after user confirmation.
* Title A/B awareness: when a content item's title/meta changes (draft version), later CTR is attributed to the new title (event-based).

---

## Database changes proposal (migration `0006_content_intelligence.sql`, additive)

| Table | Columns (key ones) |
|---|---|
| `content_drafts` | id, site_id, content_id, version, title, meta_description, body_html, body_text, word_count, structure JSON (h1, h2[], h3[], links[], images[], faq), source (`user`,`import`,`ai:<provider>`), revision_of, change_summary, review_status (`none`,`changes_requested`,`ready`), created_at |
| `content_scores` | id, site_id, content_id, draft_id, total, dims JSON (7 scores), findings JSON, weights JSON, engine_version, created_at |
| `content_reviews` | id, site_id, content_id, draft_id, kind (`rules`,`ai`), findings JSON, summary_fa, provenance JSON, created_at |
| `content_metrics` | id, site_id, content_id, url, window (`7d`,`28d`), date, clicks, impressions, ctr, position, top_queries JSON, delta JSON |
| `content_insights` | id, site_id, feature, value, metric, effect, n, confidence, message_fa, status (`new`,`accepted`,`dismissed`), created_at |
| `site_settings` (or extend `site_memory`) | scoring weights per dimension, thresholds, `review_gate`, per-intent min word counts |
| `content_items` (+cols) | `current_draft_id`, `latest_score`, `review_status` (denormalized for lists) |
Indexes on (site_id, content_id) and (site_id, date). All forward-only, no changes to existing tables' semantics.

## API proposal (additive, `/api/v1/sites/{id}/content/...`)

| Endpoint | Purpose |
|---|---|
| `GET/POST /{cid}/drafts` · `GET /{cid}/drafts/{v}` · `POST /{cid}/drafts/import` (HTML/Markdown/DOCX-as-text upload) | draft versions; POST creates v+1 (`revision_of`, `change_summary`) |
| `POST /{cid}/drafts/{v}/score` · `GET /{cid}/scores` | run scoring engine; history |
| `POST /{cid}/drafts/{v}/review {use_ai}` · `GET /{cid}/reviews` | rules (+AI) review with findings |
| `POST /{cid}/drafts/{v}/suggest {finding_id}` | AI rewrite *proposal* for a paragraph/section (returns text, never writes) — 202 job when a real provider is used |
| `POST /{cid}/transition` (existing) | new guard when `review_gate=strict`: latest draft `ready` or `note` required |
| `GET /analytics/overview` · `GET /{cid}/metrics` · `POST /analytics/snapshot` (202 job) | performance snapshots + deltas |
| `GET /analytics/insights` · `PATCH /analytics/insights/{id}` (accept → writes Site Brain pattern) | learned patterns |
| `GET/PUT /settings/scoring` | weights, thresholds, gate |
Errors follow the envelope; long AI/analytics operations go through `/jobs` (202) per contract §5.

## UI proposal (Persian, existing routes extended)

* **مغز محتوا › ویرایشگر**: new tab **پیش‌نویس و امتیاز** — draft editor (paste/upload HTML/Markdown, versions dropdown, diff summary), **score card** (total gauge + 7 dimension bars, click → findings), **بازبینی** panel (findings grouped by area with severity, "پیشنهاد اصلاح" per finding, "بازنویسی با AI" → proposal side-by-side → apply creates a new version), review status badge; approval button shows gate state.
* **کانبان**: card shows score chip (color by threshold) and review status icon.
* **تحلیل محتوا** (new tab in مغز محتوا or route `/dashboard/content/analytics`): per-content performance table (CTR/position/impressions 7d/28d + deltas, sparkline), **الگوهای موفق** cards (feature → effect, n, confidence, accept/dismiss), title performance list.
* **تنظیمات سایت › امتیازدهی**: sliders for weights, thresholds, gate mode.
* **گراف**: CONTENT node details gain `latest_score`, review status, 28d metrics.

## Tests & docs (when implemented)
Unit: scoring determinism, each rule (fixtures of Persian drafts), duplicate-concept detection, analytics feature extraction & effect gating (n ≥ 5). API: draft versions, review loop, strict/advisory gate, insights accept → Site Brain. Live validation additions. Docs: `11-phase7-content-intelligence.md`, contract §12.

## Open decisions for you
1. Review gate default: **advisory** (recommended) or strict?
2. Draft storage: HTML+text in SQLite (proposed) vs. files in the site workspace (`data/sites/<id>/drafts/`) — SQLite keeps versioning/scoring simple; workspace files are Obsidian-friendly. Proposal: SQLite as source of truth + optional Markdown export to workspace.
3. Analytics windows 7d/28d and thresholds n ≥ 5, effect ≥ 0.5 pos / 15 % CTR — acceptable?
4. Should accepted insights auto-adjust scoring weights (suggested: no — only write to Site Brain patterns; weights stay user-controlled)?
