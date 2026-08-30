'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { endpoints } from '@/lib/api/client';
import { IconLock, IconRefresh, IconShieldCheck, IconShieldX } from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

type BlockedItem = { ip: string; reason: string | null; blocked_at: string | null; status: string };

const fa = new Intl.NumberFormat('fa-IR');

/** امنیت سایت — وضعیت اتصال پلاگین مسدودسازی + مدیریت IPهای مسدود. همهٔ عملیات با کلیک انسانی و از مسیر Backend خود Brain. */
export function SecurityCard({ siteId }: { siteId: string }) {
  const [status, setStatus] = useState<{ connected: boolean; count?: number; message?: string; writable?: boolean } | null>(null);
  const [items, setItems] = useState<BlockedItem[] | null>(null);
  const [showList, setShowList] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmUnblock, setConfirmUnblock] = useState<string | null>(null);

  const load = useCallback(async (withList = false) => {
    setBusy('status');
    try {
      const st = await endpoints.securityStatus(siteId);
      setStatus(st);
      if (withList && st.connected) setItems((await endpoints.securityBlocked(siteId)).items);
    } catch {
      setStatus({ connected: false, message: 'اتصال به سرویس برقرار نشد' });
    } finally {
      setBusy(null);
    }
  }, [siteId]);

  useEffect(() => { void load(); }, [load]);

  async function unblock(ip: string) {
    setBusy(ip);
    try {
      const r = await endpoints.securityUnblock(siteId, ip);
      if (r.success) {
        toast.success(r.status === 'already_unblocked' ? 'این IP مسدود نبود.' : '✓ مسدودی IP برداشته شد.');
        await load(true);
      } else {
        toast.error(r.message || '✕ برداشتن مسدودی انجام نشد.');
      }
    } catch {
      toast.error('✕ برداشتن مسدودی انجام نشد.');
    } finally {
      setBusy(null);
      setConfirmUnblock(null);
    }
  }

  return (
    <Card data-testid='security-card'>
      <CardHeader>
        <CardTitle className='flex items-center gap-2'><IconLock className='size-5' />امنیت سایت</CardTitle>
        <CardDescription>مسدودسازی IP از طریق پلاگین امنیتی خود سایت — هیچ عملی بدون کلیک شما انجام نمی‌شود</CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='flex flex-wrap items-center gap-2 text-sm'>
          <span>وضعیت اتصال پلاگین:</span>
          {status === null ? (
            <Badge variant='outline'>در حال بررسی…</Badge>
          ) : status.connected ? (
            <Badge className='border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'><IconShieldCheck className='me-1 size-3.5' />متصل</Badge>
          ) : (
            <Badge variant='destructive'><IconShieldX className='me-1 size-3.5' />متصل نیست</Badge>
          )}
          <Button size='sm' variant='ghost' onClick={() => void load(showList)} disabled={busy === 'status'}>
            <IconRefresh className={busy === 'status' ? 'animate-spin' : ''} />
          </Button>
        </div>
        {status && !status.connected && status.message && (
          <p className='text-muted-foreground text-xs'>{status.message}</p>
        )}
        {status?.connected && status.writable === false && (
          <p className='text-destructive text-xs'>هشدار: فایل تنظیمات سایت قابل نوشتن نیست؛ مسدودسازی اعمال نخواهد شد.</p>
        )}
        {status?.connected && (
          <>
            <div className='text-sm'>IPهای مسدود شده: <b>{fa.format(status.count ?? 0)}</b></div>
            <Button size='sm' variant='outline' onClick={async () => { const next = !showList; setShowList(next); if (next) await load(true); }}>
              {showList ? 'بستن لیست' : 'مشاهده IPهای مسدود شده'}
            </Button>
            {showList && items && (
              items.length === 0 ? <p className='text-muted-foreground text-xs'>هیچ IP مسدودی وجود ندارد.</p> : (
                <ul className='space-y-1.5 text-sm'>
                  {items.map((it) => (
                    <li key={it.ip} className='flex flex-wrap items-center gap-2 rounded-md border p-2'>
                      <code dir='ltr'>{it.ip}</code>
                      <Badge variant='secondary'>مسدود شده</Badge>
                      {it.reason && <span className='text-muted-foreground text-xs'>{it.reason}</span>}
                      {it.blocked_at && <span className='text-muted-foreground text-xs' dir='ltr'>{it.blocked_at.slice(0, 16).replace('T', ' ')}</span>}
                      {confirmUnblock === it.ip ? (
                        <span className='ms-auto flex items-center gap-1'>
                          <span className='text-xs'>مسدودی برداشته شود؟</span>
                          <Button size='sm' variant='destructive' disabled={busy === it.ip} onClick={() => void unblock(it.ip)}>بله</Button>
                          <Button size='sm' variant='ghost' onClick={() => setConfirmUnblock(null)}>انصراف</Button>
                        </span>
                      ) : (
                        <Button size='sm' variant='outline' className='ms-auto' onClick={() => setConfirmUnblock(it.ip)}>رفع مسدودی</Button>
                      )}
                    </li>
                  ))}
                </ul>
              )
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
