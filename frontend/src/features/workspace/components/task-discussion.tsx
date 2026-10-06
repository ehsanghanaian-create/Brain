'use client';

import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { formatUserDateTime, useDatePreference } from '@/lib/date-preference';
import { commandApi, type CommandWorkItem } from '../api';

type WorkEvent = Awaited<ReturnType<typeof commandApi.events>>[number];
const eventName: Record<string, string> = {
  created: 'تسک ساخته شد', updated: 'تسک ویرایش شد', deleted: 'به آرشیو حذف‌شده‌ها رفت',
  restored: 'از آرشیو برگشت', subtask_added: 'زیرتسک ساخته شد',
  checklist_added: 'گام افزوده شد', checklist_updated: 'گام تغییر کرد',
  bulk_updated: 'ویرایش گروهی شد', comment: 'پیام'
};

export function TaskDiscussion({ item, canEdit, onOpenTask, onChanged }: {
  item: CommandWorkItem; canEdit: boolean; onOpenTask: (item: CommandWorkItem) => void;
  onChanged: () => void;
}) {
  const { calendar } = useDatePreference();
  const [children, setChildren] = useState<CommandWorkItem[]>([]);
  const [events, setEvents] = useState<WorkEvent[]>([]);
  const [childTitle, setChildTitle] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const [childRows, eventRows] = await Promise.all([commandApi.subtasks(item), commandApi.events(item)]);
      setChildren(childRows); setEvents(eventRows);
    } catch (error) { toast.error(error instanceof Error ? error.message : 'جزئیات تسک دریافت نشد'); }
  }, [item.id, item.site_id]);
  useEffect(() => { void refresh(); }, [refresh]);

  async function addChild() {
    if (childTitle.trim().length < 3) return;
    setBusy(true);
    try { await commandApi.createSubtask(item, childTitle.trim()); setChildTitle(''); await refresh(); onChanged();
      toast.success('زیرتسک ساخته شد'); }
    catch (error) { toast.error(error instanceof Error ? error.message : 'ساخت زیرتسک انجام نشد'); }
    finally { setBusy(false); }
  }
  async function post() {
    if (!message.trim()) return;
    setBusy(true);
    try { await commandApi.addComment(item, message.trim()); setMessage(''); await refresh(); onChanged(); }
    catch (error) { toast.error(error instanceof Error ? error.message : 'ارسال پیام انجام نشد'); }
    finally { setBusy(false); }
  }

  return <section className='grid gap-4 border-t pt-4 sm:col-span-2 lg:grid-cols-[minmax(0,1fr)_320px]'>
    <div className='space-y-3'>
      <div className='flex items-center justify-between'><h3 className='text-sm font-semibold'>زیرتسک‌ها</h3><span className='text-muted-foreground text-xs'>{children.length} مورد</span></div>
      <div className='overflow-hidden rounded-lg border'>
        {children.map((child) => <button key={child.id} type='button' onClick={() => onOpenTask(child)} className='flex w-full items-center justify-between gap-2 border-b px-3 py-2 text-right text-sm last:border-b-0 hover:bg-muted/50'>
          <span className='min-w-0 truncate'>{child.status === 'verified' ? '✓ ' : '○ '}{child.title}</span>
          <span className='text-muted-foreground shrink-0 text-xs'>{child.owner_name || 'بی‌مسئول'}</span>
        </button>)}
        {!children.length && <p className='text-muted-foreground p-3 text-xs'>زیرتسکی ثبت نشده است.</p>}
      </div>
      {canEdit && <div className='flex gap-2'><Input aria-label='عنوان زیرتسک' placeholder='افزودن زیرتسک…' value={childTitle} maxLength={200} onChange={(event) => setChildTitle(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void addChild(); }} /><Button size='sm' disabled={busy || childTitle.trim().length < 3} onClick={() => void addChild()}>افزودن</Button></div>}
      {!canEdit && <p className='text-muted-foreground text-xs'>این تسک برای شما فقط خواندنی است؛ برای هماهنگی از گفت‌وگو استفاده کنید.</p>}
    </div>
    <aside className='flex min-h-64 flex-col overflow-hidden rounded-xl border bg-muted/20'>
      <h3 className='border-b px-3 py-2 text-sm font-semibold'>گفت‌وگو و فعالیت</h3>
      <div className='max-h-80 flex-1 space-y-2 overflow-y-auto p-3'>
        {[...events].reverse().map((event) => <div key={event.id} className={event.event_type === 'comment' ? 'rounded-lg border bg-background p-2' : 'border-r-2 border-muted-foreground/30 pr-2'}>
          <div className='flex flex-wrap items-center justify-between gap-1 text-[11px] text-muted-foreground'><span>{event.actor_username || 'سیستم'} · {eventName[event.event_type] || 'تغییر'}</span><time>{formatUserDateTime(event.created_at, calendar)}</time></div>
          {event.note && <p className='mt-1 whitespace-pre-wrap text-xs leading-5'>{event.note}</p>}
        </div>)}
        {!events.length && <p className='text-muted-foreground text-xs'>هنوز فعالیتی ثبت نشده است.</p>}
      </div>
      <div className='space-y-2 border-t bg-background p-3'><Textarea aria-label='پیام گفت‌وگوی تسک' placeholder='برای اعضای پروژه پیام بگذارید…' rows={2} maxLength={2000} value={message} onChange={(event) => setMessage(event.target.value)} /><Button size='sm' disabled={busy || !message.trim()} onClick={() => void post()}>ارسال پیام</Button></div>
    </aside>
  </section>;
}
