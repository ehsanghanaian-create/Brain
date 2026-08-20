import { describe, expect, it } from 'vitest';
import { checkResultView, saCardView } from '../gsc-sa';

describe('GSC Service Account card helpers', () => {
  it('not configured → hidden state', () => {
    expect(saCardView({ configured: false, service_account_email: null, accessible_properties: [], last_check: null }).state).toBe('not_configured');
    expect(saCardView(null).state).toBe('not_configured');
  });

  it('configured, never checked → ready with email, no hint', () => {
    const v = saCardView({ configured: true, service_account_email: 'seo-brain-gsc-reader@p.iam.gserviceaccount.com', accessible_properties: [], last_check: null });
    expect(v.state).toBe('ready');
    expect(v.email).toContain('gserviceaccount.com');
    expect(v.emptyHint).toBeNull();
  });

  it('checked with properties → friendly domains (no sc-domain prefix in the UI)', () => {
    const v = saCardView({ configured: true, service_account_email: 'x@p.iam.gserviceaccount.com', last_check: '2026-08-20T18:00:00Z',
      accessible_properties: [{ property: 'sc-domain:renaultemdad.com', permission: 'siteFullUser' }, { property: 'https://modirankhodro-emdad.com/', permission: 'siteRestrictedUser' }] });
    expect(v.state).toBe('checked');
    expect(v.properties.map((p) => p.domain)).toEqual(['renaultemdad.com', 'modirankhodro-emdad.com']);
    expect(v.properties[0].property).toBe('sc-domain:renaultemdad.com');   // real value kept for site creation
    expect(v.emptyHint).toBeNull();
  });

  it('checked but zero access → guidance hint (error state)', () => {
    const v = saCardView({ configured: true, service_account_email: 'x@p.iam.gserviceaccount.com', accessible_properties: [], last_check: '2026-08-20T18:00:00Z' });
    expect(v.emptyHint).toContain('Search Console');
  });

  it('check result → toast text for ok/empty/error', () => {
    expect(checkResultView({ status: 'ok', properties: [{ property: 'x', permission: null }] }).ok).toBe(true);
    expect(checkResultView({ status: 'ok', properties: [] }).text).toContain('هنوز');
    expect(checkResultView({ status: 'error', message: 'بررسی دسترسی ناموفق بود (HttpError)' }).ok).toBe(false);
    expect(checkResultView(null).ok).toBe(false);
  });
});
