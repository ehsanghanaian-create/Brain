import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { ActionInboxPage } from '@/features/opportunities/components/action-inbox-page';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'مرکز فرصت‌های سئو' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const sites = await settle(endpoints.sites());
  if (sites.error) return <PageContainer pageTitle='مرکز فرصت‌های سئو'><BackendError error={sites.error} /></PageContainer>;
  const initialSiteId = sites.data!.some((item) => item.site_id === site) ? site! : '';
  return <PageContainer pageTitle='مرکز فرصت‌های سئو' pageDescription='پرونده، کلمه و لینک در یک صف قابل ردیابی'><ActionInboxPage sites={sites.data!} initialSiteId={initialSiteId} /></PageContainer>;
}
