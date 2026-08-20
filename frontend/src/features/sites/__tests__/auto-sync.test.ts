import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { autoSyncLine, intervalFa, nextSyncFa } from '../auto-sync';

const plan = (over: object = {}) => ({
  site_id: 's', enabled: true, interval_hours: 24,
  sources: {
    wordpress: { configured: true, last_success: '2026-08-20T05:00:00Z', next_at: '2026-08-21T05:00:00Z', due: false },
    gsc: { configured: true, last_success: null, next_at: '2026-08-20T09:00:00Z', due: true },
    ga4: { configured: false, last_success: null, next_at: null, due: false }
  }, ...over
});

describe('auto-sync helpers', () => {
  beforeEach(() => vi.useFakeTimers().setSystemTime(new Date('2026-08-20T10:00:00Z')));
  afterEach(() => vi.useRealTimers());

  it('intervalFa: daily / multi-day / hourly', () => {
    expect(intervalFa(24)).toBe('روزانه');
    expect(intervalFa(72)).toContain('روز');
    expect(intervalFa(6)).toContain('ساعت');
  });

  it('nextSyncFa picks the soonest next_at; past → «در نوبت اجرا»', () => {
    expect(nextSyncFa(plan())).toBe('در نوبت اجرا');            // gsc next_at is in the past
    const future = plan({ sources: { ...plan().sources, gsc: { ...plan().sources.gsc, next_at: '2026-08-21T02:00:00Z', due: false } } });
    expect(nextSyncFa(future)).not.toBe('در نوبت اجرا');
    expect(nextSyncFa(future)).toBeTruthy();
  });

  it('disabled plan → خاموش, no next; null-safe', () => {
    expect(autoSyncLine(plan({ enabled: false }))).toBe('به‌روزرسانی خودکار: خاموش');
    expect(autoSyncLine(plan())).toContain('روزانه');
    expect(nextSyncFa(null)).toBeNull();
    expect(autoSyncLine(null)).toBe('');
  });
});
