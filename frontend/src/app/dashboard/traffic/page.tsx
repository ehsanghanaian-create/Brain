import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { TrafficPage } from '@/features/traffic/components/traffic-page';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'ترافیک و تماس‌ها' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const sites = await settle(endpoints.sites());
  if (sites.error)
    return (
      <PageContainer pageTitle='ترافیک و تماس‌ها'>
        <BackendError error={sites.error} />
      </PageContainer>
    );
  const list = sites.data!;
  const initial = list.find((s) => s.site_id === site)?.site_id ?? list[0]?.site_id;
  return (
    <PageContainer
      pageTitle='ترافیک و تماس‌ها'
      pageDescription='ورودی ارگانیک، رفتار کاربر و کلیک روی شماره تماس — از ترکر فرست‌پارتی قالب، کنار داده سرچ‌کنسول.'
    >
      {!initial ? <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p> : <TrafficPage sites={list} initialSiteId={initial} />}
    </PageContainer>
  );
}
