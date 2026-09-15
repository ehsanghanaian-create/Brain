'use client';

import { Icons } from '@/components/icons';
import { EmptyState, ErrorState, LoadingState } from '@/components/seo-brain/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { traffic } from '@/lib/api/client';
import type { Site, TrafficBehavior, TrafficCalls, TrafficEntries, TrafficKeywords, TrafficOverview, TrafficPaid, TrackerSetup } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import { useCallback, useEffect, useState } from 'react';

const fa = new Intl.NumberFormat('fa-IR');
const pct = (v: number) => `${fa.format(Math.round(v * 1000) / 10)}٪`;

const CHANNEL_FA: Record<string, string> = {
  organic: 'ارگانیک',
  paid: 'تبلیغات',
  referral: 'ارجاع',
  social: 'شبکه اجتماعی',
  direct: 'مستقیم'
};
const DEVICE_FA: Record<string, string> = { mobile: 'موبایل', tablet: 'تبلت', desktop: 'دسکتاپ' };
const INTENT_FA: Record<string, string> = {
  branded: 'برندی',
  transactional: 'تراکنشی',
  commercial: 'تجاری',
  navigational: 'ناوبری',
  informational: 'اطلاعاتی'
};
const CONFIDENCE_FA: Record<string, string> = { high: 'بالا', medium: 'متوسط', low: 'پایین' };

/** One place for every fetch on this page: keeps loading/error handling identical across tabs. */
function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data: T | null; error: unknown; loading: boolean }>({ data: null, error: null, loading: true });
  const run = useCallback(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn()
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((error) => alive && setState({ data: null, error, loading: false }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(run, [run]);
  return { ...state, reload: run };
}

/** Re-renders on a timer so a tab can poll. Returns a nonce to drop into a useAsync dep list. */
function useLive(seconds: number, on: boolean) {
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    if (!on) return;
    const id = setInterval(() => setNonce((n) => n + 1), seconds * 1000);
    return () => clearInterval(id);
  }, [seconds, on]);
  return nonce;
}

