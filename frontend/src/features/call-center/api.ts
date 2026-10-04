import { api } from '@/lib/api/client';

export type CallSource = 'seo' | 'ads' | 'direct' | 'referral' | 'unknown';
export type CallStatus = 'new' | 'follow_up' | 'resolved' | 'cancelled' | 'unreviewed';
export type SourceBasis = 'manual' | 'customer' | 'gclid' | 'utm' | 'import';
export type UserRole = 'admin' | 'analyst' | 'call_center';
export type PanelUser = {
  id: number;
  full_name: string;
  email: string;
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

const params = (values: Record<string, string | number | undefined>) => {
  const q = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== '') q.set(key, String(value));
  });
  return q.toString();
};
export const callCenterApi = {
  users: () => api<PanelUser[]>('/call-center/users'),
  addUser: (body: Omit<PanelUser, 'id' | 'created_at' | 'updated_at'>) =>
    api<PanelUser>('/call-center/users', { method: 'POST', json: body }),
  patchUser: (id: number, body: Partial<PanelUser>) =>
    api<PanelUser>(`/call-center/users/${id}`, { method: 'PATCH', json: body }),
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
  analytics: (days: number, site_id?: string) =>
    api<CallAnalytics>(`/call-center/analytics?${params({ days, site_id })}`)
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
export const roleLabel: Record<UserRole, string> = {
  admin: 'مدیر',
  analyst: 'تحلیل‌گر',
  call_center: 'اپراتور کال‌سنتر'
};
