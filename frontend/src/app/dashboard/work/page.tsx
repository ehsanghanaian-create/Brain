import PageContainer from '@/components/layout/page-container';
import { WorkCommandCenter } from '@/features/workspace/components/work-command-center';

export const metadata = { title: 'میز عملیات و مدیریت تیم' };
export default function WorkPage() {
  return <PageContainer pageTitle='میز عملیات و مدیریت تیم' pageDescription='مدیریت کارهای تمام سایت‌ها، تیم‌ها، مسئولیت‌ها، موعدها و مسیر اجرا'>
    <WorkCommandCenter />
  </PageContainer>;
}
