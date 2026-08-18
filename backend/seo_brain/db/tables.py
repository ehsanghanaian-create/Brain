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
    # phase 7 (migration 0006)
    Column("current_draft_id", Integer),
    Column("latest_score", Float),
    Column("review_status", String, nullable=False, server_default="none"),
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
    # phase 9
    Column("fallbacks", Text, nullable=False, server_default="[]"),
    Column("policy", String, nullable=False, server_default="auto"),
)


# ----------------------------------------------------------------------------- phase 7: content intelligence
content_drafts = Table(
    "content_drafts", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("content_id", Integer, nullable=False),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("title", String),
    Column("meta_description", Text),
    Column("format", String, nullable=False, server_default="markdown"),
    Column("body", Text, nullable=False),
    Column("body_text", Text),
    Column("word_count", Integer, nullable=False, server_default="0"),
    Column("structure", Text, nullable=False, server_default="{}"),
    Column("source", String, nullable=False, server_default="user"),
    Column("author", String),
    Column("revision_of", Integer),
    Column("change_summary", Text),
    Column("provenance", Text, nullable=False, server_default="{}"),
    Column("review_status", String, nullable=False, server_default="none"),
    Column("created_at", String, nullable=False),
)

content_scores = Table(
    "content_scores", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("content_id", Integer, nullable=False),
    Column("draft_id", Integer, nullable=False),
    Column("total", Float, nullable=False),
    Column("dims", Text, nullable=False, server_default="{}"),
    Column("findings", Text, nullable=False, server_default="[]"),
    Column("weights", Text, nullable=False, server_default="{}"),
    Column("engine_version", String, nullable=False, server_default="score-v1"),
    Column("created_at", String, nullable=False),
)

content_reviews = Table(
    "content_reviews", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("content_id", Integer, nullable=False),
    Column("draft_id", Integer, nullable=False),
    Column("kind", String, nullable=False),
    Column("findings", Text, nullable=False, server_default="[]"),
    Column("summary_fa", Text),
    Column("counts", Text, nullable=False, server_default="{}"),
    Column("provenance", Text, nullable=False, server_default="{}"),
    Column("created_at", String, nullable=False),
)

content_metrics = Table(
    "content_metrics", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("content_id", Integer, nullable=False),
    Column("url", String, nullable=False),
    Column("window", String, nullable=False),
    Column("date", String, nullable=False),
    Column("clicks", Integer, nullable=False, server_default="0"),
    Column("impressions", Integer, nullable=False, server_default="0"),
    Column("ctr", Float, nullable=False, server_default="0"),
    Column("position", Float),
    Column("top_queries", Text, nullable=False, server_default="[]"),
    Column("delta", Text, nullable=False, server_default="{}"),
    Column("created_at", String, nullable=False),
)

