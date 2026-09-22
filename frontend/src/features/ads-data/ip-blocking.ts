type BlockResult = { success: boolean; status?: string; message?: string };
type SecurityApi = {
  securityResolveSite: (domain: string) => Promise<{ configured: boolean; site_id: string | null }>;
  securityBlocked: (siteId: string) => Promise<{ connected: boolean; message?: string; items: { ip: string }[] }>;
  securityBlock: (siteId: string, ip: string, reason?: string) => Promise<BlockResult>;
  securityUnblock: (siteId: string, ip: string) => Promise<BlockResult>;
};

/** One authoritative IP state for every row and drawer in the selected site. */
export function createIpBlockController(domain: string, api: SecurityApi) {
  let generation = 0;
  let state = {
    siteId: null as string | null,
    status: 'loading' as 'loading' | 'ready' | 'unavailable' | 'error',
    message: '',
    blockedIps: new Set<string>(),
    pendingIps: new Set<string>()
  };
  const listeners = new Set<() => void>();
  function update(next: Partial<typeof state>) {
    state = { ...state, ...next };
    listeners.forEach((listener) => listener());
  }
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    dispose() { generation++; },
    async load() {
      const request = ++generation;
      update({ status: 'loading', siteId: null, message: '', blockedIps: new Set(), pendingIps: new Set() });
      try {
        const resolved = await api.securityResolveSite(domain);
        if (request !== generation) return;
        if (!resolved.configured || !resolved.site_id) {
          update({ status: 'unavailable', message: 'اتصال مسدودسازی این سایت تنظیم نشده است.' });
          return;
        }
        const result = await api.securityBlocked(resolved.site_id);
        if (request !== generation) return;
        if (!result.connected) throw new Error(result.message || 'ارتباط با افزونه امنیتی برقرار نیست.');
        update({ siteId: resolved.site_id, status: 'ready', blockedIps: new Set(result.items.map((item) => item.ip)) });
      } catch {
        if (request === generation) update({ status: 'error', message: 'وضعیت بلاک IP دریافت نشد؛ دوباره تلاش کنید.' });
      }
    },
    async toggle(ip: string): Promise<BlockResult | null> {
      if (!ip || state.status !== 'ready' || !state.siteId || state.pendingIps.has(ip)) return null;
      const request = generation;
      const blocked = state.blockedIps.has(ip);
      const siteId = state.siteId;
      update({ pendingIps: new Set([...state.pendingIps, ip]) });
      try {
        const result = blocked
          ? await api.securityUnblock(siteId, ip)
          : await api.securityBlock(siteId, ip, 'ترافیک مشکوک — بررسی دستی در Ads Data');
        if (request !== generation) return null;
        if (result.success) {
          const blockedIps = new Set(state.blockedIps);
          if (blocked) blockedIps.delete(ip); else blockedIps.add(ip);
          update({ blockedIps });
        }
        return { ...result, message: result.message || (result.success
          ? blocked ? 'مسدودی IP برداشته شد.' : 'IP در این سایت مسدود شد.'
          : 'تغییر وضعیت بلاک انجام نشد.') };
      } catch {
        if (request !== generation) return null;
        const message = 'پاسخ تغییر وضعیت دریافت نشد؛ پیش از تلاش دوباره وضعیت را تازه کنید.';
        update({ status: 'error', message });
        return { success: false, message };
      } finally {
        if (request === generation) {
          const pendingIps = new Set(state.pendingIps);
          pendingIps.delete(ip);
          update({ pendingIps });
        }
      }
    }
  };
}
