import { describe, expect, it } from 'vitest';
import { googleAccountView } from '../google-account';

describe('Google Account card helpers', () => {
  it('no client config → no_client state, connect disabled, setup hint', () => {
    const v = googleAccountView({ connected: false, client_configured: false });
    expect(v.state).toBe('no_client');
    expect(v.canConnect).toBe(false);
    expect(v.hint).toContain('Desktop app');
  });

  it('disconnected → connect enabled; busy disables', () => {
    const v = googleAccountView({ connected: false, client_configured: true });
    expect(v.state).toBe('disconnected');
    expect(v.canConnect).toBe(true);
    expect(v.canDisconnect).toBe(false);
    expect(googleAccountView({ connected: false, client_configured: true }, { busy: true }).canConnect).toBe(false);
  });

  it('connected → email + both permission chips + disconnect enabled', () => {
    const v = googleAccountView({ connected: true, client_configured: true, email: 'user@example.com', gsc_scope: true, ga4_scope: true });
    expect(v.state).toBe('connected');
    expect(v.email).toBe('user@example.com');
    expect(v.permissions).toEqual([
      { key: 'gsc', fa: 'Search Console (فقط‌خواندنی)', granted: true },
      { key: 'ga4', fa: 'Google Analytics (فقط‌خواندنی)', granted: true }
    ]);
    expect(v.canDisconnect).toBe(true);
    expect(v.hint).toBeNull();
  });

  it('connected legacy token without GA4 scope → re-consent hint', () => {
    const v = googleAccountView({ connected: true, client_configured: true, email: null, gsc_scope: true, ga4_scope: false });
    expect(v.permissions[1].granted).toBe(false);
    expect(v.hint).toContain('اتصال دوباره');
  });
});
