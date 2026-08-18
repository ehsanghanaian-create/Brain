import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { LinkingPage } from '@/features/linking/components/linking-page';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'لینک‌سازی داخلی' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const sites = await settle(endpoints.sites());
  if (sites.error) return <PageContainer pageTitle='لینک‌سازی داخلی'><BackendError error={sites.error} /></PageContainer>;
  const list = sites.data!;
  const initial = list.find((s) => s.site_id === site)?.site_id ?? list[0]?.site_id;
  return (
    <PageContainer pageTitle='لینک‌سازی داخلی — موتور هوشمند' pageDescription='پیشنهادهای توضیح‌پذیر لینک داخلی بر پایه گراف دانش، کلمات کلیدی، موجودیت‌ها، اینتنت و سفر کاربر؛ صفحات یتیم و ضعیف؛ امتیاز سلامت لینک؛ یادگیری از تصمیم‌های شما.'>
      {!initial ? <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p> : <LinkingPage sites={list} initialSiteId={initial} />}
    </PageContainer>
  );
}