function Toolbar({
  sites,
  siteId,
  onSite,
  days,
  onDays
}: {
  sites: Site[];
  siteId: string;
  onSite: (id: string) => void;
  days: number;
  onDays: (d: number) => void;
}) {
  return (
    <div className='flex flex-wrap items-center gap-2'>
      <div className='flex flex-wrap gap-1'>
        {sites.map((s) => (
          <Button key={s.site_id} size='sm' variant={s.site_id === siteId ? 'default' : 'outline'} onClick={() => onSite(s.site_id)}>
            {s.name}
          </Button>
        ))}
      </div>
      <Separator orientation='vertical' className='mx-1 h-6' />
      <div className='flex gap-1'>
        {[7, 28, 90].map((d) => (
          <Button key={d} size='sm' variant={d === days ? 'secondary' : 'ghost'} onClick={() => onDays(d)}>
            {fa.format(d)} روز
          </Button>
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: 'good' | 'warn' }) {
  return (
    <Card size='sm'>
      <CardHeader>
        <CardDescription className='text-xs'>{label}</CardDescription>
        <CardTitle className={cn('text-2xl font-semibold tabular-nums', tone === 'good' && 'text-emerald-600', tone === 'warn' && 'text-amber-600')}>
          {value}
        </CardTitle>
        {hint && <p className='text-muted-foreground text-[11px]'>{hint}</p>}
      </CardHeader>
    </Card>
  );
}

/** Daily series as plain bars — no chart library, so nothing to keep in sync and nothing to break in RTL. */
function Series({ rows }: { rows: { day: string; sessions: number; organic: number; conversions: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.sessions));
  return (
    <div className='flex h-32 items-end gap-[3px]' dir='ltr'>
      {rows.map((r) => (
        <div
          key={r.day}
          className='group relative flex-1 rounded-t bg-muted'
          style={{ height: `${Math.max(2, (r.sessions / max) * 100)}%` }}
          title={`${r.day} — ${r.sessions} نشست، ${r.organic} ارگانیک، ${r.conversions} تبدیل`}
        >
          <div className='bg-primary/70 absolute inset-x-0 bottom-0 rounded-t' style={{ height: `${r.sessions ? (r.organic / r.sessions) * 100 : 0}%` }} />
        </div>
      ))}
    </div>
  );
}

function NoData({ onGo }: { onGo: () => void }) {
  return (
    <EmptyState
      icon='focus'
      title='هنوز داده‌ای نرسیده'
      description='اسکریپت ترکر روی سایت نصب نشده یا هنوز بازدیدی ثبت نشده است. از تب «نصب» کد را بردارید و در قالب قرار دهید.'
      action={
        <Button size='sm' onClick={onGo}>
          رفتن به نصب
        </Button>
      }
    />
  );
}

export function TrafficPage({ sites, initialSiteId }: { sites: Site[]; initialSiteId: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [days, setDays] = useState(28);
  const [tab, setTab] = useState('overview');

  return (
    <div className='flex flex-col gap-4'>
      <Toolbar sites={sites} siteId={siteId} onSite={setSiteId} days={days} onDays={setDays} />

      <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
        <div className='-mx-1 overflow-x-auto px-1'>
          <TabsList variant='line'>
            <TabsTrigger value='overview'>نمای کلی</TabsTrigger>
            <TabsTrigger value='ads'>تبلیغات</TabsTrigger>
            <TabsTrigger value='entries'>ورودی ارگانیک</TabsTrigger>
            <TabsTrigger value='calls'>تماس‌ها</TabsTrigger>
            <TabsTrigger value='behavior'>رفتار</TabsTrigger>
            <TabsTrigger value='keywords'>کلمه به تماس</TabsTrigger>
            <TabsTrigger value='setup'>نصب</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value='overview' className='pt-4'>
          <OverviewTab siteId={siteId} days={days} onSetup={() => setTab('setup')} />
        </TabsContent>
        <TabsContent value='ads' className='pt-4'>
          <AdsTab siteId={siteId} days={days} onSetup={() => setTab('setup')} />
        </TabsContent>
        <TabsContent value='entries' className='pt-4'>
          <EntriesTab siteId={siteId} days={days} />
        </TabsContent>
        <TabsContent value='calls' className='pt-4'>
          <CallsTab siteId={siteId} days={days} onSetup={() => setTab('setup')} />
        </TabsContent>
        <TabsContent value='behavior' className='pt-4'>
          <BehaviorTab siteId={siteId} days={days} onSetup={() => setTab('setup')} />
        </TabsContent>
        <TabsContent value='keywords' className='pt-4'>
          <KeywordsTab siteId={siteId} days={days} />
        </TabsContent>
        <TabsContent value='setup' className='pt-4'>
          <SetupTab siteId={siteId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/* ------------------------------------------------------------------ overview */

function OverviewTab({ siteId, days, onSetup }: { siteId: string; days: number; onSetup: () => void }) {
  const { data, error, loading, reload } = useAsync<TrafficOverview>(() => traffic.overview(siteId, days), [siteId, days]);
  if (loading) return <LoadingState label='در حال خواندن ترافیک…' />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  if (!data.coverage.sessions) return <NoData onGo={onSetup} />;

  return (
    <div className='flex flex-col gap-4'>
      <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-5'>
        <Stat label='نشست‌ها' value={fa.format(data.sessions)} hint={`${data.date_from} → ${data.date_to}`} />
        <Stat label='بازدید صفحه' value={fa.format(data.pageviews)} />
        <Stat label='کلیک روی شماره' value={fa.format(data.tel_clicks)} tone='good' hint='قصد تماس، نه تماس برقرارشده' />
        <Stat label='نرخ تبدیل' value={pct(data.conversion_rate)} />
        <Stat label='میانگین زمان' value={`${fa.format(Math.round(data.avg_duration_s))} ثانیه`} hint={`نرخ خروج سریع ${pct(data.bounce_rate)}`} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className='text-sm'>روند روزانه</CardTitle>
          <CardDescription className='text-xs'>ارتفاع میله کل نشست‌ها؛ بخش پررنگ سهم ارگانیک.</CardDescription>
        </CardHeader>
        <CardContent>
          <Series rows={data.series} />
        </CardContent>
      </Card>

      <div className='grid gap-3 lg:grid-cols-3'>
        <Card>
          <CardHeader>
            <CardTitle className='text-sm'>کانال ورود</CardTitle>
          </CardHeader>
          <CardContent className='flex flex-col gap-2 text-sm'>
            {data.by_channel.map((c) => (
              <div key={c.channel} className='flex items-center justify-between gap-2'>
                <span>{CHANNEL_FA[c.channel] ?? c.channel}</span>
                <span className='text-muted-foreground tabular-nums'>
                  {fa.format(c.sessions)} نشست · {fa.format(c.conversions)} تبدیل
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className='text-sm'>موتور جستجو</CardTitle>
            <CardDescription className='text-xs'>زربین و گردو هم اینجا ارگانیک حساب می‌شوند.</CardDescription>
          </CardHeader>
          <CardContent className='flex flex-col gap-2 text-sm'>
            {data.by_search_engine.length === 0 && <span className='text-muted-foreground text-xs'>هنوز ورودی ارگانیکی ثبت نشده.</span>}
            {data.by_search_engine.map((e) => (
              <div key={e.search_engine} className='flex items-center justify-between gap-2'>
                <span dir='ltr'>{e.search_engine}</span>
                <span className='text-muted-foreground tabular-nums'>{fa.format(e.sessions)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className='text-sm'>دستگاه</CardTitle>
          </CardHeader>
          <CardContent className='flex flex-col gap-2 text-sm'>
            {data.by_device.map((d) => (
              <div key={d.device} className='flex items-center justify-between gap-2'>
                <span>{DEVICE_FA[d.device] ?? d.device}</span>
                <span className='text-muted-foreground tabular-nums'>
                  {fa.format(d.sessions)} · {fa.format(d.conversions)} تبدیل
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ ads (live) */

function AdsTab({ siteId, days, onSetup }: { siteId: string; days: number; onSetup: () => void }) {
  const [live, setLive] = useState(true);
  const nonce = useLive(10, live);
  const window_ = Math.min(days, 90); // the endpoint caps at 90 — the Ads API lookback for gclid is 90 days
  const { data, error, loading, reload } = useAsync<TrafficPaid>(() => traffic.paid(siteId, window_), [siteId, window_, nonce]);

  if (loading && !data) return <LoadingState label='در حال خواندن ترافیک تبلیغات…' />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  const rows = data.items;
  const conversions = rows.filter((r) => r.conversion_type).length;
  const campaigns = new Set(rows.map((r) => r.utm_campaign).filter(Boolean)).size;

  return (
    <div className='flex flex-col gap-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <Button size='sm' variant={live ? 'secondary' : 'outline'} onClick={() => setLive((v) => !v)}>
          <span className={cn('me-1 inline-block size-2 rounded-full', live ? 'bg-emerald-500' : 'bg-muted-foreground')} />
          {live ? 'زنده — هر ۱۰ ثانیه' : 'به‌روزرسانی متوقف'}
        </Button>
        <Button size='sm' variant='ghost' onClick={reload}>
          به‌روزرسانی دستی
        </Button>
        <span className='text-muted-foreground text-xs'>پنجره: {fa.format(window_)} روز</span>
      </div>

      {!rows.length ? (
        <EmptyState
          icon='focus'
          title='هنوز نشست تبلیغاتی ثبت نشده'
          description='نشستی با gclid نیامده است. یا ترکر روی سایت نصب نیست، یا در این بازه کلیکی از تبلیغات نبوده.'
          action={
            <Button size='sm' onClick={onSetup}>
              رفتن به نصب
            </Button>
          }
        />
      ) : (
        <>
          <div className='grid gap-3 sm:grid-cols-3'>
            <Stat label='نشست از تبلیغات' value={fa.format(rows.length)} hint='هر ردیف یک ورود با gclid' />
            <Stat label='تبدیل از تبلیغات' value={fa.format(conversions)} tone={conversions ? 'good' : undefined} />
            <Stat label='کمپین‌های درگیر' value={fa.format(campaigns)} />
          </div>

          <Card className='py-0'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className='text-start'>زمان</TableHead>
                  <TableHead className='text-start'>صفحه ورود</TableHead>
                  <TableHead className='text-start'>دستگاه</TableHead>
                  <TableHead className='text-start'>کمپین</TableHead>
                  <TableHead className='text-start'>عبارت</TableHead>
                  <TableHead className='text-start'>تبدیل</TableHead>
                  <TableHead className='text-start'>gclid</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r, i) => (
                  <TableRow key={`${r.gclid}-${i}`}>
                    <TableCell className='font-mono text-xs whitespace-nowrap' dir='ltr'>
                      {r.started_at?.slice(11, 19) ?? '—'}
                    </TableCell>
                    <TableCell className='max-w-[18rem] whitespace-normal'>
                      <span dir='ltr' className='font-mono text-xs'>
                        {r.landing_path}
                      </span>
                    </TableCell>
                    <TableCell className='text-xs'>{DEVICE_FA[r.device] ?? r.device}</TableCell>
                    <TableCell className='text-xs'>{r.utm_campaign || '—'}</TableCell>
                    <TableCell className='text-xs'>{r.utm_term || '—'}</TableCell>
                    <TableCell>
                      {r.conversion_type ? (
                        <Badge variant='outline' className='border-transparent bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'>
                          تماس
                        </Badge>
                      ) : (
                        <span className='text-muted-foreground text-xs'>—</span>
                      )}
                    </TableCell>
                    <TableCell className='text-muted-foreground max-w-[12rem] truncate font-mono text-[11px]' dir='ltr' title={r.gclid}>
                      {r.gclid}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>

          <Card className='border-s-2 border-s-amber-500'>
            <CardHeader>
              <CardTitle className='text-sm'>کلمه کلیدی این کلیک‌ها هنوز حل نشده</CardTitle>
              <CardDescription className='text-xs leading-6'>{data.note}</CardDescription>
            </CardHeader>
          </Card>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ entries */

function EntriesTab({ siteId, days }: { siteId: string; days: number }) {
  const { data, error, loading, reload } = useAsync<TrafficEntries>(() => traffic.entries(siteId, days), [siteId, days]);
  if (loading) return <LoadingState label='در حال خواندن صفحات ورود…' />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data?.items.length) return <EmptyState icon='focus' title='صفحه ورودی‌ای پیدا نشد' description='نه ترکر داده‌ای دارد و نه سرچ‌کنسول برای این بازه.' />;

  return (
    <div className='flex flex-col gap-3'>
      <p className='text-muted-foreground text-xs leading-6'>
        دو ستون سمت راست از ترکر خودمان می‌آید و دقیق است؛ ستون‌های سرچ‌کنسول از <span dir='ltr' className='font-mono'>gsc_daily</span> خوانده می‌شود. این دو
        عدد با هم نمی‌خوانند و قرار هم نیست بخوانند — نسبتشان در ستون آخر آمده تا اندازه اختلاف دیده شود.
      </p>
      <Card className='py-0'>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className='text-start'>صفحه ورود</TableHead>
              <TableHead className='text-start'>نشست</TableHead>
              <TableHead className='text-start'>تماس</TableHead>
              <TableHead className='text-start'>نرخ تبدیل</TableHead>
              <TableHead className='text-start'>کلیک GSC</TableHead>
              <TableHead className='text-start'>ایمپرشن</TableHead>
              <TableHead className='text-start'>میانگین جایگاه</TableHead>
              <TableHead className='text-start'>کلیک به نشست</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((r) => (
              <TableRow key={r.path}>
                <TableCell className='max-w-[22rem] whitespace-normal'>
                  <span dir='ltr' className='font-mono text-xs'>
                    {r.path}
                  </span>
                </TableCell>
                <TableCell className='tabular-nums'>{fa.format(r.sessions)}</TableCell>
                <TableCell className='tabular-nums'>{fa.format(r.tel_clicks)}</TableCell>
                <TableCell className='tabular-nums'>{r.sessions ? pct(r.conversion_rate) : '—'}</TableCell>
                <TableCell className='tabular-nums'>{fa.format(r.gsc_clicks)}</TableCell>
                <TableCell className='text-muted-foreground tabular-nums'>{fa.format(r.gsc_impressions)}</TableCell>
                <TableCell className='tabular-nums'>{r.gsc_position ? fa.format(r.gsc_position) : '—'}</TableCell>
                <TableCell className='text-muted-foreground tabular-nums'>{r.gsc_to_session_ratio ? `${fa.format(r.gsc_to_session_ratio)}×` : '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ calls */

function CallsTab({ siteId, days, onSetup }: { siteId: string; days: number; onSetup: () => void }) {
  const { data, error, loading, reload } = useAsync<TrafficCalls>(() => traffic.calls(siteId, days), [siteId, days]);
  if (loading) return <LoadingState label='در حال خواندن تماس‌ها…' />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data?.total) return <NoData onGo={onSetup} />;
  const maxHour = Math.max(1, ...data.by_hour.map((h) => h.clicks));

  return (
    <div className='flex flex-col gap-4'>
      <div className='grid gap-3 sm:grid-cols-3'>
        <Stat label='کل کلیک روی شماره' value={fa.format(data.total)} tone='good' hint={`${data.date_from} → ${data.date_to}`} />
        <Stat label='صفحه برتر' value={data.by_page[0]?.path ?? '—'} hint={`${fa.format(data.by_page[0]?.clicks ?? 0)} کلیک`} />
        <Stat label='ساعت اوج' value={`${data.by_hour.reduce((a, b) => (b.clicks > a.clicks ? b : a), data.by_hour[0]).hour}:۰۰`} hint='به وقت UTC' />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className='text-sm'>ساعت‌های تماس</CardTitle>
          <CardDescription className='text-xs'>برای تنظیم شیفت اپراتور و زمان‌بندی کمپین.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className='flex h-24 items-end gap-[2px]' dir='ltr'>
            {data.by_hour.map((h) => (
              <div key={h.hour} className='bg-primary/70 flex-1 rounded-t' style={{ height: `${Math.max(3, (h.clicks / maxHour) * 100)}%` }} title={`${h.hour}:00 — ${h.clicks}`} />
            ))}
          </div>
        </CardContent>
      </Card>

      <div className='grid gap-3 lg:grid-cols-2'>
        <Card className='py-0'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className='text-start'>صفحه</TableHead>
                <TableHead className='text-start'>کلیک</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.by_page.map((p) => (
                <TableRow key={p.path}>
                  <TableCell className='max-w-[20rem] whitespace-normal'>
                    <span dir='ltr' className='font-mono text-xs'>
                      {p.path}
                    </span>
                  </TableCell>
                  <TableCell className='tabular-nums'>{fa.format(p.clicks)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
        <Card className='py-0'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className='text-start'>کانال</TableHead>
                <TableHead className='text-start'>کلیک</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.by_channel.map((ch) => (
                <TableRow key={`${ch.channel}-${ch.search_engine}`}>
                  <TableCell>
                    {CHANNEL_FA[ch.channel] ?? ch.channel}
                    {ch.search_engine && <span className='text-muted-foreground ms-1 text-xs' dir='ltr'>({ch.search_engine})</span>}
                  </TableCell>
                  <TableCell className='tabular-nums'>{fa.format(ch.clicks)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ behavior */

function BehaviorTab({ siteId, days, onSetup }: { siteId: string; days: number; onSetup: () => void }) {
  const [path, setPath] = useState<string | null>(null);
  const { data, error, loading, reload } = useAsync<TrafficBehavior>(() => traffic.behavior(siteId, days, path), [siteId, days, path]);
  if (loading) return <LoadingState label='در حال خواندن رفتار…' />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data?.pages.length) return <NoData onGo={onSetup} />;
  const scrollTotal = Math.max(1, ...data.scroll.map((s) => s.hits));

  return (
    <div className='flex flex-col gap-4'>
      <div className='flex flex-wrap items-center gap-1'>
        <Button size='sm' variant={path ? 'ghost' : 'secondary'} onClick={() => setPath(null)}>
          همه صفحات
        </Button>
        {data.pages.slice(0, 6).map((p) => (
          <Button key={p.path} size='sm' variant={path === p.path ? 'secondary' : 'ghost'} onClick={() => setPath(p.path)}>
            <span dir='ltr' className='font-mono text-[11px]'>
              {p.path}
            </span>
          </Button>
        ))}
      </div>

      <div className='grid gap-3 lg:grid-cols-2'>
        <Card>
          <CardHeader>
            <CardTitle className='text-sm'>عمق اسکرول</CardTitle>
            <CardDescription className='text-xs'>چند نفر تا هر ربع صفحه رسیده‌اند.</CardDescription>
          </CardHeader>
          <CardContent className='flex flex-col gap-2'>
            {data.scroll.map((s) => (
              <div key={s.depth} className='flex items-center gap-2 text-xs'>
                <span className='w-10 tabular-nums'>{fa.format(s.depth)}٪</span>
                <div className='bg-muted h-3 flex-1 overflow-hidden rounded'>
                  <div className='bg-primary/70 h-full rounded' style={{ width: `${(s.hits / scrollTotal) * 100}%` }} />
                </div>
                <span className='text-muted-foreground w-10 tabular-nums'>{fa.format(s.hits)}</span>
              </div>
            ))}
            {!data.scroll.length && <span className='text-muted-foreground text-xs'>رویداد اسکرولی ثبت نشده.</span>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className='text-sm'>نقشه کلیک</CardTitle>
            <CardDescription className='text-xs'>موقعیت نسبی کلیک‌ها؛ قرمز یعنی کلیک روی شماره تماس.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className='bg-muted/40 relative aspect-[3/4] w-full overflow-hidden rounded border' dir='ltr'>
              {data.points.map((p, i) => (
                <span
                  key={i}
                  className={cn('absolute size-2 -translate-x-1/2 -translate-y-1/2 rounded-full', p.type === 'tel_click' ? 'bg-rose-500/70' : 'bg-sky-500/40')}
                  style={{ left: `${p.x * 100}%`, top: `${p.y * 100}%` }}
                />
              ))}
              {!data.points.length && <span className='text-muted-foreground absolute inset-0 grid place-items-center text-xs'>کلیکی ثبت نشده</span>}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className='py-0'>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className='text-start'>عنصر</TableHead>
              <TableHead className='text-start'>صفحه</TableHead>
              <TableHead className='text-start'>کلیک</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.clicks.map((c, i) => (
              <TableRow key={`${c.path}-${c.label}-${i}`}>
                <TableCell className='max-w-[24rem] whitespace-normal text-xs'>{c.label || '—'}</TableCell>
                <TableCell>
                  <span dir='ltr' className='font-mono text-xs'>
                    {c.path}
                  </span>
                </TableCell>
                <TableCell className='tabular-nums'>{fa.format(c.clicks)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ keywords (estimated) */

function KeywordsTab({ siteId, days }: { siteId: string; days: number }) {
  const { data, error, loading, reload } = useAsync<TrafficKeywords>(() => traffic.keywords(siteId, days), [siteId, days]);
  if (loading) return <LoadingState label='در حال تخمین…' />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data?.items.length)
    return (
      <EmptyState
        icon='keywords'
        title='هنوز چیزی برای تخمین نیست'
        description='این صفحه وقتی کار می‌کند که هم ترکر تبدیل ثبت کرده باشد و هم سرچ‌کنسول برای همان صفحه کوئری داشته باشد.'
      />
    );

  return (
    <div className='flex flex-col gap-3'>
      <Card className='border-s-2 border-s-amber-500'>
        <CardHeader>
          <CardTitle className='flex flex-wrap items-center gap-2 text-sm'>
            این اعداد تخمینی‌اند
            <Badge variant='outline' className='border-transparent bg-amber-500/10 text-amber-700 dark:text-amber-400'>
              estimated
            </Badge>
          </CardTitle>
          <CardDescription className='text-xs leading-6'>{data.caveat}</CardDescription>
        </CardHeader>
        <CardContent className='text-muted-foreground text-xs leading-6'>روش: {data.method}</CardContent>
      </Card>

      <Card className='py-0'>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className='text-start'>کلمه کلیدی</TableHead>
              <TableHead className='text-start'>نیت</TableHead>
              <TableHead className='text-start'>صفحه</TableHead>
              <TableHead className='text-start'>کلیک GSC</TableHead>
              <TableHead className='text-start'>جایگاه</TableHead>
              <TableHead className='text-start'>سهم</TableHead>
              <TableHead className='text-start'>تبدیل تخمینی</TableHead>
              <TableHead className='text-start'>اطمینان</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((r, i) => (
              <TableRow key={`${r.path}-${r.query}-${i}`}>
                <TableCell className='max-w-[18rem] whitespace-normal font-medium'>{r.query}</TableCell>
                <TableCell className='text-xs'>{INTENT_FA[r.intent] ?? r.intent}</TableCell>
                <TableCell className='max-w-[16rem] whitespace-normal'>
                  <span dir='ltr' className='font-mono text-xs'>
                    {r.path}
                  </span>
                </TableCell>
                <TableCell className='tabular-nums'>{fa.format(r.gsc_clicks)}</TableCell>
                <TableCell className='tabular-nums'>{fa.format(r.gsc_position)}</TableCell>
                <TableCell className='text-muted-foreground tabular-nums'>{pct(r.share)}</TableCell>
                <TableCell className='tabular-nums'>{fa.format(r.est_conversions)}</TableCell>
                <TableCell>
                  <Badge
                    variant='outline'
                    className={cn(
                      'border-transparent',
                      r.confidence === 'high' && 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
                      r.confidence === 'medium' && 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
                      r.confidence === 'low' && 'bg-rose-500/10 text-rose-700 dark:text-rose-400'
                    )}
                  >
                    {CONFIDENCE_FA[r.confidence]}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ setup */

function SetupTab({ siteId }: { siteId: string }) {
  const [nonce, setNonce] = useState(0);
  const [busy, setBusy] = useState(false);
  const { data, error, loading, reload } = useAsync<TrackerSetup>(() => traffic.setup(siteId), [siteId, nonce]);
  if (loading) return <LoadingState label='در حال خواندن تنظیمات…' rows={2} />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  // built server-side from the API's own origin — the panel runs on a different port (and in production a
  // different host), so the browser origin is the wrong base for a tag that ships to 13 other domains
  const snippet = data.snippet;

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      setNonce((n) => n + 1);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className='flex flex-col gap-4'>
      <Card>
        <CardHeader>
          <CardTitle className='text-sm'>یک خط، برای هر ۱۳ سایت</CardTitle>
          <CardDescription className='text-xs leading-6'>
            این خط را در فوتر قالب <span dir='ltr' className='font-mono'>emdad-master</span> بگذارید. کلید داخل اسکریپت تزریق می‌شود، پس برای هر سایت
            آدرس متفاوت است. اسکریپت کوکی نمی‌گذارد و شناسه بازدیدکننده هر شب صفر می‌شود.
          </CardDescription>
        </CardHeader>
        <CardContent className='flex flex-col gap-3'>
          <pre dir='ltr' className='bg-muted/60 overflow-x-auto rounded-lg p-3 text-left font-mono text-xs'>
            {snippet}
          </pre>
          <div className='flex flex-wrap items-center gap-2'>
            <Button size='sm' variant='outline' onClick={() => navigator.clipboard?.writeText(snippet)}>
              <Icons.code className='size-3.5' /> کپی
            </Button>
            <Button size='sm' variant='ghost' disabled={busy} onClick={() => act(() => traffic.setEnabled(siteId, !data.enabled))}>
              {data.enabled ? 'غیرفعال کردن دریافت' : 'فعال کردن دریافت'}
            </Button>
            <Button size='sm' variant='ghost' disabled={busy} onClick={() => act(() => traffic.rotate(siteId))}>
              چرخاندن کلید
            </Button>
            <Badge variant='outline' className={cn('border-transparent', data.enabled ? 'bg-emerald-500/10 text-emerald-700' : 'bg-rose-500/10 text-rose-700')}>
              {data.enabled ? 'فعال' : 'غیرفعال'}
            </Badge>
          </div>
          <p className='text-muted-foreground text-[11px] leading-6'>
            کلید نوشتن عمومی است و داخل صفحه دیده می‌شود — نقشش محدودکردن نوشتن به یک سایت است، نه امنیت. چرخاندن کلید، کلید قبلی را بلافاصله
            بی‌اثر می‌کند، پس قالب باید دوباره اسکریپت را بگیرد.
          </p>
        </CardContent>
      </Card>

      <div className='grid gap-3 sm:grid-cols-4'>
        <Stat label='نشست ثبت‌شده' value={fa.format(data.coverage.sessions)} />
        <Stat label='رویداد' value={fa.format(data.coverage.events)} />
        <Stat label='اولین روز' value={data.coverage.first_day ?? '—'} />
        <Stat label='ردیف سرچ‌کنسول' value={fa.format(data.coverage.gsc_rows)} hint='از پایپ‌لاین موجود' />
      </div>
    </div>
  );
}
