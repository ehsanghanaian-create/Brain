'use client';

import { useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '@/components/ui/chart';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ErrorState, LoadingState } from '@/components/seo-brain/states';
import { ApiError, endpoints } from '@/lib/api/client';
import type { MonthlyProgress } from '@/features/reports/types';

const fa = new Intl.NumberFormat('fa-IR');
const config = { clicks: { label: 'کلیک GSC', color: 'var(--chart-1)' },
  sessions: { label: 'نشست GA4', color: 'var(--chart-4)' } } satisfies ChartConfig;

export function MonthlyProgressPanel({ siteId, refreshKey }: { siteId: string; refreshKey: number }) {
  const [data, setData] = useState<MonthlyProgress | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    endpoints.reportMonthly(siteId)
      .then((next) => { if (!cancelled) { setData(next); setError(null); } })
      .catch((cause) => { if (!cancelled) setError(cause instanceof ApiError ? cause : new ApiError(0, 'unknown', String(cause), null, '')); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [siteId, refreshKey, retry]);
  if (loading && !data) return <LoadingState label='در حال ساخت روند ماهانه…' rows={4} />;
  if (error) return <ErrorState error={error} onRetry={() => setRetry((value) => value + 1)} />;
  if (!data) return null;
  const chartRows = data.months.map((row) => ({ month: row.month,
    clicks: row.gsc.status === 'missing' ? null : row.gsc.clicks,
    sessions: row.ga4.status === 'missing' ? null : row.ga4.sessions }));
  return <div className='space-y-4'>
    <Card><CardHeader><CardTitle className='text-base'>روند ۱۲ ماههٔ سایت</CardTitle><p className='text-muted-foreground text-xs'>{data.note}</p></CardHeader>
      <CardContent><ChartContainer config={config} className='h-64 w-full' dir='ltr'>
        <BarChart data={chartRows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} strokeDasharray='3 3' />
          <XAxis dataKey='month' tick={{ fontSize: 10 }} minTickGap={15} />
          <YAxis tick={{ fontSize: 10 }} width={45} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <Bar dataKey='clicks' fill='var(--color-clicks)' radius={3} animationDuration={650} />
          <Bar dataKey='sessions' fill='var(--color-sessions)' radius={3} animationDuration={650} />
        </BarChart>
      </ChartContainer></CardContent>
    </Card>
    <Card><CardContent className='overflow-x-auto pt-4'><Table><TableHeader><TableRow>
      <TableHead>ماه میلادی</TableHead><TableHead>کلیک GSC</TableHead><TableHead>پوشش GSC</TableHead>
      <TableHead>نشست GA4</TableHead><TableHead>پوشش GA4</TableHead>
    </TableRow></TableHeader><TableBody>{data.months.map((row) => <TableRow key={row.month}>
      <TableCell dir='ltr'>{row.month}</TableCell>
      <TableCell>{row.gsc.clicks == null ? '—' : fa.format(row.gsc.clicks)}</TableCell>
      <TableCell><Badge variant='outline'>{row.gsc.status === 'ready' ? 'کامل' : row.gsc.status === 'partial' ? 'ناقص' : 'بدون داده'}</Badge>
        <span className='text-muted-foreground ms-1 text-xs'>{fa.format(row.gsc.covered_days)}/{fa.format(row.gsc.expected_days)} روز</span></TableCell>
      <TableCell>{row.ga4.sessions == null ? '—' : fa.format(row.ga4.sessions)}</TableCell>
      <TableCell><Badge variant='outline'>{row.ga4.status === 'ready' ? 'کامل' : row.ga4.status === 'partial' ? 'ناقص' : 'بدون داده'}</Badge>
        <span className='text-muted-foreground ms-1 text-xs'>{fa.format(row.ga4.covered_days)}/{fa.format(row.ga4.expected_days)} روز</span></TableCell>
    </TableRow>)}</TableBody></Table></CardContent></Card>
  </div>;
}
