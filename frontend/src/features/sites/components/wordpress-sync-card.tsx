'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError, endpoints, type WpSyncQueued, type WpSyncStatus } from '@/lib/api/client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { queueMessage, stepRows, wpSyncView } from '../wp-sync';

/**
 * WordPress Sync Card — last sync · counters (دسته‌ها/صفحات/نوشته‌ها/گره‌های گراف) · «شروع همگام‌سازی» · «بازسازی گراف» · step progress.
 * Everything runs as a job on the backend (POST …/wordpress/sync, …/graph/rebuild); this card only polls GET …/wordpress/sync/status.
 */
export function WordPressSyncCard({ siteId, initial, refreshKey = 0 }: { siteId: string; initial?: WpSyncStatus | null; refreshKey?: number }) {
  const [status, setStatus] = useState<WpSyncStatus | null>(initial ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const s = await endpoints.wpSyncStatus(siteId);
      setStatus(s);
      setError(null);
      return s;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      return null;
    }
  }, [siteId]);

  // initial load + reload when the parent signals a change (e.g. connection test queued a job)
  useEffect(() => { void load(); }, [load, refreshKey]);

  // poll while queued/running
  const view = wpSyncView(status, { busy });
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (view.shouldPoll) timer.current = setTimeout(() => { void load(); }, 2000);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [view.shouldPoll, status, load]);

  async function run(fn: () => Promise<WpSyncQueued>) {
    setBusy(true);
    try {
      const r = await fn();
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

  const rows = stepRows(status);
  const dot = (st: string) => (st === 'done' ? 'bg-emerald-500' : st === 'failed' ? 'bg-red-500' : st === 'running' ? 'bg-amber-500 animate-pulse' : st === 'skipped' ? 'bg-slate-400' : 'bg-slate-200');

  return (
    <Card data-testid='wp-sync-card'>
      <CardHeader>
        <CardTitle className='flex flex-wrap items-center justify-between gap-2'>
          <span>همگام‌سازی وردپرس → گراف</span>
          <Badge variant={view.running ? 'default' : status?.status === 'succeeded' ? 'secondary' : status?.status && status.status !== 'never' ? 'destructive' : 'outline'}>{view.statusFa}</Badge>
        </CardTitle>
        <CardDescription>
          دسته‌ها، صفحات و نوشته‌ها از REST وردپرس (فقط‌خواندنی) خوانده می‌شوند، سپس لینک‌ها استخراج و گراف ساخته می‌شود. اجرا همیشه به‌صورت job در پس‌زمینه است.
          {view.lastSync && <span className='block' dir='ltr'>آخرین همگام‌سازی: {new Date(view.lastSync).toLocaleString('fa-IR')}</span>}
        </CardDescription>
      </CardHeader>
      <CardContent className='grid gap-3'>
        <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
          {view.counters.map((c) => (
            <div key={c.key} className='rounded-md border p-2 text-center' data-testid={`wp-count-${c.key}`}>
              <div className='text-xl font-semibold' dir='ltr'>{c.value.toLocaleString('fa-IR')}</div>
              <div className='text-muted-foreground text-xs'>{c.fa}</div>
            </div>
          ))}
        </div>

        <div className='flex flex-wrap items-center gap-2'>
          <Button type='button' size='sm' disabled={!view.canStart} title={view.startDisabledReason ?? undefined} onClick={() => run(() => endpoints.wpSyncStart(siteId, { crawl: true }))} data-testid='wp-sync-start'>
            شروع همگام‌سازی
          </Button>
          <Button type='button' size='sm' variant='outline' disabled={!view.canRebuild} onClick={() => run(() => endpoints.graphRebuild(siteId))} data-testid='wp-graph-rebuild'>
            بازسازی گراف
          </Button>
          <Button type='button' size='sm' variant='ghost' disabled={busy} onClick={() => void load()}>به‌روزرسانی وضعیت</Button>
          {view.startDisabledReason && !view.running && <span className='text-muted-foreground text-xs'>{view.startDisabledReason}</span>}
        </div>

        {(view.running || (status?.steps?.length ?? 0) > 0) && (
          <div className='rounded-md border p-2 text-xs'>
            <div className='mb-1 flex items-center justify-between'>
              <span>{view.running ? view.stepFa : status?.stage === 'graph_only' ? 'آخرین اجرا: بازسازی گراف' : 'آخرین اجرا: همگام‌سازی کامل'}</span>
              <span dir='ltr'>{view.percent}%</span>
            </div>
            <div className='bg-muted h-1.5 w-full overflow-hidden rounded'>
              <div className='h-full bg-emerald-500 transition-all' style={{ width: `${view.percent}%` }} data-testid='wp-progress' />
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
          <ul className='rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950/30'>
            {status!.errors.map((e, i) => <li key={i} dir='ltr'>{e}</li>)}
          </ul>
        )}
        {error && <p className='text-destructive text-xs'>{error}</p>}
      </CardContent>
    </Card>
  );
}
