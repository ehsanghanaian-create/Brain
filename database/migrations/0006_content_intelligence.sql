-- 0006: SEO Brain phase 7 — Content Intelligence Layer
--  content_drafts    versioned drafts (every modification = new version; previous content, change summary, author/source, AI provenance kept)
--  content_scores    quality scores per draft (7 dimensions, explainable findings)
--  content_reviews   review runs per draft (rules and/or AI — advisory)
--  content_metrics   GSC performance snapshots per published content (7d/28d windows)
--  content_insights  learned patterns (only from large samples) awaiting human confirmation → Site Brain memory
--  site_settings     per-site JSON settings (scoring weights, thresholds, review gate)

CREATE TABLE IF NOT EXISTS content_drafts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL,
  content_id      INTEGER NOT NULL REFERENCES content_items(id),
  version         INTEGER NOT NULL DEFAULT 1,
  title           TEXT,
  meta_description TEXT,
  format          TEXT NOT NULL DEFAULT 'markdown',   -- markdown | html | text
  body            TEXT NOT NULL,                      -- original body as submitted
  body_text       TEXT,                               -- plain text (derived)
  word_count      INTEGER NOT NULL DEFAULT 0,
  structure       TEXT NOT NULL DEFAULT '{}',         -- JSON: {h1[], h2[], h3[], paragraphs, links[], images[], faq, questions[]}
  source          TEXT NOT NULL DEFAULT 'user',       -- user | import | ai:<provider>
  author          TEXT,
  revision_of     INTEGER REFERENCES content_drafts(id),
  change_summary  TEXT,
  provenance      TEXT NOT NULL DEFAULT '{}',         -- JSON: {provider, model, run_id, prompt_id, applied_findings[]}
  review_status   TEXT NOT NULL DEFAULT 'none',       -- none | changes_requested | ready
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_drafts_content ON content_drafts(site_id, content_id, version);

CREATE TABLE IF NOT EXISTS content_scores (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL,
  content_id      INTEGER NOT NULL,
  draft_id        INTEGER NOT NULL REFERENCES content_drafts(id),
  total           REAL NOT NULL,
  dims            TEXT NOT NULL DEFAULT '{}',         -- JSON: {intent, keywords, entities, headings, links, cta, completeness}
  findings        TEXT NOT NULL DEFAULT '[]',         -- JSON: [{rule, dim, passed, weight, evidence, fix_fa}]
  weights         TEXT NOT NULL DEFAULT '{}',
  engine_version  TEXT NOT NULL DEFAULT 'score-v1',
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_scores_content ON content_scores(site_id, content_id);

CREATE TABLE IF NOT EXISTS content_reviews (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL,
  content_id      INTEGER NOT NULL,
  draft_id        INTEGER NOT NULL REFERENCES content_drafts(id),
  kind            TEXT NOT NULL,                      -- rules | ai
  findings        TEXT NOT NULL DEFAULT '[]',         -- JSON: [{code, severity, area, message_fa, evidence, suggestion_fa, auto_fixable}]
  summary_fa      TEXT,
  counts          TEXT NOT NULL DEFAULT '{}',         -- JSON: {high, medium, low}
  provenance      TEXT NOT NULL DEFAULT '{}',
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_reviews_content ON content_reviews(site_id, content_id);

CREATE TABLE IF NOT EXISTS content_metrics (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL,
  content_id      INTEGER NOT NULL,
  url             TEXT NOT NULL,
  window          TEXT NOT NULL,                      -- 7d | 28d
  date            TEXT NOT NULL,                      -- snapshot day (YYYY-MM-DD)
  clicks          INTEGER NOT NULL DEFAULT 0,
  impressions     INTEGER NOT NULL DEFAULT 0,
  ctr             REAL NOT NULL DEFAULT 0,
  position        REAL,
  top_queries     TEXT NOT NULL DEFAULT '[]',
  delta           TEXT NOT NULL DEFAULT '{}',         -- JSON vs previous snapshot / baseline
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (site_id, content_id, window, date)
);

CREATE TABLE IF NOT EXISTS content_insights (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL,
  category        TEXT NOT NULL,                      -- heading_structure | faq | entity_coverage | cta | local_seo | title | length
  feature         TEXT NOT NULL,
  value           TEXT NOT NULL,
  metric          TEXT NOT NULL,                      -- ctr | position | clicks
  effect          REAL NOT NULL,
  baseline        REAL,
  n               INTEGER NOT NULL,                   -- number of content items in the sample
  impressions     INTEGER NOT NULL DEFAULT 0,
  clicks          INTEGER NOT NULL DEFAULT 0,
  confidence      REAL,
  message_fa      TEXT NOT NULL,
  evidence        TEXT NOT NULL DEFAULT '{}',
  status          TEXT NOT NULL DEFAULT 'new',        -- new | accepted | dismissed
  memory_pattern_ref TEXT,                            -- set when applied to site_memory.successful_patterns
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (site_id, category, feature, value, metric)
);

CREATE TABLE IF NOT EXISTS site_settings (
  site_id         TEXT NOT NULL REFERENCES sites(site_id),
  key             TEXT NOT NULL,                      -- scoring | review_gate | analytics
  value           TEXT NOT NULL DEFAULT '{}',         -- JSON
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (site_id, key)
);

ALTER TABLE content_items ADD COLUMN current_draft_id INTEGER;
ALTER TABLE content_items ADD COLUMN latest_score REAL;
ALTER TABLE content_items ADD COLUMN review_status TEXT NOT NULL DEFAULT 'none';
