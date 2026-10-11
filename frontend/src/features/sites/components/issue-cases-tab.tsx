'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { endpoints } from '@/lib/api/client';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

const labels: Record<string, string> = {
  orphan: 'صفحهٔ یتیم', no_body_inbound_links: 'لینک ورودی متنی ندارد', low_inbound_links: 'لینک ورودی کم',
  high_outbound_links: 'لینک خروجی زیاد', missing_h1: 'H1 ندارد', multiple_h1: 'چند H1', duplicate_h1: 'H1 تکراری',
  duplicate_title: 'عنوان تکراری', missing_meta_description: 'توضیح متا ندارد', images_missing_alt: 'تصویر بدون alt',
  missing_canonical: 'canonical ندارد', important_non_indexable: 'صفحهٔ مهم غیرقابل ایندکس',
  thin_content: 'محتوای کم', redirect_in_sitemap: 'ریدایرکت در سایت‌مپ',
};
const eventFa = { opened: 'شناسایی شد', reopened: 'دوباره باز شد', resolved: 'رفع آن در خزش کامل تأیید شد' } as const;

export function IssueCasesTab({ siteId }: { siteId: string }) {
  const [status, setStatus] = useState<'open' | 'resolved'>('open');
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const cases = useQuery({ queryKey: ['issue-cases', siteId, status, page], queryFn: () => endpoints.issueCases(siteId, { status, offset: page * 30, limit: 30 }), staleTime: 30_000 });
  const detail = useQuery({ queryKey: ['issue-case', siteId, selected], queryFn: () => endpoints.issueCase(siteId, selected!), enabled: selected !== null, staleTime: 30_000 });
  const data = cases.data;
  return <div className='space-y-4'>
    <Card>
      <CardHeader><CardTitle>پرونده‌های سئو</CardTitle><CardDescription>هر مشکل در تحلیل‌های بعدی همان پرونده را حفظ می‌کند. بسته‌شدن خودکار فقط پس از خزش کامل و موفق انجام می‌شود.</CardDescription></CardHeader>
      <CardContent className='space-y-4'>
        <div className='flex flex-wrap gap-2'>
          <Button size='sm' variant={status === 'open' ? 'default' : 'outline'} onClick={() => { setStatus('open'); setPage(0); setSelected(null); }}>باز · {data?.counts.open.toLocaleString('fa-IR') ?? '—'}</Button>
          <Button size='sm' variant={status === 'resolved' ? 'default' : 'outline'} onClick={() => { setStatus('resolved'); setPage(0); setSelected(null); }}>رفع‌شده · {data?.counts.resolved.toLocaleString('fa-IR') ?? '—'}</Button>
        </div>
        {cases.isLoading && <p className='py-8 text-center text-sm text-muted-foreground'>در حال خواندن پرونده‌ها…</p>}
        {cases.isError && <p className='text-sm text-destructive'>خواندن پرونده‌ها ناموفق بود: {String(cases.error)}</p>}
        {data?.items.length === 0 && <p className='rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground'>پرونده‌ای در این بخش ثبت نشده است.</p>}
        {data && data.items.length > 0 && <Table>
          <TableHeader><TableRow><TableHead>مشکل و صفحه</TableHead><TableHead>شدت</TableHead><TableHead>اولین مشاهده</TableHead><TableHead>آخرین مشاهده</TableHead><TableHead>دفعات</TableHead><TableHead>بررسی</TableHead></TableRow></TableHeader>
          <TableBody>{data.items.map((item) => <TableRow key={item.id}>
            <TableCell className='max-w-80 whitespace-normal'><strong>{labels[item.problem_type] ?? item.problem_type}</strong><span dir='ltr' className='block max-w-80 truncate text-xs text-muted-foreground' title={item.url}>{item.url || '—'}</span></TableCell>
            <TableCell><Badge variant={item.severity === 'high' ? 'destructive' : 'secondary'}>{item.severity === 'high' ? 'بالا' : item.severity === 'medium' ? 'متوسط' : 'پایین'}</Badge></TableCell>
            <TableCell>{new Date(item.first_seen).toLocaleDateString('fa-IR')}</TableCell>
            <TableCell>{new Date(item.last_seen).toLocaleDateString('fa-IR')}</TableCell>
            <TableCell>{item.seen_count.toLocaleString('fa-IR')}</TableCell>
            <TableCell><Button size='sm' variant={selected === item.id ? 'secondary' : 'outline'} onClick={() => setSelected(selected === item.id ? null : item.id)}>شواهد و تاریخچه</Button></TableCell>
          </TableRow>)}</TableBody>
        </Table>}
        {data && data.total > 30 && <div className='flex justify-end gap-2'><Button size='sm' variant='outline' disabled={page === 0} onClick={() => setPage((p) => p - 1)}>قبلی</Button><Button size='sm' variant='outline' disabled={(page + 1) * 30 >= data.total} onClick={() => setPage((p) => p + 1)}>بعدی</Button></div>}
      </CardContent>
    </Card>
    {selected !== null && <Card>
      <CardHeader><CardTitle className='text-base'>شواهد و تاریخچهٔ پرونده</CardTitle><CardDescription>رد تحلیل‌های ثبت‌شده برای پروندهٔ انتخاب‌شده</CardDescription></CardHeader>
      <CardContent className='space-y-4 text-sm'>
        {detail.isLoading && <p>در حال بارگذاری…</p>}
        {detail.isError && <p className='text-destructive'>خواندن جزئیات ناموفق بود: {String(detail.error)}</p>}
        {detail.data && <>
          <div className='grid gap-2 sm:grid-cols-2'><span>نوع: {labels[detail.data.problem_type] ?? detail.data.problem_type}</span><span>وضعیت: {detail.data.status === 'open' ? 'باز' : 'رفع‌شده'}</span></div>
          <div dir='ltr' className='break-all rounded-lg bg-muted/40 p-2 text-xs'>{detail.data.url}</div>
          {Object.keys(detail.data.detail).length > 0 && <div className='rounded-lg border p-3'><strong>آخرین شواهد</strong><dl className='mt-2 grid gap-1'>{Object.entries(detail.data.detail).map(([key, value]) => <div key={key} className='flex flex-wrap gap-2'><dt className='text-muted-foreground'>{key}:</dt><dd dir='auto'>{typeof value === 'string' ? value : JSON.stringify(value)}</dd></div>)}</dl></div>}
          <div><strong>رویدادها</strong><ul className='mt-2 space-y-1'>{detail.data.events.map((event, i) => <li key={`${event.created_at}-${i}`} className='rounded-lg border px-3 py-2'>{eventFa[event.event_type]} · {new Date(event.created_at).toLocaleString('fa-IR')} <span dir='ltr' className='text-xs text-muted-foreground'>{event.run_id}</span></li>)}</ul></div>
        </>}
      </CardContent>
    </Card>}
  </div>;
}
