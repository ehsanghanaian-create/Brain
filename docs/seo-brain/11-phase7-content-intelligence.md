# SEO Brain — Phase 7: Content Intelligence Layer

Date: 2026-08-18 · Approved decisions applied: **strict gate by default**, **versioned drafts (every change = new version, with previous content / change summary / author-source / AI provenance)**, **conservative analytics gates (≥1000 impressions, ≥30 clicks, ≥28 days)**, **insights never change weights — human confirmation → Site Brain memory**, **Content Knowledge Memory** (accepted patterns stored in `site_memory.successful_patterns`, source `content_analytics`). AI stays advisory. No auto-publishing (assisted/autopilot remain future publishing modes).
Backend **73/73** · Live validation **108/108** · `tsc` clean · verified in the browser on the real site.

## 1. Data model — migration `0006_content_intelligence.sql`
| Table | Purpose |
|---|---|
| `content_drafts` | versioned drafts: version, title, meta, format (markdown/html/text), body, body_text, word_count, **structure** JSON (h1/h2/h3/headings/paragraphs/links/images/questions/faq), source (`user`/`import`/`ai:<provider>`), author, `revision_of`, `change_summary`, `provenance`, `review_status` (`none/changes_requested/ready`) |
| `content_scores` | per-draft score: total, 7 dims, findings (rule/passed/weight/evidence/fix_fa), weights, engine_version |
| `content_reviews` | per-draft review run: kind (`rules`/`rules+ai`), findings (code/severity/area/message_fa/evidence/suggestion_fa/auto_fixable/paragraph_index), summary_fa, counts, provenance |
| `content_metrics` | GSC snapshots per published content: window 7d/28d, date, clicks/impressions/ctr/position, top_queries, delta vs previous |
| `content_insights` | learned patterns: category/feature/value/metric, effect, baseline, n, impressions, clicks, confidence, message_fa, evidence, status (`new/accepted/dismissed`), `memory_pattern_ref` |
| `site_settings` | per-site JSON: `scoring` (weights, thresholds, min_words, min_internal_links, **review_gate strict|advisory**), `analytics` (min_impressions 1000, min_clicks 30, min_age_days 28, windows) |
| `content_items` +cols | `current_draft_id`, `latest_score`, `review_status` |

## 2. A — Content Quality Scoring Engine (`brain/content/scoring.py`, `score-v1`)
Deterministic (same input → same score, tested), explainable: every rule emits `{rule, dim, passed, weight, evidence, fix_fa}`.
| Dimension (default weight) | Rules |
|---|---|
| تطابق با اینتنت (20) | transactional/local/commercial: CTA/phone present, keyword tokens in first 2 paragraphs, location present for local; informational: question/step headings, definition early, ≥700 words |
| پوشش کلمات کلیدی (15) | keyword in title/H1, in first paragraph, in meta; ≥50 % cluster siblings covered; density 0.3–3 % |
| پوشش موجودیت‌ها (15) | ≥60 % brief entities present; ≥1 entity in headings |
| ساختار سرفصل‌ها (15) | exactly one H1; ≥60 % brief outline covered (or ≥3 H2); no skipped levels; FAQ when brief has questions |
| کیفیت لینک داخلی (15) | ≥ min internal links (3); links to brief targets; descriptive anchors; no duplicates; link to a hub page |
| کیفیت CTA (10) | Site Brain `cta_rules` (phone/CTA in first paragraph), CTA count per intent, **no forbidden claims** |
| کامل بودن (10) | min words per intent (Site Brain/settings), brief questions answered, image alt, meta 100–165, title 20–65 |
Total = weighted mean (0–100); labels `ready ≥ 80`, `needs_work ≥ 60`, `weak`. Weights/thresholds/gate editable per site (`PUT /content/settings/scoring`).

## 3. B — AI Content Review System (`brain/content/review.py`, `review-v1`)
* **Rules pass (always)**: missing sections (brief outline vs headings), missing FAQ, missing entities, weak paragraphs (short / off-topic / boilerplate), duplicate concepts (3-shingle Jaccard ≥ 0.6) and duplicate H2, SEO issues (no title, multiple H1, meta missing/length, title length, image alt, **links to non-indexable / redirecting pages via graph props**), plus score-derived high findings (forbidden claim, keyword not in title, CTA rule).
* **AI pass (optional, advisory)**: orchestrator task `SEO_ANALYSIS` with a JSON schema; findings validated & capped; provenance (provider/model/cost) stored; with only Echo → no AI findings and the note says so. AI never rewrites or applies anything.
* `review_status` = `ready` when no *high* findings and score ≥ threshold, else `changes_requested`; written to draft + item.

