import { describe, expect, it } from 'vitest';
import { navigationHref, siteFromLocation } from '../routing';
import { sessionDisplayName } from '../session-display';

describe('operational navigation', () => {
  it('carries the selected site and preserves other filters', () => {
    expect(navigationHref('/dashboard/graph?mode=links', 'salimore')).toBe(
      '/dashboard/graph?mode=links&site=salimore'
    );
    expect(navigationHref('/dashboard/calendar?site=old&plan=7', 'new')).toBe(
      '/dashboard/calendar?site=new&plan=7'
    );
    expect(navigationHref('/dashboard/sites/new', 'salimore')).toBe('/dashboard/sites/new');
    expect(navigationHref('/ads-data', 'salimore')).toBe('/ads-data');
  });
  it('recognizes site detail paths without treating new as a site', () => {
    expect(siteFromLocation('/dashboard/sites/salimore', null)).toBe('salimore');
    expect(siteFromLocation('/dashboard/graph', 'salimore')).toBe('salimore');
    expect(siteFromLocation('/dashboard/sites/new', null)).toBe('');
  });
  it('displays session identity without manufacturing a role or accepting expiry', () => {
    const payload = Buffer.from(`manager\n${Math.floor(Date.now() / 1000) + 3600}\nnonce`).toString(
      'base64url'
    );
    expect(sessionDisplayName(`${payload}.signature`)).toBe('manager');
    expect(
      sessionDisplayName(`${Buffer.from('manager\n1\nnonce').toString('base64url')}.signature`)
    ).toBeNull();
    expect(sessionDisplayName('invalid')).toBeNull();
    expect(sessionDisplayName()).toBeNull();
  });
});
