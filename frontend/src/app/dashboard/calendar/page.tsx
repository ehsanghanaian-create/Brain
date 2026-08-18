import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { CalendarPage } from '@/features/content/components/calendar-page';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'تقویم محتوایی' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const sites = await settle(endpoints.sites());
  if (sites.error) return <PageContainer pageTitle='تقویم محتوایی'><BackendError error={sites.error} /></PageContainer>;
  const list = sites.data!;
  const initial = list.find((s) => s.site_id === site)?.site_id ?? list[0]?.site_id;
  return (
    <PageContainer pageTitle='تقویم محتوایی' pageDescription='نمای ماهانه (تقویم شمسی) و فهرست؛ محتوا را بین روزها بکشید تا زمان‌بندی شود. وضعیت هر آیتم با رنگ مشخص است.'>
      {!initial ? <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p> : <CalendarPage sites={list} initialSiteId={initial} />}
    </PageContainer>
  );
}
