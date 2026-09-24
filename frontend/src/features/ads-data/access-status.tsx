'use client';
import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
export type AccessDecision = { ip: string; status: 'blocked' | 'pending' | 'unknown'; received: number; match_gclids: string[]; decision_id: number; origins: { name: string; acknowledged: boolean }[] };
export type AccessStatus = { site: string; enabled: boolean; healthy: boolean; generated_at: number; items: AccessDecision[]; errors: string[] };
export function useAccessStatus(site: string) {
  const [status, setStatus] = useState<AccessStatus | null>(null);
  useEffect(() => {
    let stopped = false;
    async function load() {
      try {
        const res = await fetch(`/api/ads-data/access-status?site_id=${encodeURIComponent(site)}`, { cache: 'no-store', signal: AbortSignal.timeout(4000) });
        if (!res.ok) throw new Error('unavailable');
        const data = await res.json() as AccessStatus;
        if (!stopped) setStatus(data.site === site && Math.abs(Date.now()/1000-data.generated_at) < 30 ? data : null);
      } catch { if (!stopped) setStatus(null); }
    }
    void load(); const timer = setInterval(() => void load(), 5000);
    return () => { stopped = true; clearInterval(timer); };
  }, [site]);
  return status;
}
export function matchAccess(status: AccessStatus | null, ip: string, gclid?: string | null, trustedIp = false) {
  if (!status || Math.abs(Date.now()/1000-status.generated_at) >= 30) return null;
  const exact = status.items.find(item => item.ip === ip);
  if (exact && trustedIp) return exact;
  const matches = gclid ? status.items.filter(item => item.match_gclids.includes(gclid)) : [];
  return matches.length === 1 ? matches[0] : null;
}
export function AccessBadge({ status, ip, gclid, legacyBlocked = false, automaticPluginBlocked = false, trustedIp = false }: { status: AccessStatus | null; ip: string; gclid?: string | null; legacyBlocked?: boolean; automaticPluginBlocked?: boolean; trustedIp?: boolean }) {
  const item = matchAccess(status, ip, gclid, trustedIp);
  if (item) {
    const confirmed = item.status === 'blocked';
    return <Badge variant={confirmed ? 'destructive' : 'outline'} className='text-[10px]' title={`IP سایت: ${item.ip} — ${item.origins.map(o => `${o.name}: ${o.acknowledged ? 'ثبت شده' : 'در انتظار'}`).join('، ')}. اعمال روی هاست ممکن است چند ثانیه تأخیر داشته باشد.`}>
      {confirmed ? 'مسدود شده · دائمی' : item.status === 'pending' ? 'در انتظار اعمال بلاک' : 'وضعیت بلاک نیازمند بررسی'}{item.ip !== ip ? ` · IP سایت: ${item.ip}` : ''}
    </Badge>;
  }
  if (automaticPluginBlocked) return <Badge variant='destructive' className='text-[10px]' title='این IP به‌صورت خودکار به‌دلیل عبور از آستانهٔ ورود یا تماس Ads در افزونهٔ سایت مسدود شده است.'>مسدود خودکار · دائمی</Badge>;
  if (legacyBlocked) return <Badge variant='destructive' className='text-[10px]' title='در فهرست افزونهٔ مسدودسازی سایت ثبت شده؛ تأیید بلاک هر دو هاست توسط قانون خودکار نیست.'>مسدود در افزونهٔ سایت</Badge>;
  return <Badge variant='outline' className='text-muted-foreground text-[10px]'>{status ? 'بلاک خودکار ثبت نشده' : 'وضعیت بلاک در دسترس نیست'}</Badge>;
}
export function AccessOverview({ status, automaticPluginIps = new Set<string>() }: { status: AccessStatus | null; automaticPluginIps?: Set<string> }) {
  const count = status ? new Set([...status.items.filter(i => i.status === 'blocked').map(i => i.ip), ...automaticPluginIps]).size : automaticPluginIps.size;
  return <Badge variant='outline'>{!status ? 'وضعیت مسدودسازی نامشخص' : !status.enabled ? 'قانون خودکار خاموش' : !status.healthy ? 'قانون فعال؛ ارتباط نیازمند بررسی' : `قانون خودکار فعال · ${count.toLocaleString('fa-IR')} IP مسدود`}</Badge>;
}
