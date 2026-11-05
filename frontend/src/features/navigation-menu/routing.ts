const siteScopedPaths = new Set([
  '/dashboard/graph',
  '/dashboard/keywords',
  '/dashboard/research',
  '/dashboard/rank-tracking',
  '/dashboard/sales',
  '/dashboard/calendar',
  '/dashboard/content-planner',
  '/dashboard/content',
  '/dashboard/internal-linking',
  '/dashboard/opportunities',
  '/dashboard/problems',
  '/dashboard/ai-visibility',
  '/dashboard/ai-content-test',
  '/dashboard/ai-studio',
  '/dashboard/ai-models',
  '/dashboard/reports',
  '/dashboard/traffic'
]);

export function navigationHref(href: string, siteId?: string): string {
  const url = new URL(href, 'https://seo-brain.invalid');
  if (siteId && siteScopedPaths.has(url.pathname)) url.searchParams.set('site', siteId);
  return `${url.pathname}${url.search}${url.hash}`;
}

export function siteFromLocation(pathname: string, querySite: string | null): string {
  const match = pathname.match(/^\/dashboard\/sites\/([^/]+)(?:\/|$)/);
  return match && match[1] !== 'new' ? decodeURIComponent(match[1]) : (querySite ?? '');
}
