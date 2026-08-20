'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { GoogleAccountCard } from '@/features/sites/components/google-account-card';
import { ApiError, endpoints, type GoogleAccountStatus, type IntegrationBlock } from '@/lib/api/client';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { SYNC_BADGE_FA, friendlyDomain, mergeDiscovery, siteSlug, type DiscoveredSite } from '../lib';

/**
 * راه‌اندازی سریع — onboarding چهارقدمی برای کاربر غیرفنی. هیچ Property ID، ‏Client ID یا اصطلاح فنی‌ای در این
 * مسیر نیست؛ همه‌چیز روی APIهای موجود سوار است: discovery ‏GSC/GA4، ‏ساخت سایت، تست اتصال (که sync را خودکار
 * صف می‌کند) و endpoint تجمیعی /integrations برای نمایش پیشرفت.
 */
const STEPS = ['اتصال گوگل', 'انتخاب سایت‌ها', 'اتصال وردپرس', 'شروع تحلیل'];

type Created = { site_id: string; domain: string; wp_url?: string };

export function OnboardingWizard() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [google, setGoogle] = useState<GoogleAccountStatus | null>(null);
  const [sites, setSites] = useState<DiscoveredSite[] | null>(null);
  const [ga4All, setGa4All] = useState<{ property_id: string; display_name: string | null }[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [ga4Pick, setGa4Pick] = useState<Record<string, string>>({});
  const [created, setCreated] = useState<Created[]>([]);
  const [wpUrls, setWpUrls] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  return (
    <div className='mx-auto grid max-w-3xl gap-4'>
      <div className='flex flex-wrap items-center gap-2 text-sm'>
        {STEPS.map((t, i) => (
          <span key={t} className='flex items-center gap-2'>
            <Badge variant={i === step ? 'default' : i < step ? 'secondary' : 'outline'}>{i + 1}. {t}</Badge>
            {i < STEPS.length - 1 && <span className='text-muted-foreground'>←</span>}
          </span>
        ))}
      </div>

      {step === 0 && <StepGoogle onReady={(g) => { setGoogle(g); setStep(1); }} />}
      {step === 1 && (
        <StepPick google={google} sites={sites} setSites={setSites} ga4All={ga4All} setGa4All={setGa4All}
          picked={picked} setPicked={setPicked} ga4Pick={ga4Pick} setGa4Pick={setGa4Pick} busy={busy}
          onBack={() => setStep(0)}
          onNext={async () => {
            const chosen = (sites ?? []).filter((s) => picked[s.domain]);
            if (!chosen.length) { toast.error('حداقل یک سایت را انتخاب کنید'); return; }
            setBusy(true);
            const done: Created[] = [];
            try {
              const existing = new Set((await endpoints.sites()).map((s) => s.site_id));
              for (const s of chosen) {
                const id = siteSlug(s.domain);
                const ga4Id = ga4Pick[s.domain] ?? s.ga4?.property_id ?? '';
                if (!existing.has(id)) {
                  await endpoints.createSite({ site_id: id, name: s.domain, canonical_url: `https://${s.domain}/`,
                    gsc_property: s.gsc_property, ...(ga4Id ? { ga4_property: ga4Id } : {}) } as never);
                }
                done.push({ site_id: id, domain: s.domain });
              }
              setCreated(done);
              setWpUrls(Object.fromEntries(done.map((d) => [d.site_id, `https://${d.domain}`])));
              setStep(2);
            } catch (e) {
              toast.error(e instanceof ApiError ? e.message : 'ساخت سایت انجام نشد — بعداً دوباره تلاش کنید');
            } finally {
              setBusy(false);
            }
          }} />
      )}
      {step === 2 && (
        <StepWordPress created={created} wpUrls={wpUrls} setWpUrls={setWpUrls}
          onBack={() => setStep(1)} onNext={() => setStep(3)} />
      )}
      {step === 3 && <StepLaunch created={created} onDone={() => router.push(created[0] ? `/dashboard/sites/${created[0].site_id}?tab=connections` : '/dashboard/overview')} />}
    </div>
  );
}

