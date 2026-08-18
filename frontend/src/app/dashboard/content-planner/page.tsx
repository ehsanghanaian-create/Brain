import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { ContentPlannerPage } from '@/features/content-planner/components/content-planner-page';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'برنامه‌ریز محتوا' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string; plan?: string; tab?: string }> }) {
  const { site, plan, tab } = await searchParams;
  const sites = await settle(endpoints.sites());
  if (sites.error) return <PageContainer pageTitle='برنامه‌ریز محتوا'><BackendError error={sites.error} /></PageContainer>;
  const list = sites.data!;
  const initial = list.find((s) => s.site_id === site)?.site_id ?? list[0]?.site_id;
  return (
    <PageContainer pageTitle='برنامه‌ریز محتوا' pageDescription='برنامه‌ریزی استراتژیک محتوا مثل یک صفحه‌گسترده: کلمات کلیدی → برنامه → تقویم → بریف → تولید AI → بازبینی → لینک داخلی → انتشار (انسانی). سه نما: جدول، کانبان، گراف. پیشنهادهای مغز قاعده‌محور و قابل توضیح‌اند؛ هیچ چیزی خودکار منتشر نمی‌شود.'>
      {!initial ? <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p> : <ContentPlannerPage sites={list} initialSiteId={initial} initialPlanId={plan ? Number(plan) : undefined} initialTab={tab} />}
    </PageContainer>
  );
}
