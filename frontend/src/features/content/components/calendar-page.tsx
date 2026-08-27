'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ApiError, endpoints, type ContentCalendar, type ContentItem, type Site } from '@/lib/api/client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { JMONTHS, STATUS_COLOR, STATUS_FA, STATUS_ORDER, WEEKDAYS_FA, addDays, faNum, faYear, iso, jalali, jalaliMonthDays } from '../constants';
import { ContentEditor } from './content-editor';

export function CalendarPage({ sites, initialSiteId }: { sites: Site[]; initialSiteId: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [anchor, setAnchor] = useState(() => new Date(Date.UTC(new Date().getFullYear(), new Date().getMonth(), new Date().getDate())));
  const [cal, setCal] = useState<ContentCalendar | null>(null);
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const [dragId, setDragId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const month = useMemo(() => jalaliMonthDays(anchor), [anchor]);
  const first = month.days[0]; const last = month.days[month.days.length - 1];
  const from = iso(addDays(first, -7)); const to = iso(addDays(last, 7));

  const load = useCallback(async () => {
    setError(null);
    try { setCal(await endpoints.contentCalendar(siteId, from, to)); } catch (e) { setError(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)); }
  }, [siteId, from, to]);
  useEffect(() => { load(); }, [load]);

  async function reschedule(id: number, day: string | null) {
    try { await endpoints.updateContent(siteId, id, day ? { publish_date: day } : { clear_date: true }); toast.success(day ? `زمان‌بندی: ${day}` : 'از تقویم برداشته شد'); load(); }
    catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
  }
  // Saturday-first grid: pad leading cells
  const lead = (first.getUTCDay() + 1) % 7; // Sat=0 … Fri=6
  const cells: (Date | null)[] = [...Array(lead).fill(null), ...month.days];
  while (cells.length % 7) cells.push(null);
  const today = iso(new Date());
  const scheduled = useMemo(() => Object.entries(cal?.days ?? {}).flatMap(([d, items]) => items.map((i) => ({ ...i, publish_date: d }))).sort((a, b) => (a.publish_date! + (a.publish_time ?? '')).localeCompare(b.publish_date! + (b.publish_time ?? ''))), [cal]);

  return (
    <div className='flex flex-col gap-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect value={siteId} onChange={(e) => setSiteId(e.target.value)} className='w-44'>{sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>)}</NativeSelect>
        <Button variant='outline' size='sm' onClick={() => setAnchor(addDays(first, -1))}>‹ ماه قبل</Button>
        <span className='text-sm font-semibold'>{JMONTHS[month.m - 1]} {faYear.format(month.y)}</span>
        <Button variant='outline' size='sm' onClick={() => setAnchor(addDays(last, 1))}>ماه بعد ›</Button>
        <Button variant='ghost' size='sm' onClick={() => setAnchor(new Date())}>امروز</Button>
        <Button onClick={() => setEditing('new')} className='ms-auto'>محتوای جدید</Button>
      </div>
      {error && <p className='text-destructive text-sm'>{error}</p>}
      <div className='flex flex-wrap gap-1 text-xs'>
        {STATUS_ORDER.map((s) => <span key={s} className='flex items-center gap-1'><span className='inline-block h-2.5 w-2.5 rounded-full' style={{ background: STATUS_COLOR[s] }} />{STATUS_FA[s]} {cal ? faNum.format(cal.counts.by_status[s]) : ''}</span>)}
      </div>
      <Tabs defaultValue='month'>
        <TabsList><TabsTrigger value='month'>نمای ماهانه</TabsTrigger><TabsTrigger value='list'>فهرست</TabsTrigger></TabsList>
        <TabsContent value='month'>
          <div className='grid grid-cols-7 gap-1 text-center text-xs'>
            {WEEKDAYS_FA.map((w) => <div key={w} className='text-muted-foreground py-1 font-medium'>{w}</div>)}
            {cells.map((d, i) => {
              if (!d) return <div key={i} className='min-h-24 rounded border border-dashed opacity-30' />;
              const day = iso(d); const items = cal?.days[day] ?? []; const j = jalali(d);
              return (
                <div key={day} className={`bg-card min-h-24 rounded border p-1 text-start ${day === today ? 'border-primary' : ''}`}
                     onDragOver={(e) => e.preventDefault()} onDrop={() => { if (dragId) reschedule(dragId, day); setDragId(null); }}>
                  <div className='text-muted-foreground flex justify-between text-[10px]'><span>{faNum.format(j.d)}</span><span dir='ltr'>{day.slice(5)}</span></div>
                  <div className='mt-1 flex flex-col gap-0.5'>
                    {items.map((it) => (
                      <button key={it.id} draggable onDragStart={() => setDragId(it.id)} onClick={() => setEditing(it.id)} title={`${it.title} · ${STATUS_FA[it.status]}`}
                              className='truncate rounded px-1 py-0.5 text-start text-[11px] text-white' style={{ background: STATUS_COLOR[it.status] }}>
                        {it.publish_time ? <span dir='ltr'>{it.publish_time} </span> : null}{it.title}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
          <div className='mt-3 rounded-lg border border-dashed p-2' onDragOver={(e) => e.preventDefault()} onDrop={() => { if (dragId) reschedule(dragId, null); setDragId(null); }}>
            <div className='mb-1 text-xs font-medium'>بدون تاریخ ({faNum.format(cal?.unscheduled.length ?? 0)}) — برای زمان‌بندی، به یک روز بکشید</div>
            <div className='flex flex-wrap gap-1'>{cal?.unscheduled.map((it) => <Badge key={it.id} draggable onDragStart={() => setDragId(it.id)} onClick={() => setEditing(it.id)} className='cursor-grab' style={{ background: STATUS_COLOR[it.status] }}>{it.title}</Badge>)}</div>
          </div>
        </TabsContent>
        <TabsContent value='list'>
          <div className='overflow-x-auto rounded-md border'>
            <Table>
              <TableHeader><TableRow><TableHead>تاریخ</TableHead><TableHead>ساعت</TableHead><TableHead>عنوان</TableHead><TableHead>کلمه کلیدی</TableHead><TableHead>وضعیت</TableHead><TableHead>اولویت</TableHead><TableHead>URL</TableHead></TableRow></TableHeader>
              <TableBody>
                {scheduled.map((it: ContentItem) => (
                  <TableRow key={it.id} className='cursor-pointer' onClick={() => setEditing(it.id)}>
                    <TableCell title={it.publish_date ?? undefined}>{(() => { const j = jalali(new Date(it.publish_date + 'T00:00:00Z')); return `${faNum.format(j.d)} ${JMONTHS[j.m - 1]} ${faYear.format(j.y)}`; })()}</TableCell>
                    <TableCell dir='ltr'>{it.publish_time ?? '—'}</TableCell><TableCell className='font-medium'>{it.title}</TableCell><TableCell>{it.target_keyword ?? '—'}</TableCell>
                    <TableCell><Badge style={{ background: STATUS_COLOR[it.status] }}>{it.status_fa}</Badge></TableCell><TableCell>{it.priority ?? '—'}</TableCell><TableCell className='max-w-48 truncate' dir='ltr'>{it.url ?? '—'}</TableCell>
                  </TableRow>
                ))}
                {scheduled.length === 0 && <TableRow><TableCell colSpan={7} className='text-muted-foreground text-center'>در این بازه محتوای زمان‌بندی‌شده‌ای نیست.</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>
      <ContentEditor siteId={siteId} cid={editing} onClose={() => setEditing(null)} onChanged={load} />
    </div>
  );
}
