'use client';

import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { endpoints, type ActionInboxItem, type ActionInboxKind, type Site } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';
import { IconArrowLeft, IconChartBar, IconCircleCheck, IconFileSearch, IconLink, IconRefresh, IconSearch, IconTargetArrow } from '@tabler/icons-react';
import Link from 'next/link';
import { useState } from 'react';

const fa = new Intl.NumberFormat('fa-IR');
const PAGE_SIZE = 20;
const kinds = {
  issue: { label: 'پرونده‌های سئو', source: 'خزش و تحلیل', icon: IconFileSearch, color: 'bg-rose-500' },
  keyword: { label: 'فرصت‌های کلمه', source: 'کلمه و جست‌وجو', icon: IconSearch, color: 'bg-sky-500' },
  link: { label: 'لینک‌های داخلی', source: 'گراف لینک', icon: IconLink, color: 'bg-violet-500' },
} as const;
const issueLabels: Record<string, string> = {
  orphan: 'صفحهٔ یتیم', no_body_inbound_links: 'بدون لینک محتوایی ورودی', low_inbound_links: 'لینک ورودی کم',
  high_outbound_links: 'لینک خروجی زیاد', missing_h1: 'H1 ندارد', multiple_h1: 'چند H1', duplicate_h1: 'H1 تکراری',
  duplicate_title: 'عنوان تکراری', missing_meta_description: 'توضیح متا ندارد', images_missing_alt: 'تصویر بدون alt',
  missing_canonical: 'canonical ندارد', important_non_indexable: 'صفحهٔ مهم غیرقابل ایندکس', thin_content: 'محتوای کم',
  redirect_in_sitemap: 'ریدایرکت در سایت‌مپ',
};
const priorityLabel = { high: 'مرور زودتر', medium: 'مرور معمول', low: 'مرور بعدی' } as const;

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'زمان نامشخص' : new Intl.DateTimeFormat('fa-IR', { timeZone: 'Asia/Tehran', dateStyle: 'medium' }).format(date);
}

function sourceHref(item: ActionInboxItem) {
  const site = encodeURIComponent(item.site_id);
  if (item.kind === 'issue') return `/dashboard/sites/${site}?tab=issues&case=${item.source_id}`;
  if (item.kind === 'keyword') return `/dashboard/keywords?site=${site}&tab=opps`;
  return `/dashboard/internal-linking?site=${site}`;
}

export function ActionSignalCard({ item, compact = false }: { item: ActionInboxItem; compact?: boolean }) {
  const info = kinds[item.kind];
  const Icon = info.icon;
  const title = item.kind === 'issue' ? issueLabels[item.subtype] ?? item.title : item.title;
  return <article className={cn('group relative overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm transition-colors hover:border-primary/30', compact ? 'p-3' : 'p-4 sm:p-5')}>
    <div className={cn('absolute inset-y-0 right-0 w-1', info.color)} aria-hidden='true' />
    <div className='flex flex-col gap-3 sm:flex-row sm:items-start'>
      <span className='flex size-10 shrink-0 items-center justify-center rounded-xl bg-muted'><Icon className='size-5' aria-hidden='true' /></span>
      <div className='min-w-0 flex-1'>
        <div className='flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground'><span>{info.label}</span><span aria-hidden='true'>·</span><span>{item.site_name}</span><span aria-hidden='true'>·</span><span>{formatDate(item.observed_at)}</span></div>
        <h3 className='mt-1 text-sm font-semibold leading-6 sm:text-base'>{title}</h3>
        {!compact && item.summary && <p className='mt-1 text-sm leading-6 text-muted-foreground'>{item.summary}</p>}
        {!compact && item.url && <p dir='ltr' className='mt-2 max-w-full truncate rounded-lg bg-muted/50 px-2 py-1 text-left text-xs text-muted-foreground' title={item.url}>{item.url}</p>}
        {!compact && <details className='mt-3 text-xs text-muted-foreground'><summary className='cursor-pointer select-none hover:text-foreground'>منبع و شواهد</summary><div className='mt-2 space-y-1 rounded-lg border border-border/70 bg-muted/20 p-2'><p>منبع: {info.source}</p>{item.run_id && <p dir='ltr' className='truncate text-left'>Run: {item.run_id}</p>}{Object.keys(item.evidence).length > 0 && <pre dir='ltr' className='max-h-32 overflow-auto whitespace-pre-wrap break-all text-[11px]'>{JSON.stringify(item.evidence, null, 2)}</pre>}{item.score != null && <p>امتیاز در همین منبع: {fa.format(Math.round(item.score * 100))} از ۱۰۰</p>}</div></details>}
      </div>
      <div className='flex shrink-0 items-center gap-2 sm:flex-col sm:items-end'><Badge variant='outline' className={cn(item.priority === 'high' && 'border-rose-500/30 text-rose-600')}>{priorityLabel[item.priority]}</Badge><Link href={sourceHref(item)} className={cn(buttonVariants({ variant: compact ? 'ghost' : 'outline', size: 'sm' }), 'ms-auto sm:ms-0')}>بررسی و تصمیم<IconArrowLeft className='size-4' /></Link></div>
    </div>
  </article>;
}

