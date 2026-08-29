/**
 * Typed fetch wrapper for the SEO Brain API (contract: docs/seo-brain/04-frontend-contract.md).
 * - browser: goes through the Next.js proxy /api/backend/* (token added server-side)
 * - server components: talk to the backend directly with the env token
 * - never throws raw fetch errors: every failure becomes ApiError {status, code, message, details, requestId}
 * Types come from schema.d.ts (generated from docs/seo-brain/openapi.v1.json — never hand-written).
 */
import type { components } from './schema';

export type Schemas = components['schemas'];
export type Site = Schemas['SiteCreate'] & { mode: 'manual' | 'assisted' | 'autopilot'; workspace_path: string | null; created_at: string; updated_at: string; gsc_property: string | null; ga4_property: string | null; wp_url: string | null };
export type ErrorEnvelope = { error: { code: string; message: string; details: unknown; request_id: string } };

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: unknown, public requestId: string) {
    super(message);
  }
}

const isServer = typeof window === 'undefined';

function baseUrl(): string {
  if (isServer) return `${(process.env.SEO_BRAIN_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')}/api/v1`;
  return '/api/backend';
}

function newRequestId(): string {
  return crypto.randomUUID().replace(/-/g, '').slice(0, 16);
}

type ApiInit = RequestInit & { json?: unknown; cacheSeconds?: number };

export async function api<T>(path: string, init: ApiInit = {}): Promise<T> {
  const { json, cacheSeconds, ...requestInit } = init;
  const requestId = newRequestId();
  const headers: Record<string, string> = { Accept: 'application/json', 'X-Request-ID': requestId, ...(requestInit.headers as Record<string, string> | undefined) };
  let body = requestInit.body;
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  }
  if (isServer && process.env.SEO_BRAIN_API_TOKEN) headers['X-API-Token'] = process.env.SEO_BRAIN_API_TOKEN;
  let res: Response;
  try {
    const cacheOptions = isServer && cacheSeconds && (!requestInit.method || requestInit.method === 'GET')
      ? { next: { revalidate: cacheSeconds } }
      : { cache: 'no-store' as const };
    res = await fetch(`${baseUrl()}${path.startsWith('/') ? path : `/${path}`}`, { ...requestInit, headers, body, ...cacheOptions });
  } catch (e) {
    throw new ApiError(0, 'network_error', `ارتباط با بک‌اند برقرار نشد (${String(e)})`, null, requestId);
  }
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const env = (data as ErrorEnvelope | null)?.error;
    throw new ApiError(res.status, env?.code ?? `http_${res.status}`, env?.message ?? res.statusText, env?.details ?? data, env?.request_id ?? res.headers.get('x-request-id') ?? requestId);
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

