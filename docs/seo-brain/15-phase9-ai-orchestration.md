# Phase 9 — AI Content Generation & Agent Orchestration Layer (implementation report)

Date: 2026-08-18 · Plan: `14-phase9-ai-orchestration-plan.md` (approved with 10 final decisions) · Contract: `04-frontend-contract.md` §14 · OpenAPI: 112 paths.

**Guardrails kept:** AI never publishes; WordPress is never written; every generation ends in a *draft version* that goes through the Phase-7 gate (score → review → human approval); routing/prompts/budget change only by human action; provider keys never leave the SecretStore (not in API, logs, artifacts, or git); autopilot mode is reserved and rejected (`422`).

---

## 1. Migration report — `0008_ai_orchestration.sql` (forward-only, additive)

| Table | Purpose |
|---|---|
| `ai_models` | model catalog per provider: `tier` (fast/balanced/quality/reasoning), `tags`, `context_tokens`, `price_in_per_m`, `price_out_per_m`, `enabled`, `source` (catalog/discovered/manual). Seeded from `ai/gateway/catalog.py` on provider create + `POST /ai/models/sync`. |
| `ai_calls` | ledger of every gateway call: site, task_kind, agent, provider/model, prompt version, tokens in/out, `cost_usd`, latency, ok/error, run_id. Drives usage + budget. |
| `ai_provider_health` | per-provider calls/failures/consecutive_failures/p50/`breaker_open_until`/last_error (circuit breaker: 3 consecutive failures → 300 s open). |
| `memory_snapshots` | immutable rendered **MemoryPack** per site (deduped by content hash) — every run/preview/test references a snapshot id. |
| `prompts`, `prompt_versions`, `prompt_tests` | DB-versioned prompt library: key/scope/site, versions with `template`, `variables` (auto-extracted), `model_hints`, `is_active`, `approval` (draft/approved/rejected), `approved_by`, `changelog`; tests store rendered prompt, output, cost, latency, human rating. |
| `generation_runs`, `generation_artifacts` | pipeline runs (mode, status, `step`, `steps[]` checkpoints, `models{agent→provider/model}`, `prompt_versions{agent→id}`, `memory_snapshot_id`, `estimate`, `actual`, `draft_id`, `score`, `review_status`, `error`) + per-step artifacts (payload JSON, provenance). |
| `draft_feedback` | human rating 1–5 + tags (`good_structure, weak_intro, wrong_intent, too_generic, excellent_entities, good_links`) per draft/run. |
| `ai_insights` | learning output: category/feature/value/metric/effect/n/confidence, Persian message, evidence, **recommendation JSON**, status (new/accepted/dismissed), `memory_pattern_ref`. |
| `ai_routes` (+cols) | `fallbacks TEXT '[]'` (ordered chain `[{provider_id, model}]`), `policy TEXT 'auto'` (`explicit|auto|echo`). |

Applied on the live DB: `migrations.applied = 0001…0008`, no pending. Rollback: drop the 11 new tables (no existing rows altered; the two `ai_routes` columns have defaults). Site force-delete cascades `generation_runs`, `draft_feedback`, `memory_snapshots` (and `generation_artifacts` via run subquery).

## 2. Engine

