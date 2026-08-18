# SEO Brain — Phase 9 plan: AI Content Generation & Agent Orchestration Layer (DESIGN ONLY — awaiting approval)

Status: proposal · Date: 2026-08-18 · Builds on the existing `seo_brain/ai/` orchestrator (Task → Router → Provider → Validator → Memory, EchoProvider only), `ai_providers`/`ai_routes` config (Phase 6, DPAPI SecretStore), Content Brain (items, briefs, versioned drafts, scoring, review, strict gate), Keyword Intelligence, Internal Linking, Site Memory, GSC. **AI never publishes; humans approve; nothing changes routing/rules automatically.**

Goal: turn the Content Brain into a real AI-assisted production system: a provider-agnostic gateway with cost/latency/token accounting and fallback, task-based routing, a multi-agent pipeline that consumes everything the Brain knows (keyword, cluster, brief, memory, entities, internal links, competitors when available), versioned prompts, an AI Studio UI, and a learning system that records what worked without acting on it.

---

## 1. AI Provider Gateway (`seo_brain/ai/gateway/`)

```
AITask ──▶ TaskRouter ──▶ Gateway.complete(provider, model, messages, opts)
                              │  adapters (one per kind, same interface)
                              ├─ AnthropicAdapter   (Messages API, system prompt, JSON mode via tool/JSON instruction, streaming)
                              ├─ OpenAIAdapter      (Chat Completions/Responses; also used by OpenRouter + custom OpenAI-compatible; base_url)
                              ├─ GeminiAdapter      (generateContent; safety settings; JSON mime)
                              ├─ OllamaAdapter      (/api/chat, local; no cost)
                              └─ EchoAdapter        (offline/tests)
                              ▼
                     AIResponse {text, parsed?, provider, model, input_tokens, output_tokens, cost_usd, latency_ms, finish_reason, raw_id}
                              ▼
                     ai_calls row (usage ledger) + validator + memory
```
* One `ProviderAdapter` interface: `test()`, `list_models()`, `complete(messages, model, temperature, max_tokens, json_schema?, stream=False)`, `stream()` (SSE chunks), `estimate(messages, model)` (tokens + cost from a **model catalog**), `capabilities` (json_mode, vision, tools, max_context, pricing).
* **Model catalog** (`ai_models` table + built-in defaults per kind): id, provider kind, context window, input/output price per 1M tokens, quality tier (`fast/balanced/quality/reasoning`), speciality tags (`persian`, `long_form`, `reasoning`, `cheap`, `translation`), enabled. Prices editable (OpenRouter/local = 0 or user-set).
* **Fallback**: `AIRoute` = primary (provider, model) + ordered fallbacks; gateway retries transient errors (429/5xx/timeouts) with backoff, then moves to the next; every attempt is recorded (`ai_calls.attempts`). Circuit-breaker per provider (N failures in M minutes → skip for a cooldown; visible in UI).
* **Accounting**: `ai_calls` ledger per call: task kind, site, agent, provider, model, prompt id/version, tokens in/out, cost, latency, ok/error, run_id, content_id, cache hit. Aggregations for the Studio and the learning system. Budget guard per site/month (`site_settings.ai.budget_usd`, soft warning + hard stop, both human-configured).
* Secrets stay in the SecretStore; keys never leave the backend; logs mask them (existing masking).
* Business logic (agents, pipeline, scoring) only ever sees `Gateway` + `TaskRouter`; no provider imports outside `ai/gateway/`.

## 2. Task-based AI Routing (`seo_brain/ai/routing.py`)

Task kinds (extend existing `TASK_KINDS`): `research`, `outline`, `article_long`, `article_section`, `rewrite`, `seo_review`, `title_meta`, `faq`, `translation`, `internal_linking`, `schema`, `brief`, `keyword_analysis`, `generic`.
```
Task(kind, priority low|normal|high, quality_min, max_cost_usd?, needs: {json, long_context, persian})
  ↓ 1. explicit route for (task_kind, site) or global (ai_routes)            — user-configured wins
  ↓ 2. else policy per kind: outline/rewrite/title_meta → tier fast/cheap; article_long → quality (persian, long_form);
        seo_review → reasoning; translation → speciality translation; research → balanced/long_context
  ↓ 3. filter available models: provider enabled + tested ok + not in circuit-break + capability match + budget left
  ↓ 4. rank by (quality_tier ≥ min) then estimated cost, then latency (from ledger p50)
  ↓ 5. execute via gateway with fallback chain (route fallbacks + next ranked models)
```
Routing decisions are logged with the reason (`route_reason`) into `ai_calls`, so the Studio can show "why this model". The learning system may *suggest* route changes; it never applies them.

