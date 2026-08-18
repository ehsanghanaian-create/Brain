-- 0008: SEO Brain phase 9 — AI Content Generation & Agent Orchestration
--  ai_models            model catalog (per provider): tier, tags, context, prices, enabled
--  ai_calls             usage ledger for every gateway call (tokens, cost, latency, attempts, route reason, prompt refs)
--  ai_provider_health   rolling failure counters / circuit breaker state per provider
--  memory_snapshots     immutable MemoryPack snapshots (what the AI was told about the site) — referenced by runs
--  prompts / prompt_versions / prompt_tests   DB-versioned prompt library (activation + approval + performance)
--  generation_runs / generation_artifacts     section-by-section pipeline runs with checkpoints + per-agent outputs
--  draft_feedback       human rating 1–5 + tags on drafts / runs (learning signal)
--  ai_insights          learned AI performance patterns (recommendation only; never applied automatically)
--  ai_routes            + fallbacks (ordered list) + policy (explicit | auto)

CREATE TABLE IF NOT EXISTS ai_models (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_id     INTEGER NOT NULL REFERENCES ai_providers(id),
  model_id        TEXT NOT NULL,
  display         TEXT,
  tier            TEXT NOT NULL DEFAULT 'balanced',     -- fast | balanced | quality | reasoning
  tags            TEXT NOT NULL DEFAULT '[]',           -- JSON: persian, long_form, reasoning, cheap, translation, json, local
  context_tokens  INTEGER,
  price_in_per_m  REAL NOT NULL DEFAULT 0,              -- USD per 1M input tokens
  price_out_per_m REAL NOT NULL DEFAULT 0,
  enabled         INTEGER NOT NULL DEFAULT 1,
  source          TEXT NOT NULL DEFAULT 'catalog',      -- catalog | discovered | user
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (provider_id, model_id)
);

