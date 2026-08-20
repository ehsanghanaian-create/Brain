'use client';

import { Button } from '@/components/ui/button';
import { endpoints, type ConnectionResult, type GscSyncStatus } from '@/lib/api/client';
import { useCallback, useState } from 'react';
import { toast } from 'sonner';
import { gscStepRows, gscSyncView } from '../gsc-sync';
import { useIntegrationSyncStatus } from '../use-sync-status';
import { queueMessage } from '../wp-sync';
import { ConnectionTester } from './connection-tester';
import { IntegrationCard, SyncCounters, SyncErrors, SyncProgress } from './integration-card';

/**
 * GSC integration card — connection (property picker/tester) و pipeline «داده → فرصت‌ها → اسنپ‌شات → گراف» در یک قاب.
 * Sync always runs as a backend job (POST …/gsc/sync); this card polls GET …/gsc/sync/status.
 */
export function GscIntegrationCard({ siteId, initialValue, initialResult, refreshKey = 0 }: {
  siteId: string;
  initialValue?: string | null;
  initialResult?: ConnectionResult;
  refreshKey?: number;
}) {
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const load = useCallback(() => endpoints.gscSyncStatus(siteId), [siteId]);
  const shouldPoll = useCallback((s: GscSyncStatus | null) => gscSyncView(s).shouldPoll, []);
  const { status, error, setError, reload } = useIntegrationSyncStatus<GscSyncStatus>({ load, shouldPoll, refreshKey: refreshKey + refresh });

  const view = gscSyncView(status, { busy });

  async function start() {
    setBusy(true);
    try {
      const r = await endpoints.gscSyncStart(siteId, {});
      const m = queueMessage(r);
      (m.ok ? toast.success : toast.error)(m.text);
      await reload();
    } catch (e) {
      setError(String(e));
      toast.error(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <IntegrationCard
      kind='gsc'
      title='Google Search Console'
      badge={view.statusFa}
      badgeVariant={view.running ? 'default' : status?.status === 'succeeded' ? 'secondary' : status?.status === 'not_authorized' || status?.status === 'failed' ? 'destructive' : 'outline'}
      description={
        <>
          داده کوئری/صفحه از Search Console خوانده می‌شود، سپس فرصت‌های کلمات کلیدی، اسنپ‌شات عملکرد محتوا و گراف به‌روز می‌شوند. اجرا همیشه به‌صورت job در پس‌زمینه است.
          {status?.property && <span className='block' dir='ltr'>property: {status.property}</span>}
          {view.dateRange && <span className='block' dir='ltr'>بازه داده: {view.dateRange}</span>}
          {view.lastSync && <span className='block' dir='ltr'>آخرین همگام‌سازی: {new Date(view.lastSync).toLocaleString('fa-IR')}</span>}
        </>
      }
    >
      <ConnectionTester siteId={siteId} kind='gsc' label='Google Search Console' hint='sc-domain:example.com'
        initialValue={initialValue} initialResult={initialResult} onResult={() => setRefresh((n) => n + 1)} />

      <SyncCounters kind='gsc' items={view.counters} />

      <div className='flex flex-wrap items-center gap-2'>
        <Button type='button' size='sm' disabled={!view.canSync} title={view.syncDisabledReason ?? undefined} onClick={() => void start()} data-testid='gsc-sync-start'>
          همگام‌سازی
        </Button>
        <Button type='button' size='sm' variant='ghost' disabled={busy} onClick={() => void reload()}>به‌روزرسانی وضعیت</Button>
        {view.syncDisabledReason && !view.running && <span className='text-muted-foreground text-xs'>{view.syncDisabledReason}</span>}
      </div>

      {(view.running || (status?.steps?.length ?? 0) > 0) && (
        <SyncProgress kind='gsc' percent={view.percent} rows={gscStepRows(status)} label={view.running ? view.stepFa : 'آخرین اجرا'} />
      )}

      <SyncErrors kind='gsc' errors={status?.errors ?? []} />
      {error && <p className='text-destructive text-xs'>{error}</p>}
    </IntegrationCard>
  );
}
