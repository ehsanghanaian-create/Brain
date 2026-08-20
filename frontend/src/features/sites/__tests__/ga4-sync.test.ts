import { describe, expect, it } from 'vitest';
import { GA4_STEP_FA, ga4StepRows, ga4SyncView } from '../ga4-sync';

const coverage = { date_from: '2026-07-20', date_to: '2026-08-18', rows: 900, pages: 42, sessions: 5400, users: 4100, conversions: 37.0, content_snapshots: 8, top_pages: [{ path: '/a/', sessions: 800, conversions: 5 }, { path: '/b/', sessions: 300, conversions: 0 }] };

describe('GA4 Sync Card helpers', () => {
  it('connected + authorized + never synced → sync enabled, no polling', () => {
    const v = ga4SyncView({ status: 'never', property: '471988572', authorized: true, coverage });
    expect(v.canSync).toBe(true);
    expect(v.shouldPoll).toBe(false);
    expect(v.dateRange).toBe('2026-07-20 → 2026-08-18');
    expect(v.topPages).toHaveLength(2);
  });

  it('no property / no scope → disabled with Persian reason', () => {
    expect(ga4SyncView({ status: 'never', property: null, authorized: true }).syncDisabledReason).toContain('Property ID');
    const v = ga4SyncView({ status: 'not_authorized', property: '471988572', authorized: false, coverage });
    expect(v.canSync).toBe(false);
    expect(v.syncDisabledReason).toContain('analytics.readonly');
    expect(v.statusFa).toBe('بدون مجوز Google');
  });

  it('running → polling on, step label + percent; busy disables', () => {
    const v = ga4SyncView({ status: 'running', property: '471988572', authorized: true, step: 'snapshot', step_fa: null, progress: 2 / 3, coverage });
    expect(v.running).toBe(true);
    expect(v.shouldPoll).toBe(true);
    expect(v.percent).toBe(67);
    expect(v.stepFa).toBe(GA4_STEP_FA.snapshot);
    expect(ga4SyncView({ status: 'succeeded', property: 'x', authorized: true, coverage }, { busy: true }).canSync).toBe(false);
  });

  it('succeeded → counters sessions/users/conversions/pages + last sync', () => {
    const v = ga4SyncView({ status: 'succeeded', property: '471988572', authorized: true, finished_at: '2026-08-20T09:00:00Z', progress: 1, coverage });
    expect(v.counters.map((c) => [c.key, c.value])).toEqual([['sessions', 5400], ['users', 4100], ['conversions', 37], ['pages', 42]]);
    expect(v.lastSync).toBe('2026-08-20T09:00:00Z');
    expect(v.percent).toBe(100);
  });

  it('step rows: default pending; server steps with error text (errors display)', () => {
    expect(ga4StepRows(null).map((r) => r.status)).toEqual(['pending', 'pending', 'pending']);
    const rows = ga4StepRows({ steps: [{ key: 'sync', status: 'failed', error: 'permission denied' }, { key: 'graph', status: 'skipped' }] });
    expect(rows[0]).toEqual({ key: 'sync', fa: GA4_STEP_FA.sync, status: 'failed', info: 'permission denied' });
    expect(rows[1].status).toBe('skipped');
  });
});
