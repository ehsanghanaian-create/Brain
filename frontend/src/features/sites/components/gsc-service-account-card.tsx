'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ApiError, endpoints, type SaGscStatus } from '@/lib/api/client';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { checkResultView, saCardView } from '../gsc-sa';
import { IntegrationCard } from './integration-card';

/**
 * اتصال سریع Search Console با Service Account — بدون OAuth، بدون تأیید گوگل، بدون انقضای ۷روزه.
 * کاربر فقط یک ایمیل را در Search Console سایتش اضافه می‌کند؛ «بررسی دسترسی» سایت‌های قابل‌خواندن را نشان می‌دهد.
 * هیچ JSON/کلیدی هرگز در UI ظاهر نمی‌شود — فقط ایمیل عمومی Service Account.
 */
export function GoogleSearchConsoleConnectionCard({ onSelect, onChecked }: { onSelect?: (property: string, domain: string) => void; onChecked?: () => void }) {
  const [status, setStatus] = useState<SaGscStatus | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { void endpoints.saGscStatus().then(setStatus).catch(() => null); }, []);

  const view = saCardView(status);

  async function copyEmail() {
    if (!view.email) return;
    try {
      await navigator.clipboard.writeText(view.email);
      toast.success('ایمیل کپی شد — آن را در Search Console → Settings → Users اضافه کنید');
    } catch {
      toast.error('کپی خودکار ممکن نشد؛ ایمیل را دستی انتخاب و کپی کنید');
    }
  }

  async function check() {
    setBusy(true);
    try {
      const r = await endpoints.saGscCheck();
      const v = checkResultView(r);
      (v.ok ? toast.success : toast.error)(v.text);
      setStatus(await endpoints.saGscStatus());
      onChecked?.();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (view.state === 'not_configured') return null;      // نصب بدون SA: فقط مسیر OAuth نمایش داده می‌شود

  return (
    <IntegrationCard
      kind='gsc-sa'
      title='اتصال سریع Search Console'
      badge={view.properties.length > 0 ? `${view.properties.length.toLocaleString('fa-IR')} سایت متصل` : 'پیشنهادی'}
      badgeVariant={view.properties.length > 0 ? 'secondary' : 'default'}
      description='ایمیل زیر را در Search Console سایت خود اضافه کنید تا Brain بتواند آمار جستجو را فقط بخواند — بدون ورود به حساب گوگل.'
    >
      <div className='flex flex-wrap items-center gap-2 rounded-md border p-2'>
        <code className='flex-1 select-all break-all text-xs' dir='ltr' data-testid='sa-email'>{view.email}</code>
        <Button type='button' size='sm' variant='outline' onClick={() => void copyEmail()} data-testid='sa-copy'>کپی ایمیل</Button>
      </div>
      <p className='text-muted-foreground text-xs'>
        ‏Search Console → انتخاب سایت → ‏Settings ‏(تنظیمات) → ‏Users and permissions → ‏Add user → این ایمیل با سطح Full.
      </p>
      <div className='flex flex-wrap items-center gap-2'>
        <Button type='button' size='sm' disabled={busy} onClick={() => void check()} data-testid='sa-check'>
          {busy ? 'در حال بررسی…' : 'بررسی دسترسی'}
        </Button>
        {view.lastCheck && <span className='text-muted-foreground text-xs' dir='ltr'>آخرین بررسی: {new Date(view.lastCheck).toLocaleString('fa-IR')}</span>}
      </div>

      {view.properties.length > 0 && (
        <ul className='grid gap-2' data-testid='sa-properties'>
          {view.properties.map((p) => (
            <li key={p.property} className='flex flex-wrap items-center justify-between gap-2 rounded-md border p-2'>
              <div className='text-sm'>
                <div className='font-medium' dir='ltr'>🌐 {p.domain}</div>
                <div className='text-xs text-emerald-600'>✓ دسترسی Search Console فعال است</div>
              </div>
              {onSelect && (
                <Button type='button' size='sm' variant='outline' onClick={() => onSelect(p.property, p.domain)} data-testid={`sa-pick-${p.domain}`}>
                  انتخاب سایت
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {view.emptyHint && (
        <p className='rounded-md border border-dashed p-2 text-xs' data-testid='sa-empty-hint'>⚠️ {view.emptyHint}</p>
      )}
      <Badge variant='outline' className='w-fit text-[10px]'>فقط‌خواندنی — Brain هیچ‌چیزی را تغییر نمی‌دهد</Badge>
    </IntegrationCard>
  );
}
