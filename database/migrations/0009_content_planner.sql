-- 0009: SEO Brain phase 8.5 — Content Strategy Planner + Advanced Content Brain (additive)
--  content_categories          WordPress categories (synced read-only) + Brain topic categories + manual ones, with intelligence
--  content_clusters            editorial clusters (pillar + supporting plans)
--  content_plans               strategy rows (planner spreadsheet); 1:1 optional link to content_items (production object)
--  content_plan_keywords       keyword ↔ plan with role
--  content_plan_events         audit / history
--  content_plan_imports        import audit (file or Google Sheet)
--  content_plan_sources        future-compatible sync sources (Google Sheet CSV export URL now; API later)
--  content_plan_recommendations permanent Brain recommendation storage (versioned, human accept/dismiss)
--  content_plan_generation_jobs future AI generation layer: plan → generation_job → content_item → draft (prepared only)
--  link_suggestions            + plan_id (pre-writing link suggestions, scope='plan')

CREATE TABLE IF NOT EXISTS content_categories (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id                TEXT NOT NULL REFERENCES sites(site_id),
  source                 TEXT NOT NULL DEFAULT 'wordpress',   -- wordpress | brain | manual
  wordpress_category_id  INTEGER,                             -- WP term id (NULL unless source=wordpress)
  parent_id              INTEGER REFERENCES content_categories(id),
  name                   TEXT NOT NULL,
  slug                   TEXT,
  url                    TEXT,
  description            TEXT,
  post_count             INTEGER NOT NULL DEFAULT 0,          -- from WordPress
  page_count             INTEGER NOT NULL DEFAULT 0,          -- crawled pages/posts mapped to this category
  keyword_count          INTEGER NOT NULL DEFAULT 0,          -- keywords related by rules/graph
  plan_count             INTEGER NOT NULL DEFAULT 0,
  coverage_score         REAL,                                -- 0–100: share of related keywords covered by existing pages
  intelligence           TEXT NOT NULL DEFAULT '{}',          -- JSON: clusters[], intents{}, top_keywords[], gaps[], entities[], graph_node_id
  metadata               TEXT NOT NULL DEFAULT '{}',
  synced_at              TEXT,
  created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_content_categories_wp ON content_categories(site_id, wordpress_category_id) WHERE wordpress_category_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_content_categories_slug ON content_categories(site_id, source, slug) WHERE slug IS NOT NULL;

CREATE TABLE IF NOT EXISTS content_clusters (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id            TEXT NOT NULL REFERENCES sites(site_id),
  name               TEXT NOT NULL,
  slug               TEXT,
  pillar_plan_id     INTEGER,
  keyword_cluster_id TEXT,
  topic              TEXT,
  category_id        INTEGER REFERENCES content_categories(id),
  description        TEXT,
  metadata           TEXT NOT NULL DEFAULT '{}',
  created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS content_plans (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id                TEXT NOT NULL REFERENCES sites(site_id),
  content_item_id        INTEGER REFERENCES content_items(id),   -- 1:1 production object, created on demand
  title                  TEXT NOT NULL,
  url                    TEXT,
  slug                   TEXT,
  intent                 TEXT,                                   -- informational | navigational | commercial | transactional | local
  serp_intent            TEXT,                                   -- intent observed on the SERP / GSC (may differ from planned intent)
  page_type              TEXT,                                   -- service_landing | location_landing | pillar | article | guide | comparison | faq | product | category_page | news
  funnel_stage           TEXT,                                   -- awareness | consideration | decision | retention (derived from intent + page type)
  category_id            INTEGER REFERENCES content_categories(id),
  category_suggested_id  INTEGER,
  category_reason        TEXT,
  primary_keyword_id     INTEGER REFERENCES keywords(id),
  primary_keyword        TEXT,
  secondary_keywords     TEXT NOT NULL DEFAULT '[]',             -- JSON [string]
  heading_structure      TEXT NOT NULL DEFAULT '[]',             -- JSON [{level, text}]
  seo_title              TEXT,
  meta_description       TEXT,
  topic_id               TEXT,
  cluster_id             TEXT,                                   -- keyword cluster id
  content_cluster_id     INTEGER REFERENCES content_clusters(id),
  search_volume          INTEGER,
  keyword_difficulty     REAL,
  priority               TEXT,                                   -- high | medium | low
  priority_score         REAL,                                   -- 0–100 rule-based
  ai_priority            REAL,                                   -- 0–100 reserved for the AI/learning layer (advisory)
  business_value         REAL,                                   -- 0–100 human-set commercial value
  traffic_opportunity    REAL,                                   -- estimated monthly clicks gain
  content_gap            TEXT,                                   -- none | partial | full  (coverage of the topic by existing pages)
  cannibalization_risk   REAL,                                   -- 0–1
  cannibalization        TEXT NOT NULL DEFAULT '[]',             -- JSON [{kind: plan|page|content, id, url, title, keyword}]
  ranking_url            TEXT,
  ranking_position       REAL,
  target_audience        TEXT,
  publish_date           TEXT,
  publish_time           TEXT,
  status                 TEXT NOT NULL DEFAULT 'planned',        -- planned | researching | brief_ready | writing | review | approved | published
  existing_pages         TEXT NOT NULL DEFAULT '[]',             -- JSON [{node_id, url, title, position, relation}]
  link_targets           TEXT NOT NULL DEFAULT '[]',             -- JSON [{direction, node_id, url, title, anchor, reason_fa, score}]
  graph_connections      INTEGER NOT NULL DEFAULT 0,
  content_score          REAL,                                   -- latest Phase-7 score of the linked item (denormalised)
  recommendation_id      INTEGER,                                -- current row in content_plan_recommendations
  recommendation         TEXT NOT NULL DEFAULT '{}',             -- JSON copy of the current recommendation (grid column)
  publishing             TEXT NOT NULL DEFAULT '{}',             -- JSON publishing metadata (target, wp_status, scheduled_at, checklist) — publishing itself disabled
  metadata               TEXT NOT NULL DEFAULT '{}',
  notes                  TEXT,
  source                 TEXT,                                   -- manual | import:<file> | sheet:<id> | keyword:<id> | opportunity:<id> | suggestion:<id> | backfill
  created_by             TEXT,
  created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_content_plans_site_status ON content_plans(site_id, status);
CREATE INDEX IF NOT EXISTS idx_content_plans_site_date ON content_plans(site_id, publish_date);
CREATE INDEX IF NOT EXISTS idx_content_plans_site_cat ON content_plans(site_id, category_id);
CREATE INDEX IF NOT EXISTS idx_content_plans_item ON content_plans(content_item_id);

CREATE TABLE IF NOT EXISTS content_plan_keywords (
  content_plan_id  INTEGER NOT NULL REFERENCES content_plans(id),
  keyword_id       INTEGER NOT NULL REFERENCES keywords(id),
  site_id          TEXT NOT NULL,
  role             TEXT NOT NULL DEFAULT 'secondary',            -- primary | secondary | supporting | question | gsc_query
  source           TEXT,                                         -- manual | import | mapping | brain
  score            REAL,
  created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (content_plan_id, keyword_id)
);
CREATE INDEX IF NOT EXISTS idx_cpk_keyword ON content_plan_keywords(site_id, keyword_id);

CREATE TABLE IF NOT EXISTS content_plan_events (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id          TEXT NOT NULL,
  content_plan_id  INTEGER NOT NULL,
  event            TEXT NOT NULL,        -- created | updated | status_changed | imported | analyzed | category_set | keywords_mapped | linked_content | links_prepared | generation_prepared | deleted
  actor            TEXT,
  from_value       TEXT,
  to_value         TEXT,
  payload          TEXT NOT NULL DEFAULT '{}',
  created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_cpe_plan ON content_plan_events(content_plan_id);

CREATE TABLE IF NOT EXISTS content_plan_imports (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL,
  source        TEXT NOT NULL DEFAULT 'file',   -- file | google_sheet
  source_id     INTEGER,                        -- content_plan_sources.id when synced
  filename      TEXT,
  format        TEXT,
  rows_total    INTEGER NOT NULL DEFAULT 0,
  rows_created  INTEGER NOT NULL DEFAULT 0,
  rows_updated  INTEGER NOT NULL DEFAULT 0,
  rows_skipped  INTEGER NOT NULL DEFAULT 0,
  errors        TEXT NOT NULL DEFAULT '[]',
  mapping       TEXT NOT NULL DEFAULT '{}',
  dry_run       INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS content_plan_sources (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       TEXT NOT NULL,
  kind          TEXT NOT NULL DEFAULT 'google_sheet',   -- google_sheet (public CSV export) | csv_url | google_sheets_api (future)
  name          TEXT NOT NULL,
  url           TEXT,                                   -- share URL or CSV export URL
  sheet_id      TEXT,
  gid           TEXT,
  range         TEXT,
  mapping       TEXT NOT NULL DEFAULT '{}',
  key_columns   TEXT NOT NULL DEFAULT '["url","primary_keyword","title"]',
  enabled       INTEGER NOT NULL DEFAULT 1,
  auto_sync     INTEGER NOT NULL DEFAULT 0,             -- reserved (scheduler) — never enabled automatically
  status        TEXT,
  last_sync_at  TEXT,
  last_result   TEXT NOT NULL DEFAULT '{}',
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS content_plan_recommendations (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id        TEXT NOT NULL,
  plan_id        INTEGER,                    -- NULL for keyword/category-level suggestions not yet planned
  keyword_id     INTEGER,
  category_id    INTEGER,
  kind           TEXT NOT NULL,              -- create_new | optimize_existing | improve_page | add_to_cluster | merge | category | link_prep | gap | schedule
  action         TEXT,                       -- machine action key
  title          TEXT,
  page_type      TEXT,
  intent         TEXT,
  priority       TEXT,
  priority_score REAL,
  confidence     REAL,
  reasons        TEXT NOT NULL DEFAULT '[]', -- JSON [string fa]
  payload        TEXT NOT NULL DEFAULT '{}', -- JSON full recommendation (existing_pages, category, cluster, links…)
  version        INTEGER NOT NULL DEFAULT 1,
  status         TEXT NOT NULL DEFAULT 'new',   -- new | accepted | dismissed | superseded | applied
  engine         TEXT NOT NULL DEFAULT 'rules-v1',
  computed_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  decided_at     TEXT,
  decided_by     TEXT
);
CREATE INDEX IF NOT EXISTS idx_cpr_site_status ON content_plan_recommendations(site_id, status);
CREATE INDEX IF NOT EXISTS idx_cpr_plan ON content_plan_recommendations(plan_id);

CREATE TABLE IF NOT EXISTS content_plan_generation_jobs (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id            TEXT NOT NULL,
  plan_id            INTEGER NOT NULL,
  content_item_id    INTEGER,
  generation_run_id  TEXT,                    -- generation_runs.run_id once a Phase-9 run is started by a human
  draft_id           INTEGER,
  kind               TEXT NOT NULL DEFAULT 'article',   -- brief | outline | article | rewrite | title_meta
  status             TEXT NOT NULL DEFAULT 'prepared',  -- prepared | queued | running | done | failed | cancelled  (only 'prepared' is produced now)
  params             TEXT NOT NULL DEFAULT '{}',        -- JSON {mode, models, prompt_versions, notes}
  requested_by       TEXT,
  created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_cpgj_plan ON content_plan_generation_jobs(plan_id);

ALTER TABLE link_suggestions ADD COLUMN plan_id INTEGER;
