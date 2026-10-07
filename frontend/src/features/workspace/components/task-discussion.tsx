'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { formatUserDateTime, useDatePreference } from '@/lib/date-preference';
import { commandApi, type CommandWorkItem, type TaskDiscussionData, type WorkChecklistItem } from '../api';

const noteType: Record<string, string> = {
  created: 'توضیح هنگام ایجاد', updated: 'یادداشت تغییر', handoff: 'دلیل ارجاع',
  comment: 'پیام', deleted: 'یادداشت حذف', restored: 'یادداشت بازگردانی'
};
const activityType: Record<string, string> = {
  created: 'ساخته شد', updated: 'ویرایش شد', deleted: 'حذف شد', restored: 'بازیابی شد',
  subtask_added: 'زیرتسک افزوده شد', checklist_added: 'گام افزوده شد',
  checklist_updated: 'گام تغییر کرد', bulk_updated: 'گروهی ویرایش شد',
  handoff: 'ارجاع شد'
};

export function TaskDiscussion({ item, canEdit, canComment, onChanged }: {
  item: CommandWorkItem; canEdit: boolean; canComment: boolean;
  onChanged: () => void;
}) {
  const { calendar } = useDatePreference();
  const input = useRef<HTMLTextAreaElement>(null);
  const [checklist, setChecklist] = useState<WorkChecklistItem[]>([]);
  const [thread, setThread] = useState<TaskDiscussionData | null>(null);
  const [checklistTitle, setChecklistTitle] = useState('');
  const [message, setMessage] = useState('');
  const [caret, setCaret] = useState(0);
  const [focused, setFocused] = useState(false);
  const [mentionIndex, setMentionIndex] = useState(0);
  const [threadError, setThreadError] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [checklistResult, threadResult] = await Promise.allSettled([
      commandApi.checklist(item), commandApi.discussion(item)
    ]);
    if (checklistResult.status === 'fulfilled') setChecklist(checklistResult.value);
    else toast.error('چک‌لیست دریافت نشد');
    if (threadResult.status === 'fulfilled') {
      setThread(threadResult.value); setThreadError('');
    } else setThreadError(threadResult.reason instanceof Error ? threadResult.reason.message : 'گفت‌وگو دریافت نشد');
  }, [item]);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        void commandApi.discussion(item).then((updated) => { setThread(updated); setThreadError(''); }).catch(() => {});
      }
    }, 20000);
    return () => window.clearInterval(timer);
  }, [item]);

  const beforeCaret = message.slice(0, caret);
  const mention = focused ? beforeCaret.match(/(?:^|\s)@([A-Za-z0-9_.-]*)$/) : null;
  const suggestions = mention ? (thread?.participants || []).filter((person) =>
    person.username.toLowerCase().includes(mention[1].toLowerCase()) ||
    person.full_name.toLowerCase().includes(mention[1].toLowerCase())).slice(0, 6) : [];

  function insertMention(username: string) {
    if (!mention) return;
    const start = caret - mention[0].length + (mention[0].startsWith('@') ? 0 : 1);
    const next = `${message.slice(0, start)}@${username} ${message.slice(caret)}`;
    const nextCaret = start + username.length + 2;
    setMessage(next); setCaret(nextCaret); setMentionIndex(0);
    requestAnimationFrame(() => { input.current?.focus(); input.current?.setSelectionRange(nextCaret, nextCaret); });
  }

  async function addStep() {
    if (checklistTitle.trim().length < 2) return;
    setBusy(true);
    try {
      await commandApi.addChecklist(item, checklistTitle.trim());
      setChecklistTitle(''); await refresh(); onChanged(); toast.success('زیرکار به چک‌لیست افزوده شد');
    } catch (error) { toast.error(error instanceof Error ? error.message : 'افزودن زیرکار انجام نشد'); }
    finally { setBusy(false); }
  }
  async function toggleStep(step: WorkChecklistItem) {
    setBusy(true);
    try { await commandApi.toggleChecklist(item, step.id, !step.done); await refresh(); onChanged(); }
    catch (error) { toast.error(error instanceof Error ? error.message : 'تغییر چک‌لیست انجام نشد'); }
    finally { setBusy(false); }
  }
  async function removeStep(step: WorkChecklistItem) {
    setBusy(true);
    try { await commandApi.removeChecklist(item, step.id); await refresh(); onChanged(); }
    catch (error) { toast.error(error instanceof Error ? error.message : 'حذف زیرکار انجام نشد'); }
    finally { setBusy(false); }
  }
  async function post() {
    if (!canComment || !message.trim() || busy) return;
    setBusy(true);
    try {
      await commandApi.addComment(item, message.trim());
      setMessage(''); setCaret(0); await refresh(); onChanged();
    } catch (error) { toast.error(error instanceof Error ? error.message : 'ارسال پیام انجام نشد'); }
    finally { setBusy(false); }
  }

  function renderMessage(text: string) {
    const known = new Set((thread?.participants || []).map((person) => person.username.toLowerCase()));
    return text.split(/(@[A-Za-z0-9_.-]{3,40})/g).map((part, index) => {
      if (!part.startsWith('@')) return part;
      const handle = known.has(part.slice(1).toLowerCase()) ? part : part.replace(/[.-]+$/, '');
      return known.has(handle.slice(1).toLowerCase()) ?
        <span key={index}><strong className='text-primary font-semibold' dir='ltr'>{handle}</strong>{part.slice(handle.length)}</span> : part;
    });
  }

  return <section className='space-y-4 border-t pt-4 sm:col-span-2'>
    <div className='overflow-hidden rounded-xl border bg-muted/10'>
      <div className='flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3'>
        <div><h3 className='text-sm font-semibold'>گفت‌وگوی کار</h3>
          <p className='text-muted-foreground mt-1 text-xs'>پیام‌ها و یادداشت‌های این کار در همین گفتگو دیده می‌شوند.</p></div>
        {thread && thread.root_id !== item.id && <span className='rounded-md bg-muted px-2 py-1 text-xs'>کار اصلی: {thread.root_title}</span>}
      </div>
      <div className='max-h-80 min-h-32 space-y-3 overflow-y-auto p-4' aria-live='polite'>
        {threadError && <p role='alert' className='text-destructive text-sm'>{threadError}</p>}
        {!threadError && !thread && <p className='text-muted-foreground text-xs'>در حال دریافت گفتگو…</p>}
        {thread?.messages.map((entry) => <div key={entry.id} className='rounded-lg border bg-background p-3 text-sm'>
          <div className='text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-xs'>
            <strong className='text-foreground'>{entry.actor_name || entry.actor_username || 'سیستم'}</strong>
            <span>· {noteType[entry.event_type] || 'فعالیت'}</span>
            {entry.work_item_id !== thread.root_id && <span className='rounded bg-muted px-1.5 py-0.5'>زیرتسک: {entry.task_title}</span>}
            <time className='mr-auto'>{formatUserDateTime(entry.created_at, calendar)}</time>
          </div>
          <p className='mt-2 whitespace-pre-wrap break-words leading-6' dir='auto'>{renderMessage(entry.note)}</p>
        </div>)}
        {thread && !thread.messages.length && <p className='text-muted-foreground text-xs'>هنوز پیامی ثبت نشده است؛ اولین توضیح را همین‌جا بنویسید.</p>}
      </div>
      {!!thread?.activity.length && <details className='border-t px-4 py-2 text-xs'>
        <summary className='text-muted-foreground cursor-pointer'>تاریخچهٔ فعالیت ({thread.activity.length})</summary>
        <div className='mt-2 max-h-40 space-y-1 overflow-y-auto'>
          {thread.activity.map((event) => <p key={event.id} className='text-muted-foreground flex flex-wrap gap-x-2 rounded px-1 py-1'>
            <span>{event.actor_username || 'سیستم'} · {activityType[event.event_type] || 'تغییر'}</span>
            {event.work_item_id !== thread.root_id && <span>· {event.task_title}</span>}
            <time className='mr-auto'>{formatUserDateTime(event.created_at, calendar)}</time>
          </p>)}
        </div>
      </details>}
      <div className='space-y-2 border-t bg-background p-4'>
        {canComment ? <>
          <div className='relative'>
            <Textarea ref={input} aria-label='پیام گفت‌وگوی تسک' placeholder='توضیح خود را بنویسید؛ برای منشن کردن @ را وارد کنید…'
              rows={4} maxLength={2000} value={message}
              onFocus={() => setFocused(true)} onBlur={() => { setTimeout(() => setFocused(false), 150); }}
              onChange={(event) => { setMessage(event.target.value); setCaret(event.target.selectionStart); setMentionIndex(0); }}
              onClick={(event) => setCaret(event.currentTarget.selectionStart)}
              onKeyUp={(event) => { if (!['ArrowDown', 'ArrowUp'].includes(event.key)) setCaret(event.currentTarget.selectionStart); }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); void post(); }
                else if (suggestions.length && ['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key)) {
                  event.preventDefault();
                  if (event.key === 'Enter') insertMention(suggestions[mentionIndex]?.username || suggestions[0].username);
                  else setMentionIndex((current) => (current + (event.key === 'ArrowDown' ? 1 : suggestions.length - 1)) % suggestions.length);
                } else if (event.key === 'Escape') setFocused(false);
              }} />
            {!!suggestions.length && <div role='listbox' aria-label='افراد قابل منشن' className='absolute inset-x-0 bottom-full z-10 mb-1 max-h-44 overflow-y-auto rounded-lg border bg-popover p-1 shadow-lg'>
              {suggestions.map((person, index) => <button key={person.id} type='button' role='option'
                aria-selected={index === mentionIndex} onMouseDown={(event) => event.preventDefault()}
                onClick={() => insertMention(person.username)}
                className={`flex w-full items-center justify-between rounded px-3 py-2 text-right text-xs hover:bg-muted ${index === mentionIndex ? 'bg-muted' : ''}`}>
                <span>{person.full_name}</span><span dir='ltr' className='text-muted-foreground'>@{person.username}</span>
              </button>)}
            </div>}
          </div>
          <div className='flex items-center justify-between gap-2'><span className='text-muted-foreground text-xs'>Ctrl + Enter برای ارسال · منشن به همکار اعلان می‌دهد</span>
            <Button size='sm' disabled={busy || !message.trim() || !!threadError} onClick={() => void post()}>ارسال پیام</Button></div>
        </> : <p className='text-muted-foreground text-xs'>برای ارسال پیام باید عضو این پروژه باشید.</p>}
      </div>
    </div>
    <div className='space-y-2 rounded-xl border p-4'>
      <div className='flex items-center justify-between'><h3 className='text-sm font-semibold'>چک‌لیست زیرکارها</h3><span className='text-muted-foreground text-xs'>{checklist.filter((step) => step.done).length} از {checklist.length} انجام‌شده</span></div>
      {!!checklist.length && <div className='overflow-hidden rounded-lg border'>{checklist.map((step) => <div key={step.id}
        className='flex items-center justify-between gap-2 border-b px-3 py-2 text-sm last:border-b-0'>
        <label className='flex min-w-0 flex-1 items-center gap-2'><input type='checkbox' checked={step.done} disabled={!canEdit || busy} onChange={() => void toggleStep(step)} aria-label={step.title} />
          <span className={`min-w-0 break-words ${step.done ? 'text-muted-foreground line-through' : ''}`}>{step.title}</span></label>
        {canEdit && !step.legacy && <Button size='sm' variant='ghost' disabled={busy} onClick={() => void removeStep(step)}>برداشتن</Button>}
      </div>)}</div>}
      {!checklist.length && <p className='text-muted-foreground text-xs'>هنوز زیرکاری ثبت نشده است.</p>}
      {canEdit && <div className='flex gap-2'><Input aria-label='عنوان زیرکار' placeholder='افزودن زیرکار به چک‌لیست…' value={checklistTitle}
        maxLength={200} onChange={(event) => setChecklistTitle(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void addStep(); }} />
        <Button size='sm' disabled={busy || checklistTitle.trim().length < 2} onClick={() => void addStep()}>افزودن</Button></div>}
      {!canEdit && <p className='text-muted-foreground text-xs'>چک‌لیست برای شما فقط خواندنی است؛ برای هماهنگی از گفت‌وگو استفاده کنید.</p>}
    </div>
  </section>;
}
