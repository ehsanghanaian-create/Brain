import PageContainer from '@/components/layout/page-container';
import { SiteWizard } from '@/features/sites/components/site-wizard';
import { parseSiteDraft } from '@/features/sites/site-draft';

export const metadata = { title: 'افزودن سایت' };

export default async function NewSitePage({
  searchParams
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const initialValues = parseSiteDraft({ name: params.name, domain: params.domain });
  return (
    <PageContainer
      pageTitle='افزودن سایت'
      pageDescription='ویزارد سه‌مرحله‌ای: اطلاعات سایت → اتصال‌ها و تست مجوز → ایجاد فضای کاری'
    >
      <SiteWizard initialValues={initialValues} />
    </PageContainer>
  );
}
