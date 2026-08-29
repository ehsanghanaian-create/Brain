-- 0014: graph-derived Content Knowledge Pack + durable content automation

CREATE TABLE IF NOT EXISTS content_knowledge_packs (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id        TEXT NOT NULL REFERENCES sites(site_id),
  version        INTEGER NOT NULL,
  hash           TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'ready',
  pack           TEXT NOT NULL DEFAULT '{}',
  rendered       TEXT NOT NULL,
  source_counts  TEXT NOT NULL DEFAULT '{}',
  warnings       TEXT NOT NULL DEFAULT '[]',
  created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, hash)
);
CREATE INDEX IF NOT EXISTS idx_ckp_site_version ON content_knowledge_packs(site_id, version DESC);

ALTER TABLE content_plan_generation_jobs ADD COLUMN scheduled_at TEXT;
ALTER TABLE content_plan_generation_jobs ADD COLUMN publish_at TEXT;
ALTER TABLE content_plan_generation_jobs ADD COLUMN publish_action TEXT NOT NULL DEFAULT 'none';
ALTER TABLE content_plan_generation_jobs ADD COLUMN approval_mode TEXT NOT NULL DEFAULT 'human';
ALTER TABLE content_plan_generation_jobs ADD COLUMN category_ids TEXT NOT NULL DEFAULT '[]';
ALTER TABLE content_plan_generation_jobs ADD COLUMN min_score REAL NOT NULL DEFAULT 85;
ALTER TABLE content_plan_generation_jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE content_plan_generation_jobs ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3;
ALTER TABLE content_plan_generation_jobs ADD COLUMN queue_run_id TEXT;
ALTER TABLE content_plan_generation_jobs ADD COLUMN last_error TEXT;
ALTER TABLE content_plan_generation_jobs ADD COLUMN started_at TEXT;
ALTER TABLE content_plan_generation_jobs ADD COLUMN finished_at TEXT;

CREATE INDEX IF NOT EXISTS idx_cpgj_due ON content_plan_generation_jobs(status, scheduled_at);
