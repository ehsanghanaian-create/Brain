import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { PortfolioDashboard } from '@/features/overview/components/portfolio-dashboard';
import { endpoints, settle } from '@/lib/api/client';
import { redirect } from 'next/navigation';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'داشبورد' };

export default async function OverviewPage() {
  const [health, portfolio] = await Promise.all([
    settle(endpoints.health()),
    settle(endpoints.portfolioOverview())
  ]);

  if (!portfolio.error && portfolio.data.totals.sites === 0) {
    redirect('/dashboard/onboarding');
  }

  return (
    <PageContainer pageTitle='داشبورد' pageDescription='مرکز کنترل وضعیت و اقدام‌های بعدی در تمام سایت‌ها'>
      {portfolio.error ? (
        <BackendError error={portfolio.error} />
      ) : (
        <PortfolioDashboard data={portfolio.data} health={health.data} />
      )}
    </PageContainer>
  );
}
