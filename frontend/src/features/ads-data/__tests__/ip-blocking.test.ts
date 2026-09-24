import { describe, expect, it, vi } from 'vitest';
import { createIpBlockController } from '../ip-blocking';

function setup() {
  const api = {
    securityResolveSite: vi.fn(async () => ({ configured: true, site_id: 'site-123' })),
    securityBlocked: vi.fn(async () => ({ connected: true, items: [{ ip: '192.0.2.1' }] })),
    securityBlock: vi.fn(async () => ({ success: true })),
    securityUnblock: vi.fn(async () => ({ success: true }))
  };
  return { api, controller: createIpBlockController('example.com', api) };
}

describe('shared site IP blocking', () => {
  it('loads authoritative status and toggles the resolved site in both directions', async () => {
    const { api, controller } = setup();
    await controller.load();
    expect(api.securityResolveSite).toHaveBeenCalledWith('example.com');
    expect(controller.getSnapshot().blockedIps.has('192.0.2.1')).toBe(true);
    await controller.toggle('192.0.2.1');
    expect(api.securityUnblock).toHaveBeenCalledWith('site-123', '192.0.2.1');
    expect(controller.getSnapshot().blockedIps.has('192.0.2.1')).toBe(false);
    await controller.toggle('192.0.2.1');
    expect(api.securityBlock).toHaveBeenCalledWith('site-123', '192.0.2.1', expect.any(String));
    expect(controller.getSnapshot().blockedIps.has('192.0.2.1')).toBe(true);
  });

  it('prevents duplicate row clicks and waits for server success', async () => {
    const { api, controller } = setup();
    await controller.load();
    let finish!: (value: { success: boolean }) => void;
    api.securityBlock.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const pending = controller.toggle('192.0.2.2');
    expect(controller.getSnapshot().pendingIps.has('192.0.2.2')).toBe(true);
    expect(controller.getSnapshot().blockedIps.has('192.0.2.2')).toBe(false);
    expect(await controller.toggle('192.0.2.2')).toBeNull();
    expect(api.securityBlock).toHaveBeenCalledTimes(1);
    finish({ success: true });
    await pending;
    expect(controller.getSnapshot().blockedIps.has('192.0.2.2')).toBe(true);
    expect(controller.getSnapshot().pendingIps.size).toBe(0);
  });

  it('does not show a successful unblock when the server rejects it', async () => {
    const { api, controller } = setup();
    await controller.load();
    api.securityUnblock.mockResolvedValue({ success: false });
    expect((await controller.toggle('192.0.2.1'))?.success).toBe(false);
    expect(controller.getSnapshot().blockedIps.has('192.0.2.1')).toBe(true);
  });

  it('requires status reconciliation after a lost mutation response', async () => {
    const { api, controller } = setup();
    await controller.load();
    api.securityBlock.mockRejectedValue(new Error('timeout'));
    await controller.toggle('192.0.2.2');
    expect(controller.getSnapshot().status).toBe('error');
    expect(await controller.toggle('192.0.2.2')).toBeNull();
    api.securityBlocked.mockResolvedValue({ connected: true, items: [{ ip: '192.0.2.2' }] });
    await controller.load();
    expect(controller.getSnapshot().status).toBe('ready');
    expect(controller.getSnapshot().blockedIps.has('192.0.2.2')).toBe(true);
  });

  it('refreshes blocks made outside this dashboard without clearing a pending mutation', async () => {
    const { api, controller } = setup();
    await controller.load();
    api.securityBlocked.mockResolvedValue({ connected: true, items: [{ ip: '192.0.2.2' }] });
    await controller.refresh();
    expect(controller.getSnapshot().blockedIps.has('192.0.2.2')).toBe(true);
    let finish!: (value: { success: boolean }) => void;
    api.securityBlock.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const pending = controller.toggle('192.0.2.3');
    await controller.refresh();
    expect(api.securityBlocked).toHaveBeenCalledTimes(2);
    finish({ success: true });
    await pending;
    expect(controller.getSnapshot().blockedIps.has('192.0.2.3')).toBe(true);
  });

  it('disables mutations before loading and on disconnected sites', async () => {
    const { api, controller } = setup();
    expect(await controller.toggle('192.0.2.2')).toBeNull();
    api.securityBlocked.mockResolvedValue({ connected: false, items: [] });
    await controller.load();
    expect(controller.getSnapshot().status).toBe('error');
    expect(await controller.toggle('192.0.2.2')).toBeNull();
    expect(api.securityBlock).not.toHaveBeenCalled();
  });

  it('ignores mutation responses after leaving the site', async () => {
    const { api, controller } = setup();
    await controller.load();
    let finish!: (value: { success: boolean }) => void;
    api.securityBlock.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const pending = controller.toggle('192.0.2.2');
    controller.dispose();
    finish({ success: true });
    expect(await pending).toBeNull();
    expect(controller.getSnapshot().blockedIps.has('192.0.2.2')).toBe(false);
  });
});
