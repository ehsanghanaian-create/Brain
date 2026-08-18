"""SQLAlchemy Core Table definitions for the SEO Brain aggregates.

Only tables that the new repositories touch are declared explicitly (typed, Postgres-compatible).
Everything else from the v0.1 schema is available through `reflect(engine)` until it is migrated.
JSON columns are stored as TEXT (SQLite) and read/written as JSON by the repositories, so the same
definitions work on PostgreSQL (`TEXT`→`JSONB` is a later, mechanical migration).
"""
from __future__ import annotations

from sqlalchemy import Column, Float, Integer, MetaData, String, Table, Text

metadata = MetaData()

sites = Table(
    "sites", metadata,
    Column("site_id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("canonical_url", String, nullable=False),
    Column("wp_url", String),
    Column("language", String),
    Column("gsc_property", String),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    # phase 1 additions (migration 0002)
    Column("business_type", String),
    Column("country", String),
    Column("mode", String, nullable=False, server_default="manual"),   # manual | assisted | autopilot
    Column("ga4_property", String),
    Column("workspace_path", String),
    Column("timezone", String),
)

site_memory = Table(
    "site_memory", metadata,
    Column("site_id", String, primary_key=True),
    Column("business_rules", Text, nullable=False, server_default="[]"),
    Column("tone", Text, nullable=False, server_default="{}"),
    Column("content_rules", Text, nullable=False, server_default="[]"),
    Column("successful_patterns", Text, nullable=False, server_default="[]"),
    Column("updated_at", String, nullable=False),
    # phase 3 (migration 0003)
    Column("audience", Text, nullable=False, server_default="{}"),
    Column("cta_rules", Text, nullable=False, server_default="[]"),
    Column("forbidden_claims", Text, nullable=False, server_default="[]"),
)

site_connections = Table(
    "site_connections", metadata,
    Column("site_id", String, primary_key=True),
    Column("kind", String, primary_key=True),          # gsc | ga4 | wordpress
    Column("status", String, nullable=False),          # ok | not_configured | not_authorized | not_found | error
    Column("detail", Text),
    Column("tested_at", String, nullable=False),
)

graph_nodes = Table(
    "graph_nodes", metadata,
    Column("site_id", String, primary_key=True),
    Column("node_id", String, primary_key=True),
    Column("node_type", String, nullable=False),
    Column("label", String, nullable=False),
    Column("url", String),
    Column("props", Text),
    Column("vault_path", String),
    Column("pagerank", Float),
    Column("community", Integer),
    Column("updated_at", String, nullable=False),
)

graph_edges = Table(
    "graph_edges", metadata,
    Column("site_id", String, primary_key=True),
    Column("edge_id", String, primary_key=True),
    Column("source_id", String, nullable=False),
    Column("target_id", String, nullable=False),
    Column("edge_type", String, nullable=False),
    Column("weight", Float, server_default="1"),
    Column("props", Text),
)

schema_migrations = Table(
    "schema_migrations", metadata,
    Column("version", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("applied_at", String, nullable=False),
)


def reflect(engine) -> MetaData:
    """Reflect the whole live schema (legacy tables) for ad-hoc, read-only Core queries."""
    md = MetaData()
    md.reflect(bind=engine)
    return md


# ----------------------------------------------------------------------------- phase 5: keywords
keyword_clusters = Table(
    "keyword_clusters", metadata,
    Column("cluster_id", String, primary_key=True),
    Column("site_id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("topic", String),
    Column("keywords_count", Integer, nullable=False, server_default="0"),
    Column("method", String),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

keywords = Table(
    "keywords", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("keyword", String, nullable=False),
    Column("normalized", String, nullable=False),
    Column("intent", String),
    Column("cluster_id", String),
    Column("topic", String),
    Column("volume", Integer),
    Column("difficulty", Float),
    Column("priority", String),
    Column("target_url", String),
    Column("status", String, nullable=False, server_default="new"),
    Column("source", String),
    Column("notes", Text),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

keyword_imports = Table(
    "keyword_imports", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("filename", String),
    Column("format", String),
    Column("rows_total", Integer, nullable=False, server_default="0"),
    Column("rows_imported", Integer, nullable=False, server_default="0"),
    Column("rows_updated", Integer, nullable=False, server_default="0"),
    Column("rows_skipped", Integer, nullable=False, server_default="0"),
    Column("mapping", Text),
    Column("errors", Text),
    Column("created_at", String, nullable=False),
)

keyword_opportunities = Table(
    "keyword_opportunities", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("keyword_id", Integer, nullable=False),
    Column("kind", String, nullable=False),
    Column("target_url", String),
    Column("score", Float, nullable=False, server_default="0"),
    Column("reason", Text),
    Column("evidence", Text),
    Column("status", String, nullable=False, server_default="new"),
    Column("run_id", String),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)


# ----------------------------------------------------------------------------- phase 6: content brain + ai providers
content_items = Table(
    "content_items", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("title", String, nullable=False),
    Column("slug", String),
    Column("target_keyword_id", Integer),
    Column("target_keyword", String),
    Column("topic", String),
    Column("cluster_id", String),
    Column("intent", String),
    Column("status", String, nullable=False, server_default="planned"),
    Column("priority", String),
    Column("publish_date", String),
    Column("publish_time", String),
    Column("ai_provider", String),
    Column("ai_model", String),
    Column("url", String),
    Column("wp_post_id", Integer),
    Column("brief_id", Integer),
    Column("metadata", Text, nullable=False, server_default="{}"),
    Column("notes", Text),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

content_events = Table(
    "content_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("content_id", Integer, nullable=False),
    Column("from_status", String),
    Column("to_status", String),
    Column("actor", String, nullable=False, server_default="user"),
    Column("note", Text),
    Column("created_at", String, nullable=False),
)

content_briefs = Table(
    "content_briefs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("content_id", Integer, nullable=False),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("h1", String),
    Column("seo_title", String),
    Column("meta_description", Text),
    Column("intent", String),
    Column("outline", Text, nullable=False, server_default="[]"),
    Column("entities", Text, nullable=False, server_default="[]"),
    Column("questions", Text, nullable=False, server_default="[]"),
    Column("internal_links", Text, nullable=False, server_default="[]"),
    Column("sources", Text, nullable=False, server_default="{}"),
    Column("markdown", Text),
    Column("provenance", Text, nullable=False, server_default="{}"),
    Column("created_at", String, nullable=False),
)

ai_providers = Table(
    "ai_providers", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String, nullable=False),
    Column("kind", String, nullable=False),
    Column("base_url", String),
    Column("default_model", String),
    Column("models", Text, nullable=False, server_default="[]"),
    Column("enabled", Integer, nullable=False, server_default="1"),
    Column("secret_ref", String),
    Column("key_hint", String),
    Column("last_test", Text),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

ai_routes = Table(
    "ai_routes", metadata,
    Column("task_kind", String, primary_key=True),
    Column("site_id", String, primary_key=True, server_default="*"),
    Column("provider_id", Integer),
    Column("model", String),
    Column("fallback_provider_id", Integer),
    Column("fallback_model", String),
    Column("updated_at", String, nullable=False),
)
