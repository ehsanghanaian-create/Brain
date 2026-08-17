-- 0004: SEO Brain phase 5 — Keyword Intelligence
--  keywords            imported / managed keywords (one row per normalized keyword per site)
--  keyword_clusters    clusters (topics) produced by clustering or set by hand
--  keyword_imports     import runs (file, mapping, counts, errors) — audit trail
--  keyword_opportunities  rule-based opportunities derived from keywords + GSC + graph (explainable)

CREATE TABLE IF NOT EXISTS keyword_clusters (
  cluster_id    TEXT NOT NULL,                -- e.g. c-<hash>
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  name          TEXT NOT NULL,                -- representative keyword
  topic         TEXT,                         -- human topic label (editable)
  keywords_count INTEGER NOT NULL DEFAULT 0,
  method        TEXT,                         -- token_jaccard | manual
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (site_id, cluster_id)
);

CREATE TABLE IF NOT EXISTS keywords (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  keyword       TEXT NOT NULL,                -- as entered
  normalized    TEXT NOT NULL,                -- Persian/Arabic-normalized, lower, single-spaced
  intent        TEXT,                         -- informational | navigational | commercial | transactional | local
  cluster_id    TEXT,
  topic         TEXT,
  volume        INTEGER,
  difficulty    REAL,
  priority      TEXT,                         -- high | medium | low
  target_url    TEXT,
  status        TEXT NOT NULL DEFAULT 'new',  -- new | planned | in_progress | published | ignored
  source        TEXT,                         -- import:<file> | manual | gsc
  notes         TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (site_id, normalized)
);
CREATE INDEX IF NOT EXISTS idx_keywords_site_cluster ON keywords(site_id, cluster_id);
CREATE INDEX IF NOT EXISTS idx_keywords_site_status ON keywords(site_id, status);

CREATE TABLE IF NOT EXISTS keyword_imports (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  filename      TEXT,
  format        TEXT,                         -- csv | tsv | xlsx | sheet
  rows_total    INTEGER NOT NULL DEFAULT 0,
  rows_imported INTEGER NOT NULL DEFAULT 0,
  rows_updated  INTEGER NOT NULL DEFAULT 0,
  rows_skipped  INTEGER NOT NULL DEFAULT 0,
  mapping       TEXT,                         -- JSON: {source_column: field}
  errors        TEXT,                         -- JSON: [{row, error}]
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS keyword_opportunities (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  keyword_id    INTEGER NOT NULL REFERENCES keywords(id),
  kind          TEXT NOT NULL,                -- improve_page | create_content | update_title | add_internal_links
  target_url    TEXT,
  score         REAL NOT NULL DEFAULT 0,
  reason        TEXT,                         -- Persian, explainable
  evidence      TEXT,                         -- JSON: metrics used
  status        TEXT NOT NULL DEFAULT 'new',  -- new | accepted | dismissed | done
  run_id        TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (site_id, keyword_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_kw_opps_site_kind ON keyword_opportunities(site_id, kind, status);
