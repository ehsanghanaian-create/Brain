-- 0005: SEO Brain phase 6 — Content Brain foundation + AI provider management
--  content_items    content entities (planned → brief_ready → writing → review → approved → published)
--  content_events   status transitions / notes (audit trail; human approval workflow)
--  content_briefs   structured briefs (versioned) generated from keyword + cluster + GSC + graph
--  ai_providers     provider configurations (secrets live in the SecretStore, only a reference is stored)
--  ai_routes        task kind → provider/model (+ fallback)

CREATE TABLE IF NOT EXISTS content_items (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL REFERENCES sites(site_id),
  title           TEXT NOT NULL,
  slug            TEXT,
  target_keyword_id INTEGER REFERENCES keywords(id),
  target_keyword  TEXT,
  topic           TEXT,
  cluster_id      TEXT,
  intent          TEXT,
  status          TEXT NOT NULL DEFAULT 'planned',   -- planned | brief_ready | writing | review | approved | published
  priority        TEXT,                              -- high | medium | low
  publish_date    TEXT,                              -- YYYY-MM-DD (site timezone)
  publish_time    TEXT,                              -- HH:MM
  ai_provider     TEXT,                              -- provider config name/kind used for generation (informational)
  ai_model        TEXT,
  url             TEXT,                              -- final URL once published
  wp_post_id      INTEGER,
  brief_id        INTEGER,                           -- current brief
  metadata        TEXT NOT NULL DEFAULT '{}',        -- JSON: h1, seo_title, meta_description, word_count, opportunity_id, source…
  notes           TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_content_site_status ON content_items(site_id, status);
CREATE INDEX IF NOT EXISTS idx_content_site_date ON content_items(site_id, publish_date);

CREATE TABLE IF NOT EXISTS content_events (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL,
  content_id      INTEGER NOT NULL REFERENCES content_items(id),
  from_status     TEXT,
  to_status       TEXT,
  actor           TEXT NOT NULL DEFAULT 'user',      -- user | system | ai:<provider>
  note            TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_content_events ON content_events(site_id, content_id);

CREATE TABLE IF NOT EXISTS content_briefs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL,
  content_id      INTEGER NOT NULL REFERENCES content_items(id),
  version         INTEGER NOT NULL DEFAULT 1,
  h1              TEXT,
  seo_title       TEXT,
  meta_description TEXT,
  intent          TEXT,
  outline         TEXT NOT NULL DEFAULT '[]',        -- JSON: [{h2, h3:[], why}]
  entities        TEXT NOT NULL DEFAULT '[]',        -- JSON: [{type, label, node_id}]
  questions       TEXT NOT NULL DEFAULT '[]',        -- JSON: [{question, source}]
  internal_links  TEXT NOT NULL DEFAULT '[]',        -- JSON: [{url, anchor, reason, node_id}]
  sources         TEXT NOT NULL DEFAULT '{}',        -- JSON: {keyword, cluster, gsc, existing_pages, competitors, opportunities}
  markdown        TEXT,
  provenance      TEXT NOT NULL DEFAULT '{}',        -- JSON: {generator, provider, model, run_id, ai_used}
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_briefs_content ON content_briefs(site_id, content_id);

CREATE TABLE IF NOT EXISTS ai_providers (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT NOT NULL UNIQUE,              -- user label, also the provider name in the router
  kind            TEXT NOT NULL,                     -- anthropic | openai | google | openrouter | ollama | custom
  base_url        TEXT,
  default_model   TEXT,
  models          TEXT NOT NULL DEFAULT '[]',        -- JSON list
  enabled         INTEGER NOT NULL DEFAULT 1,
  secret_ref      TEXT,                              -- SecretStore reference (never the key)
  key_hint        TEXT,                              -- last 4 chars for the UI
  last_test       TEXT,                              -- JSON: {ok, message, tested_at, models_found}
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS ai_routes (
  task_kind       TEXT NOT NULL,                     -- content_writing | seo_analysis | research | brief | keyword_analysis | internal_linking | schema | generic
  site_id         TEXT NOT NULL DEFAULT '*',         -- '*' = global default
  provider_id     INTEGER REFERENCES ai_providers(id),
  model           TEXT,
  fallback_provider_id INTEGER REFERENCES ai_providers(id),
  fallback_model  TEXT,
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (task_kind, site_id)
);
