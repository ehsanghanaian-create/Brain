import { api } from '@/lib/api/client';

export type CallSource = 'seo' | 'ads' | 'direct' | 'referral' | 'unknown';
export type CallStatus = 'new' | 'follow_up' | 'resolved' | 'cancelled' | 'unreviewed';
export type SourceBasis = 'manual' | 'customer' | 'gclid' | 'utm' | 'import';
export type CallOutcome = 'pending' | 'qualified' | 'unqualified' | 'order' | 'lost';
export type SourceConfidence = 'confirmed' | 'probable' | 'unknown';
export type UserRole = 'admin' | 'analyst' | 'call_center';
export type PanelUser = {
  id: number;
  full_name: string;
  email: string;
  username: string | null;
  has_password: boolean;
  role: UserRole;
  active: boolean;
  created_at: string;
  updated_at: string;
};
export type CallRecord = {
  id: number;
  site_id: string | null;
  occurred_at: string | null;
  customer_name: string;
  phone: string;
  warranty: boolean;
  brand: string;
  model: string;
  region: string;
  issue: string;
  source: CallSource;
  source_basis: SourceBasis;
  source_note: string;
  campaign: string;
  status: CallStatus;
  outcome: CallOutcome;
  order_value: number | null;
  follow_up_at: string | null;
  source_confidence: SourceConfidence;
  attribution_event: string | null;
  attribution_checked_at: string | null;
  auto_attributed: boolean;
  attribution_locked: boolean;
  operator_id: number | null;
  operator_name: string | null;
  import_key: string | null;
  created_at: string;
  updated_at: string;
};
export type CallAnalytics = {
  total: number;
  by_source: Record<CallSource, number>;
  by_brand: [string, number][];
  by_model: [string, number][];
  by_region: [string, number][];
  by_status: Record<CallStatus, number>;
  by_outcome: Record<CallOutcome, number>;
  by_source_outcome: Record<CallSource, { total: number; qualified: number; orders: number;
    order_value: number; unknown_confidence: number }>;
  warranty: number;
  daily: {
    date: string;
    seo: number;
    ads: number;
    direct: number;
    referral: number;
    unknown: number;
  }[];
  days: number;
  undated: number;
  future: number;
  generated_at: string;
};
export type CallImportResult = {
  columns: string[];
  mapping: Record<string, string | null>;
  rows_total: number;
  rows_valid: number;
  rows_imported: number;
  rows_skipped: number;
  errors_count: number;
  errors: { row: number; error: string }[];
  preview: { customer_name: string; phone: string; occurred_at: string | null; source: CallSource; site_id: string | null; region: string; outcome: CallOutcome }[];
  dry_run: boolean;
};
export type CallWorkbookResult = {
  dry_run: boolean;
  sha256: string;
  sheets: Record<string, { candidates: number; valid: number; imported: number; skipped_existing: number;
    missing_date: number; missing_phone: number; short_phone: number; future_date: number; cancelled: number; changed_rows: number }>;
  rows_valid: number;
  rows_imported: number;
  rows_skipped: number;
  rows_changed: number;
  conflicts: { sheet: string; row: number }[];
  source: CallSource;
  source_reason: string;
};

const params = (values: Record<string, string | number | undefined>) => {
  const q = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== '') q.set(key, String(value));
  });
  return q.toString();
};
export const callCenterApi = {
  users: () => api<PanelUser[]>('/call-center/users'),
  operators: () => api<{ id: number; full_name: string; active: boolean }[]>('/call-center/operators'),
  addUser: (body: { full_name: string; email: string; username: string; password: string; role: UserRole; active: boolean }) =>
    api<PanelUser>('/call-center/users', { method: 'POST', json: body }),
  patchUser: (id: number, body: Partial<PanelUser> & { password?: string }) =>
    api<PanelUser>(`/call-center/users/${id}`, { method: 'PATCH', json: body }),
  audit: () => api<{ items: { id: number; actor_username: string; actor_role: UserRole; method: string; path: string; status_code: number; changed_fields: string; created_at: string }[]; total: number }>('/auth/audit?limit=100'),
  calls: (filters: {
    source?: string;
    status?: string;
    site_id?: string;
    q?: string;
    limit?: number;
    offset?: number;
  }) =>
    api<{ items: CallRecord[]; limit: number; offset: number; total: number }>(
      `/call-center/calls?${params(filters)}`
    ),
  addCall: (body: Partial<CallRecord>) =>
    api<CallRecord>('/call-center/calls', { method: 'POST', json: body }),
  patchCall: (id: number, body: Partial<CallRecord>) =>
    api<CallRecord>(`/call-center/calls/${id}`, { method: 'PATCH', json: body }),
  reconcile: (siteId?: string) =>
    api<{ checked: number; changed: number }>(`/call-center/reconcile?${params({ site_id: siteId })}`, { method: 'POST' }),
  importCalls: (file: File, mapping: Record<string, string>, dryRun: boolean, siteId?: string) => {
    const form = new FormData();
    form.set('file', file);
    form.set('dry_run', String(dryRun));
    form.set('mapping', JSON.stringify(mapping));
    if (siteId) form.set('default_site_id', siteId);
    return api<CallImportResult>('/call-center/calls/import', { method: 'POST', body: form });
  },
  importWorkbook: (file: File, dryRun: boolean, siteId?: string) => {
    const form = new FormData();
    form.set('file', file);
    form.set('dry_run', String(dryRun));
    if (siteId) form.set('site_id', siteId);
    return api<CallWorkbookResult>('/call-center/calls/import-workbook', { method: 'POST', body: form });
  },
  analytics: (days: number, site_id?: string, source?: CallSource) =>
    api<CallAnalytics>(`/call-center/analytics?${params({ days, site_id, source })}`)
};

export const sourceLabel: Record<CallSource, string> = {
  seo: 'سئو',
  ads: 'ادز',
  direct: 'مستقیم',
  referral: 'ارجاع',
  unknown: 'نامشخص'
};
export const statusLabel: Record<CallStatus, string> = {
  new: 'جدید',
  follow_up: 'پیگیری',
  resolved: 'انجام‌شده',
  cancelled: 'کنسل‌شده',
  unreviewed: 'بازبینی نشده'
};
export const outcomeLabel: Record<CallOutcome, string> = {
  pending: 'در انتظار نتیجه', qualified: 'واجدکیفیت', unqualified: 'فاقدکیفیت',
  order: 'سفارش', lost: 'از دست‌رفته'
};
export const confidenceLabel: Record<SourceConfidence, string> = {
  confirmed: 'قطعی', probable: 'محتمل', unknown: 'نامشخص'
};
export const roleLabel: Record<UserRole, string> = {
  admin: 'دسترسی کامل (مدیر)',
  analyst: 'تحلیل‌گر',
  call_center: 'اپراتور کال‌سنتر'
};
