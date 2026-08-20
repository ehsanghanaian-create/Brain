import type { GoogleAccountStatus } from '@/lib/api/client';

/** Pure helpers for the Google Account card (unit-tested): view state, permission chips, button gating. */
export type GoogleAccountView = {
  state: 'no_client' | 'disconnected' | 'connected';
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
  const state = !clientOk ? 'no_client' : connected ? 'connected' : 'disconnected';
  return {
    state,
    title: state === 'connected' ? 'حساب گوگل متصل است' : state === 'no_client' ? 'پیکربندی گوگل ناقص است' : 'حساب گوگل متصل نیست',
    canConnect: clientOk && !connected && !opts.busy,
    canDisconnect: connected && !opts.busy,
    email: s?.email ?? null,
    permissions: [
      { key: 'gsc', fa: 'Search Console (فقط‌خواندنی)', granted: Boolean(s?.gsc_scope) },
      { key: 'ga4', fa: 'Google Analytics (فقط‌خواندنی)', granted: Boolean(s?.ga4_scope) }
    ],
    hint: state === 'no_client'
      ? 'GOOGLE_CLIENT_ID/SECRET تنظیم نشده است (در .env یا SecretStore) — یک OAuth Client از نوع Desktop در Google Cloud بسازید'
      : state === 'connected' && !s?.ga4_scope
        ? 'توکن فعلی اسکوپ GA4 ندارد؛ برای فعال‌شدن GA4 یک‌بار «اتصال دوباره» بزنید'
        : null
  };
}
