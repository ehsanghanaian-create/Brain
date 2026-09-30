'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ApiError, endpoints, type GoogleAccountStatus } from '@/lib/api/client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { googleAccountView } from '../google-account';
import { IntegrationCard } from './integration-card';

/**
 * Google Account card — the web replacement for `sync-gsc.py --auth-only`.
 * «اتصال حساب گوگل» opens Google's account chooser in a new tab (web OAuth flow); the card polls status until the
 * callback stores the token, then GSC/GA4 property discovery works immediately. Token stays server-side.
 */
export function GoogleAccountCard({ onChange, simple = false }: { onChange?: () => void; simple?: boolean }) {
  const [status, setStatus] = useState<GoogleAccountStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [awaiting, setAwaiting] = useState(false);
  const deadline = useRef<number>(0);
  const awaitingRef = useRef(false);
  const previousConnection = useRef<string | null>(null);
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [editClient, setEditClient] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const s = await endpoints.googleStatus();
      setStatus(s);
      if (awaitingRef.current && s.connected && s.connected_at !== previousConnection.current) {
        awaitingRef.current = false;
        setAwaiting(false);
        toast.success(`حساب گوگل متصل شد${s.email ? ` — ${s.email}` : ''}`);
        onChange?.();
      }
      return s;
    } catch {
      return null;
    }
  }, [onChange]);

  useEffect(() => { void load(); }, [load]);

  // Allow time for account selection, password entry, and 2FA; match the server's 15-minute OAuth state lifetime.
  useEffect(() => {
    if (!awaiting) return;
    let cancelled = false;
    const check = async () => {
      if (Date.now() > deadline.current) {
        awaitingRef.current = false;
        setAwaiting(false);
        toast.error('زمان تأیید گوگل تمام شد — دوباره «اتصال حساب گوگل» را بزنید');
        return;
      }
      await load();
      if (!cancelled && awaitingRef.current) timer.current = setTimeout(() => { void check(); }, 5000);
    };
    timer.current = setTimeout(() => { void check(); }, 5000);
    return () => { cancelled = true; if (timer.current) clearTimeout(timer.current); };
  }, [awaiting, load]);

  useEffect(() => {
    if (!awaiting || typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel('seo-brain-google-oauth');
    channel.onmessage = (event: MessageEvent<{ result?: string }>) => {
      if (event.data?.result === 'success') void load();
      if (event.data?.result === 'error') {
        awaitingRef.current = false;
        setAwaiting(false);
        toast.error('اتصال گوگل کامل نشد. نتیجه را در پنجرهٔ گوگل ببینید و دوباره تلاش کنید.');
      }
    };
    return () => channel.close();
  }, [awaiting, load]);

  const view = googleAccountView(status, { busy });

  async function connect() {
    const tab = window.open('about:blank', '_blank');
    if (!tab) { toast.error('باز شدن پنجرهٔ Google مسدود شد؛ اجازهٔ Pop-up را برای پنل فعال کنید.'); return; }
    tab.opener = null;
    setBusy(true);
    try {
      const r = await endpoints.googleAuthorize();
      tab.location.replace(r.url);
      deadline.current = Date.now() + 900_000;
      previousConnection.current = status?.connected_at ?? null;
      awaitingRef.current = true;
      setAwaiting(true);
      toast.info('حساب موردنظر را در صفحهٔ رسمی گوگل انتخاب کنید؛ اگر لازم بود همان‌جا وارد شوید و دسترسی‌ها را تأیید کنید');
    } catch (e) {
      tab.close();
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveClient() {
    setBusy(true);
    try {
      const r = await endpoints.googleClientSave(clientId, clientSecret);
      toast.success(`مشخصات کلاینت گوگل ذخیره شد (${r.client_id_hint ?? ''})`);
      setClientId('');
      setClientSecret('');       // never keep the secret in component state
      setEditClient(false);
      await load();
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
      badge={view.state === 'connected' ? 'متصل' : view.state === 'needs_reconnect' ? 'نیازمند اتصال دوباره'
        : view.state === 'temporary_error' ? 'خطای موقت' : view.state === 'no_client' ? 'پیکربندی ناقص' : 'متصل نیست'}
      badgeVariant={view.state === 'connected' ? 'secondary' : ['no_client', 'needs_reconnect'].includes(view.state) ? 'destructive' : 'outline'}
      description='یک ورود گوگل برای دسترسی فقط‌خواندنی به Search Console و Google Analytics. توکن به‌صورت رمزگذاری‌شده روی سرور نگه‌داری می‌شود.'
    >
      {view.state === 'connected' ? (
        <div className='grid gap-2 text-sm' data-testid='google-connected'>
          <div className='flex flex-wrap items-center gap-2'>
            <span className='text-muted-foreground'>حساب:</span>
            <Badge variant='outline' dir='ltr'>{view.email ?? 'ایمیل نامشخص (اتصال قدیمی از CLI)'}</Badge>
            {!simple && status?.expiry && <span className='text-muted-foreground text-xs'>زمان تمدید خودکار توکن: <span dir='ltr'>{status.expiry}</span></span>}
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
          <p className='text-muted-foreground text-xs'>برای تغییر حساب، «اتصال دوباره» را بزنید و حساب دیگری را در گوگل انتخاب کنید.</p>
        </div>
      ) : (
        <div className='grid gap-2' data-testid='google-disconnected'>
          {view.state === 'needs_reconnect' && (
            <div className='rounded-md border border-amber-500 p-3 text-xs'>
              {status?.email && <p>حساب قبلی: {status.email}</p>}
              <p>مجوز ذخیره‌شده دیگر توسط Google پذیرفته نمی‌شود. در پروژهٔ مربوط به Client ID ‏{status?.client_id_hint ?? 'فعلی'}، وضعیت برنامه را بررسی کنید.</p>
              <a className='text-primary underline' href='https://console.cloud.google.com/auth/audience' target='_blank' rel='noreferrer'>باز کردن Google Auth Platform → Audience</a>
            </div>
          )}
          {view.state === 'temporary_error' && <Button type='button' size='sm' variant='outline' className='w-fit' onClick={() => void load()}>بررسی دوبارهٔ اتصال</Button>}
          {view.state === 'no_client' && simple && (
            <p className='text-muted-foreground rounded-md border border-dashed p-3 text-xs'>
              راه‌اندازی اولیهٔ گوگل هنوز توسط مدیر انجام نشده است — از صفحهٔ هر سایت، بخش «حساب گوگل»، یک‌بار انجام می‌شود.
            </p>
          )}
          <div className='flex flex-wrap gap-2'>
            <Button type='button' size='sm' disabled={!view.canConnect || awaiting} onClick={() => void connect()} data-testid='google-connect'>
              {awaiting ? 'در انتظار تأیید در گوگل…' : view.state === 'needs_reconnect' ? 'اتصال دوبارهٔ حساب گوگل' : 'اتصال حساب گوگل'}
            </Button>
            {awaiting && (
              <>
                <Button type='button' size='sm' variant='ghost' onClick={() => void load()}>بررسی وضعیت</Button>
                <Button type='button' size='sm' variant='outline' onClick={() => { awaitingRef.current = false; setAwaiting(false); }} data-testid='google-cancel'>انصراف</Button>
              </>
            )}
          </div>
          <p className='text-muted-foreground text-xs'>حساب را در صفحهٔ رسمی گوگل انتخاب می‌کنید. رمز گوگل فقط همان‌جا وارد می‌شود و به SEO Brain داده نمی‌شود.</p>
        </div>
      )}
      {!simple && view.state !== 'no_client' && (
        <Button type='button' size='sm' variant='ghost' className='w-fit' onClick={() => setEditClient((value) => !value)}>
          {editClient ? 'بستن تنظیمات OAuth Client' : 'تغییر OAuth Client'}
        </Button>
      )}
      {!simple && (view.state === 'no_client' || editClient) && (
        <div className='grid gap-2 rounded-md border border-dashed p-3' data-testid='google-client-form'>
          <p className='text-xs font-medium'>Google Auth Platform → Clients → Create client → نوع «Web application». نشانی بازگشت زیر را دقیقاً در Authorized redirect URIs ثبت کنید.</p>
          {status?.redirect_uri && <code className='break-all text-xs' dir='ltr'>{status.redirect_uri}</code>}
          <Input value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder='Client ID (…apps.googleusercontent.com)' dir='ltr' autoComplete='off' />
          <Input type='password' value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} placeholder='Client Secret' dir='ltr' autoComplete='new-password' />
          <Button type='button' size='sm' className='w-fit' disabled={busy || !clientId || !clientSecret} onClick={() => void saveClient()} data-testid='google-client-save'>ذخیرهٔ امن</Button>
        </div>
      )}
      {view.hint && <p className='text-muted-foreground text-xs'>{view.hint}</p>}
      <p className='text-muted-foreground text-xs'>پیش از اتصال، <a href='/privacy' target='_blank' rel='noreferrer' className='text-primary underline'>نحوهٔ استفاده و نگهداری داده‌های گوگل</a> را بخوانید.</p>
    </IntegrationCard>
  );
}
