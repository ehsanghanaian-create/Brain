-- Durable case history beside the replaceable seo_problems read model.
CREATE TABLE IF NOT EXISTS issue_cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  fingerprint TEXT NOT NULL UNIQUE,
  problem_type TEXT NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  related_url TEXT NOT NULL DEFAULT '',
  severity TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved')),
  detail TEXT,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  last_run_id TEXT,
  seen_count INTEGER NOT NULL DEFAULT 1,
  resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_issue_cases_site_status ON issue_cases(site_id,status,severity,last_seen);
CREATE TABLE IF NOT EXISTS issue_case_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  case_id INTEGER NOT NULL REFERENCES issue_cases(id),
  run_id TEXT NOT NULL,
  severity TEXT NOT NULL,
  detail TEXT,
  observed_at TEXT NOT NULL,
  UNIQUE(case_id,run_id)
);
CREATE INDEX IF NOT EXISTS idx_issue_case_observations_case ON issue_case_observations(case_id,observed_at);
CREATE TABLE IF NOT EXISTS issue_case_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  case_id INTEGER NOT NULL REFERENCES issue_cases(id),
  run_id TEXT,
  event_type TEXT NOT NULL CHECK(event_type IN ('opened','reopened','resolved')),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_issue_case_events_case ON issue_case_events(case_id,created_at);
-- Adopt the current snapshot on migration; older history cannot be reconstructed.
INSERT OR IGNORE INTO issue_cases(site_id,fingerprint,problem_type,url,related_url,severity,detail,first_seen,last_seen,last_run_id)
SELECT site_id,site_id||char(31)||problem_type||char(31)||COALESCE(url,'')||char(31)||COALESCE(related_url,''),
       problem_type,COALESCE(url,''),COALESCE(related_url,''),severity,detail,created_at,created_at,run_id
FROM seo_problems;
INSERT OR IGNORE INTO issue_case_observations(site_id,case_id,run_id,severity,detail,observed_at)
SELECT p.site_id,c.id,COALESCE(p.run_id,'legacy:'||p.id),p.severity,p.detail,p.created_at
FROM seo_problems p JOIN issue_cases c ON c.fingerprint=p.site_id||char(31)||p.problem_type||char(31)||COALESCE(p.url,'')||char(31)||COALESCE(p.related_url,'');
INSERT INTO issue_case_events(site_id,case_id,run_id,event_type,created_at)
SELECT c.site_id,c.id,c.last_run_id,'opened',c.first_seen FROM issue_cases c
WHERE NOT EXISTS (SELECT 1 FROM issue_case_events e WHERE e.case_id=c.id AND e.event_type='opened');
