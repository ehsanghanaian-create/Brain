'use client';

import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import type { PortfolioOverview, PortfolioSite, PortfolioSiteState, Site } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconBrandWordpress,
  IconChartBar,
  IconCircleCheck,
  IconClock,
  IconExternalLink,
  IconFileText,
  IconLink,
  IconNetwork,
  IconPlus,
  IconSearch,
  IconWorld
} from '@tabler/icons-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { DeleteSiteButton } from './delete-site-button';

type SiteView = PortfolioSite & { details?: Site };
type StatusFilter = 'all' | PortfolioSiteState;
type SortKey = 'priority' | 'name' | 'content' | 'opportunities';

const fa = new Intl.NumberFormat('fa-IR');

const STATE: Record<PortfolioSiteState, { label: string; className: string; dot: string }> = {
  ready: {
    label: 'آماده به کار',
    className: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
    dot: 'bg-emerald-500'
  },
  running: {
    label: 'در حال پردازش',
    className: 'border-sky-500/25 bg-sky-500/10 text-sky-700 dark:text-sky-300',
    dot: 'animate-pulse bg-sky-500'
  },
  attention: {
    label: 'نیازمند بررسی',
    className: 'border-rose-500/25 bg-rose-500/10 text-rose-700 dark:text-rose-300',
    dot: 'bg-rose-500'
  },
  partial: {
    label: 'راه‌اندازی ناقص',
    className: 'border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300',
    dot: 'bg-amber-500'
  },
  not_started: {
    label: 'شروع نشده',
    className: 'border-border bg-muted text-muted-foreground',
    dot: 'bg-muted-foreground/60'
  }
};

const STATUS_OPTIONS: Array<{ key: StatusFilter; label: string }> = [
  { key: 'all', label: 'همه سایت‌ها' },
  { key: 'ready', label: 'آماده' },
  { key: 'attention', label: 'نیازمند بررسی' },
  { key: 'running', label: 'در حال پردازش' },
  { key: 'partial', label: 'راه‌اندازی ناقص' },
  { key: 'not_started', label: 'شروع نشده' }
];

const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: 'priority', label: 'اولویت اقدام' },
  { key: 'name', label: 'نام سایت' },
  { key: 'content', label: 'بیشترین محتوا' },
  { key: 'opportunities', label: 'بیشترین فرصت' }
];

