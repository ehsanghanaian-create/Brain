import type { GoogleAccountStatus } from '@/lib/api/client';

/** Pure helpers for the Google Account card (unit-tested): view state, permission chips, button gating. */
export type GoogleAccountView = {
  state: 'no_client' | 'disconnected' | 'connected' | 'needs_reconnect' | 'temporary_error';
  title: string;
  canConnect: boolean;
  canDisconnect: boolean;
  email: string | null;
  permissions: { key: string; fa: string; granted: boolean }[];
  hint: string | null;
};

export function googleAccountView(s: Partial<GoogleAccountStatus> | null | undefined, opts: { busy?: boolean } = {}): GoogleAccountView {
  const clientOk = s?.client_configured !== false;
  const connected = Boolean(s?.connected);
  const state = !clientOk ? 'no_client' : connected ? 'connected'
    : s?.authorization_state === 'needs_reconnect' ? 'needs_reconnect'
    : s?.authorization_state === 'temporary_error' ? 'temporary_error' : 'disconnected';
  return {
    state,
    title: state === 'connected' ? 'حساب گوگل متصل است' : state === 'no_client' ? 'پیکربندی گوگل ناقص است'
      : state === 'needs_reconnect' ? 'مجوز گوگل منقضی یا لغو شده است'
      : state === 'temporary_error' ? 'تمدید اتصال گوگل موقتاً ناموفق بود' : 'حساب گوگل متصل نیست',
    canConnect: clientOk && !connected && !opts.busy,
    canDisconnect: Boolean(connected || s?.refresh_token_stored) && !opts.busy,
    email: s?.email ?? null,
    permissions: [
      { key: 'gsc', fa: 'Search Console (فقط‌خواندنی)', granted: Boolean(s?.gsc_scope) },
      { key: 'ga4', fa: 'Google Analytics (فقط‌خواندنی)', granted: Boolean(s?.ga4_scope) }
    ],
    hint: state === 'no_client'
      ? 'در Google Cloud Console یک OAuth Client از نوع «Desktop app» بسازید و شناسه‌ها را در فرم زیر ذخیره کنید — نیازی به ویرایش .env نیست'
      : state === 'needs_reconnect'
        ? 'گوگل refresh token ذخیره‌شده را رد کرد. اگر این اتفاق هر هفت روز تکرار می‌شود، وضعیت OAuth برنامه را در Google Auth Platform → Audience بررسی کنید؛ برنامهٔ Testing مجوز بلندمدت نمی‌دهد.'
      : state === 'temporary_error'
        ? 'مجوز ذخیره‌شده حفظ شده است؛ اتصال شبکه را بررسی کنید و چند دقیقه دیگر وضعیت را تازه کنید.'
      : state === 'connected' && !s?.ga4_scope
        ? 'توکن فعلی اسکوپ GA4 ندارد؛ برای فعال‌شدن GA4 یک‌بار «اتصال دوباره» بزنید'
        : null
  };
}
