export const BUSINESS_CATEGORIES: { value: string; label: string }[] = [
  { value: 'auto-service', label: 'خدمات خودرو / امداد خودرو' },
  { value: 'auto-dealer', label: 'نمایندگی و فروش خودرو' },
  { value: 'local-service', label: 'خدمات محلی (تعمیرات، نصب، …)' },
  { value: 'ecommerce', label: 'فروشگاه اینترنتی' },
  { value: 'medical', label: 'پزشکی و سلامت' },
  { value: 'education', label: 'آموزش' },
  { value: 'real-estate', label: 'املاک' },
  { value: 'saas', label: 'نرم‌افزار / SaaS' },
  { value: 'media', label: 'رسانه و محتوا' },
  { value: 'other', label: 'سایر' }
];

export const LANGUAGES: { value: string; label: string }[] = [
  { value: 'fa-IR', label: 'فارسی (fa-IR)' },
  { value: 'en-US', label: 'English (en-US)' },
  { value: 'ar', label: 'العربية (ar)' },
  { value: 'tr', label: 'Türkçe (tr)' },
  { value: 'de', label: 'Deutsch (de)' }
];

export const COUNTRIES: { value: string; label: string; tz: string }[] = [
  { value: 'IR', label: 'ایران', tz: 'Asia/Tehran' },
  { value: 'AE', label: 'امارات', tz: 'Asia/Dubai' },
  { value: 'TR', label: 'ترکیه', tz: 'Europe/Istanbul' },
  { value: 'IQ', label: 'عراق', tz: 'Asia/Baghdad' },
  { value: 'DE', label: 'آلمان', tz: 'Europe/Berlin' },
  { value: 'US', label: 'آمریکا', tz: 'America/New_York' },
  { value: 'GB', label: 'بریتانیا', tz: 'Europe/London' }
];

export const MODE_FA: Record<'manual' | 'assisted' | 'autopilot', string> = {
  manual: 'دستی',
  assisted: 'نیمه‌خودکار',
  autopilot: 'خودکار'
};

export const CONNECTION_STATUS_FA: Record<string, string> = {
  ok: 'متصل',
  not_configured: 'پیکربندی نشده',
  not_authorized: 'بدون مجوز',
  not_found: 'یافت نشد',
  error: 'خطا'
};

/** slug from a domain/URL, mirrors backend seo_brain.sites.slugify_domain */
export function slugifyDomain(input: string): string {
  let host = input.trim().toLowerCase();
  try {
    host = new URL(host.includes('://') ? host : `https://${host}`).hostname;
  } catch {
    /* keep raw */
  }
  host = host.replace(/^www\./, '');
  const base = host.includes('.') ? host.slice(0, host.lastIndexOf('.')) : host;
  return base.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 63) || 'site';
}

export function normalizeUrl(input: string): string {
  const v = input.trim();
  if (!v) return '';
  const withScheme = v.includes('://') ? v : `https://${v}`;
  try {
    const u = new URL(withScheme);
    return `${u.protocol}//${u.hostname}/`;
  } catch {
    return withScheme;
  }
}
