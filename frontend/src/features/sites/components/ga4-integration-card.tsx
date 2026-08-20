'use client';

import { type ConnectionResult } from '@/lib/api/client';
import { ConnectionTester } from './connection-tester';
import { IntegrationCard } from './integration-card';

const STATUS_FA: Record<string, string> = { ok: 'متصل', not_authorized: 'بدون مجوز', not_configured: 'تنظیم نشده', error: 'خطا' };

/**
 * GA4 integration card — placeholder: فقط اتصال/تست property؛ pipeline همگام‌سازی GA4 هنوز ساخته نشده
 * (طبق audit: نیازمند scope ‏analytics.readonly، client و جدول داده — فاز بعدی).
 */
export function Ga4IntegrationCard({ siteId, initialValue, initialResult }: {
  siteId: string;
  initialValue?: string | null;
  initialResult?: ConnectionResult;
}) {
  const st = initialResult?.status;
  return (
    <IntegrationCard
      kind='ga4'
      title='Google Analytics 4'
      badge={st ? (STATUS_FA[st] ?? st) : 'تست نشده'}
      badgeVariant={st === 'ok' ? 'secondary' : st === 'error' || st === 'not_authorized' ? 'destructive' : 'outline'}
      description='اتصال به GA4 Data API (فقط‌خواندنی). همگام‌سازی داده‌ها — sessions، کاربران و conversionها — در فاز بعدی به همین کارت اضافه می‌شود.'
    >
      <ConnectionTester siteId={siteId} kind='ga4' label='GA4 Property ID' hint='123456789' initialValue={initialValue} initialResult={initialResult} />
      <div className='text-muted-foreground rounded-md border border-dashed p-3 text-xs' data-testid='ga4-placeholder'>
        همگام‌سازی GA4 هنوز فعال نیست. پس از فعال‌سازی: دریافت روزانه sessions / users / conversions per page، اسنپ‌شات عملکرد محتوا و اتصال به گراف — با همان الگوی Search Console.
      </div>
    </IntegrationCard>
  );
}
