import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { AiStudio } from '@/features/ai-studio/components/ai-studio';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'استودیوی AI' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string; content?: string }> }) {
  const { site, content } = await searchParams;
  const sites = await settle(endpoints.sites());
  if (sites.error) return <PageContainer pageTitle='استودیوی AI'><BackendError error={sites.error} /></PageContainer>;
  const list = sites.data!;
  const initial = list.find((s) => s.site_id === site)?.site_id ?? list[0]?.site_id;
  return (
    <PageContainer pageTitle='استودیوی AI' pageDescription='تولید محتوا با چند عامل (تحقیق → ساختار → نگارش بخش‌به‌بخش → راستی‌آزمایی → سئو → لینک‌سازی → بازبینی) با تزریق حافظه سایت. خروجی فقط پیش‌نویس است؛ امتیاز، بازبینی و تأیید انسانی در مغز محتوا انجام می‌شود. انتشار خودکار وجود ندارد.'>
      {!initial ? <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p> : <AiStudio sites={list} initialSiteId={initial} initialContentId={content ? Number(content) : undefined} />}
    </PageContainer>
  );
}
