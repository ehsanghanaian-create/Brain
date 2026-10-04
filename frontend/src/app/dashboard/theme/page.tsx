import PageContainer from '@/components/layout/page-container';
import { ThemeStudio } from '@/features/theme/components/theme-studio';

export const metadata = { title: 'تم داشبورد' };
export default function Page() {
  return <PageContainer pageTitle='تم داشبورد' pageDescription='ظاهر، رنگ و حالت نمایش پنل را تنظیم کنید.'><ThemeStudio /></PageContainer>;
}
