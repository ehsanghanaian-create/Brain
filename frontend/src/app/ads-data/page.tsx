import { AdsDataDashboard } from '@/features/ads-data/ads-data-dashboard';
import { IpFlowGraph } from '@/features/ip-graph/components/ip-flow-graph';
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
  return (
    <main className='bg-background min-h-screen'>
      <details className='mx-auto max-w-[1600px] px-4 pt-4' open>
        <summary className='cursor-pointer select-none text-sm font-semibold'>گراف IPهای ورودی از تبلیغات — {siteLabel}</summary>
        <p className='text-muted-foreground mt-1 mb-3 text-xs'>کلمه/کمپین ← IP ← صفحهٔ ورود ← تماس. IPهای پرخطر قرمز، زیر نظر نارنجی و تماس‌گرفته‌ها سبز هستند؛ روی هر گره کلیک کنید.</p>
        <IpFlowGraph scope='ads' siteId={siteId} defaultHours={168} height={560} />
      </details>
      <AdsDataDashboard siteId={siteId} siteLabel={siteLabel} />
    </main>
  );
}
