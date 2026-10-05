'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { commandApi, type CommandOverview } from '../api';

const fa = new Intl.NumberFormat('fa-IR');
export function WorkPulse() {
  const [data, setData] = useState<CommandOverview | null>(null);
  useEffect(() => {
    let live = true;
    const load = () => { commandApi.overview({ limit: 5 }).then((result) => { if (live) setData(result); }).catch(() => {}); };
    load(); const timer = setInterval(load, 30000);
    return () => { live = false; clearInterval(timer); };
  }, []);
  return <Card className='border-emerald-500/25 bg-gradient-to-l from-emerald-500/[0.08] to-card shadow-sm'>
    <CardHeader className='flex flex-row flex-wrap items-start justify-between gap-3'><div><CardTitle>نبض اجرای تیم</CardTitle><CardDescription className='mt-1'>از داده‌های سئو تا کار مشخص با مسئول و موعد؛ آخرین تغییرها هر ۳۰ ثانیه خوانده می‌شوند.</CardDescription></div>
      <Link className={buttonVariants()} href='/dashboard/work'>باز کردن میز عملیات ←</Link></CardHeader>
    <CardContent><div className='grid gap-3 md:grid-cols-[repeat(4,minmax(0,1fr))_minmax(220px,1.5fr)]'>
      {([
        ['کار باز', data?.summary.open ?? 0], ['بی‌مسئول', data?.summary.unassigned ?? 0],
        ['عقب‌افتاده', data?.summary.overdue ?? 0], ['مسدود', data?.summary.blocked ?? 0]
      ] as const).map(([label, value]) => <div key={label} className='rounded-xl border bg-background/80 p-3'><div className='text-muted-foreground text-xs'>{label}</div><div className='mt-1 text-xl font-bold'>{data ? fa.format(value) : '…'}</div></div>)}
      <div className='rounded-xl border bg-background/80 p-3'><div className='text-muted-foreground mb-2 text-xs'>کار بعدی</div>
        {data?.items[0] ? <><strong className='block truncate text-sm'>{data.items[0].title}</strong><div className='mt-1 flex flex-wrap gap-1'><Badge variant='outline'>{data.items[0].site_name}</Badge><Badge variant='outline'>{data.items[0].owner_name || 'بی‌مسئول'}</Badge></div></> : <span className='text-muted-foreground text-xs'>هنوز کاری در میز ثبت نشده است.</span>}
      </div></div></CardContent>
  </Card>;
}
