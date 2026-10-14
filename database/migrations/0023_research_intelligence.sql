-- Competitor URLs are explicit research targets. Store bounded page metadata,
-- not copied article bodies or inferred search rankings.
CREATE TABLE IF NOT EXISTS research_competitor_pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  url TEXT NOT NULL,
  focus_query TEXT NOT NULL DEFAULT '',
  own_url TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','queued','ready','error')),
  http_status INTEGER,
  title TEXT NOT NULL DEFAULT '',
  meta_description TEXT NOT NULL DEFAULT '',
  h1_json TEXT NOT NULL DEFAULT '[]',
  h2_json TEXT NOT NULL DEFAULT '[]',
  canonical TEXT NOT NULL DEFAULT '',
  word_count INTEGER,
  error_code TEXT NOT NULL DEFAULT '',
  last_requested_at TEXT,
  last_checked_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(site_id,url)
);
CREATE INDEX IF NOT EXISTS idx_research_competitors_due
  ON research_competitor_pages(status,last_checked_at,last_requested_at);