content_insights = Table(
    "content_insights", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("category", String, nullable=False),
    Column("feature", String, nullable=False),
    Column("value", String, nullable=False),
    Column("metric", String, nullable=False),
    Column("effect", Float, nullable=False),
    Column("baseline", Float),
    Column("n", Integer, nullable=False),
    Column("impressions", Integer, nullable=False, server_default="0"),
    Column("clicks", Integer, nullable=False, server_default="0"),
    Column("confidence", Float),
    Column("message_fa", Text, nullable=False),
    Column("evidence", Text, nullable=False, server_default="{}"),
    Column("status", String, nullable=False, server_default="new"),
    Column("memory_pattern_ref", String),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

site_settings = Table(
    "site_settings", metadata,
    Column("site_id", String, primary_key=True),
    Column("key", String, primary_key=True),
    Column("value", Text, nullable=False, server_default="{}"),
    Column("updated_at", String, nullable=False),
)


# ----------------------------------------------------------------------------- phase 8: internal linking
link_suggestions = Table(
    "link_suggestions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("scope", String, nullable=False, server_default="internal"),
    Column("kind", String, nullable=False),
    Column("source_node_id", String, nullable=False),
    Column("source_url", String),
    Column("source_title", String),
    Column("source_stage", String),
    Column("target_node_id", String, nullable=False),
    Column("target_url", String),
    Column("target_title", String),
    Column("target_stage", String),
    Column("anchor", String),
    Column("anchor_alternatives", Text, nullable=False, server_default="[]"),
    Column("placement_hint", String),
    Column("score", Float, nullable=False),
    Column("confidence", String, nullable=False),
    Column("score_breakdown", Text, nullable=False, server_default="{}"),
    Column("reason_fa", Text),
    Column("evidence", Text, nullable=False, server_default="{}"),
    Column("status", String, nullable=False, server_default="new"),
    Column("content_task_id", Integer),
    Column("run_id", String),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

link_page_stats = Table(
    "link_page_stats", metadata,
    Column("site_id", String, primary_key=True),
    Column("node_id", String, primary_key=True),
    Column("url", String),
    Column("title", String),
    Column("stage", String),
    Column("inbound_total", Integer, nullable=False, server_default="0"),
    Column("inbound_body", Integer, nullable=False, server_default="0"),
    Column("inbound_nav_only", Integer, nullable=False, server_default="0"),
    Column("unique_sources", Integer, nullable=False, server_default="0"),
    Column("outbound_body", Integer, nullable=False, server_default="0"),
    Column("outbound_total", Integer, nullable=False, server_default="0"),
    Column("anchor_distribution", Text, nullable=False, server_default="[]"),
    Column("exact_match_ratio", Float, nullable=False, server_default="0"),
    Column("generic_ratio", Float, nullable=False, server_default="0"),
    Column("flags", Text, nullable=False, server_default="[]"),
    Column("pagerank", Float),
    Column("health_score", Float, nullable=False, server_default="0"),
    Column("health_breakdown", Text, nullable=False, server_default="{}"),
    Column("computed_at", String, nullable=False),
)

link_patterns = Table(
    "link_patterns", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("pattern_key", String, nullable=False),
    Column("feature", Text, nullable=False, server_default="{}"),
    Column("accepted", Integer, nullable=False, server_default="0"),
    Column("dismissed", Integer, nullable=False, server_default="0"),
    Column("done", Integer, nullable=False, server_default="0"),
    Column("acceptance_rate", Float, nullable=False, server_default="0"),
    Column("message_fa", Text, nullable=False),
    Column("status", String, nullable=False, server_default="new"),
    Column("memory_pattern_ref", String),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)


# ----------------------------------------------------------------------------- phase 9: ai orchestration
ai_models = Table(
    "ai_models", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("provider_id", Integer, nullable=False),
    Column("model_id", String, nullable=False),
    Column("display", String),
    Column("tier", String, nullable=False, server_default='balanced'),
    Column("tags", Text, nullable=False, server_default='[]'),
    Column("context_tokens", Integer),
    Column("price_in_per_m", Float, nullable=False, server_default='0'),
    Column("price_out_per_m", Float, nullable=False, server_default='0'),
    Column("enabled", Integer, nullable=False, server_default='1'),
    Column("source", String, nullable=False, server_default='catalog'),
    Column("updated_at", String, nullable=False),
)

ai_calls = Table(
    "ai_calls", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String),
    Column("run_id", String),
    Column("content_id", Integer),
    Column("agent", String),
    Column("task_kind", String, nullable=False),
    Column("provider", String, nullable=False),
    Column("model", String, nullable=False),
    Column("prompt_refs", Text, nullable=False, server_default='{}'),
    Column("memory_snapshot_id", Integer),
    Column("input_tokens", Integer, nullable=False, server_default='0'),
    Column("output_tokens", Integer, nullable=False, server_default='0'),
    Column("cost_usd", Float, nullable=False, server_default='0'),
    Column("latency_ms", Integer, nullable=False, server_default='0'),
    Column("ok", Integer, nullable=False, server_default='1'),
    Column("error", Text),
    Column("attempts", Text, nullable=False, server_default='[]'),
    Column("route_reason", String),
    Column("created_at", String, nullable=False),
)

ai_provider_health = Table(
    "ai_provider_health", metadata,
    Column("provider", String, primary_key=True),
    Column("calls", Integer, nullable=False, server_default='0'),
    Column("failures", Integer, nullable=False, server_default='0'),
    Column("consecutive_failures", Integer, nullable=False, server_default='0'),
    Column("p50_ms", Integer),
    Column("breaker_open_until", String),
    Column("last_error", Text),
    Column("updated_at", String, nullable=False),
)

memory_snapshots = Table(
    "memory_snapshots", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("hash", String, nullable=False),
    Column("pack", Text, nullable=False),
    Column("rendered", Text, nullable=False),
    Column("created_at", String, nullable=False),
)

prompts = Table(
    "prompts", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("key", String, nullable=False),
    Column("scope", String, nullable=False),
    Column("site_id", String),
    Column("title", String, nullable=False),
    Column("description", Text),
    Column("tags", Text, nullable=False, server_default='[]'),
    Column("created_at", String, nullable=False),
)

prompt_versions = Table(
    "prompt_versions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("prompt_id", Integer, nullable=False),
    Column("version", Integer, nullable=False),
    Column("template", Text, nullable=False),
    Column("variables", Text, nullable=False, server_default='[]'),
    Column("model_hints", Text, nullable=False, server_default='{}'),
    Column("is_active", Integer, nullable=False, server_default='0'),
    Column("approval", String, nullable=False, server_default='draft'),
    Column("approved_by", String),
    Column("approved_at", String),
    Column("changelog", Text),
    Column("created_by", String),
    Column("created_at", String, nullable=False),
)

prompt_tests = Table(
    "prompt_tests", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("prompt_version_id", Integer, nullable=False),
    Column("site_id", String),
    Column("content_id", Integer),
    Column("model", String),
    Column("provider", String),
    Column("input_ref", String),
    Column("output", Text),
    Column("score", Float),
    Column("input_tokens", Integer),
    Column("output_tokens", Integer),
    Column("cost_usd", Float),
    Column("latency_ms", Integer),
    Column("human_rating", Integer),
    Column("notes", Text),
    Column("created_at", String, nullable=False),
)

generation_runs = Table(
    "generation_runs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String, nullable=False),
    Column("site_id", String, nullable=False),
    Column("content_id", Integer, nullable=False),
    Column("mode", String, nullable=False),
    Column("status", String, nullable=False, server_default='queued'),
    Column("step", String),
    Column("steps", Text, nullable=False, server_default='[]'),
    Column("models", Text, nullable=False, server_default='{}'),
    Column("prompt_versions", Text, nullable=False, server_default='{}'),
    Column("memory_snapshot_id", Integer),
    Column("estimate", Text, nullable=False, server_default='{}'),
    Column("actual", Text, nullable=False, server_default='{}'),
    Column("draft_id", Integer),
    Column("score", Float),
    Column("review_status", String),
    Column("error", Text),
    Column("created_by", String),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

generation_artifacts = Table(
    "generation_artifacts", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String, nullable=False),
    Column("step", String, nullable=False),
    Column("agent", String, nullable=False),
    Column("version", Integer, nullable=False, server_default='1'),
    Column("schema_key", String),
    Column("payload", Text, nullable=False),
    Column("provenance", Text, nullable=False, server_default='{}'),
    Column("created_at", String, nullable=False),
)

draft_feedback = Table(
    "draft_feedback", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String, nullable=False),
    Column("content_id", Integer),
    Column("draft_id", Integer),
    Column("run_id", String),
    Column("rating", Integer, nullable=False),
    Column("tags", Text, nullable=False, server_default='[]'),
    Column("notes", Text),
    Column("created_by", String),
    Column("created_at", String, nullable=False),
)

ai_insights = Table(
    "ai_insights", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("site_id", String),
    Column("category", String, nullable=False),
    Column("feature", String, nullable=False),
    Column("value", String, nullable=False),
    Column("metric", String, nullable=False),
    Column("effect", Float, nullable=False),
    Column("baseline", Float),
    Column("n", Integer, nullable=False),
    Column("confidence", Float),
    Column("message_fa", Text, nullable=False),
    Column("evidence", Text, nullable=False, server_default='{}'),
    Column("recommendation", Text, nullable=False, server_default='{}'),
    Column("status", String, nullable=False, server_default='new'),
    Column("memory_pattern_ref", String),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)
