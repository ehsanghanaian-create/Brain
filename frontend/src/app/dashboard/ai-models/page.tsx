import PageContainer from '@/components/layout/page-container';
import { AiModelsPage } from '@/features/ai-models/components/ai-models-page';

export const metadata = { title: 'مدل‌های AI' };

export default function Page() {
  return (
    <PageContainer pageTitle='مدل‌های AI' pageDescription='مدیریت ارائه‌دهنده‌ها (Claude، ChatGPT، Gemini، OpenRouter، مدل محلی) با ذخیره امن کلیدها و مسیردهی وظایف به مدل‌ها.'>
      <AiModelsPage />
    </PageContainer>
  );
}
