'use client';

import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ContentEditor } from '@/features/content/components/content-editor';
import { endpoints, type PlanCategory, type PlanMeta, type Site } from '@/lib/api/client';
import { useEffect, useState } from 'react';
import { PlanCalendar } from './plan-calendar';
import { PlanSheet } from './plan-sheet';

/** /dashboard/calendar — upgraded content calendar (phase 8.5): plans + content items, month/week/list, drag & drop, filters. */
export function CalendarStandalone({ sites, initialSiteId }: { sites: Site[]; initialSiteId: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [openPlan, setOpenPlan] = useState<number | null>(null);
  const [openItem, setOpenItem] = useState<number | 'new' | null>(null);
  const [tick, setTick] = useState(0);
  const [meta, setMeta] = useState<PlanMeta | null>(null);
  const [categories, setCategories] = useState<PlanCategory[]>([]);
  useEffect(() => { endpoints.planMeta(siteId).then(setMeta).catch(() => null); endpoints.planCategories(siteId).then(setCategories).catch(() => null); }, [siteId, tick]);
  return (
    <div className='flex flex-col gap-3'>
      <div className='flex flex-wrap items-center gap-2 text-xs'>
        <NativeSelect value={siteId} onChange={(e) => setSiteId(e.target.value)} className='w-44'>{sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>)}</NativeSelect>
        <span className='text-muted-foreground'>کارت‌های برنامه محتوایی و آیتم‌های مغز محتوا (◦ = بدون برنامه) — نمای ماهانه/هفتگی/فهرست، کشیدن برای زمان‌بندی، فیلتر دسته/وضعیت/اولویت.</span>
        <a className='ms-auto underline' href={`/dashboard/content-planner?site=${siteId}`}>برنامه‌ریز محتوا</a>
      </div>
      <PlanCalendar siteId={siteId} onOpenPlan={setOpenPlan} onOpenItem={setOpenItem} refreshKey={tick} onChanged={() => setTick((t) => t + 1)} />
      <PlanSheet siteId={siteId} pid={openPlan} meta={meta} categories={categories} onClose={() => setOpenPlan(null)} onChanged={() => setTick((t) => t + 1)} />
      <ContentEditor siteId={siteId} cid={openItem} onClose={() => setOpenItem(null)} onChanged={() => setTick((t) => t + 1)} />
    </div>
  );
}
