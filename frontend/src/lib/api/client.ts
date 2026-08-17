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
export type SiteMemory = { site_id: string; business_rules: string[]; tone: Record<string, unknown>; content_rules: string[]; successful_patterns: Record<string, unknown>[]; updated_at: string | null };

export const endpoints = {
  health: () => api<Health>('/health'),
  sites: () => api<Site[]>('/sites'),
  site: (id: string) => api<Site>(`/sites/${encodeURIComponent(id)}`),
  graphSummary: (id: string) => api<GraphSummary>(`/sites/${encodeURIComponent(id)}/graph/summary`),
  memory: (id: string) => api<SiteMemory>(`/sites/${encodeURIComponent(id)}/memory`)
};

/** Resolve a value or an ApiError without throwing — for server components that render partial data. */
export async function settle<T>(p: Promise<T>): Promise<{ data: T; error: null } | { data: null; error: ApiError }> {
  try {
    return { data: await p, error: null };
  } catch (e) {
    return { data: null, error: e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e), null, '-') };
  }
}