CREATE TABLE IF NOT EXISTS ai_calls (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT,
  run_id          TEXT,
  content_id      INTEGER,
  agent           TEXT,
  task_kind       TEXT NOT NULL,
  provider        TEXT NOT NULL,
  model           TEXT NOT NULL,
  prompt_refs     TEXT NOT NULL DEFAULT '{}',           -- JSON: {system: "key@v", site: "key@v", agent: "key@v"}
  memory_snapshot_id INTEGER,
  input_tokens    INTEGER NOT NULL DEFAULT 0,
  output_tokens   INTEGER NOT NULL DEFAULT 0,
  cost_usd        REAL NOT NULL DEFAULT 0,
  latency_ms      INTEGER NOT NULL DEFAULT 0,
  ok              INTEGER NOT NULL DEFAULT 1,
  error           TEXT,
  attempts        TEXT NOT NULL DEFAULT '[]',           -- JSON: [{provider, model, ok, error, latency_ms}]
  route_reason    TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_ai_calls_site_date ON ai_calls(site_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_calls_run ON ai_calls(run_id);

CREATE TABLE IF NOT EXISTS ai_provider_health (
  provider        TEXT PRIMARY KEY,
  calls           INTEGER NOT NULL DEFAULT 0,
  failures        INTEGER NOT NULL DEFAULT 0,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  p50_ms          INTEGER,
  breaker_open_until TEXT,
  last_error      TEXT,
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS memory_snapshots (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL,
  hash            TEXT NOT NULL,
  pack            TEXT NOT NULL,                        -- JSON MemoryPack
  rendered        TEXT NOT NULL,                        -- the exact Persian text injected into prompts
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (site_id, hash)
);

CREATE TABLE IF NOT EXISTS prompts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  key             TEXT NOT NULL,                        -- system.base | site.brain | agent.research | agent.outline | agent.writer_section | agent.fact_check | agent.seo | agent.linking | agent.reviewer | task.rewrite | task.title_meta | task.translation
  scope           TEXT NOT NULL,                        -- system | site | agent | task
  site_id         TEXT,                                 -- NULL = global; site override when set
  title           TEXT NOT NULL,
  description     TEXT,
  tags            TEXT NOT NULL DEFAULT '[]',
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (key, site_id)
);

CREATE TABLE IF NOT EXISTS prompt_versions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  prompt_id       INTEGER NOT NULL REFERENCES prompts(id),
  version         INTEGER NOT NULL,
  template        TEXT NOT NULL,                        -- {{variable}} placeholders; agent/task templates must contain {{memory_pack}}
  variables       TEXT NOT NULL DEFAULT '[]',           -- JSON: [{name, required, description}]
  model_hints     TEXT NOT NULL DEFAULT '{}',           -- JSON: {tier, temperature, max_tokens}
  is_active       INTEGER NOT NULL DEFAULT 0,
  approval        TEXT NOT NULL DEFAULT 'draft',        -- draft | approved | retired
  approved_by     TEXT,
  approved_at     TEXT,
  changelog       TEXT,
  created_by      TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (prompt_id, version)
);

CREATE TABLE IF NOT EXISTS prompt_tests (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  prompt_version_id INTEGER NOT NULL REFERENCES prompt_versions(id),
  site_id         TEXT,
  content_id      INTEGER,
  model           TEXT,
  provider        TEXT,
  input_ref       TEXT,
  output          TEXT,
  score           REAL,                                 -- Phase 7 scoring when the output is a draft
  input_tokens    INTEGER, output_tokens INTEGER, cost_usd REAL, latency_ms INTEGER,
  human_rating    INTEGER,                              -- 1–5
  notes           TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS generation_runs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id          TEXT NOT NULL UNIQUE,                 -- gen-<hex>; also used as job run id and SSE topic
  site_id         TEXT NOT NULL,
  content_id      INTEGER NOT NULL,
  mode            TEXT NOT NULL,                        -- manual | assisted   (autopilot reserved)
  status          TEXT NOT NULL DEFAULT 'queued',       -- queued | running | paused | succeeded | failed | cancelled
  step            TEXT,                                 -- current/last step key
  steps           TEXT NOT NULL DEFAULT '[]',           -- JSON: [{key, agent, status, artifact_id, provenance, started_at, finished_at, error}]
  models          TEXT NOT NULL DEFAULT '{}',           -- JSON: {agent: {provider, model}} chosen/overridden
  prompt_versions TEXT NOT NULL DEFAULT '{}',           -- JSON: {agent: prompt_version_id}
  memory_snapshot_id INTEGER,
  estimate        TEXT NOT NULL DEFAULT '{}',           -- JSON: {input_tokens, output_tokens, cost_usd, per_agent}
  actual          TEXT NOT NULL DEFAULT '{}',           -- JSON: {input_tokens, output_tokens, cost_usd, latency_ms}
  draft_id        INTEGER,                              -- resulting draft version (assisted or after human click)
  score           REAL,
  review_status   TEXT,
  error           TEXT,
  created_by      TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_gen_runs_site ON generation_runs(site_id, content_id);

CREATE TABLE IF NOT EXISTS generation_artifacts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id          TEXT NOT NULL,
  step            TEXT NOT NULL,                        -- research | outline | section:<n> | fact_check | assembly | seo | linking | review
  agent           TEXT NOT NULL,
  version         INTEGER NOT NULL DEFAULT 1,
  schema_key      TEXT,
  payload         TEXT NOT NULL,                        -- JSON output validated against the agent schema
  provenance      TEXT NOT NULL DEFAULT '{}',           -- JSON: {provider, model, prompt_version_id, memory_snapshot_id, input_tokens, output_tokens, cost_usd, latency_ms, call_id}
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_gen_artifacts_run ON generation_artifacts(run_id, step);

CREATE TABLE IF NOT EXISTS draft_feedback (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL,
  content_id      INTEGER,
  draft_id        INTEGER,
  run_id          TEXT,
  rating          INTEGER NOT NULL,                     -- 1–5
  tags            TEXT NOT NULL DEFAULT '[]',           -- JSON: good_structure | weak_intro | wrong_intent | too_generic | excellent_entities | good_links
  notes           TEXT,
  created_by      TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS ai_insights (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT,                                 -- NULL = global
  category        TEXT NOT NULL,                        -- model | prompt | structure
  feature         TEXT NOT NULL,
  value           TEXT NOT NULL,
  metric          TEXT NOT NULL,                        -- score | cost | rating | revisions | ctr | position
  effect          REAL NOT NULL,
  baseline        REAL,
  n               INTEGER NOT NULL,
  confidence      REAL,
  message_fa      TEXT NOT NULL,
  evidence        TEXT NOT NULL DEFAULT '{}',
  recommendation  TEXT NOT NULL DEFAULT '{}',           -- JSON: e.g. {task_kind, provider, model} — a *suggested* route (never applied automatically)
  status          TEXT NOT NULL DEFAULT 'new',          -- new | accepted | dismissed
  memory_pattern_ref TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (site_id, category, feature, value, metric)
);

ALTER TABLE ai_routes ADD COLUMN fallbacks TEXT NOT NULL DEFAULT '[]';   -- JSON: [{provider_id, model}]
ALTER TABLE ai_routes ADD COLUMN policy TEXT NOT NULL DEFAULT 'auto';    -- explicit | auto
