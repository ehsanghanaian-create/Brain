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
  return (
    domain
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 63) || 'site'
  );
}

export type ExistingSiteLike = {
  site_id: string;
  canonical_url: string;
  wp_url?: string | null;
  gsc_property?: string | null;
  created_at?: string | null;
};

/** Resolve by the real domain instead of a generated slug. This prevents onboarding from creating a second site
 *  when an older/imported record uses a different site_id (for example emdadmodiran vs emdadmodiran-com). */
export function findExistingSiteByDomain<T extends ExistingSiteLike>(
  sites: T[],
  domain: string
): T | null {
  const wanted = friendlyDomain(domain);
  const matches = (sites ?? []).filter((site) =>
    [site.canonical_url, site.wp_url, site.gsc_property].some(
      (value) => friendlyDomain(value) === wanted
    )
  );
  return (
    matches.toSorted((a, b) => {
      const at = a.created_at ? Date.parse(a.created_at) : Number.POSITIVE_INFINITY;
      const bt = b.created_at ? Date.parse(b.created_at) : Number.POSITIVE_INFINITY;
      return at - bt || a.site_id.localeCompare(b.site_id);
    })[0] ?? null
  );
}

export function normalizeWebsiteUrl(value: string): string | null {
  const raw = value.trim();
  if (!raw) return null;
  try {
    const parsed = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname.includes('.'))
      return null;
    return `${parsed.protocol}//${parsed.host}`;
  } catch {
    return null;
  }
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9؀-ۿ]+/g, '');
const propertyScore = (property: { property: string; permission: string | null }) =>
  (property.property.startsWith('sc-domain:') ? 2 : 0) +
  (['siteOwner', 'siteFullUser'].includes(property.permission ?? '') ? 1 : 0);

export type DiscoveredSite = {
  domain: string;
  gsc_property: string; // best GSC property for the domain (sc-domain preferred, owner preferred)
  gsc_permission: string | null;
  verified: boolean; // user has real access (not siteUnverifiedUser)
  ga4: Ga4Property | null; // best-guess GA4 match (user can change it)
};

/** Merge the two existing discoveries into friendly per-domain cards. GA4 is matched by name similarity
 *  (Admin API does not return the website URL) — the guess is editable in the UI. */
export function mergeDiscovery(
  gsc: { property: string; permission?: string | null }[],
  ga4: Ga4Property[]
): DiscoveredSite[] {
  const byDomain = new Map<string, { property: string; permission: string | null }[]>();
  for (const p of gsc ?? []) {
    const d = friendlyDomain(p.property);
    if (!d) continue;
    byDomain.set(d, [
      ...(byDomain.get(d) ?? []),
      { property: p.property, permission: p.permission ?? null }
    ]);
  }
  const out: DiscoveredSite[] = [];
  for (const [domain, props] of byDomain) {
    const best = props.toSorted((a, b) => propertyScore(b) - propertyScore(a))[0];
    const core = norm(domain.split('.')[0]);
    // 1) exact domain from the GA4 web stream URL (Admin API) — 2) name-similarity fallback
    const match =
      (ga4 ?? []).find((g) => friendlyDomain(g.website_url) === domain) ??
      (ga4 ?? []).find((g) => {
        const n = norm(g.display_name ?? '');
        return core.length >= 4 && n.length >= 4 && (n.includes(core) || core.includes(n));
      }) ??
      null;
    out.push({
      domain,
      gsc_property: best.property,
      gsc_permission: best.permission,
      verified: best.permission !== 'siteUnverifiedUser',
      ga4: match
    });
  }
  // verified domains first, then alphabetical — the list reads like "your websites"
  return out.toSorted(
    (a, b) => Number(b.verified) - Number(a.verified) || a.domain.localeCompare(b.domain)
  );
}

export const SYNC_BADGE_FA: Record<string, string> = {
  never: 'در انتظار',
  queued: 'در صف',
  running: 'در حال دریافت',
  succeeded: 'انجام شد',
  completed_with_errors: 'با خطا',
  failed: 'ناموفق',
  not_authorized: 'بدون مجوز',
  not_available: '—'
};
