'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ApiError, endpoints, type ConnectionsStatus, type GraphSummary, type InitializeResult, type Site, type SiteMemory } from '@/lib/api/client';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';
import { BUSINESS_CATEGORIES, MODE_FA } from '../constants';
import { StatusBadge } from './connection-tester';
import { SiteBrainForm } from './site-brain-form';
import { AutoSyncLine } from './auto-sync-line';
import { DeleteSiteButton } from './delete-site-button';
import { Ga4IntegrationCard } from './ga4-integration-card';
import { GoogleAccountCard } from './google-account-card';
import { GscIntegrationCard } from './gsc-sync-card';
import { WordPressIntegrationCard } from './wordpress-sync-card';

const fa = new Intl.NumberFormat('fa-IR');

export function SiteDetail({
  site,
  connections,
  memory,
  graph,
  initialTab
}: {
  site: Site;
  connections: ConnectionsStatus;
  memory: SiteMemory;
  graph: GraphSummary | null;
  initialTab: string;
}) {
  const router = useRouter();
  const [mode, setMode] = useState(site.mode);
  const [busy, setBusy] = useState(false);
  const [init, setInit] = useState<InitializeResult | null>(null);
  const [wpRefresh] = useState(0);          // cards own their refresh after connection tests; key kept for external triggers
  const [gscRefresh, setGscRefresh] = useState(0);
  const [ga4Refresh, setGa4Refresh] = useState(0);

  async function changeMode(next: 'manual' | 'assisted' | 'autopilot') {
    setBusy(true);
    try {
      await endpoints.updateSite(site.site_id, { mode: next });
      setMode(next);
      toast.success(`حالت انتشار: ${MODE_FA[next]}`);
      router.refresh();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function reinit() {
    setBusy(true);
    try {
      setInit(await endpoints.initializeSite(site.site_id));
      toast.success('فضای کاری بررسی/ایجاد شد');
      router.refresh();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const category = BUSINESS_CATEGORIES.find((c) => c.value === site.business_type)?.label ?? site.business_type ?? '—';

  return (
    <Tabs defaultValue={initialTab === 'brain' ? 'brain' : 'overview'} className='gap-4'>
      <TabsList>
        <TabsTrigger value='overview'>اطلاعات و اتصال‌ها</TabsTrigger>
        <TabsTrigger value='brain'>مغز سایت</TabsTrigger>
      </TabsList>

      <TabsContent value='overview' className='grid gap-4 lg:grid-cols-2'>
        <Card>
          <CardHeader>
            <CardTitle>مشخصات</CardTitle>
            <CardDescription dir='ltr'>{site.canonical_url}</CardDescription>
          </CardHeader>
          <CardContent className='grid gap-2 text-sm'>
            <Row k='شناسه' v={<code dir='ltr'>{site.site_id}</code>} />
            <Row k='حوزه کسب‌وکار' v={category} />
            <Row k='زبان / کشور / منطقه زمانی' v={<span dir='ltr'>{site.language ?? '—'} / {site.country ?? '—'} / {(site as Site & { timezone?: string }).timezone ?? '—'}</span>} />
            <Row k='فضای کاری' v={<code dir='ltr'>{site.workspace_path ?? '—'}</code>} />
            <Row k='گراف' v={graph ? `${fa.format(graph.nodes)} گره · ${fa.format(graph.edges)} یال` : '—'} />
            <div className='mt-2 grid gap-1.5'>
              <Label>حالت انتشار (هیچ نوشتنی به وردپرس تا حالت «دستی» است انجام نمی‌شود)</Label>
              <div className='flex items-center gap-2'>
                <NativeSelect value={mode} onChange={(e) => changeMode(e.target.value as 'manual' | 'assisted' | 'autopilot')} disabled={busy} className='max-w-56'>
                  <NativeSelectOption value='manual'>دستی — فقط پیشنهاد</NativeSelectOption>
                  <NativeSelectOption value='assisted'>نیمه‌خودکار — با تأیید هر مورد</NativeSelectOption>
                  <NativeSelectOption value='autopilot'>خودکار — طبق زمان‌بندی</NativeSelectOption>
                </NativeSelect>
                <Badge variant={mode === 'manual' ? 'secondary' : 'default'}>{MODE_FA[mode]}</Badge>
              </div>
            </div>
            <div className='mt-2 flex items-center gap-2'>
              <Button variant='secondary' size='sm' onClick={reinit} disabled={busy}>بررسی / ایجاد فضای کاری</Button>
              <DeleteSiteButton siteId={site.site_id} siteName={site.name} redirectAfter />
              {init && (
                <span className='text-muted-foreground text-xs' dir='ltr'>
                  {init.workspace.path} · memory {init.memory.existed ? 'exists' : 'created'} · {init.graph.site_node}
                </span>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Integration Center — یک کارت کامل per integration: اتصال + همگام‌سازی + شمارنده‌ها */}
        <div className='flex flex-wrap items-center gap-2 text-xs'>
          <span className='font-medium'>مرکز اتصال‌ها:</span>
          <span>WordPress <StatusBadge status={connections.status.wordpress?.status} /></span>
          <span>GSC <StatusBadge status={connections.status.gsc?.status} /></span>
          <span>GA4 <StatusBadge status={connections.status.ga4?.status} /></span>
          <AutoSyncLine siteId={site.site_id} />
        </div>
        <GoogleAccountCard onChange={() => { setGscRefresh((n) => n + 1); setGa4Refresh((n) => n + 1); }} />
        <WordPressIntegrationCard siteId={site.site_id} initialValue={site.wp_url} initialResult={connections.status.wordpress} initialAuth={connections.wordpress_auth ?? null} refreshKey={wpRefresh} />
        <GscIntegrationCard siteId={site.site_id} initialValue={site.gsc_property} initialResult={connections.status.gsc} refreshKey={gscRefresh} />
        <Ga4IntegrationCard siteId={site.site_id} initialValue={site.ga4_property} initialResult={connections.status.ga4} refreshKey={ga4Refresh} />
      </TabsContent>

      <TabsContent value='brain'>
        <SiteBrainForm siteId={site.site_id} initial={memory} />
      </TabsContent>
    </Tabs>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className='flex items-start justify-between gap-4 border-b py-1 last:border-0'>
      <span className='text-muted-foreground'>{k}</span>
      <span className='text-end'>{v}</span>
    </div>
  );
}
