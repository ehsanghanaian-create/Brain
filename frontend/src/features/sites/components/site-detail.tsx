'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ApiError, endpoints, type ConnectionsStatus, type GraphSummary, type InitializeResult, type JobRun, type Site, type SiteMemory } from '@/lib/api/client';
import { useQuery } from '@tanstack/react-query';
import { IconActivity, IconAdjustments, IconBrain, IconCheck, IconClock, IconExternalLink, IconPlugConnected, IconSettings, IconWorld } from '@tabler/icons-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';
import { BUSINESS_CATEGORIES, MODE_FA } from '../constants';
import { AutoSyncLine } from './auto-sync-line';
import { StatusBadge } from './connection-tester';
import { DeleteSiteButton } from './delete-site-button';
import { Ga4IntegrationCard } from './ga4-integration-card';
import { GoogleAccountCard } from './google-account-card';
import { GscIntegrationCard } from './gsc-sync-card';
import { SiteBrainForm } from './site-brain-form';
import { WordPressIntegrationCard } from './wordpress-sync-card';

const fa = new Intl.NumberFormat('fa-IR');
type SiteTab = 'overview' | 'integrations' | 'automation' | 'brain' | 'settings';
const validTabs = new Set<SiteTab>(['overview', 'integrations', 'automation', 'brain', 'settings']);

