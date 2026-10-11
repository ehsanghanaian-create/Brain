'use client';

import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { UrlDossier } from '@/features/sites/components/url-dossier';
import { endpoints, type PortfolioSite, type SalesPath, type Site } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';
import { IconArrowLeft, IconChartBar, IconExternalLink, IconRefresh, IconShoppingBag, IconTargetArrow } from '@tabler/icons-react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useMemo, useState } from 'react';

const SalesTrend = dynamic(() => import('./sales-trend').then((module) => module.SalesTrend), { ssr: false });
const fa = new Intl.NumberFormat('fa-IR');
const percent = new Intl.NumberFormat('fa-IR', { style: 'percent', maximumFractionDigits: 1 });
const labels = { product: 'صفحات محصول', category: 'صفحات دسته‌بندی', shop: 'فروشگاه' } as const;

function ageDays(day: string | null) {
  if (!day) return null;
  const value = Date.parse(`${day}T00:00:00Z`);
  return Number.isNaN(value) ? null : Math.max(0, Math.floor((Date.now() - value) / 86_400_000));
}

function pagePath(url: string) {
  try { return new URL(url).pathname; } catch { return url; }
}

function PageRow({ item, siteId, onInspect }: { item: SalesPath['top_pages'][number]; siteId: string; onInspect: () => void }) {
  const path = pagePath(item.url);
  return <div className='grid gap-3 border-b border-border/60 px-3 py-3 last:border-0 hover:bg-muted/30 sm:grid-cols-[minmax(0,1fr)_105px_105px_130px] sm:items-center'>
    <div className='min-w-0'><div className='flex flex-wrap items-center gap-2'><Badge variant='outline'>{labels[item.kind]}</Badge>{item.open_issues > 0 && <Badge variant='destructive'>{fa.format(item.open_issues)} مسئله باز</Badge>}{item.new_keyword_opportunities > 0 && <Badge variant='secondary'>{fa.format(item.new_keyword_opportunities)} فرصت کلمه</Badge>}</div><p className='mt-1 truncate text-sm font-medium' dir='ltr' title={item.url}>{path}</p></div>
    <div><strong className='block tabular-nums'>{fa.format(item.clicks)}</strong><span className='text-xs text-muted-foreground'>کلیک مشاهده‌شده</span></div>
    <div><strong className='block tabular-nums'>{fa.format(item.impressions)}</strong><span className='text-xs text-muted-foreground'>نمایش</span></div>
    <div className='flex flex-wrap gap-1'><Button size='sm' variant='outline' onClick={onInspect}>پرونده صفحه</Button>{item.open_issues > 0 && <Link href={`/dashboard/sites/${encodeURIComponent(siteId)}?tab=issues`} className={cn(buttonVariants({ variant: 'ghost', size: 'sm' }), 'text-xs')}>مسائل<IconArrowLeft className='size-3.5' /></Link>}</div>
  </div>;
}

