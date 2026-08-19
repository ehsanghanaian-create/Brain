# Phase 9 — OmniRoute as an external routing provider

Status: **implemented, real generation verified, uncommitted** · Date: 2026-08-19 · Additive to the Phase 9 AI Gateway (nothing removed).

OmniRoute (`https://github.com/diegosouzapw/OmniRoute`, v3.8.49) is an open-source AI gateway that fronts Claude / OpenAI / Gemini / hundreds of others behind one OpenAI-compatible endpoint. SEO Brain keeps its own Gateway; OmniRoute is a **provider kind behind it**:

```
SEO Brain (UI → API → Gateway: budget · breaker · ledger · validator · TaskRouter · PromptLibrary · MemoryPack)
   └─ OmniRouteAdapter   (seo_brain/ai/gateway/providers/omniroute.py)
        └─ OmniRoute  http://127.0.0.1:20128/v1   → claude / openai / gemini / … (OmniRoute's own routing, "auto*")
   └─ AnthropicAdapter / OpenAI / Gemini / Ollama   (direct providers — unchanged)
   └─ EchoProvider                                  (offline fallback — unchanged)
```

## 1. API compatibility (studied)

| OmniRoute | Used by the adapter |
|---|---|
| `GET /v1/models` — list, `data[].id` like `auto/best-fast`, `aug/fable-5`, `ddgw/claude-haiku-4-5`; grouped variant also accepted | `list_models()` + `POST /ai/models/sync` (discovered ids get guessed tiers; `auto*` always selectable) |
| `POST /v1/chat/completions` — OpenAI shape; `stream:true` → SSE; **some `auto/*` routes answer with SSE even without `stream`** | `stream()` reads both SSE and JSON; `complete()` consumes `stream()` so both shapes work |
| `Authorization: Bearer <key>` — optional on a local install | key (optional) from SecretStore via the Gateway; never in code/env/logs |
| `X-OmniRoute-*` response headers (route class, cache, selected connection, decision) | captured as `raw.decision` → workspace meta `gateway_decision`, gateway-status `routing.last_decision` |
| `GET /api/monitoring/health` | available for ops; the adapter's `test()` uses `/v1/models` (same as every other provider) |
| model ids `provider/model`, `auto`, `auto/fast`, `auto/cheap`, `auto/coding`, `auto/claude-sonnet`, … | catalog seeds the four `auto*` entries; discovery adds the rest (116 on the test box) |

## 2. Adapter contract (`ProviderAdapter`, `ai/gateway/providers/__init__.py`)

`test()` · `list_models()` · `complete()` · `stream()` (yields text deltas, last item = `AIResponse`) · `estimate()` · `capabilities()`.
`HttpAdapter` (all existing adapters) now satisfies the same contract (default `stream()` = single chunk, `capabilities()` basic). `make_adapter("omniroute", …)` returns `OmniRouteAdapter` (lazy import). Sampling params are dropped for Claude 4.7+/5-family ids routed through OmniRoute, `response_format: json_object` is requested in JSON mode, `stream_options.include_usage` asks for usage in the last chunk, 401/403 → non-retryable, 429/5xx/network → retryable (SEO Brain Gateway retries once, then next RouteStep, breaker after 3 failures).

## 3. Database (no migration — existing tables)

| Requirement | Where |
|---|---|
| provider kind `omniroute` | `ai_providers.kind` (`PROVIDER_KINDS["omniroute"]`, `KEYLESS_KINDS`, `GATEWAY_KINDS`) |
| endpoint_url | `ai_providers.base_url` (exposed as `endpoint_url`, default `http://127.0.0.1:20128/v1`) |
| api key reference | `ai_providers.secret_ref` → SecretStore (`ai-provider-{id}`), `key_hint` only |
| health status | `ai_provider_health` (calls, failures, p50, breaker) + adapter `last_health`; `last_test` on the provider row |
| available models | `ai_models` rows (catalog `auto*` + discovered `provider/model`) |

`ProviderConfig.to_dict()` adds `is_gateway`, `route_kind` (`direct|gateway`), `endpoint_url`, `configured` (keyless kinds count as configured).

## 4. API (additive)

- `GET /ai/provider-kinds` → `omniroute` kind with `is_gateway`, `setup` text.
- `GET /ai/provider-configs/{id}/gateway-status` → status, health, breaker, capabilities, `routing` (last OmniRoute decision, tasks it is primary for, auto models, models available), `fallback` (tasks it is fallback for, SEO Brain chain policy, upstream resilience), recent calls.
- `GET/POST /ai/provider-configs/{id}/recommended-routes` now has an OmniRoute table (`auto` for content/analysis tasks with `auto/fast` fallback; `auto/fast` for quick tasks).
- Workspace `options` providers carry `route_kind` (`direct|gateway|offline`); `generate` meta carries `gateway_decision` and `served_model`.

## 5. UI

- **AI Models → OmniRoute card**: connection status (connected / untested / error / missing), models (auto first), health + last test, usage, and a routing/fallback panel (endpoint, last decision, primary-for / fallback-for task kinds, chain policy, recent calls). Buttons: تست اتصال · همگام‌سازی مدل‌ها · اعمال مسیرهای پیشنهادی · ویرایش / کلید (اختیاری). The Claude card is the same component (`ProviderKindCard`).
- **AI Studio** override selector: *ارائه‌دهنده مستقیم (Claude · OpenAI · Gemini · …)* vs *گیت‌وی (OmniRoute → …)* optgroups, default *خودکار (مسیریاب SEO Brain)*.
- **AI Content Test**: provider selector grouped *مستقیم / گیت‌وی / آفلاین*; meta tab shows *تصمیم گیت‌وی* + served model.

