import PageContainer from '@/components/layout/page-container';
import { CallCenterPage } from '@/features/call-center/components/call-center-page';

export const metadata = { title: 'کال‌سنتر' };
export default function Page() {
  return <PageContainer pageTitle='کال‌سنتر' pageDescription='ثبت تماس‌ها و پایش جداگانهٔ سئو، ادز، منطقه و مدل خودرو'><CallCenterPage /></PageContainer>;
}
