'use client';

import { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatUserDate, useDatePreference } from '@/lib/date-preference';
import type { CommandWorkItem, WorkPerson } from '../api';

const number = new Intl.NumberFormat('fa-IR');
const closed = new Set(['verified', 'rejected', 'deferred']);
const day = (value: Date) => { const result = new Date(value); result.setHours(0, 0, 0, 0); return result; };
const phase = (status: string) => status === 'review' ? 'منتظر بازبینی' : status === 'in_progress' ? 'در حال اجرا' :
  status === 'blocked' ? 'مانع‌دار' : 'آماده / ورودی';

export function TeamPlanner({ items, people, total, onTask }: {
  items: CommandWorkItem[]; people: WorkPerson[]; total?: number;
  onTask: (item: CommandWorkItem) => void;
}) {
  const { calendar } = useDatePreference();
  const [weekOffset, setWeekOffset] = useState(0);
  const days = useMemo(() => Array.from({ length: 14 }, (_, index) => {
    const date = day(new Date()); date.setDate(date.getDate() + weekOffset * 7 + index);
    return date;
  }), [weekOffset]);
  const active = items.filter((item) => !closed.has(item.status));
  const assigned = people.filter((person) => person.active && active.some((item) => item.owner_id === person.id));
  const withoutOwner = active.filter((item) => !item.owner_id);
  const withoutDue = active.filter((item) => !item.due_at);
  const dated = active.filter((item) => item.due_at);
  const dayMatches = (item: CommandWorkItem, date: Date) => {
    if (!item.due_at) return false;
    const start = day(new Date(item.start_at || item.due_at)).getTime();
    const end = day(new Date(item.due_at)).getTime();
    return date.getTime() >= start && date.getTime() <= end;
  };
  const taskButton = (item: CommandWorkItem) => <button key={item.id} type='button' onClick={() => onTask(item)}
    className={`flex w-full items-start justify-between gap-2 rounded-lg border p-2 text-right text-xs transition-colors hover:border-primary/50 hover:bg-muted/50 ${item.status === 'review' ? 'border-amber-500/30 bg-amber-500/5' : ''}`}>
    <span className='min-w-0'><strong className='block truncate'>{item.title}</strong>
      <span className='text-muted-foreground mt-1 block truncate'>{item.site_name} · {phase(item.status)}</span></span>
    <span className='shrink-0 text-[10px] text-muted-foreground'>{item.due_at ? formatUserDate(item.due_at, calendar, { month: 'short', day: 'numeric' }) : 'بی‌موعد'}</span>
  </button>;

  return <div className='space-y-4'>
    <Card><CardHeader><CardTitle>کارهای واقعی تیم</CardTitle>
      <CardDescription>همهٔ کارهای باز هر نفر، حتی اگر هنوز تاریخ ندارند. «بی‌موعد» یعنی زمان‌بندی ثبت نشده است؛ تاریخ حدسی نمایش داده نمی‌شود.</CardDescription>
    </CardHeader><CardContent className='space-y-4'>
      <div className='flex flex-wrap gap-2 text-xs'>
        <Badge variant='outline'>{number.format(active.length)} کار باز در این نما</Badge>
        <Badge variant='outline'>{number.format(active.filter((item) => item.status === 'review').length)} منتظر بازبینی</Badge>
        <Badge variant='outline'>{number.format(withoutDue.length)} بی‌موعد</Badge>
      </div>
      {total !== undefined && total > items.length && <p className='rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-700'>این نما {number.format(items.length)} کار از {number.format(total)} کار را دریافت کرده است. برای فهرست کامل از داشبورد مدیریت استفاده کنید.</p>}
      <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-3'>
        {assigned.map((person) => {
          const tasks = active.filter((item) => item.owner_id === person.id).toSorted((a, b) =>
            Number(b.status === 'review') - Number(a.status === 'review') || (a.due_at || '9999').localeCompare(b.due_at || '9999'));
          return <section key={person.id} className='rounded-xl border bg-card p-3'>
            <div className='mb-3 flex items-center justify-between gap-2'><strong className='text-sm'>{person.full_name}</strong>
              <span className='text-muted-foreground text-xs'>{number.format(tasks.length)} کار · {number.format(tasks.filter((item) => !item.due_at).length)} بی‌موعد</span></div>
            <div className='max-h-72 space-y-1.5 overflow-y-auto'>{tasks.map(taskButton)}</div>
          </section>;
        })}
        {withoutOwner.length > 0 && <section className='rounded-xl border border-amber-500/30 bg-amber-500/5 p-3'>
          <div className='mb-3 flex items-center justify-between gap-2'><strong className='text-sm'>بی‌مسئول</strong><Badge variant='outline'>{number.format(withoutOwner.length)}</Badge></div>
          <div className='max-h-72 space-y-1.5 overflow-y-auto'>{withoutOwner.map(taskButton)}</div>
        </section>}
      </div>
      {!active.length && <p className='text-muted-foreground rounded-xl border border-dashed p-8 text-center text-sm'>کار بازی در این نما ثبت نشده است.</p>}
    </CardContent></Card>

    <Card><CardHeader className='flex flex-row flex-wrap items-center justify-between gap-3'><div>
      <CardTitle>زمان‌بندی دو هفته‌ای</CardTitle><CardDescription>فقط کارهایی که برایشان موعد واقعی ثبت شده است روی تقویم قرار می‌گیرند.</CardDescription>
    </div><div className='flex gap-2'><Button size='sm' variant='outline' onClick={() => setWeekOffset((value) => value - 1)}>هفتهٔ قبل</Button>
      <Button size='sm' variant='outline' onClick={() => setWeekOffset(0)}>امروز</Button>
      <Button size='sm' variant='outline' onClick={() => setWeekOffset((value) => value + 1)}>هفتهٔ بعد</Button></div></CardHeader>
      <CardContent>{dated.length ? <div className='overflow-x-auto rounded-xl border'><table className='w-full min-w-[1150px] border-collapse text-xs'>
        <thead><tr className='bg-muted/60'><th className='sticky right-0 z-10 min-w-40 border-l bg-muted p-3 text-right'>مسئول / بار کار</th>
          {days.map((date) => <th key={date.toISOString()} className={`min-w-16 border-l p-2 text-center ${date.toDateString() === new Date().toDateString() ? 'bg-emerald-500/15' : ''}`}>{formatUserDate(date, calendar, { weekday: 'short', day: 'numeric', month: 'short' })}</th>)}</tr></thead>
        <tbody>{assigned.map((person) => {
          const tasks = dated.filter((item) => item.owner_id === person.id);
          return <tr key={person.id} className='border-t'><th className='sticky right-0 z-10 border-l bg-card p-3 text-right'><strong className='block truncate'>{person.full_name}</strong>
            <span className='text-muted-foreground'>{number.format(tasks.length)} کار دارای موعد</span></th>
            {days.map((date) => { const daily = tasks.filter((item) => dayMatches(item, date)); return <td key={date.toISOString()} className={`h-16 border-l p-1 align-top ${daily.length > 2 ? 'bg-rose-500/10' : daily.length ? 'bg-emerald-500/5' : ''}`}>
              {daily.map((item) => <button key={item.id} type='button' onClick={() => onTask(item)} title={`${item.title} · ${item.site_name}`}
                className='mb-1 block w-full truncate rounded bg-sky-500/15 px-1.5 py-1 text-right text-[11px] hover:bg-sky-500/25'>{item.title}</button>)}
            </td>; })}</tr>;
        })}</tbody></table></div> : <div className='rounded-xl border border-dashed p-6 text-sm'>
        <strong>هنوز هیچ کار بازی موعد ندارد.</strong><p className='text-muted-foreground mt-1'>کارها در کارت‌های بالا دیده می‌شوند. با ثبت موعد در کارت هر کار، برنامهٔ روزانه و گانت مدیریت هم پر می‌شوند.</p>
      </div>}</CardContent></Card>
  </div>;
}
