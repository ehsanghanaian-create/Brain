import type { Ga4Property } from '@/lib/api/client';

/** Pure helpers for the non-technical onboarding flow (unit-tested):
 *  friendly domains (no sc-domain:/protocol jargon), GSC+GA4 discovery merge, site slugs. */

export function friendlyDomain(input: string | null | undefined): string {
  if (!input) return '';
  let s = String(input).trim();
  if (s.startsWith('sc-domain:')) s = s.slice('sc-domain:'.length);
  s = s.replace(/^https?:\/\//, '').replace(/^www\./, '');
  return s.replace(/\/.*$/, '').toLowerCase();
}

export function siteSlug(domain: string): string {
  return domain.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 63) || 'site';
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9؀-ۿ]+/g, '');

export type DiscoveredSite = {
  domain: string;
  gsc_property: string;            // best GSC property for the domain (sc-domain preferred, owner preferred)
  gsc_permission: string | null;
  verified: boolean;               // user has real access (not siteUnverifiedUser)
  ga4: Ga4Property | null;         // best-guess GA4 match (user can change it)
};

/** Merge the two existing discoveries into friendly per-domain cards. GA4 is matched by name similarity
 *  (Admin API does not return the website URL) — the guess is editable in the UI. */
export function mergeDiscovery(gsc: { property: string; permission?: string | null }[], ga4: Ga4Property[]): DiscoveredSite[] {
  const byDomain = new Map<string, { property: string; permission: string | null }[]>();
  for (const p of gsc ?? []) {
    const d = friendlyDomain(p.property);
    if (!d) continue;
    byDomain.set(d, [...(byDomain.get(d) ?? []), { property: p.property, permission: p.permission ?? null }]);
  }
  const score = (p: { property: string; permission: string | null }) =>
    (p.property.startsWith('sc-domain:') ? 2 : 0) + (p.permission === 'siteOwner' ? 1 : 0);
  const out: DiscoveredSite[] = [];
  for (const [domain, props] of byDomain) {
    const best = [...props].sort((a, b) => score(b) - score(a))[0];
    const core = norm(domain.split('.')[0]);
    const match = (ga4 ?? []).find((g) => {
      const n = norm(g.display_name ?? '');
      return core.length >= 4 && n.length >= 4 && (n.includes(core) || core.includes(n));
    }) ?? null;
    out.push({ domain, gsc_property: best.property, gsc_permission: best.permission,
               verified: best.permission !== 'siteUnverifiedUser', ga4: match });
  }
  // verified domains first, then alphabetical — the list reads like "your websites"
  return out.sort((a, b) => Number(b.verified) - Number(a.verified) || a.domain.localeCompare(b.domain));
}

export const SYNC_BADGE_FA: Record<string, string> = {
  never: 'در انتظار', queued: 'در صف', running: 'در حال دریافت', succeeded: 'انجام شد',
  completed_with_errors: 'با خطا', failed: 'ناموفق', not_authorized: 'بدون مجوز', not_available: '—'
};
