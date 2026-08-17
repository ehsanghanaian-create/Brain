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