export function ActionInboxPage({ sites, initialSiteId }: { sites: Site[]; initialSiteId: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [kind, setKind] = useState<ActionInboxKind>('all');
  const [page, setPage] = useState(0);
  const query = useQuery({ queryKey: ['action-inbox', siteId, kind, page], queryFn: () => endpoints.actionInbox({ siteId: siteId || undefined, kind, limit: PAGE_SIZE, offset: page * PAGE_SIZE }), staleTime: 30_000 });
  const data = query.data;
  const counts = data?.counts;
  const total = counts ? counts.issue + counts.keyword + counts.link : 0;
  return <div className='space-y-5'>
    <section className='relative overflow-hidden rounded-3xl border border-sky-500/20 bg-gradient-to-bl from-sky-500/10 via-card to-violet-500/10 p-5 shadow-sm sm:p-7'>
      <div className='absolute -left-12 -top-16 size-48 rounded-full bg-violet-500/10 blur-3xl' aria-hidden='true' />
      <div className='relative flex flex-col justify-between gap-5 lg:flex-row lg:items-end'>
        <div className='max-w-2xl'><span className='inline-flex items-center gap-2 text-xs font-semibold text-sky-700 dark:text-sky-300'><IconTargetArrow className='size-4' /> مرکز تصمیم سئو</span><h2 className='mt-2 text-2xl font-bold tracking-tight sm:text-3xl'>از داده به اقدام روشن</h2><p className='mt-2 text-sm leading-7 text-muted-foreground'>پرونده‌های باز، فرصت‌های کلمه و پیشنهادهای لینک را کنار هم مرور کنید. هر مورد به صفحهٔ منبع و شواهد خودش وصل است؛ تصمیم و اجرا همان‌جا ثبت می‌شود.</p></div>
        <div className='flex flex-wrap gap-2'><NativeSelect aria-label='انتخاب سایت' value={siteId} onChange={(event) => { setSiteId(event.target.value); setPage(0); }} className='min-w-48 bg-background/80'><NativeSelectOption value=''>همهٔ سایت‌ها</NativeSelectOption>{sites.map((site) => <NativeSelectOption key={site.site_id} value={site.site_id}>{site.name}</NativeSelectOption>)}</NativeSelect><Button variant='outline' onClick={() => void query.refetch()} disabled={query.isFetching}><IconRefresh className={cn('size-4', query.isFetching && 'animate-spin')} />تازه‌سازی</Button></div>
      </div>
      <div className='relative mt-5 flex flex-wrap items-center gap-2 border-t border-border/50 pt-4 text-xs text-muted-foreground'><Badge variant='secondary'>فقط موارد باز و جدید</Badge><span>آخرین دریافت: {data ? formatDate(data.generated_at) : '—'}</span><span>·</span><span>امتیاز منبع‌ها مستقیماً با هم مقایسه نمی‌شود.</span></div>
    </section>
    {query.isError && <div role='alert' className='rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive'>خواندن فرصت‌ها ناموفق بود: {String(query.error)}</div>}
    <section aria-label='ترکیب فرصت‌ها' className='grid gap-3 sm:grid-cols-2 xl:grid-cols-4'>
      {([['all', 'همهٔ موارد', total, IconChartBar, 'bg-foreground'], ['issue', kinds.issue.label, counts?.issue, kinds.issue.icon, kinds.issue.color], ['keyword', kinds.keyword.label, counts?.keyword, kinds.keyword.icon, kinds.keyword.color], ['link', kinds.link.label, counts?.link, kinds.link.icon, kinds.link.color]] as const).map(([key, label, count, Icon, color]) => <button key={key} type='button' aria-pressed={kind === key} onClick={() => { setKind(key); setPage(0); }} className={cn('relative overflow-hidden rounded-2xl border bg-card p-4 text-right shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', kind === key ? 'border-primary/40 ring-1 ring-primary/20' : 'border-border/70')}><div className={cn('absolute inset-x-0 top-0 h-0.5', color)} /><div className='flex items-start justify-between gap-3'><span><span className='block text-xs text-muted-foreground'>{label}</span><strong className='mt-2 block text-3xl tabular-nums'>{count == null ? '—' : fa.format(count)}</strong></span><Icon className='size-5 text-muted-foreground' aria-hidden='true' /></div></button>)}
    </section>
    {counts && total > 0 && <div className='flex h-2 overflow-hidden rounded-full bg-muted' aria-label='سهم هر منبع از موارد قابل بررسی'>{(['issue', 'keyword', 'link'] as const).map((source) => <div key={source} title={`${kinds[source].label}: ${fa.format(counts[source])}`} className={kinds[source].color} style={{ width: `${(counts[source] / total) * 100}%` }} />)}</div>}
    <div className='flex flex-wrap items-baseline justify-between gap-2'><div><h3 className='text-base font-semibold'>صف بررسی</h3><p className='mt-1 text-xs text-muted-foreground'>مرتب‌شده برای مرور؛ تأیید یک مورد به معنی رفع مشکل یا رشد رتبه نیست.</p></div>{data && <span className='text-xs text-muted-foreground'>{fa.format(data.total)} مورد در این فیلتر</span>}</div>
    {query.isLoading && <div role='status' className='space-y-3'>{[0, 1, 2].map((n) => <div key={n} className='h-32 animate-pulse rounded-2xl border bg-muted/30' />)}</div>}
    {data && data.items.length > 0 && <div className='space-y-3'>{data.items.map((item) => <ActionSignalCard key={`${item.kind}:${item.site_id}:${item.source_id}`} item={item} />)}</div>}
    {data && data.items.length === 0 && <Card className='border-dashed'><CardContent className='flex min-h-44 flex-col items-center justify-center gap-2 text-center'><IconCircleCheck className='size-7 text-muted-foreground' /><strong>موردی در این فیلتر ثبت نشده است</strong><p className='max-w-lg text-xs leading-6 text-muted-foreground'>این نتیجه فقط به داده‌های فعلی خزش، تحلیل کلمات و گراف لینک مربوط است. پوشش ناقص یا دادهٔ قدیمی را در صفحهٔ سایت بررسی کنید.</p></CardContent></Card>}
    {data && data.total > PAGE_SIZE && <div className='flex items-center justify-between gap-3'><Button variant='outline' size='sm' disabled={page === 0} onClick={() => setPage((n) => n - 1)}>قبلی</Button><span className='text-xs text-muted-foreground'>صفحهٔ {fa.format(page + 1)} از {fa.format(Math.ceil(data.total / PAGE_SIZE))}</span><Button variant='outline' size='sm' disabled={(page + 1) * PAGE_SIZE >= data.total} onClick={() => setPage((n) => n + 1)}>بعدی</Button></div>}
  </div>;
}
