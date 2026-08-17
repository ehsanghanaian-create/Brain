import { RoadmapPage } from '@/components/seo-brain/roadmap-page';

export const metadata = { title: 'مدل‌های AI' };

export default function Page() {
  return (
    <RoadmapPage
      title='مدل‌های AI'
      description='ارائه‌دهنده‌ها، مسیردهی وظایف و کتابخانه پرامپت'
      phase='فاز ۹–۱۱'
      features={[
        'Claude، OpenAI، Gemini، OpenRouter، Ollama، API سفارشی',
        'مسیردهی هر وظیفه به مدل مشخص با مدل جایگزین',
        'پرامپت‌ها با متغیرهای {{keyword}}، {{intent}}، {{entities}}، {{brand}}'
      ]}
    />
  );
}
