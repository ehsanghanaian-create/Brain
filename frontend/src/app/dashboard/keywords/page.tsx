import { RoadmapPage } from '@/components/seo-brain/roadmap-page';

export const metadata = { title: 'کلمات کلیدی' };

export default function Page() {
  return (
    <RoadmapPage
      title='کلمات کلیدی'
      description='ورود از CSV/Excel/Google Sheet، خوشه‌بندی و نقشه موضوعی'
      phase='فاز ۵'
      features={[
        'ورود فایل با نگاشت ستون‌ها (Keyword, Intent, Volume, Difficulty, Priority, Target URL, Status)',
        'خوشه‌بندی و روابط کلمات کلیدی',
        'اتصال کلمات کلیدی به گراف دانش'
      ]}
    />
  );
}
