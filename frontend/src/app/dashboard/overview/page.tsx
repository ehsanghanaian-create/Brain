import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { BackendError } from '@/components/seo-brain/backend-error';
import { KpiCard } from '@/components/seo-brain/kpi-card';
import { endpoints, settle } from '@/lib/api/client';
import Link from 'next/link';
import { redirect } from 'next/navigation';
import { Button } from '@/components/ui/button';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'داشبورد' };

const fa = new Intl.NumberFormat('fa-IR');
const TYPE_FA: Record<string, string> = {
  SITE: 'سایت',
  PAGE: 'صفحه',
  POST: 'نوشته',
  CATEGORY: 'دسته',
  TAG: 'برچسب',
  BRAND: 'برند',
  MODEL: 'مدل',
  SERVICE: 'خدمت',
  LOCATION: 'مکان',
  QUERY: 'کوئری GSC',
  SCHEMA: 'اسکیما',
  SEO_PROBLEM: 'مشکل سئو',
  SEO_OPPORTUNITY: 'فرصت سئو',
  KEYWORD: 'کلمه کلیدی',
  TOPIC: 'موضوع',
  CONTENT: 'محتوا'
};
const MODE_FA = { manual: 'دستی', assisted: 'نیمه‌خودکار', autopilot: 'خودکار' } as const;

export default async function OverviewPage() {
  const [health, sites] = await Promise.all([settle(endpoints.health()), settle(endpoints.sites())]);
  const siteList = sites.data ?? [];
  // fresh installation (backend up, zero sites) → guided four-step onboarding instead of an empty dashboard
  if (!sites.error && siteList.length === 0) redirect('/dashboard/onboarding');
  const summaries = await Promise.all(siteList.map((s) => settle(endpoints.graphSummary(s.site_id))));
  const totals = { nodes: 0, edges: 0, byType: {} as Record<string, number> };
  for (const r of summaries) {
    if (!r.data) continue;
    totals.nodes += r.data.nodes;
    totals.edges += r.data.edges;
    for (const [t, n] of Object.entries(r.data.by_node_type)) totals.byType[t] = (totals.byType[t] ?? 0) + n;
  }

  return (
    <PageContainer pageTitle='داشبورد' pageDescription='وضعیت کلی سایت‌ها، گراف دانش و بک‌اند SEO Brain'>
      <div className='flex flex-1 flex-col gap-4'>
        {health.error && <BackendError error={health.error} />}
        <div className='grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4'>
          <KpiCard label='سایت‌ها' value={sites.data?.length ?? null} hint='فضای کاری مستقل برای هر سایت' />
          <KpiCard label='گره‌های گراف' value={health.error ? null : totals.nodes} hint='صفحات، کوئری‌ها، موجودیت‌ها، اسکیما' />
          <KpiCard label='یال‌های گراف' value={health.error ? null : totals.edges} hint='فقط روابط واقعی' />
          <KpiCard
            label='بک‌اند'
            value={health.data ? `v${health.data.version} · ${health.data.database}` : 'قطع'}
            hint={health.data ? `مهاجرت‌ها: ${health.data.migrations.applied.join(', ')}` : undefined}
          />
        </div>

        <div className='grid grid-cols-1 gap-4 lg:grid-cols-2'>
          <Card>
            <CardHeader>
              <CardTitle>سایت‌ها</CardTitle>
              <CardDescription>حالت انتشار هر سایت — پیش‌فرض «دستی» (هیچ چیزی به وردپرس نوشته نمی‌شود)</CardDescription>
            </CardHeader>
            <CardContent className='space-y-2'>
              {siteList.length === 0 && (
                <div className='grid gap-2 rounded-md border border-dashed p-4 text-sm'>
                  <p className='font-medium'>هنوز سایتی ثبت نشده است.</p>
                  <p className='text-muted-foreground'>اتصال گوگل ← انتخاب سایت‌ها ← شروع تحلیل سئو — همه‌چیز در چهار قدم، بدون هیچ تنظیم فنی.</p>
                  <Button className='w-fit' nativeButton={false} render={<Link href='/dashboard/onboarding' />}>✨ شروع راه‌اندازی</Button>
                </div>
              )}
              {siteList.map((s, i) => (
                <div key={s.site_id} className='flex items-center justify-between rounded-md border p-2 text-sm'>
                  <div>
                    <Link href='/dashboard/sites' className='font-medium hover:underline'>
                      {s.name}
                    </Link>
                    <div className='text-muted-foreground text-xs' dir='ltr'>
                      {s.canonical_url}
                    </div>
                  </div>
                  <div className='flex items-center gap-2'>
                    {summaries[i]?.data && (
                      <span className='text-muted-foreground text-xs'>{fa.format(summaries[i].data!.nodes)} گره</span>
                    )}
                    <Badge variant={s.mode === 'manual' ? 'secondary' : 'default'}>{MODE_FA[s.mode]}</Badge>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>ترکیب گراف دانش</CardTitle>
              <CardDescription>تعداد گره‌ها به تفکیک نوع (همه سایت‌ها)</CardDescription>
            </CardHeader>
            <CardContent>
              <div className='flex flex-wrap gap-2'>
                {Object.entries(totals.byType)
                  .sort((a, b) => b[1] - a[1])
                  .map(([t, n]) => (
                    <Badge key={t} variant='outline' className='gap-1'>
                      {TYPE_FA[t] ?? t} <span className='tabular-nums'>{fa.format(n)}</span>
                    </Badge>
                  ))}
                {!Object.keys(totals.byType).length && <p className='text-muted-foreground text-sm'>داده‌ای برای نمایش نیست.</p>}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </PageContainer>
  );
}
