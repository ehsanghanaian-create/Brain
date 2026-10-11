import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { CommandCenter } from '@/features/graph/components/command-center';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'نقشه تصمیم' };

export default async function GraphPage({ searchParams }: { searchParams: Promise<{ site?: string; mode?: string }> }) {
  const { site, mode } = await searchParams;
  const [sites, portfolio] = await Promise.all([settle(endpoints.sites()), settle(endpoints.portfolioOverview())]);
  if (sites.error) {
    return (
      <PageContainer pageTitle='گراف دانش'>
        <BackendError error={sites.error} />
      </PageContainer>
    );
  }
  const list = sites.data!;
  const initial = list.find((s) => s.site_id === site)?.site_id ?? list[0]?.site_id;
  return (
    <PageContainer pageTitle='نقشه تصمیم سایت' pageDescription='یک سؤال انتخاب کنید، شواهد مرتبط را در گراف ببینید و از همان‌جا وارد اقدام شوید.'>
      {!initial ? <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p> : <CommandCenter sites={list} portfolio={portfolio.data ?? null} initialSiteId={initial} initialMode={mode && ['seo', 'content', 'links', 'planner'].includes(mode) ? mode as 'seo' | 'content' | 'links' | 'planner' : 'seo'} />}
    </PageContainer>
  );
}
