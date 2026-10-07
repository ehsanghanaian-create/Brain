import PageContainer from '@/components/layout/page-container';
import { ManagementDashboard } from '@/features/workspace/components/management-dashboard';

export const metadata = { title: 'داشبورد مدیریت تیم' };

export default function TeamManagementPage() {
  return <PageContainer pageTitle='داشبورد مدیریت تیم' pageDescription='نمای یکپارچهٔ مسئولیت‌ها، فعالیت‌ها و پیشرفت کل تیم'>
    <ManagementDashboard />
  </PageContainer>;
}