## 4. C — Content Revision Loop & gate
Draft vN → `POST /review` (rules + optional AI) → findings + score → user edits → **new version** (`revision_of`, `change_summary` auto-derived: ±words, new/removed H2, ±links, title changed) → re-review … → human `review → approved`.
**Gate (strict, default)**: `review → approved` is refused (409 `invalid_transition`) unless the latest draft is `ready`; `advisory` only warns (UI). Publishing remains manual (URL + transition). Every draft/review is logged in `content_events`.

## 5. D — Content Analytics Feedback (`brain/content/analytics.py`)
* `POST /analytics/snapshot`: for each content item with a URL, 7d/28d clicks/impressions/CTR/weighted position + top queries from `gsc_daily` (fallback `gsc_query_page`), delta vs previous snapshot.
* `POST /analytics/learn`: features per content from its latest draft (title pattern question/number/brand-first/plain, H2 band, FAQ, entity coverage band, CTA in first paragraph, **location in title (local SEO)**, word-count band, internal-links band, intent) × 28d metrics → per feature-value effect vs site baseline (CTR delta; position delta) — an insight is written **only if** n ≥ 5 **and** impressions ≥ 1000 **and** clicks ≥ 30 **and** content age ≥ 28 days, and the effect is material (≥15 % relative CTR or ≥0.5 position). Confidence from n and impressions. Nothing touches scoring weights.
* **Content Knowledge Memory**: `PATCH /content/insights/{id} {status: accepted}` → `site_memory.successful_patterns` gets `{pattern: message_fa, evidence, source: content_analytics, run_id: insight:<id>}` (idempotent) → used by the AI memory context in later briefs/reviews. Dismiss keeps it out.

## 6. API (additive) — `/sites/{id}/content/...`
`GET/POST /{cid}/drafts` · `GET /{cid}/drafts/{did}` · `POST /{cid}/score?draft_id` · `POST /{cid}/review {draft_id?, use_ai}` · `GET /{cid}/intelligence` (drafts/scores/reviews history) · `GET /{cid}/metrics?window` · `GET/PUT /settings/scoring` · `GET/PUT /analytics/settings` · `POST /analytics/snapshot` · `POST /analytics/learn?min_n` · `GET /analytics/overview` · `GET /insights?status` · `PATCH /insights/{iid}`. Transition endpoint now enforces the gate. Contract §12; OpenAPI 69 paths.

## 7. UI (Persian)
* Editor → tab **پیش‌نویس و امتیاز**: version selector (vN · source · words · status), *ویرایش → نسخه جدید* (title/format/meta/body/change summary), **بازبینی و امتیاز** / **بازبینی با AI**, draft structure summary + body, **score card** (total, label, 7 dimension bars with weights, failed rules with fixes), **review findings** grouped by severity/area with evidence and suggestion; note that suggestions are advisory. Approval buttons show the gate hint when the latest draft is not ready.
* Kanban card: score chip (color by threshold, ✓ when ready).
* Content page → tab **تحلیل و یادگیری**: performance table (28d, deltas, top queries), snapshot / learn actions, insights cards (**تأیید و ذخیره در حافظه** / رد, filter by status), scoring weights/thresholds/gate settings, analytics thresholds.

## 8. Verification
| Check | Result |
|---|---|
| Backend pytest | **73 passed** (+5 phase-7: parser (md/html), deterministic scoring good vs weak with expected failed rules, versioned drafts + review findings + strict/advisory gate end-to-end, insight acceptance → memory, analytics snapshot/learn with gates (12 backdated contents: FAQ CTR/position insights produced; raising min_clicks removes the small group; min_age skips all) |
| Live validation | **108/108** (+13 phase-7 checks) |
| Browser (real content «راهنمای امداد خودرو MVM در تهران») | draft v1 732 words → review: **94.8 آماده**, findings from the real brief; v2 created via UI (+H2 «قیمت…»), re-reviewed, both versions listed; Kanban chip `95 ✓`; analytics tab with gates «۱٬۰۰۰ ایمپرشن، ۳۰ کلیک، ۲۸ روز», gate select = strict |
| tsc | 0 errors |

## 9. Known limitations / next
* AI review/suggestions become real when a provider is routed (Phase 9); until then reviews are rules-only and say so.
* Insights need real published content with URLs + GSC history; the site currently has none published through the Brain, so the analytics table is empty until content is published/URL-linked and snapshots run (a nightly job can be scheduled in Phase 8/17).
* No paragraph-level "AI rewrite proposal" endpoint yet (design §C "suggest") — deferred to Phase 9 with real providers.
