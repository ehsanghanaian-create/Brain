# Phase 9 — Claude (Anthropic) Integration

Status: **implemented, awaiting credentials + approval** · Date: 2026-08-19 · Scope: SEO Brain AI Gateway → Anthropic adapter → AI Content Test Workspace / AI Models UI.

Claude replaces Echo as the **default generation provider**. Echo stays available only as an offline/development fallback (last entry in every selector, never chosen automatically once a real provider is configured).

---

## 1. Setup (human steps)

1. **Create an API key** in the Anthropic Console: `https://platform.claude.com/settings/keys` → *Create Key* (`sk-ant-…`).
2. **AI Models → Claude (Anthropic) card** → «اتصال Claude» (or «ثبت کلید» if the `anthropic` provider entry already exists) → paste the key → ذخیره.
   The key travels once over the local proxy (`/api/backend/ai/provider-configs`, `X-API-Token`), is written to the **SecretStore** (DPAPI-encrypted file on this machine, ref `ai-provider-{id}`), and only the last four characters (`key_hint`) are ever shown again.
3. Press **«تست اتصال»** — a read-only `GET /v1/models` probe through the Gateway adapter; no prompt is sent. Status flips to *Connected*.
4. Optional: **«همگام‌سازی مدل‌ها»** to merge the live model list into the catalog (built-in Sonnet 5 / Opus 5 / Haiku 4.5 / Opus 4.8 / Sonnet 4.6 / Fable 5 rows are seeded on creation with list prices).
5. **«اعمال مسیرهای پیشنهادی»** — applies the curated route table (below) as *explicit* `ai_routes`. This is deliberately a human action: routing never changes automatically.

Alternative (headless / scripts): `POST /api/v1/ai/provider-configs {"name":"anthropic","kind":"anthropic","api_key":"sk-ant-…","default_model":"claude-sonnet-5"}` — same SecretStore path, same guarantees. Do **not** put the key in `.env`, source, or the DB.

No Anthropic session was found in the connected Chrome profile during this phase (platform.claude.com showed the login page; no `ant` CLI, no `ANTHROPIC_API_KEY`), so the provider entry `anthropic` was created **without a key** and the UI shows the *Missing credentials* setup screen until step 2 is done.

---

## 2. Architecture

```
UI (AI Content Test / AI Studio / AI Models)
  └─ Next proxy /api/backend/* (adds X-API-Token)
      └─ FastAPI /api/v1/ai/* · /sites/{id}/ai-workspace/*
          └─ ContentTestWorkspace / GenerationPipeline / AIStudio
              └─ TaskRouter (ai_routes explicit → policy → echo)      ai/gateway/routing.py
                  └─ Gateway.run(task, chain, meta)                    ai/gateway/gateway.py
                      budget (20$/site/month 80/100/120%) → circuit breaker → adapter.complete → validator → ai_calls ledger → health
                      └─ AnthropicAdapter (httpx, injectable transport)   ai/gateway/adapters.py
                          POST /v1/messages (stream:true) · GET /v1/models · POST /v1/messages/count_tokens
                              └─ api.anthropic.com  (key from SecretStore, x-api-key header only)
```

Nothing above the Gateway imports an adapter; the workspace, pipeline and Studio only ever see `RouteStep(provider, model)` and `AIResponse`.

### Provider flow (AI Content Test)