function getDomain(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

function formatDate(value: string | null | undefined) {
  if (!value) return 'هنوز اجرایی ثبت نشده';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'زمان نامشخص';
  return new Intl.DateTimeFormat('fa-IR', {
    timeZone: 'Asia/Tehran',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}

function readableError(error: string | undefined) {
  if (!error) return 'آخرین همگام‌سازی کامل نشده است؛ جزئیات اتصال را بررسی کنید.';
  const normalized = error.toLowerCase();
  if (normalized.includes('certificate') || normalized.includes('ssl')) {
    return 'اتصال امن دامنه معتبر نیست یا گواهی SSL با آدرس سایت تطابق ندارد.';
  }
  if (normalized.includes('name or service not known') || normalized.includes('getaddrinfo')) {
    return 'دامنه از شبکه قابل شناسایی نیست؛ DNS یا آدرس وردپرس را بررسی کنید.';
  }
  if (normalized.includes('timeout') || normalized.includes('timed out')) {
    return 'پاسخ وردپرس در زمان مناسب دریافت نشد؛ دسترسی سرور یا سرعت پاسخ را بررسی کنید.';
  }
  if (normalized.includes('unexpected_eof') || normalized.includes('eof occurred')) {
    return 'ارتباط امن هنگام دریافت داده قطع شد؛ تنظیمات SSL و سرور وردپرس را بررسی کنید.';
  }
  return 'آخرین همگام‌سازی با خطا متوقف شد؛ جزئیات اجرا را در صفحه سایت بررسی کنید.';
}

function StateBadge({ state }: { state: PortfolioSiteState }) {
  const item = STATE[state];
  return (
    <Badge variant='outline' className={cn('h-7 gap-2 px-2.5 text-xs font-medium', item.className)}>
      <span aria-hidden='true' className={cn('size-2 rounded-full', item.dot)} />
      {item.label}
    </Badge>
  );
}

function SummaryCard({ label, value, hint, icon: Icon, tone }: {
  label: string;
  value: number;
  hint: string;
  icon: typeof IconWorld;
  tone: string;
}) {
  return (
    <Card className='border-border/70 py-4 shadow-sm'>
      <CardContent className='flex items-center gap-3 px-4'>
        <span className={cn('flex size-11 shrink-0 items-center justify-center rounded-xl', tone)}>
          <Icon className='size-5' aria-hidden='true' />
        </span>
        <span className='min-w-0'>
          <span className='text-muted-foreground block text-sm'>{label}</span>
          <span className='mt-0.5 flex items-baseline gap-2'>
            <strong className='text-2xl font-bold tabular-nums'>{fa.format(value)}</strong>
            <span className='text-muted-foreground truncate text-xs'>{hint}</span>
          </span>
        </span>
      </CardContent>
    </Card>
  );
}

function Integration({ label, active, warning = false, icon: Icon }: {
  label: string;
  active: boolean;
  warning?: boolean;
  icon: typeof IconWorld;
}) {
  return (
    <span className={cn(
      'inline-flex h-7 items-center gap-1.5 rounded-lg border px-2 text-xs font-medium',
      warning
        ? 'border-rose-500/20 bg-rose-500/8 text-rose-700 dark:text-rose-300'
        : active
          ? 'border-emerald-500/20 bg-emerald-500/8 text-emerald-700 dark:text-emerald-300'
          : 'border-border/70 bg-muted/40 text-muted-foreground'
    )}>
      <Icon className='size-3.5' aria-hidden='true' />
      {label}
      <span className={cn('size-1.5 rounded-full', warning ? 'bg-rose-500' : active ? 'bg-emerald-500' : 'bg-muted-foreground/40')} />
    </span>
  );
}

function Metric({ label, value, icon: Icon, highlight = false }: {
  label: string;
  value: number;
  icon: typeof IconWorld;
  highlight?: boolean;
}) {
  return (
    <div className='rounded-xl border border-border/60 bg-muted/25 p-3'>
      <div className='text-muted-foreground flex items-center gap-1.5 text-xs'>
        <Icon className='size-3.5' aria-hidden='true' />
        {label}
      </div>
      <strong className={cn('mt-1.5 block text-lg font-bold tabular-nums', highlight && value > 0 && 'text-amber-600 dark:text-amber-400')}>
        {fa.format(value)}
      </strong>
    </div>
  );
}

function SiteCard({ site }: { site: SiteView }) {
  const wpState = site.connections.wordpress;
  const latestAt = site.latest_sync?.finished_at ?? site.latest_sync?.started_at;
  const highPriority = site.counts.high_link_suggestions;

  return (
    <Card className={cn(
      'relative border-border/70 py-0 shadow-sm transition-colors hover:border-border',
      site.state === 'attention' && 'ring-rose-500/20'
    )}>
      <CardHeader className='gap-4 px-5 pt-5'>
        <div className='flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between'>
          <div className='flex min-w-0 items-start gap-3'>
            <span className={cn(
              'flex size-11 shrink-0 items-center justify-center rounded-xl border font-bold',
              site.state === 'attention'
                ? 'border-rose-500/20 bg-rose-500/10 text-rose-600'
                : 'border-sky-500/20 bg-sky-500/10 text-sky-600'
            )}>
              <IconWorld className='size-5' aria-hidden='true' />
            </span>
            <div className='min-w-0'>
              <Link href={`/dashboard/sites/${site.site_id}`} className='block truncate text-base font-bold hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'>
                {site.name}
              </Link>
              <a href={site.canonical_url} target='_blank' rel='noreferrer' className='text-muted-foreground mt-1 inline-flex max-w-full items-center gap-1 text-sm hover:text-foreground'>
                <span className='truncate' dir='ltr'>{getDomain(site.canonical_url)}</span>
                <IconExternalLink className='size-3.5 shrink-0' aria-hidden='true' />
              </a>
            </div>
          </div>
          <StateBadge state={site.state} />
        </div>

        <div className='space-y-2'>
          <div className='flex items-center justify-between gap-4 text-sm'>
            <span className='text-muted-foreground'>آمادگی داده و ابزارها</span>
            <strong className='tabular-nums'>{fa.format(site.setup_progress)}٪</strong>
          </div>
          <Progress value={site.setup_progress} aria-label={`آمادگی ${site.name}`} className='[&_[data-slot=progress-track]]:h-2' />
        </div>
      </CardHeader>

      <CardContent className='space-y-4 px-5 pb-5'>
        {site.state === 'attention' && (
          <div className='flex gap-2.5 rounded-xl border border-rose-500/20 bg-rose-500/[0.07] p-3 text-rose-800 dark:text-rose-200'>
            <IconAlertTriangle className='mt-0.5 size-4 shrink-0' aria-hidden='true' />
            <div className='min-w-0'>
              <p className='text-sm font-semibold'>اتصال نیازمند رسیدگی است</p>
              <p className='mt-1 text-xs leading-5 opacity-85'>{readableError(site.latest_sync?.errors[0])}</p>
            </div>
          </div>
        )}

        <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
          <Metric label='محتوا' value={site.counts.content} icon={IconFileText} />
          <Metric label='خزش‌شده' value={site.counts.crawled} icon={IconChartBar} />
          <Metric label='گره گراف' value={site.counts.graph_nodes} icon={IconNetwork} />
          <Metric label='فرصت لینک' value={site.counts.new_link_suggestions} icon={IconLink} highlight />
        </div>

        <div className='flex flex-wrap items-center justify-between gap-3'>
          <div className='flex flex-wrap gap-1.5' aria-label={`اتصال‌های ${site.name}`}>
            <Integration label='وردپرس' icon={IconBrandWordpress} active={wpState === 'ok'} warning={wpState === 'error'} />
            <Integration label='Search Console' icon={IconSearch} active={Boolean(site.details?.gsc_property)} />
            <Integration label='GA4' icon={IconChartBar} active={Boolean(site.details?.ga4_property)} />
          </div>
          {highPriority > 0 && (
            <span className='inline-flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-300'>
              <IconAlertTriangle className='size-3.5' aria-hidden='true' />
              {fa.format(highPriority)} فرصت با اولویت بالا
            </span>
          )}
        </div>
      </CardContent>

      <CardFooter className='flex flex-col items-stretch justify-between gap-3 px-5 py-3 sm:flex-row sm:items-center'>
        <span className='text-muted-foreground flex items-center gap-1.5 text-xs'>
          <IconClock className='size-3.5' aria-hidden='true' />
          آخرین اجرا: {formatDate(latestAt)}
        </span>
        <div className='flex gap-2'>
          <DeleteSiteButton siteId={site.site_id} siteName={site.name} />
          {site.counts.new_link_suggestions > 0 && (
            <Link href={`/dashboard/internal-linking?site=${site.site_id}`} className={buttonVariants({ variant: 'ghost', size: 'sm' })}>
              فرصت‌ها
            </Link>
          )}
          <Link href={`/dashboard/sites/${site.site_id}`} className={buttonVariants({ variant: 'outline', size: 'sm' })}>
            مدیریت سایت
            <IconArrowLeft aria-hidden='true' />
          </Link>
        </div>
      </CardFooter>
    </Card>
  );
}

export function SitesCommandCenter({ portfolio, sites }: { portfolio: PortfolioOverview; sites: Site[] }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<StatusFilter>('all');
  const [sort, setSort] = useState<SortKey>('priority');

  const details = useMemo(() => new Map(sites.map((site) => [site.site_id, site])), [sites]);
  const allSites = useMemo<SiteView[]>(
    () => portfolio.sites.map((site) => ({ ...site, details: details.get(site.site_id) })),
    [details, portfolio.sites]
  );
  const visibleSites = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('fa');
    const rank: Record<PortfolioSiteState, number> = { attention: 0, running: 1, partial: 2, not_started: 3, ready: 4 };
    return allSites
      .filter((site) => status === 'all' || site.state === status)
      .filter((site) => !normalized || `${site.name} ${site.site_id} ${site.canonical_url}`.toLocaleLowerCase('fa').includes(normalized))
      .toSorted((a, b) => {
        if (sort === 'name') return a.name.localeCompare(b.name, 'fa');
        if (sort === 'content') return b.counts.content - a.counts.content;
        if (sort === 'opportunities') return b.counts.new_link_suggestions - a.counts.new_link_suggestions;
        return rank[a.state] - rank[b.state] || b.counts.high_link_suggestions - a.counts.high_link_suggestions;
      });
  }, [allSites, query, sort, status]);

  const wordpressOk = portfolio.sites.filter((site) => site.connections.wordpress === 'ok').length;

  return (
    <div className='flex flex-col gap-5'>
      <section className='relative overflow-hidden rounded-2xl border border-sky-500/15 bg-gradient-to-l from-sky-500/[0.08] via-background to-violet-500/[0.05] p-5 shadow-sm sm:p-6'>
        <div className='absolute -top-20 -left-16 size-56 rounded-full bg-sky-500/10 blur-3xl' aria-hidden='true' />
        <div className='relative flex flex-col justify-between gap-5 lg:flex-row lg:items-center'>
          <div>
            <div className='mb-2 flex items-center gap-2 text-sm font-medium text-sky-700 dark:text-sky-300'>
              <IconWorld className='size-4' aria-hidden='true' />
              مرکز مدیریت سایت‌ها
            </div>
            <h1 className='text-2xl font-bold tracking-tight sm:text-3xl'>وضعیت هر سایت، واضح و قابل اقدام</h1>
            <p className='text-muted-foreground mt-2 max-w-2xl text-sm leading-6'>
              آمادگی داده، سلامت اتصال، موجودی محتوا و فرصت‌های هر سایت را مقایسه کنید و مستقیم وارد مرحله بعد شوید.
            </p>
          </div>
          <div className='flex w-full flex-col gap-2 sm:w-auto sm:flex-row'>
            <Link href='/dashboard/onboarding' className={cn(buttonVariants({ variant: 'outline', size: 'lg' }), 'w-full sm:w-auto')}>
              راه‌اندازی سریع
            </Link>
            <Link href='/dashboard/sites/new' className={cn(buttonVariants({ size: 'lg' }), 'w-full sm:w-auto')}>
              <IconPlus aria-hidden='true' />
              افزودن سایت جدید
            </Link>
          </div>
        </div>
      </section>

      <section aria-label='خلاصه وضعیت سایت‌ها' className='grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4'>
        <SummaryCard label='کل سایت‌ها' value={portfolio.totals.sites} hint='در سبد فعال' icon={IconWorld} tone='bg-sky-500/10 text-sky-600' />
        <SummaryCard label='آماده به کار' value={portfolio.totals.ready_sites} hint={`از ${fa.format(portfolio.totals.sites)} سایت`} icon={IconCircleCheck} tone='bg-emerald-500/10 text-emerald-600' />
        <SummaryCard label='نیازمند رسیدگی' value={portfolio.totals.needs_attention} hint='اقدام اولویت‌دار' icon={IconAlertTriangle} tone='bg-rose-500/10 text-rose-600' />
        <SummaryCard label='وردپرس تأییدشده' value={wordpressOk} hint='اتصال سالم' icon={IconBrandWordpress} tone='bg-violet-500/10 text-violet-600' />
      </section>

      <section className='rounded-2xl border border-border/70 bg-card p-4 shadow-sm'>
        <div className='flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between'>
          <div>
            <h2 className='text-lg font-bold'>فهرست سایت‌ها</h2>
            <p className='text-muted-foreground mt-1 text-sm'>سایت‌های مشکل‌دار به‌صورت پیش‌فرض در ابتدای فهرست قرار گرفته‌اند.</p>
          </div>
          <div className='flex flex-col gap-2 sm:flex-row'>
            <label htmlFor='sites-search' className='relative min-w-0 sm:w-72'>
              <span className='sr-only'>جست‌وجوی سایت‌ها</span>
              <IconSearch className='text-muted-foreground pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2' aria-hidden='true' />
              <Input id='sites-search' value={query} onChange={(event) => setQuery(event.target.value)} placeholder='جست‌وجوی نام یا دامنه…' className='h-9 pr-9 text-sm' />
            </label>
            <label>
              <span className='sr-only'>مرتب‌سازی سایت‌ها</span>
              <select value={sort} onChange={(event) => setSort(event.target.value as SortKey)} className='border-input bg-background h-9 w-full rounded-lg border px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring sm:w-44'>
                {SORT_OPTIONS.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}
              </select>
            </label>
          </div>
        </div>

        <div className='mt-4 flex gap-2 overflow-x-auto pb-1' role='group' aria-label='فیلتر وضعیت سایت‌ها'>
          {STATUS_OPTIONS.map((option) => {
            const count = option.key === 'all' ? portfolio.totals.sites : portfolio.state_counts[option.key];
            if (option.key !== 'all' && count === 0) return null;
            return (
              <Button key={option.key} size='sm' variant={status === option.key ? 'secondary' : 'ghost'} onClick={() => setStatus(option.key)} aria-pressed={status === option.key}>
                {option.label}
                <span className='text-muted-foreground tabular-nums'>{fa.format(count)}</span>
              </Button>
            );
          })}
        </div>
      </section>

      <div className='flex items-center justify-between gap-3 px-1 text-sm'>
        <p className='text-muted-foreground'>نمایش <strong className='text-foreground'>{fa.format(visibleSites.length)}</strong> سایت</p>
        {(query || status !== 'all') && (
          <Button variant='ghost' size='sm' onClick={() => { setQuery(''); setStatus('all'); }}>پاک‌کردن فیلترها</Button>
        )}
      </div>

      {visibleSites.length ? (
        <section aria-label='کارت سایت‌ها' className='grid grid-cols-1 gap-4 2xl:grid-cols-2'>
          {visibleSites.map((site) => <SiteCard key={site.site_id} site={site} />)}
        </section>
      ) : (
        <Card className='border-dashed py-14'>
          <CardContent className='flex flex-col items-center text-center'>
            <span className='flex size-12 items-center justify-center rounded-full bg-muted'><IconSearch className='text-muted-foreground size-5' /></span>
            <h3 className='mt-4 font-bold'>سایتی پیدا نشد</h3>
            <p className='text-muted-foreground mt-1 text-sm'>عبارت جست‌وجو یا فیلتر وضعیت را تغییر دهید.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
