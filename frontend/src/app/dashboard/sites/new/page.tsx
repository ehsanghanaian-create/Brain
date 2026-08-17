import PageContainer from '@/components/layout/page-container';
import { SiteWizard } from '@/features/sites/components/site-wizard';

export const metadata = { title: 'افزودن سایت' };

export default function NewSitePage() {
  return (
    <PageContainer pageTitle='افزودن سایت' pageDescription='ویزارد سه‌مرحله‌ای: اطلاعات سایت → اتصال‌ها و تست مجوز → ایجاد فضای کاری'>
      <SiteWizard />
    </PageContainer>
  );
}
