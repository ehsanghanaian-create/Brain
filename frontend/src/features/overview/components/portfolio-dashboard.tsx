'use client';

import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { endpoints, type Health, type PortfolioOverview, type PortfolioSite, type PortfolioSiteState } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import {
  IconAlertTriangle, IconArrowLeft, IconBolt, IconBrandWordpress, IconChartDots3, IconCircleCheck,
  IconClock, IconDatabase, IconFileText, IconLink, IconNetwork, IconPlus, IconSearch, IconSparkles, IconWorld
} from '@tabler/icons-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';
import { toast } from 'sonner';

const fa = new Intl.NumberFormat('fa-IR');
const TYPE_FA: Record<string, string> = {
  SITE: 'سایت', PAGE: 'صفحه', POST: 'نوشته', CATEGORY: 'دسته', TAG: 'برچسب', BRAND: 'برند', MODEL: 'مدل',
  SERVICE: 'خدمت', LOCATION: 'مکان', QUERY: 'کوئری', SCHEMA: 'اسکیما', SEO_PROBLEM: 'مشکل سئو',
  SEO_OPPORTUNITY: 'فرصت سئو', KEYWORD: 'کلمه کلیدی', TOPIC: 'موضوع', CONTENT: 'محتوا'
};

const STATE: Record<PortfolioSiteState, { label: string; dot: string; badge: string }> = {
  ready: { label: 'آماده', dot: 'bg-emerald-500', badge: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' },
  running: { label: 'در حال پردازش', dot: 'bg-sky-500 animate-pulse', badge: 'border-sky-500/25 bg-sky-500/10 text-sky-700 dark:text-sky-300' },
  attention: { label: 'نیازمند بررسی', dot: 'bg-rose-500', badge: 'border-rose-500/25 bg-rose-500/10 text-rose-700 dark:text-rose-300' },
  partial: { label: 'راه‌اندازی ناقص', dot: 'bg-amber-500', badge: 'border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300' },
  not_started: { label: 'شروع نشده', dot: 'bg-muted-foreground/50', badge: 'border-border bg-muted/70 text-muted-foreground' }
};

function formatDate(value: string | null | undefined) {
  if (!value) return 'هنوز اجرا نشده';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'زمان نامشخص';
  return new Intl.DateTimeFormat('fa-IR', {
    timeZone: 'Asia/Tehran', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  }).format(date);
}

function domain(url: string) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
}

function siteNextAction(site: PortfolioSite) {
  if (site.next_action) return site.next_action;
  if (site.state === 'attention') return 'بررسی خطای اتصال';
  if (site.state === 'partial') return 'تکمیل راه‌اندازی داده';
  if (site.state === 'not_started') return 'شروع همگام‌سازی';
  if (site.state === 'running') return 'در حال پردازش';
  return 'مرور فرصت‌های جدید';
}

function siteStateReason(site: PortfolioSite) {
  if (site.state_reason) return site.state_reason;
  if (site.latest_sync?.errors?.length) return site.latest_sync.errors[0];
  if (site.state === 'ready') return 'محتوا و گراف دانش این سایت آماده استفاده است.';
  if (site.state === 'partial') return 'بخشی از داده‌ها هنوز نیاز به تکمیل دارد.';
  if (site.state === 'not_started') return 'همگام‌سازی داده برای این سایت هنوز شروع نشده است.';
  return 'اتصال یا آخرین اجرای این سایت باید بررسی شود.';
}

function StateBadge({ state }: { state: PortfolioSiteState }) {
  const item = STATE[state];
  return <Badge variant='outline' className={cn('h-6 gap-1.5 px-2.5', item.badge)}><span aria-hidden='true' className={cn('size-1.5 rounded-full', item.dot)} />{item.label}</Badge>;
}

function MetricCard({ title, value, description, icon: Icon, iconClass, lineClass, footer }: {
  title: string; value: number; description: string; icon: typeof IconWorld; iconClass: string; lineClass: string; footer: React.ReactNode;
}) {
  return (
    <Card className='relative overflow-hidden border-border/70 shadow-sm'>
      <div className={cn('absolute inset-x-0 top-0 h-0.5', lineClass)} />
      <CardHeader className='flex-row items-start justify-between gap-3 pb-2'>
        <div className='space-y-1'><CardDescription className='font-medium'>{title}</CardDescription><CardTitle className='text-3xl font-bold tracking-tight tabular-nums'>{fa.format(value)}</CardTitle></div>
        <div className={cn('flex size-10 items-center justify-center rounded-xl', iconClass)}><Icon className='size-5' aria-hidden='true' /></div>
      </CardHeader>
      <CardContent className='space-y-3'><p className='text-muted-foreground min-h-10 text-xs leading-5'>{description}</p><div className='border-border/70 border-t pt-3 text-xs'>{footer}</div></CardContent>
    </Card>
  );
}

