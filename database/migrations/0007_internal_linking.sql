-- 0007: SEO Brain phase 8 — Internal Link Intelligence Engine
--  link_suggestions  explainable link suggestions (source → target, anchor, score/confidence, journey, reason, evidence, status)
--  link_page_stats   per-page audit + Internal Link Health Score (0–100)
--  link_patterns     learned patterns from accept/dismiss/done (human-confirmed → Site Brain memory)
--  scope column keeps the engine future-compatible: internal | external | backlink | competitor (only 'internal' is produced now)

CREATE TABLE IF NOT EXISTS link_suggestions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL REFERENCES sites(site_id),
  scope           TEXT NOT NULL DEFAULT 'internal',    -- internal | external | backlink | competitor (future)
  kind            TEXT NOT NULL,                       -- contextual | orphan_rescue | hub_spoke | supports | anchor_fix | content_outbound
  source_node_id  TEXT NOT NULL,
  source_url      TEXT,
  source_title    TEXT,
  source_stage    TEXT,                                -- informational | commercial | service | conversion | hub | unknown
  target_node_id  TEXT NOT NULL,
  target_url      TEXT,
  target_title    TEXT,
  target_stage    TEXT,
  anchor          TEXT,
  anchor_alternatives TEXT NOT NULL DEFAULT '[]',      -- JSON list
  placement_hint  TEXT,
  score           REAL NOT NULL,
  confidence      TEXT NOT NULL,                       -- low (0.45–0.60) | recommended (0.60–0.80) | high (0.80+)
  score_breakdown TEXT NOT NULL DEFAULT '{}',          -- JSON: {topic, entities, intent, authority, anchor, journey, pattern_boost, penalties}
  reason_fa       TEXT,
  evidence        TEXT NOT NULL DEFAULT '{}',          -- JSON: {shared_entities[], cluster, queries[], inbound_body, pagerank…}
  status          TEXT NOT NULL DEFAULT 'new',         -- new | accepted | dismissed | done
  content_task_id INTEGER,                             -- Content Brain item created from this suggestion (optional)
  run_id          TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (site_id, scope, kind, source_node_id, target_node_id)
);
CREATE INDEX IF NOT EXISTS idx_link_sugg_site_status ON link_suggestions(site_id, status, score);
CREATE INDEX IF NOT EXISTS idx_link_sugg_target ON link_suggestions(site_id, target_node_id);

CREATE TABLE IF NOT EXISTS link_page_stats (
  site_id         TEXT NOT NULL,
  node_id         TEXT NOT NULL,
  url             TEXT,
  title           TEXT,
  stage           TEXT,
  inbound_total   INTEGER NOT NULL DEFAULT 0,
  inbound_body    INTEGER NOT NULL DEFAULT 0,
  inbound_nav_only INTEGER NOT NULL DEFAULT 0,
  unique_sources  INTEGER NOT NULL DEFAULT 0,
  outbound_body   INTEGER NOT NULL DEFAULT 0,
  outbound_total  INTEGER NOT NULL DEFAULT 0,
  anchor_distribution TEXT NOT NULL DEFAULT '[]',      -- JSON: [{anchor, count}]
  exact_match_ratio REAL NOT NULL DEFAULT 0,
  generic_ratio   REAL NOT NULL DEFAULT 0,
  flags           TEXT NOT NULL DEFAULT '[]',          -- JSON list: orphan | nav_only_inbound | low_inbound | single_source | generic_anchors | over_optimized_anchor | no_outbound_body | links_to_noindex | too_many_outbound
  pagerank        REAL,
  health_score    REAL NOT NULL DEFAULT 0,             -- Internal Link Health Score 0–100
  health_breakdown TEXT NOT NULL DEFAULT '{}',         -- JSON: {inbound_contextual, outbound_balance, anchor_diversity, orphan_risk, authority}
  computed_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (site_id, node_id)
);

CREATE TABLE IF NOT EXISTS link_patterns (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL,
  pattern_key     TEXT NOT NULL,                       -- e.g. journey:informational>service|anchor:entity
  feature         TEXT NOT NULL DEFAULT '{}',          -- JSON: {source_stage, target_stage, top_component, anchor_style, entity_type}
  accepted        INTEGER NOT NULL DEFAULT 0,
  dismissed       INTEGER NOT NULL DEFAULT 0,
  done            INTEGER NOT NULL DEFAULT 0,
  acceptance_rate REAL NOT NULL DEFAULT 0,
  message_fa      TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'new',         -- new | accepted | dismissed
  memory_pattern_ref TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (site_id, pattern_key)
);
