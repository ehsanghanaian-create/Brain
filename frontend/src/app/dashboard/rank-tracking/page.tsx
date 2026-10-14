import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { RankTrackingDashboard } from '@/features/rank-tracking/rank-tracking-dashboard';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'پایش روزانهٔ رتبه' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const result = await settle(endpoints.sites());
  const sites = result.data ?? [];
  const initialSiteId = sites.find((item) => item.site_id === site)?.site_id ?? sites[0]?.site_id;
  return (
    <PageContainer pageTitle='پایش روزانهٔ رتبه' pageDescription='جایگاه مشاهده‌شدهٔ ارگانیک، هر روز ساعت ۶ صبح تهران؛ مستقل از میانگین سرچ کنسول'>
      {result.error && <BackendError error={result.error} />}
      {initialSiteId ? <RankTrackingDashboard sites={sites} initialSiteId={initialSiteId} /> :
        <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p>}
    </PageContainer>
  );
}
