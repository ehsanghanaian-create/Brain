import type { GscSyncStatus } from '@/lib/api/client';

/** Pure helpers for the GSC Sync Card (unit-tested): button state, progress, coverage counters, status labels. */
export const GSC_STEP_FA: Record<string, string> = {
  sync: 'در حال دریافت داده از Search Console',
  keyword_opportunities: 'در حال تحلیل فرصت‌های کلمات کلیدی',
  snapshot: 'در حال ثبت اسنپ‌شات عملکرد محتوا',
  graph: 'در حال به‌روزرسانی گراف'
};

export const GSC_STATUS_FA: Record<string, string> = {
  never: 'هنوز همگام‌سازی نشده',
  queued: 'در صف اجرا',
  running: 'در حال اجرا',
  succeeded: 'موفق',
  completed_with_errors: 'انجام شد با خطا',
  failed: 'ناموفق',
  not_authorized: 'بدون مجوز Google'
};

export type GscSyncView = {
  running: boolean;
  canSync: boolean;
  syncDisabledReason: string | null;
  percent: number;
  statusFa: string;
  stepFa: string | null;
  lastSync: string | null;
  dateRange: string | null;          // «2026-07-16 → 2026-08-14» or null when no data
  counters: { key: string; fa: string; value: number }[];
  shouldPoll: boolean;
};

export function gscSyncView(s: Partial<GscSyncStatus> | null | undefined, opts: { busy?: boolean } = {}): GscSyncView {
  const status = s?.status ?? 'never';
  const running = status === 'queued' || status === 'running';
  const configured = Boolean(s?.property);
  const authorized = s?.authorized !== false;
  const cov: Partial<import('@/lib/api/client').GscSyncCoverage> = s?.coverage ?? {};
  const progress = typeof s?.progress === 'number' ? s.progress : 0;
  return {
    running,
    canSync: configured && authorized && !running && !opts.busy,
    syncDisabledReason: !configured
      ? 'ابتدا property سرچ‌کنسول را وصل و تست کنید'
      : !authorized
        ? 'توکن Google موجود نیست؛ یک‌بار «sync-gsc.py --auth-only» را اجرا کنید'
        : running
          ? 'همگام‌سازی در حال اجراست'
          : null,
    percent: Math.max(0, Math.min(100, Math.round(progress * 100))),
    statusFa: GSC_STATUS_FA[status] ?? status,
    stepFa: running ? (s?.step_fa ?? (s?.step ? GSC_STEP_FA[s.step] ?? s.step : GSC_STEP_FA.sync)) : null,
    lastSync: !running ? (s?.finished_at ?? s?.coverage?.last_gsc_sync ?? null) : null,
    dateRange: cov.date_from && cov.date_to ? `${cov.date_from} → ${cov.date_to}` : null,
    counters: [
      { key: 'queries', fa: 'کوئری‌ها', value: cov.queries ?? 0 },
      { key: 'important_queries', fa: 'کوئری‌های مهم', value: cov.important_queries ?? 0 },
      { key: 'pages', fa: 'صفحات دارای داده', value: cov.pages ?? 0 },
      { key: 'rows', fa: 'ردیف‌های خام', value: cov.rows ?? 0 }
    ],
    shouldPoll: running
  };
}

/** Per-step rows for the progress list (same shape the WordPress card uses). */
export function gscStepRows(s: Partial<GscSyncStatus> | null | undefined): { key: string; fa: string; status: string; info?: string }[] {
  const steps = s?.steps ?? [];
  if (!steps.length) return Object.entries(GSC_STEP_FA).map(([key, fa]) => ({ key, fa, status: 'pending' }));
  return steps.map((st) => ({ key: st.key, fa: st.fa ?? GSC_STEP_FA[st.key] ?? st.key, status: st.status, info: st.error ?? undefined }));
}
