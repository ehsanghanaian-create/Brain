-- Backlink & reportage (sponsored article) tracking for the Site Report Center.
-- Backlinks may later be filled by an external provider (Ahrefs/DataForSEO/GSC links);
-- reportages are entered manually and verified by the read-only link checker.

CREATE TABLE IF NOT EXISTS backlinks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
    source_url TEXT NOT NULL,
    source_domain TEXT NOT NULL,
    target_url TEXT NOT NULL,
    anchor_text TEXT,
    link_type TEXT NOT NULL DEFAULT 'generic',          -- generic|reportage|directory|comment|profile|other
    rel TEXT,                                           -- follow|nofollow|sponsored|ugc (as observed)
    provider TEXT NOT NULL DEFAULT 'manual',            -- manual|gsc|ahrefs|dataforseo|...
    first_seen TEXT,
    last_seen TEXT,
    status TEXT NOT NULL DEFAULT 'active',              -- active|lost|unverified
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(site_id, source_url, target_url)
);
CREATE INDEX IF NOT EXISTS idx_backlinks_site ON backlinks(site_id, status);
CREATE INDEX IF NOT EXISTS idx_backlinks_domain ON backlinks(site_id, source_domain);

CREATE TABLE IF NOT EXISTS reportages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
    publication_domain TEXT NOT NULL,
    article_url TEXT NOT NULL,
    target_url TEXT NOT NULL,
    anchor_text TEXT,
    target_keyword TEXT,
    publication_date TEXT,
    link_type TEXT,                                     -- follow|nofollow|sponsored|ugc (expected/observed)
    cost INTEGER,                                       -- تومان
    status TEXT NOT NULL DEFAULT 'pending',             -- pending|published|link_found|link_missing|article_missing|target_changed
    verified_rel TEXT,                                  -- rel observed at last verification
    last_verified_at TEXT,
    verify_detail TEXT,                                 -- JSON evidence from last verification
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(site_id, article_url, target_url)
);
CREATE INDEX IF NOT EXISTS idx_reportages_site ON reportages(site_id, status);
