'use client';
/** Site Report Center — مرکز گزارش کامل هر سایت (فقط داده واقعی: GSC/GA4/کراولر/ثبت دستی). */
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '@/components/ui/chart';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { EmptyState, ErrorState, LoadingState } from '@/components/seo-brain/states';
import { KpiCard } from '@/components/seo-brain/kpi-card';
import { ApiError, endpoints, type Site } from '@/lib/api/client';
import type {
  BacklinkRow, ReportageRow, ReportBacklinks, ReportFull, ReportKeywordList,
  ReportMainKeyword, ReportOpportunities, ReportProblems, ReportReportages, ReportSummary
} from '@/features/reports/types';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { toast } from 'sonner';

const fa = new Intl.NumberFormat('fa-IR');
const num = (v: number | null | undefined, d = 0) => (typeof v === 'number' && Number.isFinite(v) ? fa.format(Number(v.toFixed(d))) : '—');
const pos = (v: number | null | undefined) => (typeof v === 'number' && Number.isFinite(v) ? fa.format(Number(v.toFixed(1))) : '—');
const pct = (v: number | null | undefined) => (typeof v === 'number' && Number.isFinite(v) ? `${fa.format(Number((v * 100).toFixed(2)))}٪` : '—');
const time = new Intl.DateTimeFormat('fa-IR', { timeZone: 'Asia/Tehran', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
const ago = (iso: string | null | undefined) => {
  if (!iso) return 'هنوز اجرا نشده';
  const t = Date.parse(iso);
  return Number.isNaN(t) ? 'زمان نامشخص' : time.format(new Date(t));
};

const RANGES: { value: number; label: string }[] = [
  { value: 7, label: '۷ روز' }, { value: 28, label: '۲۸ روز' }, { value: 90, label: '۳ ماه' },
  { value: 180, label: '۶ ماه' }, { value: 365, label: '۱۲ ماه' }
];

const SEVERITY_FA: Record<string, { label: string; cls: string }> = {
  high: { label: 'بحرانی', cls: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300' },
  medium: { label: 'متوسط', cls: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300' },
  low: { label: 'کم', cls: 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300' }
};

const REPORTAGE_STATUS_FA: Record<string, { label: string; cls: string }> = {
  pending: { label: 'در انتظار انتشار', cls: 'bg-muted text-muted-foreground' },
  published: { label: 'منتشرشده (بررسی‌نشده)', cls: 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300' },
  link_found: { label: '✓ لینک پیدا شد', cls: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' },
  link_missing: { label: '⚠ لینک پیدا نشد', cls: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300' },
  article_missing: { label: '⚠ مقاله در دسترس نیست', cls: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300' },
  target_changed: { label: '⚠ مقصد لینک عوض شده', cls: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300' }
};

const chartConfig = {
  clicks: { label: 'کلیک', color: 'var(--chart-1)' },
  impressions: { label: 'نمایش', color: 'var(--chart-2)' },
  position: { label: 'جایگاه', color: 'var(--chart-3)' },
  sessions: { label: 'نشست', color: 'var(--chart-4)' }
} satisfies ChartConfig;

function Delta({ cur, prev, invert = false, digits = 0 }: { cur: number | null | undefined; prev: number | null | undefined; invert?: boolean; digits?: number }) {
  if (typeof cur !== 'number' || typeof prev !== 'number' || !Number.isFinite(cur) || !Number.isFinite(prev)) return null;
  const diff = cur - prev;
  if (Math.abs(diff) < 0.05) return <span className='text-muted-foreground text-xs'>بدون تغییر</span>;
  const good = invert ? diff < 0 : diff > 0;
  return (
    <span className={`text-xs ${good ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
      {good ? '▲' : '▼'} {fa.format(Number(Math.abs(diff).toFixed(digits)))}
    </span>
  );
}

function ChangeCell({ change }: { change: number | null }) {
  if (change === null || !Number.isFinite(change)) return <span className='text-muted-foreground'>—</span>;
  if (Math.abs(change) < 0.05) return <span className='text-muted-foreground'>۰</span>;
  const up = change > 0; // change = prev - cur → مثبت یعنی بهبود جایگاه
  return (
    <span className={up ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}>
      {up ? '▲' : '▼'} {fa.format(Number(Math.abs(change).toFixed(1)))}
    </span>
  );
}

const CONNECTION_FA: Record<string, string> = { gsc: 'Search Console', wordpress: 'وردپرس', ga4: 'GA4' };
const SOURCE_FA: Record<string, string> = {
  gsc_pipeline: 'Search Console', gsc: 'Search Console (داده)', wordpress_pipeline: 'وردپرس',
  wordpress: 'وردپرس (داده)', ga4_pipeline: 'GA4', ga4: 'GA4 (داده)', analysis: 'تحلیل سئو', graph: 'گراف'
};

export function SiteReportCenter({ sites, initialSiteId }: { sites: Site[]; initialSiteId: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [days, setDays] = useState(28);
  const [summary, setSummary] = useState<ReportFull | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    endpoints.reportFull(siteId, days)
      .then((s) => { if (!cancelled) { setSummary(s); setError(null); } })
      .catch((e) => { if (!cancelled) setError(e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e), null, '')); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [siteId, days, refreshKey]);

  // تا وقتی همگام‌سازی در جریان است هر ۵ ثانیه گزارش را تازه کن؛ با پایان sync خودش می‌ایستد
  useEffect(() => {
    if (summary?.sync_running) {
      pollRef.current = window.setTimeout(() => refresh(), 5000);
      return () => { if (pollRef.current) window.clearTimeout(pollRef.current); };
    }
    setRefreshing(false);
    return undefined;
  }, [summary, refresh]);

  const refreshNow = async () => {
    setRefreshing(true);
    try {
      const out = await endpoints.refreshSite(siteId);
      if (out.queued.length === 0) toast.info('اتصال فعالی برای همگام‌سازی وجود ندارد');
      else toast.success(`همگام‌سازی شروع شد: ${out.queued.map((x) => CONNECTION_FA[x.kind] ?? x.kind).join('، ')}`);
      refresh();
    } catch (e) {
      setRefreshing(false);
      toast.error(e instanceof ApiError ? e.message : String(e));
    }
  };

  const site = sites.find((s) => s.site_id === siteId);
  const g = summary?.gsc;
  const cur = g?.totals;
  const prev = g?.previous ?? undefined;
  const syncing = refreshing || Boolean(summary?.sync_running);
  const lastUpdate = summary ? Object.values(summary.freshness.last_runs).sort().at(-1) : null;
  const nextAt = summary
    ? Object.values(summary.freshness.auto_sync?.sources ?? {}).map((s) => s.next_at).filter(Boolean).sort()[0]
    : null;

  return (
    <div className='space-y-5'>
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect value={siteId} onChange={(e) => setSiteId(e.target.value)} className='w-52' aria-label='انتخاب سایت'>
          {sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name || s.site_id}</NativeSelectOption>)}
        </NativeSelect>
        <div className='bg-muted flex rounded-lg p-0.5' role='group' aria-label='بازه زمانی'>
          {RANGES.map((r) => (
            <Button key={r.value} size='sm' variant={days === r.value ? 'default' : 'ghost'} className='px-2.5' onClick={() => setDays(r.value)}>
              {r.label}
            </Button>
          ))}
        </div>
        <Button size='sm' variant='outline' onClick={refreshNow} disabled={syncing}>
          {syncing ? 'در حال همگام‌سازی…' : 'بروزرسانی الان'}
        </Button>
        {summary && (
          <span className='text-muted-foreground ms-auto text-xs'>
            آخرین بروزرسانی: {ago(lastUpdate)}{nextAt ? ` · بعدی: ${ago(nextAt)}` : ''}
          </span>
        )}
      </div>

      {summary && (
        <div className='flex flex-wrap gap-1.5'>
          {(['gsc', 'wordpress', 'ga4'] as const).map((k) => {
            const c = summary.connections[k];
            return (
              <Badge key={k} variant='outline'
                className={c.connected ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                  : c.configured ? 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300'
                  : 'text-muted-foreground'}>
                {CONNECTION_FA[k]}: {c.connected ? 'متصل' : c.configured ? 'مشکل اتصال' : 'متصل نیست'}
              </Badge>
            );
          })}
          {syncing && <Badge className='border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300'><span className='me-1 inline-block size-1.5 animate-pulse rounded-full bg-sky-500' />در حال دریافت داده جدید…</Badge>}
        </div>
      )}

      {error && <ErrorState error={error} onRetry={refresh} />}
      {loading && !summary && <LoadingState label='در حال ساخت گزارش سایت…' rows={6} />}

      {summary && (
        <>
          {/* ---- خلاصه مدیریتی ---- */}
          <Card>
            <CardHeader className='flex-row flex-wrap items-center justify-between gap-3 space-y-0'>
              <div>
                <CardTitle className='text-lg'>گزارش SEO — {site?.name || siteId}</CardTitle>
                <CardDescription dir='ltr' className='text-start'>{summary.site.canonical_url || summary.site.wp_url || siteId}</CardDescription>
              </div>
              <div className='text-center'>
                <div className='text-3xl font-bold tabular-nums'>{fa.format(summary.score)}<span className='text-muted-foreground text-base'>/۱۰۰</span></div>
                <div className='text-muted-foreground text-xs' title={`جریمه مشکلات: ${summary.score_breakdown.problems_penalty} · جریمه اتصال‌ها: ${summary.score_breakdown.connections_penalty}`}>
                  امتیاز سلامت سئو
                </div>
              </div>
            </CardHeader>
            <CardContent className='grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8'>
              <KpiCard label='ورودی ارگانیک' value={cur?.clicks ?? null} hint={prev ? undefined : `${days} روز اخیر GSC`} />
              <KpiCard label='نمایش (Impression)' value={cur?.impressions ?? null} />
              <KpiCard label='میانگین جایگاه' value={cur?.position != null ? Number(cur.position.toFixed(1)) : null} />
              <KpiCard label='صفحات ایندکس‌پذیر' value={summary.counts.indexable_pages} />
              <KpiCard label='کوئری‌های GSC' value={summary.counts.gsc_queries} />
              <KpiCard label='بک‌لینک‌ها' value={summary.counts.backlinks} />
              <KpiCard label='دامنه‌های ارجاع‌دهنده' value={summary.counts.referring_domains} />
              <KpiCard label='مشکلات سئو' value={summary.counts.problems.total} hint={`${fa.format(summary.counts.problems.high)} بحرانی`} />
            </CardContent>
            {(cur || prev) && (
              <CardContent className='text-muted-foreground flex flex-wrap gap-4 pt-0 text-xs'>
                {prev && <span>کلیک نسبت به دوره قبل: <Delta cur={cur?.clicks} prev={prev.clicks} /></span>}
                {prev && <span>نمایش: <Delta cur={cur?.impressions} prev={prev.impressions} /></span>}
                {prev && <span>جایگاه: <Delta cur={cur?.position} prev={prev.position} invert digits={1} /></span>}
                {g?.window && <span dir='ltr'>{g.window.from} → {g.window.to}</span>}
              </CardContent>
            )}
          </Card>

          {!g?.available && (
            <EmptyState
              title='Search Console برای این سایت متصل نیست'
              description='برای دیدن جایگاه، کلیک و نمایش واقعی، ابتدا GSC را در صفحه سایت متصل و همگام‌سازی کنید. هیچ عدد فرضی نمایش داده نمی‌شود.'
              action={<Button size='sm' variant='outline' nativeButton={false} render={<a href={`/dashboard/sites/${encodeURIComponent(siteId)}?tab=integrations`} />}>اتصال GSC</Button>}
            />
          )}

          <MainKeywordCard siteId={siteId} days={days} summary={summary} onChanged={refresh} />

          {g?.available && g.timeseries && g.timeseries.length > 1 && (
            <div className='grid gap-4 lg:grid-cols-2'>
              <Card>
                <CardHeader className='pb-2'><CardTitle className='text-base'>روند ورودی ارگانیک (کلیک GSC)</CardTitle></CardHeader>
                <CardContent>
                  <ChartContainer config={chartConfig} className='h-48 w-full' dir='ltr'>
                    <AreaChart data={g.timeseries} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid vertical={false} strokeDasharray='3 3' />
                      <XAxis dataKey='date' tick={{ fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={40} />
                      <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={36} />
                      <ChartTooltip content={<ChartTooltipContent />} />
                      <Area type='monotone' dataKey='clicks' stroke='var(--color-clicks)' fill='var(--color-clicks)' fillOpacity={0.18} strokeWidth={2} />
                    </AreaChart>
                  </ChartContainer>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className='pb-2'>
                  <CardTitle className='text-base'>روند جایگاه (میانگین وزنی روزانه)</CardTitle>
                  <CardDescription>محور وارونه — بالاتر یعنی جایگاه بهتر</CardDescription>
                </CardHeader>
                <CardContent>
                  <ChartContainer config={chartConfig} className='h-48 w-full' dir='ltr'>
                    <AreaChart data={g.timeseries} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid vertical={false} strokeDasharray='3 3' />
                      <XAxis dataKey='date' tick={{ fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={40} />
                      <YAxis reversed tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={36} domain={['auto', 'auto']} />
                      <ChartTooltip content={<ChartTooltipContent />} />
                      <Area type='monotone' dataKey='position' stroke='var(--color-position)' fill='var(--color-position)' fillOpacity={0.12} strokeWidth={2} connectNulls />
                    </AreaChart>
                  </ChartContainer>
                </CardContent>
              </Card>
              {summary.ga4.available && summary.ga4.timeseries && summary.ga4.timeseries.length > 1 && (
                <Card className='lg:col-span-2'>
                  <CardHeader className='pb-2'>
                    <CardTitle className='text-base'>روند ترافیک GA4 (کل نشست‌ها)</CardTitle>
                    {summary.ga4.totals && (
                      <CardDescription>
                        {summary.ga4.date_from} تا {summary.ga4.date_to}: {num(summary.ga4.totals.sessions)} نشست · {num(summary.ga4.totals.users)} کاربر · {num(summary.ga4.totals.conversions)} تبدیل · تعامل {pct(summary.ga4.totals.engagement_rate)}
                      </CardDescription>
                    )}
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={chartConfig} className='h-44 w-full' dir='ltr'>
                      <AreaChart data={summary.ga4.timeseries} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                        <CartesianGrid vertical={false} strokeDasharray='3 3' />
                        <XAxis dataKey='date' tick={{ fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={40} />
                        <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={36} />
                        <ChartTooltip content={<ChartTooltipContent />} />
                        <Area type='monotone' dataKey='sessions' stroke='var(--color-sessions)' fill='var(--color-sessions)' fillOpacity={0.15} strokeWidth={2} />
                      </AreaChart>
                    </ChartContainer>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          <Tabs defaultValue='keywords'>
            <TabsList className='flex-wrap'>
              <TabsTrigger value='keywords'>کلمات کلیدی</TabsTrigger>
              <TabsTrigger value='problems'>
                مشکلات {summary.counts.problems.total > 0 && <Badge variant='secondary' className='ms-1'>{fa.format(summary.counts.problems.total)}</Badge>}
              </TabsTrigger>
              <TabsTrigger value='opportunities'>فرصت‌ها</TabsTrigger>
              <TabsTrigger value='backlinks'>بک‌لینک‌ها</TabsTrigger>
              <TabsTrigger value='reportages'>رپورتاژها</TabsTrigger>
              <TabsTrigger value='history'>تاریخچه همگام‌سازی</TabsTrigger>
            </TabsList>
            <TabsContent value='keywords'><KeywordsPanel siteId={siteId} days={days} /></TabsContent>
            <TabsContent value='problems'><ProblemsPanel siteId={siteId} refreshKey={refreshKey} /></TabsContent>
            <TabsContent value='opportunities'><OpportunitiesPanel siteId={siteId} refreshKey={refreshKey} /></TabsContent>
            <TabsContent value='backlinks'><BacklinksPanel siteId={siteId} onChanged={refresh} /></TabsContent>
            <TabsContent value='reportages'><ReportagesPanel siteId={siteId} onChanged={refresh} /></TabsContent>
            <TabsContent value='history'><SyncHistoryPanel history={summary.sync_history} /></TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- کلمه کلیدی اصلی */

function MainKeywordCard({ siteId, days, summary, onChanged }: { siteId: string; days: number; summary: ReportSummary; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<ReportMainKeyword | null>(null);
  const [value, setValue] = useState('');
  const [saving, setSaving] = useState(false);
  const mk = summary.main_keyword;
  const perf = mk.performance;

  const openDialog = async () => {
    setValue(mk.keyword ?? '');
    setOpen(true);
    try { setDetail(await endpoints.reportMainKeyword(siteId, days)); } catch { /* پیشنهادها اختیاری است */ }
  };
  const save = async () => {
    if (!value.trim()) return;
    setSaving(true);
    try {
      await endpoints.setReportMainKeyword(siteId, value.trim());
      toast.success('کلمه کلیدی اصلی ذخیره شد');
      setOpen(false);
      onChanged();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally { setSaving(false); }
  };

  return (
    <Card>
      <CardHeader className='flex-row items-center justify-between space-y-0 pb-3'>
        <CardTitle className='text-base'>کلمه کلیدی اصلی</CardTitle>
        <Button size='sm' variant='outline' onClick={openDialog}>{mk.keyword ? 'تغییر' : 'تعیین کلمه کلیدی اصلی'}</Button>
      </CardHeader>
      <CardContent>
        {!mk.keyword ? (
          <p className='text-muted-foreground text-sm'>کلمه کلیدی اصلی برای این سایت تعیین نشده است.</p>
        ) : !perf ? (
          <div className='space-y-1'>
            <div className='text-xl font-bold'>{mk.keyword}</div>
            <p className='text-muted-foreground text-sm'>هنوز داده‌ای از Search Console برای این عبارت ثبت نشده است (جایگاه فرضی نمایش داده نمی‌شود).</p>
          </div>
        ) : (
          <div className='flex flex-wrap items-center gap-x-8 gap-y-3'>
            <div>
              <div className='text-xl font-bold'>{mk.keyword}</div>
              {perf.landing_page && (
                <a className='text-muted-foreground max-w-72 truncate text-xs underline-offset-2 hover:underline block' dir='ltr' href={perf.landing_page} target='_blank' rel='noreferrer' title={perf.landing_page}>
                  {perf.landing_page}
                </a>
              )}
            </div>
            <div className='text-center'>
              <div className='text-3xl font-bold tabular-nums'>{pos(perf.position)}</div>
              <div className='text-muted-foreground text-xs'>جایگاه فعلی <Delta cur={perf.position} prev={perf.prev_position} invert digits={1} /></div>
              {perf.prev_position != null && <div className='text-muted-foreground text-[11px]'>دوره قبل: {pos(perf.prev_position)}</div>}
            </div>
            <div className='text-center'><div className='text-2xl font-bold tabular-nums'>{num(perf.clicks)}</div><div className='text-muted-foreground text-xs'>کلیک (ورودی)</div></div>
            <div className='text-center'><div className='text-2xl font-bold tabular-nums'>{num(perf.impressions)}</div><div className='text-muted-foreground text-xs'>نمایش</div></div>
            <div className='text-center'><div className='text-2xl font-bold tabular-nums'>{pct(perf.ctr)}</div><div className='text-muted-foreground text-xs'>CTR</div></div>
            <div className='text-muted-foreground ms-auto text-[11px]' dir='ltr'>
              {perf.source === 'gsc_daily' ? `${perf.date_from} → ${perf.date_to}` : 'بازه کل داده GSC'}
            </div>
          </div>
        )}
      </CardContent>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent dir='rtl'>
          <DialogHeader>
            <DialogTitle>تعیین کلمه کلیدی اصلی</DialogTitle>
            <DialogDescription>جایگاه و کلیک این عبارت از داده واقعی Search Console محاسبه می‌شود؛ بهتر است یکی از کوئری‌های واقعی را انتخاب کنید.</DialogDescription>
          </DialogHeader>
          <div className='space-y-3'>
            <div className='space-y-1.5'>
              <Label htmlFor='mk-input'>کلمه کلیدی</Label>
              <Input id='mk-input' value={value} onChange={(e) => setValue(e.target.value)} placeholder='مثلاً: امداد خودرو رنو' />
            </div>
            {detail && detail.suggestions.length > 0 && (
              <div className='space-y-1.5'>
                <div className='text-muted-foreground text-xs'>پرکلیک‌ترین کوئری‌های واقعی این سایت:</div>
                <div className='flex flex-wrap gap-1.5'>
                  {detail.suggestions.map((s) => (
                    <button key={s.query} type='button' onClick={() => setValue(s.query)}
                      className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${value === s.query ? 'border-primary bg-primary/10' : 'hover:bg-muted'}`}>
                      {s.query} <span className='text-muted-foreground'>({num(s.clicks)} کلیک · جایگاه {pos(s.position)})</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className='flex justify-end gap-2'>
              <Button variant='outline' onClick={() => setOpen(false)}>انصراف</Button>
              <Button onClick={save} disabled={saving || !value.trim()}>{saving ? 'در حال ذخیره…' : 'ذخیره'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/* ---------------------------------------------------------------- تاریخچه همگام‌سازی */

function SyncHistoryPanel({ history }: { history: import('@/features/reports/types').SyncHistoryRow[] }) {
  if (history.length === 0) {
    return <EmptyState title='هنوز همگام‌سازی‌ای اجرا نشده است' description='با اولین Sync (خودکار یا «بروزرسانی الان») تاریخچه اینجا ثبت می‌شود.' />;
  }
  return (
    <Card>
      <CardContent className='pt-4'>
        <div className='overflow-x-auto rounded-md border'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>زمان</TableHead><TableHead>منبع</TableHead><TableHead>وضعیت</TableHead>
                <TableHead>مدت</TableHead><TableHead>ردیف‌های ذخیره‌شده</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.map((h, i) => (
                <TableRow key={i}>
                  <TableCell className='text-xs'>{ago(h.started_at)}</TableCell>
                  <TableCell className='text-xs'>{SOURCE_FA[h.source] ?? h.source}</TableCell>
                  <TableCell>
                    <Badge variant='outline' className={
                      h.status === 'failed' ? 'border-red-500/30 text-red-700 dark:text-red-300'
                        : h.status in { queued: 1, running: 1 } ? 'border-sky-500/30 text-sky-700 dark:text-sky-300'
                        : 'border-emerald-500/30 text-emerald-700 dark:text-emerald-300'}>
                      {h.status === 'failed' ? 'ناموفق' : h.status === 'queued' ? 'در صف' : h.status === 'running' ? 'در حال اجرا' : 'موفق'}
                    </Badge>
                  </TableCell>
                  <TableCell className='text-xs tabular-nums'>{h.duration_seconds != null ? `${fa.format(h.duration_seconds)} ثانیه` : '—'}</TableCell>
                  <TableCell className='text-xs tabular-nums'>{h.rows_written != null ? fa.format(h.rows_written) : '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ---------------------------------------------------------------- عملکرد کلمات کلیدی */

function KeywordsPanel({ siteId, days }: { siteId: string; days: number }) {
  const PAGE = 25;
  const [data, setData] = useState<ReportKeywordList | null>(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [scope, setScope] = useState<'all' | 'tracked'>('all');
  const [order, setOrder] = useState('clicks');
  const [dirn, setDirn] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    endpoints.reportKeywords(siteId, { days, q, scope, order, dir: dirn, limit: PAGE, offset: page * PAGE })
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) toast.error(e instanceof ApiError ? e.message : String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [siteId, days, q, scope, order, dirn, page]);

  const setSort = (k: string) => {
    if (order === k) setDirn(dirn === 'desc' ? 'asc' : 'desc');
    else { setOrder(k); setDirn(k === 'position' ? 'asc' : 'desc'); }
    setPage(0);
  };
  const arrow = (k: string) => (order === k ? (dirn === 'desc' ? ' ↓' : ' ↑') : '');
  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE));

  if (data?.status === 'NO_GSC_DATA') {
    return <EmptyState title='داده Search Console موجود نیست' description='بعد از اتصال و همگام‌سازی GSC، جدول عملکرد کلمات کلیدی اینجا ساخته می‌شود.' />;
  }
  return (
    <Card>
      <CardContent className='space-y-3 pt-4'>
        <div className='flex flex-wrap items-center gap-2'>
          <div className='bg-muted flex rounded-lg p-0.5' role='group' aria-label='محدوده کلمات'>
            <Button size='sm' variant={scope === 'all' ? 'default' : 'ghost'} className='px-2.5' onClick={() => { setScope('all'); setPage(0); }}>همه کوئری‌ها</Button>
            <Button size='sm' variant={scope === 'tracked' ? 'default' : 'ghost'} className='px-2.5' onClick={() => { setScope('tracked'); setPage(0); }}>کلمات اصلی (ردیابی‌شده)</Button>
          </div>
          <Input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder='جست‌وجوی کلمه کلیدی…' className='w-56' />
          {data?.window && <span className='text-muted-foreground text-xs' dir='ltr'>{data.window.from} → {data.window.to}</span>}
          <span className='text-muted-foreground ms-auto text-xs'>{fa.format(data?.total ?? 0)} کوئری</span>
        </div>
        {scope === 'tracked' && data?.status === 'OK' && data.total === 0 && (
          <p className='text-muted-foreground text-xs'>
            هنوز کلمه‌ای در «کلمات کلیدی» این سایت ثبت نشده یا در این بازه داده GSC ندارد — از صفحه{' '}
            <a className='underline underline-offset-2' href={`/dashboard/keywords?site=${encodeURIComponent(siteId)}`}>کلمات کلیدی</a> اضافه کنید.
          </p>
        )}
        <div className='overflow-x-auto rounded-md border'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>کلمه کلیدی</TableHead>
                <TableHead className='cursor-pointer select-none' onClick={() => setSort('position')}>جایگاه{arrow('position')}</TableHead>
                <TableHead>جایگاه قبلی</TableHead>
                <TableHead className='cursor-pointer select-none' onClick={() => setSort('change')}>تغییر{arrow('change')}</TableHead>
                <TableHead className='cursor-pointer select-none' onClick={() => setSort('clicks')}>کلیک{arrow('clicks')}</TableHead>
                <TableHead className='cursor-pointer select-none' onClick={() => setSort('impressions')}>نمایش{arrow('impressions')}</TableHead>
                <TableHead className='cursor-pointer select-none' onClick={() => setSort('ctr')}>CTR{arrow('ctr')}</TableHead>
                <TableHead>صفحه فرود</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && !data ? (
                <TableRow><TableCell colSpan={8} className='text-muted-foreground text-center'>در حال بارگیری…</TableCell></TableRow>
              ) : (data?.items ?? []).length === 0 ? (
                <TableRow><TableCell colSpan={8} className='text-muted-foreground text-center'>کوئری‌ای در این بازه پیدا نشد</TableCell></TableRow>
              ) : (
                data!.items.map((r) => (
                  <TableRow key={r.query}>
                    <TableCell className='font-medium'>{r.query}</TableCell>
                    <TableCell className='tabular-nums'>{pos(r.position)}</TableCell>
                    <TableCell className='text-muted-foreground tabular-nums'>{pos(r.prev_position)}</TableCell>
                    <TableCell className='tabular-nums'><ChangeCell change={r.change} /></TableCell>
                    <TableCell className='tabular-nums'>{num(r.clicks)}</TableCell>
                    <TableCell className='tabular-nums'>{num(r.impressions)}</TableCell>
                    <TableCell className='tabular-nums'>{pct(r.ctr)}</TableCell>
                    <TableCell dir='ltr' className='max-w-56 truncate text-xs' title={r.landing_page ?? ''}>{r.landing_page ?? '—'}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
        {pages > 1 && (
          <div className='flex items-center justify-between text-xs'>
            <Button size='sm' variant='outline' disabled={page === 0} onClick={() => setPage(page - 1)}>قبلی</Button>
            <span className='text-muted-foreground'>صفحه {fa.format(page + 1)} از {fa.format(pages)}</span>
            <Button size='sm' variant='outline' disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>بعدی</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ---------------------------------------------------------------- مشکلات */

function ProblemsPanel({ siteId, refreshKey }: { siteId: string; refreshKey: number }) {
  const [data, setData] = useState<ReportProblems | null>(null);
  const [severity, setSeverity] = useState('');
  const [category, setCategory] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    endpoints.reportProblems(siteId, { severity: severity || undefined, category: category || undefined })
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) toast.error(e instanceof ApiError ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [siteId, severity, category, refreshKey]);

  if (!data) return <LoadingState label='در حال بارگیری مشکلات…' rows={4} />;
  const groups = Object.entries(data.summary);
  if (groups.length === 0 && !severity && !category) {
    return <EmptyState title='مشکلی ثبت نشده است' description='آخرین تحلیل کراولر مشکلی برای این سایت پیدا نکرده، یا هنوز تحلیل اجرا نشده است.' />;
  }
  return (
    <Card>
      <CardContent className='space-y-3 pt-4'>
        <div className='flex flex-wrap gap-2'>
          <NativeSelect value={severity} onChange={(e) => setSeverity(e.target.value)} className='w-36' aria-label='شدت'>
            <NativeSelectOption value=''>همه شدت‌ها</NativeSelectOption>
            <NativeSelectOption value='high'>بحرانی</NativeSelectOption>
            <NativeSelectOption value='medium'>متوسط</NativeSelectOption>
            <NativeSelectOption value='low'>کم</NativeSelectOption>
          </NativeSelect>
          <NativeSelect value={category} onChange={(e) => setCategory(e.target.value)} className='w-44' aria-label='دسته'>
            <NativeSelectOption value=''>همه دسته‌ها</NativeSelectOption>
            {Object.entries(data.categories).map(([k, v]) => <NativeSelectOption key={k} value={k}>{v}</NativeSelectOption>)}
          </NativeSelect>
          <span className='text-muted-foreground ms-auto self-center text-xs'>منبع: کراولر / تحلیل داخلی — هر مشکل شواهد واقعی دارد</span>
        </div>
        <div className='space-y-2'>
          {groups.map(([type, gsum]) => {
            const items = data.items.filter((it) => it.problem_type === type);
            if (items.length === 0) return null;
            const sev = SEVERITY_FA[gsum.severity] ?? SEVERITY_FA.low;
            const isOpen = expanded === type;
            return (
              <div key={type} className='rounded-lg border'>
                <button type='button' className='flex w-full flex-wrap items-center gap-2 px-3 py-2.5 text-start' onClick={() => setExpanded(isOpen ? null : type)}>
                  <Badge className={sev.cls}>{sev.label}</Badge>
                  <span className='text-sm font-medium'>{gsum.title_fa}</span>
                  <Badge variant='outline'>{gsum.category_fa}</Badge>
                  <span className='text-muted-foreground ms-auto text-xs'>{fa.format(items.length)} صفحه {isOpen ? '▴' : '▾'}</span>
                </button>
                {isOpen && (
                  <div className='space-y-1 border-t px-3 py-2'>
                    {items.slice(0, 30).map((it, i) => (
                      <div key={i} className='flex items-center gap-2 text-xs'>
                        <a href={it.url ?? '#'} target='_blank' rel='noreferrer' dir='ltr' className='max-w-xl truncate underline-offset-2 hover:underline' title={it.url ?? ''}>{it.url}</a>
                        {it.related_url && <span className='text-muted-foreground truncate' dir='ltr'>↔ {it.related_url}</span>}
                      </div>
                    ))}
                    {items.length > 30 && <div className='text-muted-foreground text-xs'>و {fa.format(items.length - 30)} صفحه دیگر…</div>}
                  </div>
                )}
              </div>
            );
          })}
          {groups.length === 0 && <p className='text-muted-foreground py-6 text-center text-sm'>با این فیلتر مشکلی پیدا نشد</p>}
        </div>
      </CardContent>
    </Card>
  );
}

/* ---------------------------------------------------------------- فرصت‌ها */

function OpportunitiesPanel({ siteId, refreshKey }: { siteId: string; refreshKey: number }) {
  const [data, setData] = useState<ReportOpportunities | null>(null);
  const [type, setType] = useState('');

  useEffect(() => {
    let cancelled = false;
    endpoints.reportOpportunities(siteId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) toast.error(e instanceof ApiError ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [siteId, refreshKey]);

  if (!data) return <LoadingState label='در حال بارگیری فرصت‌ها…' rows={4} />;
  if (data.items.length === 0) {
    return <EmptyState title='فرصتی ثبت نشده است' description='بعد از همگام‌سازی GSC و اجرای تحلیل، فرصت‌های سئو (جایگاه ۴ تا ۱۵، CTR پایین و…) اینجا نمایش داده می‌شوند.' />;
  }
  const items = type ? data.items.filter((it) => it.opp_type === type) : data.items;
  return (
    <Card>
      <CardContent className='space-y-3 pt-4'>
        <div className='flex flex-wrap gap-1.5'>
          <button type='button' onClick={() => setType('')} className={`rounded-full border px-2.5 py-1 text-xs ${type === '' ? 'border-primary bg-primary/10' : 'hover:bg-muted'}`}>همه ({fa.format(data.items.length)})</button>
          {Object.entries(data.summary).map(([t, s]) => (
            <button key={t} type='button' onClick={() => setType(t)} className={`rounded-full border px-2.5 py-1 text-xs ${type === t ? 'border-primary bg-primary/10' : 'hover:bg-muted'}`}>
              {s.type_fa} ({fa.format(s.count)})
            </button>
          ))}
          <Button size='sm' variant='outline' className='ms-auto' nativeButton={false}
            render={<a href={`/dashboard/content-planner?site=${encodeURIComponent(siteId)}`} />}>
            ساخت محتوا از این فرصت‌ها در پلنر ←
          </Button>
        </div>
        <div className='overflow-x-auto rounded-md border'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>نوع فرصت</TableHead><TableHead>کوئری</TableHead><TableHead>صفحه</TableHead><TableHead>امتیاز</TableHead><TableHead>توضیح</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.slice(0, 100).map((it, i) => (
                <TableRow key={i}>
                  <TableCell className='text-xs'>{it.type_fa}</TableCell>
                  <TableCell className='text-sm'>{it.query ?? '—'}</TableCell>
                  <TableCell dir='ltr' className='max-w-52 truncate text-xs' title={it.url ?? ''}>{it.url ?? '—'}</TableCell>
                  <TableCell className='tabular-nums'>{num(it.score, 2)}</TableCell>
                  <TableCell className='text-muted-foreground max-w-72 truncate text-xs' title={it.reason ?? ''}>{it.reason ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ---------------------------------------------------------------- بک‌لینک‌ها */

const emptyBacklink = { source_url: '', target_url: '', anchor_text: '', link_type: 'generic', rel: 'follow', status: 'active' as const, notes: '' };

function BacklinksPanel({ siteId, onChanged }: { siteId: string; onChanged: () => void }) {
  const [data, setData] = useState<ReportBacklinks | null>(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<BacklinkRow | null>(null);
  const [form, setForm] = useState<Record<string, string>>({ ...emptyBacklink });
  const [saving, setSaving] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    endpoints.reportBacklinks(siteId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) toast.error(e instanceof ApiError ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [siteId, tick]);

  const openNew = () => { setEditing(null); setForm({ ...emptyBacklink }); setOpen(true); };
  const openEdit = (b: BacklinkRow) => {
    setEditing(b);
    setForm({ source_url: b.source_url, target_url: b.target_url, anchor_text: b.anchor_text ?? '', link_type: b.link_type, rel: b.rel ?? 'follow', status: b.status, notes: b.notes ?? '' });
    setOpen(true);
  };
  const save = async () => {
    setSaving(true);
    try {
      const body = { ...form, anchor_text: form.anchor_text || null, notes: form.notes || null };
      if (editing) await endpoints.updateReportBacklink(siteId, editing.id, body);
      else await endpoints.createReportBacklink(siteId, body);
      toast.success('ذخیره شد');
      setOpen(false); setTick((t) => t + 1); onChanged();
    } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
    finally { setSaving(false); }
  };
  const remove = async (b: BacklinkRow) => {
    if (!window.confirm('این بک‌لینک حذف شود؟')) return;
    try { await endpoints.deleteReportBacklink(siteId, b.id); setTick((t) => t + 1); onChanged(); }
    catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
  };

  if (!data) return <LoadingState label='در حال بارگیری بک‌لینک‌ها…' rows={3} />;
  return (
    <div className='space-y-3'>
      <div className='text-muted-foreground flex flex-wrap items-center gap-2 text-xs'>
        <Badge variant='outline'>{data.provider_note}</Badge>
        <span>مجموع: {fa.format(data.totals.total)}</span>
        <span>فعال: {fa.format(data.totals.active)}</span>
        <span>Follow: {fa.format(data.totals.follow)}</span>
        <span>Nofollow/Sponsored: {fa.format(data.totals.nofollow)}</span>
        <span>دامنه ارجاع‌دهنده: {fa.format(data.totals.referring_domains)}</span>
        <Button size='sm' className='ms-auto' onClick={openNew}>افزودن بک‌لینک</Button>
      </div>
      {data.items.length === 0 ? (
        <EmptyState title='هنوز بک‌لینکی ثبت نشده است' description='منبع بک‌لینک خارجی (Ahrefs و…) متصل نیست؛ می‌توانید بک‌لینک‌ها را دستی ثبت کنید — رپورتاژها تب جداگانه دارند.'
          action={<Button size='sm' onClick={openNew}>افزودن بک‌لینک</Button>} />
      ) : (
        <div className='overflow-x-auto rounded-md border'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>دامنه مبدأ</TableHead><TableHead>URL مبدأ</TableHead><TableHead>مقصد</TableHead><TableHead>انکر</TableHead>
                <TableHead>نوع</TableHead><TableHead>Rel</TableHead><TableHead>وضعیت</TableHead><TableHead>اولین مشاهده</TableHead><TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((b) => (
                <TableRow key={b.id}>
                  <TableCell dir='ltr' className='text-xs font-medium'>{b.source_domain}</TableCell>
                  <TableCell dir='ltr' className='max-w-48 truncate text-xs' title={b.source_url}>
                    <a href={b.source_url} target='_blank' rel='noreferrer' className='underline-offset-2 hover:underline'>{b.source_url}</a>
                  </TableCell>
                  <TableCell dir='ltr' className='max-w-44 truncate text-xs' title={b.target_url}>{b.target_url}</TableCell>
                  <TableCell className='max-w-40 truncate text-sm' title={b.anchor_text ?? ''}>{b.anchor_text ?? '—'}</TableCell>
                  <TableCell className='text-xs'>{({ reportage: 'رپورتاژ', guest_post: 'پست مهمان', natural: 'طبیعی' } as Record<string, string>)[b.link_type] ?? 'سایر'}</TableCell>
                  <TableCell className='text-xs' dir='ltr'>{b.rel ?? 'follow'}</TableCell>
                  <TableCell>
                    <Badge variant='outline' className={b.status === 'active' ? 'border-emerald-500/30 text-emerald-700 dark:text-emerald-300' : b.status === 'lost' ? 'border-red-500/30 text-red-700 dark:text-red-300' : ''}>
                      {b.status === 'active' ? 'فعال' : b.status === 'lost' ? 'ازدست‌رفته' : 'بررسی‌نشده'}
                    </Badge>
                  </TableCell>
                  <TableCell dir='ltr' className='text-xs'>{b.first_seen ?? '—'}</TableCell>
                  <TableCell className='space-x-1 whitespace-nowrap'>
                    <Button size='sm' variant='ghost' onClick={() => openEdit(b)}>ویرایش</Button>
                    <Button size='sm' variant='ghost' className='text-destructive' onClick={() => remove(b)}>حذف</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {data.top_anchors.length > 0 && (
        <Card>
          <CardHeader className='pb-2'><CardTitle className='text-sm'>پرتکرارترین انکرتکست‌ها</CardTitle></CardHeader>
          <CardContent className='flex flex-wrap gap-1.5'>
            {data.top_anchors.map((a) => (
              <Badge key={a.anchor_text} variant='secondary'>{a.anchor_text} <span className='text-muted-foreground ms-1'>×{fa.format(a.backlinks)}</span></Badge>
            ))}
          </CardContent>
        </Card>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent dir='rtl'>
          <DialogHeader><DialogTitle>{editing ? 'ویرایش بک‌لینک' : 'افزودن بک‌لینک'}</DialogTitle></DialogHeader>
          <div className='space-y-3'>
            <Field label='URL صفحه‌ای که به ما لینک داده' ltr value={form.source_url} onChange={(v) => setForm({ ...form, source_url: v })} placeholder='https://example-news.com/post' />
            <Field label='URL مقصد در سایت ما' ltr value={form.target_url} onChange={(v) => setForm({ ...form, target_url: v })} placeholder='https://oursite.com/service' />
            <Field label='انکرتکست' value={form.anchor_text} onChange={(v) => setForm({ ...form, anchor_text: v })} />
            <div className='space-y-1.5'>
              <Label>نوع بک‌لینک</Label>
              <NativeSelect value={form.link_type} onChange={(e) => setForm({ ...form, link_type: e.target.value })}>
                <NativeSelectOption value='reportage'>رپورتاژ</NativeSelectOption>
                <NativeSelectOption value='guest_post'>پست مهمان</NativeSelectOption>
                <NativeSelectOption value='natural'>طبیعی</NativeSelectOption>
                <NativeSelectOption value='generic'>سایر</NativeSelectOption>
              </NativeSelect>
            </div>
            <div className='grid grid-cols-2 gap-3'>
              <div className='space-y-1.5'>
                <Label>Rel</Label>
                <NativeSelect value={form.rel} onChange={(e) => setForm({ ...form, rel: e.target.value })}>
                  <NativeSelectOption value='follow'>follow</NativeSelectOption>
                  <NativeSelectOption value='nofollow'>nofollow</NativeSelectOption>
                  <NativeSelectOption value='sponsored'>sponsored</NativeSelectOption>
                  <NativeSelectOption value='ugc'>ugc</NativeSelectOption>
                </NativeSelect>
              </div>
              <div className='space-y-1.5'>
                <Label>وضعیت</Label>
                <NativeSelect value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  <NativeSelectOption value='active'>فعال</NativeSelectOption>
                  <NativeSelectOption value='lost'>ازدست‌رفته</NativeSelectOption>
                  <NativeSelectOption value='unverified'>بررسی‌نشده</NativeSelectOption>
                </NativeSelect>
              </div>
            </div>
            <Field label='یادداشت' value={form.notes} onChange={(v) => setForm({ ...form, notes: v })} />
            <div className='flex justify-end gap-2'>
              <Button variant='outline' onClick={() => setOpen(false)}>انصراف</Button>
              <Button onClick={save} disabled={saving || !form.source_url || !form.target_url}>{saving ? 'در حال ذخیره…' : 'ذخیره'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ---------------------------------------------------------------- رپورتاژها */

const emptyReportage = { article_url: '', target_url: '', anchor_text: '', target_keyword: '', publication_date: '', link_type: 'follow', cost: '', status: 'published', notes: '' };

function ReportagesPanel({ siteId, onChanged }: { siteId: string; onChanged: () => void }) {
  const [data, setData] = useState<ReportReportages | null>(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ReportageRow | null>(null);
  const [form, setForm] = useState<Record<string, string>>({ ...emptyReportage });
  const [saving, setSaving] = useState(false);
  const [verifying, setVerifying] = useState<number | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    endpoints.reportReportages(siteId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) toast.error(e instanceof ApiError ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [siteId, tick]);

  const openNew = () => { setEditing(null); setForm({ ...emptyReportage }); setOpen(true); };
  const openEdit = (r: ReportageRow) => {
    setEditing(r);
    setForm({ article_url: r.article_url, target_url: r.target_url, anchor_text: r.anchor_text ?? '', target_keyword: r.target_keyword ?? '',
              publication_date: r.publication_date ?? '', link_type: r.link_type ?? 'follow', cost: r.cost != null ? String(r.cost) : '',
              status: r.status, notes: r.notes ?? '' });
    setOpen(true);
  };
  const save = async () => {
    setSaving(true);
    try {
      const body = { article_url: form.article_url, target_url: form.target_url, anchor_text: form.anchor_text || null,
                     target_keyword: form.target_keyword || null, publication_date: form.publication_date || null,
                     link_type: form.link_type || null, cost: form.cost ? Number(form.cost) : null, status: form.status, notes: form.notes || null };
      if (editing) await endpoints.updateReportage(siteId, editing.id, body);
      else await endpoints.createReportage(siteId, body);
      toast.success('ذخیره شد');
      setOpen(false); setTick((t) => t + 1); onChanged();
    } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
    finally { setSaving(false); }
  };
  const remove = async (r: ReportageRow) => {
    if (!window.confirm('این رپورتاژ حذف شود؟')) return;
    try { await endpoints.deleteReportage(siteId, r.id); setTick((t) => t + 1); onChanged(); }
    catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
  };
  const verify = async (r: ReportageRow) => {
    setVerifying(r.id);
    try {
      const out = await endpoints.verifyReportage(siteId, r.id);
      if (out.status) toast.success(`نتیجه بررسی: ${REPORTAGE_STATUS_FA[out.status]?.label ?? out.status}`);
      else toast.error(`بررسی ناموفق: ${out.error ?? 'خطای نامشخص'}`);
      setTick((t) => t + 1); onChanged();
    } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
    finally { setVerifying(null); }
  };

  if (!data) return <LoadingState label='در حال بارگیری رپورتاژها…' rows={3} />;
  return (
    <div className='space-y-3'>
      <div className='text-muted-foreground flex flex-wrap items-center gap-2 text-xs'>
        <span>مجموع: {fa.format(data.totals.total)}</span>
        <span className='text-emerald-600 dark:text-emerald-400'>لینک سالم: {fa.format(data.totals.link_found)}</span>
        <span className='text-red-600 dark:text-red-400'>مشکل‌دار: {fa.format(data.totals.link_missing)}</span>
        {data.totals.cost_total > 0 && <span>هزینه کل: {fa.format(data.totals.cost_total)} تومان</span>}
        <Button size='sm' className='ms-auto' onClick={openNew}>افزودن رپورتاژ</Button>
      </div>
      {data.items.length === 0 ? (
        <EmptyState title='هنوز رپورتاژی برای این سایت ثبت نشده است' description='رپورتاژهای خریداری‌شده را ثبت کنید تا وضعیت لینک هرکدام به‌صورت خودکار بررسی و پایش شود.'
          action={<Button size='sm' onClick={openNew}>افزودن رپورتاژ</Button>} />
      ) : (
        <div className='overflow-x-auto rounded-md border'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>سایت منتشرکننده</TableHead><TableHead>مقاله</TableHead><TableHead>مقصد</TableHead><TableHead>انکر / کلمه هدف</TableHead>
                <TableHead>تاریخ انتشار</TableHead><TableHead>هزینه</TableHead><TableHead>وضعیت لینک</TableHead><TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((r) => {
                const st = REPORTAGE_STATUS_FA[r.status] ?? REPORTAGE_STATUS_FA.pending;
                return (
                  <TableRow key={r.id}>
                    <TableCell dir='ltr' className='text-xs font-medium'>{r.publication_domain}</TableCell>
                    <TableCell dir='ltr' className='max-w-44 truncate text-xs' title={r.article_url}>
                      <a href={r.article_url} target='_blank' rel='noreferrer' className='underline-offset-2 hover:underline'>{r.article_url}</a>
                    </TableCell>
                    <TableCell dir='ltr' className='max-w-40 truncate text-xs' title={r.target_url}>{r.target_url}</TableCell>
                    <TableCell className='max-w-40 text-xs'>
                      <div className='truncate' title={r.anchor_text ?? ''}>{r.anchor_text ?? '—'}</div>
                      {r.target_keyword && <div className='text-muted-foreground truncate'>{r.target_keyword}</div>}
                    </TableCell>
                    <TableCell dir='ltr' className='text-xs'>{r.publication_date ?? '—'}</TableCell>
                    <TableCell className='text-xs tabular-nums'>{r.cost != null ? fa.format(r.cost) : '—'}</TableCell>
                    <TableCell>
                      <Badge variant='outline' className={st.cls}>{st.label}</Badge>
                      {r.verified_rel && r.verified_rel !== 'follow' && <div className='text-muted-foreground mt-0.5 text-[10px]' dir='ltr'>{r.verified_rel}</div>}
                      {r.last_verified_at && <div className='text-muted-foreground mt-0.5 text-[10px]'>بررسی: {ago(r.last_verified_at)}</div>}
                    </TableCell>
                    <TableCell className='space-x-1 whitespace-nowrap'>
                      <Button size='sm' variant='outline' disabled={verifying === r.id} onClick={() => verify(r)}>
                        {verifying === r.id ? 'در حال بررسی…' : 'بررسی لینک'}
                      </Button>
                      <Button size='sm' variant='ghost' onClick={() => openEdit(r)}>ویرایش</Button>
                      <Button size='sm' variant='ghost' className='text-destructive' onClick={() => remove(r)}>حذف</Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent dir='rtl' className='max-h-[85vh] overflow-y-auto'>
          <DialogHeader>
            <DialogTitle>{editing ? 'ویرایش رپورتاژ' : 'افزودن رپورتاژ'}</DialogTitle>
            <DialogDescription>بعد از ثبت، با دکمه «بررسی لینک» وضعیت واقعی لینک داخل مقاله بررسی می‌شود.</DialogDescription>
          </DialogHeader>
          <div className='space-y-3'>
            <Field label='URL مقاله رپورتاژ' ltr value={form.article_url} onChange={(v) => setForm({ ...form, article_url: v })} placeholder='https://news-site.com/article' />
            <Field label='URL مقصد در سایت ما' ltr value={form.target_url} onChange={(v) => setForm({ ...form, target_url: v })} placeholder='https://oursite.com/service' />
            <div className='grid grid-cols-2 gap-3'>
              <Field label='انکرتکست' value={form.anchor_text} onChange={(v) => setForm({ ...form, anchor_text: v })} />
              <Field label='کلمه کلیدی هدف' value={form.target_keyword} onChange={(v) => setForm({ ...form, target_keyword: v })} />
            </div>
            <div className='grid grid-cols-2 gap-3'>
              <Field label='تاریخ انتشار (میلادی)' ltr value={form.publication_date} onChange={(v) => setForm({ ...form, publication_date: v })} placeholder='2026-08-01' />
              <Field label='هزینه (تومان)' ltr value={form.cost} onChange={(v) => setForm({ ...form, cost: v.replace(/[^0-9]/g, '') })} />
            </div>
            <div className='grid grid-cols-2 gap-3'>
              <div className='space-y-1.5'>
                <Label>نوع لینک (توافق‌شده)</Label>
                <NativeSelect value={form.link_type} onChange={(e) => setForm({ ...form, link_type: e.target.value })}>
                  <NativeSelectOption value='follow'>follow</NativeSelectOption>
                  <NativeSelectOption value='nofollow'>nofollow</NativeSelectOption>
                  <NativeSelectOption value='sponsored'>sponsored</NativeSelectOption>
                </NativeSelect>
              </div>
              <div className='space-y-1.5'>
                <Label>وضعیت</Label>
                <NativeSelect value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  <NativeSelectOption value='pending'>در انتظار انتشار</NativeSelectOption>
                  <NativeSelectOption value='published'>منتشرشده</NativeSelectOption>
                </NativeSelect>
              </div>
            </div>
            <Field label='یادداشت' value={form.notes} onChange={(v) => setForm({ ...form, notes: v })} />
            <div className='flex justify-end gap-2'>
              <Button variant='outline' onClick={() => setOpen(false)}>انصراف</Button>
              <Button onClick={save} disabled={saving || !form.article_url || !form.target_url}>{saving ? 'در حال ذخیره…' : 'ذخیره'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, ltr }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; ltr?: boolean }) {
  return (
    <div className='space-y-1.5'>
      <Label>{label}</Label>
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} dir={ltr ? 'ltr' : undefined} />
    </div>
  );
}
