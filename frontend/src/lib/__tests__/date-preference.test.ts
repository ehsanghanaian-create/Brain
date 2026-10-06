import { describe, expect, it } from 'vitest';
import { formatUserDay } from '../date-preference';
import { userMonthDays } from '../calendar-days';

describe('per-user calendar', () => {
  it('shows one stored ISO day in the selected calendar without changing the day', () => {
    expect(formatUserDay('2026-10-06', 'jalali')).toContain('۱۴۰۵');
    expect(formatUserDay('2026-10-06', 'gregorian')).toContain('۲۰۲۶');
  });

  it('changes the actual month grid between Jalali and Gregorian calendars', () => {
    const anchor = new Date('2026-10-06T12:00:00Z');
    const gregorian = userMonthDays(anchor, 'gregorian');
    const jalali = userMonthDays(anchor, 'jalali');
    expect(gregorian[0].toISOString().slice(0, 10)).toBe('2026-10-01');
    expect(jalali[0].toISOString().slice(0, 10)).not.toBe('2026-10-01');
  });
});
