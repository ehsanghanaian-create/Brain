'use client';

import { endpoints } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';

export function SearchDataHealth({ siteId }: { siteId: string }) {
  const { data: sources } = useQuery({
    queryKey: ['search-data-health', siteId],
    refetchInterval: 60_000,
    queryFn: async () => {
      const results = await Promise.allSettled([endpoints.gscSyncStatus(siteId), endpoints.ga4SyncStatus(siteId)]);
      return results.map((result, index) => ({
        name: index === 0 ? 'Search Console' : 'GA4',
        date: result.status === 'fulfilled' ? result.value.coverage.date_to : null,
        blocked: result.status === 'rejected' || result.value.status === 'not_authorized',
        unavailable: result.status === 'rejected'
      }));
    }
  });
  const validDate = (date: string | null) => Boolean(date && Number.isFinite(Date.parse(date)));
  const needsAttention = sources?.some((source) => source.blocked || !validDate(source.date) || Date.now() - Date.parse(source.date!) > 7 * 86400000);
  return <section aria-label='تازگی داده‌های جست‌وجو' className={cn('rounded-xl border p-4', needsAttention ? 'border-amber-500/40 bg-amber-500/5' : 'border-border bg-card')}>
    <div className='flex flex-wrap items-center justify-between gap-2'>
      <h2 className='text-sm font-semibold'>{sources ? needsAttention ? 'داده‌های جست‌وجو نیازمند پیگیری‌اند' : 'تازگی داده‌های جست‌وجو' : 'در حال بررسی تازگی داده‌ها…'}</h2>
      <Link className='inline-flex min-h-10 items-center text-sm font-medium text-primary hover:underline' href={`/dashboard/sites/${encodeURIComponent(siteId)}?tab=integrations`}>بررسی اتصال و همگام‌سازی ←</Link>
    </div>
    {sources && <div className='mt-2 flex flex-wrap gap-x-6 gap-y-2 text-xs leading-6'>{sources.map((source) => <p key={source.name}><bdi className='font-semibold'>{source.name}</bdi>: {validDate(source.date) ? `آخرین روز داده ${new Intl.DateTimeFormat('fa-IR', { timeZone: 'Asia/Tehran', dateStyle: 'medium' }).format(new Date(`${source.date}T00:00:00Z`))}` : 'تازگی داده تأیید نشد'}{source.blocked && (source.unavailable ? ' · دریافت وضعیت ناموفق بود' : ' · دسترسی نیازمند اتصال دوباره است')}</p>)}</div>}
    {needsAttention && <p className='mt-2 text-xs leading-6 text-muted-foreground'>آماده بودن محتوا و گراف، به معنی تازه بودن آمار گوگل نیست. پیش از تصمیم دربارهٔ رشد، اتصال‌ها و تاریخ داده را بررسی کنید.</p>}
  </section>;
}
