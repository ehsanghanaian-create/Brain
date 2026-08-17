import { RoadmapPage } from '@/components/seo-brain/roadmap-page';

export const metadata = { title: 'گزارش‌ها' };

export default function Page() {
  return (
    <RoadmapPage
      title='گزارش‌ها'
      description='گزارش‌های سئو با خروجی PDF و Markdown'
      phase='فاز ۱۷'
      features={[
        'رشد کلمات کلیدی، عملکرد محتوا، امتیاز لینک، داده GSC، مشکلات سئو'
      ]}
    />
  );
}
