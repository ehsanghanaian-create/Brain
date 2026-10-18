'use client';

import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ActionSignalCard } from '@/features/opportunities/components/action-inbox-page';
import {
  endpoints,
  type ActionInbox,
  type PortfolioOverview,
  type PortfolioSite,
  type PortfolioSiteState
} from '@/lib/api/client';
import { cn } from '@/lib/utils';
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconArrowUpLeft,
  IconChartBar,
  IconCircleCheck,
  IconClock,
  IconFileText,
  IconNetwork,
  IconPlus,
  IconSearch,
  IconTargetArrow,
  IconWorld
} from '@tabler/icons-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';
import { toast } from 'sonner';

const fa = new Intl.NumberFormat('fa-IR');
const statusOrder: PortfolioSiteState[] = [
  'attention',
  'partial',
  'running',
  'ready',
  'not_started'
];
const status: Record<
  PortfolioSiteState,
  { label: string; dot: string; bar: string; badge: string }
> = {
  ready: {
    label: 'آماده',
    dot: 'bg-emerald-400',
    bar: 'bg-emerald-500',
    badge: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
  },
  running: {
    label: 'در حال پردازش',
    dot: 'bg-sky-400',
    bar: 'bg-sky-500',
    badge: 'border-sky-500/25 bg-sky-500/10 text-sky-700 dark:text-sky-300'
  },
  attention: {
    label: 'نیازمند بررسی',
    dot: 'bg-rose-400',
    bar: 'bg-rose-500',
    badge: 'border-rose-500/25 bg-rose-500/10 text-rose-700 dark:text-rose-300'
  },
  partial: {
    label: 'دادهٔ ناقص',
    dot: 'bg-amber-400',
    bar: 'bg-amber-500',
    badge: 'border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300'
  },
  not_started: {
    label: 'شروع نشده',
    dot: 'bg-slate-400',
    bar: 'bg-slate-400',
    badge: 'border-border bg-muted text-muted-foreground'
  }
};

function formatDate(value: string | null | undefined) {
  if (!value) return 'هنوز اجرا نشده';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? 'زمان نامشخص'
    : new Intl.DateTimeFormat('fa-IR', {
        timeZone: 'Asia/Tehran',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      }).format(date);
}

