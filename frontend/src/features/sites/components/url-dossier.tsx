'use client';

import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { endpoints } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';
import { IconArrowLeft, IconChartDots3, IconExternalLink, IconX } from '@tabler/icons-react';
import Link from 'next/link';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const fa = new Intl.NumberFormat('fa-IR');
const issueLabels: Record<string, string> = {
  orphan: 'صفحهٔ یتیم', no_body_inbound_links: 'بدون لینک محتوایی ورودی', missing_h1: 'H1 ندارد',
  duplicate_title: 'عنوان تکراری', missing_meta_description: 'توضیح متا ندارد', images_missing_alt: 'تصویر بدون alt',
};
function monthLabel(value: string) {
  const date = new Date(`${value}-01T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('fa-IR', { month: 'short', year: 'numeric', timeZone: 'Asia/Tehran' }).format(date);
}

export function UrlDossier({ siteId, url, onClose }: { siteId: string; url: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ['url-dossier', siteId, url], queryFn: () => endpoints.urlDetail(siteId, url), staleTime: 60_000 });
  const data = query.data;
  const last = data?.monthly_gsc.at(-1);
  return <Card className='overflow-hidden border-sky-500/30 bg-gradient-to-bl from-sky-500/[0.05] via-card to-card shadow-sm' aria-label='پروندهٔ صفحه'>
    <CardHeader className='flex flex-row items-start justify-between gap-3'><div className='min-w-0'><span className='flex items-center gap-1.5 text-xs font-semibold text-sky-600'><IconChartDots3 className='size-4' /> روند یک صفحه</span><CardTitle className='mt-2 text-lg'>{data?.inventory.title || 'پروندهٔ URL انتخاب‌شده'}</CardTitle><CardDescription className='mt-1 break-all' dir='ltr'>{url}</CardDescription></div><Button size='icon-sm' variant='ghost' aria-label='بستن پروندهٔ صفحه' onClick={onClose}><IconX className='size-4' /></Button></CardHeader>
    <CardContent className='space-y-5'>
      {query.isLoading && <div role='status' className='h-56 animate-pulse rounded-xl bg-muted/30' />}
      {query.isError && <p role='alert' className='rounded-xl border border-destructive/40 p-3 text-sm text-destructive'>خواندن روند این صفحه ناموفق بود: {String(query.error)}</p>}
      {data && <>
        <div className='flex flex-wrap items-center gap-2 text-xs'><Badge variant='secondary'>منابع: {data.inventory.sources.join('، ') || 'نامشخص'}</Badge><Badge variant='outline'>آخرین دادهٔ GSC: {data.gsc_latest_date ?? 'ثبت نشده'}</Badge><span className='text-muted-foreground'>ماه بدون ردیف، صفر ترافیک محسوب نمی‌شود.</span></div>
        {last && <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>{[
          ['آخرین ماه مشاهده‌شده', monthLabel(last.month)], ['کلیک مشاهده‌شده', fa.format(last.clicks)],
          ['نمایش مشاهده‌شده', fa.format(last.impressions)], ['میانگین جایگاه GSC', last.position == null ? '—' : fa.format(Number(last.position.toFixed(1)))],
        ].map(([label, value]) => <div key={label} className='rounded-xl border bg-card p-3'><span className='block text-xs text-muted-foreground'>{label}</span><strong className='mt-1 block text-base tabular-nums'>{value}</strong></div>)}</div>}
        {data.monthly_gsc.length ? <div className='grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(250px,1fr)]'>
          <div className='min-w-0 rounded-xl border bg-card p-3'><div className='mb-3 flex flex-wrap items-center justify-between gap-2'><strong className='text-sm'>کلیک‌های ماهانهٔ مشاهده‌شده</strong><span className='text-xs text-muted-foreground'>حداکثر ۱۲ ماهِ دارای داده</span></div><div className='h-56 w-full' dir='ltr'><ResponsiveContainer width='100%' height='100%'><AreaChart data={data.monthly_gsc} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}><defs><linearGradient id='url-clicks-fill' x1='0' y1='0' x2='0' y2='1'><stop offset='0%' stopColor='#0ea5e9' stopOpacity={0.32} /><stop offset='100%' stopColor='#0ea5e9' stopOpacity={0.02} /></linearGradient></defs><CartesianGrid strokeDasharray='3 3' strokeOpacity={0.2} vertical={false} /><XAxis dataKey='month' tickFormatter={monthLabel} tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} width={32} allowDecimals={false} /><Tooltip labelFormatter={(label) => monthLabel(String(label))} formatter={(value) => [fa.format(Number(value)), 'کلیک مشاهده‌شده']} /><Area type='monotone' dataKey='clicks' stroke='#0ea5e9' fill='url(#url-clicks-fill)' strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} /></AreaChart></ResponsiveContainer></div></div>
          <div className='rounded-xl border bg-card p-3'><strong className='text-sm'>روند ماه به ماه</strong><div className='mt-3 max-h-56 overflow-auto'><Table><TableHeader><TableRow><TableHead>ماه</TableHead><TableHead>کلیک</TableHead><TableHead>نمایش</TableHead><TableHead>جایگاه</TableHead></TableRow></TableHeader><TableBody>{data.monthly_gsc.toReversed().map((month) => <TableRow key={month.month}><TableCell className='whitespace-nowrap text-xs'>{monthLabel(month.month)}</TableCell><TableCell>{fa.format(month.clicks)}</TableCell><TableCell>{fa.format(month.impressions)}</TableCell><TableCell>{month.position == null ? '—' : fa.format(Number(month.position.toFixed(1)))}</TableCell></TableRow>)}</TableBody></Table></div></div>
        </div> : <p className='rounded-xl border border-dashed p-5 text-sm text-muted-foreground'>برای این URL ردیف ماهانهٔ GSC ثبت نشده است. نبود داده به معنی صفر بودن کلیک یا جایگاه نیست.</p>}
        <div className='grid gap-4 xl:grid-cols-2'>
          <div className='rounded-xl border bg-card p-4'><div className='flex items-center justify-between gap-2'><strong className='text-sm'>عبارت‌های مرتبط با این صفحه</strong><Badge variant='outline'>۹۰ روز تا آخرین داده</Badge></div>{data.top_queries.length ? <div className='mt-3 space-y-2'>{data.top_queries.map((item) => <div key={item.query} className='flex items-center justify-between gap-3 border-b pb-2 text-xs last:border-0'><span className='min-w-0 truncate'>{item.query}</span><span className='shrink-0 tabular-nums text-muted-foreground'>{fa.format(item.clicks)} کلیک · {fa.format(item.impressions)} نمایش</span></div>)}</div> : <p className='mt-3 text-xs text-muted-foreground'>عبارت قابل نمایش برای این بازه ثبت نشده است.</p>}</div>
          <div className='rounded-xl border bg-card p-4'><strong className='text-sm'>پرونده و فرصت مرتبط</strong><div className='mt-3 space-y-2'>{data.issue_cases.length ? data.issue_cases.map((issue) => <Link key={issue.id} href={`/dashboard/sites/${encodeURIComponent(siteId)}?tab=issues&case=${issue.id}`} className='flex items-center justify-between gap-2 rounded-lg bg-muted/40 px-3 py-2 text-xs hover:bg-muted'><span>{issueLabels[issue.problem_type] ?? issue.problem_type}</span><Badge variant={issue.status === 'open' ? 'destructive' : 'secondary'}>{issue.status === 'open' ? 'باز' : 'رفع‌شده'}</Badge></Link>) : <p className='text-xs text-muted-foreground'>پرونده‌ای برای این URL ثبت نشده است؛ این نتیجه به پوشش خزش وابسته است.</p>}{data.new_keyword_opportunities > 0 && <Link href={`/dashboard/keywords?site=${encodeURIComponent(siteId)}&tab=opps`} className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'w-full justify-between')}>{fa.format(data.new_keyword_opportunities)} فرصت کلمهٔ جدید<IconArrowLeft className='size-4' /></Link>}</div></div>
        </div>
        <div className='flex flex-wrap items-center justify-between gap-2 border-t pt-3 text-xs text-muted-foreground'><p>منبع روند: فقط ردیف‌های مشاهده‌شدهٔ Search Console؛ دادهٔ جزئی یا قدیمی نتیجهٔ قطعی دربارهٔ رتبه نیست.</p>{/^https?:\/\//i.test(url) && <a href={url} target='_blank' rel='noreferrer' className='inline-flex items-center gap-1 text-sky-600 hover:underline'>باز کردن صفحه<IconExternalLink className='size-3.5' /></a>}</div>
      </>}
    </CardContent>
  </Card>;
}
