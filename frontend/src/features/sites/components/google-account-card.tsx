'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ApiError, endpoints, type GoogleAccountStatus } from '@/lib/api/client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { googleAccountView } from '../google-account';
import { IntegrationCard } from './integration-card';

/**
 * Google Account card — the web replacement for `sync-gsc.py --auth-only`.
 * «اتصال حساب گوگل» opens Google's consent in a new tab (web OAuth flow); the card polls status until the
 * callback stores the token, then GSC/GA4 property discovery works immediately. Token stays server-side.
 */
export function GoogleAccountCard({ onChange }: { onChange?: () => void }) {
  const [status, setStatus] = useState<GoogleAccountStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [awaiting, setAwaiting] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const s = await endpoints.googleStatus();
      setStatus((prev) => {
        if (prev && !prev.connected && s.connected) {
          toast.success(`حساب گوگل متصل شد${s.email ? ` — ${s.email}` : ''}`);
          setAwaiting(false);
          onChange?.();
        }
        return s;
      });
      return s;
    } catch {
      return null;
    }
  }, [onChange]);

  useEffect(() => { void load(); }, [load]);

  // while the consent tab is open, poll until the callback lands
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (awaiting && !status?.connected) timer.current = setTimeout(() => { void load(); }, 3000);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [awaiting, status, load]);

  const view = googleAccountView(status, { busy });

  async function connect() {
    setBusy(true);
    try {
      const r = await endpoints.googleAuthorize();
      window.open(r.url, '_blank', 'noopener');
      setAwaiting(true);
      toast.info('در پنجرهٔ بازشده با حساب گوگل خود وارد شوید و هر دو دسترسی را تأیید کنید');
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!window.confirm('اتصال حساب گوگل قطع شود؟ همگام‌سازی GSC و GA4 تا اتصال مجدد کار نخواهند کرد.')) return;
    setBusy(true);
    try {
      await endpoints.googleDisconnect();
      toast.success('اتصال حساب گوگل قطع شد');
      await load();
      onChange?.();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <IntegrationCard
      kind='google-account'
      title='حساب گوگل'
      badge={view.state === 'connected' ? 'متصل' : view.state === 'no_client' ? 'پیکربندی ناقص' : 'متصل نیست'}
      badgeVariant={view.state === 'connected' ? 'secondary' : view.state === 'no_client' ? 'destructive' : 'outline'}
      description='یک ورود گوگل برای Search Console و Google Analytics — هر دو فقط‌خواندنی. توکن فقط روی همین سیستم و خارج از دیتابیس نگه‌داری می‌شود.'
    >
      {view.state === 'connected' ? (
        <div className='grid gap-2 text-sm' data-testid='google-connected'>
          <div className='flex flex-wrap items-center gap-2'>
            <span className='text-muted-foreground'>حساب:</span>
            <Badge variant='outline' dir='ltr'>{view.email ?? 'ایمیل نامشخص (اتصال قدیمی از CLI)'}</Badge>
            {status?.expiry && <span className='text-muted-foreground text-xs' dir='ltr'>expiry: {status.expiry}</span>}
          </div>
          <div className='flex flex-wrap items-center gap-2 text-xs'>
            <span className='text-muted-foreground'>دسترسی‌ها:</span>
            {view.permissions.map((p) => (
              <Badge key={p.key} variant={p.granted ? 'secondary' : 'destructive'}>{p.fa}{p.granted ? ' ✓' : ' ✗'}</Badge>
            ))}
          </div>
          <div className='flex flex-wrap gap-2'>
            <Button type='button' size='sm' variant='outline' disabled={busy} onClick={() => void connect()}>اتصال دوباره</Button>
            <Button type='button' size='sm' variant='destructive' disabled={!view.canDisconnect} onClick={() => void disconnect()} data-testid='google-disconnect'>قطع اتصال</Button>
          </div>
        </div>
      ) : (
        <div className='grid gap-2' data-testid='google-disconnected'>
          <Button type='button' size='sm' className='w-fit' disabled={!view.canConnect} onClick={() => void connect()} data-testid='google-connect'>
            {awaiting ? 'در انتظار تأیید در گوگل…' : 'اتصال حساب گوگل'}
          </Button>
          {awaiting && <Button type='button' size='sm' variant='ghost' className='w-fit' onClick={() => void load()}>بررسی وضعیت</Button>}
        </div>
      )}
      {view.hint && <p className='text-muted-foreground text-xs'>{view.hint}</p>}
    </IntegrationCard>
  );
}
