-- SEO Knowledge Graph — SQLite schema (source of truth). Every site-scoped table carries site_id.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sites (
  site_id       TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  wp_url        TEXT,
  language      TEXT,
  gsc_property  TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Run bookkeeping -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS crawl_runs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id        TEXT UNIQUE NOT NULL,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  started_at    TEXT NOT NULL,
  finished_at   TEXT,
  max_urls      INTEGER,
  urls_crawled  INTEGER DEFAULT 0,
  urls_failed   INTEGER DEFAULT 0,
  status        TEXT NOT NULL DEFAULT 'running',  -- running|completed|failed|aborted
  notes         TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS sync_runs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id        TEXT UNIQUE NOT NULL,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  source        TEXT NOT NULL,          -- wordpress|gsc|graph|analysis
  started_at    TEXT NOT NULL,
  finished_at   TEXT,
  status        TEXT NOT NULL DEFAULT 'running',
  rows_written  INTEGER DEFAULT 0,
  params        TEXT,                    -- JSON
  notes         TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- WordPress content ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS posts (            -- posts AND pages AND any public CPT (type column)
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL REFERENCES sites(site_id),
  wp_id           INTEGER NOT NULL,
  type            TEXT NOT NULL,             -- post|page|<cpt>
  url             TEXT NOT NULL,             -- normalized link
  slug            TEXT,
  title           TEXT,
  content_html    TEXT,
  content_text    TEXT,
  excerpt         TEXT,
  status          TEXT,
  date_gmt        TEXT,
  modified_gmt    TEXT,
  author_id       INTEGER,
  featured_media  INTEGER,
  parent_wp_id    INTEGER,
  yoast_title     TEXT,
  yoast_description TEXT,
  yoast_canonical TEXT,
  yoast_robots    TEXT,                      -- JSON
  yoast_schema    TEXT,                      -- JSON
  word_count      INTEGER,
  raw_json_path   TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, type, wp_id),
  UNIQUE(site_id, url)
);
CREATE INDEX IF NOT EXISTS idx_posts_site_type ON posts(site_id, type);

CREATE TABLE IF NOT EXISTS taxonomies (      -- taxonomy definitions (category, post_tag, custom)
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  slug          TEXT NOT NULL,                -- category | post_tag | ...
  name          TEXT,
  rest_base     TEXT,
  hierarchical  INTEGER DEFAULT 0,
  object_types  TEXT,                         -- JSON list
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, slug)
);

CREATE TABLE IF NOT EXISTS categories (      -- terms of hierarchical taxonomies (category + custom hierarchical)
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  taxonomy      TEXT NOT NULL DEFAULT 'category',
  wp_id         INTEGER NOT NULL,
  name          TEXT,
  slug          TEXT,
  url           TEXT,
  description   TEXT,
  parent_wp_id  INTEGER DEFAULT 0,
  count         INTEGER DEFAULT 0,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, taxonomy, wp_id)
);

CREATE TABLE IF NOT EXISTS tags (            -- terms of flat taxonomies (post_tag + custom flat)
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  taxonomy      TEXT NOT NULL DEFAULT 'post_tag',
  wp_id         INTEGER NOT NULL,
  name          TEXT,
  slug          TEXT,
  url           TEXT,
  count         INTEGER DEFAULT 0,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, taxonomy, wp_id)
);

CREATE TABLE IF NOT EXISTS post_terms (      -- post <-> term relationships
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  post_type     TEXT NOT NULL,
  post_wp_id    INTEGER NOT NULL,
  taxonomy      TEXT NOT NULL,
  term_wp_id    INTEGER NOT NULL,
  PRIMARY KEY (site_id, post_type, post_wp_id, taxonomy, term_wp_id)
);

CREATE TABLE IF NOT EXISTS media (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  wp_id         INTEGER NOT NULL,
  source_url    TEXT,
  alt_text      TEXT,
  title         TEXT,
  mime_type     TEXT,
  post_wp_id    INTEGER,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, wp_id)
);

