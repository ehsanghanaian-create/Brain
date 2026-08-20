'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError, endpoints, type GscSyncStatus, type WpSyncQueued } from '@/lib/api/client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { gscStepRows, gscSyncView } from '../gsc-sync';
import { queueMessage } from '../wp-sync';

/**
 * GSC Sync Card — property · آخرین sync · بازه داده · counters (کوئری‌ها/مهم/صفحات/ردیف‌ها) · «همگام‌سازی» · step progress.
 * Runs as a job on the backend (POST …/gsc/sync); this card only polls GET …/gsc/sync/status.
 */
export function GscSyncCard({ siteId, refreshKey = 0 }: { siteId: string; refreshKey?: number }) {
  const [status, setStatus] = useState<GscSyncStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const s = await endpoints.gscSyncStatus(siteId);
      setStatus(s);
      setError(null);
      return s;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      return null;
    }
  }, [siteId]);

  useEffect(() => { void load(); }, [load, refreshKey]);

  const view = gscSyncView(status, { busy });
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (view.shouldPoll) timer.current = setTimeout(() => { void load(); }, 2000);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [view.shouldPoll, status, load]);

  async function start() {
    setBusy(true);
    try {
      const r: WpSyncQueued = await endpoints.gscSyncStart(siteId, {});
      const m = queueMessage(r);
      (m.ok ? toast.success : toast.error)(m.text);
      await load();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      setError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  }

  const rows = gscStepRows(status);
  const dot = (st: string) => (st === 'done' ? 'bg-emerald-500' : st === 'failed' ? 'bg-red-500' : st === 'running' ? 'bg-amber-500 animate-pulse' : st === 'skipped' ? 'bg-slate-400' : 'bg-slate-200');

  return (
    <Card data-testid='gsc-sync-card'>
      <CardHeader>
        <CardTitle className='flex flex-wrap items-center justify-between gap-2'>
          <span>همگام‌سازی Search Console</span>
          <Badge variant={view.running ? 'default' : status?.status === 'succeeded' ? 'secondary' : status?.status === 'not_authorized' || status?.status === 'failed' ? 'destructive' : 'outline'}>{view.statusFa}</Badge>
        </CardTitle>
        <CardDescription>
          داده کوئری/صفحه از Search Console خوانده می‌شود، سپس فرصت‌های کلمات کلیدی، اسنپ‌شات عملکرد محتوا و گراف به‌روز می‌شوند. اجرا همیشه به‌صورت job در پس‌زمینه است.
          {status?.property && <span className='block' dir='ltr'>property: {status.property}</span>}
          {view.dateRange && <span className='block' dir='ltr'>بازه داده: {view.dateRange}</span>}
          {view.lastSync && <span className='block' dir='ltr'>آخرین همگام‌سازی: {new Date(view.lastSync).toLocaleString('fa-IR')}</span>}
        </CardDescription>
      </CardHeader>
      <CardContent className='grid gap-3'>
        <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
          {view.counters.map((c) => (
            <div key={c.key} className='rounded-md border p-2 text-center' data-testid={`gsc-count-${c.key}`}>
              <div className='text-xl font-semibold' dir='ltr'>{c.value.toLocaleString('fa-IR')}</div>
              <div className='text-muted-foreground text-xs'>{c.fa}</div>
            </div>
          ))}
        </div>

        <div className='flex flex-wrap items-center gap-2'>
          <Button type='button' size='sm' disabled={!view.canSync} title={view.syncDisabledReason ?? undefined} onClick={() => void start()} data-testid='gsc-sync-start'>
            همگام‌سازی
          </Button>
          <Button type='button' size='sm' variant='ghost' disabled={busy} onClick={() => void load()}>به‌روزرسانی وضعیت</Button>
          {view.syncDisabledReason && !view.running && <span className='text-muted-foreground text-xs'>{view.syncDisabledReason}</span>}
        </div>

        {(view.running || (status?.steps?.length ?? 0) > 0) && (
          <div className='rounded-md border p-2 text-xs'>
            <div className='mb-1 flex items-center justify-between'>
              <span>{view.running ? view.stepFa : 'آخرین اجرا'}</span>
              <span dir='ltr'>{view.percent}%</span>
            </div>
            <div className='bg-muted h-1.5 w-full overflow-hidden rounded'>
              <div className='h-full bg-emerald-500 transition-all' style={{ width: `${view.percent}%` }} data-testid='gsc-progress' />
            </div>
            <ul className='mt-2 grid gap-1 sm:grid-cols-2'>
              {rows.map((r) => (
                <li key={r.key} className='flex items-center gap-1'>
                  <span className={`inline-block h-2 w-2 rounded-full ${dot(r.status)}`} />
                  <span>{r.fa}</span>
                  {r.info && <span className='text-muted-foreground truncate' dir='ltr' title={r.info}>· {r.info}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}

        {(status?.errors?.length ?? 0) > 0 && (
          <ul className='rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950/30' data-testid='gsc-errors'>
            {status!.errors.map((e, i) => <li key={i} dir='ltr'>{e}</li>)}
          </ul>
        )}
        {error && <p className='text-destructive text-xs'>{error}</p>}
      </CardContent>
    </Card>
  );
}
