import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { ContentCalendarPage } from '@/features/content-calendar/components/content-calendar-page';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'تقویم محتوا' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string; plan?: string }> }) {
  const { site, plan } = await searchParams;
  const sites = await settle(endpoints.sites());
  if (sites.error) return <PageContainer pageTitle='تقویم محتوا'><BackendError error={sites.error} /></PageContainer>;
  const list = sites.data!;
  const initial = list.find((s) => s.site_id === site)?.site_id ?? list[0]?.site_id;
  const initialPlanId = plan && /^\d+$/.test(plan) ? Number(plan) : undefined;
  return (
    <PageContainer pageTitle='تقویم محتوا' pageDescription='عنوان و کلمهٔ کلیدی را روی یک روز بگذارید، با هوش مصنوعی بنویسید و رأس همان تاریخ در وردپرس منتشر کنید.'>
      {!initial ? <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p> : <ContentCalendarPage sites={list} initialSiteId={initial} initialPlanId={initialPlanId} />}
    </PageContainer>
  );
}
