import type { WpSyncStatus } from '@/lib/api/client';

/** Pure helpers for the WordPress Sync Card (unit-tested): button state, progress, step labels, counters. */
export const WP_STEP_FA: Record<string, string> = {
  resolve: 'بررسی آدرس وردپرس',
  categories: 'در حال دریافت دسته‌بندی‌ها',
  pages: 'در حال دریافت صفحات',
  posts: 'در حال دریافت نوشته‌ها',
  taxonomies: 'در حال دریافت تاکسونومی‌ها و رسانه‌ها',
  category_intelligence: 'در حال تحلیل دسته‌بندی‌ها',
  crawl: 'در حال استخراج لینک‌ها',
  build_graph: 'در حال ساخت گراف'
};

export const WP_STATUS_FA: Record<string, string> = {
  never: 'هنوز همگام‌سازی نشده',
  queued: 'در صف اجرا',
  running: 'در حال اجرا',
  succeeded: 'موفق',
  completed_with_errors: 'انجام شد با خطا',
  failed: 'ناموفق'
};

export type WpSyncView = {
  running: boolean;
  canStart: boolean;          // «شروع همگام‌سازی» enabled?
  canRebuild: boolean;        // «بازسازی گراف» enabled?
  startDisabledReason: string | null;
  percent: number;            // 0..100
  statusFa: string;
  stepFa: string | null;      // current step label (Persian) while running
  lastSync: string | null;    // finished_at of the last run (ISO) or null
  counters: { key: string; fa: string; value: number }[];
  shouldPoll: boolean;        // keep polling status while queued/running
};

export function wpSyncView(s: Partial<WpSyncStatus> | null | undefined, opts: { busy?: boolean } = {}): WpSyncView {
  const status = s?.status ?? 'never';
  const running = status === 'queued' || status === 'running';
  const configured = Boolean(s?.wp_url);
  const counts = s?.counts ?? { categories: 0, pages: 0, posts: 0, graph_nodes: 0, graph_edges: 0, crawled: 0 };
  const stepKey = s?.step ?? null;
  const stepFa = running ? (s?.step_fa ?? (stepKey ? WP_STEP_FA[stepKey] ?? stepKey : WP_STEP_FA.resolve)) : null;
  const progress = typeof s?.progress === 'number' ? s.progress : 0;
  return {
    running,
    canStart: configured && !running && !opts.busy,
    canRebuild: !running && !opts.busy,
    startDisabledReason: !configured ? 'ابتدا آدرس وردپرس را وصل و تست کنید' : running ? 'همگام‌سازی در حال اجراست' : null,
    percent: Math.max(0, Math.min(100, Math.round(progress * 100))),
    statusFa: WP_STATUS_FA[status] ?? status,
    stepFa,
    lastSync: !running && s?.finished_at ? s.finished_at : null,
    counters: [
      { key: 'categories', fa: 'دسته‌بندی‌ها', value: counts.categories ?? 0 },
      { key: 'pages', fa: 'صفحات', value: counts.pages ?? 0 },
      { key: 'posts', fa: 'نوشته‌ها', value: counts.posts ?? 0 },
      { key: 'graph_nodes', fa: 'گره‌های گراف', value: counts.graph_nodes ?? 0 }
    ],
    shouldPoll: running
  };
}

/** Result of POST /wordpress/sync · /graph/rebuild · connection test's `detail.sync_job` → one toast line. */
export function queueMessage(r: { status?: string; job_id?: string | null; error?: string | null } | null | undefined): { ok: boolean; text: string } {
  if (!r) return { ok: false, text: 'پاسخی دریافت نشد' };
  if (r.status === 'queued') return { ok: true, text: `در صف اجرا قرار گرفت (${r.job_id ?? '—'})` };
  if (r.status === 'already_running') return { ok: true, text: 'همگام‌سازی قبلی هنوز در حال اجراست' };
  if (r.status === 'not_queued') return { ok: false, text: `اجرای خودکار ممکن نشد: ${r.error ?? 'نامشخص'}` };
  return { ok: false, text: r.status ?? 'نامشخص' };
}

/** Per-step rows for the progress list (done ✓ · running … · failed ✗ · skipped –). */
export function stepRows(s: Partial<WpSyncStatus> | null | undefined): { key: string; fa: string; status: string; info?: string }[] {
  const steps = s?.steps ?? [];
  if (!steps.length) return Object.entries(WP_STEP_FA).map(([key, fa]) => ({ key, fa, status: 'pending' }));
  return steps.map((st) => ({ key: st.key, fa: st.fa ?? WP_STEP_FA[st.key] ?? st.key, status: st.status, info: st.error ?? (st.note as string | undefined) }));
}