function SetupCoverage({ site }: { site: PortfolioSite }) {
  return <div className='min-w-28 space-y-1.5'><div className='flex items-center justify-between gap-3 text-xs'><span className='text-muted-foreground'>پوشش داده</span><span className='font-semibold tabular-nums'>{fa.format(site.setup_progress)}٪</span></div><Progress value={site.setup_progress} aria-label={`پوشش داده ${site.name}`} className='h-1.5' /></div>;
}

function SiteTable({ sites }: { sites: PortfolioSite[] }) {
  if (!sites.length) return <div className='flex min-h-48 flex-col items-center justify-center gap-2 text-center'><IconSearch className='text-muted-foreground size-7' aria-hidden='true' /><p className='font-medium'>سایتی با این فیلتر پیدا نشد</p><p className='text-muted-foreground text-sm'>عبارت جست‌وجو یا وضعیت انتخاب‌شده را تغییر دهید.</p></div>;
  return (
    <>
      <div className='space-y-2 py-3 md:hidden'>
        {sites.map((site) => (
          <Link key={site.site_id} href={`/dashboard/sites/${site.site_id}`} className='block rounded-xl border border-border/70 p-3 outline-none transition-colors hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring'>
            <div className='flex items-start justify-between gap-3'><span className='min-w-0'><span className='block truncate font-semibold'>{site.name}</span><span className='text-muted-foreground mt-0.5 block truncate text-xs' dir='ltr'>{domain(site.canonical_url)}</span></span><StateBadge state={site.state} /></div>
            <p className='text-muted-foreground mt-2 text-xs leading-5'>{siteStateReason(site)}</p>
            <div className='my-3'><SetupCoverage site={site} /></div>
            <div className='grid grid-cols-3 gap-2 text-center text-xs'><span className='rounded-lg bg-muted/60 p-2'><strong className='block text-sm tabular-nums'>{fa.format(site.counts.content)}</strong><span className='text-muted-foreground'>محتوا</span></span><span className='rounded-lg bg-muted/60 p-2'><strong className='block text-sm tabular-nums'>{fa.format(site.counts.graph_nodes)}</strong><span className='text-muted-foreground'>گره</span></span><span className='rounded-lg bg-muted/60 p-2'><strong className='block text-sm tabular-nums'>{fa.format(site.counts.new_link_suggestions)}</strong><span className='text-muted-foreground'>فرصت</span></span></div>
            <div className='mt-3 border-t pt-2 text-[11px]'><div className='flex items-center justify-between'><span className='text-muted-foreground'>اقدام بعدی</span><span className='font-medium'>{siteNextAction(site)}</span></div><div className='text-muted-foreground mt-1 flex items-center justify-between'><span>آخرین اجرا</span><span>{formatDate(site.latest_sync?.finished_at ?? site.latest_sync?.started_at)}</span></div></div>
          </Link>
        ))}
      </div>
      <div className='hidden overflow-x-auto md:block'>
      <table className='w-full min-w-[850px] text-sm'>
        <thead><tr className='text-muted-foreground border-b text-right text-xs'><th className='px-1 py-3 font-medium'>سایت</th><th className='px-3 py-3 font-medium'>وضعیت و اقدام بعدی</th><th className='px-3 py-3 font-medium'>آمادگی</th><th className='px-3 py-3 font-medium'>محتوا / خزش</th><th className='px-3 py-3 font-medium'>گراف</th><th className='px-3 py-3 font-medium'>فرصت‌ها</th><th className='px-3 py-3 font-medium'>آخرین اجرا</th><th className='w-9'><span className='sr-only'>مشاهده</span></th></tr></thead>
        <tbody>{sites.map((site) => (
          <tr key={site.site_id} className='group border-b last:border-0 hover:bg-muted/35'>
            <td className='px-1 py-3.5'><Link aria-label={`مشاهده سایت ${site.name}`} href={`/dashboard/sites/${site.site_id}`} className='block max-w-56 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring'><span className='block truncate font-semibold'>{site.name}</span><span className='text-muted-foreground mt-0.5 block truncate text-xs' dir='ltr'>{domain(site.canonical_url)}</span></Link></td>
            <td className='max-w-60 px-3 py-3.5'><StateBadge state={site.state} /><span className='mt-1.5 block text-xs font-medium'>{siteNextAction(site)}</span><span className='text-muted-foreground mt-0.5 line-clamp-2 block text-[11px] leading-4'>{siteStateReason(site)}</span></td><td className='px-3 py-3.5'><SetupCoverage site={site} /></td>
            <td className='px-3 py-3.5'><span className='font-semibold tabular-nums'>{fa.format(site.counts.content)}</span><span className='text-muted-foreground'> / {fa.format(site.counts.crawled)}</span></td>
            <td className='px-3 py-3.5'><span className='font-semibold tabular-nums'>{fa.format(site.counts.graph_nodes)}</span><span className='text-muted-foreground text-xs'> گره</span></td>
            <td className='px-3 py-3.5'><span className={cn('font-semibold tabular-nums', site.counts.high_link_suggestions > 0 && 'text-amber-600 dark:text-amber-400')}>{fa.format(site.counts.new_link_suggestions)}</span>{site.counts.high_link_suggestions > 0 && <span className='text-muted-foreground block text-[11px]'>{fa.format(site.counts.high_link_suggestions)} اولویت بالا</span>}</td>
            <td className='text-muted-foreground px-3 py-3.5 text-xs'>{formatDate(site.latest_sync?.finished_at ?? site.latest_sync?.started_at)}</td>
            <td className='px-1 py-3.5'><Link href={`/dashboard/sites/${site.site_id}`} aria-label={`مشاهده ${site.name}`} className={buttonVariants({ variant: 'ghost', size: 'icon-sm' })}><IconArrowLeft aria-hidden='true' /></Link></td>
          </tr>
        ))}</tbody>
      </table>
      </div>
    </>
  );
}

