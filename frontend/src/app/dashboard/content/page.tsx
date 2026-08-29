import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { ContentBrainPage } from '@/features/content/components/content-brain-page';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'مغز محتوا' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string; content?: string }> }) {
  const { site, content } = await searchParams;
  const sites = await settle(endpoints.sites());
  if (sites.error) return <PageContainer pageTitle='مغز محتوا'><BackendError error={sites.error} /></PageContainer>;
  const list = sites.data!;
  const initial = list.find((s) => s.site_id === site)?.site_id ?? list[0]?.site_id;
  const parsedContent = Number(content);
  const initialContentId = Number.isInteger(parsedContent) && parsedContent > 0 ? parsedContent : null;
  return (
    <PageContainer pageTitle='مغز محتوا' pageDescription='خط لوله محتوا با تأیید انسانی: برنامه‌ریزی → بریف → نگارش → بازبینی → تأیید → انتشار واقعی در وردپرس. دسته‌ها از همان سایت خوانده می‌شوند و زمان‌بندی در خود وردپرس ذخیره می‌شود.'>
      {!initial ? <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p> : <ContentBrainPage sites={list} initialSiteId={initial} initialContentId={initialContentId} />}
    </PageContainer>
  );
}
