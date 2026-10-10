import { describe, expect, it } from 'vitest';
import { allowedPage, homeFor } from '../panel-access';

describe('panel page permissions', () => {
  it('keeps call-center operators on the call-center page', () => {
    expect(homeFor('call_center')).toBe('/dashboard/call-center');
    expect(allowedPage('call_center', '/dashboard/call-center')).toBe(true);
    expect(allowedPage('call_center', '/dashboard/users')).toBe(false);
    expect(allowedPage('call_center', '/dashboard/work')).toBe(false);
    expect(allowedPage('call_center', '/ads-data')).toBe(false);
  });
  it('gives analysts read-only dashboard routes without user management', () => {
    expect(allowedPage('analyst', '/dashboard/reports')).toBe(true);
    expect(allowedPage('analyst', '/dashboard/work')).toBe(true);
    expect(allowedPage('analyst', '/dashboard/sites/demo')).toBe(true);
    expect(allowedPage('analyst', '/dashboard/users')).toBe(false);
    expect(allowedPage('admin', '/dashboard/users')).toBe(true);
    expect(allowedPage('admin', '/dashboard/team-management')).toBe(false);
    expect(allowedPage('admin', '/dashboard/team-management', true)).toBe(true);
    expect(allowedPage('analyst', '/dashboard/team-management', true)).toBe(false);
  });
});