export function SiteDetail({ site, connections, memory, graph, initialTab }: {
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
  const [gscRefresh, setGscRefresh] = useState(0);
  const [ga4Refresh, setGa4Refresh] = useState(0);
  const [tab, setTab] = useState<SiteTab>(validTabs.has(initialTab as SiteTab) ? initialTab as SiteTab : 'overview');

  function changeTab(next: string) {
    const value = next as SiteTab;
    setTab(value);
    const url = new URL(window.location.href);
    if (value === 'overview') url.searchParams.delete('tab');
    else url.searchParams.set('tab', value);
    window.history.replaceState(window.history.state, '', url);
  }

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
      toast.success('فضای کاری بررسی و آماده شد');
      router.refresh();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const category = BUSINESS_CATEGORIES.find((c) => c.value === site.business_type)?.label ?? site.business_type ?? '—';
  const connectionEntries = [connections.status.wordpress, connections.status.gsc, connections.status.ga4];
  const connected = connectionEntries.filter((c) => c?.ok).length;
  const readiness = Math.round(((connected + (site.workspace_path ? 1 : 0) + (graph?.nodes ? 1 : 0)) / 5) * 100);

  return (
    <Tabs value={tab} onValueChange={changeTab} className='gap-5'>
      <div className='sticky top-14 z-20 -mx-4 border-y bg-background/95 px-4 py-2 backdrop-blur md:-mx-6 md:px-6'>
        <TabsList variant='line' className='h-10 max-w-full justify-start overflow-x-auto'>
          <TabsTrigger value='overview'><IconActivity />نمای کلی</TabsTrigger>
          <TabsTrigger value='integrations'><IconPlugConnected />اتصال‌ها</TabsTrigger>
          <TabsTrigger value='automation'><IconClock />عملیات و زمان‌بندی</TabsTrigger>
          <TabsTrigger value='brain'><IconBrain />مغز سایت</TabsTrigger>
          <TabsTrigger value='settings'><IconSettings />تنظیمات</TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value='overview' className='space-y-5'>
        <section className='overflow-hidden rounded-2xl border bg-gradient-to-bl from-sky-500/10 via-card to-card'>
          <div className='grid gap-5 p-5 lg:grid-cols-[1fr_auto] lg:items-center'>
            <div className='min-w-0'>
              <div className='flex flex-wrap items-center gap-2'>
                <span className='rounded-xl bg-sky-500/10 p-2 text-sky-500'><IconWorld className='size-5' /></span>
                <h2 className='text-xl font-semibold'>{site.name}</h2>
                <Badge variant={readiness >= 80 ? 'default' : 'secondary'}>{readiness.toLocaleString('fa-IR')}٪ آماده</Badge>
              </div>
              <a href={site.canonical_url} target='_blank' rel='noreferrer' dir='ltr' className='mt-2 inline-flex max-w-full items-center gap-1 truncate text-sm text-muted-foreground hover:text-foreground'>
                {site.canonical_url}<IconExternalLink className='size-3.5' />
              </a>
              <p className='mt-3 max-w-2xl text-sm leading-7 text-muted-foreground'>سلامت داده‌ها، اتصال سرویس‌ها، عملیات در حال اجرا و حافظه اختصاصی این سایت را از یک نقطه مدیریت کنید.</p>
            </div>
            <div className='grid grid-cols-3 gap-2 text-center'>
              <MiniMetric label='اتصال فعال' value={`${connected.toLocaleString('fa-IR')} از ۳`} />
              <MiniMetric label='گره گراف' value={graph ? fa.format(graph.nodes) : '—'} />
              <MiniMetric label='یال گراف' value={graph ? fa.format(graph.edges) : '—'} />
            </div>
          </div>
        </section>

        <div className='grid gap-4 xl:grid-cols-[1.4fr_1fr]'>
          <Card>
            <CardHeader><CardTitle className='text-base'>وضعیت راه‌اندازی</CardTitle><CardDescription>موارد لازم برای استفاده کامل از اطلاعات زنده سایت</CardDescription></CardHeader>
            <CardContent className='grid gap-2 sm:grid-cols-2'>
              <CheckItem ok={Boolean(site.workspace_path)} title='فضای کاری سایت' detail={site.workspace_path ? 'آماده است' : 'نیاز به راه‌اندازی دارد'} onClick={() => changeTab('settings')} />
              <CheckItem ok={Boolean(connections.status.wordpress?.ok)} title='وردپرس' detail={connections.status.wordpress?.message ?? 'بررسی نشده'} onClick={() => changeTab('integrations')} />
              <CheckItem ok={Boolean(connections.status.gsc?.ok)} title='Search Console' detail={connections.status.gsc?.message ?? 'بررسی نشده'} onClick={() => changeTab('integrations')} />
              <CheckItem ok={Boolean(connections.status.ga4?.ok)} title='Google Analytics' detail={connections.status.ga4?.message ?? 'بررسی نشده'} onClick={() => changeTab('integrations')} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className='text-base'>اقدام‌های سریع</CardTitle><CardDescription>مسیرهای پرکاربرد مدیریت این سایت</CardDescription></CardHeader>
            <CardContent className='grid gap-2'>
              <Button variant='outline' className='justify-start' onClick={() => changeTab('integrations')}><IconPlugConnected />مدیریت اتصال‌ها و همگام‌سازی</Button>
              <Button variant='outline' className='justify-start' onClick={() => changeTab('automation')}><IconClock />مشاهده کارهای در حال اجرا</Button>
              <Button variant='outline' className='justify-start' onClick={() => changeTab('brain')}><IconBrain />ویرایش حافظه و قواعد سایت</Button>
            </CardContent>
          </Card>
        </div>
      </TabsContent>

      <TabsContent value='integrations' className='space-y-4'>
        <div className='flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card p-4'>
          <div><h2 className='font-medium'>مرکز اتصال داده‌ها</h2><p className='mt-1 text-sm text-muted-foreground'>اتصال، تست و همگام‌سازی هر منبع مستقل است؛ قطع یک سرویس بقیه را متوقف نمی‌کند.</p></div>
          <div className='flex flex-wrap gap-2 text-xs'>
            <span>WordPress <StatusBadge status={connections.status.wordpress?.status} /></span>
            <span>GSC <StatusBadge status={connections.status.gsc?.status} /></span>
            <span>GA4 <StatusBadge status={connections.status.ga4?.status} /></span>
          </div>
        </div>
        <div className='grid items-start gap-4 xl:grid-cols-2'>
          <WordPressIntegrationCard siteId={site.site_id} initialValue={site.wp_url} initialResult={connections.status.wordpress} initialAuth={connections.wordpress_auth ?? null} refreshKey={0} />
          <GscIntegrationCard siteId={site.site_id} initialValue={site.gsc_property} initialResult={connections.status.gsc} refreshKey={gscRefresh} />
          <Ga4IntegrationCard siteId={site.site_id} initialValue={site.ga4_property} initialResult={connections.status.ga4} refreshKey={ga4Refresh} />
          <GoogleAccountCard onChange={() => { setGscRefresh((n) => n + 1); setGa4Refresh((n) => n + 1); }} />
        </div>
      </TabsContent>

      <TabsContent value='automation' className='space-y-4'>
        <Card>
          <CardHeader><CardTitle className='text-base'>به‌روزرسانی خودکار</CardTitle><CardDescription>داده‌های وردپرس، Search Console و GA4 طبق برنامه در پس‌زمینه تازه می‌شوند.</CardDescription></CardHeader>
          <CardContent><AutoSyncLine siteId={site.site_id} /></CardContent>
        </Card>
        <SiteJobs siteId={site.site_id} />
      </TabsContent>

      <TabsContent value='brain'><SiteBrainForm siteId={site.site_id} initial={memory} /></TabsContent>

      <TabsContent value='settings' className='grid gap-4 xl:grid-cols-[1.4fr_1fr]'>
        <Card>
          <CardHeader><CardTitle className='flex items-center gap-2 text-base'><IconAdjustments className='size-4' />مشخصات و نحوه انتشار</CardTitle><CardDescription dir='ltr'>{site.canonical_url}</CardDescription></CardHeader>
          <CardContent className='grid gap-2 text-sm'>
            <Row k='شناسه' v={<code dir='ltr'>{site.site_id}</code>} />
            <Row k='حوزه کسب‌وکار' v={category} />
            <Row k='زبان / کشور / منطقه زمانی' v={<span dir='ltr'>{site.language ?? '—'} / {site.country ?? '—'} / {(site as Site & { timezone?: string }).timezone ?? '—'}</span>} />
            <Row k='فضای کاری' v={<code className='break-all' dir='ltr'>{site.workspace_path ?? '—'}</code>} />
            <div className='mt-3 grid gap-1.5'>
              <Label>حالت انتشار</Label>
              <p className='text-xs text-muted-foreground'>در حالت دستی هیچ تغییری بدون تأیید شما در وردپرس اعمال نمی‌شود.</p>
              <div className='flex flex-wrap items-center gap-2'>
                <NativeSelect value={mode} onChange={(e) => changeMode(e.target.value as 'manual' | 'assisted' | 'autopilot')} disabled={busy} className='max-w-64'>
                  <NativeSelectOption value='manual'>دستی — فقط پیشنهاد</NativeSelectOption>
                  <NativeSelectOption value='assisted'>نیمه‌خودکار — با تأیید</NativeSelectOption>
                  <NativeSelectOption value='autopilot'>خودکار — طبق زمان‌بندی</NativeSelectOption>
                </NativeSelect>
                <Badge variant={mode === 'manual' ? 'secondary' : 'default'}>{MODE_FA[mode]}</Badge>
              </div>
            </div>
            <div className='mt-3 flex flex-wrap items-center gap-2'>
              <Button variant='secondary' size='sm' onClick={reinit} disabled={busy}>بررسی و آماده‌سازی فضای کاری</Button>
              {init && <span className='text-xs text-muted-foreground' dir='ltr'>{init.workspace.path}</span>}
            </div>
          </CardContent>
        </Card>
        <Card className='border-destructive/30'>
          <CardHeader><CardTitle className='text-base'>عملیات حساس</CardTitle><CardDescription>حذف سایت فقط رکورد و داده‌های همین سایت را هدف می‌گیرد.</CardDescription></CardHeader>
          <CardContent><DeleteSiteButton siteId={site.site_id} siteName={site.name} redirectAfter /></CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return <div className='min-w-24 rounded-xl border bg-background/70 px-3 py-3'><div className='text-base font-semibold'>{value}</div><div className='mt-1 text-[11px] text-muted-foreground'>{label}</div></div>;
}

function CheckItem({ ok, title, detail, onClick }: { ok: boolean; title: string; detail: string; onClick: () => void }) {
  return <button type='button' onClick={onClick} className='flex items-start gap-3 rounded-xl border p-3 text-start transition-colors hover:bg-muted/50'><span className={ok ? 'rounded-full bg-emerald-500/10 p-1 text-emerald-500' : 'rounded-full bg-amber-500/10 p-1 text-amber-500'}><IconCheck className='size-4' /></span><span className='min-w-0'><span className='block font-medium'>{title}</span><span className='mt-1 block line-clamp-2 text-xs text-muted-foreground'>{detail}</span></span></button>;
}

function SiteJobs({ siteId }: { siteId: string }) {
  const query = useQuery({ queryKey: ['background-jobs'], queryFn: () => endpoints.jobs(40), refetchInterval: 3000 });
  const jobs = (query.data ?? []).filter((job) => job.site_id === siteId).slice(0, 12);
  return <Card><CardHeader><CardTitle className='text-base'>تاریخچه عملیات</CardTitle><CardDescription>این وضعیت روی سرور ذخیره می‌شود و با خروج از صفحه از بین نمی‌رود.</CardDescription></CardHeader><CardContent className='space-y-2'>{jobs.length === 0 && <p className='rounded-xl border border-dashed py-10 text-center text-sm text-muted-foreground'>هنوز عملیات پس‌زمینه‌ای برای این سایت ثبت نشده است.</p>}{jobs.map((job) => <SiteJobRow key={job.run_id} job={job} />)}</CardContent></Card>;
}

function SiteJobRow({ job }: { job: JobRun }) {
  const label: Record<string, string> = { wordpress_sync: 'همگام‌سازی وردپرس', gsc_sync: 'دریافت Search Console', ga4_sync: 'دریافت GA4', links_analyze: 'تحلیل لینک‌های داخلی', planner_analyze: 'تحلیل برنامه محتوا', generation_run: 'تولید محتوا', build_graph: 'ساخت گراف' };
  return <div className='flex flex-wrap items-center gap-3 rounded-xl border p-3'><span className={job.status === 'failed' ? 'size-2 rounded-full bg-destructive' : job.status === 'succeeded' ? 'size-2 rounded-full bg-emerald-500' : 'size-2 animate-pulse rounded-full bg-sky-500'} /><div className='min-w-0 flex-1'><p className='font-medium'>{label[job.type] ?? job.type}</p><p className='mt-0.5 text-xs text-muted-foreground' dir='ltr'>{job.run_id}</p></div><Badge variant={job.status === 'failed' ? 'destructive' : 'secondary'}>{job.status === 'queued' ? 'در صف' : job.status === 'running' ? 'در حال اجرا' : job.status === 'succeeded' ? 'انجام شد' : 'ناموفق'}</Badge></div>;
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className='flex items-start justify-between gap-4 border-b py-2 last:border-0'><span className='text-muted-foreground'>{k}</span><span className='text-end'>{v}</span></div>;
}
