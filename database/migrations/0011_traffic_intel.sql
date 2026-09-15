-- 0011: Traffic Intel — first-party visit tracking (phase 1 of the organic-intel feature).
--  track_keys      per-site public write key + the daily-rotated hashing secret for visitor ids
--  track_sessions  one row per stitched visit (cookieless: daily hash of key+ip+ua, 30-minute inactivity window)
--  track_events    the raw hit stream: pageview / scroll / click / tel_click / form_submit / engaged / exit
-- Search Console data is NOT duplicated here: the organic-entry views join these tables to the existing gsc_daily.
CREATE TABLE IF NOT EXISTS track_keys (
  site_id       TEXT PRIMARY KEY REFERENCES sites(site_id),
  write_key     TEXT NOT NULL UNIQUE,       -- public, site-scoped, write-only; identifies the site, not a secret
  hash_secret   TEXT NOT NULL,              -- server-only; salts the daily visitor hash so ids cannot be reversed
  enabled       INTEGER NOT NULL DEFAULT 1,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  rotated_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_track_keys_key ON track_keys(write_key);

CREATE TABLE IF NOT EXISTS track_sessions (
  session_id      TEXT PRIMARY KEY,
  site_id         TEXT NOT NULL REFERENCES sites(site_id),
  visitor_id      TEXT NOT NULL,              -- daily hash; changes every day by design, never joins across days
  day             TEXT NOT NULL,              -- YYYY-MM-DD in UTC, the grouping key for every report
  started_at      TEXT NOT NULL,
  last_seen_at    TEXT NOT NULL,
  landing_path    TEXT NOT NULL DEFAULT '/',
  exit_path       TEXT NOT NULL DEFAULT '',
  referrer_host   TEXT NOT NULL DEFAULT '',
  channel         TEXT NOT NULL DEFAULT 'direct',   -- organic | paid | referral | social | direct
  search_engine   TEXT NOT NULL DEFAULT '',         -- google | bing | zarebin | yooz | ... ('' when not a search engine)
  utm_source      TEXT NOT NULL DEFAULT '',
  utm_medium      TEXT NOT NULL DEFAULT '',
  utm_campaign    TEXT NOT NULL DEFAULT '',
  utm_term        TEXT NOT NULL DEFAULT '',
  gclid           TEXT NOT NULL DEFAULT '',         -- the only exact keyword bridge that exists (paid only)
  device          TEXT NOT NULL DEFAULT 'desktop',  -- mobile | tablet | desktop
  country         TEXT NOT NULL DEFAULT '',
  pages_count     INTEGER NOT NULL DEFAULT 0,
  events_count    INTEGER NOT NULL DEFAULT 0,
  max_scroll      INTEGER NOT NULL DEFAULT 0,       -- 0..100
  duration_s      INTEGER NOT NULL DEFAULT 0,
  converted_at    TEXT,
  conversion_type TEXT,                             -- tel_click | form_submit (intent to call, not a completed call)
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_track_sessions_site_day ON track_sessions(site_id, day);
CREATE INDEX IF NOT EXISTS idx_track_sessions_visitor ON track_sessions(site_id, visitor_id, last_seen_at);
CREATE INDEX IF NOT EXISTS idx_track_sessions_landing ON track_sessions(site_id, landing_path);
CREATE INDEX IF NOT EXISTS idx_track_sessions_channel ON track_sessions(site_id, channel, day);
CREATE INDEX IF NOT EXISTS idx_track_sessions_conv ON track_sessions(site_id, conversion_type, day);

CREATE TABLE IF NOT EXISTS track_events (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  session_id    TEXT NOT NULL REFERENCES track_sessions(session_id),
  day           TEXT NOT NULL,
  ts            TEXT NOT NULL,
  type          TEXT NOT NULL,              -- pageview | scroll | click | tel_click | form_submit | engaged | exit
  path          TEXT NOT NULL DEFAULT '/',
  label         TEXT NOT NULL DEFAULT '',   -- selector path, tel: number, or form id
  value         REAL,                       -- scroll depth 0..100, engaged seconds
  pos_x         REAL,                       -- click position, normalized 0..1 of viewport width
  pos_y         REAL,                       -- click position, normalized 0..1 of full document height
  meta          TEXT NOT NULL DEFAULT '{}',
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_track_events_site_day ON track_events(site_id, day);
CREATE INDEX IF NOT EXISTS idx_track_events_type ON track_events(site_id, type, day);
CREATE INDEX IF NOT EXISTS idx_track_events_session ON track_events(session_id);
CREATE INDEX IF NOT EXISTS idx_track_events_path ON track_events(site_id, path, type);
