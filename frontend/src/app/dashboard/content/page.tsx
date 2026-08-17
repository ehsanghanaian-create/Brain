import { RoadmapPage } from '@/components/seo-brain/roadmap-page';

export const metadata = { title: 'مغز محتوا' };

export default function Page() {
  return (
    <RoadmapPage
      title='مغز محتوا'
      description='خط لوله محتوا از ایده تا انتشار به شکل کانبان'
      phase='فاز ۶'
      features={[
        'مراحل: ایده → تحقیق → بریف آماده → نگارش → بازبینی → تأیید → منتشرشده',
        'تولید بریف و پیش‌نویس با ارکستریتور AI (با ذخیره منشأ)',
        'انتشار فقط در حالت نیمه‌خودکار/خودکار و با تأیید شما'
      ]}
    />
  );
}