export function SalesPathDashboard({ sites, portfolio, initialSiteId }: { sites: Site[]; portfolio: PortfolioSite[]; initialSiteId: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [days, setDays] = useState(28);
  const [selectedUrl, setSelectedUrl] = useState<string | null>(null);
  const site = useMemo(() => portfolio.find((item) => item.site_id === siteId), [portfolio, siteId]);
  const query = useQuery({ queryKey: ['sales-path', siteId, days], queryFn: () => endpoints.salesPath(siteId, days), staleTime: 60_000, enabled: !!siteId });
  const measurementQuery = useQuery({ queryKey: ['sales-measurement', siteId, days], queryFn: () => endpoints.salesMeasurement(siteId, days), staleTime: 15 * 60_000, enabled: !!siteId });
  const data = query.data;
  const measurement = measurementQuery.data;
  const totalClicks = data?.stages.reduce((sum, item) => sum + item.clicks, 0) ?? 0;
  const observedPages = data?.stages.reduce((sum, item) => sum + item.pages_observed, 0) ?? 0;
  const inventoryPages = data ? Object.values(data.inventory).reduce((sum, count) => sum + count, 0) : 0;
  const stale = ageDays(data?.latest_gsc_date ?? null);
  const delta = data?.previous_total_clicks != null && data.previous_total_clicks > 0 ? (totalClicks - data.previous_total_clicks) / data.previous_total_clicks : null;
  const topIssue = data?.top_pages.find((item) => item.open_issues > 0);
  const topOpportunity = data?.top_pages.find((item) => item.new_keyword_opportunities > 0);
  const maxChannelSessions = Math.max(1, ...(measurement?.channels.map((item) => item.sessions) ?? []));

  return <div className='space-y-5'>
    <section className='overflow-hidden rounded-3xl border border-primary/20 bg-gradient-to-bl from-primary/10 via-card to-amber-500/[0.07] p-5 shadow-sm sm:p-7'>
      <div className='flex flex-col justify-between gap-4 lg:flex-row lg:items-start'><div className='max-w-3xl'><span className='inline-flex items-center gap-2 text-xs font-semibold text-primary'><IconTargetArrow className='size-4' aria-hidden='true' /> هدف تجاری سایت</span><h2 className='mt-2 text-2xl font-bold tracking-tight sm:text-3xl'>مسیر رشد فروش از جست‌وجو</h2><p className='mt-2 text-sm leading-7'>{site?.mission.objective || 'هدف فروش برای این سایت هنوز ثبت نشده است.'}</p><p className='mt-1 text-xs leading-6 text-muted-foreground'>{site?.mission.success_metric || 'معیار موفقیت را در صفحهٔ سایت ثبت کنید.'}</p></div><div className='flex flex-wrap gap-2'><NativeSelect aria-label='انتخاب سایت برای مسیر فروش' value={siteId} onChange={(event) => { setSiteId(event.target.value); setSelectedUrl(null); }} className='min-w-44 bg-background/80'>{sites.map((item) => <NativeSelectOption key={item.site_id} value={item.site_id}>{item.name}</NativeSelectOption>)}</NativeSelect><NativeSelect aria-label='بازه مشاهده جست‌وجو' value={String(days)} onChange={(event) => setDays(Number(event.target.value))} className='bg-background/80'><NativeSelectOption value='7'>۷ روز</NativeSelectOption><NativeSelectOption value='28'>۲۸ روز</NativeSelectOption><NativeSelectOption value='90'>۹۰ روز</NativeSelectOption></NativeSelect><Button variant='outline' onClick={() => { void query.refetch(); void measurementQuery.refetch(); }} disabled={query.isFetching || measurementQuery.isFetching}><IconRefresh className={cn('size-4', (query.isFetching || measurementQuery.isFetching) && 'animate-spin')} />تازه‌سازی</Button></div></div>
      <div className='mt-4 flex flex-wrap items-center gap-2 border-t border-border/60 pt-4 text-xs text-muted-foreground'><Badge variant='secondary'>منبع: ردیف‌های مشاهده‌شده Search Console</Badge><span>آخرین روز: {data?.latest_gsc_date ?? 'ناموجود'}</span>{stale != null && stale > 4 && <Badge variant='destructive'>داده {fa.format(stale)} روز قدیمی است</Badge>}<span>کلیک جست‌وجو به معنی سفارش نیست.</span></div>
    </section>
    {query.isError && <div role='alert' className='rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive'>خواندن مسیر فروش ناموفق بود: {String(query.error)}</div>}
    {query.isLoading && <div role='status' className='h-72 animate-pulse rounded-2xl border bg-muted/30' />}
    {data && <>
      <section className='grid gap-3 md:grid-cols-3' aria-label='شاخص‌های مسیر فروش'>
        <Card className='border-primary/20 bg-primary/[0.04]'><CardContent className='p-5'><span className='text-xs text-muted-foreground'>کلیک صفحات تجاری · {fa.format(days)} روز تا آخرین داده</span><strong className='mt-2 block text-3xl tabular-nums'>{data.latest_gsc_date ? fa.format(totalClicks) : '—'}</strong><p className='mt-1 text-xs text-muted-foreground'>{delta == null ? 'دورهٔ قبل برای مقایسهٔ معتبر ثبت نشده' : `${delta >= 0 ? 'افزایش' : 'کاهش'} ${percent.format(Math.abs(delta))} نسبت به دورهٔ قبلِ مشاهده‌شده`}</p></CardContent></Card>
        <Card><CardContent className='p-5'><span className='text-xs text-muted-foreground'>صفحات تجاری با ردیف GSC</span><strong className='mt-2 block text-3xl tabular-nums'>{fa.format(observedPages)} <small className='text-base text-muted-foreground'>/ {fa.format(inventoryPages)}</small></strong><p className='mt-1 text-xs text-muted-foreground'>موجودی شناخته‌شده از خزش و وردپرس؛ نبود ردیف معادل صفر نیست.</p></CardContent></Card>
        <Card className='border-amber-500/25 bg-amber-500/[0.05]'><CardContent className='p-5'><span className='text-xs text-muted-foreground'>GA4 · کانال Organic Search</span><strong className='mt-2 block text-xl'>{measurementQuery.isLoading ? 'در حال خواندن…' : measurement?.status === 'reported' && measurement.organic_search ? `${fa.format(measurement.organic_search.sessions)} نشست · ${fa.format(measurement.organic_search.transactions)} تراکنش ثبت‌شده` : 'گزارش در دسترس نیست'}</strong><p className='mt-1 text-xs leading-5 text-muted-foreground'>{measurement?.status === 'reported' && measurement.organic_search ? `درآمد گزارش‌شده: ${fa.format(measurement.organic_search.purchase_revenue)} ${measurement.currency ?? 'با واحد پول نامشخص'}. صحت ثبت خرید هنوز تأیید نشده؛ صفر GA4 به معنی صفر فروش واقعی نیست.` : 'برای سنجش فروش، اتصال GA4 و صحت ثبت purchase و revenue باید بررسی شود.'}</p></CardContent></Card>
      </section>
      {measurement?.status === 'reported' && measurement.channels.length > 0 && <Card><CardHeader><CardTitle className='text-base'>ورودی کانال‌ها در GA4</CardTitle><p className='text-xs text-muted-foreground'>نشست‌ها بر اساس گروه کانال پیش‌فرضِ سشن؛ تراکنش گزارش‌شده کنار هر کانال آمده است.</p></CardHeader><CardContent className='grid gap-3 sm:grid-cols-2 xl:grid-cols-3'>{measurement.channels.map((item) => <div key={item.channel} className={cn('rounded-xl border p-3', item.channel === 'Organic Search' && 'border-primary/40 bg-primary/[0.05]')}><div className='flex items-center justify-between gap-2 text-sm'><strong dir='ltr'>{item.channel}</strong><span className='tabular-nums'>{fa.format(item.sessions)} نشست</span></div><div className='mt-2 h-1.5 overflow-hidden rounded-full bg-muted'><div className='h-full rounded-full bg-primary' style={{ width: `${(item.sessions / maxChannelSessions) * 100}%` }} /></div><p className='mt-1 text-xs text-muted-foreground'>{fa.format(item.transactions)} تراکنش در GA4</p></div>)}</CardContent></Card>}
      <section className='grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(290px,1fr)]'>
        <Card className='min-w-0'><CardHeader><div className='flex flex-wrap items-start justify-between gap-2'><div><CardTitle className='flex items-center gap-2 text-base'><IconChartBar className='size-5 text-primary' />روند تقاضای تجاری</CardTitle><p className='mt-1 text-xs text-muted-foreground'>کلیک روزانهٔ مشاهده‌شده برای محصول، دسته‌بندی و فروشگاه</p></div><Badge variant='outline'>{data.daily.length} روز دارای ردیف</Badge></div></CardHeader><CardContent>{data.daily.length >= 4 ? <SalesTrend daily={data.daily} /> : <p className='flex min-h-40 items-center justify-center rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground'>برای نمودار روند، دست‌کم چهار روز دارای داده لازم است.</p>}<div className='mt-3 flex flex-wrap gap-4 text-xs'>{(['product', 'category', 'shop'] as const).map((kind, index) => <span key={kind} className='flex items-center gap-1.5'><span className='size-2.5 rounded-sm' style={{ backgroundColor: `var(--chart-${index + 1})` }} />{labels[kind]}</span>)}</div><details className='mt-4 text-xs'><summary className='cursor-pointer font-medium'>جدول دادهٔ نمودار</summary><div className='mt-2 max-h-48 overflow-auto rounded-lg border'><table className='w-full text-right'><thead><tr className='border-b bg-muted/30'><th className='p-2'>روز</th><th className='p-2'>محصول</th><th className='p-2'>دسته‌بندی</th><th className='p-2'>فروشگاه</th></tr></thead><tbody>{data.daily.map((row) => <tr key={row.date} className='border-b last:border-0'><td className='p-2' dir='ltr'>{row.date}</td><td className='p-2'>{fa.format(row.product)}</td><td className='p-2'>{fa.format(row.category)}</td><td className='p-2'>{fa.format(row.shop)}</td></tr>)}</tbody></table></div></details></CardContent></Card>
        <Card><CardHeader><CardTitle className='text-base'>کدام بخش ورودی می‌آورد؟</CardTitle><p className='text-xs text-muted-foreground'>مقایسهٔ صفحات تجاری در همین بازه؛ مبنای تصمیم، کلیک و نمایش مشاهده‌شده است.</p></CardHeader><CardContent className='space-y-4'>{data.stages.map((stage) => <div key={stage.kind}><div className='flex items-center justify-between gap-2 text-sm'><span>{labels[stage.kind]}</span><strong>{fa.format(stage.clicks)} کلیک</strong></div><div className='mt-1.5 h-2 overflow-hidden rounded-full bg-muted'><div className='h-full rounded-full bg-primary transition-[width] duration-300 motion-reduce:transition-none' style={{ width: `${totalClicks ? (stage.clicks / totalClicks) * 100 : 0}%` }} /></div><p className='mt-1 text-xs text-muted-foreground'>{fa.format(stage.impressions)} نمایش · {fa.format(stage.pages_observed)} صفحه دارای ردیف</p></div>)}{!data.stages.length && <p className='text-sm text-muted-foreground'>دادهٔ GSC برای مقایسه ثبت نشده است.</p>}</CardContent></Card>
      </section>
      <section className='grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(290px,1fr)]'>
        <Card className='min-w-0'><CardHeader><CardTitle className='flex items-center gap-2 text-base'><IconShoppingBag className='size-5 text-primary' />صفحات تجاری برای بررسی</CardTitle><p className='text-xs text-muted-foreground'>مرتب‌شده با تعداد نمایش مشاهده‌شده؛ روی هر ردیف پرونده و مسئلهٔ همان صفحه را باز کنید.</p></CardHeader><CardContent className='p-0'>{data.top_pages.length ? data.top_pages.map((item) => <PageRow key={item.url} item={item} siteId={siteId} onInspect={() => setSelectedUrl(selectedUrl === item.url ? null : item.url)} />) : <p className='p-5 text-sm text-muted-foreground'>برای صفحات تجاری ردیف GSC ثبت نشده است؛ وضعیت اتصال و تازگی داده را بررسی کنید.</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle className='text-base'>قدم‌های پیشنهادی بعدی</CardTitle><p className='text-xs text-muted-foreground'>هر قدم به داده یا صفحهٔ عملیاتی مربوط وصل است.</p></CardHeader><CardContent className='space-y-3 text-sm'><div className='rounded-xl border bg-muted/20 p-3'><strong>۱. سنجش خرید را کامل کنید</strong><p className='mt-1 text-xs leading-6 text-muted-foreground'>برای فهمیدن اثر سئو بر فروش، رویداد purchase، درآمد و کانال ورود باید در یک گزارش معتبر جمع شوند.</p><Link href={`/dashboard/sites/${encodeURIComponent(siteId)}?tab=integrations`} className='mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline'>بررسی اتصال‌ها<IconArrowLeft className='size-3.5' /></Link></div><div className='rounded-xl border bg-muted/20 p-3'><strong>۲. مسئلهٔ صفحهٔ پرنمایش را بررسی کنید</strong><p className='mt-1 text-xs leading-6 text-muted-foreground'>{topIssue ? `${pagePath(topIssue.url)} · ${fa.format(topIssue.open_issues)} مسئله باز` : 'در ده صفحهٔ تجاری پرنمایش، مسئلهٔ باز ثبت نشده؛ پوشش خزش را نیز بررسی کنید.'}</p>{topIssue && <Button variant='link' size='sm' className='px-0' onClick={() => setSelectedUrl(topIssue.url)}>پرونده صفحه<IconArrowLeft className='size-3.5' /></Button>}</div><div className='rounded-xl border bg-muted/20 p-3'><strong>۳. فرصت کلمه را به صفحه وصل کنید</strong><p className='mt-1 text-xs leading-6 text-muted-foreground'>{topOpportunity ? `${pagePath(topOpportunity.url)} · ${fa.format(topOpportunity.new_keyword_opportunities)} فرصت جدید` : 'برای این ده صفحه فرصت کلمه ثبت نشده است.'}</p><Link href={`/dashboard/keywords?site=${encodeURIComponent(siteId)}&tab=opps`} className='mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline'>فرصت‌های کلمه<IconArrowLeft className='size-3.5' /></Link></div></CardContent></Card>
      </section>
      {selectedUrl && <div id='sales-page-dossier'><UrlDossier siteId={siteId} url={selectedUrl} onClose={() => setSelectedUrl(null)} /></div>}
      <div className='flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-muted/20 px-4 py-3 text-xs text-muted-foreground'><span>دامنهٔ داده: فقط ردیف‌های برترِ مشاهده‌شده در GSC. روز یا صفحهٔ غایب، صفر ترافیک نیست. این نمودار سفارش، درآمد یا انتساب قطعی فروش را نشان نمی‌دهد.</span><Link href={`/dashboard/graph?site=${encodeURIComponent(siteId)}`} className='inline-flex items-center gap-1 font-medium text-primary hover:underline'>نقشه روابط صفحات<IconExternalLink className='size-3.5' /></Link></div>
    </>}
  </div>;
}