// ---- typed helpers for the endpoints the foundation uses (more are added per phase) --------------
export type Health = { status: string; version: string; database: string; migrations: { applied: string[]; pending: string[] } };
export type PortfolioSiteState = 'ready' | 'running' | 'attention' | 'partial' | 'not_started';
export type PortfolioActivity = {
  site_id: string; site_name: string; run_id: string; status: string; progress: number; step: string | null; step_fa: string | null;
  started_at: string | null; finished_at: string | null; errors: string[];
};
export type PortfolioSite = {
  site_id: string; name: string; canonical_url: string; wp_url: string | null; mode: 'manual' | 'assisted' | 'autopilot';
  state: PortfolioSiteState; state_reason: string; next_action: string;
  issues: { kind: string; severity: 'blocking' | 'warning'; message: string }[];
  setup_progress: number; setup_steps: { wordpress_configured: boolean; content_synced: boolean; crawl_ready: boolean; graph_ready: boolean };
  connections: Record<string, string>; latest_sync: PortfolioActivity | null;
  counts: { content: number; crawled: number; graph_nodes: number; graph_edges: number; keywords: number; planned_content: number; new_link_suggestions: number; high_link_suggestions: number };
};
export type PortfolioOverview = {
  generated_at: string;
  totals: { sites: number; ready_sites: number; needs_attention: number; content: number; crawled: number; graph_nodes: number; graph_edges: number; keywords: number; planned_content: number; new_link_suggestions: number; high_link_suggestions: number };
  state_counts: Record<PortfolioSiteState, number>;
  by_node_type: Record<string, number>;
  sites: PortfolioSite[];
  recent_activity: PortfolioActivity[];
};
export type GraphSummary = { site_id: string; nodes: number; edges: number; by_node_type: Record<string, number>; by_relation_type: Record<string, number>; site: Record<string, unknown> };
export type SiteMemory = {
  site_id: string;
  business_rules: string[];
  tone: Record<string, unknown>;
  audience: Record<string, unknown>;
  cta_rules: string[];
  content_rules: string[];
  forbidden_claims: string[];
  successful_patterns: Record<string, unknown>[];
  updated_at: string | null;
};
export type ConnectionKind = 'gsc' | 'ga4' | 'wordpress';
export type ConnectionResult = {
  kind: ConnectionKind;
  status: 'ok' | 'not_configured' | 'not_authorized' | 'not_found' | 'error';
  ok: boolean;
  message: string;
  detail: Record<string, unknown>;
  tested_at: string;
};
export type WpAuthStatus = { configured: boolean; username: string | null; key_hint: string | null; source: 'explicit' | 'site' | 'env' | null };
export type WpSyncStep = { key: string; fa?: string; status: 'pending' | 'running' | 'done' | 'failed' | 'skipped' | string; started_at?: string | null; finished_at?: string | null; items?: Record<string, unknown>; error?: string | null; note?: string | null };
export type WpSyncCounts = { categories: number; pages: number; posts: number; content_items?: number; taxonomies?: number; crawled: number; graph_nodes: number; graph_edges: number; graph_by_type?: Record<string, number> };
export type WpSyncStatus = {
  site_id: string; wp_url: string | null;
  status: 'never' | 'queued' | 'running' | 'succeeded' | 'completed_with_errors' | 'failed' | string;
  step: string | null; step_fa: string | null; progress: number; stage: 'full' | 'graph_only' | null;
  started_at: string | null; finished_at: string | null; items: Record<string, unknown>; errors: string[]; steps: WpSyncStep[];
  run_id: string | null; job_id: string | null; job: { run_id: string; status: string; error?: string | null } | null; counts: WpSyncCounts; steps_fa: Record<string, string>;
};
export type WpSyncQueued = { status: 'queued' | 'already_running' | 'not_queued' | string; job_id?: string | null; run_id?: string | null; stage?: string; step?: string | null; error?: string | null };
export type GscSyncCoverage = { date_from: string | null; date_to: string | null; rows: number; queries: number; important_queries: number; pages: number; content_snapshots: number; keyword_opportunities?: number; last_gsc_sync?: string | null };
export type GscSyncStatus = {
  site_id: string; property: string | null; authorized: boolean;
  status: 'never' | 'queued' | 'running' | 'succeeded' | 'completed_with_errors' | 'failed' | 'not_authorized' | string;
  step: string | null; step_fa: string | null; progress: number;
  started_at: string | null; finished_at: string | null; items: Record<string, unknown>; errors: string[];
  steps: WpSyncStep[]; run_id: string | null; job_id: string | null; job: { run_id: string; status: string; error?: string | null } | null;
  coverage: GscSyncCoverage; steps_fa: Record<string, string>;
};
export type GoogleAccountStatus = { connected: boolean; email: string | null; scopes: string[]; expiry: string | null; gsc_scope: boolean; ga4_scope: boolean; client_configured: boolean; client_id_hint?: string | null; connected_at?: string | null };
export type Ga4Property = { property_id: string; display_name: string | null; account: string | null; website_url?: string | null };
export type Ga4Properties = { status: 'ok' | 'not_configured' | 'not_authorized' | 'error' | string; properties: Ga4Property[]; message?: string };
export type Ga4SyncCoverage = { date_from: string | null; date_to: string | null; rows: number; pages: number; sessions: number; users: number; conversions: number; content_snapshots: number; last_ga4_sync?: string | null; top_pages: { path: string; sessions: number; conversions: number }[] };
export type Ga4SyncStatus = {
  site_id: string; property: string | null; authorized: boolean;
  status: 'never' | 'queued' | 'running' | 'succeeded' | 'completed_with_errors' | 'failed' | 'not_authorized' | string;
  step: string | null; step_fa: string | null; progress: number;
  started_at: string | null; finished_at: string | null; items: Record<string, unknown>; errors: string[];
  steps: WpSyncStep[]; run_id: string | null; job_id: string | null; job: { run_id: string; status: string; error?: string | null } | null;
  coverage: Ga4SyncCoverage; steps_fa: Record<string, string>;
};
export type SaGscProperty = { property: string; permission: string | null };
export type SaGscStatus = { configured: boolean; service_account_email: string | null; accessible_properties: SaGscProperty[]; last_check: string | null };
export type SaGscCheck = { status: 'ok' | 'not_configured' | 'error' | string; service_account_email: string | null; properties: SaGscProperty[]; message?: string; checked_at?: string };
export type AutoSyncSource = { configured: boolean; last_success: string | null; next_at: string | null; due: boolean };
export type AutoSyncPlan = { site_id: string; enabled: boolean; interval_hours: number; sources: Record<'wordpress' | 'gsc' | 'ga4', AutoSyncSource> };
export type IntegrationBlock = {
  kind: 'wordpress' | 'gsc' | 'ga4' | string; label: string;
  connection: { status: string; tested_at: string | null; detail: Record<string, unknown> };
  sync: { status: string; last_run: string | null; progress: number; step: string | null; step_fa: string | null; run_id: string | null; coverage: Record<string, unknown>; error: string | null };
  configured: boolean; property?: string | null; authorized?: boolean; actions: string[];
};
export type IntegrationsSummary = { site_id: string; integrations: IntegrationBlock[] };
export type ConnectionsStatus = {
  site_id: string;
  configured: { gsc: string | null; ga4: string | null; wordpress: string | null };
  status: Partial<Record<ConnectionKind, ConnectionResult>>;
  wordpress_auth?: WpAuthStatus;
};
export type GscProperties = { status: string; message?: string; properties: { property: string; permission: string }[] };
export type InitializeResult = {
  site_id: string;
  workspace: { path: string; created: string[]; existed: boolean };
  memory: { initialized: boolean; existed: boolean; updated_at: string | null };
  graph: { site_node: string; existed: boolean; nodes: number; edges: number };
};
export type GraphNode = { id: string; site_id: string; type: string; metadata: { label?: string; url?: string | null; pagerank?: number | null; community?: number | null; vault_path?: string | null; props?: Record<string, unknown> } & Record<string, unknown> };
export type GraphEdge = { source: string; target: string; relation_type: string; weight: number; metadata: { edge_id?: string; props?: Record<string, unknown> }; site_id: string };
export type GraphMode = { key: 'seo' | 'content' | 'links' | 'planner'; title_fa: string; description_fa: string; layout: string; group_by: string; node_types: string[]; relation_types: string[] };
export type GraphView = { mode: GraphMode; nodes: GraphNode[]; edges: GraphEdge[]; truncated: boolean; total_nodes: number; stats: { by_type: Record<string, number>; by_relation: Record<string, number> } };
export type NodeDetails = Record<string, unknown> & { id: string; type: string; label: string; url: string | null; pagerank: number | null; community: number | null; props: Record<string, unknown>; degree: number };
// phase 5 — keywords
export type KeywordGsc = { clicks: number; impressions: number; ctr: number; position: number | null; top_page: string | null; pages_count: number } | null;
export type KeywordRow = {
  id: number; site_id: string; keyword: string; normalized: string; intent: string | null; cluster_id: string | null; topic: string | null;
  volume: number | null; difficulty: number | null; priority: string | null; target_url: string | null; status: string; source: string | null;
  notes: string | null; created_at: string; updated_at: string; gsc: KeywordGsc; cluster: { cluster_id: string; name: string; topic: string | null } | null;
};
export type KeywordDetail = KeywordRow & { gsc_pages: { page: string; clicks: number; impressions: number; position: number }[]; opportunities: KeywordOpportunity[] };
export type KeywordCounts = { total: number; by_status: Record<string, number>; by_intent: Record<string, number>; clusters: number; with_target: number; opportunities_new: Record<string, number> };
export type KeywordList = { items: KeywordRow[]; total: number; limit: number; offset: number; counts: KeywordCounts };
export type KeywordCluster = { site_id: string; cluster_id: string; name: string; topic: string | null; keywords_count: number; method: string | null; created_at: string | null; updated_at: string | null };
export type TopicMap = { clusters: (KeywordCluster & { members: KeywordRow[]; gsc: { impressions: number; clicks: number; avg_position: number | null; with_data: number }; targets: string[]; volume: number })[]; unclustered: KeywordRow[]; counts: KeywordCounts };
export type KeywordOpportunity = { id: number; site_id: string; keyword_id: number; kind: string; kind_fa?: string; keyword?: string | null; keyword_status?: string | null; target_url: string | null; score: number; reason: string; evidence: Record<string, unknown>; status: string; run_id: string | null; created_at: string; updated_at: string };
export type ImportResult = { format: string; columns: string[]; mapping: Record<string, string>; unmapped_columns: string[]; rows_total: number; rows_valid: number; rows_imported: number; rows_updated: number; rows_skipped: number; errors: { row: number; error: string }[]; errors_count: number; preview: Record<string, unknown>[]; import_id: number | null; dry_run: boolean };
export type KeywordsMeta = { intents: string[]; priorities: string[]; statuses: string[]; opportunity_kinds: { kind: string; fa: string }[]; opportunity_statuses: string[] };
// phase 6 — content brain + ai providers
export type ContentStatus = 'planned' | 'brief_ready' | 'writing' | 'review' | 'approved' | 'published';
export type ContentItem = {
  id: number; site_id: string; title: string; slug: string | null; target_keyword_id: number | null; target_keyword: string | null; topic: string | null;
  cluster_id: string | null; intent: string | null; status: ContentStatus; status_fa: string; priority: string | null; publish_date: string | null; publish_time: string | null;
  ai_provider: string | null; ai_model: string | null; url: string | null; wp_post_id: number | null; brief_id: number | null; metadata: Record<string, unknown>;
  notes: string | null; created_at: string; updated_at: string; allowed_transitions: ContentStatus[]; has_brief: boolean;
  current_draft_id?: number | null; latest_score?: number | null; review_status?: string;
};
export type ContentBrief = {
  id: number; content_id: number; version: number; h1: string | null; seo_title: string | null; meta_description: string | null; intent: string | null;
  outline: { h2: string; h3: string[]; why?: string }[]; entities: { type: string; label: string; node_id: string }[]; questions: { question: string; source: string }[];
  internal_links: { url: string; anchor: string; reason: string; node_id: string | null }[]; sources: Record<string, unknown>; markdown: string | null; provenance: Record<string, unknown>; created_at: string;
};
export type ContentDetail = ContentItem & { brief: ContentBrief | null; briefs: { id: number; version: number; created_at: string; provenance: Record<string, unknown> }[]; events: { id: number; from_status: string | null; to_status: string | null; actor: string; note: string | null; created_at: string }[]; keyword?: KeywordRow & { gsc: KeywordGsc } };
export type ContentCounts = { total: number; by_status: Record<ContentStatus, number>; scheduled: number };
export type ContentBoard = { columns: { status: ContentStatus; status_fa: string; items: ContentItem[] }[]; counts: ContentCounts };
export type ContentCalendar = { from: string; to: string; days: Record<string, ContentItem[]>; unscheduled: ContentItem[]; counts: ContentCounts };
export type ContentMeta = { statuses: { key: ContentStatus; fa: string; next: ContentStatus[] }[]; priorities: string[] };
export type ProviderKind = { kind: string; label: string; base_url: string; models: string[]; needs_key: boolean; is_gateway?: boolean; setup?: { console_url: string; key_prefix: string; docs: string; fa: string }; auth_type?: 'api_key' | 'optional_api_key'; requires_base_url?: boolean; supports_model_discovery?: boolean; capabilities?: string[]; env_key?: string; env_model?: string };
export type RecommendedRoute = { task_kind: string; provider_id: number; provider_name: string; model: string; fallback_model: string | null; policy: string };
export type ProviderConfig = { id: number; name: string; kind: string; kind_label: string; base_url: string | null; default_model: string | null; models: string[]; enabled: boolean; has_key: boolean; key_hint: string | null; last_test: { ok: boolean; status: string; message: string; tested_at: string; models_found?: string[] } | null; created_at: string; updated_at: string; is_gateway?: boolean; route_kind?: 'direct' | 'gateway'; endpoint_url?: string | null; configured?: boolean };
export type GatewayStatus = { provider_id: number; name: string; kind: string; is_gateway: boolean; endpoint_url: string | null; status: 'connected' | 'error' | 'untested' | 'missing_credentials'; has_key: boolean; last_test: any; health: Record<string, any> | null; breaker_open: boolean; capabilities: Record<string, any>; adapter_health: Record<string, any> | null; routing: { last_decision: Record<string, string> | null; primary_for: string[]; auto_models: string[]; models_available: number; models: string[] }; fallback: { fallback_for: string[]; chain_fallback: string; upstream?: string | null }; recent_calls: { id: number; model: string; ok: number; latency_ms: number; cost_usd: number; task_kind: string; created_at: string; error: string | null }[] };
export type TaskRoute = { task_kind: string; site_id: string; provider_id: number | null; model: string | null; fallback_provider_id: number | null; fallback_model: string | null; provider_name: string | null; fallback_provider_name: string | null; updated_at: string | null; policy?: 'explicit' | 'auto' | 'echo'; fallbacks?: { provider_id: number; model: string; provider_name?: string | null }[] };
// phase 7 — content intelligence
export type ContentDraft = { id: number; content_id: number; version: number; title: string | null; meta_description: string | null; format: string; body?: string; body_text?: string; word_count: number; structure: { h1: string[]; h2: string[]; h3: string[]; paragraphs: string[]; links: { href: string; anchor: string }[]; images: { src: string; alt: string }[]; questions: string[]; faq: boolean; word_count: number }; source: string; author: string | null; revision_of: number | null; change_summary: string | null; provenance: Record<string, unknown>; review_status: string; created_at: string };
export type ScoreFinding = { rule: string; dim: string; passed: boolean; weight: number; evidence: string; fix_fa: string };
export type ContentScore = { id?: number; draft_id?: number; version?: number; total: number; dims: Record<string, number>; dims_fa: Record<string, string>; findings: ScoreFinding[]; failed: ScoreFinding[]; weights: Record<string, number>; engine_version: string; label: string; thresholds?: { ready: number; needs_work: number } };
export type ReviewFinding = { code: string; severity: 'high' | 'medium' | 'low'; area: string; message_fa: string; evidence: string; suggestion_fa: string; auto_fixable: boolean; paragraph_index: number | null };
export type ContentReview = { id: number; draft_id: number; version: number; review_status: string; score: ContentScore; findings: ReviewFinding[]; counts: { high: number; medium: number; low: number }; summary_fa: string; provenance: Record<string, unknown>; gate: string };
export type ScoringSettings = { weights: Record<string, number>; thresholds: { ready: number; needs_work: number }; min_words: Record<string, number>; min_internal_links: number; review_gate: 'strict' | 'advisory' };
export type AnalyticsSettings = { min_impressions: number; min_clicks: number; min_age_days: number; windows: string[] };
export type ContentInsight = { id: number; category: string; feature: string; value: string; metric: string; effect: number; baseline: number | null; n: number; impressions: number; clicks: number; confidence: number | null; message_fa: string; evidence: Record<string, unknown>; status: string; memory_pattern_ref: string | null; created_at: string };
export type AnalyticsOverview = { window: string; rows: { content_id: number; title: string; status: string; publish_date: string | null; url: string; date: string; clicks: number; impressions: number; ctr: number; position: number | null; delta: Record<string, number | null>; top_queries: { query: string; impressions: number }[] }[]; totals: { contents: number; clicks: number; impressions: number; ctr: number }; gates: AnalyticsSettings };
// phase 8 — internal linking
export type LinkSuggestion = { id: number; scope: string; kind: string; kind_fa: string; source_node_id: string; source_url: string | null; source_title: string | null; source_stage: string | null; target_node_id: string; target_url: string | null; target_title: string | null; target_stage: string | null; anchor: string | null; anchor_alternatives: string[]; placement_hint: string | null; score: number; confidence: 'low' | 'recommended' | 'high'; confidence_fa: string; score_breakdown: Record<string, any>; reason_fa: string | null; evidence: Record<string, any>; status: 'new' | 'accepted' | 'dismissed' | 'done'; content_task_id: number | null; run_id: string | null; created_at: string; updated_at: string };
export type LinkPageStat = { node_id: string; url: string | null; title: string | null; stage: string | null; inbound_total: number; inbound_body: number; inbound_nav_only: number; unique_sources: number; outbound_body: number; outbound_total: number; anchor_distribution: { anchor: string; count: number }[]; exact_match_ratio: number; generic_ratio: number; flags: string[]; flags_fa?: string[]; pagerank: number | null; health_score: number; health_breakdown: Record<string, number>; computed_at: string };
export type LinkPattern = { id: number; pattern_key: string; feature: Record<string, string>; accepted: number; dismissed: number; done: number; acceptance_rate: number; message_fa: string; status: string; memory_pattern_ref: string | null };
export type LinkSummary = { by_status: Record<string, number>; by_kind: Record<string, number>; by_confidence: Record<string, number>; pages: number; flags: Record<string, number>; avg_health: number | null; settings: Record<string, any> };
export type LinkAnalyzeResult = { mode: 'sync' | 'job'; run_id: string; pages?: number; targets?: number; suggestions?: number; by_confidence?: Record<string, number>; supports_edges?: number; created?: number; graph?: Record<string, number>; stats?: Record<string, number | null>; status?: string };
// phase 9 — ai orchestration
export type AiModel = { id: number; provider_id: number; provider: string | null; kind: string | null; model_id: string; display: string | null; tier: string; tags: string[]; context_tokens: number | null; price_in_per_m: number; price_out_per_m: number; enabled: boolean; source: string };
export type RoutingDecision = { chain: { provider: string; model: string; reason: string }[]; reason: string; policy: string; candidates: any[] };
export type Budget = { month: string; limit_usd: number; spent_usd: number; ratio: number; state: 'ok' | 'warning' | 'soft_limit' | 'hard_stop'; thresholds: Record<string, number> };
export type Usage = { group_by: string; rows: { key: string; calls: number; input_tokens: number; output_tokens: number; cost_usd: number; avg_latency_ms: number; ok: number }[]; by_day: { date: string; cost_usd: number; calls: number }[]; budget: Budget };
export type PromptVersion = { id: number; prompt_id: number; version: number; template: string; variables: string[]; model_hints: Record<string, any>; is_active: number; approval: string; approved_by: string | null; changelog: string | null; created_at: string; key?: string; ref?: string };
export type Prompt = { id: number; key: string; scope: string; site_id: string | null; title: string; description: string | null; tags: string[]; versions: PromptVersion[]; active_version: number | null; performance?: { version_id: number; version: number; tests: number; avg_score: number | null; avg_rating: number | null; avg_cost_usd: number | null; avg_latency_ms: number | null }[]; tests?: any[] };
export type GenerationRun = { id: number; run_id: string; site_id: string; content_id: number; mode: string; status: string; step: string | null; step_fa?: string; steps: { key: string; agent: string; status: string; artifact_id?: number | null; provenance?: Record<string, any>; error?: string | null; words?: number; validation_ok?: boolean; fact_check?: string; sections?: number; draft_id?: number; score?: number; review_status?: string }[]; models: Record<string, { provider: string; model: string }>; prompt_versions: Record<string, number>; memory_snapshot_id: number | null; estimate: Record<string, any>; actual: Record<string, any>; draft_id: number | null; score: number | null; review_status: string | null; error: string | null; created_at: string; artifacts?: { id: number; step: string; agent: string; version: number; payload: Record<string, any>; provenance: Record<string, any> }[] };
export type GenEstimate = { per_agent: Record<string, { input_tokens: number; output_tokens: number; cost_usd: number; provider?: string; model?: string; route?: any[]; reason?: string; prompt?: string; sections?: number }>; total: { input_tokens: number; output_tokens: number; cost_usd: number }; sections: number; budget: Budget; memory_snapshot_id: number };
export type AiInsight = { id: number; site_id: string | null; category: string; feature: string; value: string; metric: string; effect: number; baseline: number | null; n: number; confidence: number | null; message_fa: string; evidence: Record<string, any>; recommendation: Record<string, any>; status: string; memory_pattern_ref: string | null };
// phase 8.5 — content strategy planner
export type PlanStatus = 'planned' | 'researching' | 'brief_ready' | 'writing' | 'review' | 'approved' | 'published';
export type PlanColumn = { key: string; fa: string; group: 'basic' | 'seo' | 'advanced'; editable: boolean; type: string; options?: string[] };
export type PlanMeta = { statuses: { key: PlanStatus; fa: string; item_status: string }[]; transitions: Record<string, string[]>; page_types: { key: string; fa: string }[]; intents: { key: string; fa: string }[]; priorities: { key: string; fa: string }[]; funnel_stages: { key: string; fa: string }[]; content_gaps: { key: string; fa: string }[]; keyword_roles: { key: string; fa: string }[]; category_sources: { key: string; fa: string }[]; recommendation_kinds: { key: string; fa: string }[]; generation_job_kinds: string[]; columns: PlanColumn[]; export_columns: string[]; views: string[]; publishing: { enabled: boolean; note: string }; ai_generation: { enabled: boolean; note: string } };
export type PlanCategory = { id: number; site_id: string; source: 'wordpress' | 'brain' | 'manual'; source_fa: string; wordpress_category_id: number | null; parent_id: number | null; name: string; slug: string | null; url: string | null; description: string | null; post_count: number; page_count: number; keyword_count: number; plan_count: number; coverage_score: number | null; intelligence: Record<string, any>; metadata: Record<string, any>; synced_at: string | null; children?: PlanCategory[]; plans?: ContentPlan[] };
export type PlanRecommendation = { engine?: string; action: string; action_fa?: string; title?: string; page_type?: string; intent?: string; serp_intent?: string; funnel_stage?: string; priority?: string; priority_score?: number; reasons_fa: string[]; gaps_fa?: string[]; confidence?: number; content_gap?: string; cannibalization_risk?: number; cannibalization?: any[]; ranking_url?: string | null; ranking_position?: number | null; traffic_opportunity?: number | null; existing_pages?: any[]; category?: any; mapping?: { type: 'new' | 'attach'; plan_id?: number; plan_title?: string; role?: string; url?: string | null } };
export type ContentPlan = { id: number; site_id: string; content_item_id: number | null; title: string; url: string | null; slug: string | null; intent: string | null; serp_intent: string | null; page_type: string | null; funnel_stage: string | null; category_id: number | null; category_suggested_id: number | null; category_reason: string | null; primary_keyword_id: number | null; primary_keyword: string | null; secondary_keywords: string[]; heading_structure: { level: number; text: string }[]; seo_title: string | null; meta_description: string | null; topic_id: string | null; cluster_id: string | null; content_cluster_id: number | null; search_volume: number | null; keyword_difficulty: number | null; priority: string | null; priority_score: number | null; ai_priority: number | null; business_value: number | null; traffic_opportunity: number | null; content_gap: string | null; cannibalization_risk: number | null; cannibalization: any[]; ranking_url: string | null; ranking_position: number | null; target_audience: string | null; publish_date: string | null; publish_time: string | null; status: PlanStatus; status_fa: string; page_type_fa: string | null; intent_fa: string | null; priority_fa: string | null; existing_pages: { node_id: string | null; url: string; title: string; position?: number | null; relation?: string }[]; link_targets: { direction: 'from' | 'to'; node_id: string; url: string; title: string; anchor: string; reason_fa: string; score: number }[]; graph_connections: number; content_score: number | null; recommendation_id: number | null; recommendation: PlanRecommendation | Record<string, never>; publishing: Record<string, any>; metadata: Record<string, any>; notes: string | null; source: string | null; created_by: string | null; created_at: string; updated_at: string; allowed_transitions: PlanStatus[]; category: { id: number; name: string; source: string; parent_id: number | null } | null; parent_category: string | null; category_suggested: { id: number; name: string; reason: string | null } | null; content_item: { id: number; status: string; has_brief: boolean; url: string | null; latest_score: number | null; review_status: string; draft_count: number } | null; keywords: { id: number; keyword: string; role: string; volume: number | null; intent: string | null }[]; events?: any[]; recommendations?: any[]; generation_jobs?: any[] };
export type PlanList = { items: ContentPlan[]; total: number; counts: { total: number; by_status: Record<string, number>; by_priority: Record<string, number>; by_category: Record<string, number>; by_page_type: Record<string, number>; unscheduled: number } };
export type PlanSuggestion = { id: number; site_id: string; plan_id: number | null; keyword_id: number | null; category_id: number | null; kind: string; kind_fa: string; action: string | null; title: string | null; page_type: string | null; intent: string | null; priority: string | null; priority_score: number | null; confidence: number | null; reasons: string[]; payload: Record<string, any>; version: number; status: string; engine: string; computed_at: string; plan_title?: string | null; created_plan?: { id: number; title: string } };
export type PlanImportResult = { import_id: number; format: string; columns: string[]; mapping: Record<string, string>; unmapped_columns: string[]; rows: number; created: number; updated: number; skipped: number; errors: any[]; preview: any[]; dry_run: boolean; key_columns: string[]; source?: string; url?: string };
export type PlanSource = { id: number; site_id: string; kind: string; name: string; url: string | null; sheet_id: string | null; gid: string | null; mapping: Record<string, string>; key_columns: string[]; enabled: boolean; auto_sync: boolean; status: string | null; last_sync_at: string | null; last_result: Record<string, any> };
// ai content test workspace
export type WsProviderStatus = 'connected' | 'error' | 'untested' | 'missing_credentials' | 'offline_fallback';
export type WsProvider = { name: string; kind: string; kind_label: string | null; configured: boolean; route_kind?: 'direct' | 'gateway' | 'offline'; enabled: boolean; has_key: boolean; default_model: string | null; status: WsProviderStatus; last_test: { ok: boolean | null; message: string | null; tested_at: string | null } | null; models: { model_id: string; display: string; tier: string; price_in_per_m: number; price_out_per_m: number }[]; health: Record<string, any> };
export type WsOptions = { providers: WsProvider[]; default: { provider: string; model: string | null; kind: string }; auto_route: RoutingDecision; content_types: { key: string; fa: string }[]; tones: { key: string; fa: string }[]; intents: string[]; steps: { key: string; fa: string; implemented: boolean }[]; budget: Budget; prompt: string | null };
export type WsSpec = { title: string; keyword: string; secondary_keywords: string[]; intent: string; content_type: string; category?: string | null; audience?: string | null; tone: string; word_count: number; instructions?: string | null; provider?: string | null; model?: string | null };
export type WsEstimate = { provider: string; model: string; input_tokens: number; output_tokens: number; cost_usd: number; exact?: boolean; route: { provider: string; model: string; reason: string }[]; reason: string; policy: string; prompt_ref: string; memory_snapshot_id: number; max_tokens: number; budget: Budget };
export type WsResult = { ok: boolean; run_id: string; step: string; result: { title: string; meta_description?: string; h1?: string; sections: { h2: string; h3?: any[]; paragraphs?: string[] }[]; faq?: { question: string; answer: string }[]; internal_links?: { anchor: string; target_topic?: string; target?: string }[]; keywords_used?: string[]; notes?: string; markdown: string; word_count: number; _placeholder?: boolean }; seo: { score: { total: number | null; dims?: Record<string, number>; failed?: any[]; label?: string; weights?: Record<string, number> }; checks: { key: string; fa: string; ok: boolean; value?: number }[]; passed: number; total_checks: number; word_count: number; h2: string[]; h3_count: number; keyword_density: number; secondary_keywords: { keyword: string; used: boolean }[]; forbidden_claims_found: string[]; questions: string[]; keywords_used: string[] }; prompt: { system: string; user: string; ref: string; prompt_version_id: number | null; memory_snapshot_id: number; schema: Record<string, any> }; meta: { provider: string; provider_kind?: string; model: string; input_tokens: number; output_tokens: number; cost_usd: number; latency_ms: number; elapsed_ms: number; attempts: any[]; route: any[]; route_reason: string; policy: string; placeholder: boolean; task_kind: string; run_id: string; prompt_version?: string | null; prompt_version_id?: number | null; memory_snapshot_id?: number | null; stop_reason?: string | null; streamed?: boolean; gateway_decision?: Record<string, string> | null; served_model?: string | null; budget: Budget; raw_excerpt: string | null } };
export type SiteCreateBody = Schemas['SiteCreate'];
export type SiteUpdateBody = Schemas['SiteUpdate'];
export type MemoryUpdateBody = Schemas['MemoryUpdate'];
export type JobRun = {
  run_id: string;
  type: string;
  site_id: string | null;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | string;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: unknown;
  error: string | null;
};

