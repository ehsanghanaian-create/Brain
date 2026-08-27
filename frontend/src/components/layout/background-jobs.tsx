'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { endpoints, type JobRun } from '@/lib/api/client';
import { useQuery } from '@tanstack/react-query';
import { IconAlertTriangle, IconCheck, IconLoader2, IconStack2 } from '@tabler/icons-react';
import { useEffect, useMemo, useRef } from 'react';
import { toast } from 'sonner';

const TYPE_FA: Record<string, string> = {
  wordpress_sync: 'همگام‌سازی وردپرس',
  gsc_sync: 'دریافت داده Search Console',
  ga4_sync: 'دریافت داده GA4',
  links_analyze: 'تحلیل لینک‌های داخلی',
  planner_analyze: 'تحلیل برنامه محتوایی',
  generation_run: 'تولید محتوا با AI',
  build_graph: 'ساخت گراف سایت',
  sync_wordpress: 'دریافت اطلاعات وردپرس',
  noop: 'آزمایش سیستم'
};

const STATUS_FA: Record<string, string> = {
  queued: 'در صف', running: 'در حال اجرا', succeeded: 'انجام شد', failed: 'ناموفق'
};
const EMPTY_JOBS: JobRun[] = [];

function JobIcon({ status }: { status: string }) {
  if (status === 'failed') return <IconAlertTriangle className='size-4 text-destructive' />;
  if (status === 'succeeded') return <IconCheck className='size-4 text-emerald-500' />;
  return <IconLoader2 className='size-4 animate-spin text-sky-500' />;
}

export function BackgroundJobs() {
  const previous = useRef<Map<string, string>>(new Map());
  const query = useQuery({
    queryKey: ['background-jobs'],
    queryFn: () => endpoints.jobs(40),
    refetchInterval: (q) => (q.state.data?.some((j) => j.status === 'queued' || j.status === 'running') ? 2000 : 15000),
    refetchOnWindowFocus: true,
    staleTime: 1000
  });
  const jobs = query.data ?? EMPTY_JOBS;
  const active = useMemo(() => jobs.filter((j) => j.status === 'queued' || j.status === 'running'), [jobs]);

  useEffect(() => {
    for (const job of jobs) {
      const before = previous.current.get(job.run_id);
      if (before && before !== job.status && job.status === 'succeeded') toast.success(`${TYPE_FA[job.type] ?? job.type} با موفقیت تمام شد`);
      if (before && before !== job.status && job.status === 'failed') toast.error(`${TYPE_FA[job.type] ?? job.type} ناموفق بود`);
      previous.current.set(job.run_id, job.status);
    }
  }, [jobs]);

  return (
    <Sheet>
      <SheetTrigger
        render={
          <Button
            variant={active.length ? 'default' : 'outline'}
            className='fixed bottom-4 left-4 z-40 h-10 gap-2 rounded-full px-4 shadow-lg'
            aria-label='کارهای پس‌زمینه'
          />
        }
      >
        {active.length ? <IconLoader2 className='size-4 animate-spin' /> : <IconStack2 className='size-4' />}
        <span>کارهای پس‌زمینه</span>
        {active.length > 0 && <Badge variant='secondary'>{active.length.toLocaleString('fa-IR')}</Badge>}
      </SheetTrigger>
      <SheetContent side='left' className='w-[min(92vw,420px)] sm:max-w-[420px]' dir='rtl'>
        <SheetHeader className='border-b'>
          <SheetTitle>کارهای پس‌زمینه</SheetTitle>
          <SheetDescription>با تعویض صفحه یا بستن مرورگر، این کارها روی سرور ادامه پیدا می‌کنند.</SheetDescription>
        </SheetHeader>
        <ScrollArea className='min-h-0 flex-1 px-4 pb-4'>
          {query.isError && <p className='rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive'>وضعیت کارها دریافت نشد؛ اتصال بک‌اند را بررسی کنید.</p>}
          {!query.isLoading && jobs.length === 0 && <p className='py-12 text-center text-sm text-muted-foreground'>هنوز کاری ثبت نشده است.</p>}
          <div className='space-y-2'>
            {jobs.map((job) => <JobRow key={job.run_id} job={job} />)}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}

function JobRow({ job }: { job: JobRun }) {
  const active = job.status === 'queued' || job.status === 'running';
  const at = job.finished_at ?? job.started_at ?? job.queued_at;
  return (
    <div className='rounded-xl border bg-card p-3'>
      <div className='flex items-start gap-2'>
        <span className='mt-0.5 rounded-md bg-muted p-1.5'><JobIcon status={job.status} /></span>
        <div className='min-w-0 flex-1'>
          <div className='flex items-center justify-between gap-2'>
            <p className='truncate text-sm font-medium'>{TYPE_FA[job.type] ?? job.type}</p>
            <Badge variant={job.status === 'failed' ? 'destructive' : active ? 'default' : 'secondary'}>{STATUS_FA[job.status] ?? job.status}</Badge>
          </div>
          <div className='mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground'>
            {job.site_id && <span dir='ltr'>{job.site_id}</span>}
            <time>{new Date(at).toLocaleString('fa-IR', { dateStyle: 'short', timeStyle: 'short' })}</time>
          </div>
          {active && <div className='mt-3 h-1 overflow-hidden rounded-full bg-muted'><div className='h-full w-1/2 animate-pulse rounded-full bg-sky-500' /></div>}
          {job.error && <p className='mt-2 line-clamp-3 text-xs text-destructive' dir='ltr'>{job.error}</p>}
        </div>
      </div>
    </div>
  );
}
