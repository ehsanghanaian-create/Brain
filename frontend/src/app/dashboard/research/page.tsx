import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { ResearchDashboard } from '@/features/research/research-dashboard';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'پژوهش بازار و رقبا' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const result = await settle(endpoints.sites());
  const sites = result.data ?? [];
  const initialSiteId = sites.find((item) => item.site_id === site)?.site_id ?? sites[0]?.site_id;
  return (
    <PageContainer
      pageTitle='پژوهش بازار و رقبا'
      pageDescription='کشف عبارت‌های تازه، پرسش‌های خریدار و مقایسهٔ صفحات رقیب با منبع و زمان مشخص'
    >
      {result.error && <BackendError error={result.error} />}
      {initialSiteId ? (
        <ResearchDashboard sites={sites} initialSiteId={initialSiteId} />
      ) : (
        <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p>
      )}
    </PageContainer>
  );
}
