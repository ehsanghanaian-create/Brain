import { readFile } from 'node:fs/promises';

type Options = {
  enabled?: string;
  site?: string;
  now?: number;
  read?: () => Promise<string>;
};

/** A disabled capability is configuration; a broken configured feed is an outage. */
export async function accessStatusResponse(site: string | null, options: Options = {}) {
  if (!site || !/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,252}$/.test(site)) {
    return { status: 400, data: { error: 'site_id_required' } };
  }
  if (options.site && site !== options.site) {
    return { status: 404, data: { error: 'access_status_site_not_configured' } };
  }
  if (options.enabled === 'false') {
    if (!options.site) return { status: 503, data: { error: 'access_status_configuration_invalid' } };
    return { status: 200, data: {
      site, configured: false, enabled: false, healthy: false,
      state: 'not_configured', source: 'deployment_configuration',
      generated_at: options.now ?? Date.now() / 1000, items: [], errors: []
    } };
  }
  try {
    const data = JSON.parse(await (options.read ?? (() => readFile('/app/access-status/status.json', 'utf8')))());
    if (data.site !== site) return { status: 404, data: { error: 'access_status_site_not_configured' } };
    const now = options.now ?? Date.now() / 1000;
    if (!Array.isArray(data.items) || typeof data.enabled !== 'boolean' || typeof data.healthy !== 'boolean'
      || typeof data.generated_at !== 'number' || !Number.isFinite(data.generated_at)
      || Math.abs(now - data.generated_at) >= 30) {
      throw new Error('invalid_or_stale_snapshot');
    }
    return { status: 200, data: { ...data, configured: true, source: 'enforcement_snapshot' } };
  } catch {
    return { status: 503, data: { error: 'access_status_unavailable' } };
  }
}