function domain(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

function nextAction(site: PortfolioSite) {
  if (site.next_action) return site.next_action;
  if (site.state === 'attention') return 'بررسی اتصال و خطاها';
  if (site.state === 'partial') return 'تکمیل داده‌ها';
  if (site.state === 'not_started') return 'شروع راه‌اندازی';
  if (site.state === 'running') return 'پیگیری پردازش';
  return 'مرور فرصت‌های سئو';
}

function nextActionHref(site: PortfolioSite) {
  const id = encodeURIComponent(site.site_id);
  if (site.state === 'attention') return `/dashboard/sites/${id}?tab=integrations`;
  if (site.state === 'partial' || site.state === 'not_started') return `/dashboard/sites/${id}`;
  return `/dashboard/opportunities?site=${id}`;
}

function StateBadge({ value }: { value: PortfolioSiteState }) {
  const item = status[value];
  return (
    <Badge
      variant='outline'
      className={cn('gap-1.5 px-2.5 py-1 text-[11px] font-medium', item.badge)}
    >
      <span aria-hidden='true' className={cn('size-1.5 rounded-full', item.dot)} />
      {item.label}
    </Badge>
  );
}

function FocusSite({
  site,
  sites,
  onSelect
}: {
  site: PortfolioSite;
  sites: PortfolioSite[];
  onSelect: (id: string) => void;
}) {
  const steps = [
    ['اتصال وردپرس', site.setup_steps.wordpress_configured],
    ['دریافت محتوا', site.setup_steps.content_synced],
    ['خزش', site.setup_steps.crawl_ready],
    ['گراف', site.setup_steps.graph_ready]
  ] as const;

  return (
    <section
      id='focus-site-panel'
      aria-labelledby='focus-site-title'
      className='relative min-w-0 scroll-mt-20 overflow-hidden rounded-[28px] bg-slate-950 p-5 text-white shadow-[0_18px_50px_-32px_rgba(15,23,42,.8)] sm:p-7'
    >
      <div
        aria-hidden='true'
        className='pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_10%_0%,rgba(45,212,191,.18),transparent_44%)]'
      />
      <div className='relative flex h-full flex-col'>
        <div className='flex flex-wrap items-start justify-between gap-4'>
          <div className='space-y-1'>
            <p className='text-[11px] font-bold tracking-[.18em] text-teal-300'>
              سایت در کانون توجه
            </p>
            <h2 id='focus-site-title' className='text-xl font-bold sm:text-2xl'>
              {site.name}
            </h2>
            <p dir='ltr' className='text-left text-xs text-slate-400'>
              {domain(site.canonical_url)}
            </p>
          </div>
          <label className='w-full max-w-60 text-xs text-slate-300 sm:w-auto sm:min-w-48'>
            <span className='mb-1.5 block'>انتخاب سایت</span>
            <select
              value={site.site_id}
              onChange={(event) => onSelect(event.target.value)}
              className='h-10 w-full rounded-xl border border-white/20 bg-slate-900 px-3 text-sm text-white outline-none focus-visible:ring-2 focus-visible:ring-teal-300'
            >
              {sites.map((item) => (
                <option key={item.site_id} value={item.site_id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className='mt-6 flex flex-wrap items-center gap-2'>
          <span className='inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-[11px] font-medium text-white'>
            <span className={cn('size-1.5 rounded-full', status[site.state].dot)} />
            {status[site.state].label}
          </span>
          <span className='text-xs text-slate-400'>
            آخرین اجرا: {formatDate(site.latest_sync?.finished_at ?? site.latest_sync?.started_at)}
          </span>
        </div>
        <div className='mt-5 grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(220px,.75fr)]'>
          <div className='rounded-2xl border border-white/10 bg-white/[.06] p-4'>
            <p className='text-xs text-slate-400'>هدف ثبت‌شده</p>
            <p className='mt-1.5 line-clamp-2 min-h-12 text-base font-semibold leading-6'>
              {site.mission?.objective || 'برای این سایت هنوز هدف کاری ثبت نشده است.'}
            </p>
            <p className='mt-2 text-xs leading-5 text-slate-400'>
              {site.mission?.success_metric
                ? `معیار موفقیت: ${site.mission.success_metric}`
                : 'معیار موفقیت را در پروندهٔ سایت مشخص کنید.'}
            </p>
          </div>
          <div className='rounded-2xl border border-teal-300/20 bg-teal-300/[.08] p-4'>
            <p className='text-xs text-teal-200'>اقدام بعدی</p>
            <p className='mt-1.5 min-h-12 text-base font-semibold leading-6'>{nextAction(site)}</p>
            <Link
              href={nextActionHref(site)}
              className='mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-teal-200 underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-300'
            >
              رفتن به محل اقدام <IconArrowLeft className='size-4' aria-hidden='true' />
            </Link>
          </div>
        </div>

        <div className='mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4'>
          {(
            [
              ['محتوا', site.counts.content],
              ['خزش‌شده', site.counts.crawled],
              ['کلمات', site.counts.keywords],
              ['فرصت لینک', site.counts.new_link_suggestions]
            ] as const
          ).map(([label, value]) => (
            <div
              key={label}
              className='rounded-xl border border-white/10 bg-white/[.04] px-3 py-2.5'
            >
              <strong className='block text-xl font-bold tabular-nums'>{fa.format(value)}</strong>
              <span className='text-[11px] text-slate-400'>{label}</span>
            </div>
          ))}
        </div>
        <div className='mt-auto pt-6'>
          <div className='flex items-center justify-between gap-3 text-xs'>
            <span className='text-slate-300'>آمادگی داده و گراف</span>
            <strong className='tabular-nums'>{fa.format(site.setup_progress)}٪</strong>
          </div>
          <div className='mt-2 h-1.5 overflow-hidden rounded-full bg-white/15'>
            <div
              className='h-full rounded-full bg-teal-300 transition-[width] duration-300 motion-reduce:transition-none'
              style={{ width: `${Math.min(100, Math.max(0, site.setup_progress))}%` }}
            />
          </div>
          <ol className='mt-3 grid grid-cols-2 gap-2 text-[11px] text-slate-300 sm:grid-cols-4'>
            {steps.map(([label, done]) => (
              <li key={label} className='flex items-center gap-1.5'>
                <span
                  className={cn(
                    'flex size-4 shrink-0 items-center justify-center rounded-full',
                    done ? 'bg-teal-300 text-slate-950' : 'border border-white/30 text-slate-400'
                  )}
                >
                  {done && <IconCircleCheck className='size-3' aria-hidden='true' />}
                </span>
                {label}
              </li>
            ))}
          </ol>
          <div className='mt-5 flex flex-wrap gap-2'>
            <Link
              href={`/dashboard/graph?site=${encodeURIComponent(site.site_id)}`}
              className={cn(
                buttonVariants({ size: 'sm' }),
                'bg-teal-300 text-slate-950 hover:bg-teal-200'
              )}
            >
              نقشهٔ تصمیم <IconArrowUpLeft className='size-4' aria-hidden='true' />
            </Link>
            <Link
              href={`/dashboard/sales?site=${encodeURIComponent(site.site_id)}`}
              className={cn(
                buttonVariants({ size: 'sm', variant: 'outline' }),
                'border-white/25 bg-transparent text-white hover:bg-white/10 hover:text-white'
              )}
            >
              مسیر رشد فروش
            </Link>
            <Link
              href={`/dashboard/sites/${encodeURIComponent(site.site_id)}`}
              className={cn(
                buttonVariants({ size: 'sm', variant: 'outline' }),
                'border-white/25 bg-transparent text-white hover:bg-white/10 hover:text-white'
              )}
            >
              پروندهٔ سایت
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

function PortfolioPulse({ data }: { data: PortfolioOverview }) {
  const ready = data.totals.sites
    ? Math.round((data.state_counts.ready / data.totals.sites) * 100)
    : 0;
  const goals = data.sites.filter((site) => Boolean(site.mission?.objective)).length;
  return (
    <Card className='min-w-0 rounded-[28px] border-border/70 py-0 shadow-sm'>
      <CardHeader className='border-b border-border/60 px-5 py-5 sm:px-6'>
        <div className='flex items-start justify-between gap-3'>
          <div>
            <p className='text-muted-foreground text-xs font-semibold'>نمای سبد</p>
            <h2 className='mt-1 text-lg font-semibold'>سلامت سایت‌ها</h2>
          </div>
          <span className='flex size-10 items-center justify-center rounded-xl bg-teal-500/10 text-teal-700 dark:text-teal-300'>
            <IconChartBar className='size-5' aria-hidden='true' />
          </span>
        </div>
      </CardHeader>
      <CardContent className='flex flex-1 flex-col px-5 py-5 sm:px-6'>
        <div className='flex items-end gap-2'>
          <strong className='text-5xl font-bold tracking-tight tabular-nums'>
            {fa.format(data.state_counts.ready)}
          </strong>
          <span className='text-muted-foreground pb-1 text-sm'>
            از {fa.format(data.totals.sites)} سایت آمادهٔ کار
          </span>
        </div>
        <p className='text-muted-foreground mt-2 text-xs'>
          «آماده» یعنی داده و گراف قابل استفاده است؛ نشانهٔ رشد ترافیک نیست.
        </p>
        <div
          className='mt-6'
          role='img'
          aria-label={`توزیع وضعیت سایت‌ها: ${statusOrder.map((key) => `${status[key].label} ${fa.format(data.state_counts[key])}`).join('، ')}`}
        >
          <div className='flex h-3 overflow-hidden rounded-full bg-muted'>
            {statusOrder.map(
              (key) =>
                data.state_counts[key] > 0 && (
                  <div
                    key={key}
                    className={status[key].bar}
                    style={{ width: `${(data.state_counts[key] / data.totals.sites) * 100}%` }}
                  />
                )
            )}
          </div>
        </div>
        <div className='mt-5 grid grid-cols-2 gap-x-3 gap-y-3 text-xs'>
          {statusOrder
            .filter((key) => data.state_counts[key] > 0)
            .map((key) => (
              <div key={key} className='flex items-center justify-between gap-2'>
                <span className='flex items-center gap-1.5 text-muted-foreground'>
                  <span className={cn('size-2 rounded-full', status[key].bar)} />
                  {status[key].label}
                </span>
                <strong className='tabular-nums'>{fa.format(data.state_counts[key])}</strong>
              </div>
            ))}
        </div>
        <div className='mt-6 space-y-2 rounded-xl bg-muted/40 p-3 text-xs'>
          <p className='font-semibold'>شکاف‌های داده و برنامه</p>
          <div className='flex justify-between gap-3 text-muted-foreground'>
            <span>سایت بدون هدف ثبت‌شده</span>
            <strong className='text-foreground tabular-nums'>
              {fa.format(data.totals.sites - goals)}
            </strong>
          </div>
          <div className='flex justify-between gap-3 text-muted-foreground'>
            <span>سایت با محتوای بدون گراف</span>
            <strong className='text-foreground tabular-nums'>
              {fa.format(
                data.sites.filter(
                  (site) => site.counts.content > 0 && site.counts.graph_nodes === 0
                ).length
              )}
            </strong>
          </div>
        </div>
        <div className='mt-auto grid grid-cols-2 gap-3 border-t border-border/70 pt-5 text-sm'>
          <div>
            <strong className='block text-lg tabular-nums'>{fa.format(ready)}٪</strong>
            <span className='text-muted-foreground text-xs'>آمادگی سبد</span>
          </div>
          <div>
            <strong className='block text-lg tabular-nums'>{fa.format(goals)}</strong>
            <span className='text-muted-foreground text-xs'>سایت دارای هدف</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  href
}: {
  title: string;
  value: number | null;
  subtitle: string;
  icon: typeof IconWorld;
  href: string;
}) {
  return (
    <Link
      href={href}
      className='group flex min-w-0 items-center gap-4 rounded-2xl border border-border/70 bg-card p-4 shadow-sm outline-none transition-[border-color,transform] duration-200 hover:-translate-y-0.5 hover:border-teal-500/40 focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none motion-reduce:hover:translate-y-0 sm:p-5'
    >
      <span className='flex size-11 shrink-0 items-center justify-center rounded-xl bg-teal-500/10 text-teal-700 dark:text-teal-300'>
        <Icon className='size-5' aria-hidden='true' />
      </span>
      <span className='min-w-0 flex-1'>
        <span className='text-muted-foreground block text-xs'>{title}</span>
        <strong className='mt-1 block text-2xl font-bold tabular-nums'>
          {value === null ? '—' : fa.format(value)}
        </strong>
        <span className='text-muted-foreground mt-0.5 block truncate text-xs'>{subtitle}</span>
      </span>
      <IconArrowLeft
        className='text-muted-foreground size-4 shrink-0 transition-transform group-hover:-translate-x-1 motion-reduce:transition-none'
        aria-hidden='true'
      />
    </Link>
  );
}

function AttentionPanel({
  data,
  graphCandidates,
  onRebuild,
  busy
}: {
  data: PortfolioOverview;
  graphCandidates: PortfolioSite[];
  onRebuild: () => void;
  busy: boolean;
}) {
  const issues = data.sites
    .filter(
      (site) =>
        site.state === 'attention' || site.state === 'partial' || site.state === 'not_started'
    )
    .toSorted((a, b) => statusOrder.indexOf(a.state) - statusOrder.indexOf(b.state))
    .slice(0, 4);
  return (
    <Card className='min-w-0 rounded-2xl border-border/70 shadow-sm'>
      <CardHeader className='flex flex-row items-start justify-between gap-3'>
        <div>
          <p className='text-muted-foreground text-xs font-semibold'>اولویت‌های اجرایی</p>
          <h2 className='mt-1 text-base font-semibold'>نیازمند پیگیری</h2>
        </div>
        <Badge variant='secondary'>{fa.format(data.totals.needs_attention)}</Badge>
      </CardHeader>
      <CardContent className='space-y-2'>
        {issues.length ? (
          issues.map((site) => (
            <Link
              key={site.site_id}
              href={nextActionHref(site)}
              className='group flex items-start gap-3 rounded-xl border border-border/60 p-3 outline-none transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring'
            >
              <span className={cn('mt-1 size-2 shrink-0 rounded-full', status[site.state].bar)} />
              <span className='min-w-0 flex-1'>
                <strong className='block truncate text-sm'>{site.name}</strong>
                <span className='text-muted-foreground mt-0.5 block text-xs'>
                  {nextAction(site)}
                </span>
              </span>
              <IconArrowLeft
                className='text-muted-foreground mt-1 size-4 shrink-0'
                aria-hidden='true'
              />
            </Link>
          ))
        ) : (
          <div className='rounded-xl border border-dashed p-5 text-center'>
            <IconCircleCheck className='mx-auto size-6 text-emerald-600' aria-hidden='true' />
            <p className='mt-2 text-sm font-medium'>پیگیری فوری ثبت نشده است</p>
          </div>
        )}
        {graphCandidates.length > 0 && (
          <div className='rounded-xl border border-amber-500/25 bg-amber-500/[.06] p-3'>
            <p className='text-xs leading-5'>
              <strong>{fa.format(graphCandidates.length)} سایت</strong> محتوا دارند اما گراف هنوز
              ساخته نشده است.
            </p>
            <Button
              size='sm'
              variant='outline'
              className='mt-2'
              onClick={onRebuild}
              disabled={busy}
            >
              <IconNetwork
                className={cn('size-4', busy && 'animate-pulse motion-reduce:animate-none')}
                aria-hidden='true'
              />
              {busy ? 'در حال صف‌گذاری…' : 'ساخت گراف‌ها'}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SiteList({
  sites,
  selectedId,
  onSelect
}: {
  sites: PortfolioSite[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  if (!sites.length)
    return (
      <div className='py-12 text-center'>
        <IconSearch className='text-muted-foreground mx-auto size-7' aria-hidden='true' />
        <p className='mt-2 text-sm font-medium'>سایتی با این فیلتر پیدا نشد</p>
        <p className='text-muted-foreground mt-1 text-xs'>جست‌وجو یا فیلتر وضعیت را تغییر دهید.</p>
      </div>
    );
  return (
    <div className='divide-y divide-border/60'>
      {sites.map((site) => (
        <div
          key={site.site_id}
          className={cn(
            'flex flex-col gap-3 px-4 py-3.5 transition-colors sm:flex-row sm:items-center sm:px-5',
            selectedId === site.site_id ? 'bg-teal-500/[.055]' : 'hover:bg-muted/35'
          )}
        >
          <button
            type='button'
            onClick={() => onSelect(site.site_id)}
            aria-pressed={selectedId === site.site_id}
            aria-label={`انتخاب ${site.name} برای نمای اصلی`}
            className='flex min-w-0 flex-1 items-center gap-3 rounded-lg text-right outline-none focus-visible:ring-2 focus-visible:ring-ring'
          >
            <span
              className='flex size-10 shrink-0 items-center justify-center rounded-xl border border-border/60 bg-background text-sm font-bold text-teal-700 dark:text-teal-300'
              aria-hidden='true'
            >
              {site.name.trim().slice(0, 1)}
            </span>
            <span className='min-w-0 flex-1'>
              <strong className='block truncate text-sm'>{site.name}</strong>
              <span
                dir='ltr'
                className='text-muted-foreground mt-0.5 block truncate text-left text-[11px]'
              >
                {domain(site.canonical_url)}
              </span>
            </span>
          </button>
          <div className='flex min-w-0 flex-wrap items-center justify-between gap-3 sm:w-[min(52%,490px)] sm:justify-end'>
            <div className='min-w-0 flex-1 sm:max-w-44'>
              <p className='truncate text-xs font-medium'>{nextAction(site)}</p>
              <p className='text-muted-foreground mt-0.5 truncate text-[11px]'>
                آخرین اجرا:{' '}
                {formatDate(site.latest_sync?.finished_at ?? site.latest_sync?.started_at)}
              </p>
            </div>
            <div className='flex items-center gap-2'>
              <StateBadge value={site.state} />
              <span className='hidden w-14 text-left text-xs font-semibold tabular-nums lg:inline'>
                {fa.format(site.setup_progress)}٪
              </span>
              <Link
                href={`/dashboard/sites/${encodeURIComponent(site.site_id)}`}
                aria-label={`باز کردن پرونده ${site.name}`}
                className={cn(buttonVariants({ variant: 'ghost', size: 'icon-sm' }), 'shrink-0')}
              >
                <IconArrowLeft className='size-4' aria-hidden='true' />
              </Link>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function PortfolioDashboard({
  data,
  inbox
}: {
  data: PortfolioOverview;
  inbox: ActionInbox | null;
}) {
  const router = useRouter();
  const [selectedId, setSelectedId] = useState(
    () =>
      data.sites.find((site) =>
        /salimore/i.test(`${site.site_id} ${site.name} ${site.canonical_url}`)
      )?.site_id ??
      data.sites[0]?.site_id ??
      ''
  );
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | PortfolioSiteState>('all');
  const [busy, setBusy] = useState(false);
  const selected = data.sites.find((site) => site.site_id === selectedId) ?? data.sites[0];
  function focusSite(id: string) {
    setSelectedId(id);
    document.getElementById('focus-site-panel')?.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      block: 'start'
    });
  }
  const visibleSites = useMemo(() => {
    const search = query.trim().toLocaleLowerCase('fa');
    return data.sites.filter(
      (site) =>
        (filter === 'all' || site.state === filter) &&
        (!search ||
          `${site.name} ${site.site_id} ${site.canonical_url}`
            .toLocaleLowerCase('fa')
            .includes(search))
    );
  }, [data.sites, filter, query]);
  const graphCandidates = useMemo(
    () =>
      data.sites.filter(
        (site) =>
          site.state === 'partial' &&
          (site.next_action === 'ساخت گراف دانش' ||
            (site.counts.content > 0 && site.counts.graph_nodes === 0))
      ),
    [data.sites]
  );

  async function rebuildMissingGraphs() {
    if (!graphCandidates.length || busy) return;
    setBusy(true);
    const queued: string[] = [];
    const failed: string[] = [];
    try {
      for (const site of graphCandidates) {
        try {
          const result = await endpoints.graphRebuild(site.site_id);
          if (result.status === 'queued' || result.status === 'already_running')
            queued.push(site.name);
          else failed.push(site.name);
        } catch {
          failed.push(site.name);
        }
      }
      if (queued.length)
        toast.success(`ساخت گراف ${fa.format(queued.length)} سایت در پس‌زمینه شروع شد.`);
      if (failed.length)
        toast.error(
          `شروع گراف برای ${fa.format(failed.length)} سایت انجام نشد: ${failed.join('، ')}`
        );
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className='mx-auto flex w-full max-w-[1580px] flex-col gap-5 pb-6'>
      <header className='flex flex-col justify-between gap-4 border-b border-border/70 pb-5 sm:flex-row sm:items-end'>
        <div>
          <p className='flex items-center gap-2 text-xs font-bold text-teal-700 dark:text-teal-300'>
            <span className='size-2 rounded-full bg-teal-500' />
            SEO BRAIN / نمای امروز
          </p>
          <h1 className='mt-1 text-2xl font-bold tracking-tight sm:text-3xl'>نبض رشد سایت‌ها</h1>
          <p className='text-muted-foreground mt-1 max-w-2xl text-sm leading-6'>
            از وضعیت داده تا تصمیم بعدی؛ یک سایت را انتخاب کنید و مستقیم به محل اقدام بروید.
          </p>
          <p className='text-muted-foreground mt-2 text-[11px]'>
            آخرین دریافت داده: {formatDate(data.generated_at)}
          </p>
        </div>
        <div className='flex shrink-0 flex-wrap gap-2'>
          <Link
            href='/dashboard/sites'
            className={buttonVariants({ variant: 'outline', size: 'sm' })}
          >
            <IconWorld className='size-4' aria-hidden='true' /> همهٔ سایت‌ها
          </Link>
          <Link href='/dashboard/sites/new' className={buttonVariants({ size: 'sm' })}>
            <IconPlus className='size-4' aria-hidden='true' /> افزودن سایت
          </Link>
        </div>
      </header>

      <div className='grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(310px,1fr)]'>
        {selected && <FocusSite site={selected} sites={data.sites} onSelect={setSelectedId} />}
        <PortfolioPulse data={data} />
      </div>

      <section aria-label='شاخص‌های عملیاتی' className='grid gap-3 md:grid-cols-3'>
        <StatCard
          title='موارد باز در صف تصمیم'
          value={inbox?.total ?? null}
          subtitle={inbox ? 'پرونده، کلمه و لینک در انتظار بررسی' : 'صف فرصت‌ها در دسترس نیست'}
          icon={IconAlertTriangle}
          href='/dashboard/opportunities'
        />
        <StatCard
          title='صفحات خزش‌شده'
          value={data.totals.crawled}
          subtitle={`${fa.format(data.totals.content)} محتوای دریافت‌شده`}
          icon={IconFileText}
          href='/dashboard/sites'
        />
        <StatCard
          title='کلمات ثبت‌شده'
          value={data.totals.keywords}
          subtitle={`${fa.format(data.totals.planned_content)} محتوای برنامه‌ریزی‌شده`}
          icon={IconTargetArrow}
          href='/dashboard/keywords'
        />
      </section>

      <section className='grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(300px,1fr)]'>
        <Card className='min-w-0 rounded-2xl border-border/70 shadow-sm'>
          <CardHeader className='flex flex-row flex-wrap items-start justify-between gap-3'>
            <div>
              <p className='text-muted-foreground text-xs font-semibold'>صف تصمیم</p>
              <h2 className='mt-1 text-base font-semibold'>از شواهد به اقدام</h2>
              <p className='text-muted-foreground mt-1 text-xs'>
                آخرین موارد باز از تحلیل سایت، کلمات و لینک‌ها
              </p>
            </div>
            <Link
              href='/dashboard/opportunities'
              className={buttonVariants({ variant: 'outline', size: 'sm' })}
            >
              دیدن همه <IconArrowLeft className='size-4' aria-hidden='true' />
            </Link>
          </CardHeader>
          <CardContent className='space-y-2'>
            {inbox?.items.length ? (
              inbox.items
                .slice(0, 4)
                .map((item) => (
                  <ActionSignalCard
                    key={`${item.kind}:${item.site_id}:${item.source_id}`}
                    item={item}
                    compact
                  />
                ))
            ) : (
              <div className='rounded-xl border border-dashed p-5 text-sm text-muted-foreground'>
                {inbox
                  ? 'مورد بازی ثبت نشده است؛ پوشش دادهٔ هر منبع را جداگانه بررسی کنید.'
                  : 'صف فرصت‌ها فعلاً بارگذاری نشده است.'}
              </div>
            )}
          </CardContent>
        </Card>
        <AttentionPanel
          data={data}
          graphCandidates={graphCandidates}
          onRebuild={rebuildMissingGraphs}
          busy={busy}
        />
      </section>

      <section
        aria-labelledby='site-list-title'
        className='overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm'
      >
        <div className='flex flex-col gap-4 border-b border-border/60 p-4 sm:flex-row sm:items-start sm:justify-between sm:p-5'>
          <div>
            <h2 id='site-list-title' className='text-base font-semibold'>
              سایت‌های شما
            </h2>
            <p className='text-muted-foreground mt-1 text-xs'>
              انتخاب هر ردیف، نمای اصلی را روی همان سایت متمرکز می‌کند.
            </p>
          </div>
          <div className='relative block w-full sm:w-64'>
            <span className='sr-only'>جست‌وجوی سایت‌ها</span>
            <IconSearch
              className='text-muted-foreground pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2'
              aria-hidden='true'
            />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder='جست‌وجوی سایت…'
              className='pr-9'
              aria-label='جست‌وجوی سایت‌ها'
            />
          </div>
        </div>
        <div
          className='flex gap-1 overflow-x-auto border-b border-border/60 px-3 py-2'
          role='group'
          aria-label='فیلتر وضعیت سایت‌ها'
        >
          {(
            [
              ['all', 'همه', data.totals.sites],
              ...statusOrder.map((key) => [key, status[key].label, data.state_counts[key]])
            ] as [string, string, number][]
          )
            .filter(([key, , count]) => key === 'all' || count > 0)
            .map(([key, label, count]) => (
              <Button
                key={key}
                size='sm'
                variant={filter === key ? 'secondary' : 'ghost'}
                onClick={() => setFilter(key as 'all' | PortfolioSiteState)}
                aria-pressed={filter === key}
                className='shrink-0'
              >
                {label}
                <span className='text-muted-foreground tabular-nums'>{fa.format(count)}</span>
              </Button>
            ))}
        </div>
        <SiteList sites={visibleSites} selectedId={selected?.site_id ?? ''} onSelect={focusSite} />
      </section>

      <section
        aria-labelledby='activity-title'
        className='rounded-2xl border border-border/70 bg-card p-4 shadow-sm sm:p-5'
      >
        <div className='flex items-start justify-between gap-3'>
          <div>
            <h2 id='activity-title' className='text-base font-semibold'>
              آخرین همگام‌سازی‌ها
            </h2>
            <p className='text-muted-foreground mt-1 text-xs'>
              فقط اجرای کامل وردپرس؛ ساخت گراف به‌تنهایی همگام‌سازی کامل نیست.
            </p>
          </div>
          <IconClock className='text-muted-foreground size-5' aria-hidden='true' />
        </div>
        {data.recent_activity.length ? (
          <ol className='mt-4 grid gap-2 lg:grid-cols-2'>
            {data.recent_activity.slice(0, 4).map((activity) => {
              const success = activity.status === 'succeeded';
              const running = ['queued', 'running'].includes(activity.status);
              return (
                <li key={activity.run_id}>
                  <Link
                    href={`/dashboard/sites/${encodeURIComponent(activity.site_id)}`}
                    className='flex items-center gap-3 rounded-xl border border-border/60 p-3 outline-none transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring'
                  >
                    <span
                      className={cn(
                        'flex size-8 shrink-0 items-center justify-center rounded-lg',
                        success
                          ? 'bg-emerald-500/10 text-emerald-600'
                          : running
                            ? 'bg-sky-500/10 text-sky-600'
                            : 'bg-rose-500/10 text-rose-600'
                      )}
                    >
                      {success ? (
                        <IconCircleCheck className='size-4' aria-hidden='true' />
                      ) : running ? (
                        <IconNetwork className='size-4' aria-hidden='true' />
                      ) : (
                        <IconAlertTriangle className='size-4' aria-hidden='true' />
                      )}
                    </span>
                    <span className='min-w-0 flex-1'>
                      <strong className='block truncate text-sm'>{activity.site_name}</strong>
                      <span className='text-muted-foreground block truncate text-xs'>
                        {success
                          ? 'اجرای کامل موفق'
                          : running
                            ? activity.step_fa || 'در حال اجرا'
                            : 'نیازمند بررسی'}
                      </span>
                    </span>
                    <span className='text-muted-foreground text-[11px]'>
                      {formatDate(activity.finished_at ?? activity.started_at)}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className='text-muted-foreground mt-4 rounded-xl border border-dashed p-5 text-center text-xs'>
            هنوز اجرای کاملی ثبت نشده است.
          </p>
        )}
      </section>
    </div>
  );
}
