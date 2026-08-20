-- GA4 Data API ingestion (pattern of gsc_daily): one row per date x page_path x source dimension.
-- source: 'page' (dimension pagePath) | 'landing' (dimension landingPage). Read-only analytics.readonly data.
CREATE TABLE IF NOT EXISTS ga4_daily (
  id                        INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id                   TEXT NOT NULL REFERENCES sites(site_id),
  date                      TEXT NOT NULL,
  page_path                 TEXT NOT NULL,              -- decoded path, e.g. /امداد-خودرو/
  sessions                  INTEGER NOT NULL DEFAULT 0,
  total_users               INTEGER NOT NULL DEFAULT 0,
  screen_page_views         INTEGER NOT NULL DEFAULT 0,
  engagement_rate           REAL NOT NULL DEFAULT 0,    -- 0..1
  average_session_duration  REAL NOT NULL DEFAULT 0,    -- seconds
  conversions               REAL NOT NULL DEFAULT 0,    -- key events
  source                    TEXT NOT NULL DEFAULT 'page',
  sync_run_id               TEXT,
  created_at                TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, date, page_path, source)
);
CREATE INDEX IF NOT EXISTS idx_ga4_daily_site ON ga4_daily(site_id);
CREATE INDEX IF NOT EXISTS idx_ga4_daily_date ON ga4_daily(site_id, date);
CREATE INDEX IF NOT EXISTS idx_ga4_daily_path ON ga4_daily(site_id, page_path);

-- GA4 columns join the existing content analytics snapshots (no parallel analytics table)
ALTER TABLE content_metrics ADD COLUMN ga4_sessions INTEGER;
ALTER TABLE content_metrics ADD COLUMN ga4_users INTEGER;
ALTER TABLE content_metrics ADD COLUMN ga4_views INTEGER;
ALTER TABLE content_metrics ADD COLUMN ga4_conversions REAL;
ALTER TABLE content_metrics ADD COLUMN ga4_engagement_rate REAL;
