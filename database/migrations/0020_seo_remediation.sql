CREATE TABLE IF NOT EXISTS seo_remediation_proposals (
  id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  issue_key TEXT NOT NULL,
  problem_type TEXT NOT NULL,
  url TEXT NOT NULL,
  related_url TEXT NOT NULL DEFAULT '',
  evidence_hash TEXT NOT NULL,
  evidence TEXT NOT NULL,
  methods TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ready',
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_seo_remediation_proposals_issue
ON seo_remediation_proposals(site_id, issue_key, created_at DESC);

CREATE TABLE IF NOT EXISTS seo_remediation_runs (
  id TEXT PRIMARY KEY,
  proposal_id TEXT NOT NULL REFERENCES seo_remediation_proposals(id),
  site_id TEXT NOT NULL,
  issue_key TEXT NOT NULL,
  method_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  status TEXT NOT NULL,
  job_id TEXT,
  before_snapshot TEXT,
  after_snapshot TEXT,
  verification TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(site_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_seo_remediation_runs_issue
ON seo_remediation_runs(site_id, issue_key, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_seo_remediation_one_active_per_site
ON seo_remediation_runs(site_id) WHERE status IN ('queued', 'running');

CREATE TABLE IF NOT EXISTS seo_remediation_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES seo_remediation_runs(id),
  event_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_seo_remediation_events_run
ON seo_remediation_events(run_id, created_at);
