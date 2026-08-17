import { RoadmapPage } from '@/components/seo-brain/roadmap-page';

export const metadata = { title: 'فرصت‌های سئو' };

export default function Page() {
  return (
    <RoadmapPage
      title='فرصت‌های سئو'
      description='تحلیل فرصت‌ها و پیشنهاد اقدام'
      phase='فاز ۱۵'
      features={[
        'صفحات جایگاه ۵–۲۰، CTR پایین، صفحات ضعیف، لینک‌های ازدست‌رفته، شکاف محتوا',
        'اقدام پیشنهادی: تولید محتوا / افزودن لینک / به‌روزرسانی صفحه'
      ]}
    />
  );
}
