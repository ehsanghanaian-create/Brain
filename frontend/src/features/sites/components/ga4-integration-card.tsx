'use client';

import { Button } from '@/components/ui/button';
import { endpoints, type ConnectionResult, type Ga4SyncStatus } from '@/lib/api/client';
import { useCallback, useState } from 'react';
import { toast } from 'sonner';
import { ga4StepRows, ga4SyncView } from '../ga4-sync';
import { useIntegrationSyncStatus } from '../use-sync-status';
import { queueMessage } from '../wp-sync';
import { ConnectionTester } from './connection-tester';
import { IntegrationCard, SyncCounters, SyncErrors, SyncProgress } from './integration-card';

/**
 * GA4 integration card — connection (Property ID tester) و pipeline «داده → اسنپ‌شات → گراف/فرصت‌ها» در یک قاب.
 * Sync always runs as a backend job (POST …/ga4/sync); this card polls GET …/ga4/sync/status.
 */
export function Ga4IntegrationCard({ siteId, initialValue, initialResult, refreshKey = 0 }: {
  siteId: string;
  initialValue?: string | null;
  initialResult?: ConnectionResult;
  refreshKey?: number;
}) {
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const load = useCallback(() => endpoints.ga4SyncStatus(siteId), [siteId]);
  const shouldPoll = useCallback((s: Ga4SyncStatus | null) => ga4SyncView(s).shouldPoll, []);
  const { status, error, setError, reload } = useIntegrationSyncStatus<Ga4SyncStatus>({ load, shouldPoll, refreshKey: refreshKey + refresh });

  const view = ga4SyncView(status, { busy });

  async function start() {
    setBusy(true);
    try {
      const r = await endpoints.ga4SyncStart(siteId, {});
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
      kind='ga4'
      title='Google Analytics 4'
      badge={view.statusFa}
      badgeVariant={view.running ? 'default' : status?.status === 'succeeded' ? 'secondary' : status?.status === 'not_authorized' || status?.status === 'failed' ? 'destructive' : 'outline'}
      description={
        <>
          داده رفتاری کاربران (sessions، کاربران، تبدیل‌ها) از GA4 Data API خوانده می‌شود (فقط‌خواندنی)، سپس اسنپ‌شات عملکرد محتوا، گراف و فرصت‌های سئو به‌روز می‌شوند. اجرا همیشه به‌صورت job در پس‌زمینه است.
          {status?.property && <span className='block' dir='ltr'>property: {status.property}</span>}
          {view.dateRange && <span className='block' dir='ltr'>بازه داده: {view.dateRange}</span>}
          {view.lastSync && <span className='block' dir='ltr'>آخرین همگام‌سازی: {new Date(view.lastSync).toLocaleString('fa-IR')}</span>}
        </>
      }
    >
      <ConnectionTester siteId={siteId} kind='ga4' label='GA4 Property ID' hint='123456789'
        initialValue={initialValue} initialResult={initialResult} onResult={() => setRefresh((n) => n + 1)} />

      <SyncCounters kind='ga4' items={view.counters} />

      <div className='flex flex-wrap items-center gap-2'>
        <Button type='button' size='sm' disabled={!view.canSync} title={view.syncDisabledReason ?? undefined} onClick={() => void start()} data-testid='ga4-sync-start'>
          همگام‌سازی
        </Button>
        <Button type='button' size='sm' variant='ghost' disabled={busy} onClick={() => void reload()}>به‌روزرسانی وضعیت</Button>
        {view.syncDisabledReason && !view.running && <span className='text-muted-foreground text-xs'>{view.syncDisabledReason}</span>}
      </div>

      {view.topPages.length > 0 && (
        <div className='rounded-md border p-2 text-xs' data-testid='ga4-top-pages'>
          <div className='text-muted-foreground mb-1'>پربازدیدترین صفحات (sessions · تبدیل)</div>
          <ul className='grid gap-1'>
            {view.topPages.map((p) => (
              <li key={p.path} className='flex items-center justify-between gap-2'>
                <span className='truncate' dir='ltr'>{p.path}</span>
                <span className='shrink-0' dir='ltr'>{p.sessions.toLocaleString('fa-IR')} · {p.conversions.toLocaleString('fa-IR')}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(view.running || (status?.steps?.length ?? 0) > 0) && (
        <SyncProgress kind='ga4' percent={view.percent} rows={ga4StepRows(status)} label={view.running ? view.stepFa : 'آخرین اجرا'} />
      )}

      <SyncErrors kind='ga4' errors={status?.errors ?? []} />
      {error && <p className='text-destructive text-xs'>{error}</p>}
    </IntegrationCard>
  );
}