## 3. Content Generation Pipeline & agents (`seo_brain/brain/generation/`)

Multi-agent, sequential with checkpoints; every agent: responsibility, input/output JSON schema (validated), provenance (provider/model/prompt version/tokens/cost/latency), can be re-run alone.

| Agent | Input | Output (schema) | Default task/tier |
|---|---|---|---|
| **Research Agent** | keyword + cluster siblings + GSC related queries + existing pages + entities + (competitor insights if a source exists) | `{facts[], questions[], gaps[], entities_to_cover[], sources[]}` — only from provided context; no invented facts (validator checks every fact has a `source` from context) | research / balanced |
| **Outline Agent** | brief (rules-v1) + research + Site Brain | `{h1, sections[{h2, h3[], goal, target_words, entities[], links[]}], faq[], schema_types[]}` | outline / fast |
| **Writer Agent** | outline (section by section for long articles) + Site Brain + entities + internal-link targets | `{sections[{h2, html/markdown, word_count}], intro, conclusion, cta_blocks[]}` → assembled Markdown | article_section/article_long / quality |
| **SEO Agent** | draft + keyword/cluster + review rules | `{title_options[], meta_options[], keyword_coverage_fixes[], schema_jsonld}` | seo_review / reasoning |
| **Reviewer Agent** | draft + brief + Site Brain (uses Phase 7 review engine first, then AI) | `{findings[], rewrite_proposals[{paragraph_index, text}]}` — proposals only | seo_review / reasoning |
| **Linking Agent** | draft + Phase 8 suggestions (`content_outbound`) + brief.internal_links | `{links[{anchor, url, section, sentence_proposal}]}` | internal_linking / fast |

Pipeline (`GenerationRun`): `plan → research → outline → write → seo → link → review → draft` with **checkpoints** (`generation_runs.step`); each step stores its artifact; a step can be re-run with a different model/prompt; the final artifact becomes a **new draft version** (`source=ai:<provider>`, provenance = run id + per-agent provenance) → Phase 7 **score → review → strict gate → human approval**. Estimated cost is shown before start; hard stop when budget exceeded. Runs are jobs (JobQueue) with progress events (SSE `GET /jobs/{run_id}/stream`, contract §3 placeholder) — the same job type runs under Redis/RQ later.

**Site Brain injection** — a `MemoryPack` builder assembles, for every agent call: business rules, tone (voice/formality/person/notes), audience, forbidden claims (also enforced post-hoc by the validator: reject/retry), CTA rules, content rules, successful patterns (content analytics + internal linking + AI performance), internal linking rules (anchor style, journey), language/locale. Prompt templates have mandatory `{{memory_pack}}` slots; the validator refuses to run a template without them ("no generic AI writing").

## 4. Prompt Management System (`seo_brain/ai/prompts/`)

* Tables `prompts` (id, scope `system|site|task|agent`, site_id nullable, key e.g. `agent.writer`, title, description, tags) and `prompt_versions` (prompt_id, version, template (Jinja-like `{{var}}`), variables schema, model hints, is_active, created_by, changelog, created_at). Built-in defaults seeded (v1) for every agent + `system.base` + `site.brain` (renders the MemoryPack).
* Rendering = system.base + site.brain + task/agent template; every `ai_calls` row records `prompt_id`/`version` per layer.
* **Prompt testing**: `POST /ai/prompts/{id}/versions/{v}/test` runs the version against a saved *test case* (content item / keyword) with a chosen model → stores a `prompt_tests` row (score from Phase 7 scoring engine when the output is a draft, tokens/cost/latency, human rating 1–5). Comparison view: v1 vs v2 side by side; performance table over time. Activation of a version is manual.

## 5. Learning System (`ai_performance` views + `ai_insights`)

Signals recorded automatically: per generation — model, prompt versions, cost, latency, Phase 7 score at first review, number of revision loops until `ready`, human rating, whether the draft was approved/published; later, GSC performance of the published content (Phase 7 analytics) joined by `content_id`.
Aggregations (`ai_insights`, gated like Phase 7: min n ≥ 5, published+28 days for ranking metrics): "model X yields +9 score at 1/3 the cost of Y for article_long", "prompt writer v2 needs 0.8 fewer revisions", "outline structures with FAQ + 5–7 H2 rank better". Shown in the Studio; **accepting** an insight only writes it to Site Brain memory / marks a route *recommendation* — routing changes remain a human action in AI Models.

