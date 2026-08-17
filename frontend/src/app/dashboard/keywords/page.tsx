import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { KeywordsPage } from '@/features/keywords/components/keywords-page';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'کلمات کلیدی' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const sites = await settle(endpoints.sites());
  if (sites.error) return <PageContainer pageTitle='کلمات کلیدی'><BackendError error={sites.error} /></PageContainer>;
  const list = sites.data!;
  const initial = list.find((s) => s.site_id === site)?.site_id ?? list[0]?.site_id;
  return (
    <PageContainer pageTitle='کلمات کلیدی — هوش کلمات کلیدی' pageDescription='ورود از CSV/Excel/Google Sheet، اینتنت و اولویت، خوشه‌بندی و نقشه موضوعی، اتصال به Search Console و گراف دانش، فرصت‌های سئو.'>
      {!initial ? <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p> : <KeywordsPage sites={list} initialSiteId={initial} />}
    </PageContainer>
  );
}
