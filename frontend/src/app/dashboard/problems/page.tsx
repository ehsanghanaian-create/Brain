import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { ProblemsPage } from '@/features/remediation/problems-page';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'مشکلات سئو' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const sites = await settle(endpoints.sites());
  return <PageContainer pageTitle='مشکلات سئو' pageDescription='برای هر مشکل روش‌های رفع را بررسی و روش دلخواه را اجرا کنید.'>
    {sites.error ? <BackendError error={sites.error} /> : sites.data?.length
      ? <ProblemsPage sites={sites.data.map((s) => ({ site_id: s.site_id, name: s.name }))} initialSiteId={sites.data.find((s) => s.site_id === site)?.site_id ?? sites.data[0].site_id} />
      : <p>ابتدا یک سایت بسازید.</p>}
  </PageContainer>;
}