## 6. Human control modes

Site `mode` (existing): **manual** — agents produce *suggestions* only (outline/proposals/rewrites shown, no draft version created unless the user clicks "ساخت پیش‌نویس"); **assisted** — pipeline creates draft versions and runs score/review automatically, still needing human approval to advance/publish; **autopilot** — *reserved*, disabled in this phase (UI shows it greyed with "فاز بعدی"). In all modes there is no publish path (unchanged).

## 7. Database proposal — migration `0008_ai_orchestration.sql` (additive)

| Table | Key columns |
|---|---|
| `ai_models` | id, provider_id (FK ai_providers), model_id, display, tier (`fast/balanced/quality/reasoning`), tags JSON, context_tokens, price_in_per_m, price_out_per_m, enabled, source (`catalog/discovered/user`), updated_at · UNIQUE(provider_id, model_id) |
| `ai_calls` | id, site_id, run_id, content_id, agent, task_kind, provider, model, prompt_refs JSON, input_tokens, output_tokens, cost_usd, latency_ms, ok, error, attempts JSON, route_reason, cache_key, created_at |
| `generation_runs` | id, site_id, content_id, mode, status (`queued/running/paused/succeeded/failed/cancelled`), step, steps JSON (per-agent status/artifact ids/provenance), estimate JSON, actual JSON (tokens/cost/latency), draft_id (result), job_run_id, created_by, created_at, updated_at |
| `generation_artifacts` | id, run_id, agent, version, schema_key, payload JSON, provenance JSON, created_at |
| `prompts`, `prompt_versions`, `prompt_tests` | as in §4 (+ `prompt_tests`: prompt_version_id, model, input_ref, output_ref, score, tokens, cost, latency, human_rating, notes) |
| `ai_insights` | site_id nullable, category (`model/prompt/structure`), feature, value, metric, effect, n, confidence, message_fa, evidence, status (`new/accepted/dismissed`), recommendation JSON |
| `ai_provider_health` | provider_id, window_start, calls, failures, p50_ms, breaker_open_until |
| `site_settings.ai` | budget_usd_month, default_language, mode overrides, allow_streaming |
`ai_routes` (existing) gains `fallbacks JSON` (ordered list) and `policy` (`explicit/auto`). All additive; forward-only.

## 8. API proposal (additive; contract §14)

**Gateway/models**: `GET /ai/models?provider_id` · `POST /ai/models/sync` (discover from provider `list_models`, keep user prices) · `PATCH /ai/models/{id}` (tier/tags/prices/enabled) · `POST /ai/estimate {task_kind, messages|content_id, model?}` → tokens/cost · `GET /ai/health` (breakers, p50, failures) · `GET /ai/usage?site_id&from&to&group_by=model|task|day` (ledger aggregations) · existing `provider-configs`/`task-routes` extended (`fallbacks`, `policy`) · `POST /ai/run` (existing generic task) now uses the real gateway.
**Prompts**: `GET/POST /ai/prompts` · `GET/POST /ai/prompts/{id}/versions` · `PATCH /ai/prompts/{id}/versions/{v}` (activate/changelog) · `POST /ai/prompts/{id}/versions/{v}/test` · `GET /ai/prompts/{id}/tests` · `POST /ai/prompts/preview {key, site_id, content_id?}` (rendered prompt + memory pack).
**Generation** (site-scoped): `POST /sites/{id}/content/{cid}/generate {agents?: [...], models?: {agent: model}, prompt_versions?: {...}, mode?}` → `202 GenerationRun` (job) · `GET /sites/{id}/generation/runs?content_id` · `GET /sites/{id}/generation/runs/{rid}` (steps, artifacts, estimate/actual) · `POST /sites/{id}/generation/runs/{rid}/{pause|resume|cancel|rerun-step}` · `GET /jobs/{run_id}/stream` (SSE progress) · `POST /sites/{id}/generation/runs/{rid}/accept` (assisted mode: promotes artifact to draft version + runs score/review; manual mode: only after human click) · agent-level utilities: `POST /sites/{id}/content/{cid}/agents/{outline|research|seo|linking|reviewer}/run` (single agent, returns proposal; no draft).
**Learning**: `GET /ai/insights?site_id&status` · `PATCH /ai/insights/{id}` (accept → memory/recommendation, dismiss).
Errors follow the envelope; `mode_blocked` (409) when a site is `manual` and a call would create a draft; `budget_exceeded` (409); `provider_unavailable` (503 with attempts).

