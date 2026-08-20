import type { SaGscCheck, SaGscStatus } from '@/lib/api/client';
import { friendlyDomain } from '@/features/onboarding/lib';

/** Pure helpers for the Service-Account GSC card (unit-tested) — friendly domains, view states, no jargon. */
export type SaCardView = {
  state: 'not_configured' | 'ready' | 'checked';
  email: string | null;
  properties: { domain: string; property: string; permission: string | null }[];
  lastCheck: string | null;
  emptyHint: string | null;
};

export function saCardView(s: Partial<SaGscStatus> | null | undefined): SaCardView {
  const props = (s?.accessible_properties ?? []).map((p) => ({
    domain: friendlyDomain(p.property), property: p.property, permission: p.permission ?? null
  }));
  const configured = Boolean(s?.configured && s?.service_account_email);
  return {
    state: !configured ? 'not_configured' : s?.last_check ? 'checked' : 'ready',
    email: s?.service_account_email ?? null,
    properties: props,
    lastCheck: s?.last_check ?? null,
    emptyHint: configured && s?.last_check && props.length === 0
      ? 'هنوز دسترسی‌ای پیدا نشد — ایمیل بالا را در Search Console سایت خود به‌عنوان کاربر اضافه کنید و دوباره «بررسی دسترسی» بزنید.'
      : null
  };
}

export function checkResultView(r: Partial<SaGscCheck> | null | undefined): { ok: boolean; text: string } {
  if (!r) return { ok: false, text: 'پاسخی دریافت نشد' };
  if (r.status === 'ok') {
    const n = r.properties?.length ?? 0;
    return n > 0
      ? { ok: true, text: `${n.toLocaleString('fa-IR')} سایت با دسترسی فعال پیدا شد` }
      : { ok: true, text: 'اتصال برقرار است ولی هنوز به هیچ سایتی دسترسی داده نشده' };
  }
  if (r.status === 'not_configured') return { ok: false, text: 'Service Account هنوز ثبت نشده است' };
  return { ok: false, text: r.message ?? 'بررسی ناموفق بود' };
}
