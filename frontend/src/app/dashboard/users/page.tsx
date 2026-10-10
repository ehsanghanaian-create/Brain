import PageContainer from '@/components/layout/page-container';
import { UserManagement } from '@/features/call-center/components/user-management';

export const metadata = { title: 'مدیریت کاربران' };
export default function Page() {
  return <PageContainer pageTitle='مدیریت کاربران' pageDescription='اعضای تیم، نقش‌ها و وضعیت فعالیت را مدیریت کنید.'><UserManagement /></PageContainer>;
}
