'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { JMONTHS, WEEKDAYS_FA, addDays, faNum, faYear, iso, jalali, jalaliMonthDays } from '@/features/content/constants';
import { ApiError, endpoints, type PlanStatus } from '@/lib/api/client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { PLAN_STATUS_COLOR, PLAN_STATUS_FA, PLAN_STATUS_ORDER, PRIORITY_COLOR, PRIORITY_FA } from '../constants';

type Card = { id: number; title: string; status: PlanStatus | string; publish_date: string; publish_time?: string | null; priority?: string | null; kind?: 'content_item'; category?: { name: string } | null; primary_keyword?: string | null; page_type?: string | null };

/** Content calendar (month / week / list) over content plans (+ content items without a plan). Drag a card onto a day to reschedule. */
export function PlanCalendar({ siteId, onOpenPlan, onOpenItem, refreshKey, onChanged }: { siteId: string; onOpenPlan: (pid: number) => void; onOpenItem?: (cid: number) => void; refreshKey?: number; onChanged?: () => void }) {
  const [anchor, setAnchor] = useState(() => new Date(Date.UTC(new Date().getFullYear(), new Date().getMonth(), new Date().getDate())));
  const [view, setView] = useState<'month' | 'week' | 'list'>('month');
  const [cal, setCal] = useState<Awaited<ReturnType<typeof endpoints.planCalendar>> | null>(null);
  const [filters, setFilters] = useState({ category_id: '', status: '', priority: '' });
  const [drag, setDrag] = useState<Card | null>(null);
  const month = useMemo(() => jalaliMonthDays(anchor), [anchor]);
  const first = month.days[0]; const last = month.days[month.days.length - 1];
  const weekStart = useMemo(() => addDays(anchor, -((anchor.getUTCDay() + 1) % 7)), [anchor]);
  const from = view === 'week' ? iso(weekStart) : iso(addDays(first, -7)); const to = view === 'week' ? iso(addDays(weekStart, 6)) : iso(addDays(last, 7));
  const load = useCallback(async () => { try { setCal(await endpoints.planCalendar(siteId, { from, to, ...filters })); } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); } }, [siteId, from, to, filters]);
  useEffect(() => { load(); }, [load, refreshKey]);
  async function reschedule(c: Card, day: string | null) {
    try {
      if (c.kind === 'content_item') await endpoints.updateContent(siteId, c.id, day ? { publish_date: day } : { clear_date: true });
      else await endpoints.planPatch(siteId, c.id, { publish_date: day });
      toast.success(day ? `زمان‌بندی: ${day}` : 'از تقویم برداشته شد'); load(); onChanged?.();
    } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
  }
  const open = (c: Card) => (c.kind === 'content_item' ? onOpenItem?.(c.id) : onOpenPlan(c.id));
  const lead = (first.getUTCDay() + 1) % 7;
  const cells: (Date | null)[] = [...Array(lead).fill(null), ...month.days];
  while (cells.length % 7) cells.push(null);
  const today = iso(new Date());
  const scheduled = useMemo(() => Object.entries(cal?.days ?? {}).flatMap(([d, items]) => (items as Card[]).map((i) => ({ ...i, publish_date: d }))).sort((a, b) => (a.publish_date + (a.publish_time ?? '')).localeCompare(b.publish_date + (b.publish_time ?? ''))), [cal]);
  const CardBtn = ({ c, full }: { c: Card; full?: boolean }) => (
    <button draggable onDragStart={() => setDrag(c)} onClick={() => open(c)} title={`${c.title} · ${PLAN_STATUS_FA[c.status as PlanStatus] ?? c.status}${c.priority ? ` · اولویت ${PRIORITY_FA[c.priority]}` : ''}${c.category ? ` · ${c.category.name}` : ''}`}
            className={`flex items-center gap-1 truncate rounded px-1 py-0.5 text-start text-[11px] text-white ${full ? 'w-full' : ''}`} style={{ background: PLAN_STATUS_COLOR[c.status as PlanStatus] ?? '#64748b', borderInlineStart: `3px solid ${PRIORITY_COLOR[c.priority ?? ''] ?? 'transparent'}` }}>
      {c.kind === 'content_item' && <span title='آیتم محتوا بدون برنامه'>◦</span>}{c.publish_time ? <span dir='ltr'>{c.publish_time}</span> : null}<span className='truncate'>{c.title}</span>
    </button>
  );
  const dayCell = (d: Date, tall?: boolean) => { const day = iso(d); const items = (cal?.days[day] ?? []) as Card[]; const j = jalali(d); return (
    <div key={day} className={`bg-card rounded border p-1 text-start ${tall ? 'min-h-40' : 'min-h-24'} ${day === today ? 'border-primary' : ''}`} onDragOver={(e) => e.preventDefault()} onDrop={() => { if (drag) reschedule(drag, day); setDrag(null); }}>
      <div className='text-muted-foreground flex justify-between text-[10px]'><span>{faNum.format(j.d)} {tall ? JMONTHS[j.m - 1] : ''}</span><span dir='ltr'>{day.slice(5)}</span></div>
      <div className='mt-1 flex flex-col gap-0.5'>{items.map((c) => <CardBtn key={`${c.kind ?? 'p'}-${c.id}`} c={c} full />)}</div>
    </div>); };
  return (
    <div className='flex flex-col gap-2'>
      <div className='flex flex-wrap items-center gap-1 text-xs'>
        <Button variant='outline' size='sm' onClick={() => setAnchor(view === 'week' ? addDays(anchor, -7) : addDays(first, -1))}>‹ {view === 'week' ? 'هفته قبل' : 'ماه قبل'}</Button>
        <span className='text-sm font-semibold'>{view === 'week' ? `هفته ${faNum.format(jalali(weekStart).d)} ${JMONTHS[jalali(weekStart).m - 1]}` : `${JMONTHS[month.m - 1]} ${faYear.format(month.y)}`}</span>
        <Button variant='outline' size='sm' onClick={() => setAnchor(view === 'week' ? addDays(anchor, 7) : addDays(last, 1))}>{view === 'week' ? 'هفته بعد' : 'ماه بعد'} ›</Button>
        <Button variant='ghost' size='sm' onClick={() => setAnchor(new Date(Date.UTC(new Date().getFullYear(), new Date().getMonth(), new Date().getDate())))}>امروز</Button>
        <NativeSelect value={filters.category_id} onChange={(e) => setFilters((f) => ({ ...f, category_id: e.target.value }))} className='h-8 w-36'><NativeSelectOption value=''>همه دسته‌ها</NativeSelectOption>{(cal?.categories ?? []).map((c) => <NativeSelectOption key={c.id} value={c.id}>{c.name}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))} className='h-8 w-32'><NativeSelectOption value=''>همه وضعیت‌ها</NativeSelectOption>{PLAN_STATUS_ORDER.map((s) => <NativeSelectOption key={s} value={s}>{PLAN_STATUS_FA[s]}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect value={filters.priority} onChange={(e) => setFilters((f) => ({ ...f, priority: e.target.value }))} className='h-8 w-24'><NativeSelectOption value=''>اولویت</NativeSelectOption>{Object.entries(PRIORITY_FA).map(([k, v]) => <NativeSelectOption key={k} value={k}>{v}</NativeSelectOption>)}</NativeSelect>
        <span className='ms-auto flex flex-wrap gap-2'>{PLAN_STATUS_ORDER.map((s) => <span key={s} className='flex items-center gap-1'><span className='inline-block h-2.5 w-2.5 rounded-full' style={{ background: PLAN_STATUS_COLOR[s] }} />{PLAN_STATUS_FA[s]} {cal ? faNum.format(cal.counts.by_status[s] ?? 0) : ''}</span>)}</span>
      </div>
      <Tabs value={view} onValueChange={(v) => setView(v as any)}>
        <TabsList><TabsTrigger value='month'>ماهانه</TabsTrigger><TabsTrigger value='week'>هفتگی</TabsTrigger><TabsTrigger value='list'>فهرست</TabsTrigger></TabsList>
        <TabsContent value='month'>
          <div className='grid grid-cols-7 gap-1 text-center text-xs'>{WEEKDAYS_FA.map((w) => <div key={w} className='text-muted-foreground py-1 font-medium'>{w}</div>)}{cells.map((d, i) => (d ? dayCell(d) : <div key={i} className='min-h-24 rounded border border-dashed opacity-30' />))}</div>
        </TabsContent>
        <TabsContent value='week'>
          <div className='grid grid-cols-7 gap-1 text-center text-xs'>{WEEKDAYS_FA.map((w) => <div key={w} className='text-muted-foreground py-1 font-medium'>{w}</div>)}{Array.from({ length: 7 }, (_, i) => dayCell(addDays(weekStart, i), true))}</div>
        </TabsContent>
        <TabsContent value='list'>
          <div className='overflow-x-auto rounded-md border'><Table>
            <TableHeader><TableRow><TableHead>تاریخ</TableHead><TableHead>عنوان</TableHead><TableHead>کلمه کلیدی</TableHead><TableHead>دسته</TableHead><TableHead>وضعیت</TableHead><TableHead>اولویت</TableHead></TableRow></TableHeader>
            <TableBody>{scheduled.map((c) => { const j = jalali(new Date(c.publish_date + 'T00:00:00Z')); return (
              <TableRow key={`${c.kind ?? 'p'}-${c.id}`} className='cursor-pointer' onClick={() => open(c)}><TableCell title={c.publish_date}>{faNum.format(j.d)} {JMONTHS[j.m - 1]} {faYear.format(j.y)}{c.publish_time && <span className='text-muted-foreground' dir='ltr'> · {c.publish_time}</span>}</TableCell><TableCell className='font-medium'>{c.title}</TableCell><TableCell>{c.primary_keyword ?? '—'}</TableCell><TableCell>{c.category?.name ?? '—'}</TableCell><TableCell><Badge style={{ background: PLAN_STATUS_COLOR[c.status as PlanStatus] }}>{PLAN_STATUS_FA[c.status as PlanStatus] ?? c.status}</Badge></TableCell><TableCell>{c.priority ? PRIORITY_FA[c.priority] : '—'}</TableCell></TableRow>); })}
              {scheduled.length === 0 && <TableRow><TableCell colSpan={6} className='text-muted-foreground text-center'>در این بازه برنامه‌ای نیست.</TableCell></TableRow>}
            </TableBody></Table></div>
        </TabsContent>
      </Tabs>
      <div className='rounded-lg border border-dashed p-2' onDragOver={(e) => e.preventDefault()} onDrop={() => { if (drag) reschedule(drag, null); setDrag(null); }}>
        <div className='mb-1 text-xs font-medium'>بدون تاریخ ({faNum.format(cal?.unscheduled.length ?? 0)}) — برای زمان‌بندی، به یک روز بکشید</div>
        <div className='flex flex-wrap gap-1'>{(cal?.unscheduled ?? []).map((p) => <Badge key={p.id} draggable onDragStart={() => setDrag({ ...p, publish_date: '' })} onClick={() => onOpenPlan(p.id)} className='cursor-grab' style={{ background: PLAN_STATUS_COLOR[p.status] }}>{p.title}</Badge>)}</div>
      </div>
    </div>
  );
}
