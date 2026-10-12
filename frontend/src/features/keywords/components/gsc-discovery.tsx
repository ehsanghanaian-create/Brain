'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ApiError, endpoints, type GscKeywordDiscovery } from '@/lib/api/client';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { num, pct } from '../constants';

const PAGE_SIZE = 25;

export function GscDiscovery({ siteId, onChanged }: { siteId: string; onChanged: () => void }) {
  const [data, setData] = useState<GscKeywordDiscovery | null>(null);
  const [minImpressions, setMinImpressions] = useState(10);
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await endpoints.discoverGscKeywords(siteId, minImpressions, PAGE_SIZE, page * PAGE_SIZE));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }, [siteId, minImpressions, page]);

  useEffect(() => { void load(); }, [load]);

  async function decide(keyword: string, action: 'save' | 'ignore') {
    setBusy(keyword);
    try {
      await endpoints.decideGscKeyword(siteId, keyword, action);
      toast.success(action === 'save' ? 'کلمه به فهرست اضافه شد' : 'این عبارت نادیده گرفته شد');
      await load();
      onChanged();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className='flex flex-col gap-3'>
      <div className='flex flex-wrap items-start justify-between gap-2 rounded-lg border bg-muted/30 p-3 text-sm'>
        <div>
          <h3 className='font-semibold'>عبارت‌های دیده‌شده در Search Console</h3>
          <p className='text-muted-foreground mt-1'>این عبارت‌ها در سایت دیده شده‌اند اما هنوز در فهرست کلمات کلیدی ثبت نشده‌اند. صفحهٔ نمایش‌داده‌شده، صفحهٔ مشاهده‌شده است و خودکار به‌عنوان هدف انتخاب نمی‌شود.</p>
          <p className='text-muted-foreground mt-1 text-xs'>GSC فقط بخشی از ردیف‌های جست‌وجو را برمی‌گرداند؛ نبود عبارت در این فهرست به معنی نبود تقاضا یا رتبه نیست.</p>
        </div>
        <Badge variant='outline'>منبع: GSC · بدون هزینهٔ بیرونی</Badge>
      </div>
      <div className='flex flex-wrap items-center gap-2 text-xs'>
        <label htmlFor='gsc-discovery-min'>حداقل ایمپرشن</label>
        <NativeSelect id='gsc-discovery-min' value={String(minImpressions)} onChange={(e) => { setMinImpressions(Number(e.target.value)); setPage(0); }} className='w-28'>
          {[0, 10, 50, 100].map((n) => <NativeSelectOption key={n} value={String(n)}>{num(n)}</NativeSelectOption>)}
        </NativeSelect>
        <Button size='sm' variant='outline' onClick={() => void load()} disabled={!!busy}>به‌روزرسانی</Button>
        <span className='text-muted-foreground ms-auto'>{data ? `${num(data.total)} عبارت` : 'در حال بارگذاری…'}{data?.last_updated ? ` · آخرین داده: ${data.last_updated.slice(0, 10)}` : ''}</span>
      </div>
      {error && <p className='text-destructive text-sm'>{error}</p>}
      <div className='overflow-x-auto rounded-md border'>
        <Table>
          <TableHeader><TableRow><TableHead>عبارت</TableHead><TableHead>ایمپرشن</TableHead><TableHead>کلیک</TableHead><TableHead>جایگاه میانگین</TableHead><TableHead>CTR</TableHead><TableHead>صفحهٔ دیده‌شده</TableHead><TableHead>بازهٔ داده</TableHead><TableHead>تصمیم</TableHead></TableRow></TableHeader>
          <TableBody>
            {data?.items.map((candidate) => (
              <TableRow key={candidate.normalized}>
                <TableCell className='min-w-44 font-medium'>{candidate.keyword}</TableCell>
                <TableCell className='tabular-nums'>{num(candidate.impressions)}</TableCell>
                <TableCell className='tabular-nums'>{num(candidate.clicks)}</TableCell>
                <TableCell className='tabular-nums'>{num(candidate.position, 1)}</TableCell>
                <TableCell className='tabular-nums'>{pct(candidate.ctr)}</TableCell>
                <TableCell className='max-w-64 truncate text-xs' dir='ltr' title={candidate.top_page ?? ''}>{candidate.top_page ?? '—'}</TableCell>
                <TableCell className='text-muted-foreground whitespace-nowrap text-xs' dir='ltr'>{candidate.period_start && candidate.period_end ? `${candidate.period_start} – ${candidate.period_end}` : 'نامشخص'}</TableCell>
                <TableCell><div className='flex gap-1'>
                  <Button size='sm' disabled={!!busy} onClick={() => void decide(candidate.keyword, 'save')}>{busy === candidate.keyword ? '…' : 'ثبت'}</Button>
                  <Button size='sm' variant='ghost' disabled={!!busy} onClick={() => void decide(candidate.keyword, 'ignore')}>نادیده</Button>
                </div></TableCell>
              </TableRow>
            ))}
            {data?.items.length === 0 && <TableRow><TableCell colSpan={8} className='text-muted-foreground py-6 text-center'>{data.state === 'no_gsc_data' ? 'دادهٔ query/page از GSC هنوز در دسترس نیست.' : 'عبارت ثبت‌نشده‌ای با این حداقل ایمپرشن پیدا نشد.'}</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>
      {data && data.total > PAGE_SIZE && <div className='flex items-center justify-between text-xs'>
        <Button size='sm' variant='outline' disabled={page === 0} onClick={() => setPage((p) => p - 1)}>قبلی</Button>
        <span>صفحه {num(page + 1)} از {num(Math.ceil(data.total / PAGE_SIZE))}</span>
        <Button size='sm' variant='outline' disabled={(page + 1) * PAGE_SIZE >= data.total} onClick={() => setPage((p) => p + 1)}>بعدی</Button>
      </div>}
    </section>
  );
}
