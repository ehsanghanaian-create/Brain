'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ContentEditor } from '@/features/content/components/content-editor';
import { CommandCenter } from '@/features/graph/components/command-center';
import { ApiError, endpoints, type PlanCategory, type PlanList, type PlanMeta, type Site } from '@/lib/api/client';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { PLAN_STATUS_COLOR, PLAN_STATUS_FA, PLAN_STATUS_ORDER, fa } from '../constants';
import { PlanCalendar } from './plan-calendar';
import { PlanCategories } from './plan-categories';
import { PlanKanban } from './plan-kanban';
import { PlanKeywordMapping } from './plan-keyword-mapping';
import { PlanSheet } from './plan-sheet';
import { PlanSuggestions } from './plan-suggestions';
import { PlanTable } from './plan-table';

export function ContentPlannerPage({ sites, initialSiteId, initialPlanId, initialTab }: { sites: Site[]; initialSiteId: string; initialPlanId?: number; initialTab?: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [meta, setMeta] = useState<PlanMeta | null>(null);
  const [categories, setCategories] = useState<PlanCategory[]>([]);
  const [counts, setCounts] = useState<PlanList['counts'] | null>(null);
  const [open, setOpen] = useState<number | null>(initialPlanId ?? null);
  const [openItem, setOpenItem] = useState<number | null>(null);
  const [tick, setTick] = useState(0);
  const [tab, setTab] = useState(initialTab && ['table', 'kanban', 'calendar', 'categories', 'keywords', 'suggestions', 'graph'].includes(initialTab) ? initialTab : 'table');
  const site = sites.find((s) => s.site_id === siteId);
  const refresh = useCallback(async () => {
    try { const [m, c, l] = await Promise.all([endpoints.planMeta(siteId), endpoints.planCategories(siteId), endpoints.plans(siteId, { limit: 1 })]); setMeta(m); setCategories(c); setCounts(l.counts); }
    catch (e) { toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)); }
  }, [siteId]);
  useEffect(() => { refresh(); }, [refresh, tick]);
  const bump = () => setTick((t) => t + 1);
  return (
    <div className='flex flex-col gap-3'>
      <div className='flex flex-wrap items-center gap-2 text-xs'>
        <NativeSelect value={siteId} onChange={(e) => { setSiteId(e.target.value); setOpen(null); }} className='w-44'>{sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>)}</NativeSelect>
        {counts && <span className='flex flex-wrap gap-2'>{PLAN_STATUS_ORDER.map((s) => <span key={s} className='flex items-center gap-1'><span className='inline-block h-2.5 w-2.5 rounded-full' style={{ background: PLAN_STATUS_COLOR[s] }} />{PLAN_STATUS_FA[s]} {fa.format(counts.by_status[s] ?? 0)}</span>)}<Badge variant='outline'>کل {fa.format(counts.total)} · بدون تاریخ {fa.format(counts.unscheduled)}</Badge></span>}
        <span className='ms-auto flex gap-1'>
          <Button size='sm' variant='outline' onClick={async () => { try { const r = await endpoints.planBackfill(siteId); toast.success(`${r.created} برنامه از آیتم‌های محتوای موجود ساخته شد`); bump(); } catch (e) { toast.error(String(e)); } }} title='برای هر آیتم مغز محتوا که برنامه ندارد یک ردیف برنامه بساز'>وارد کردن آیتم‌های موجود</Button>
          <Button size='sm' variant='ghost' onClick={async () => { await endpoints.planSyncGraph(siteId); toast.success('گراف همگام شد'); }}>همگام‌سازی گراف</Button>
        </span>
      </div>
      {meta && <p className='text-muted-foreground text-xs'>{meta.publishing.note} · {meta.ai_generation.note}</p>}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className='flex-wrap'>
          <TabsTrigger value='table'>جدول برنامه‌ریزی</TabsTrigger><TabsTrigger value='kanban'>کانبان</TabsTrigger><TabsTrigger value='calendar'>تقویم</TabsTrigger><TabsTrigger value='categories'>دسته‌ها</TabsTrigger><TabsTrigger value='keywords'>نگاشت کلمات کلیدی</TabsTrigger><TabsTrigger value='suggestions'>پیشنهادهای مغز</TabsTrigger><TabsTrigger value='graph'>ارتباطات گراف</TabsTrigger>
        </TabsList>
        <TabsContent value='table'><PlanTable siteId={siteId} meta={meta} categories={categories} onOpen={setOpen} refreshKey={tick} onChanged={bump} /></TabsContent>
        <TabsContent value='kanban'><PlanKanban siteId={siteId} categories={categories} onOpen={setOpen} refreshKey={tick} onChanged={bump} /></TabsContent>
        <TabsContent value='calendar'><PlanCalendar siteId={siteId} onOpenPlan={setOpen} onOpenItem={setOpenItem} refreshKey={tick} onChanged={bump} /></TabsContent>
        <TabsContent value='categories'><PlanCategories siteId={siteId} hasWp={!!site?.wp_url} onOpen={setOpen} onChanged={bump} refreshKey={tick} /></TabsContent>
        <TabsContent value='keywords'><PlanKeywordMapping siteId={siteId} onOpen={setOpen} onChanged={bump} refreshKey={tick} /></TabsContent>
        <TabsContent value='suggestions'><PlanSuggestions siteId={siteId} onOpen={setOpen} onChanged={bump} refreshKey={tick} /></TabsContent>
        <TabsContent value='graph'>
          <p className='text-muted-foreground mb-2 text-xs'>نقشه برنامه محتوا: دسته (وردپرس/مغز) ← برنامه محتوایی → کلمه کلیدی هدف · اینتنت · مرحله قیف · محتوای تولیدشده · صفحات مرتبط و لینک‌های داخلی پیشنهادی. روی گره کلیک کنید تا جزئیات و پیوند به برنامه‌ریز نمایش داده شود.</p>
          {tab === 'graph' && <CommandCenter key={`${siteId}-${tick}`} sites={sites} initialSiteId={siteId} initialMode='planner' focusNodeId={open ? `plan:${open}` : null} />}
        </TabsContent>
      </Tabs>
      <PlanSheet siteId={siteId} pid={open} meta={meta} categories={categories} onClose={() => setOpen(null)} onChanged={bump} />
      <ContentEditor siteId={siteId} cid={openItem} onClose={() => setOpenItem(null)} onChanged={bump} />
    </div>
  );
}