// ---------------------------------------------------------------- قدم ۱ — فقط یک دکمه
function StepGoogle({ onReady }: { onReady: (g: GoogleAccountStatus) => void }) {
  const [status, setStatus] = useState<GoogleAccountStatus | null>(null);
  useEffect(() => { void endpoints.googleStatus().then(setStatus).catch(() => null); }, []);
  return (
    <div className='grid gap-3'>
      <Card>
        <CardHeader>
          <CardTitle>به SEO Brain خوش آمدید 👋</CardTitle>
          <CardDescription>با یک ورود به حساب گوگل، آمار جستجو و بازدید سایت‌هایتان فقط «خوانده» می‌شود — هیچ‌چیزی تغییر نمی‌کند.</CardDescription>
        </CardHeader>
      </Card>
      <GoogleAccountCard simple onChange={() => void endpoints.googleStatus().then(setStatus).catch(() => null)} />
      <div className='flex justify-end'>
        <Button disabled={!status?.connected} onClick={() => status && onReady(status)} data-testid='onboarding-next-1'>
          {status?.connected ? 'ادامه' : 'ابتدا حساب گوگل را متصل کنید'}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- قدم ۲ — کارت‌های دامنهٔ دوستانه
function StepPick(props: {
  google: GoogleAccountStatus | null;
  sites: DiscoveredSite[] | null; setSites: (s: DiscoveredSite[]) => void;
  ga4All: { property_id: string; display_name: string | null }[]; setGa4All: (g: { property_id: string; display_name: string | null }[]) => void;
  picked: Record<string, boolean>; setPicked: (p: Record<string, boolean>) => void;
  ga4Pick: Record<string, string>; setGa4Pick: (p: Record<string, string>) => void;
  busy: boolean; onBack: () => void; onNext: () => void;
}) {
  const { sites, setSites, setGa4All, ga4All, picked, setPicked, ga4Pick, setGa4Pick, busy, onBack, onNext } = props;
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (sites) return;
    Promise.all([endpoints.gscProperties(), endpoints.ga4Properties()])
      .then(([g, a]) => {
        setGa4All(a.status === 'ok' ? a.properties : []);
        setSites(mergeDiscovery(g.status === 'ok' ? g.properties.map((p) => ({ property: p.property, permission: p.permission })) : [], a.status === 'ok' ? a.properties : []));
      })
      .catch(() => setError('دریافت فهرست سایت‌ها ممکن نشد — اتصال گوگل را بررسی کنید'));
  }, [sites, setSites, setGa4All]);
  return (
    <Card>
      <CardHeader>
        <CardTitle>کدام سایت‌ها را تحلیل کنیم؟</CardTitle>
        <CardDescription>این فهرست از حساب گوگل شما خوانده شده است. سایت‌های موردنظر را انتخاب کنید.</CardDescription>
      </CardHeader>
      <CardContent className='grid gap-2'>
        {error && <p className='text-destructive text-sm'>{error}</p>}
        {!sites && !error && <p className='text-muted-foreground text-sm'>در حال دریافت سایت‌های شما…</p>}
        {sites?.length === 0 && <p className='text-muted-foreground text-sm'>سایتی در Search Console شما یافت نشد.</p>}
        {sites?.map((s) => (
          <label key={s.domain} className={`flex flex-wrap items-center gap-3 rounded-md border p-3 ${s.verified ? '' : 'opacity-60'}`} data-testid={`site-card-${s.domain}`}>
            <input type='checkbox' className='size-4' checked={Boolean(picked[s.domain])}
              onChange={(e) => setPicked({ ...picked, [s.domain]: e.target.checked })} disabled={!s.verified} />
            <span className='font-medium' dir='ltr'>🌐 {s.domain}</span>
            <Badge variant='secondary'>آمار جستجو ✓</Badge>
            {ga4All.length > 0 ? (
              <NativeSelect className='max-w-56' value={ga4Pick[s.domain] ?? s.ga4?.property_id ?? ''}
                onChange={(e) => setGa4Pick({ ...ga4Pick, [s.domain]: e.target.value })}>
                <NativeSelectOption value=''>بدون آمار بازدید</NativeSelectOption>
                {ga4All.map((g) => <NativeSelectOption key={g.property_id} value={g.property_id}>{g.display_name ?? 'Analytics'}</NativeSelectOption>)}
              </NativeSelect>
            ) : (
              <Badge variant='outline'>بدون آنالیتیکس</Badge>
            )}
            {!s.verified && <span className='text-muted-foreground text-xs'>دسترسی تأییدنشده</span>}
          </label>
        ))}
        <div className='mt-2 flex justify-between'>
          <Button variant='ghost' onClick={onBack}>بازگشت</Button>
          <Button onClick={onNext} disabled={busy} data-testid='onboarding-next-2'>{busy ? 'در حال ساخت…' : 'ادامه'}</Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------- قدم ۳ — فقط آدرس سایت
function StepWordPress({ created, wpUrls, setWpUrls, onBack, onNext }: {
  created: Created[]; wpUrls: Record<string, string>; setWpUrls: (w: Record<string, string>) => void;
  onBack: () => void; onNext: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [ok, setOk] = useState<Record<string, boolean>>({});
  async function test(siteId: string) {
    setBusy(siteId);
    try {
      const r = await endpoints.testConnection(siteId, 'wordpress', wpUrls[siteId] || null);
      setOk((o) => ({ ...o, [siteId]: r.ok }));
      (r.ok ? toast.success : toast.error)(r.ok ? 'سایت وردپرسی شناسایی شد — دریافت محتوا شروع شد' : 'اتصال برقرار نشد — می‌توانید بعداً از صفحهٔ سایت تلاش کنید');
    } catch {
      toast.error('اتصال برقرار نشد — می‌توانید این مرحله را فعلاً رد کنید');
    } finally {
      setBusy(null);
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>اتصال به وردپرس</CardTitle>
        <CardDescription>فقط آدرس سایت کافی است — محتوای سایت (فقط‌خواندنی) دریافت می‌شود. این مرحله اختیاری است.</CardDescription>
      </CardHeader>
      <CardContent className='grid gap-3'>
        {created.map((c) => (
          <div key={c.site_id} className='flex flex-wrap items-center gap-2 rounded-md border p-3'>
            <span className='min-w-36 font-medium' dir='ltr'>{c.domain}</span>
            <Input className='flex-1' dir='ltr' value={wpUrls[c.site_id] ?? ''} placeholder='https://example.com'
              onChange={(e) => setWpUrls({ ...wpUrls, [c.site_id]: e.target.value })} />
            <Button size='sm' disabled={busy === c.site_id} onClick={() => void test(c.site_id)}>
              {busy === c.site_id ? 'در حال بررسی…' : ok[c.site_id] ? 'متصل ✓' : 'بررسی اتصال'}
            </Button>
          </div>
        ))}
        <p className='text-muted-foreground text-xs'>ورود پیشرفته (رمز برنامهٔ وردپرس) بعداً از صفحهٔ هر سایت، بخش وردپرس، در دسترس است.</p>
        <div className='flex justify-between'>
          <Button variant='ghost' onClick={onBack}>بازگشت</Button>
          <Button onClick={onNext} data-testid='onboarding-next-3'>ادامه</Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------- قدم ۴ — شروع تحلیل + پیشرفت
function StepLaunch({ created, onDone }: { created: Created[]; onDone: () => void }) {
  const [started, setStarted] = useState(false);
  const [state, setState] = useState<Record<string, IntegrationBlock[]>>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const poll = useCallback(async () => {
    const next: Record<string, IntegrationBlock[]> = {};
    for (const c of created) {
      try { next[c.site_id] = (await endpoints.integrations(c.site_id)).integrations; } catch { /* keep last */ }
    }
    setState((prev) => ({ ...prev, ...next }));
  }, [created]);

  useEffect(() => {
    if (!started) return;
    void poll();
    const running = Object.values(state).flat().some((i) => ['queued', 'running'].includes(i.sync.status));
    timer.current = setTimeout(() => { void poll(); }, 4000);
    if (!running && Object.keys(state).length && timer.current) { /* keep slow polling until user leaves */ }
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [started, state, poll]);

  async function start() {
    setStarted(true);
    for (const c of created) {
      try { await endpoints.testConnection(c.site_id, 'gsc', null); } catch { /* shown in progress */ }
      try { await endpoints.testConnection(c.site_id, 'ga4', null); } catch { /* optional */ }
    }
    void poll();
    toast.success('تحلیل شروع شد — دریافت داده‌ها چند دقیقه طول می‌کشد');
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>همه‌چیز آماده است 🎉</CardTitle>
        <CardDescription>با «شروع تحلیل»، داده‌های جستجو، بازدید و محتوا در پس‌زمینه جمع‌آوری می‌شوند.</CardDescription>
      </CardHeader>
      <CardContent className='grid gap-3'>
        {created.map((c) => (
          <div key={c.site_id} className='rounded-md border p-3'>
            <div className='mb-1 font-medium' dir='ltr'>🌐 {c.domain}</div>
            <div className='flex flex-wrap gap-2 text-xs'>
              {(state[c.site_id] ?? []).map((i) => (
                <Badge key={i.kind} variant={i.sync.status === 'succeeded' ? 'secondary' : ['failed', 'not_authorized'].includes(i.sync.status) ? 'destructive' : 'outline'}>
                  {i.label}: {SYNC_BADGE_FA[i.sync.status] ?? i.sync.status}{['queued', 'running'].includes(i.sync.status) && i.sync.step_fa ? ` — ${i.sync.step_fa}` : ''}
                </Badge>
              ))}
              {!state[c.site_id] && started && <span className='text-muted-foreground'>در حال بررسی…</span>}
            </div>
          </div>
        ))}
        <div className='flex justify-end gap-2'>
          {!started
            ? <Button onClick={() => void start()} data-testid='onboarding-start'>شروع تحلیل سئو</Button>
            : <Button onClick={onDone} data-testid='onboarding-done'>رفتن به داشبورد</Button>}
        </div>
      </CardContent>
    </Card>
  );
}
