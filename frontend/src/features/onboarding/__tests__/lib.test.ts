import { describe, expect, it } from 'vitest';
import { friendlyDomain, mergeDiscovery, siteSlug } from '../lib';

describe('onboarding helpers', () => {
  it('friendlyDomain strips sc-domain:, protocol, www and paths', () => {
    expect(friendlyDomain('sc-domain:example.com')).toBe('example.com');
    expect(friendlyDomain('https://www.example.com/')).toBe('example.com');
    expect(friendlyDomain('http://example.com/some/path')).toBe('example.com');
    expect(friendlyDomain(null)).toBe('');
  });

  it('siteSlug makes a valid site id from a domain', () => {
    expect(siteSlug('example.com')).toBe('example-com');
    expect(siteSlug('پارس.example.co.uk')).toMatch(/^[a-z0-9-]+$/);
  });

  it('mergeDiscovery groups by domain, prefers sc-domain + owner, sorts verified first', () => {
    const gsc = [
      { property: 'https://example.com/', permission: 'siteOwner' },
      { property: 'sc-domain:example.com', permission: 'siteOwner' },
      { property: 'sc-domain:other.com', permission: 'siteUnverifiedUser' }
    ];
    const out = mergeDiscovery(gsc, []);
    expect(out).toHaveLength(2);
    expect(out[0].domain).toBe('example.com');
    expect(out[0].gsc_property).toBe('sc-domain:example.com');       // sc-domain wins over url-prefix
    expect(out[0].verified).toBe(true);
    expect(out[1].domain).toBe('other.com');
    expect(out[1].verified).toBe(false);                              // unverified sinks to the bottom
  });

  it('mergeDiscovery matches GA4 by website_url first (exact domain beats name similarity)', () => {
    const gsc = [{ property: 'sc-domain:kermanemdad.com', permission: 'siteOwner' }];
    const ga4 = [
      { property_id: '111', display_name: 'kermanemdad-lookalike', account: 'A', website_url: null },
      { property_id: '222', display_name: 'Totally Different Name', account: 'A', website_url: 'https://www.kermanemdad.com/' }
    ];
    expect(mergeDiscovery(gsc, ga4)[0].ga4?.property_id).toBe('222');   // URL match wins over the name heuristic
  });

  it('mergeDiscovery guesses GA4 by name similarity (editable guess, never an ID in the UI)', () => {
    const gsc = [{ property: 'sc-domain:kermanemdad.com', permission: 'siteOwner' }];
    const ga4 = [
      { property_id: '111', display_name: 'Something Else', account: 'A' },
      { property_id: '471988572', display_name: 'Emdad Kerman Motor kermanemdad', account: 'A' }
    ];
    const out = mergeDiscovery(gsc, ga4);
    expect(out[0].ga4?.property_id).toBe('471988572');
    // no plausible match → null (the card simply shows «بدون آنالیتیکس»)
    expect(mergeDiscovery([{ property: 'sc-domain:zzz-qqq.com', permission: 'siteOwner' }], ga4)[0].ga4).toBeNull();
  });
});
