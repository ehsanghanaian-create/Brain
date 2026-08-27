import { AdsDataDashboard } from '@/features/ads-data/ads-data-dashboard';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'داده زنده تبلیغات | SEO Brain',
  description: 'داشبورد خصوصی داده زنده ورودی تبلیغات مدیران خودرو',
  robots: { index: false, follow: false, nocache: true }
};

export default function AdsDataPage() {
  return <main className='bg-background min-h-screen'><AdsDataDashboard /></main>;
}