export const endpoints = {
  health: () => api<Health>('/health'),
  jobs: (limit = 50) => api<JobRun[]>(`/jobs?limit=${limit}`),
  job: (runId: string) => api<JobRun>(`/jobs/${encodeURIComponent(runId)}`),
  portfolioOverview: () => api<PortfolioOverview>('/portfolio/overview', { cacheSeconds: 10 }),
  sites: () => api<Site[]>('/sites', { cacheSeconds: 10 }),
  site: (id: string) => api<Site>(`/sites/${encodeURIComponent(id)}`, { cacheSeconds: 5 }),
  graphSummary: (id: string) => api<GraphSummary>(`/sites/${encodeURIComponent(id)}/graph/summary`, { cacheSeconds: 10 }),
  memory: (id: string) => api<SiteMemory>(`/sites/${encodeURIComponent(id)}/memory`, { cacheSeconds: 5 }),
  // phase 3 — sites management
  createSite: (body: SiteCreateBody) => api<Site>('/sites', { method: 'POST', json: body }),
  updateSite: (id: string, body: SiteUpdateBody) => api<Site>(`/sites/${encodeURIComponent(id)}`, { method: 'PATCH', json: body }),
  deleteSite: (id: string, force = false) => api<{ deleted: string }>(`/sites/${encodeURIComponent(id)}${force ? '?force=true' : ''}`, { method: 'DELETE' }),
  connections: (id: string) => api<ConnectionsStatus>(`/sites/${encodeURIComponent(id)}/connections`, { cacheSeconds: 3 }),
  testConnection: (id: string, kind: ConnectionKind, property?: string | null, extra?: { wp_username?: string | null; wp_app_password?: string | null; clear_wp_credentials?: boolean }) =>
    api<ConnectionResult>(`/sites/${encodeURIComponent(id)}/connections/${kind}/test`, { method: 'POST', json: { property: property || null, ...extra } }),
  gscProperties: () => api<GscProperties>('/connections/gsc/properties'),
  initializeSite: (id: string) => api<InitializeResult>(`/sites/${encodeURIComponent(id)}/initialize`, { method: 'POST' }),
  saGscStatus: () => api<SaGscStatus>('/connections/gsc/service-account/status'),
  saGscCheck: () => api<SaGscCheck>('/connections/gsc/service-account/check', { method: 'POST' }),
  autoSyncGet: (id: string) => api<AutoSyncPlan>(`/sites/${encodeURIComponent(id)}/auto-sync`),
  autoSyncPut: (id: string, body: { enabled?: boolean; interval_hours?: number }) => api<AutoSyncPlan>(`/sites/${encodeURIComponent(id)}/auto-sync`, { method: 'PUT', json: body }),
  integrations: (id: string) => api<IntegrationsSummary>(`/sites/${encodeURIComponent(id)}/integrations`),
  // WordPress → sync → graph pipeline (job-based; never inline)
  wpSyncStart: (id: string, body: { crawl?: boolean; max_urls?: number | null } = {}) => api<WpSyncQueued>(`/sites/${encodeURIComponent(id)}/wordpress/sync`, { method: 'POST', json: body }),
  wpSyncStatus: (id: string) => api<WpSyncStatus>(`/sites/${encodeURIComponent(id)}/wordpress/sync/status`),
  graphRebuild: (id: string) => api<WpSyncQueued>(`/sites/${encodeURIComponent(id)}/graph/rebuild`, { method: 'POST' }),
  // GSC → sync → graph pipeline (job-based; never inline)
  gscSyncStart: (id: string, body: { days?: number | null } = {}) => api<WpSyncQueued>(`/sites/${encodeURIComponent(id)}/gsc/sync`, { method: 'POST', json: body }),
  gscSyncStatus: (id: string) => api<GscSyncStatus>(`/sites/${encodeURIComponent(id)}/gsc/sync/status`),
  googleStatus: () => api<GoogleAccountStatus>('/connections/google/status'),
  googleAuthorize: () => api<{ url: string; redirect_uri: string }>('/connections/google/authorize'),
  googleClientSave: (client_id: string, client_secret: string) => api<{ configured: boolean; client_id_hint: string | null }>('/connections/google/client', { method: 'PUT', json: { client_id, client_secret } }),
  googleDisconnect: () => api<{ disconnected: boolean; revoked: boolean }>('/connections/google', { method: 'DELETE' }),
  ga4Properties: () => api<Ga4Properties>('/connections/ga4/properties'),
  ga4SyncStart: (id: string, body: { days?: number | null } = {}) => api<WpSyncQueued>(`/sites/${encodeURIComponent(id)}/ga4/sync`, { method: 'POST', json: body }),
  ga4SyncStatus: (id: string) => api<Ga4SyncStatus>(`/sites/${encodeURIComponent(id)}/ga4/sync/status`),
  // phase 4 — graph command center
  graphModes: (id: string) => api<GraphMode[]>(`/sites/${encodeURIComponent(id)}/graph/modes`),
  graphView: (id: string, params: { mode: string; types?: string[]; relation_types?: string[]; limit?: number; include_isolated?: boolean }) => {
    const q = new URLSearchParams({ mode: params.mode });
    if (params.types?.length) q.set('types', params.types.join(','));
    if (params.relation_types?.length) q.set('relation_types', params.relation_types.join(','));
    if (params.limit) q.set('limit', String(params.limit));
    if (params.include_isolated === false) q.set('include_isolated', 'false');
    return api<GraphView>(`/sites/${encodeURIComponent(id)}/graph/view?${q.toString()}`);
  },
  nodeDetails: (id: string, nodeId: string) => api<NodeDetails>(`/sites/${encodeURIComponent(id)}/graph/node-details/${encodeURIComponent(nodeId)}`),
  // phase 5 — keywords
  keywords: (id: string, params: Record<string, string | number | undefined> = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && q.set(k, String(v)));
    return api<KeywordList>(`/sites/${encodeURIComponent(id)}/keywords?${q.toString()}`);
  },
  keyword: (id: string, kid: number) => api<KeywordDetail>(`/sites/${encodeURIComponent(id)}/keywords/${kid}`),
  createKeyword: (id: string, body: Record<string, unknown>) => api<KeywordRow>(`/sites/${encodeURIComponent(id)}/keywords`, { method: 'POST', json: body }),
  updateKeyword: (id: string, kid: number, body: Record<string, unknown>) => api<KeywordRow>(`/sites/${encodeURIComponent(id)}/keywords/${kid}`, { method: 'PATCH', json: body }),
  deleteKeyword: (id: string, kid: number) => api<{ deleted: number }>(`/sites/${encodeURIComponent(id)}/keywords/${kid}`, { method: 'DELETE' }),
  keywordsMeta: (id: string) => api<KeywordsMeta>(`/sites/${encodeURIComponent(id)}/keywords/meta`),
  importKeywords: (id: string, file: File, opts: { dryRun: boolean; mapping?: Record<string, string> }) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('dry_run', opts.dryRun ? 'true' : 'false');
    if (opts.mapping) fd.append('mapping', JSON.stringify(opts.mapping));
    return api<ImportResult>(`/sites/${encodeURIComponent(id)}/keywords/import`, { method: 'POST', body: fd });
  },
  keywordClusters: (id: string) => api<KeywordCluster[]>(`/sites/${encodeURIComponent(id)}/keywords/clusters`),
  runClustering: (id: string, threshold?: number) => api<Record<string, unknown>>(`/sites/${encodeURIComponent(id)}/keywords/cluster${threshold ? `?threshold=${threshold}` : ''}`, { method: 'POST' }),
  updateCluster: (id: string, cid: string, body: { name?: string; topic?: string }) => api<KeywordCluster>(`/sites/${encodeURIComponent(id)}/keywords/clusters/${encodeURIComponent(cid)}`, { method: 'PATCH', json: body }),
  topicMap: (id: string) => api<TopicMap>(`/sites/${encodeURIComponent(id)}/keywords/topic-map`),
  analyzeKeywords: (id: string) => api<Record<string, unknown>>(`/sites/${encodeURIComponent(id)}/keywords/analyze`, { method: 'POST' }),
  keywordOpportunities: (id: string, params: Record<string, string | number | undefined> = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && q.set(k, String(v)));
    return api<{ items: KeywordOpportunity[]; total: number }>(`/sites/${encodeURIComponent(id)}/keywords/opportunities?${q.toString()}`);
  },
  setOpportunityStatus: (id: string, oid: number, status: string) => api<KeywordOpportunity>(`/sites/${encodeURIComponent(id)}/keywords/opportunities/${oid}`, { method: 'PATCH', json: { status } }),
  syncKeywordGraph: (id: string) => api<Record<string, unknown>>(`/sites/${encodeURIComponent(id)}/keywords/sync-graph`, { method: 'POST' }),
  // phase 6 — content brain
  contentMeta: (id: string) => api<ContentMeta>(`/sites/${encodeURIComponent(id)}/content/meta`),
  contentList: (id: string, params: Record<string, string | number | undefined> = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && q.set(k, String(v)));
    return api<{ items: ContentItem[]; total: number; counts: ContentCounts }>(`/sites/${encodeURIComponent(id)}/content?${q.toString()}`);
  },
  contentBoard: (id: string) => api<ContentBoard>(`/sites/${encodeURIComponent(id)}/content/board`),
  contentCalendar: (id: string, from: string, to: string) => api<ContentCalendar>(`/sites/${encodeURIComponent(id)}/content/calendar?from=${from}&to=${to}`),
  content: (id: string, cid: number) => api<ContentDetail>(`/sites/${encodeURIComponent(id)}/content/${cid}`),
  createContent: (id: string, body: Record<string, unknown>) => api<ContentItem>(`/sites/${encodeURIComponent(id)}/content`, { method: 'POST', json: body }),
  contentFromOpportunity: (id: string, oid: number) => api<ContentItem>(`/sites/${encodeURIComponent(id)}/content/from-opportunity/${oid}`, { method: 'POST' }),
  updateContent: (id: string, cid: number, body: Record<string, unknown>) => api<ContentItem>(`/sites/${encodeURIComponent(id)}/content/${cid}`, { method: 'PATCH', json: body }),
  transitionContent: (id: string, cid: number, status: ContentStatus, note?: string) => api<ContentItem>(`/sites/${encodeURIComponent(id)}/content/${cid}/transition`, { method: 'POST', json: { status, note } }),
  deleteContent: (id: string, cid: number) => api<{ deleted: number }>(`/sites/${encodeURIComponent(id)}/content/${cid}`, { method: 'DELETE' }),
  generateBrief: (id: string, cid: number, opts: { use_ai?: boolean; mark_ready?: boolean } = {}) => api<ContentBrief>(`/sites/${encodeURIComponent(id)}/content/${cid}/brief`, { method: 'POST', json: { use_ai: !!opts.use_ai, mark_ready: opts.mark_ready ?? true } }),
  syncContentGraph: (id: string) => api<Record<string, unknown>>(`/sites/${encodeURIComponent(id)}/content/sync-graph`, { method: 'POST' }),
  // phase 7 — content intelligence
  contentDrafts: (id: string, cid: number) => api<ContentDraft[]>(`/sites/${encodeURIComponent(id)}/content/${cid}/drafts`),
  contentDraft: (id: string, cid: number, did: number) => api<ContentDraft>(`/sites/${encodeURIComponent(id)}/content/${cid}/drafts/${did}`),
  createDraft: (id: string, cid: number, body: Record<string, unknown>) => api<ContentDraft>(`/sites/${encodeURIComponent(id)}/content/${cid}/drafts`, { method: 'POST', json: body }),
  scoreContent: (id: string, cid: number, draftId?: number) => api<ContentScore>(`/sites/${encodeURIComponent(id)}/content/${cid}/score${draftId ? `?draft_id=${draftId}` : ''}`, { method: 'POST' }),
  reviewContent: (id: string, cid: number, opts: { draft_id?: number; use_ai?: boolean } = {}) => api<ContentReview>(`/sites/${encodeURIComponent(id)}/content/${cid}/review`, { method: 'POST', json: opts }),
  contentIntelligence: (id: string, cid: number) => api<{ drafts: ContentDraft[]; scores: Record<string, unknown>[]; reviews: (Record<string, unknown> & { findings: ReviewFinding[]; counts: Record<string, number> })[] }>(`/sites/${encodeURIComponent(id)}/content/${cid}/intelligence`),
  scoringSettings: (id: string) => api<ScoringSettings>(`/sites/${encodeURIComponent(id)}/content/settings/scoring`),
  putScoringSettings: (id: string, body: Partial<ScoringSettings>) => api<ScoringSettings>(`/sites/${encodeURIComponent(id)}/content/settings/scoring`, { method: 'PUT', json: body }),
  contentInsights: (id: string, status?: string) => api<ContentInsight[]>(`/sites/${encodeURIComponent(id)}/content/insights${status ? `?status=${status}` : ''}`),
  setInsightStatus: (id: string, iid: number, status: string) => api<ContentInsight>(`/sites/${encodeURIComponent(id)}/content/insights/${iid}`, { method: 'PATCH', json: { status } }),
  analyticsOverview: (id: string) => api<AnalyticsOverview>(`/sites/${encodeURIComponent(id)}/content/analytics/overview`),
  analyticsSnapshot: (id: string) => api<Record<string, unknown>>(`/sites/${encodeURIComponent(id)}/content/analytics/snapshot`, { method: 'POST' }),
  analyticsLearn: (id: string) => api<{ samples: number; skipped: Record<string, number>; insights: ContentInsight[]; gates: Record<string, number> }>(`/sites/${encodeURIComponent(id)}/content/analytics/learn`, { method: 'POST' }),
  analyticsSettings: (id: string) => api<AnalyticsSettings>(`/sites/${encodeURIComponent(id)}/content/analytics/settings`),
  putAnalyticsSettings: (id: string, body: Partial<AnalyticsSettings>) => api<AnalyticsSettings>(`/sites/${encodeURIComponent(id)}/content/analytics/settings`, { method: 'PUT', json: body }),
  contentMetrics: (id: string, cid: number, window = '28d') => api<Record<string, unknown>[]>(`/sites/${encodeURIComponent(id)}/content/${cid}/metrics?window=${window}`),
  // phase 8 — internal linking
  linksAnalyze: (id: string) => api<LinkAnalyzeResult>(`/sites/${encodeURIComponent(id)}/links/analyze`, { method: 'POST' }),
  linksSummary: (id: string) => api<LinkSummary>(`/sites/${encodeURIComponent(id)}/links/summary`),
  linkSuggestions: (id: string, params: Record<string, string | number | undefined> = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && q.set(k, String(v)));
    return api<{ items: LinkSuggestion[]; total: number }>(`/sites/${encodeURIComponent(id)}/links/suggestions?${q.toString()}`);
  },
  setLinkSuggestion: (id: string, sid: number, body: { status: string; anchor?: string }) => api<LinkSuggestion>(`/sites/${encodeURIComponent(id)}/links/suggestions/${sid}`, { method: 'PATCH', json: body }),
  linkContentTask: (id: string, sid: number, body: { title?: string; note?: string }) => api<{ content_id: number; title: string; status: string; suggestion: LinkSuggestion }>(`/sites/${encodeURIComponent(id)}/links/suggestions/${sid}/content-task`, { method: 'POST', json: body }),
  linkPages: (id: string, params: Record<string, string | number | undefined> = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && q.set(k, String(v)));
    return api<{ items: LinkPageStat[]; total: number }>(`/sites/${encodeURIComponent(id)}/links/pages?${q.toString()}`);
  },
  linkPage: (id: string, nodeId: string) => api<LinkPageStat & { inbound: any[]; outbound: any[]; suggestions_to: LinkSuggestion[]; suggestions_from: LinkSuggestion[]; flags_fa: string[] }>(`/sites/${encodeURIComponent(id)}/links/pages/${encodeURIComponent(nodeId)}`),
  linkPatterns: (id: string, status?: string) => api<LinkPattern[]>(`/sites/${encodeURIComponent(id)}/links/patterns${status ? `?status=${status}` : ''}`),
  setLinkPattern: (id: string, pid: number, status: string) => api<LinkPattern>(`/sites/${encodeURIComponent(id)}/links/patterns/${pid}`, { method: 'PATCH', json: { status } }),
  linkSettings: (id: string) => api<Record<string, any>>(`/sites/${encodeURIComponent(id)}/links/settings`),
  putLinkSettings: (id: string, body: Record<string, unknown>) => api<Record<string, any>>(`/sites/${encodeURIComponent(id)}/links/settings`, { method: 'PUT', json: body }),
  // phase 8.5 — content strategy planner
  planMeta: (id: string) => api<PlanMeta>(`/sites/${encodeURIComponent(id)}/content-plans/meta`),
  plans: (id: string, params: Record<string, string | number | boolean | undefined> = {}) => { const q = new URLSearchParams(); Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && q.set(k, String(v))); return api<PlanList>(`/sites/${encodeURIComponent(id)}/content-plans?${q.toString()}`); },
  plan: (id: string, pid: number) => api<ContentPlan>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}`),
  planCreate: (id: string, body: Record<string, unknown>) => api<ContentPlan>(`/sites/${encodeURIComponent(id)}/content-plans`, { method: 'POST', json: body }),
  planPatch: (id: string, pid: number, body: Record<string, unknown>) => api<ContentPlan>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}`, { method: 'PATCH', json: body }),
  planDelete: (id: string, pid: number, withItem = false) => api<{ deleted: number }>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}?with_item=${withItem}`, { method: 'DELETE' }),
  planBulk: (id: string, ids: number[], patch: Record<string, unknown>) => api<{ updated: number[]; errors: any[] }>(`/sites/${encodeURIComponent(id)}/content-plans/bulk`, { method: 'POST', json: { ids, patch } }),
  planBulkDelete: (id: string, ids: number[]) => api<{ deleted: number[] }>(`/sites/${encodeURIComponent(id)}/content-plans/bulk-delete`, { method: 'POST', json: { ids } }),
  planTransition: (id: string, pid: number, status: string) => api<ContentPlan>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}/transition`, { method: 'POST', json: { status } }),
  planEnsureItem: (id: string, pid: number, contentId?: number) => api<{ content_id: number; created: boolean }>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}/content-item`, { method: 'POST', json: { content_id: contentId } }),
  planBrief: (id: string, pid: number, body: { use_ai?: boolean; mark_ready?: boolean } = {}) => api<Record<string, any>>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}/brief`, { method: 'POST', json: body }),
  planAnalyze: (id: string, pid: number) => api<{ plan: ContentPlan; recommendation: PlanRecommendation; category: any; links: any }>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}/analyze`, { method: 'POST' }),
  planAnalyzeAll: (id: string, ids?: number[]) => api<Record<string, any>>(`/sites/${encodeURIComponent(id)}/content-plans/analyze`, { method: 'POST', json: { ids } }),
  planLinkPrep: (id: string, pid: number) => api<{ inbound: any[]; outbound: any[]; count: number }>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}/link-prep`, { method: 'POST' }),
  planGenPrepare: (id: string, pid: number, kind = 'article', params: Record<string, unknown> = {}) => api<Record<string, any>>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}/generation-jobs`, { method: 'POST', json: { kind, params } }),
  planPublishing: (id: string, pid: number, body: Record<string, unknown>) => api<ContentPlan>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}/publishing-metadata`, { method: 'PUT', json: body }),
  planGenerate: (id: string, pid: number, thenPublish = false) => api<{ status: string; job_id: string; then_publish: boolean }>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}/generate${thenPublish ? '?then_publish=true' : ''}`, { method: 'POST' }),
  planPublish: (id: string, pid: number) => api<{ status: string; job_id: string }>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}/publish`, { method: 'POST' }),
  wpPublishCapability: (id: string) => api<{ site_id: string; mode: string; configured: boolean; can_publish: boolean; username?: string; roles?: string[]; message: string }>(`/sites/${encodeURIComponent(id)}/wordpress/publish-capability`),
  planKeywordsSet: (id: string, pid: number, items: { keyword_id: number; role?: string }[]) => api<any[]>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}/keywords`, { method: 'POST', json: { items } }),
  planKeywordRemove: (id: string, pid: number, kid: number) => api<{ removed: number }>(`/sites/${encodeURIComponent(id)}/content-plans/${pid}/keywords/${kid}`, { method: 'DELETE' }),
  planCalendar: (id: string, params: Record<string, string | number | undefined> = {}) => { const q = new URLSearchParams(); Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && q.set(k, String(v))); return api<{ from: string; to: string; days: Record<string, any[]>; unscheduled: ContentPlan[]; counts: PlanList['counts']; categories: { id: number; name: string; source: string }[] }>(`/sites/${encodeURIComponent(id)}/content-plans/calendar?${q.toString()}`); },
  planBoard: (id: string, categoryId?: number) => api<{ columns: { status: PlanStatus; status_fa: string; items: ContentPlan[] }[]; counts: PlanList['counts'] }>(`/sites/${encodeURIComponent(id)}/content-plans/board${categoryId ? `?category_id=${categoryId}` : ''}`),
  planGraph: (id: string, params: { plan_id?: number; category_id?: number } = {}) => { const q = new URLSearchParams(); Object.entries(params).forEach(([k, v]) => v !== undefined && q.set(k, String(v))); return api<GraphView & { focus?: string }>(`/sites/${encodeURIComponent(id)}/content-plans/graph?${q.toString()}`); },
  planImport: (id: string, file: File, dryRun: boolean, mapping?: Record<string, string>) => { const fd = new FormData(); fd.append('file', file); fd.append('dry_run', String(dryRun)); if (mapping) fd.append('mapping', JSON.stringify(mapping)); return api<PlanImportResult>(`/sites/${encodeURIComponent(id)}/content-plans/import`, { method: 'POST', body: fd }); },
  planImports: (id: string) => api<any[]>(`/sites/${encodeURIComponent(id)}/content-plans/imports`),
  planExportUrl: (id: string, fmt: 'csv' | 'xlsx', params: Record<string, string | undefined> = {}) => { const q = new URLSearchParams(); Object.entries(params).forEach(([k, v]) => v && q.set(k, v)); return `/api/backend/sites/${encodeURIComponent(id)}/content-plans/export.${fmt}?${q.toString()}`; },
  planTemplateUrl: (id: string) => `/api/backend/sites/${encodeURIComponent(id)}/content-plans/import/template.csv`,
  planSources: (id: string) => api<PlanSource[]>(`/sites/${encodeURIComponent(id)}/content-plans/sources`),
  planSourceCreate: (id: string, body: Record<string, unknown>) => api<PlanSource>(`/sites/${encodeURIComponent(id)}/content-plans/sources`, { method: 'POST', json: body }),
  planSourceDelete: (id: string, sid: number) => api<{ deleted: number }>(`/sites/${encodeURIComponent(id)}/content-plans/sources/${sid}`, { method: 'DELETE' }),
  planSourceSync: (id: string, sid: number, dryRun = false) => api<PlanImportResult>(`/sites/${encodeURIComponent(id)}/content-plans/sources/${sid}/sync?dry_run=${dryRun}`, { method: 'POST' }),
  planCategories: (id: string, tree = false, source?: string) => api<PlanCategory[]>(`/sites/${encodeURIComponent(id)}/content-plans/categories?tree=${tree}${source ? `&source=${source}` : ''}`),
  planCategory: (id: string, cid: number) => api<PlanCategory>(`/sites/${encodeURIComponent(id)}/content-plans/categories/${cid}`),
  planCategoriesSync: (id: string, minKeywords = 3) => api<Record<string, any>>(`/sites/${encodeURIComponent(id)}/content-plans/categories/sync?min_keywords=${minKeywords}`, { method: 'POST' }),
  planCategoriesAnalyze: (id: string) => api<Record<string, any>>(`/sites/${encodeURIComponent(id)}/content-plans/categories/analyze`, { method: 'POST' }),
  planCategorySuggest: (id: string, params: { keyword?: string; keyword_id?: number; plan_id?: number }) => { const q = new URLSearchParams(); Object.entries(params).forEach(([k, v]) => v !== undefined && q.set(k, String(v))); return api<{ keyword: string; suggested: any; candidates: any[]; confidence: number }>(`/sites/${encodeURIComponent(id)}/content-plans/categories/suggest?${q.toString()}`); },
  planCategoryCreate: (id: string, body: { name: string; parent_id?: number | null; description?: string }) => api<PlanCategory>(`/sites/${encodeURIComponent(id)}/content-plans/categories`, { method: 'POST', json: body }),
  planCategoryPatch: (id: string, cid: number, body: Record<string, unknown>) => api<PlanCategory>(`/sites/${encodeURIComponent(id)}/content-plans/categories/${cid}`, { method: 'PATCH', json: body }),
  planCategoryDelete: (id: string, cid: number) => api<{ deleted: number }>(`/sites/${encodeURIComponent(id)}/content-plans/categories/${cid}`, { method: 'DELETE' }),
  planKeywordMapping: (id: string, status: 'unmapped' | 'mapped' | 'all' = 'unmapped', q?: string) => api<{ status: string; total: number; items: any[]; counts: { keywords: number; mapped: number; plans: number } }>(`/sites/${encodeURIComponent(id)}/content-plans/keyword-mapping?status=${status}${q ? `&q=${encodeURIComponent(q)}` : ''}`),
  planKeywordSuggest: (id: string, keywordIds?: number[], limit = 100) => api<{ items: { keyword: KeywordRow; recommendation: PlanRecommendation; recommendation_id: number | null; recommendation_status: string | null; category: any }[]; count: number }>(`/sites/${encodeURIComponent(id)}/content-plans/keyword-mapping/suggest`, { method: 'POST', json: { keyword_ids: keywordIds, limit } }),
  planKeywordApply: (id: string, items: { keyword_id: number; plan_id?: number | 'new'; role?: string; recommendation_id?: number | null }[]) => api<{ created: any[]; attached: any[]; errors: any[] }>(`/sites/${encodeURIComponent(id)}/content-plans/keyword-mapping/apply`, { method: 'POST', json: { items } }),
  planSuggestions: (id: string, status = 'new', kind?: string) => api<PlanSuggestion[]>(`/sites/${encodeURIComponent(id)}/content-plans/suggestions?status=${status}${kind ? `&kind=${kind}` : ''}`),
  planSuggestionDecide: (id: string, rid: number, status: 'accepted' | 'dismissed') => api<PlanSuggestion>(`/sites/${encodeURIComponent(id)}/content-plans/suggestions/${rid}`, { method: 'PATCH', json: { status } }),
  planInsights: (id: string, status?: string) => api<any[]>(`/sites/${encodeURIComponent(id)}/content-plans/insights${status ? `?status=${status}` : ''}`),
  planInsightsLearn: (id: string) => api<Record<string, any>>(`/sites/${encodeURIComponent(id)}/content-plans/insights/learn`, { method: 'POST' }),
  planInsightStatus: (id: string, iid: number, status: 'accepted' | 'dismissed') => api<Record<string, any>>(`/sites/${encodeURIComponent(id)}/content-plans/insights/${iid}`, { method: 'PATCH', json: { status } }),
  planBackfill: (id: string) => api<{ created: number }>(`/sites/${encodeURIComponent(id)}/content-plans/backfill`, { method: 'POST' }),
  planSyncGraph: (id: string) => api<Record<string, any>>(`/sites/${encodeURIComponent(id)}/content-plans/sync-graph`, { method: 'POST' }),
  // ai content test workspace
  wsOptions: (id: string) => api<WsOptions>(`/sites/${encodeURIComponent(id)}/ai-workspace/options`),
  wsEstimate: (id: string, body: WsSpec) => api<WsEstimate>(`/sites/${encodeURIComponent(id)}/ai-workspace/estimate`, { method: 'POST', json: body }),
  wsGenerate: (id: string, body: WsSpec) => api<WsResult>(`/sites/${encodeURIComponent(id)}/ai-workspace/generate`, { method: 'POST', json: body }),
  wsSaveDraft: (id: string, body: { content_id: number; markdown: string; title?: string | null; meta_description?: string | null; meta?: Record<string, unknown> }) => api<{ draft_id: number; version: number; content_id: number }>(`/sites/${encodeURIComponent(id)}/ai-workspace/save-draft`, { method: 'POST', json: body }),
  wsHistory: (id: string) => api<any[]>(`/sites/${encodeURIComponent(id)}/ai-workspace/history`),
  // phase 9 — ai orchestration
  aiTaskKinds: () => api<{ kind: string; fa: string; policy: any }[]>('/ai/task-kinds'),
  aiModels: (providerId?: number) => api<AiModel[]>(`/ai/models${providerId ? `?provider_id=${providerId}` : ''}`),
  aiModelsSync: (providerId?: number) => api<Record<string, any>>(`/ai/models/sync${providerId ? `?provider_id=${providerId}` : ''}`, { method: 'POST' }),
  aiModelUpdate: (mid: number, body: Record<string, unknown>) => api<AiModel>(`/ai/models/${mid}`, { method: 'PATCH', json: body }),
  aiHealth: () => api<{ providers: any[]; now: string }>('/ai/health'),
  aiUsage: (params: Record<string, string | undefined> = {}) => { const q = new URLSearchParams(); Object.entries(params).forEach(([k, v]) => v && q.set(k, v)); return api<Usage>(`/ai/usage?${q.toString()}`); },
  aiBudget: (siteId: string) => api<Budget>(`/ai/budget?site_id=${encodeURIComponent(siteId)}`),
  aiBudgetSet: (siteId: string, budget_usd_month: number) => api<Budget>(`/ai/budget?site_id=${encodeURIComponent(siteId)}`, { method: 'PUT', json: { budget_usd_month } }),
  aiRoutingPreview: (params: Record<string, string | undefined>) => { const q = new URLSearchParams(); Object.entries(params).forEach(([k, v]) => v && q.set(k, v)); return api<RoutingDecision>(`/ai/routing/preview?${q.toString()}`); },
  aiPrompts: (siteId?: string, scope?: string) => { const q = new URLSearchParams(); if (siteId) q.set('site_id', siteId); if (scope) q.set('scope', scope); return api<Prompt[]>(`/ai/prompts?${q.toString()}`); },
  aiPrompt: (pid: number) => api<Prompt>(`/ai/prompts/${pid}`),
  aiPromptAddVersion: (pid: number, body: { template: string; changelog?: string; activate?: boolean }) => api<PromptVersion>(`/ai/prompts/${pid}/versions`, { method: 'POST', json: body }),
  aiPromptPatchVersion: (vid: number, body: Record<string, unknown>) => api<PromptVersion>(`/ai/prompts/versions/${vid}`, { method: 'PATCH', json: body }),
  aiPromptPreview: (vid: number, body: { site_id: string; variables?: Record<string, unknown> }) => api<{ rendered: string; memory_snapshot_id: number; variables: string[]; missing: string[] }>(`/ai/prompts/versions/${vid}/preview`, { method: 'POST', json: body }),
  aiPromptTest: (vid: number, body: { site_id: string; variables?: Record<string, unknown>; provider?: string; model?: string; task_kind?: string }) => api<Record<string, any>>(`/ai/prompts/versions/${vid}/test`, { method: 'POST', json: body }),
  aiPromptRateTest: (tid: number, body: { human_rating: number; notes?: string }) => api<Record<string, any>>(`/ai/prompts/tests/${tid}`, { method: 'PATCH', json: body }),
  aiInsights: (siteId?: string, status?: string) => { const q = new URLSearchParams(); if (siteId) q.set('site_id', siteId); if (status) q.set('status', status); return api<AiInsight[]>(`/ai/insights?${q.toString()}`); },
  aiInsightsLearn: (siteId?: string) => api<Record<string, any>>(`/ai/insights/learn${siteId ? `?site_id=${siteId}` : ''}`, { method: 'POST' }),
  aiInsightStatus: (iid: number, status: string) => api<AiInsight>(`/ai/insights/${iid}`, { method: 'PATCH', json: { status } }),
  aiFeedbackTags: () => api<{ tag: string; fa: string }[]>('/ai/feedback-tags'),
  genMeta: (id: string) => api<{ agents: { agent: string; fa: string }[]; steps: { step: string; fa: string }[]; modes: string[]; reserved_modes: string[]; feedback_tags: string[] }>(`/sites/${encodeURIComponent(id)}/generation/meta`),
  genMemoryPreview: (id: string) => api<{ id: number; hash: string; pack: Record<string, any>; rendered: string }>(`/sites/${encodeURIComponent(id)}/generation/memory-preview`),
  genEstimate: (id: string, cid: number, body: Record<string, unknown> = {}) => api<GenEstimate>(`/sites/${encodeURIComponent(id)}/content/${cid}/generate/estimate`, { method: 'POST', json: body }),
  genStart: (id: string, cid: number, body: Record<string, unknown> = {}) => api<GenerationRun & { job_run_id: string; budget: Budget }>(`/sites/${encodeURIComponent(id)}/content/${cid}/generate`, { method: 'POST', json: body }),
  genRuns: (id: string, cid?: number) => api<GenerationRun[]>(`/sites/${encodeURIComponent(id)}/generation/runs${cid ? `?content_id=${cid}` : ''}`),
  genRun: (id: string, runId: string) => api<GenerationRun>(`/sites/${encodeURIComponent(id)}/generation/runs/${runId}`),
  genAccept: (id: string, runId: string) => api<Record<string, any>>(`/sites/${encodeURIComponent(id)}/generation/runs/${runId}/accept`, { method: 'POST' }),
  genCancel: (id: string, runId: string) => api<GenerationRun>(`/sites/${encodeURIComponent(id)}/generation/runs/${runId}/cancel`, { method: 'POST' }),
  genAgent: (id: string, cid: number, agent: string, body: Record<string, unknown> = {}) => api<Record<string, any>>(`/sites/${encodeURIComponent(id)}/content/${cid}/agents/${agent}/run`, { method: 'POST', json: body }),
  genFeedback: (id: string, cid: number, body: { rating: number; tags?: string[]; draft_id?: number; run_id?: string; notes?: string }) => api<Record<string, any>>(`/sites/${encodeURIComponent(id)}/content/${cid}/feedback`, { method: 'POST', json: body }),
  genFeedbackList: (id: string, cid: number) => api<any[]>(`/sites/${encodeURIComponent(id)}/content/${cid}/feedback`),
  // phase 6 — ai providers
  providerKinds: () => api<ProviderKind[]>('/ai/provider-kinds'),
  providerConfigs: () => api<ProviderConfig[]>('/ai/provider-configs'),
  createProvider: (body: Record<string, unknown>) => api<ProviderConfig>('/ai/provider-configs', { method: 'POST', json: body }),
  updateProvider: (pid: number, body: Record<string, unknown>) => api<ProviderConfig>(`/ai/provider-configs/${pid}`, { method: 'PATCH', json: body }),
  deleteProvider: (pid: number) => api<{ deleted: number }>(`/ai/provider-configs/${pid}`, { method: 'DELETE' }),
  testProvider: (pid: number) => api<{ ok: boolean; status: string; message: string; models_found?: string[] }>(`/ai/provider-configs/${pid}/test`, { method: 'POST' }),
  gatewayStatus: (pid: number) => api<GatewayStatus>(`/ai/provider-configs/${pid}/gateway-status`),
  recommendedRoutes: (pid: number) => api<{ provider_id: number; kind: string; routes: RecommendedRoute[] }>(`/ai/provider-configs/${pid}/recommended-routes`),
  applyRecommendedRoutes: (pid: number, body: { site_id?: string; overwrite?: boolean } = {}) => api<{ provider_id: number; applied: number; routes: TaskRoute[] }>(`/ai/provider-configs/${pid}/recommended-routes`, { method: 'POST', json: body }),
  taskRoutes: () => api<{ task_kinds: string[]; routes: TaskRoute[] }>('/ai/task-routes'),
  setTaskRoute: (kind: string, body: Record<string, unknown>) => api<TaskRoute>(`/ai/task-routes/${kind}`, { method: 'PUT', json: body }),
  putMemory: (id: string, body: MemoryUpdateBody) => api<SiteMemory>(`/sites/${encodeURIComponent(id)}/memory`, { method: 'PUT', json: body })
};

/** Resolve a value or an ApiError without throwing — for server components that render partial data. */
export async function settle<T>(p: Promise<T>): Promise<{ data: T; error: null } | { data: null; error: ApiError }> {
  try {
    return { data: await p, error: null };
  } catch (e) {
    return { data: null, error: e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e), null, '-') };
  }
}
