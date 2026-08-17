import { RoadmapPage } from '@/components/seo-brain/roadmap-page';

export const metadata = { title: 'گراف دانش' };

export default function Page() {
  return (
    <RoadmapPage
      title='گراف دانش'
      description='نمایش تعاملی گراف با React Flow — جست‌وجو، فیلتر، زوم و جزئیات هر گره در سایدبار'
      phase='فاز ۴'
      features={[
        'نمایش گره‌های صفحه، کوئری، موجودیت، اسکیما و محتوا',
        'جست‌وجو و فیلتر بر اساس نوع گره و رابطه',
        'کلیک روی گره: جایگاه، CTR، ایمپرشن، کلیک، اینتنت، صفحه هدف'
      ]}
    />
  );
}
