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

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const requestId = newRequestId();
  const headers: Record<string, string> = { Accept: 'application/json', 'X-Request-ID': requestId, ...(init.headers as Record<string, string> | undefined) };
  let body = init.body;
  if (init.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(init.json);
  }
  if (isServer && process.env.SEO_BRAIN_API_TOKEN) headers['X-API-Token'] = process.env.SEO_BRAIN_API_TOKEN;
  let res: Response;
  try {
    res = await fetch(`${baseUrl()}${path.startsWith('/') ? path : `/${path}`}`, { ...init, headers, body, cache: 'no-store' });
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
export type ConnectionsStatus = {
  site_id: string;
  configured: { gsc: string | null; ga4: string | null; wordpress: string | null };
  status: Partial<Record<ConnectionKind, ConnectionResult>>;
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
export type GraphMode = { key: 'seo' | 'content' | 'links'; title_fa: string; description_fa: string; layout: string; group_by: string; node_types: string[]; relation_types: string[] };
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
export type SiteCreateBody = Schemas['SiteCreate'];
export type SiteUpdateBody = Schemas['SiteUpdate'];
export type MemoryUpdateBody = Schemas['MemoryUpdate'];

export const endpoints = {
  health: () => api<Health>('/health'),
  sites: () => api<Site[]>('/sites'),
  site: (id: string) => api<Site>(`/sites/${encodeURIComponent(id)}`),
  graphSummary: (id: string) => api<GraphSummary>(`/sites/${encodeURIComponent(id)}/graph/summary`),
  memory: (id: string) => api<SiteMemory>(`/sites/${encodeURIComponent(id)}/memory`),
  // phase 3 — sites management
  createSite: (body: SiteCreateBody) => api<Site>('/sites', { method: 'POST', json: body }),
  updateSite: (id: string, body: SiteUpdateBody) => api<Site>(`/sites/${encodeURIComponent(id)}`, { method: 'PATCH', json: body }),
  deleteSite: (id: string, force = false) => api<{ deleted: string }>(`/sites/${encodeURIComponent(id)}${force ? '?force=true' : ''}`, { method: 'DELETE' }),
  connections: (id: string) => api<ConnectionsStatus>(`/sites/${encodeURIComponent(id)}/connections`),
  testConnection: (id: string, kind: ConnectionKind, property?: string | null) =>
    api<ConnectionResult>(`/sites/${encodeURIComponent(id)}/connections/${kind}/test`, { method: 'POST', json: { property: property || null } }),
  gscProperties: () => api<GscProperties>('/connections/gsc/properties'),
  initializeSite: (id: string) => api<InitializeResult>(`/sites/${encodeURIComponent(id)}/initialize`, { method: 'POST' }),
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
