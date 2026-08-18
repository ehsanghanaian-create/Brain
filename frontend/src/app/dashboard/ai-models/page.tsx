import PageContainer from '@/components/layout/page-container';
import { AiModelsPage } from '@/features/ai-models/components/ai-models-page';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'مدل‌های AI' };

export default async function Page() {
  const sites = await settle(endpoints.sites());
  return (
    <PageContainer pageTitle='مدل‌های AI' pageDescription='ارائه‌دهنده‌ها (Claude، ChatGPT، Gemini، OpenRouter، مدل محلی) با ذخیره امن کلیدها؛ کاتالوگ مدل‌ها، مسیردهی وظایف با سیاست و زنجیره جایگزین، مصرف و بودجه، کتابخانه پرامپت نسخه‌بندی‌شده و یادگیری AI (فقط پیشنهاد).'>
      <AiModelsPage sites={sites.data ?? []} />
    </PageContainer>
  );
}
