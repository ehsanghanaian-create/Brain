-- Property-level Search Console observations. Page/query rows remain a separate drill-down.
CREATE TABLE IF NOT EXISTS gsc_property_daily (
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    date TEXT NOT NULL,
    search_type TEXT NOT NULL DEFAULT 'web',
    property TEXT NOT NULL,
    clicks INTEGER NOT NULL,
    impressions INTEGER NOT NULL,
    position REAL,
    sync_run_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (site_id, date, search_type)
);
CREATE INDEX IF NOT EXISTS idx_gsc_property_daily_site_date ON gsc_property_daily(site_id, date);

-- GA4 site totals are fetched without a page dimension. The empty channel is the all-channel total.
CREATE TABLE IF NOT EXISTS ga4_site_daily (
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    date TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT '',
    property_id TEXT NOT NULL,
    sessions INTEGER NOT NULL,
    total_users INTEGER NOT NULL,
    conversions REAL NOT NULL,
    sync_run_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (site_id, date, channel)
);
CREATE INDEX IF NOT EXISTS idx_ga4_site_daily_site_date ON ga4_site_daily(site_id, date);
