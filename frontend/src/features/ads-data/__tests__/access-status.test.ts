import { describe, expect, it, vi } from 'vitest';
import { accessStatusResponse } from '../access-status-response';

const now = 1793800000;
const snapshot = { site: 'salimore', enabled: true, healthy: true, generated_at: now, items: [], errors: [] };

describe('access status configuration and evidence', () => {
  it('reports an explicitly unconfigured site without claiming successful enforcement', async () => {
    const read = vi.fn();
    const result = await accessStatusResponse('salimore', { enabled: 'false', site: 'salimore', now, read });
    expect(result.status).toBe(200);
    expect(result.data).toMatchObject({ configured: false, enabled: false, healthy: false, state: 'not_configured', items: [] });
    expect(read).not.toHaveBeenCalled();
  });

  it('keeps another business and missing site parameters outside the configured scope', async () => {
    expect((await accessStatusResponse('gearboxemdad', { enabled: 'false', site: 'salimore' })).status).toBe(404);
    expect((await accessStatusResponse(null, { enabled: 'false', site: 'salimore' })).status).toBe(400);
    expect((await accessStatusResponse('../salimore')).status).toBe(400);
    expect((await accessStatusResponse('salimore', { enabled: 'false' })).status).toBe(503);
  });

  it('retains file-backed installations without requiring new environment settings', async () => {
    const result = await accessStatusResponse('salimore', { now, read: async () => JSON.stringify(snapshot) });
    expect(result.status).toBe(200);
    expect(result.data).toMatchObject({ configured: true, healthy: true, source: 'enforcement_snapshot' });
  });

  it('reports an outage when a configured feed is missing, malformed or stale', async () => {
    for (const read of [
      async () => { throw new Error('ENOENT'); },
      async () => 'invalid JSON',
      async () => JSON.stringify({ ...snapshot, generated_at: now - 30 }),
      async () => JSON.stringify({ ...snapshot, generated_at: now + 31 }),
      async () => JSON.stringify({ ...snapshot, healthy: 'yes' })
    ]) {
      expect((await accessStatusResponse('salimore', { enabled: 'true', now, read })).status).toBe(503);
    }
  });

  it('never returns a different site snapshot as the requested site', async () => {
    const result = await accessStatusResponse('another-site', { now, read: async () => JSON.stringify(snapshot) });
    expect(result.status).toBe(404);
    expect(result.data).not.toHaveProperty('items');
  });
});
