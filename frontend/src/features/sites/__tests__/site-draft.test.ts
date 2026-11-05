import { describe, expect, it } from 'vitest';
import { parseSiteDraft, siteDraftHref } from '../site-draft';

describe('navigation to site wizard handoff', () => {
  it('preserves Persian names and the site origin through a URL roundtrip', () => {
    const href = siteDraftHref({ name: 'فروشگاه سالیمور', domain: 'shop.example.com' });
    const params = new URL(href, 'https://brain.example').searchParams;
    expect(parseSiteDraft({ name: params.get('name'), domain: params.get('domain') })).toEqual({
      name: 'فروشگاه سالیمور',
      domain: 'https://shop.example.com'
    });
  });
  it('never carries credentials or non-HTTP schemes into setup', () => {
    for (const domain of [
      'https://user:password@example.com',
      'javascript:alert(1)',
      'file:///tmp/site',
      'not a domain'
    ]) {
      expect(parseSiteDraft({ name: 'سایت', domain }).domain).toBe('');
    }
    expect(parseSiteDraft({ domain: 'https://example.com/private?token=secret#part' }).domain).toBe(
      'https://example.com'
    );
  });
  it('handles missing parameters without breaking existing wizard links', () => {
    expect(parseSiteDraft({})).toEqual({ name: '', domain: '' });
    expect(parseSiteDraft({ name: ['a'], domain: ['example.com'] })).toEqual({
      name: '',
      domain: ''
    });
  });
});
