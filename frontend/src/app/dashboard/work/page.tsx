import { Suspense } from 'react';
import PageContainer from '@/components/layout/page-container';
import { WorkCommandCenter } from '@/features/workspace/components/work-command-center';

export const metadata = { title: 'میز عملیات و مدیریت تیم' };
export default function WorkPage() {
  return <PageContainer pageTitle='میز عملیات و مدیریت تیم' pageDescription='مدیریت کارهای تمام سایت‌ها، تیم‌ها، مسئولیت‌ها، موعدها و مسیر اجرا'>
    <Suspense fallback={<div className='p-6 text-sm'>در حال بارگیری کارها…</div>}><WorkCommandCenter /></Suspense>
  </PageContainer>;
}
