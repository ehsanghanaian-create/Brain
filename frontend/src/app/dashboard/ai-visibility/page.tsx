import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { AiVisibilityDashboard } from '@/features/ai-visibility/ai-visibility-dashboard';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'جست‌وجوی هوش مصنوعی' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const result = await settle(endpoints.sites());
  const sites = result.data ?? [];
  const initialSiteId = sites.find((item) => item.site_id === site)?.site_id ?? sites[0]?.site_id;
  return (
    <PageContainer
      pageTitle='جست‌وجوی هوش مصنوعی'
      pageDescription='از دیده‌شدن در پاسخ‌ها تا ورود و خرید؛ هر عدد با منبع خودش'
    >
      {result.error && <BackendError error={result.error} />}
      {initialSiteId ? (
        <AiVisibilityDashboard sites={sites} initialSiteId={initialSiteId} />
      ) : (
        <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p>
      )}
    </PageContainer>
  );
}
