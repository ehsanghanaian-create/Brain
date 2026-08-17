-- 0003: SEO Brain phase 3 (site management)
--  * site_memory: full "Site Brain" configuration (audience, CTA rules, forbidden claims)
--  * site_connections: last known status of external connections per site (GSC, GA4, WordPress)
--  * sites.timezone / sites.wp_auth_configured helpers for the wizard

ALTER TABLE site_memory ADD COLUMN audience TEXT NOT NULL DEFAULT '{}';          -- JSON: {segments[], pains[], intent_notes}
ALTER TABLE site_memory ADD COLUMN cta_rules TEXT NOT NULL DEFAULT '[]';         -- JSON array of strings
ALTER TABLE site_memory ADD COLUMN forbidden_claims TEXT NOT NULL DEFAULT '[]';  -- JSON array of strings

CREATE TABLE IF NOT EXISTS site_connections (
  site_id     TEXT NOT NULL REFERENCES sites(site_id),
  kind        TEXT NOT NULL,                       -- gsc | ga4 | wordpress
  status      TEXT NOT NULL,                       -- ok | not_configured | not_authorized | not_found | error
  detail      TEXT,                                -- JSON (property, permission, message, scopes…) — never secrets
  tested_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (site_id, kind)
);

ALTER TABLE sites ADD COLUMN timezone TEXT;
