import { RoadmapPage } from '@/components/seo-brain/roadmap-page';

export const metadata = { title: 'لینک‌سازی داخلی' };

export default function Page() {
  return (
    <RoadmapPage
      title='لینک‌سازی داخلی'
      description='موتور پیشنهاد لینک داخلی و یادگیری الگوها'
      phase='فاز ۱۳–۱۴'
      features={[
        'تحلیل اعتبار صفحه، لینک‌های ورودی/خروجی، ارتباط موضوعی',
        'پیشنهاد مبدأ، مقصد، انکرتکست و دلیل',
        'یادگیری الگوهای لینک‌دهی از مقالات قبلی'
      ]}
    />
  );
}
