import type { ContentStatus } from '@/lib/api/client';

export const STATUS_FA: Record<ContentStatus, string> = {
  planned: 'برنامه‌ریزی‌شده',
  brief_ready: 'بریف آماده',
  writing: 'در حال نگارش',
  review: 'بازبینی',
  approved: 'تأییدشده',
  published: 'منتشرشده'
};
export const STATUS_ORDER: ContentStatus[] = ['planned', 'brief_ready', 'writing', 'review', 'approved', 'published'];
export const STATUS_COLOR: Record<ContentStatus, string> = {
  planned: '#64748b',
  brief_ready: '#0ea5e9',
  writing: '#f59e0b',
  review: '#a855f7',
  approved: '#22c55e',
  published: '#16a34a'
};
export const PRIORITY_FA: Record<string, string> = { high: 'بالا', medium: 'متوسط', low: 'کم' };
export const INTENT_FA: Record<string, string> = { informational: 'اطلاعاتی', navigational: 'ناوبری', commercial: 'تجاری', transactional: 'تراکنشی', local: 'محلی' };
export const TASK_FA: Record<string, string> = {
  content_writing: 'نگارش محتوا',
  seo_analysis: 'تحلیل سئو',
  research: 'تحقیق',
  brief: 'بریف محتوا',
  keyword_analysis: 'تحلیل کلمات کلیدی',
  internal_linking: 'لینک‌سازی داخلی',
  schema: 'اسکیما',
  generic: 'عمومی',
  outline: 'ساختار مقاله',
  article_section: 'نگارش بخش مقاله',
  article_long: 'مقاله بلند',
  rewrite: 'بازنویسی',
  seo_review: 'بازبینی سئو',
  fact_check: 'راستی‌آزمایی',
  title_meta: 'عنوان و متا',
  faq: 'پرسش‌های متداول',
  translation: 'ترجمه'
};

/** Jalali helpers via ICU (no library): parts for a Gregorian date. */
const jfmt = new Intl.DateTimeFormat('en-US-u-ca-persian', { year: 'numeric', month: 'numeric', day: 'numeric', timeZone: 'UTC' });
export function jalali(d: Date): { y: number; m: number; d: number } {
  const p = Object.fromEntries(jfmt.formatToParts(d).filter((x) => x.type !== 'literal').map((x) => [x.type, Number(x.value)]));
  return { y: p.year, m: p.month, d: p.day };
}
export const JMONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
export const WEEKDAYS_FA = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج']; // Saturday-first
export const iso = (d: Date) => d.toISOString().slice(0, 10);
export const utcDate = (isoDay: string) => new Date(isoDay + 'T00:00:00Z');
export function addDays(d: Date, n: number): Date {
  const x = new Date(d); x.setUTCDate(x.getUTCDate() + n); return x;
}
/** Return all Gregorian days (UTC) of the Jalali month containing `anchor`. */
export function jalaliMonthDays(anchor: Date): { days: Date[]; y: number; m: number } {
  const j = jalali(anchor);
  let start = new Date(anchor);
  while (jalali(start).d !== 1) start = addDays(start, -1);
  const days: Date[] = [];
  let cur = start;
  while (jalali(cur).m === j.m && days.length < 32) { days.push(cur); cur = addDays(cur, 1); }
  return { days, y: j.y, m: j.m };
}
export const faNum = new Intl.NumberFormat('fa-IR');
export const faYear = new Intl.NumberFormat('fa-IR', { useGrouping: false });

/** Inverse via the same ICU calendar: Gregorian ISO day for a Jalali date; null if invalid (e.g. ۳۰ اسفند سال غیرکبیسه). */
export function jalaliToIso(jy: number, jm: number, jd: number): string | null {
  if (jy < 1300 || jy > 1500 || jm < 1 || jm > 12 || jd < 1 || jd > 31) return null;
  let cur = utcDate(`${jy + 621}-03-15`);                                   // چند روز قبل از نوروز همان سال
  for (let i = 0; i < 12 && !(jalali(cur).m === 1 && jalali(cur).d === 1); i += 1) cur = addDays(cur, 1);
  const g = addDays(cur, (jm <= 7 ? (jm - 1) * 31 : 186 + (jm - 7) * 30) + jd - 1);
  const back = jalali(g);
  return back.y === jy && back.m === jm && back.d === jd ? iso(g) : null;
}
const toLatinDigits = (s: string) => s.replace(/[۰-۹]/g, (c) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(c))).replace(/[٠-٩]/g, (c) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(c)));
/** «۱۴۰۵/۶/۵» یا 1405-06-05 (ارقام فارسی/عربی/لاتین، جداکننده / - . فاصله) → ISO میلادی، وگرنه null. */
export function parseJalali(text: string): string | null {
  const m = toLatinDigits(text.trim()).match(/^(\d{4})[/\-.\s](\d{1,2})[/\-.\s](\d{1,2})$/);
  return m ? jalaliToIso(+m[1], +m[2], +m[3]) : null;
}
const fa2 = (n: number) => faYear.format(n).padStart(2, '۰');
export const jalaliNumeric = (isoDay?: string | null): string => { if (!isoDay) return ''; const j = jalali(utcDate(isoDay)); return `${faYear.format(j.y)}/${fa2(j.m)}/${fa2(j.d)}`; };
export const jalaliLong = (isoDay?: string | null): string => { if (!isoDay) return ''; const j = jalali(utcDate(isoDay)); return `${faNum.format(j.d)} ${JMONTHS[j.m - 1]} ${faYear.format(j.y)}`; };
