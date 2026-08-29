CREATE TABLE IF NOT EXISTS google_ads_ip_exclusions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_uuid TEXT NOT NULL UNIQUE,
    site_id TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    ip_hash TEXT NOT NULL,
    customer_id TEXT,
    source TEXT NOT NULL DEFAULT 'dashboard_manual',
    status TEXT NOT NULL,
    risk_score INTEGER NOT NULL DEFAULT 0,
    risk_reasons_json TEXT NOT NULL DEFAULT '[]',
    google_resource_name TEXT,
    google_request_id TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_ads_ip_exclusions_site_created
ON google_ads_ip_exclusions(site_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ads_ip_exclusions_ip_created
ON google_ads_ip_exclusions(ip_hash, created_at DESC);

