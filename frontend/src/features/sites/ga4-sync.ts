import type { Ga4SyncStatus } from '@/lib/api/client';

/** Pure helpers for the GA4 Sync Card (unit-tested): button state, progress, counters, top pages, status labels. */
export const GA4_STEP_FA: Record<string, string> = {
  sync: 'در حال دریافت داده از Google Analytics',
  snapshot: 'در حال ثبت اسنپ‌شات عملکرد محتوا',
  graph: 'در حال به‌روزرسانی گراف و فرصت‌ها'
};

export const GA4_STATUS_FA: Record<string, string> = {
  never: 'هنوز همگام‌سازی نشده',
  queued: 'در صف اجرا',
  running: 'در حال اجرا',
  succeeded: 'موفق',
  completed_with_errors: 'انجام شد با خطا',
  failed: 'ناموفق',
  not_authorized: 'بدون مجوز Google'
};

export type Ga4SyncView = {
  running: boolean;
  canSync: boolean;
  syncDisabledReason: string | null;
  percent: number;
  statusFa: string;
  stepFa: string | null;
  lastSync: string | null;
  dateRange: string | null;
  counters: { key: string; fa: string; value: number }[];
  topPages: { path: string; sessions: number; conversions: number }[];
  shouldPoll: boolean;
};

export function ga4SyncView(s: Partial<Ga4SyncStatus> | null | undefined, opts: { busy?: boolean } = {}): Ga4SyncView {
  const status = s?.status ?? 'never';
  const running = status === 'queued' || status === 'running';
  const configured = Boolean(s?.property);
  const authorized = s?.authorized !== false;
  const cov: Partial<import('@/lib/api/client').Ga4SyncCoverage> = s?.coverage ?? {};
  const progress = typeof s?.progress === 'number' ? s.progress : 0;
  return {
    running,
    canSync: configured && authorized && !running && !opts.busy,
    syncDisabledReason: !configured
      ? 'ابتدا Property ID گوگل‌آنالیتیکس را وصل و تست کنید'
      : !authorized
        ? 'توکن Google اسکوپ analytics.readonly ندارد؛ اتصال GA4 را دوباره تست کنید'
        : running
          ? 'همگام‌سازی در حال اجراست'
          : null,
    percent: Math.max(0, Math.min(100, Math.round(progress * 100))),
    statusFa: GA4_STATUS_FA[status] ?? status,
    stepFa: running ? (s?.step_fa ?? (s?.step ? GA4_STEP_FA[s.step] ?? s.step : GA4_STEP_FA.sync)) : null,
    lastSync: !running ? (s?.finished_at ?? s?.coverage?.last_ga4_sync ?? null) : null,
    dateRange: cov.date_from && cov.date_to ? `${cov.date_from} → ${cov.date_to}` : null,
    counters: [
      { key: 'sessions', fa: 'Sessions', value: cov.sessions ?? 0 },
      { key: 'users', fa: 'کاربران', value: cov.users ?? 0 },
      { key: 'conversions', fa: 'تبدیل‌ها', value: Math.round(cov.conversions ?? 0) },
      { key: 'pages', fa: 'صفحات دارای داده', value: cov.pages ?? 0 }
    ],
    topPages: (cov.top_pages ?? []).slice(0, 5),
    shouldPoll: running
  };
}

/** Per-step rows for the progress list (same shape the WP/GSC cards use). */
export function ga4StepRows(s: Partial<Ga4SyncStatus> | null | undefined): { key: string; fa: string; status: string; info?: string }[] {
  const steps = s?.steps ?? [];
  if (!steps.length) return Object.entries(GA4_STEP_FA).map(([key, fa]) => ({ key, fa, status: 'pending' }));
  return steps.map((st) => ({ key: st.key, fa: st.fa ?? GA4_STEP_FA[st.key] ?? st.key, status: st.status, info: st.error ?? undefined }));
}
