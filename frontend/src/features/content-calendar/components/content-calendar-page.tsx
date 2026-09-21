'use client';

import { Button } from '@/components/ui/button';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { PlanCalendar } from '@/features/content-planner/components/plan-calendar';
import { Badge } from '@/components/ui/badge';
import { endpoints, type PlanCategory, type ProviderConfig, type Site, type WsOptions } from '@/lib/api/client';
import { useEffect, useState } from 'react';
import { AiKeysDialog, keyStatus, TONE_COLOR, WRITER_KINDS } from './ai-keys-dialog';
import { ArticleEditorSheet, type EditorTarget } from './article-editor-sheet';
import { ArticleSheet } from './article-sheet';

export function ContentCalendarPage({ sites, initialSiteId, initialPlanId }: { sites: Site[]; initialSiteId: string; initialPlanId?: number }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [openPlan, setOpenPlan] = useState<number | 'new' | null>(initialPlanId ?? null);
  const [newDate, setNewDate] = useState<string | null>(null);
  const [editing, setEditing] = useState<EditorTarget | null>(null);
  const [tick, setTick] = useState(0);
  const [categories, setCategories] = useState<PlanCategory[]>([]);
  const [opts, setOpts] = useState<WsOptions | null>(null);
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [keysOpen, setKeysOpen] = useState(false);
  useEffect(() => {
    endpoints.planCategories(siteId).then(setCategories).catch(() => setCategories([]));
    endpoints.wsOptions(siteId).then(setOpts).catch(() => setOpts(null));
    endpoints.providerConfigs().then(setProviders).catch(() => setProviders([]));
  }, [siteId, tick]);
  const bump = () => setTick((t) => t + 1);
  const site = sites.find((s) => s.site_id === siteId);
  const switchSite = (id: string) => {
    setSiteId(id); setOpenPlan(null);
    const u = new URL(window.location.href); u.searchParams.set('site', id); u.searchParams.delete('plan'); window.history.replaceState(null, '', u.toString());
  };
  return (
    <div className='flex flex-col gap-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect value={siteId} onChange={(e) => switchSite(e.target.value)} className='w-48'>{sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>)}</NativeSelect>
        {site && !site.wp_url && <span className='text-xs text-amber-600'>این سایت آدرس وردپرس ندارد — انتشار غیرفعال است.</span>}
        <button type='button' className='flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors hover:bg-accent' onClick={() => setKeysOpen(true)} title='کلیدهای نویسندهٔ هوش مصنوعی'>
          {WRITER_KINDS.map((k) => { const st = keyStatus(providers.find((p) => p.kind === k.kind)); return <span key={k.kind} className='flex items-center gap-1'><span className='inline-block h-2 w-2 rounded-full' style={{ background: TONE_COLOR[st.tone] }} />{k.label}: {st.text}</span>; })}
          <Badge variant='outline' className='ms-1'>کلیدها</Badge>
        </button>
        <Button className='ms-auto' onClick={() => { setNewDate(null); setOpenPlan('new'); }}>+ مقالهٔ جدید</Button>
      </div>
      <AiKeysDialog open={keysOpen} onClose={() => setKeysOpen(false)} onChanged={bump} />
      <PlanCalendar siteId={siteId} onOpenPlan={setOpenPlan} onOpenItem={(cid) => setEditing({ cid, title: 'محتوا' })} onNewOnDay={(d) => { setNewDate(d); setOpenPlan('new'); }} refreshKey={tick} onChanged={bump} />
      <ArticleSheet siteId={siteId} pid={openPlan} defaultDate={newDate} categories={categories} opts={opts} onClose={() => setOpenPlan(null)} onChanged={bump} onOpenEditor={setEditing} />
      <ArticleEditorSheet siteId={siteId} target={editing} onClose={() => setEditing(null)} onChanged={bump} />
    </div>
  );
}
