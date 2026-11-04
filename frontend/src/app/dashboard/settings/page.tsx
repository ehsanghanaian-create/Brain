import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { BackendError } from '@/components/seo-brain/backend-error';
import { BrainNetwork } from '@/features/network/components/brain-network';
import { endpoints, settle } from '@/lib/api/client';
import Link from 'next/link';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'تنظیمات' };

export default async function SettingsPage() {
  const health = await settle(endpoints.health());
  return <PageContainer pageTitle='تنظیمات و اتصال‌ها' pageDescription='منبع داده را بررسی کنید و تنظیمات مربوط به هر سایت را از پروندهٔ همان سایت تغییر دهید.'>
    <div className='space-y-5'>
      <div className='grid gap-3 md:grid-cols-3'>
        {[
          { href: '/dashboard/sites', title: 'اتصال حساب‌ها و سایت', text: 'وضعیت وردپرس، Search Console و GA4؛ اتصال دوباره و تاریخ آخرین داده.' },
          { href: '/dashboard/rank-tracking', title: 'تنظیم پایش رتبه', text: 'کلمات تحت پایش، ساعت بررسی، دستگاه و عمق نتایج گوگل.' },
          { href: '/dashboard/calendar', title: 'نویسنده و انتشار محتوا', text: 'تنظیم نویسندهٔ هوش مصنوعی و بررسی برنامهٔ انتشار در تقویم.' }
        ].map((item) => <Link key={item.href} href={item.href} className='rounded-xl border bg-card p-5 transition-colors hover:border-primary focus-visible:outline-2 focus-visible:outline-ring'><h2 className='text-base font-semibold text-primary'>{item.title} ←</h2><p className='mt-2 text-sm leading-7 text-muted-foreground'>{item.text}</p></Link>)}
      </div>
      <Card><CardHeader><div className='flex flex-wrap items-center justify-between gap-3'><CardTitle>ارتباط داشبورد با سرویس داده</CardTitle><Badge variant={health.data ? 'secondary' : 'destructive'}>{health.data ? 'متصل' : 'دریافت وضعیت ناموفق'}</Badge></div><CardDescription>این وضعیت فقط دسترسی به سرویس را نشان می‌دهد؛ تازگی آمار هر سایت را جداگانه بررسی کنید.</CardDescription></CardHeader>
        <CardContent>{health.error && <BackendError error={health.error} />}{health.data && <details className='text-sm'><summary className='min-h-11 cursor-pointer'>جزئیات فنی برای پشتیبانی</summary><dl className='mt-2 grid grid-cols-2 gap-3 rounded-lg bg-muted p-4'><dt>نسخهٔ سرویس</dt><dd dir='ltr'>{health.data.version}</dd><dt>پایگاه داده</dt><dd>{health.data.database}</dd><dt>تغییرات ساختار اعمال‌شده</dt><dd>{health.data.migrations.applied.length.toLocaleString('fa-IR')}</dd><dt>در انتظار اعمال</dt><dd>{health.data.migrations.pending.length.toLocaleString('fa-IR')}</dd></dl></details>}</CardContent>
      </Card>
      <details className='rounded-xl border bg-card p-5'><summary className='min-h-11 cursor-pointer font-semibold'>نقشهٔ اتصال سرویس‌ها</summary><p className='mb-4 text-sm leading-7 text-muted-foreground'>ارتباط نویسنده، وردپرس و حساب‌های گوگل هر سایت را اینجا ببینید. برای تغییر اتصال‌ها، پروندهٔ سایت را باز کنید.</p><BrainNetwork /></details>
    </div>
  </PageContainer>;
}