## 9. UI proposal — **AI Studio** (`/dashboard/ai-studio`, Persian) + AI Models extensions

* Left rail: **انتخاب سایت** · **کار** (task kind) · **محتوا** (content item picker: keyword/brief/status) · **حالت** (دستی/نیمه‌خودکار; خودکار greyed).
* Panel **ارائه‌دهنده و مدل**: per-agent model selector (defaults from routing with the reason), tier badges, price/1M, health dot; toggle "استفاده از مسیردهی خودکار".
* Panel **پیش‌نمایش پرامپت**: rendered system/site/agent layers with version selectors; **پیش‌نمایش حافظه** (MemoryPack: rules/tone/audience/forbidden/CTA/patterns/linking) — read-only, link to Site Brain form.
* **برآورد**: tokens in/out and cost per agent + total, budget remaining; blocked when over budget.
* **اجرا**: progress timeline (agents as steps with live SSE status, tokens/cost per step, retry/fallback badges); pause/resume/cancel; per-step "اجرای مجدد با مدل دیگر".
* **مقایسه خروجی**: two columns (e.g. writer v1/Claude vs v2/GPT) with Phase 7 score cards, diff of outline/sections, cost/latency; "برگزیدن" → creates the draft version (assisted) or shows "ساخت پیش‌نویس" (manual).
* **تأیید پیش‌نویس**: opens the Content editor draft tab (score/review/gate) — approval remains the human workflow.
* AI Models page gains: model catalog table (tier/tags/prices/enabled/sync), route fallbacks editor, health/breakers, usage charts (cost by model/task/day), **پرامپت‌ها** (library, versions, activate, test & compare), **بینش‌ها** (insights with accept/dismiss).
* Content editor: "تولید با AI" button → opens Studio prefilled; Kanban card shows AI provenance chip.

## 10. Workflow diagrams

```
[Site memory] [Keyword+cluster] [Brief] [Entities] [Internal-link targets] [GSC] [Competitors?]
        └──────────────┬──────────────┬─────────┬──────────┬───────────────┘
                       ▼            MemoryPack + Context
   Research ─▶ Outline ─▶ Writer ─▶ SEO ─▶ Linking ─▶ Reviewer ─▶ (artifact)
     │ each: TaskRouter → Gateway(provider,model,fallback) → validator → ai_calls ledger → artifact+provenance
     ▼
   assisted: new draft version (source ai:<provider>) → score → review → [changes_requested → revision loop] → ready → HUMAN approves → (manual publish only)
   manual:   proposals shown → human clicks "ساخت پیش‌نویس" → same path
```
```
Task → Priority → explicit route? ──yes──▶ (provider, model, fallbacks)
                     │no
                     ▼
              policy tier for kind → available models (enabled ∧ healthy ∧ capable ∧ budget) → rank(quality ≥ min, cost, latency) → execute → on error: next → all failed → provider_unavailable
```

## 11. Migration proposal & rollout
1. `0008_ai_orchestration.sql` (tables above; `ai_routes` +2 columns).
2. Seed built-in model catalog + prompt v1 set (idempotent seed script `backend/cli/seed-ai.py`).
3. Gateway adapters + tests with **fake HTTP transports** (no network in CI); one opt-in live smoke script (`cli/ai-smoke.py`) that runs a tiny prompt against a configured provider and prints tokens/cost.
4. Router, MemoryPack, agents, pipeline (job), SSE progress; Studio UI; AI Models extensions.
5. Docs: `15-phase9-ai-orchestration.md`, contract §14, phase log.
Server compatibility: job type `generation_run` and `links_analyze` already go through `JobQueue`; the Redis/RQ backend implements the same protocol (`get_job_queue()` factory), workers import the same handlers; multi-site by `site_id` everywhere; scheduled generation = a cron job enqueuing `generation_run` (Phase 17/19).

## 12. Open decisions (defaults proposed)
1. Long-article writing **section-by-section** (Writer Agent per H2, then assembly) vs one call — proposal: section-by-section (better Persian quality, resumable, cheaper retries).
2. Streaming to the UI via **SSE per job** (proposal) vs polling only.
3. Budget guard defaults: warn at 80 %, hard stop at 100 % of `budget_usd_month` (default 20 USD/site) — OK?
4. Prompt templates language: Persian instructions with English structural keys (proposal), stored in DB with the seed as source of truth in repo (`backend/seo_brain/ai/prompts/defaults/*.md`).
5. Human rating (1–5) on drafts/prompt tests as an explicit learning signal — include in this phase?
