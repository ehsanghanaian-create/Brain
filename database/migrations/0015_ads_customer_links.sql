CREATE TABLE IF NOT EXISTS ads_customer_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL,
    customer_key TEXT NOT NULL,
    visitor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    first_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(site_id, customer_key, visitor_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_ads_customer_links_site_customer
ON ads_customer_links(site_id, customer_key, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_ads_customer_links_site_visitor
ON ads_customer_links(site_id, visitor_id, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_ads_customer_links_site_session
ON ads_customer_links(site_id, session_id, last_seen DESC);
