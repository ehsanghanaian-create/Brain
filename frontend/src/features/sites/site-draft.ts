/** Non-sensitive handoff from the navigation's quick-add form to the site wizard. */
export type SiteDraft = { name: string; domain: string };

export function parseSiteDraft(input: { name?: unknown; domain?: unknown }): SiteDraft {
  const name = typeof input.name === 'string' ? input.name.trim().slice(0, 80) : '';
  const value = typeof input.domain === 'string' ? input.domain.trim() : '';
  try {
    const url = new URL(value.includes('://') ? value : `https://${value}`);
    if (
      !['http:', 'https:'].includes(url.protocol) ||
      url.username ||
      url.password ||
      !url.hostname.includes('.')
    )
      return { name, domain: '' };
    // Only carry the site origin; never copy query strings, credentials or paths.
    return { name, domain: url.origin };
  } catch {
    return { name, domain: '' };
  }
}

export function siteDraftHref(input: SiteDraft): string {
  const draft = parseSiteDraft(input);
  return `/dashboard/sites/new?${new URLSearchParams(draft).toString()}`;
}
