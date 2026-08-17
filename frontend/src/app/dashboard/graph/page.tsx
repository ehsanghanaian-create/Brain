import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { CommandCenter } from '@/features/graph/components/command-center';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'گراف دانش' };

export default async function GraphPage({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const sites = await settle(endpoints.sites());
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
    <PageContainer pageTitle='گراف دانش — مرکز فرماندهی سئو' pageDescription='نقشه سئو، نقشه محتوا و نقشه لینک داخلی؛ روی هر گره کلیک کنید تا داده‌های سئوی آن را ببینید.'>
      {!initial ? <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p> : <CommandCenter sites={list} initialSiteId={initial} />}
    </PageContainer>
  );
}
