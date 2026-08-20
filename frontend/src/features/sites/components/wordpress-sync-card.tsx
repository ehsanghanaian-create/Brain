'use client';

import { Button } from '@/components/ui/button';
import { endpoints, type ConnectionResult, type WpAuthStatus, type WpSyncQueued, type WpSyncStatus } from '@/lib/api/client';
import { useCallback, useState } from 'react';
import { toast } from 'sonner';
import { useIntegrationSyncStatus } from '../use-sync-status';
import { queueMessage, stepRows, wpSyncView } from '../wp-sync';
import { ConnectionTester } from './connection-tester';
import { IntegrationCard, SyncCounters, SyncErrors, SyncProgress } from './integration-card';

/**
 * WordPress integration card — connection (URL + Application Password tester) و همگام‌سازی → گراف در یک قاب.
 * Sync always runs as a backend job (POST …/wordpress/sync · …/graph/rebuild); this card polls GET …/wordpress/sync/status.
 */
export function WordPressIntegrationCard({ siteId, initialValue, initialResult, initialAuth, refreshKey = 0 }: {
  siteId: string;
  initialValue?: string | null;
  initialResult?: ConnectionResult;
  initialAuth?: WpAuthStatus | null;
  refreshKey?: number;
}) {
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const load = useCallback(() => endpoints.wpSyncStatus(siteId), [siteId]);
  const shouldPoll = useCallback((s: WpSyncStatus | null) => wpSyncView(s).shouldPoll, []);
  const { status, error, setError, reload } = useIntegrationSyncStatus<WpSyncStatus>({ load, shouldPoll, refreshKey: refreshKey + refresh });

  const view = wpSyncView(status, { busy });

  async function run(fn: () => Promise<WpSyncQueued>) {
    setBusy(true);
    try {
      const r = await fn();
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
      kind='wordpress'
      title='وردپرس'
      badge={view.statusFa}
      badgeVariant={view.running ? 'default' : status?.status === 'succeeded' ? 'secondary' : status?.status && status.status !== 'never' ? 'destructive' : 'outline'}
      description={
        <>
          دسته‌ها، صفحات و نوشته‌ها از REST وردپرس (فقط‌خواندنی) خوانده می‌شوند، سپس لینک‌ها استخراج و گراف ساخته می‌شود. اجرا همیشه به‌صورت job در پس‌زمینه است.
          {view.lastSync && <span className='block' dir='ltr'>آخرین همگام‌سازی: {new Date(view.lastSync).toLocaleString('fa-IR')}</span>}
        </>
      }
    >
      <ConnectionTester siteId={siteId} kind='wordpress' label='WordPress REST' hint='https://example.com'
        initialValue={initialValue} initialResult={initialResult} initialAuth={initialAuth} onResult={() => setRefresh((n) => n + 1)} />

      <SyncCounters kind='wp' items={view.counters} />

      <div className='flex flex-wrap items-center gap-2'>
        <Button type='button' size='sm' disabled={!view.canStart} title={view.startDisabledReason ?? undefined} onClick={() => run(() => endpoints.wpSyncStart(siteId, { crawl: true }))} data-testid='wp-sync-start'>
          شروع همگام‌سازی
        </Button>
        <Button type='button' size='sm' variant='outline' disabled={!view.canRebuild} onClick={() => run(() => endpoints.graphRebuild(siteId))} data-testid='wp-graph-rebuild'>
          بازسازی گراف
        </Button>
        <Button type='button' size='sm' variant='ghost' disabled={busy} onClick={() => void reload()}>به‌روزرسانی وضعیت</Button>
        {view.startDisabledReason && !view.running && <span className='text-muted-foreground text-xs'>{view.startDisabledReason}</span>}
      </div>

      {(view.running || (status?.steps?.length ?? 0) > 0) && (
        <SyncProgress kind='wp' percent={view.percent} rows={stepRows(status)}
          label={view.running ? view.stepFa : status?.stage === 'graph_only' ? 'آخرین اجرا: بازسازی گراف' : 'آخرین اجرا: همگام‌سازی کامل'} />
      )}

      <SyncErrors kind='wp' errors={status?.errors ?? []} />
      {error && <p className='text-destructive text-xs'>{error}</p>}
    </IntegrationCard>
  );
}
