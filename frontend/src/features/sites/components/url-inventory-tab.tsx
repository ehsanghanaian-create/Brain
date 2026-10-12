'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { endpoints, type UrlInventoryItem } from '@/lib/api/client';
import { useQuery } from '@tanstack/react-query';
import { useDeferredValue, useState } from 'react';
import { UrlDossier } from './url-dossier';

const sourceFa = { wordpress: 'وردپرس', crawl: 'خزش', gsc: 'GSC' } as const;
type Source = 'all' | keyof typeof sourceFa;
const PAGE_SIZE = 50;

export function UrlInventoryTab({ siteId }: { siteId: string }) {
  const [search, setSearch] = useState('');
  const [source, setSource] = useState<Source>('all');
  const [page, setPage] = useState(0);
  const [selectedUrl, setSelectedUrl] = useState<string | null>(null);
  const deferredSearch = useDeferredValue(search.trim());
  const query = useQuery({
    queryKey: ['url-inventory', siteId, deferredSearch, source, page],
    queryFn: () => endpoints.urlInventory(siteId, { search: deferredSearch, source, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    staleTime: 30_000,
  });
  const data = query.data;
  const crawl = data?.coverage.crawl;
  return <div className='space-y-4'><Card>
    <CardHeader>
      <CardTitle>موجودی صفحات سایت</CardTitle>
      <CardDescription>URLهای دیده‌شده در وردپرس، خزش و ردیف‌های موجود Search Console. نبودن یک URL در یک منبع به معنی حذف صفحه یا صفر بودن ترافیک نیست.</CardDescription>
    </CardHeader>
    <CardContent className='space-y-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <Input aria-label='جست‌وجوی صفحه' value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} placeholder='جست‌وجوی URL یا عنوان' className='max-w-sm' />
        <NativeSelect aria-label='فیلتر منبع' value={source} onChange={(e) => { setSource(e.target.value as Source); setPage(0); }} className='w-40'>
          <NativeSelectOption value='all'>همهٔ منابع</NativeSelectOption>
          <NativeSelectOption value='wordpress'>وردپرس</NativeSelectOption>
          <NativeSelectOption value='crawl'>خزش</NativeSelectOption>
          <NativeSelectOption value='gsc'>GSC</NativeSelectOption>
        </NativeSelect>
        {data && <Badge variant='secondary'>{data.total.toLocaleString('fa-IR')} URL مشاهده‌شده</Badge>}
      </div>
      <div className='flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground'>
        <span>آخرین خزش: {crawl ? `${crawl.status} · ${new Date(crawl.started_at).toLocaleString('fa-IR')} · ${crawl.urls_crawled.toLocaleString('fa-IR')} URL${crawl.max_urls ? ` · سقف ${crawl.max_urls.toLocaleString('fa-IR')}` : ''}` : 'داده‌ای نیست'}</span>
        <span>آخرین روز دادهٔ GSC: {data?.coverage.gsc_latest_date ?? 'داده‌ای نیست'} (فقط ردیف‌های گزارش‌شده)</span>
      </div>
      {query.isLoading && <p className='py-8 text-center text-sm text-muted-foreground'>در حال خواندن موجودی صفحات…</p>}
      {query.isError && <p className='rounded-lg border border-destructive/40 p-3 text-sm text-destructive'>خواندن موجودی ناموفق بود: {String(query.error)}</p>}
      {data && data.items.length === 0 && <p className='rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground'>صفحه‌ای با این فیلتر پیدا نشد.</p>}
      {data && data.items.length > 0 && <Table>
        <TableHeader><TableRow><TableHead>صفحه</TableHead><TableHead>منبع</TableHead><TableHead>خزش</TableHead><TableHead>نمایه‌پذیری</TableHead><TableHead>GSC</TableHead><TableHead>روند</TableHead></TableRow></TableHeader>
        <TableBody>{data.items.map((item) => <UrlRow key={item.url} item={item} selected={selectedUrl === item.url} onInspect={() => setSelectedUrl(selectedUrl === item.url ? null : item.url)} />)}</TableBody>
      </Table>}
      {data && data.total > PAGE_SIZE && <div className='flex items-center justify-between gap-3'>
        <span className='text-xs text-muted-foreground'>صفحه {(page + 1).toLocaleString('fa-IR')} از {Math.ceil(data.total / PAGE_SIZE).toLocaleString('fa-IR')}</span>
        <div className='flex gap-2'><Button size='sm' variant='outline' disabled={page === 0} onClick={() => setPage((p) => p - 1)}>قبلی</Button><Button size='sm' variant='outline' disabled={(page + 1) * PAGE_SIZE >= data.total} onClick={() => setPage((p) => p + 1)}>بعدی</Button></div>
      </div>}
    </CardContent>
  </Card>{selectedUrl && <UrlDossier siteId={siteId} url={selectedUrl} onClose={() => setSelectedUrl(null)} />}</div>;
}

function UrlRow({ item, selected, onInspect }: { item: UrlInventoryItem; selected: boolean; onInspect: () => void }) {
  const indexability = item.indexable === null ? 'نامشخص' : item.indexable ? 'قابل نمایه' : 'غیرقابل نمایه';
  const safeUrl = /^https?:\/\//i.test(item.url) ? item.url : null;
  return <TableRow>
    <TableCell className='max-w-80 whitespace-normal'>
      <div className='font-medium'>{item.title || 'بدون عنوان ثبت‌شده'}</div>
      {safeUrl ? <a href={safeUrl} target='_blank' rel='noreferrer' dir='ltr' className='block max-w-80 truncate text-xs text-sky-600 hover:underline dark:text-sky-400' title={item.url}>{item.url}</a> : <span dir='ltr' className='block max-w-80 truncate text-xs' title={item.url}>{item.url}</span>}
      {item.wordpress_type && <span className='text-xs text-muted-foreground'>{item.wordpress_type} · {item.wordpress_status ?? 'وضعیت نامشخص'}</span>}
    </TableCell>
    <TableCell><div className='flex flex-wrap gap-1'>{item.sources.map((s) => <Badge key={s} variant='outline'>{sourceFa[s]}</Badge>)}</div></TableCell>
    <TableCell>{item.crawl_status ? <><span>{item.crawl_status} {item.status_code ?? ''}</span><span className='block text-xs text-muted-foreground'>سایت‌مپ: {item.in_sitemap ? 'بله' : 'ثبت نشده'}</span></> : 'داده‌ای نیست'}</TableCell>
    <TableCell>{indexability}</TableCell>
    <TableCell>{item.gsc_impressions === null ? <span className='text-muted-foreground'>داده‌ای نیست</span> : <><strong>{item.gsc_clicks?.toLocaleString('fa-IR')}</strong> کلیک / {item.gsc_impressions.toLocaleString('fa-IR')} نمایش<span className='block text-xs text-muted-foreground'>میانگین جایگاه: {item.gsc_position?.toFixed(1) ?? '—'} · تا {item.gsc_date_to ?? '—'}</span></>}</TableCell>
    <TableCell><Button size='sm' variant={selected ? 'secondary' : 'outline'} onClick={onInspect} aria-pressed={selected}>روند صفحه</Button></TableCell>
  </TableRow>;
}
