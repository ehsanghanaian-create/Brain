'use client';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { ApiError, endpoints, type SiteMission } from '@/lib/api/client';
import { IconArrowLeft, IconTargetArrow } from '@tabler/icons-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';

export function SiteMissionForm({ siteId, initial }: { siteId: string; initial: SiteMission }) {
  const router = useRouter();
  const [objective, setObjective] = useState(initial.objective);
  const [successMetric, setSuccessMetric] = useState(initial.success_metric);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await endpoints.putSiteMission(siteId, { objective, success_metric: successMetric });
      toast.success('هدف سایت ذخیره شد');
      router.refresh();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className='rounded-2xl border border-sky-500/20 bg-gradient-to-bl from-sky-500/[0.08] via-card to-card p-5 shadow-sm' aria-labelledby='site-mission-title'>
      <div className='flex flex-wrap items-start justify-between gap-3'>
        <div>
          <div className='flex items-center gap-2 text-sky-700 dark:text-sky-300'><IconTargetArrow className='size-5' /><h3 id='site-mission-title' className='font-semibold'>هدف این سایت</h3></div>
          <p className='text-muted-foreground mt-1 text-xs leading-5'>هدف و معیار را تیم تعیین می‌کند؛ پیشرفت فقط با دادهٔ گزارش‌ها سنجیده می‌شود.</p>
        </div>
        <Link href={`/dashboard/graph?site=${encodeURIComponent(siteId)}`} className='inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline'>بررسی نقشه سایت <IconArrowLeft className='size-4' /></Link>
      </div>
      <div className='mt-4 grid gap-3 lg:grid-cols-[1.4fr_1fr]'>
        <label htmlFor='site-objective' className='grid gap-1.5 text-xs font-medium'>هدف کاری
          <Textarea id='site-objective' value={objective} onChange={(event) => setObjective(event.target.value)} maxLength={300} rows={2} placeholder='مثلاً افزایش ورودی ارگانیک صفحات دسته‌بندی اصلی' />
        </label>
        <label htmlFor='site-success-metric' className='grid content-start gap-1.5 text-xs font-medium'>معیار موفقیت
          <Input id='site-success-metric' value={successMetric} onChange={(event) => setSuccessMetric(event.target.value)} maxLength={200} placeholder='مثلاً کلیک ارگانیک همان صفحات در GSC' />
          <span className='text-muted-foreground font-normal'>این معیار توضیح است؛ عددی به‌طور خودکار از آن محاسبه نمی‌شود.</span>
        </label>
      </div>
      <Button onClick={save} disabled={busy || (objective === initial.objective && successMetric === initial.success_metric)} size='sm' className='mt-3'>{busy ? 'در حال ذخیره…' : 'ذخیره هدف'}</Button>
    </section>
  );
}
