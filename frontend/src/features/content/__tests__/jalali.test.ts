import { describe, expect, it } from 'vitest';
import { jalali, jalaliLong, jalaliNumeric, jalaliToIso, parseJalali, utcDate } from '../constants';

describe('jalali ⇄ gregorian', () => {
  it('converts known dates both ways', () => {
    expect(jalaliToIso(1405, 6, 5)).toBe('2026-08-27');                    // امروزِ تست انتشار
    expect(jalaliToIso(1403, 1, 1)).toBe('2024-03-20');                    // نوروز ۱۴۰۳
    expect(jalaliToIso(1403, 12, 30)).toBe('2025-03-20');                  // ۱۴۰۳ کبیسه است
    expect(jalali(utcDate('2026-08-27'))).toEqual({ y: 1405, m: 6, d: 5 });
  });
  it('rejects invalid Jalali dates', () => {
    expect(jalaliToIso(1404, 12, 30)).toBeNull();                          // ۱۴۰۴ کبیسه نیست
    expect(jalaliToIso(1405, 7, 31)).toBeNull();                           // مهر ۳۰روزه است
    expect(jalaliToIso(1405, 13, 1)).toBeNull();
  });
  it('round-trips every month boundary of a full year', () => {
    for (let m = 1; m <= 12; m += 1) {
      const isoDay = jalaliToIso(1405, m, 1);
      expect(isoDay).toBeTruthy();
      expect(jalali(utcDate(isoDay!))).toEqual({ y: 1405, m, d: 1 });
    }
  });
  it('parses Persian and Latin digit inputs with mixed separators', () => {
    expect(parseJalali('۱۴۰۵/۰۶/۰۵')).toBe('2026-08-27');
    expect(parseJalali('1405-6-5')).toBe('2026-08-27');
    expect(parseJalali('1405.06.05')).toBe('2026-08-27');
    expect(parseJalali('1405/13/01')).toBeNull();
    expect(parseJalali('نامعتبر')).toBeNull();
  });
  it('formats ISO days back to Persian strings', () => {
    expect(jalaliNumeric('2026-08-27')).toBe('۱۴۰۵/۰۶/۰۵');
    expect(jalaliLong('2026-08-27')).toBe('۵ شهریور ۱۴۰۵');
    expect(jalaliNumeric(null)).toBe('');
  });
});
