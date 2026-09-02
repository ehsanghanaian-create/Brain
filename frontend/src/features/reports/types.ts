/** Types for the Site Report Center (/sites/{id}/report/*). Hand-written until the OpenAPI schema is regenerated. */

export interface ReportKeywordPerf {
  clicks: number | null;
  impressions: number | null;
  ctr: number | null;
  position: number | null;
  prev_position: number | null;
  landing_page: string | null;
  date_from?: string;
  date_to?: string;
  source: 'gsc_daily' | 'gsc_query_page';
}

export interface ReportSummary {
  site: { site_id: string; name: string; canonical_url: string | null; gsc_property: string | null; ga4_property: string | null; wp_url: string | null };
  generated_at: string;
  days: number;
  score: number;
  score_breakdown: { problems_penalty: number; connections_penalty: number };
  gsc: {
    available: boolean;
    date_from?: string;
    date_to?: string;
    window?: { from: string; to: string; days: number };
    totals?: { clicks: number; impressions: number; ctr: number | null; position: number | null };
    previous?: { clicks: number; impressions: number; ctr: number | null; position: number | null } | null;
    timeseries?: { date: string; clicks: number; impressions: number; position: number | null }[];
  };
  ga4: {
    available: boolean;
    date_from?: string;
    date_to?: string;
    totals?: { sessions: number; users: number; conversions: number; engagement_rate: number | null };
    timeseries?: { date: string; sessions: number; users: number }[];
  };
  counts: {
    indexable_pages: number;
    keywords: number;
    gsc_queries: number;
    problems: { high: number; medium: number; low: number; total: number };
    opportunities: number;
    backlinks: number;
    reportages: number;
    referring_domains: number;
  };
  main_keyword: { keyword: string | null; performance: ReportKeywordPerf | null };
  freshness: {
    last_runs: Record<string, string>;
    auto_sync: { enabled: boolean; interval_minutes: number; interval_hours: number; sources: Record<string, { configured: boolean; last_success: string | null; next_at: string | null; due: boolean }> };
  };
}

export interface ReportConnection {
  configured: boolean;
  connected: boolean;
  tested_status: string | null;
  tested_at: string | null;
  last_success: string | null;
  next_at: string | null;
}

export interface SyncHistoryRow {
  source: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  rows_written: number | null;
  duration_seconds: number | null;
}

export interface ReportFull extends ReportSummary {
  connections: Record<'gsc' | 'wordpress' | 'ga4', ReportConnection>;
  sync_history: SyncHistoryRow[];
  sync_running: boolean;
}

export interface ReportMainKeyword {
  keyword: string | null;
  performance: ReportKeywordPerf | null;
  suggestions: { query: string; clicks: number; impressions: number; position: number | null }[];
}

export interface ReportKeywordRow {
  query: string;
  clicks: number;
  impressions: number;
  ctr: number | null;
  position: number | null;
  prev_position: number | null;
  change: number | null;
  landing_page: string | null;
}

export interface ReportKeywordList {
  status: 'OK' | 'NO_GSC_DATA';
  scope?: 'all' | 'tracked';
  tracked_count?: number | null;
  window?: { from: string; to: string; days: number; previous: { from: string; to: string } };
  total: number;
  items: ReportKeywordRow[];
}

export interface ReportProblemItem {
  problem_type: string;
  severity: 'high' | 'medium' | 'low';
  url: string | null;
  related_url: string | null;
  detail: unknown;
  created_at: string;
  category: string;
  category_fa: string;
  title_fa: string;
  source: string;
}

export interface ReportProblems {
  summary: Record<string, { count: number; severity: string; category: string; category_fa: string; title_fa: string }>;
  items: ReportProblemItem[];
  categories: Record<string, string>;
}

export interface ReportOpportunities {
  summary: Record<string, { count: number; type_fa: string }>;
  items: { opp_type: string; type_fa: string; url: string | null; related_url: string | null; query: string | null; score: number; reason: string | null; confidence: number | null; detail: unknown; created_at: string }[];
}

export interface BacklinkRow {
  id: number;
  source_url: string;
  source_domain: string;
  target_url: string;
  anchor_text: string | null;
  link_type: string;
  rel: string | null;
  provider: string;
  first_seen: string | null;
  last_seen: string | null;
  status: 'active' | 'lost' | 'unverified';
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportBacklinks {
  provider: string | null;
  provider_note: string;
  totals: { total: number; active: number; lost: number; follow: number; nofollow: number; referring_domains: number };
  top_anchors: { anchor_text: string; backlinks: number; domains: number }[];
  items: BacklinkRow[];
}

export interface ReportageRow {
  id: number;
  publication_domain: string;
  article_url: string;
  target_url: string;
  anchor_text: string | null;
  target_keyword: string | null;
  publication_date: string | null;
  link_type: string | null;
  cost: number | null;
  status: 'pending' | 'published' | 'link_found' | 'link_missing' | 'article_missing' | 'target_changed';
  verified_rel: string | null;
  last_verified_at: string | null;
  verify_detail: { http_status?: number; rel?: string; anchor?: string; error?: string } | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportReportages {
  totals: { total: number; link_found: number; link_missing: number; pending: number; cost_total: number };
  items: ReportageRow[];
}