## 6. Preserved

Echo (still the explicit offline fallback), SecretStore (only secret path), `ai_calls` ledger (every OmniRoute attempt recorded), prompt versions (`task.article_test@v1`), MemoryPack snapshots (`memory_snapshot_id` in meta), budget + circuit breaker, human-only route changes.

## 7. Real generation test — «امداد خودرو رنو ساندرو» (2026-08-19, local OmniRoute keyless)

Install used for the test: `npm install omniroute --prefix D:\seo-brain\omniroute` (1186 packages, ~16 min on this box), launched via `.claude/launch.json` entry `omniroute` (port 20128; data dir `%USERPROFILE%\.omniroute`). Registered in SEO Brain as provider `omniroute` (no key) → تست اتصال OK (116 models) → همگام‌سازی (112 added).

| | Echo (`echo/echo-1`) | OmniRoute (`auto/best-free` → served `big-pickle`) |
|---|---|---|
| status | placeholder (deterministic) | **real**, streamed, via SEO Brain Gateway |
| tokens in/out | 265 / 16 | 1 068 / 2 830 |
| cost | 0 | 0 (free tier; price rows user-editable) |
| latency | 0 ms | 59 s |
| words | 223 | 738 |
| H1 | امداد خودرو رنو ساندرو | امداد خودرو رنو ساندرو |
| meta title | (placeholder) | «امداد خودرو رنو ساندرو \| تعمیرگاه و خدمات امدادی تخصصی» |
| meta description | (placeholder, 158 ch) | 120–160 ch, keyword + CTA |
| H2 / H3 | 6 generic / 2 | 6 targeted (چرا نمونه سایت، خدمات … تهران، شماره … درخواست سرویس، مزایا، تعمیرگاه تخصصی، فرآیند) / 7 |
| FAQ | 3 templated | 4 specific (پوشش تهران، خرابی در بزرگراه، سرویس دوره‌ای، زمان انتظار) |
| internal links | 4 generic | 4 (تعمیرگاه تخصصی رنو، حمل خودرو، سرویس در محل، تماس) |
| SEO checks / score | 7/9 · 86.8 | **9/9 · 93.2** |
| run_id / prompt / memory | ws-… / task.article_test@v1 / #1 | ws-fa01fcbc20 / task.article_test@v1 / #1 |

Other observations: `auto` (bare) and `auto/claude-sonnet`/`auto/claude-opus` failed on this box because OmniRoute has no upstream credentials configured yet (Felo/DuckDuckGo anonymous challenges, Claude connections absent) — the SEO Brain chain recorded every attempt, opened the breaker after 3 failures and returned the structured `generation_failed` error; Echo was untouched. Connect Claude/OpenAI/Gemini accounts inside OmniRoute's dashboard (`http://127.0.0.1:20128/dashboard`, default password must be changed) to route `auto/claude-*` for real; OmniRoute's own dashboard credentials are outside SEO Brain's SecretStore.

### Routing refinements (after the live test)
- **Auto-routing uses only the gateway's curated `auto*` entries.** Discovered `provider/model` ids (116 here, many needing upstream credentials inside OmniRoute) are for *explicit* selection in the Studio/workspace; the policy router skips `source=discovered` rows of gateway kinds so a bare "نگارش مقاله بلند" never lands on e.g. `auto/claude-opus` without credentials. Preview: `article_long` → `omniroute/auto/coding` → `omniroute/auto`.
- **Upstream diagnostics in errors.** OmniRoute explains combo failures in `x-omniroute-combo-*` / `x-omniroute-recovery-*` headers; the adapter now puts that reason in the `ProviderError` (e.g. *exhausted_connection:opencode* when the keyless free tier is used up), so the workspace error and `ai_calls.error` say why.
- **Validation script is provider-independent.** `validate-api.py` temporarily disables every enabled provider (restored at exit) and pins the pipeline run to Echo, so the 204 checks never spend tokens or depend on OmniRoute/Claude availability.
- **Draft hand-off verified:** the OmniRoute article was saved as draft v2 (`ai:omniroute`, provenance provider=omniroute) on content #15, scored (67.8 against that item's own keyword «امداد خودرو چری تهران») and reviewed (`changes_requested`) — Phase 6/7 flow intact.

## 8. Security

No key in code; OmniRoute key optional and stored only via SecretStore; adapter never logs headers; API responses carry `has_key`/`key_hint` only; `git grep` shows only test placeholders (`omni-secret-7777`, `omni-key`).

## 9. Tests

pytest **93 passed** (+`test_omniroute_adapter_contract`, `test_omniroute_provider_end_to_end`), vitest 10, `tsc --noEmit` clean, `validate-api.py` **204/204** (+5 OmniRoute checks; providers paused during the run), browser: AI Models / AI Studio / AI Content Test render, no console errors.

## 10. Files

Backend: `ai/gateway/providers/__init__.py`, `ai/gateway/providers/omniroute.py` (new), `ai/gateway/adapters.py` (contract defaults, lazy registration), `ai/gateway/catalog.py`, `ai/gateway/routing.py`, `ai/config.py`, `api/routers/ai_config.py` (gateway-status), `brain/generation/workspace.py`, `tests/api/test_ai_phase9.py`, `cli/validate-api.py`. Frontend: `lib/api/client.ts`, `features/ai-models/components/ai-models-page.tsx`, `features/ai-studio/components/ai-studio.tsx`, `features/ai-workspace/components/ai-content-test.tsx`, `lib/api/schema.d.ts`. Docs: this file, `openapi.v1.json`, `03-phase1.5-api-validation.md`. Tooling: `.claude/launch.json` (`omniroute` entry).
