import PageContainer from '@/components/layout/page-container';
import { ManagementDashboard } from '@/features/workspace/components/management-dashboard';

export const metadata = { title: 'داشبورد مدیریت تیم' };

export default function TeamManagementPage() {
  return <PageContainer pageTitle='مدیریت تیم' pageDescription='تصمیم‌های امروز و کارهای هر نفر، یک‌جا و قابل پیگیری'>
    <ManagementDashboard />
  </PageContainer>;
}
