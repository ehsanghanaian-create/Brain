import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { SalesPathDashboard } from '@/features/commerce/components/sales-path-dashboard';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'مسیر رشد فروش' };

export default async function SalesPage({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const [sites, portfolio] = await Promise.all([settle(endpoints.sites()), settle(endpoints.portfolioOverview())]);
  if (sites.error) return <PageContainer pageTitle='مسیر رشد فروش'><BackendError error={sites.error} /></PageContainer>;
  const list = sites.data!;
  const initial = list.find((item) => item.site_id === site)?.site_id ?? list[0]?.site_id;
  return <PageContainer pageTitle='مسیر رشد فروش' pageDescription='از صفحات تجاری و دادهٔ جست‌وجو به تصمیم و سنجش فروش'>
    {!initial ? <p className='text-sm text-muted-foreground'>ابتدا یک سایت بسازید.</p> : <SalesPathDashboard sites={list} portfolio={portfolio.data?.sites ?? []} initialSiteId={initial} />}
  </PageContainer>;
}
