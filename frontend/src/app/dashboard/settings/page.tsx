import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { BackendError } from '@/components/seo-brain/backend-error';
import { endpoints, settle } from '@/lib/api/client';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'تنظیمات' };

export default async function SettingsPage() {
  const health = await settle(endpoints.health());
  const base = process.env.SEO_BRAIN_API_URL ?? 'http://127.0.0.1:8000';
  return (
    <PageContainer pageTitle='تنظیمات' pageDescription='اتصال به بک‌اند و وضعیت سیستم'>
      <div className='grid gap-4 lg:grid-cols-2'>
        <Card>
          <CardHeader>
            <CardTitle>بک‌اند SEO Brain</CardTitle>
            <CardDescription>
              مقادیر از <code dir='ltr'>frontend/.env.local</code> خوانده می‌شوند؛ توکن فقط سمت سرور استفاده می‌شود.
            </CardDescription>
          </CardHeader>
          <CardContent className='space-y-2 text-sm'>
            <div className='flex justify-between'>
              <span>آدرس</span>
              <code dir='ltr'>{base}</code>
            </div>
            <div className='flex justify-between'>
              <span>توکن API</span>
              <span>{process.env.SEO_BRAIN_API_TOKEN ? 'تنظیم شده' : 'تنظیم نشده (حالت باز روی loopback)'}</span>
            </div>
            <div className='flex justify-between'>
              <span>وضعیت</span>
              {health.data ? <Badge>متصل · v{health.data.version}</Badge> : <Badge variant='destructive'>قطع</Badge>}
            </div>
            {health.data && (
              <div className='flex justify-between'>
                <span>پایگاه داده / مهاجرت‌ها</span>
                <code dir='ltr'>
                  {health.data.database} · {health.data.migrations.applied.join(', ')}
                </code>
              </div>
            )}
            {health.error && <BackendError error={health.error} />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>راهنما</CardTitle>
            <CardDescription>راهنمای کامل فارسی هر بخش در فاز ۱۸ اضافه می‌شود.</CardDescription>
          </CardHeader>
          <CardContent className='space-y-1 text-sm'>
            <p>
              اجرای بک‌اند: <code dir='ltr'>python backend\cli\api.py</code>
            </p>
            <p>
              مستندات API: <code dir='ltr'>{base}/api/docs</code>
            </p>
            <p>
              قرارداد فرانت/بک‌اند: <code dir='ltr'>docs/seo-brain/04-frontend-contract.md</code>
            </p>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