function AttentionPanel({ data }: { data: PortfolioOverview }) {
  const failed = data.sites.filter((site) => site.state === 'attention');
  const untouched = data.sites.filter((site) => site.state === 'not_started');
  const partial = data.sites.filter((site) => site.state === 'partial');
  const highLinks = data.sites.filter((site) => site.counts.high_link_suggestions > 0).toSorted((a, b) => b.counts.high_link_suggestions - a.counts.high_link_suggestions);
  const items = [
    ...failed.slice(0, 3).map((site) => ({ icon: IconAlertTriangle, tone: 'text-rose-600 bg-rose-500/10', title: `${siteNextAction(site)}: ${site.name}`, detail: siteStateReason(site), href: `/dashboard/sites/${site.site_id}` })),
    ...untouched.slice(0, 2).map((site) => ({ icon: IconBrandWordpress, tone: 'text-slate-600 bg-slate-500/10 dark:text-slate-300', title: `راه‌اندازی ${site.name}`, detail: 'هنوز محتوایی همگام و گرافی ساخته نشده است.', href: `/dashboard/sites/${site.site_id}` })),
    ...partial.slice(0, 1).map((site) => ({ icon: IconBolt, tone: 'text-amber-600 bg-amber-500/10', title: `تکمیل داده‌های ${site.name}`, detail: `پوشش فعلی ${fa.format(site.setup_progress)}٪ است؛ مرحله بعدی را اجرا کنید.`, href: `/dashboard/sites/${site.site_id}` })),
    ...highLinks.slice(0, 1).map((site) => ({ icon: IconLink, tone: 'text-violet-600 bg-violet-500/10', title: `${fa.format(site.counts.high_link_suggestions)} فرصت مهم در ${site.name}`, detail: 'پیشنهادهای لینک‌سازی با اطمینان بالا آماده بررسی هستند.', href: `/dashboard/internal-linking?site=${site.site_id}` }))
  ].slice(0, 5);
  return (
    <Card className='h-full border-border/70 shadow-sm'><CardHeader className='pb-3'><div className='flex items-center justify-between gap-3'><div><CardTitle className='text-base'>نیازمند اقدام</CardTitle><CardDescription className='mt-1'>مهم‌ترین قدم‌های بعدی در کل سبد</CardDescription></div><Badge variant={items.length ? 'destructive' : 'secondary'}>{fa.format(items.length)}</Badge></div></CardHeader><CardContent>
      {!items.length ? <div className='flex min-h-56 flex-col items-center justify-center gap-3 text-center'><div className='flex size-11 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600'><IconCircleCheck className='size-6' /></div><div><p className='font-semibold'>همه‌چیز مرتب است</p><p className='text-muted-foreground mt-1 text-xs'>اقدام فوری ثبت نشده است.</p></div></div> : <div className='space-y-1'>{items.map((item, index) => <Link key={`${item.title}-${index}`} href={item.href} className='group flex gap-3 rounded-lg p-2.5 transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'><span className={cn('mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg', item.tone)}><item.icon className='size-4' aria-hidden='true' /></span><span className='min-w-0 flex-1'><span className='block text-sm font-semibold'>{item.title}</span><span className='text-muted-foreground mt-0.5 line-clamp-2 block text-xs leading-5'>{item.detail}</span></span><IconArrowLeft className='text-muted-foreground mt-2 size-4 shrink-0 transition-transform group-hover:-translate-x-0.5' aria-hidden='true' /></Link>)}</div>}
    </CardContent></Card>
  );
}

