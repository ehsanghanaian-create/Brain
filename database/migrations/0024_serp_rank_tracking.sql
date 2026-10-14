-- Daily, independently observed organic SERP positions. Never populated from GSC averages.
CREATE TABLE IF NOT EXISTS serp_rank_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  local_date TEXT NOT NULL,
  timezone TEXT NOT NULL,
  provider TEXT NOT NULL,
  market TEXT NOT NULL,
  language TEXT NOT NULL,
  device TEXT NOT NULL,
  requested_depth INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  keywords_total INTEGER NOT NULL DEFAULT 0,
  keywords_checked INTEGER NOT NULL DEFAULT 0,
  keywords_failed INTEGER NOT NULL DEFAULT 0,
  provider_requests INTEGER NOT NULL DEFAULT 0,
  started_at TEXT,
  finished_at TEXT,
  error_code TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, local_date)
);
CREATE INDEX IF NOT EXISTS idx_serp_rank_runs_site_date ON serp_rank_runs(site_id, local_date DESC);

CREATE TABLE IF NOT EXISTS serp_rank_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL REFERENCES serp_rank_runs(id) ON DELETE CASCADE,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  keyword_id INTEGER NOT NULL REFERENCES keywords(id),
  keyword TEXT NOT NULL,
  status TEXT NOT NULL, -- found | not_found_in_results | provider_error
  organic_position INTEGER,
  absolute_position INTEGER,
  ranking_url TEXT,
  target_url TEXT,
  returned_organic_count INTEGER NOT NULL DEFAULT 0,
  competitors_json TEXT NOT NULL DEFAULT '[]',
  provider_task_id TEXT,
  error_code TEXT,
  checked_at TEXT NOT NULL,
  UNIQUE(run_id, keyword_id)
);
CREATE INDEX IF NOT EXISTS idx_serp_rank_observations_keyword ON serp_rank_observations(site_id, keyword_id, checked_at DESC);