-- Crawl data ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pages (           -- one row per normalized URL discovered by the crawler
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id         TEXT NOT NULL REFERENCES sites(site_id),
  url             TEXT NOT NULL,             -- normalized requested URL
  final_url       TEXT,
  status_code     INTEGER,
  redirect_chain  TEXT,                      -- JSON list of [url,status]
  content_type    TEXT,
  response_time_ms INTEGER,
  title           TEXT,
  meta_description TEXT,
  h1              TEXT,                      -- JSON list
  h1_count        INTEGER,
  h2              TEXT,                      -- JSON list
  canonical       TEXT,
  robots_meta     TEXT,
  x_robots_tag    TEXT,
  indexable       INTEGER,                   -- 1/0/NULL
  indexability_reason TEXT,
  word_count      INTEGER,
  language        TEXT,
  images          TEXT,                      -- JSON list of {src,alt}
  images_missing_alt INTEGER,
  internal_links_out INTEGER,
  external_links_out INTEGER,
  schema_types    TEXT,                      -- JSON list of @type
  structured_data TEXT,                      -- JSON (raw ld+json blocks)
  content_hash    TEXT,
  in_sitemap      INTEGER DEFAULT 0,
  discovered_from TEXT,
  depth           INTEGER,
  crawl_status    TEXT,                      -- ok|error|skipped_robots|skipped_external
  crawl_error     TEXT,
  last_crawled    TEXT,
  crawl_run_id    TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, url)
);
CREATE INDEX IF NOT EXISTS idx_pages_site_status ON pages(site_id, status_code);
CREATE INDEX IF NOT EXISTS idx_pages_site_indexable ON pages(site_id, indexable);

CREATE TABLE IF NOT EXISTS links (           -- actual crawled hyperlinks
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  source_url    TEXT NOT NULL,               -- normalized
  target_url    TEXT NOT NULL,               -- normalized
  anchor_text   TEXT,
  rel           TEXT,
  is_internal   INTEGER NOT NULL,
  is_nav        INTEGER DEFAULT 0,           -- inside <nav>/<header>/<footer>
  position      INTEGER,
  crawl_run_id  TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, source_url, target_url, anchor_text, is_nav)
);
CREATE INDEX IF NOT EXISTS idx_links_target ON links(site_id, target_url);
CREATE INDEX IF NOT EXISTS idx_links_source ON links(site_id, source_url);

CREATE TABLE IF NOT EXISTS schemas (         -- structured data per page (flattened)
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  url           TEXT NOT NULL,
  schema_type   TEXT NOT NULL,
  schema_id     TEXT,
  json          TEXT,
  source        TEXT DEFAULT 'ld+json',       -- ld+json|microdata|yoast_rest
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, url, schema_type, schema_id)
);

-- Entities (brands, models, services, locations) --------------------------
CREATE TABLE IF NOT EXISTS entities (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  entity_type   TEXT NOT NULL,               -- BRAND|MODEL|SERVICE|LOCATION
  name          TEXT NOT NULL,
  slug          TEXT NOT NULL,
  aliases       TEXT,                        -- JSON list
  parent_slug   TEXT,                        -- e.g. model -> brand
  source        TEXT,                        -- taxonomy|title|content|manual
  evidence      TEXT,                        -- JSON: where it was found
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, entity_type, slug)
);

CREATE TABLE IF NOT EXISTS entity_mentions ( -- page ABOUT entity (real evidence)
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  url           TEXT NOT NULL,
  entity_type   TEXT NOT NULL,
  entity_slug   TEXT NOT NULL,
  mentions      INTEGER DEFAULT 0,
  in_title      INTEGER DEFAULT 0,
  in_h1         INTEGER DEFAULT 0,
  in_url        INTEGER DEFAULT 0,
  in_taxonomy   INTEGER DEFAULT 0,
  score         REAL DEFAULT 0,
  PRIMARY KEY (site_id, url, entity_type, entity_slug)
);

-- GSC ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gsc_daily (       -- date x page x query x country x device
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  date          TEXT NOT NULL,
  page          TEXT NOT NULL,               -- normalized URL
  query         TEXT NOT NULL,
  country       TEXT DEFAULT '',
  device        TEXT DEFAULT '',
  clicks        INTEGER NOT NULL DEFAULT 0,
  impressions   INTEGER NOT NULL DEFAULT 0,
  ctr           REAL NOT NULL DEFAULT 0,
  position      REAL NOT NULL DEFAULT 0,
  sync_run_id   TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, date, page, query, country, device)
);
CREATE INDEX IF NOT EXISTS idx_gsc_daily_page ON gsc_daily(site_id, page);
CREATE INDEX IF NOT EXISTS idx_gsc_daily_query ON gsc_daily(site_id, query);
CREATE INDEX IF NOT EXISTS idx_gsc_daily_date ON gsc_daily(site_id, date);