* **Gateway** (`ai/gateway/`): `HttpAdapter` base + `AnthropicAdapter`, `OpenAICompatAdapter` (openai/openrouter/custom), `GeminiAdapter`, `OllamaAdapter`, Echo (no provider). `Gateway.run(task, chain, meta)` walks the route chain with one retry per step, records `ai_calls` + health, opens/honours breakers, and raises `BudgetExceeded` at the hard stop. `budget(site)` → `{limit_usd (default 20, `site_settings.ai.budget_usd_month`), spent_usd, ratio, state ok|warning(80%)|soft_limit(100%)|hard_stop(120%)}`. `estimate()` uses catalog prices.
* **TaskRouter** (`ai/gateway/routing.py`): 17 task kinds (`TASK_KINDS_V2`) with a policy each (preferred tiers + tags). Resolution: user override (Studio) → explicit `ai_routes` (site then `*`, honouring `policy` + `fallbacks` chain) → policy auto-chain over enabled catalog models (cost/quality ranking, breaker-aware) → Echo. Every decision carries a Persian `reason`.
* **MemoryPack** (`ai/memory_pack.py`): renders Site Brain (business rules, tone, audience, CTA/content rules, forbidden claims, successful patterns, linking rules) into a fixed Persian block; snapshot id stored on every run/test/preview. All agent templates must contain `{{memory_pack}}` (enforced with `422` on version create).
* **Prompt library** (`ai/prompts/`): 11 seeded prompts (`system.base`, `site.brain`, 7 agents, `task.rewrite`, `task.title_meta`), idempotent seed, versions with activation/approval/performance aggregation.
* **Agents** (`brain/generation/agents.py`): research → outline → writer (per section) → **fact_check** (unsupported claims, technical accuracy, vehicle specs, forbidden claims) → seo → linking → reviewer; JSON schemas + deterministic Echo placeholders; `validate_section()` (word target, keyword, entities, forbidden claims, headings).
* **Pipeline** (`brain/generation/pipeline.py`): Brief → Outline (fallback to brief outline) → per-section write + validate + fact-check (+1 retry) → assembly → SEO → linking → AI review → *assisted*: draft version + Phase-7 score/review; *manual*: stops at proposals until human `accept`. Emits `start/plan/step_start/step_done/done/failed/cancelled` on `InProcessEventBus` (topic `gen:<run_id>`) → SSE. Runs as job type `generation_run`. Sets `content_items.ai_provider/ai_model` (advisory chip only).
* **Learning** (`brain/generation/learning.py`): feedback storage; `learn(min_n=5)` aggregates rating/score/cost per model & prompt version → `ai_insights` with a *recommendation* (never applied automatically); `accepted` → Site Brain pattern (source `ai_performance`).
* **Compatibility**: `GatewayOrchestrator` in `api/deps.py` keeps the Phase-6/7 `.run(task)` contract (briefs / AI review) on top of the new gateway; Echo when no provider is configured.

## 3. API changes (all additive) — see contract §14

`/ai/task-kinds`, `/ai/models` (+`/sync`, `PATCH /{mid}`), `/ai/health`, `/ai/usage`, `GET/PUT /ai/budget`, `/ai/routing/preview` (422 unknown kind), `/ai/estimate`, `/ai/prompts` (list/create/get, `POST /{pid}/versions`, `PATCH /versions/{vid}` activate/approve, `/versions/{vid}/preview`, `/versions/{vid}/test`, `PATCH /tests/{tid}` rating), `/ai/insights` (+`/learn`, `PATCH /{iid}`), `/ai/feedback-tags`; `PUT /ai/task-routes/{kind}` accepts `policy` + `fallbacks` (omitted → unchanged).
`/sites/{id}/generation/meta`, `/generation/memory-preview`, `POST /content/{cid}/generate/estimate`, `POST /content/{cid}/generate` (202 job; 409 `budget_exceeded`; 422 autopilot), `/generation/runs` (+`/{run_id}`, `/{run_id}/stream` SSE, `/accept`, `/cancel`), `POST /content/{cid}/agents/{agent}/run` (research/outline/seo/linking/reviewer proposals), `POST/GET /content/{cid}/feedback`.

## 4. UI (Persian, RTL)

* **`/dashboard/ai-studio`** (`features/ai-studio/components/ai-studio.tsx`, nav «استودیوی AI»): site / content (brief flag) / mode (manual · assisted; autopilot greyed as reserved), per-agent provider/model override with routing reason, token/cost estimate per agent + budget bar (state colours), start; live SSE timeline (steps, per-section words/validation/fact-check/cost), cancel; artifacts viewer; **accept → draft** (manual); link to Content Brain; memory-pack preview; run comparison (2 runs side by side incl. score/cost); previous runs.
* **`/dashboard/ai-models`** now tabbed: providers + routing (policy select, fallback chain editor), **model catalog** (sync, tier, tags, prices, enabled, provider health/breakers), **usage & budget** (group by model/provider/task/agent, human budget input), **prompt library** (versions table with variables/active/approval/performance, load/activate/approve/preview/test/rate/compare, new version), **AI learning** (insights accept/dismiss — recommendation only).
* **Content Brain**: draft panel «تولید با AI» → Studio deep-link; `DraftFeedback` widget (1–5 + tags, history); Kanban card shows AI provenance chip (`✨ provider`).

