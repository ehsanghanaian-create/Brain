-- 0002: SEO Brain phase 1
--  * site_memory  — per-site brain memory (business rules, tone, content rules, successful patterns)
--  * sites        — new columns for the multi-site workspace model (mode gates outbound writes)
--  * graph_nodes_v / graph_edges_v — Neo4j-compatible projections of the existing graph tables
--    (id/site_id/type/metadata and source/target/relation_type/weight/metadata)
-- All statements are idempotent for SQLite; the ALTERs are guarded by the migration runner
-- (it skips "duplicate column" errors so re-running on an already-patched DB is safe).

CREATE TABLE IF NOT EXISTS site_memory (
  site_id             TEXT PRIMARY KEY REFERENCES sites(site_id),
  business_rules      TEXT NOT NULL DEFAULT '[]',   -- JSON array of strings
  tone                TEXT NOT NULL DEFAULT '{}',   -- JSON object: {voice, formality, audience, language_notes}
  content_rules       TEXT NOT NULL DEFAULT '[]',   -- JSON array of strings
  successful_patterns TEXT NOT NULL DEFAULT '[]',   -- JSON array of {pattern, evidence, source, run_id, created_at}
  updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

ALTER TABLE sites ADD COLUMN business_type TEXT;
ALTER TABLE sites ADD COLUMN country TEXT;
ALTER TABLE sites ADD COLUMN mode TEXT NOT NULL DEFAULT 'manual';   -- manual | assisted | autopilot (gates outbound writes)
ALTER TABLE sites ADD COLUMN ga4_property TEXT;
ALTER TABLE sites ADD COLUMN workspace_path TEXT;                  -- data/sites/<domain>

CREATE VIEW IF NOT EXISTS graph_nodes_v AS
SELECT node_id AS id, site_id, node_type AS type,
       json_object('label', label, 'url', url, 'pagerank', pagerank, 'community', community,
                   'vault_path', vault_path, 'props', json(COALESCE(props, '{}'))) AS metadata
FROM graph_nodes;

CREATE VIEW IF NOT EXISTS graph_edges_v AS
SELECT source_id AS source, target_id AS target, edge_type AS relation_type, weight, site_id,
       json_object('edge_id', edge_id, 'props', json(COALESCE(props, '{}'))) AS metadata
FROM graph_edges;