CREATE TABLE IF NOT EXISTS gsc_query_page ( -- aggregated over the lookback window
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  page          TEXT NOT NULL,
  query         TEXT NOT NULL,
  clicks        INTEGER NOT NULL DEFAULT 0,
  impressions   INTEGER NOT NULL DEFAULT 0,
  ctr           REAL NOT NULL DEFAULT 0,
  position      REAL NOT NULL DEFAULT 0,      -- impression-weighted avg
  date_from     TEXT,
  date_to       TEXT,
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (site_id, page, query)
);

CREATE TABLE IF NOT EXISTS queries (         -- distinct queries with aggregate stats + importance flag
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  query         TEXT NOT NULL,
  clicks        INTEGER NOT NULL DEFAULT 0,
  impressions   INTEGER NOT NULL DEFAULT 0,
  ctr           REAL NOT NULL DEFAULT 0,
  position      REAL NOT NULL DEFAULT 0,
  pages_count   INTEGER NOT NULL DEFAULT 0,
  is_important  INTEGER NOT NULL DEFAULT 0,
  importance_reason TEXT,
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (site_id, query)
);

-- Analysis outputs -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS seo_problems (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  problem_type  TEXT NOT NULL,               -- orphan|missing_h1|multiple_h1|duplicate_title|...
  severity      TEXT NOT NULL,               -- high|medium|low
  url           TEXT,
  related_url   TEXT,
  detail        TEXT,                        -- JSON
  run_id        TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, problem_type, url, related_url)
);

CREATE TABLE IF NOT EXISTS seo_opportunities (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  opp_type      TEXT NOT NULL,               -- striking_distance|ctr|internal_link|cannibalization_candidate
  url           TEXT,
  related_url   TEXT,
  query         TEXT,
  score         REAL,
  score_breakdown TEXT,                      -- JSON (explainable)
  reason        TEXT,
  confidence    REAL,
  detail        TEXT,                        -- JSON
  run_id        TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(site_id, opp_type, url, related_url, query)
);

-- Graph (materialized) --------------------------------------------------------
CREATE TABLE IF NOT EXISTS graph_nodes (
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  node_id       TEXT NOT NULL,               -- e.g. page:<normalized url> | category:<slug> | model:<slug>
  node_type     TEXT NOT NULL,               -- SITE|PAGE|POST|CATEGORY|TAG|BRAND|MODEL|SERVICE|LOCATION|QUERY|SCHEMA|SEO_PROBLEM|SEO_OPPORTUNITY
  label         TEXT NOT NULL,
  url           TEXT,
  props         TEXT,                        -- JSON
  vault_path    TEXT,                        -- relative markdown path in the Obsidian vault
  pagerank      REAL,
  community     INTEGER,
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (site_id, node_id)
);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(site_id, node_type);

CREATE TABLE IF NOT EXISTS graph_edges (
  site_id       TEXT NOT NULL REFERENCES sites(site_id),
  edge_id       TEXT NOT NULL,
  source_id     TEXT NOT NULL,
  target_id     TEXT NOT NULL,
  edge_type     TEXT NOT NULL,               -- HAS_PAGE|HAS_POST|HAS_CATEGORY|HAS_TAG|BELONGS_TO|LINKS_TO|ABOUT|OFFERS|TARGETS|RANKS_FOR|HAS_SCHEMA|HAS_PROBLEM|HAS_OPPORTUNITY
  weight        REAL DEFAULT 1,
  props         TEXT,
  PRIMARY KEY (site_id, edge_id)
);
CREATE INDEX IF NOT EXISTS idx_graph_edges_src ON graph_edges(site_id, source_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_tgt ON graph_edges(site_id, target_id);

-- Full-text search over graph nodes
CREATE VIRTUAL TABLE IF NOT EXISTS graph_fts USING fts5(
  node_id UNINDEXED, site_id UNINDEXED, node_type UNINDEXED, label, url, body, tokenize='unicode61 remove_diacritics 2'
);
