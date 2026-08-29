import { AdsDataDashboard } from '@/features/ads-data/ads-data-dashboard';
import type { Metadata } from 'next';

const defaultSiteId = process.env.ADS_DASHBOARD_SITE_ID ?? 'modirankhodro-emdad.com';
const defaultSiteLabel = process.env.ADS_DASHBOARD_SITE_LABEL ?? defaultSiteId;

export const metadata: Metadata = {
  title: `رفتار زنده کاربران ${defaultSiteLabel} | SEO Brain`,
  description: `داشبورد خصوصی رفتار و مسیر کاربران ${defaultSiteLabel}`,
  robots: { index: false, follow: false, nocache: true }
};

export default function AdsDataPage() {
  return <main className='bg-background min-h-screen'><AdsDataDashboard siteId={defaultSiteId} siteLabel={defaultSiteLabel} /></main>;
}
