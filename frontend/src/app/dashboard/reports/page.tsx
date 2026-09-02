import { BackendError } from '@/components/seo-brain/backend-error';
import { SiteReportCenter } from '@/features/reports/components/site-report-center';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'گزارش سایت' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const result = await settle(endpoints.sites());
  const list = result.data ?? [];
  const initial = list.find((s) => s.site_id === site)?.site_id ?? list[0]?.site_id;
  return (
    <div className='space-y-4'>
      {result.error && <BackendError error={result.error} />}
      {!initial ? (
        <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p>
      ) : (
        <SiteReportCenter sites={list} initialSiteId={initial} />
      )}
    </div>
  );
}
