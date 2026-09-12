import { AdsDataDashboard } from '@/features/ads-data/ads-data-dashboard';
import type { Metadata } from 'next';

const defaultSiteId = process.env.ADS_DASHBOARD_SITE_ID ?? 'modirankhodro-emdad.com';
const defaultSiteLabel = process.env.ADS_DASHBOARD_SITE_LABEL ?? defaultSiteId;

export const metadata: Metadata = {
  title: `رفتار زنده کاربران ${defaultSiteLabel} | SEO Brain`,
  description: `داشبورد خصوصی رفتار و مسیر کاربران ${defaultSiteLabel}`,
  robots: { index: false, follow: false, nocache: true }
};

export const dynamic = 'force-dynamic';

/** «داده زنده تبلیغات» — سایت از ?site= می‌آید (پیش‌فرض: env یا مدیران خودرو). */
export default async function AdsDataPage({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams;
  const siteId = site?.trim() || defaultSiteId;
  const siteLabel = siteId === defaultSiteId ? defaultSiteLabel : siteId;
  return <main className='bg-background min-h-screen'><AdsDataDashboard siteId={siteId} siteLabel={siteLabel} /></main>;
}
