import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { AiContentTest } from '@/features/ai-workspace/components/ai-content-test';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'آزمایش تولید محتوا با AI' };

export default async function Page({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const sites = await settle(endpoints.sites());
  if (sites.error) return <PageContainer pageTitle='آزمایش تولید محتوا با AI'><BackendError error={sites.error} /></PageContainer>;
  const list = sites.data!;
  const initial = list.find((s) => s.site_id === site)?.site_id ?? list[0]?.site_id;
  return (
    <PageContainer pageTitle='آزمایش تولید محتوا با AI' pageDescription='فضای موقت برای آزمایش تولید محتوا پیش از خط لوله کامل عامل‌ها: مشخصات را وارد کنید، ارائه‌دهنده/مدل را انتخاب کنید (Echo یا ارائه‌دهنده پیکربندی‌شده)، برآورد توکن/هزینه را ببینید و خروجی را در نماهای پیش‌نمایش/Markdown/تحلیل سئو/پرامپت/متادیتا بررسی کنید. خروجی فقط با اقدام شما به‌عنوان پیش‌نویس ذخیره می‌شود؛ هیچ انتشاری انجام نمی‌شود.'>
      {!initial ? <p className='text-muted-foreground text-sm'>ابتدا یک سایت بسازید.</p> : <AiContentTest sites={list} initialSiteId={initial} />}
    </PageContainer>
  );
}
