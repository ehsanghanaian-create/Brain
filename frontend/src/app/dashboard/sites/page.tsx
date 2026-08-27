import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { SitesCommandCenter } from '@/features/sites/components/sites-command-center';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'سایت‌ها' };

export default async function SitesPage() {
  const [sites, portfolio] = await Promise.all([
    settle(endpoints.sites()),
    settle(endpoints.portfolioOverview())
  ]);

  return (
    <PageContainer>
      {sites.error && <BackendError error={sites.error} />}
      {!sites.error && portfolio.error && <BackendError error={portfolio.error} />}
      {!sites.error && !portfolio.error && (
        <SitesCommandCenter sites={sites.data} portfolio={portfolio.data} />
      )}
    </PageContainer>
  );
}
