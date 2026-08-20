import { describe, expect, it } from 'vitest';
import { GSC_STEP_FA, gscStepRows, gscSyncView } from '../gsc-sync';

const coverage = { date_from: '2026-07-16', date_to: '2026-08-14', rows: 731, queries: 66, important_queries: 43, pages: 38, content_snapshots: 4 };

describe('GSC Sync Card helpers', () => {
  it('connected + authorized + never synced → sync enabled, no polling', () => {
    const v = gscSyncView({ status: 'never', property: 'sc-domain:example.com', authorized: true, coverage });
    expect(v.canSync).toBe(true);
    expect(v.shouldPoll).toBe(false);
    expect(v.statusFa).toBe('هنوز همگام‌سازی نشده');
    expect(v.dateRange).toBe('2026-07-16 → 2026-08-14');
  });

  it('no property → disabled with Persian reason; card renders zeros', () => {
    const v = gscSyncView({ status: 'never', property: null, authorized: true });
    expect(v.canSync).toBe(false);
    expect(v.syncDisabledReason).toContain('property');
    expect(v.counters.map((c) => c.value)).toEqual([0, 0, 0, 0]);
    expect(v.dateRange).toBeNull();
  });

  it('not authorized → disabled with auth-only hint; status label', () => {
    const v = gscSyncView({ status: 'not_authorized', property: 'sc-domain:example.com', authorized: false, coverage });
    expect(v.canSync).toBe(false);
    expect(v.syncDisabledReason).toContain('auth-only');
    expect(v.statusFa).toBe('بدون مجوز Google');
  });

  it('running → button disabled, polling on, step label + percent', () => {
    const v = gscSyncView({ status: 'running', property: 'sc-domain:example.com', authorized: true, step: 'snapshot', step_fa: null, progress: 0.5, coverage });
    expect(v.running).toBe(true);
    expect(v.canSync).toBe(false);
    expect(v.shouldPoll).toBe(true);
    expect(v.percent).toBe(50);
    expect(v.stepFa).toBe(GSC_STEP_FA.snapshot);
  });

  it('succeeded → counters (queries/important/pages/rows) + last sync; busy disables', () => {
    const v = gscSyncView({ status: 'succeeded', property: 'sc-domain:example.com', authorized: true, finished_at: '2026-08-20T07:00:00Z', progress: 1, coverage });
    expect(v.counters.map((c) => [c.key, c.value])).toEqual([['queries', 66], ['important_queries', 43], ['pages', 38], ['rows', 731]]);
    expect(v.lastSync).toBe('2026-08-20T07:00:00Z');
    expect(v.percent).toBe(100);
    expect(gscSyncView({ status: 'succeeded', property: 'x', authorized: true, coverage }, { busy: true }).canSync).toBe(false);
  });

  it('step rows: default pending list; server steps with error text (errors display)', () => {
    expect(gscStepRows(null).map((r) => r.status)).toEqual(['pending', 'pending', 'pending', 'pending']);
    const rows = gscStepRows({ steps: [{ key: 'sync', status: 'failed', error: 'GscAuthError' }, { key: 'snapshot', status: 'skipped' }] });
    expect(rows[0]).toEqual({ key: 'sync', fa: GSC_STEP_FA.sync, status: 'failed', info: 'GscAuthError' });
    expect(rows[1].status).toBe('skipped');
  });
});