Browser verification (dev server, Echo provider): Studio run `gen-9f523891bf` succeeded live via SSE (research, outline, 9 sections with fact-check pass, assembly 381 words, seo, linking, review) → accept produced draft v3 (score 76, changes_requested); AI Models tabs render (11 prompts, preview shows injected memory); feedback widget stored `5/5 (good_links)`; Kanban chip `✨ echo`. `tsc --noEmit` clean; no console errors besides HMR websocket noise.

## 5. Test results

* `pytest backend/tests` — **82 passed** (new `tests/api/test_ai_phase9.py`: adapters via `httpx.MockTransport`; prompts/memory-pack/routing; gateway fallback + ledger + breaker + budget; section validation; pipeline manual (Echo) + assisted (fake OpenAI) with SSE, feedback and learning; route policy/fallbacks + budget PUT).
* Live validation `backend/cli/validate-api.py` — **154/154** over HTTP (Phase 9 block: task-kinds, models, health, budget get/put/422, usage, routing preview + 422, route policy/fallbacks, prompts seeded/get/preview/version 422/create/approve, feedback tags, generation meta/memory-preview/estimate/start 202 + autopilot 422/run detail with provenance/SSE/list/accept + idempotent/404/feedback (+422)/single agent/insights) → `03-phase1.5-api-validation.md`.
* Security: no key/secret in any response (models/health/usage/artifacts carry provider *names* only); adapters read the key at call time from `SecretStore`; artifacts never store request headers.

## 6. Graph changes

None new in this phase (drafts created by the pipeline flow through the existing Phase-7 draft/score/review path; content nodes/edges unchanged).

## 7. Content Experiment schema proposal (future-ready — **not implemented**)

Goal: compare title / structure / intro variants of an approved content item using real GSC data, with human choice of the winner. Proposed additive migration `00XX_content_experiments.sql`:

```sql
CREATE TABLE content_experiments (
  id INTEGER PRIMARY KEY, site_id TEXT NOT NULL, content_id INTEGER NOT NULL,
  kind TEXT NOT NULL,                -- title | structure | intro
  hypothesis_fa TEXT, status TEXT NOT NULL DEFAULT 'draft',   -- draft|running|analyzed|concluded|cancelled
  metric TEXT NOT NULL DEFAULT 'ctr',                         -- ctr|position|clicks|conversion (GSC/GA4)
  min_impressions INTEGER DEFAULT 1000, min_days INTEGER DEFAULT 28,
  winner_variant_id INTEGER, decided_by TEXT, decided_at TEXT,   -- always a human
  created_by TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE content_experiment_variants (
  id INTEGER PRIMARY KEY, experiment_id INTEGER NOT NULL,
  label TEXT NOT NULL,               -- A/B/C
  draft_id INTEGER,                  -- points to content_drafts (variant is a normal versioned draft)
  run_id TEXT, prompt_version_id INTEGER, memory_snapshot_id INTEGER, model TEXT,   -- provenance
  payload TEXT NOT NULL DEFAULT '{}',-- {title, meta, h2[], intro_md} depending on kind
  is_control INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE content_experiment_metrics (
  id INTEGER PRIMARY KEY, variant_id INTEGER NOT NULL, date TEXT NOT NULL,
  impressions INTEGER, clicks INTEGER, ctr REAL, position REAL, source TEXT DEFAULT 'gsc',
  UNIQUE(variant_id, date));
```

Rules for the future implementation: variants are generated by the Studio (task kinds `title_meta` / `outline` / `rewrite`) as **drafts**, exposure changes are done by the human in WordPress (or via a future export), metrics come from the existing GSC sync, analysis re-uses Phase-7 thresholds (≥1000 impressions, ≥28 days), and the winner is *chosen* by a human; the outcome may be proposed as a Site Brain pattern (`content_experiment`), never applied automatically. Endpoints would live under `/sites/{id}/content/{cid}/experiments*` (additive).

## 8. Limitations & notes

* Real providers were exercised only through fake transports in tests; the live environment has no keys configured (Echo). Model discovery on `POST /ai/models/sync` is read-only.
* SSE is served in-process (`InProcessEventBus`); the `EventBus` protocol is the seam for a Redis Pub/Sub implementation when a worker process is introduced (jobs already run through the `JobQueue` abstraction).
* Fact-check and writer are section-scoped; single-agent runs are available for research/outline/seo/linking/reviewer.
* Unknown feedback tags are ignored (only the 6 approved tags are stored); rating is validated 1–5.
* Prompt versions are global unless `site_id` is set; per-site prompt overrides are supported by the schema but the UI creates global versions.
