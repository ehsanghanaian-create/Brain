import PageContainer from '@/components/layout/page-container';
import { OnboardingWizard } from '@/features/onboarding/components/onboarding-wizard';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'راه‌اندازی سریع' };

export default function OnboardingPage() {
  return (
    <PageContainer pageTitle='راه‌اندازی سریع' pageDescription='در چهار قدم، سایت‌هایتان را وصل کنید و تحلیل سئو را شروع کنید — بدون هیچ تنظیم فنی.'>
      <OnboardingWizard />
    </PageContainer>
  );
}