export function PortfolioDashboard({ data, health }: { data: PortfolioOverview; health: Health | null }) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | PortfolioSiteState>('all');
  const [bulkGraphBusy, setBulkGraphBusy] = useState(false);
  const filteredSites = useMemo(() => { const normalized = query.trim().toLocaleLowerCase('fa'); return data.sites.filter((site) => (filter === 'all' || site.state === filter) && (!normalized || `${site.name} ${site.site_id} ${site.canonical_url}`.toLocaleLowerCase('fa').includes(normalized))); }, [data.sites, filter, query]);
  const graphCandidates = useMemo(() => data.sites.filter((site) => site.state === 'partial' && (site.next_action === 'ساخت گراف دانش' || (site.counts.content > 0 && site.counts.graph_nodes === 0))), [data.sites]);
  const readiness = data.totals.sites ? Math.round((data.totals.ready_sites / data.totals.sites) * 100) : 0;
  const maxType = Math.max(...Object.values(data.by_node_type), 1);
  const typeEntries = Object.entries(data.by_node_type).slice(0, 8);

  async function rebuildMissingGraphs() {
    if (!graphCandidates.length || bulkGraphBusy) return;
    setBulkGraphBusy(true);
    const queued: string[] = [];
    const failed: string[] = [];
    for (const site of graphCandidates) {
      try {
        const result = await endpoints.graphRebuild(site.site_id);
        if (result.status === 'queued' || result.status === 'already_running') queued.push(site.name);
        else failed.push(site.name);
      } catch {
        failed.push(site.name);
      }
    }
    if (queued.length) toast.success(`ساخت گراف ${fa.format(queued.length)} سایت در پس‌زمینه شروع شد؛ جابه‌جایی بین صفحات آن را متوقف نمی‌کند.`);
    if (failed.length) toast.error(`شروع گراف برای ${fa.format(failed.length)} سایت انجام نشد: ${failed.join('، ')}`);
    if (!queued.length && !failed.length) toast.info('همه گراف‌های قابل اجرا از قبل در صف هستند.');
    router.refresh();
    setBulkGraphBusy(false);
  }

  return (
    <div className='flex flex-col gap-5'>
      <section className='relative overflow-hidden rounded-2xl border border-sky-500/15 bg-gradient-to-l from-sky-500/[0.08] via-background to-violet-500/[0.05] p-4 shadow-sm sm:p-5'>
        <div className='absolute -top-16 -left-10 size-44 rounded-full bg-sky-500/10 blur-3xl' aria-hidden='true' />
        <div className='relative flex flex-col justify-between gap-4 lg:flex-row lg:items-center'><div className='space-y-2'><div className='flex flex-wrap items-center gap-2'><Badge variant='outline' className='border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'><span className='size-1.5 rounded-full bg-emerald-500' /> بک‌اند متصل</Badge><span className='text-muted-foreground text-xs'>به‌روزرسانی {formatDate(data.generated_at)}</span></div><div><h2 className='text-xl font-bold tracking-tight sm:text-2xl'>نمای فرماندهی سبد سایت‌ها</h2><p className='text-muted-foreground mt-1 max-w-2xl text-sm leading-6'>وضعیت داده، گراف دانش و فرصت‌های عملیاتی همه سایت‌ها در یک نگاه؛ از اینجا مشخص است قدم بعدی روی کدام سایت باید انجام شود.</p></div></div><div className='flex flex-wrap items-center gap-2'>{graphCandidates.length > 0 && <Button onClick={rebuildMissingGraphs} disabled={bulkGraphBusy}><IconNetwork className={cn(bulkGraphBusy && 'animate-pulse')} />{bulkGraphBusy ? 'در حال صف‌گذاری…' : `ساخت گراف ${fa.format(graphCandidates.length)} سایت سالم`}</Button>}<Link href='/dashboard/sites' className={buttonVariants({ variant: 'outline' })}><IconWorld /> مدیریت سایت‌ها</Link><Link href='/dashboard/sites/new' className={buttonVariants({ variant: graphCandidates.length ? 'outline' : 'default' })}><IconPlus /> افزودن سایت</Link></div></div>
        {graphCandidates.length > 0 && <div className='relative mt-4 flex flex-col gap-2 rounded-xl border border-amber-500/20 bg-amber-500/[0.06] p-3 text-xs sm:flex-row sm:items-center sm:justify-between'><span><strong>{fa.format(graphCandidates.length)} سایت سالم فقط گراف ندارند.</strong> اجرای گروهی از محتوای موجود استفاده می‌کند و سایت‌های خطادار را وارد صف نمی‌کند.</span><span className='text-muted-foreground'>{graphCandidates.map((site) => site.name).join('، ')}</span></div>}
      </section>

      <section aria-label='شاخص‌های کلیدی' className='grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4'>
        <MetricCard title='سایت‌های آماده' value={data.totals.ready_sites} description={`از ${fa.format(data.totals.sites)} سایت ثبت‌شده، این تعداد داده و گراف قابل استفاده دارند.`} icon={IconWorld} lineClass='bg-emerald-500' iconClass='bg-emerald-500/10 text-emerald-600' footer={<div className='space-y-2'><div className='flex justify-between'><span className='text-muted-foreground'>آمادگی سبد</span><span className='font-semibold'>{fa.format(readiness)}٪</span></div><Progress value={readiness} className='h-1.5' /></div>} />
        <MetricCard title='موجودی محتوا' value={data.totals.content} description='صفحه و نوشته دریافت‌شده از وردپرس؛ مبنای تحلیل و ساخت گراف.' icon={IconFileText} lineClass='bg-sky-500' iconClass='bg-sky-500/10 text-sky-600' footer={<div className='flex justify-between gap-3'><span className='text-muted-foreground'>خزش‌شده</span><span className='font-semibold tabular-nums'>{fa.format(data.totals.crawled)} صفحه</span></div>} />
        <MetricCard title='گراف دانش' value={data.totals.graph_nodes} description='گره‌های معنادار میان محتوا، موجودیت‌ها، دسته‌ها و مسائل سئو.' icon={IconNetwork} lineClass='bg-violet-500' iconClass='bg-violet-500/10 text-violet-600' footer={<div className='flex justify-between gap-3'><span className='text-muted-foreground'>روابط ثبت‌شده</span><span className='font-semibold tabular-nums'>{fa.format(data.totals.graph_edges)} یال</span></div>} />
        <MetricCard title='فرصت‌های لینک' value={data.totals.new_link_suggestions} description='پیشنهادهای جدیدی که هنوز بررسی یا وارد جریان اجرا نشده‌اند.' icon={IconLink} lineClass='bg-amber-500' iconClass='bg-amber-500/10 text-amber-600' footer={<div className='flex justify-between gap-3'><span className='text-muted-foreground'>اولویت بالا</span><span className='font-semibold text-amber-600 dark:text-amber-400'>{fa.format(data.totals.high_link_suggestions)} مورد</span></div>} />
      </section>

      <section className='grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(310px,1fr)]'>
        <Card className='min-w-0 border-border/70 shadow-sm'><CardHeader className='gap-4 pb-0'><div className='flex flex-col justify-between gap-3 sm:flex-row sm:items-start'><div><CardTitle className='text-base'>وضعیت سایت‌ها</CardTitle><CardDescription className='mt-1'>پوشش داده، سلامت پردازش و فرصت‌های باز هر سایت</CardDescription></div><div className='relative w-full sm:w-64'><IconSearch className='text-muted-foreground pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2' aria-hidden='true' /><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder='جست‌وجوی نام یا دامنه…' className='pr-9' aria-label='جست‌وجوی سایت‌ها' /></div></div><div className='flex gap-1 overflow-x-auto pb-3' role='group' aria-label='فیلتر وضعیت سایت‌ها'>
          {([['all', 'همه', data.totals.sites], ['ready', 'آماده', data.state_counts.ready], ['running', 'در حال پردازش', data.state_counts.running], ['attention', 'خطادار', data.state_counts.attention], ['partial', 'ناقص', data.state_counts.partial], ['not_started', 'شروع نشده', data.state_counts.not_started]] as const).map(([key, label, count]) => <Button key={key} size='sm' variant={filter === key ? 'secondary' : 'ghost'} onClick={() => setFilter(key)} aria-pressed={filter === key}>{label}<span className='text-muted-foreground tabular-nums'>{fa.format(count)}</span></Button>)}
        </div></CardHeader><CardContent className='pt-0'><SiteTable sites={filteredSites} /></CardContent></Card>
        <AttentionPanel data={data} />
      </section>

      <section className='grid grid-cols-1 gap-4 lg:grid-cols-2'>
        <Card className='border-border/70 shadow-sm'><CardHeader><div className='flex items-center gap-3'><span className='flex size-9 items-center justify-center rounded-lg bg-violet-500/10 text-violet-600'><IconChartDots3 className='size-5' /></span><div><CardTitle className='text-base'>ترکیب گراف دانش</CardTitle><CardDescription className='mt-1'>توزیع گره‌ها در کل سبد سایت‌ها</CardDescription></div></div></CardHeader><CardContent className='space-y-3'>
          {typeEntries.map(([type, count]) => <div key={type} className='grid grid-cols-[90px_minmax(0,1fr)_55px] items-center gap-3 text-xs'><span className='truncate font-medium'>{TYPE_FA[type] ?? type}</span><div className='bg-muted h-2 overflow-hidden rounded-full'><div className='h-full rounded-full bg-gradient-to-l from-violet-500 to-sky-500' style={{ width: `${Math.max((count / maxType) * 100, 2)}%` }} /></div><span className='text-muted-foreground text-left font-medium tabular-nums'>{fa.format(count)}</span></div>)}
          {!typeEntries.length && <p className='text-muted-foreground py-16 text-center text-sm'>بعد از ساخت اولین گراف، ترکیب داده اینجا نمایش داده می‌شود.</p>}<Link href='/dashboard/graph' className={cn(buttonVariants({ variant: 'ghost', size: 'sm' }), 'mt-2')}><IconNetwork /> مشاهده گراف کامل <IconArrowLeft /></Link>
        </CardContent></Card>
        <Card className='border-border/70 shadow-sm'><CardHeader><div className='flex items-center justify-between'><div className='flex items-center gap-3'><span className='flex size-9 items-center justify-center rounded-lg bg-sky-500/10 text-sky-600'><IconClock className='size-5' /></span><div><CardTitle className='text-base'>فعالیت‌های اخیر</CardTitle><CardDescription className='mt-1'>آخرین اجرای زنجیره همگام‌سازی</CardDescription></div></div>{health && <span className='text-muted-foreground hidden text-xs sm:block' dir='ltr'>API v{health.version} · {health.database}</span>}</div></CardHeader><CardContent>
          {data.recent_activity.length ? <ol className='space-y-1'>{data.recent_activity.slice(0, 6).map((activity) => { const ok = activity.status === 'succeeded'; const running = ['queued', 'running'].includes(activity.status); return <li key={activity.run_id}><Link href={`/dashboard/sites/${activity.site_id}`} className='group flex items-center gap-3 rounded-lg p-2.5 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'><span className={cn('flex size-8 shrink-0 items-center justify-center rounded-full', ok ? 'bg-emerald-500/10 text-emerald-600' : running ? 'bg-sky-500/10 text-sky-600' : 'bg-rose-500/10 text-rose-600')}>{ok ? <IconCircleCheck className='size-4' /> : running ? <IconSparkles className='size-4' /> : <IconAlertTriangle className='size-4' />}</span><span className='min-w-0 flex-1'><span className='block truncate text-sm font-semibold'>{activity.site_name}</span><span className='text-muted-foreground block text-xs'>{ok ? 'همگام‌سازی با موفقیت کامل شد' : running ? activity.step_fa || 'پردازش در حال اجراست' : 'اجرا نیازمند بررسی است'}</span></span><span className='text-muted-foreground shrink-0 text-[11px]'>{formatDate(activity.finished_at ?? activity.started_at)}</span></Link></li>; })}</ol> : <div className='flex min-h-52 flex-col items-center justify-center gap-2 text-center'><IconDatabase className='text-muted-foreground size-7' /><p className='font-medium'>هنوز اجرایی ثبت نشده</p><p className='text-muted-foreground text-xs'>با راه‌اندازی یا همگام‌سازی یک سایت، تاریخچه اینجا شکل می‌گیرد.</p></div>}
        </CardContent></Card>
      </section>
    </div>
  );
}
