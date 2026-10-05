'use client';

import { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { CommandWorkItem, WorkPerson } from '../api';

const number = new Intl.NumberFormat('fa-IR');
const dayMs = 86400000;
const closed = new Set(['verified', 'rejected', 'deferred']);
const startOfDay = (date: Date) => { const result = new Date(date); result.setHours(0, 0, 0, 0); return result; };

export function TeamPlanner({ items, people, onTask }: {
  items: CommandWorkItem[]; people: WorkPerson[]; onTask: (item: CommandWorkItem) => void;
}) {
  const [weekOffset, setWeekOffset] = useState(0);
  const days = useMemo(() => Array.from({ length: 14 }, (_, index) => {
    const date = startOfDay(new Date()); date.setDate(date.getDate() + weekOffset * 7 + index);
    return date;
  }), [weekOffset]);
  const active = items.filter((item) => !closed.has(item.status));
  const assigned = people.filter((person) => person.active && active.some((item) => item.owner_id === person.id));
  const unscheduled = active.filter((item) => !item.due_at || !item.owner_id);
  const dayMatches = (item: CommandWorkItem, day: Date) => {
    if (!item.due_at) return false;
    const start = startOfDay(new Date(item.start_at || item.due_at)).getTime();
    const end = startOfDay(new Date(item.due_at)).getTime();
    return day.getTime() >= start && day.getTime() <= end;
  };

  return <div className='space-y-4'>
    <Card><CardHeader className='flex flex-row flex-wrap items-center justify-between gap-3'><div><CardTitle>برنامهٔ دو هفته‌ای تیم</CardTitle><CardDescription>ردیف هر نفر، کارهای فعال او را در روزهای برنامه‌ریزی‌شده نشان می‌دهد. برای جزئیات روی کار بزنید.</CardDescription></div><div className='flex items-center gap-2'><Button size='sm' variant='outline' onClick={() => setWeekOffset((value) => value - 1)}>هفتهٔ قبل</Button><Button size='sm' variant='outline' onClick={() => setWeekOffset(0)}>امروز</Button><Button size='sm' variant='outline' onClick={() => setWeekOffset((value) => value + 1)}>هفتهٔ بعد</Button></div></CardHeader><CardContent>
      <div className='overflow-x-auto rounded-xl border'><table className='w-full min-w-[1150px] border-collapse text-xs'><thead><tr className='bg-muted/60'><th className='sticky right-0 z-10 min-w-40 border-l bg-muted p-3 text-right'>مسئول / بار کار</th>{days.map((day) => <th key={day.toISOString()} className={`min-w-16 border-l p-2 text-center ${day.toDateString() === new Date().toDateString() ? 'bg-emerald-500/15' : ''}`}>{day.toLocaleDateString('fa-IR', { weekday: 'short', day: 'numeric', month: 'short' })}</th>)}</tr></thead><tbody>
        {assigned.map((person) => { const tasks = active.filter((item) => item.owner_id === person.id); const hours = tasks.reduce((sum, item) => sum + (item.estimated_hours || 0), 0); return <tr key={person.id} className='border-t'><th className='sticky right-0 z-10 border-l bg-card p-3 text-right'><strong className='block truncate'>{person.full_name}</strong><span className='text-muted-foreground'>{number.format(tasks.length)} کار · {number.format(hours)} ساعت برآوردی</span></th>{days.map((day) => { const daily = tasks.filter((item) => dayMatches(item, day)); return <td key={day.toISOString()} className={`h-16 border-l p-1 align-top ${daily.length > 2 ? 'bg-rose-500/10' : daily.length > 0 ? 'bg-emerald-500/5' : ''}`}>{daily.map((item) => <button key={item.id} title={`${item.title} · ${item.site_name}`} onClick={() => onTask(item)} className={`mb-1 block w-full truncate rounded px-1.5 py-1 text-right text-[11px] hover:opacity-75 ${item.status === 'blocked' ? 'bg-rose-500/20 text-rose-700 dark:text-rose-300' : 'bg-sky-500/15 text-sky-700 dark:text-sky-300'}`}>{item.title}</button>)}</td>; })}</tr>; })}
      </tbody></table>{!assigned.length && <p className='text-muted-foreground p-8 text-center text-sm'>کار زمان‌بندی‌شده‌ای به اعضای تیم واگذار نشده است.</p>}</div>
      <p className='text-muted-foreground mt-3 text-xs'>رنگ قرمز یعنی مانع یا تراکم بیش از دو کار در یک روز. ساعت‌ها جمع برآورد کل کارهای باز هر نفرند، نه ظرفیت قراردادی روزانه.</p>
    </CardContent></Card>
    <Card><CardHeader><CardTitle>کارهای بیرون از برنامه</CardTitle><CardDescription>کارهای بدون مسئول یا موعد، در برنامهٔ تیم ظاهر نمی‌شوند و باید تعیین تکلیف شوند.</CardDescription></CardHeader><CardContent className='flex flex-wrap gap-2'>{unscheduled.map((item) => <Button key={item.id} size='sm' variant='outline' onClick={() => onTask(item)}>{item.title}<Badge variant='secondary' className='mr-2'>{!item.owner_id ? 'بی‌مسئول' : 'بی‌موعد'}</Badge></Button>)}{!unscheduled.length && <p className='text-muted-foreground text-sm'>همهٔ کارهای باز مسئول و موعد دارند.</p>}</CardContent></Card>
  </div>;
}
