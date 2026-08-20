'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ApiError, endpoints, type AutoSyncPlan } from '@/lib/api/client';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { autoSyncLine } from '../auto-sync';

/** یک سطر بالای مرکز اتصال‌ها: وضعیت به‌روزرسانی خودکار + بعدی + کلید روشن/خاموش — بدون جزئیات فنی. */
export function AutoSyncLine({ siteId }: { siteId: string }) {
  const [plan, setPlan] = useState<AutoSyncPlan | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { void endpoints.autoSyncGet(siteId).then(setPlan).catch(() => null); }, [siteId]);

  async function toggle() {
    if (!plan) return;
    setBusy(true);
    try {
      const p = await endpoints.autoSyncPut(siteId, { enabled: !plan.enabled });
      setPlan(p);
      toast.success(p.enabled ? 'به‌روزرسانی خودکار روشن شد' : 'به‌روزرسانی خودکار خاموش شد');
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!plan) return null;
  return (
    <div className='flex flex-wrap items-center gap-2 text-xs' data-testid='auto-sync-line'>
      <Badge variant={plan.enabled ? 'secondary' : 'outline'}>{autoSyncLine(plan)}</Badge>
      <Button type='button' size='sm' variant='ghost' disabled={busy} onClick={() => void toggle()}>
        {plan.enabled ? 'خاموش کردن' : 'روشن کردن'}
      </Button>
    </div>
  );
}
