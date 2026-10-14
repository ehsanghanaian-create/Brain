-- Evidence-led AI search pilot. GA4 acquisition source is deliberately separate
-- from ga4_daily.source ('page' or 'landing'). No synthetic zeroes for sales.
CREATE TABLE IF NOT EXISTS ga4_ai_referrals_daily (
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  date TEXT NOT NULL,
  landing_page TEXT NOT NULL,
  session_source TEXT NOT NULL,
  session_medium TEXT NOT NULL,
  platform TEXT NOT NULL,
  sessions INTEGER NOT NULL,
  engaged_sessions INTEGER NOT NULL,
  transactions REAL,
  purchase_revenue REAL,
  currency TEXT,
  sync_run_id TEXT NOT NULL,
  PRIMARY KEY (site_id,date,landing_page,session_source,session_medium)
);
CREATE INDEX IF NOT EXISTS idx_ga4_ai_referrals_site_date ON ga4_ai_referrals_daily(site_id,date,platform);

CREATE TABLE IF NOT EXISTS ai_visibility_prompts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  question TEXT NOT NULL,
  topic TEXT NOT NULL DEFAULT '',
  target_url TEXT NOT NULL DEFAULT '',
  intent TEXT NOT NULL DEFAULT 'commercial' CHECK(intent IN ('informational','commercial','transactional')),
  locale TEXT NOT NULL DEFAULT 'fa-IR',
  market TEXT NOT NULL DEFAULT 'IR',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(site_id,question,locale,market)
);
CREATE INDEX IF NOT EXISTS idx_ai_visibility_prompts_site ON ai_visibility_prompts(site_id,active,topic);

CREATE TABLE IF NOT EXISTS ai_visibility_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  prompt_id INTEGER NOT NULL REFERENCES ai_visibility_prompts(id),
  provider TEXT NOT NULL,
  model TEXT NOT NULL DEFAULT '',
  observed_at TEXT NOT NULL,
  capture_method TEXT NOT NULL CHECK(capture_method IN ('manual','provider_api')),
  answer_text TEXT NOT NULL,
  brand_mentioned INTEGER CHECK(brand_mentioned IN (0,1)),
  mention_method TEXT NOT NULL DEFAULT 'manual',
  competitors_json TEXT NOT NULL DEFAULT '[]',
  run_status TEXT NOT NULL DEFAULT 'complete' CHECK(run_status IN ('complete','partial')),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_visibility_observations_site ON ai_visibility_observations(site_id,observed_at,provider);
CREATE INDEX IF NOT EXISTS idx_ai_visibility_observations_prompt ON ai_visibility_observations(prompt_id,observed_at);

CREATE TABLE IF NOT EXISTS ai_visibility_citations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  observation_id INTEGER NOT NULL REFERENCES ai_visibility_observations(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  domain TEXT NOT NULL,
  citation_kind TEXT NOT NULL DEFAULT 'source' CHECK(citation_kind IN ('inline','source','other')),
  position INTEGER,
  is_own_domain INTEGER NOT NULL DEFAULT 0 CHECK(is_own_domain IN (0,1)),
  UNIQUE(observation_id,url,citation_kind)
);
CREATE INDEX IF NOT EXISTS idx_ai_visibility_citations_observation ON ai_visibility_citations(observation_id);

-- Official console observations are imported, never inferred from prompt probes.
CREATE TABLE IF NOT EXISTS ai_visibility_official_daily (
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  date TEXT NOT NULL,
  platform TEXT NOT NULL CHECK(platform IN ('google_ai_search','google_ai_discover','bing_ai')),
  page_url TEXT NOT NULL DEFAULT '',
  impressions INTEGER,
  citations INTEGER,
  source_label TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  PRIMARY KEY(site_id,date,platform,page_url)
);
CREATE INDEX IF NOT EXISTS idx_ai_visibility_official_site_date ON ai_visibility_official_daily(site_id,date,platform);