1. `GET /sites/{id}/ai-workspace/options` → providers (status, models with display names, health, last test) + `default = {provider, model, kind}` = first configured Claude provider with its `default_model` (Sonnet), else first configured provider, else Echo.
2. Live estimate: `POST …/estimate` → for Claude the input count is **exact** (`count_tokens`), output is heuristic; cost from the catalog price rows.
3. `POST …/generate` → `TaskRouter.resolve("article_long", override={provider, model})` (or the provider's default model when only the provider is given) → `Gateway.run` → `AnthropicAdapter.complete` (SSE consumed server-side, text/usage re-assembled) → `JsonKeysValidator` → SEO analysis (Phase 7 engine) → response `meta` carries `provider`, `provider_kind`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `run_id`, `prompt_version`, `memory_snapshot_id`, `stop_reason`, `streamed`, `route`, `attempts`, `budget`.
4. «ذخیره پیش‌نویس» (human) → `content_drafts` (source `ai:anthropic`) → Phase 6/7 review/approve flow unchanged. No publishing path exists.

### Adapter details (`AnthropicAdapter`)

| Capability | Implementation |
|---|---|
| test connection | `GET /v1/models` (paginated, `limit=100`) — read-only, no prompt |
| list models | same endpoint; merged into `ai_models` by `POST /ai/models/sync` (catalog rows keep user edits, discovered ids get guessed tiers: sonnet→balanced, haiku→fast, opus/fable→quality) |
| completion | `POST /v1/messages` with `stream: true`; SSE `message_start/content_block_delta/message_delta` re-assembled; plain JSON bodies still accepted (fake transports, proxies) |
| stream support | server-side streaming (idle-timeout safe, `on_delta` hook for a future token stream to the UI); the existing SSE job stream in the pipeline is unchanged |
| token estimate | `POST /v1/messages/count_tokens` (exact input) with heuristic fallback when no key/network |
| sampling params | `temperature` only for models that accept it; omitted for Opus 4.7+/4.8, Opus 5, Sonnet 5, Fable/Mythos (API returns 400 otherwise) |
| refusals | `stop_reason == "refusal"` → non-retryable `ProviderError` (never an empty draft) |
| errors | 401/403 → non-retryable; 429/5xx/network → retryable (gateway retries once, then next chain step; breaker after 3 consecutive failures, 5 min) |
| cost | catalog price rows × usage from the API response (input/output tokens) |

### Routing (applied by «اعمال مسیرهای پیشنهادی»)

| Task kinds | Primary | Fallback |
|---|---|---|
| article_long, article_section, content_writing, fact_check | claude-sonnet-5 | claude-opus-5 |
| seo_review, seo_analysis, research, brief, translation | claude-sonnet-5 | claude-haiku-4-5 |
| outline, rewrite, title_meta, faq, internal_linking, schema, keyword_analysis, generic | claude-haiku-4-5 | claude-sonnet-5 |

The workspace's `article_test` prompt runs under `article_long` (Sonnet default, Opus fallback). Without any explicit route the policy engine still lands on Sonnet for balanced tiers and Opus for quality tiers; Echo is used only when no real provider is available.

---

## 3. Security model

- **Key at rest:** SecretStore only (DPAPI, per-machine); DB stores `secret_ref` + `key_hint`; API responses drop `secret_ref` and never include `api_key` (tests assert this on create/list/test).
- **Key in transit:** sent once from the browser to the local Next proxy → local FastAPI; the adapter sends it only as `x-api-key` to `api.anthropic.com`.
- **Logs:** no logger receives the key; `ProviderError` messages contain HTTP status + truncated body only. Console/pytest output was checked for `sk-ant`.
- **Git:** `git grep sk-ant` on the working tree returns only test placeholders (`sk-ant-test`, `sk-ant-x1234`); `.env` untouched.
- **UI:** the setup card explains where to get the key and what happens to it; the workspace shows only status/hint.
- **Human gates unchanged:** drafts are saved only on click, routing changes only via the explicit apply endpoint, no publish endpoint exists.

---

## 4. Supported models (catalog, USD per 1M tokens)

| Model id | Display | Tier | In / Out | Context |
|---|---|---|---|---|
| claude-sonnet-5 (default) | Claude Sonnet 5 | balanced | 3 / 15 | 1M |
| claude-opus-5 | Claude Opus 5 | quality | 5 / 25 | 1M |
| claude-haiku-4-5 | Claude Haiku 4.5 | fast | 1 / 5 | 200K |
| claude-opus-4-8 | Claude Opus 4.8 | quality | 5 / 25 | 1M |
| claude-sonnet-4-6 | Claude Sonnet 4.6 | balanced | 3 / 15 | 1M |
| claude-fable-5 | Claude Fable 5 | reasoning | 10 / 50 | 1M |

Prices are editable in *AI Models → کاتالوگ*; live discovery adds any further ids returned by `/v1/models`.

---

## 5. Files changed

Backend: `ai/gateway/adapters.py` (Anthropic adapter rewrite), `ai/gateway/catalog.py`, `ai/gateway/gateway.py` (exact estimate), `ai/config.py` (setup metadata, recommended routes, delete cascade fix), `api/routers/ai_config.py` (recommended-routes endpoints, gateway-based connection test), `brain/generation/workspace.py` (status/default/display, meta fields), `tests/api/test_ai_phase9.py` (+2 tests), `tests/api/test_content_phase6.py`, `cli/validate-api.py` (+6 checks).
Frontend: `lib/api/client.ts` (types + endpoints), `features/ai-workspace/components/ai-content-test.tsx` (Claude default, status, labels, meta), `features/ai-models/components/ai-models-page.tsx` (`ClaudeCard` + setup screen), `lib/api/schema.d.ts` (regenerated).
Docs: `docs/seo-brain/openapi.v1.json` (164 paths), `docs/seo-brain/03-phase1.5-api-validation.md` (199/199), this file.

---

## 6. Test results (2026-08-19)

| Suite | Result |
|---|---|
| `pytest tests -q` | **91 passed** (incl. `test_anthropic_adapter_streaming_sampling_count_tokens_and_refusal`, `test_claude_provider_setup_routes_and_workspace_default`) |
| `vitest run` | 10 passed |
| `tsc --noEmit` | clean |
| `validate-api.py` (live) | **199/199** |
| Browser | AI Models: Claude card renders (Missing credentials → setup instructions, 6 models, health, usage); AI Content Test: Claude listed (disabled until key), Echo as offline fallback, no console errors |

### Real generation test («امداد خودرو رنو ساندرو»)

Pending — requires the API key (section 1). Once the key is registered the exact steps are: AI Content Test → provider *Claude · anthropic* (auto-selected) → model *Claude Sonnet 5* → title/keyword «امداد خودرو رنو ساندرو», secondary «امداد خودرو ساندرو تهران / خدمات امداد خودرو ساندرو / شماره امداد خودرو ساندرو», intent commercial, type service_landing → «تولید محتوا با Claude» → verify Preview/Markdown/SEO/Prompt/Meta tabs (provider anthropic, model claude-sonnet-5, tokens, cost, latency, run_id, prompt version, memory snapshot) → «ذخیره پیش‌نویس» → Content Brain review. Compare against the last Echo run (placeholder sections, 0 cost) in «اجراهای اخیر».
