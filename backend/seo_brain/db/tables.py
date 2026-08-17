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
)

site_memory = Table(
    "site_memory", metadata,
    Column("site_id", String, primary_key=True),
    Column("business_rules", Text, nullable=False, server_default="[]"),
    Column("tone", Text, nullable=False, server_default="{}"),
    Column("content_rules", Text, nullable=False, server_default="[]"),
    Column("successful_patterns", Text, nullable=False, server_default="[]"),
    Column("updated_at", String, nullable=False),
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
