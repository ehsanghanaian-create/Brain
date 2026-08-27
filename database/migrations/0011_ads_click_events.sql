CREATE TABLE IF NOT EXISTS ads_click_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_uuid TEXT NOT NULL UNIQUE,
    site_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at_client TEXT,
    received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ip_address TEXT NOT NULL,
    ip_hash TEXT NOT NULL,
    ip_prefix TEXT,
    ip_source TEXT,
    visitor_id TEXT,
    session_id TEXT,
    gclid TEXT,
    gbraid TEXT,
    wbraid TEXT,
    campaign_id TEXT,
    ad_group_id TEXT,
    creative_id TEXT,
    keyword TEXT,
    match_type TEXT,
    device TEXT,
    network TEXT,
    utm_source TEXT,
    utm_medium TEXT,
    utm_campaign TEXT,
    utm_term TEXT,
    utm_content TEXT,
    landing_path TEXT,
    page_path TEXT,
    referrer TEXT,
    user_agent TEXT,
    browser_language TEXT,
    browser_timezone TEXT,
    screen_size TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ads_events_received ON ads_click_events(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_ads_events_site_received ON ads_click_events(site_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_ads_events_ip_received ON ads_click_events(ip_hash, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_ads_events_session ON ads_click_events(session_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_ads_events_visitor ON ads_click_events(visitor_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_ads_events_gclid ON ads_click_events(gclid, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_ads_events_type_received ON ads_click_events(event_type, received_at DESC);

