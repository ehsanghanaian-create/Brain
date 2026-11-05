import { describe, expect, it } from 'vitest';
import { navGroups } from '@/config/nav-config';
import { pearlNavigation } from '../navigation-model';

describe('complete Salimore navigation inventory', () => {
  it('preserves every existing destination and its exact title', () => {
    const actual = pearlNavigation.flatMap((group) => group.entries);
    for (const item of navGroups.flatMap((group) => group.items)) {
      expect(actual).toContainEqual(expect.objectContaining({ href: item.url, label: item.title }));
    }
    expect(actual).toHaveLength(22);
    expect(new Set(actual.map((item) => item.href)).size).toBe(22);
  });
  it('keeps settings and the non-dashboard advertising route', () => {
    const urls = pearlNavigation.flatMap((group) => group.entries.map((item) => item.href));
    expect(urls).toContain('/ads-data');
    expect(urls).toContain('/dashboard/settings');
  });
});
