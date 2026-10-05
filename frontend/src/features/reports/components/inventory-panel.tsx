'use client';

import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { EmptyState, ErrorState, LoadingState } from '@/components/seo-brain/states';
import { ApiError, endpoints } from '@/lib/api/client';
import type { InventoryDetail, ReportInventory } from '@/features/reports/types';

const fa = new Intl.NumberFormat('fa-IR');
const sourceNames: Record<string, string> = {
  wordpress: 'وردپرس', sitemap: 'سایت‌مپِ مشاهده‌شده', crawled: 'خزیده‌شده', gsc: 'GSC'
};

export function InventoryPanel({ siteId, refreshKey }: { siteId: string; refreshKey: number }) {
  const [data, setData] = useState<ReportInventory | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [source, setSource] = useState('');
  const [offset, setOffset] = useState(0);
  const [detail, setDetail] = useState<InventoryDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const limit = 50;

  useEffect(() => { setOffset(0); setDetail(null); }, [siteId, q, source]);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    endpoints.reportInventory(siteId, { q, source, limit, offset })
      .then((next) => { if (!cancelled) { setData(next); setError(null); } })
      .catch((cause) => { if (!cancelled) setError(cause instanceof ApiError ? cause : new ApiError(0, 'unknown', String(cause), null, '')); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [siteId, q, source, offset, refreshKey, retry]);

  const openDetail = async (url: string) => {
    setDetailLoading(true);
    try { setDetail(await endpoints.reportInventoryPage(siteId, url)); }
    catch (cause) { setError(cause instanceof ApiError ? cause : new ApiError(0, 'unknown', String(cause), null, '')); }
    finally { setDetailLoading(false); }
  };

  return <div className='space-y-4'>
    {error && <ErrorState error={error} onRetry={() => setRetry((value) => value + 1)} />}
    {loading && !data && <LoadingState label='در حال جمع‌آوری URLهای شناخته‌شده…' rows={5} />}
    {data && <>
      <div className='grid grid-cols-2 gap-2 sm:grid-cols-5'>
        {([
          ['شناخته‌شده', data.summary.discovered], ['وردپرس', data.summary.wordpress],
          ['خزیده‌شده', data.summary.crawled], ['در سایت‌مپِ مشاهده‌شده', data.summary.sitemap],
          ['دارای ردیف GSC', data.summary.gsc]
        ] as const).map(([label, value]) => <Card key={label}><CardContent className='pt-4'>
          <div className='text-muted-foreground text-xs'>{label}</div><div className='mt-1 text-2xl font-bold tabular-nums'>{fa.format(value)}</div>
        </CardContent></Card>)}
      </div>
      <Card>
        <CardHeader><CardTitle className='text-base'>موجودی صفحات</CardTitle><p className='text-muted-foreground text-xs'>{data.coverage_note} سایت‌مپ فقط برای URLهایی شمرده می‌شود که خزنده مشاهده کرده است.</p></CardHeader>
        <CardContent className='space-y-3'>
          <div className='flex flex-wrap gap-2'>
            <Input value={q} onChange={(event) => setQ(event.target.value)} placeholder='جست‌وجوی URL' aria-label='جست‌وجوی URL' className='min-w-48 flex-1' />
            <NativeSelect value={source} onChange={(event) => setSource(event.target.value)} aria-label='فیلتر منبع' className='w-48'>
              <NativeSelectOption value=''>همهٔ منابع</NativeSelectOption>
              <NativeSelectOption value='wordpress'>وردپرس</NativeSelectOption>
              <NativeSelectOption value='crawl'>خزش</NativeSelectOption>
              <NativeSelectOption value='sitemap'>سایت‌مپِ مشاهده‌شده</NativeSelectOption>
              <NativeSelectOption value='gsc'>GSC</NativeSelectOption>
            </NativeSelect>
          </div>
          {data.items.length === 0 ? <EmptyState title='URLی با این فیلتر پیدا نشد' description='منبع‌ها را همگام‌سازی کنید یا فیلتر را تغییر دهید.' /> :
            <div className='overflow-x-auto rounded-md border'><Table><TableHeader><TableRow>
              <TableHead>URL</TableHead><TableHead>منابع</TableHead><TableHead>HTTP</TableHead><TableHead>ایندکس‌پذیری طبق خزش</TableHead><TableHead>آخرین مشاهده</TableHead>
            </TableRow></TableHeader><TableBody>{data.items.map((row) => <TableRow key={row.url}>
              <TableCell><button type='button' onClick={() => openDetail(row.url)} className='max-w-80 truncate text-start text-primary hover:underline' dir='ltr' title={row.url}>{row.url}</button></TableCell>
              <TableCell><div className='flex min-w-40 flex-wrap gap-1'>{row.sources.map((name) => <Badge variant='outline' key={name}>{sourceNames[name]}</Badge>)}</div></TableCell>
              <TableCell>{row.status_code ?? '—'}</TableCell>
              <TableCell>{row.indexable === 1 ? 'بله' : row.indexable === 0 ? 'خیر' : 'بررسی‌نشده'}</TableCell>
              <TableCell className='text-xs' dir='ltr'>{row.last_seen ?? '—'}</TableCell>
            </TableRow>)}</TableBody></Table></div>}
          <div className='flex items-center justify-between gap-2 text-xs'>
            <span>{fa.format(data.total)} URL مطابق فیلتر</span>
            <div className='flex gap-2'><Button variant='outline' size='sm' disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - limit))}>قبلی</Button>
              <Button variant='outline' size='sm' disabled={offset + limit >= data.total || loading} onClick={() => setOffset(offset + limit)}>بعدی</Button></div>
          </div>
        </CardContent>
      </Card>
    </>}
    <Dialog open={Boolean(detail) || detailLoading} onOpenChange={(open) => { if (!open) setDetail(null); }}><DialogContent dir='rtl' className='max-h-[85vh] overflow-y-auto'>
      <DialogHeader><DialogTitle>پروندهٔ صفحه</DialogTitle><DialogDescription>{detail?.url ?? 'در حال بارگذاری…'}</DialogDescription></DialogHeader>
      {detail && <div className='space-y-3 text-sm'>
        <div className='flex flex-wrap gap-1'>{detail.sources.map((name) => <Badge variant='outline' key={name}>{sourceNames[name]}</Badge>)}</div>
        <div>عنوان وردپرس: {detail.wordpress?.title || '—'}</div>
        <div>وضعیت HTTP: {detail.crawl?.status_code ?? 'بررسی‌نشده'} · عمق خزش: {detail.crawl?.depth ?? '—'}</div>
        <div>ایندکس‌پذیری طبق خزش: {detail.crawl?.indexable === 1 ? 'بله' : detail.crawl?.indexable === 0 ? 'خیر' : 'بررسی‌نشده'}</div>
        {detail.crawl?.indexability_reason && <div>دلیل: {detail.crawl.indexability_reason}</div>}
        {detail.crawl?.canonical && <div className='break-all' dir='ltr'>Canonical: {detail.crawl.canonical}</div>}
        {detail.crawl?.final_url && detail.crawl.final_url !== detail.url && <div className='break-all' dir='ltr'>Final URL: {detail.crawl.final_url}</div>}
        {detail.gsc_page_query_rows && <div>ردیف‌های GSC: {fa.format(detail.gsc_page_query_rows.clicks)} کلیک · {fa.format(detail.gsc_page_query_rows.impressions)} نمایش · {fa.format(detail.gsc_page_query_rows.query_count)} عبارت</div>}
        <div>مشکلات ثبت‌شده: {fa.format(detail.problems.length)}</div>
        <p className='text-muted-foreground text-xs'>{detail.note}</p>
      </div>}
    </DialogContent></Dialog>
  </div>;
}
