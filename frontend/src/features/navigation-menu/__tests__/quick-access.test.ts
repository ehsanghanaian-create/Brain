import { describe, expect, it } from 'vitest';
import { DEFAULT_QUICK_ACCESS, normalizeQuickAccess, quickAccessKey } from '../quick-access';

describe('account quick-access preferences', () => {
  it('keeps a saved order, removes duplicates and ignores non-product destinations', () => {
    expect(
      normalizeQuickAccess(['calendar', 'graph', 'calendar', 'https://example.com', 'unknown', 9])
    ).toEqual(['calendar', 'graph']);
  });
  it('bounds a saved rail and handles missing or deliberately empty preferences', () => {
    expect(
      normalizeQuickAccess(['overview', 'graph', 'keywords', 'calendar', 'research', 'reports'])
    ).toHaveLength(5);
    expect(normalizeQuickAccess(null)).toEqual(DEFAULT_QUICK_ACCESS);
    expect(normalizeQuickAccess([])).toEqual([]);
  });
  it('separates accounts without accepting a storage path from the username', () => {
    expect(quickAccessKey('amir')).not.toBe(quickAccessKey('manager'));
    expect(quickAccessKey('a/b')).toContain('a%2Fb');
  });
});
