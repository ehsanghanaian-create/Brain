import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { PortfolioDashboard } from '@/features/overview/components/portfolio-dashboard';
import { endpoints, settle } from '@/lib/api/client';
import { redirect } from 'next/navigation';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'داشبورد' };

export default async function OverviewPage() {
  const [portfolio, inbox] = await Promise.all([
    settle(endpoints.portfolioOverview()),
    settle(endpoints.actionInbox({ limit: 4 }))
  ]);

  if (!portfolio.error && portfolio.data.totals.sites === 0) {
    redirect('/dashboard/onboarding');
  }

  return (
    <PageContainer>
      {portfolio.error ? (
        <BackendError error={portfolio.error} />
      ) : (
        <PortfolioDashboard data={portfolio.data} inbox={inbox.data} />
      )}
    </PageContainer>
  );
}
