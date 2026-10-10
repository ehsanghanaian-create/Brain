import { describe, expect, it } from 'vitest';
import { isPublicBackendRoute } from '../backend-route-access';

describe('backend route access', () => {
  it.each([
    ['auth', 'login'],
    ['auth', 'status'],
    ['connections', 'google', 'callback']
  ])('allows the exact public route %s', (...segments) => {
    expect(isPublicBackendRoute(segments)).toBe(true);
  });

  it.each([
    ['connections', 'google', 'authorize'],
    ['connections', 'google', 'status'],
    ['connections', 'google', 'callback', 'extra'],
    ['connections', 'ga4', 'properties'],
    ['sites'],
    ['auth', 'logout']
  ])('keeps the private route %s protected', (...segments) => {
    expect(isPublicBackendRoute(segments)).toBe(false);
  });
});
