'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { WEEKDAYS_FA, addDays, faNum, iso } from '@/features/content/constants';
import { userMonthDays } from '@/lib/calendar-days';
import { formatUserDate, useDatePreference } from '@/lib/date-preference';
import { ApiError, endpoints, type PlanStatus } from '@/lib/api/client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { motion, useReducedMotion } from 'motion/react';
import { PLAN_STATUS_COLOR, PLAN_STATUS_FA, PLAN_STATUS_ORDER, PRIORITY_COLOR, PRIORITY_FA } from '../constants';

type Card = { id: number; title: string; status: PlanStatus | string; publish_date: string; publish_time?: string | null; priority?: string | null; kind?: 'content_item'; category?: { name: string } | null; primary_keyword?: string | null; page_type?: string | null };

/** Content calendar (month / week / list) over content plans (+ content items without a plan). Drag a card onto a day to reschedule. */
export function PlanCalendar({ siteId, onOpenPlan, onOpenItem, onNewOnDay, refreshKey, onChanged }: { siteId: string; onOpenPlan: (pid: number) => void; onOpenItem?: (cid: number) => void; onNewOnDay?: (isoDay: string) => void; refreshKey?: number; onChanged?: () => void }) {
  const { calendar } = useDatePreference();
  const [anchor, setAnchor] = useState(() => new Date(Date.UTC(new Date().getFullYear(), new Date().getMonth(), new Date().getDate())));
  const [view, setView] = useState<'month' | 'week' | 'list'>('month');
  const [cal, setCal] = useState<Awaited<ReturnType<typeof endpoints.planCalendar>> | null>(null);
  const [filters, setFilters] = useState({ category_id: '', status: '', priority: '' });
  const [drag, setDrag] = useState<Card | null>(null);
  const reducedMotion = useReducedMotion();
  const monthDays = useMemo(() => userMonthDays(anchor, calendar), [anchor, calendar]);
  const first = monthDays[0]; const last = monthDays[monthDays.length - 1];
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
  const cells: (Date | null)[] = [...Array(lead).fill(null), ...monthDays];
  while (cells.length % 7) cells.push(null);
  const today = iso(new Date());
  const scheduled = useMemo(() => Object.entries(cal?.days ?? {}).flatMap(([d, items]) => (items as Card[]).map((i) => ({ ...i, publish_date: d }))).sort((a, b) => (a.publish_date + (a.publish_time ?? '')).localeCompare(b.publish_date + (b.publish_time ?? ''))), [cal]);
  const CardBtn = ({ c, full }: { c: Card; full?: boolean }) => {
    const color = PLAN_STATUS_COLOR[c.status as PlanStatus] ?? '#64748b';
    return (
    <motion.button type='button' draggable onDragStart={() => setDrag(c)} onClick={() => open(c)} whileHover={reducedMotion ? undefined : { x: -2, scale: 1.015 }} title={`${c.title} · ${PLAN_STATUS_FA[c.status as PlanStatus] ?? c.status}${c.priority ? ` · اولویت ${PRIORITY_FA[c.priority]}` : ''}${c.category ? ` · ${c.category.name}` : ''}`}
            className={`flex items-center gap-1.5 truncate rounded-md px-2 py-1.5 text-start text-[11px] font-medium shadow-sm transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${full ? 'w-full' : ''}`} style={{ color, background: `color-mix(in srgb, ${color} 12%, var(--card))`, borderInlineStart: `3px solid ${PRIORITY_COLOR[c.priority ?? ''] ?? color}` }}>
      {c.kind === 'content_item' && <span title='آیتم محتوا بدون برنامه'>◦</span>}{c.publish_time ? <span dir='ltr'>{c.publish_time}</span> : null}<span className='truncate'>{c.title}</span>
    </motion.button>
  ); };
  const dayCell = (d: Date, tall?: boolean) => { const day = iso(d); const items = (cal?.days[day] ?? []) as Card[]; return (
    <motion.div key={day} whileHover={reducedMotion ? undefined : { backgroundColor: 'var(--muted)' }} className={`group relative bg-card border border-border/70 p-2 text-start transition-colors ${tall ? 'min-h-44' : 'min-h-28'} ${day === today ? 'ring-primary ring-2 ring-inset' : ''}`} onDragOver={(e) => e.preventDefault()} onDrop={() => { if (drag) reschedule(drag, day); setDrag(null); }}>
      <div className='text-muted-foreground flex items-center justify-between text-[11px]'>
        <span className={day === today ? 'bg-primary text-primary-foreground flex size-6 items-center justify-center rounded-full font-bold' : 'font-semibold'}>{formatUserDate(d, calendar, { day: 'numeric', ...(tall ? { month: 'long' as const } : {}), timeZone: 'UTC' })}</span>
        <span className='flex items-center gap-1'>
          {onNewOnDay && <button type='button' title='مقاله جدید در این روز' aria-label='مقاله جدید در این روز' className='hover:bg-accent rounded px-1 leading-none opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100' onClick={() => onNewOnDay(day)}>+</button>}
          <span dir='ltr'>{day.slice(5)}</span>
        </span>
      </div>
      <div className='mt-2 flex flex-col gap-1'>{items.map((c) => <CardBtn key={`${c.kind ?? 'p'}-${c.id}`} c={c} full />)}</div>
    </motion.div>); };
  return (
    <div className='flex flex-col gap-4'>
      <div className='rounded-xl border border-border bg-card p-4 shadow-sm'><div className='flex flex-wrap items-center gap-2 text-xs'>
        <Button variant='outline' size='sm' onClick={() => setAnchor(view === 'week' ? addDays(anchor, -7) : addDays(first, -1))}>‹ {view === 'week' ? 'هفته قبل' : 'ماه قبل'}</Button>
        <span className='text-sm font-semibold'>{view === 'week' ? `هفتهٔ ${formatUserDate(weekStart, calendar, { day: 'numeric', month: 'long', timeZone: 'UTC' })}` : formatUserDate(first, calendar, { month: 'long', year: 'numeric', timeZone: 'UTC' })}</span>
        <Button variant='outline' size='sm' onClick={() => setAnchor(view === 'week' ? addDays(anchor, 7) : addDays(last, 1))}>{view === 'week' ? 'هفته بعد' : 'ماه بعد'} ›</Button>
        <Button variant='ghost' size='sm' onClick={() => setAnchor(new Date(Date.UTC(new Date().getFullYear(), new Date().getMonth(), new Date().getDate())))}>امروز</Button>
        <NativeSelect value={filters.category_id} onChange={(e) => setFilters((f) => ({ ...f, category_id: e.target.value }))} className='h-8 w-36'><NativeSelectOption value=''>همه دسته‌ها</NativeSelectOption>{(cal?.categories ?? []).map((c) => <NativeSelectOption key={c.id} value={c.id}>{c.name}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))} className='h-8 w-32'><NativeSelectOption value=''>همه وضعیت‌ها</NativeSelectOption>{PLAN_STATUS_ORDER.map((s) => <NativeSelectOption key={s} value={s}>{PLAN_STATUS_FA[s]}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect value={filters.priority} onChange={(e) => setFilters((f) => ({ ...f, priority: e.target.value }))} className='h-8 w-24'><NativeSelectOption value=''>اولویت</NativeSelectOption>{Object.entries(PRIORITY_FA).map(([k, v]) => <NativeSelectOption key={k} value={k}>{v}</NativeSelectOption>)}</NativeSelect>
        <span className='ms-auto flex flex-wrap gap-2'>{PLAN_STATUS_ORDER.map((s) => <span key={s} className='flex items-center gap-1 rounded-full border border-border/70 px-2 py-1'><span className='inline-block h-2.5 w-2.5 rounded-full' style={{ background: PLAN_STATUS_COLOR[s] }} />{PLAN_STATUS_FA[s]} {cal ? faNum.format(cal.counts.by_status[s] ?? 0) : ''}</span>)}</span>
      </div></div>
      <Tabs value={view} onValueChange={(v) => setView(v as any)}>
        <TabsList><TabsTrigger value='month'>ماهانه</TabsTrigger><TabsTrigger value='week'>هفتگی</TabsTrigger><TabsTrigger value='list'>فهرست</TabsTrigger></TabsList>
        <TabsContent value='month'>
          <div className='overflow-x-auto rounded-xl border border-border bg-card shadow-sm'><div className='grid min-w-[770px] grid-cols-7 text-center text-xs'>{WEEKDAYS_FA.map((w) => <div key={w} className='bg-muted/60 border-b border-border py-3 font-semibold'>{w}</div>)}{cells.map((d, i) => (d ? dayCell(d) : <div key={i} className='min-h-28 border border-border/40 bg-muted/25' />))}</div></div>
        </TabsContent>
        <TabsContent value='week'>
          <div className='overflow-x-auto rounded-xl border border-border bg-card shadow-sm'><div className='grid min-w-[770px] grid-cols-7 text-center text-xs'>{WEEKDAYS_FA.map((w) => <div key={w} className='bg-muted/60 border-b border-border py-3 font-semibold'>{w}</div>)}{Array.from({ length: 7 }, (_, i) => dayCell(addDays(weekStart, i), true))}</div></div>
        </TabsContent>
        <TabsContent value='list'>
          <div className='overflow-x-auto rounded-md border'><Table>
            <TableHeader><TableRow><TableHead>تاریخ</TableHead><TableHead>عنوان</TableHead><TableHead>کلمه کلیدی</TableHead><TableHead>دسته</TableHead><TableHead>وضعیت</TableHead><TableHead>اولویت</TableHead></TableRow></TableHeader>
            <TableBody>{scheduled.map((c) => (
              <TableRow key={`${c.kind ?? 'p'}-${c.id}`} className='cursor-pointer' onClick={() => open(c)}><TableCell title={c.publish_date}>{formatUserDate(`${c.publish_date}T12:00:00Z`, calendar, { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' })}{c.publish_time && <span className='text-muted-foreground' dir='ltr'> · {c.publish_time}</span>}</TableCell><TableCell className='font-medium'>{c.title}</TableCell><TableCell>{c.primary_keyword ?? '—'}</TableCell><TableCell>{c.category?.name ?? '—'}</TableCell><TableCell><Badge style={{ background: PLAN_STATUS_COLOR[c.status as PlanStatus] }}>{PLAN_STATUS_FA[c.status as PlanStatus] ?? c.status}</Badge></TableCell><TableCell>{c.priority ? PRIORITY_FA[c.priority] : '—'}</TableCell></TableRow>))}
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
