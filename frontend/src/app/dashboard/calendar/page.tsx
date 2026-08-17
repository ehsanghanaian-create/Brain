import { RoadmapPage } from '@/components/seo-brain/roadmap-page';

export const metadata = { title: 'تقویم محتوایی' };

export default function Page() {
  return (
    <RoadmapPage
      title='تقویم محتوایی'
      description='برنامه‌ریزی محتوا با نمای ماهانه/هفتگی و درگ‌ودراپ'
      phase='فاز ۷'
      features={[
        'ورود از Google Sheet / CSV',
        'تقویم داخلی با نمای ماه و هفته',
        'اتصال هر ورودی به کلمه کلیدی و آیتم محتوا'
      ]}
    />
  );
}
