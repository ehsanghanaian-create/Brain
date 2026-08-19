import { describe, expect, it } from 'vitest';
import { queueMessage, stepRows, wpSyncView, WP_STEP_FA } from '../wp-sync';

const counts = { categories: 12, pages: 40, posts: 300, crawled: 5, graph_nodes: 420, graph_edges: 900 };

describe('WordPress Sync Card helpers', () => {
  it('never synced + wp configured → start enabled, rebuild enabled, no polling', () => {
    const v = wpSyncView({ status: 'never', wp_url: 'https://example.com', counts });
    expect(v.canStart).toBe(true);
    expect(v.canRebuild).toBe(true);
    expect(v.shouldPoll).toBe(false);
    expect(v.statusFa).toBe('هنوز همگام‌سازی نشده');
    expect(v.lastSync).toBeNull();
  });

  it('wp not configured → start disabled with Persian reason', () => {
    const v = wpSyncView({ status: 'never', wp_url: null, counts });
    expect(v.canStart).toBe(false);
    expect(v.startDisabledReason).toContain('آدرس وردپرس');
  });

  it('running → buttons disabled, polling on, progress + current step label', () => {
    const v = wpSyncView({ status: 'running', wp_url: 'https://example.com', step: 'pages', step_fa: null, progress: 0.375, counts });
    expect(v.running).toBe(true);
    expect(v.canStart).toBe(false);
    expect(v.canRebuild).toBe(false);
    expect(v.shouldPoll).toBe(true);
    expect(v.percent).toBe(38);
    expect(v.stepFa).toBe('در حال دریافت صفحات');
  });

  it('queued → step label falls back to first step; busy flag disables buttons', () => {
    const v = wpSyncView({ status: 'queued', wp_url: 'https://example.com', progress: 0, counts });
    expect(v.stepFa).toBe(WP_STEP_FA.resolve);
    expect(wpSyncView({ status: 'succeeded', wp_url: 'https://example.com', counts }, { busy: true }).canStart).toBe(false);
  });

  it('succeeded → counters (categories/pages/posts/graph nodes) + last sync date', () => {
    const v = wpSyncView({ status: 'succeeded', wp_url: 'https://example.com', finished_at: '2026-08-19T10:00:00Z', progress: 1, counts });
    expect(v.counters.map((c) => [c.key, c.value])).toEqual([['categories', 12], ['pages', 40], ['posts', 300], ['graph_nodes', 420]]);
    expect(v.counters.map((c) => c.fa)).toEqual(['دسته‌بندی‌ها', 'صفحات', 'نوشته‌ها', 'گره‌های گراف']);
    expect(v.lastSync).toBe('2026-08-19T10:00:00Z');
    expect(v.percent).toBe(100);
  });

  it('queue responses → toast text', () => {
    expect(queueMessage({ status: 'queued', job_id: 'job-1' })).toEqual({ ok: true, text: 'در صف اجرا قرار گرفت (job-1)' });
    expect(queueMessage({ status: 'already_running' }).ok).toBe(true);
    expect(queueMessage({ status: 'not_queued', error: 'KeyError' }).ok).toBe(false);
    expect(queueMessage(null).ok).toBe(false);
  });

  it('step rows: default pending list when no run; server steps otherwise (with error text)', () => {
    expect(stepRows(null).map((r) => r.status)).toEqual(Array(8).fill('pending'));
    const rows = stepRows({ steps: [{ key: 'resolve', status: 'done' }, { key: 'categories', status: 'failed', error: 'ConnectError' }] });
    expect(rows).toEqual([{ key: 'resolve', fa: WP_STEP_FA.resolve, status: 'done', info: undefined }, { key: 'categories', fa: WP_STEP_FA.categories, status: 'failed', info: 'ConnectError' }]);
  });
});
