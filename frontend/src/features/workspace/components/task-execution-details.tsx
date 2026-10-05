'use client';

import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { commandApi, type CommandWorkItem, type TaskDependency, type TaskTimeEntry, type WorkChecklistItem, type WorkCustomValue, type WorkLabel, type WorkPerson } from '../api';

const number = new Intl.NumberFormat('fa-IR');

export function TaskExecutionDetails({ item, items, people, canEdit, canLogTime, canLogOthers, meId, onChanged }: {
  item: CommandWorkItem; items: CommandWorkItem[]; people: WorkPerson[]; canEdit: boolean; canLogTime: boolean; canLogOthers: boolean; meId: number | null; onChanged: () => void;
}) {
  const [dependencies, setDependencies] = useState<TaskDependency[]>([]);
  const [entries, setEntries] = useState<TaskTimeEntry[]>([]);
  const [checklist, setChecklist] = useState<WorkChecklistItem[]>([]);
  const [projectLabels, setProjectLabels] = useState<WorkLabel[]>([]);
  const [itemLabels, setItemLabels] = useState<WorkLabel[]>([]);
  const [fields, setFields] = useState<WorkCustomValue[]>([]);
  const [fieldDrafts, setFieldDrafts] = useState<Record<number, string>>({});
  const [comments, setComments] = useState<Awaited<ReturnType<typeof commandApi.events>>>([]);
  const [commentText, setCommentText] = useState('');
  const [checklistTitle, setChecklistTitle] = useState('');
  const [dependencyId, setDependencyId] = useState('');
  const [userId, setUserId] = useState(meId?.toString() || item.owner_id?.toString() || '');
  const [minutes, setMinutes] = useState('');
  const [workDate, setWorkDate] = useState(new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try { const [deps, time, checks, labels, selectedLabels, history, fieldRows] = await Promise.all([
      commandApi.dependencies(item.site_id, item.id), commandApi.timeEntries(item.site_id, item.id), commandApi.checklist(item),
      commandApi.labels(item.site_id), commandApi.itemLabels(item), commandApi.events(item), commandApi.itemFields(item)
    ]); setDependencies(deps); setEntries(time); setChecklist(checks); setProjectLabels(labels); setItemLabels(selectedLabels);
      setFields(fieldRows); setFieldDrafts(Object.fromEntries(fieldRows.map((field) => [field.id, String(field.value ?? '')])));
      setComments(history.filter((event) => event.event_type === 'comment' && event.note)); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'جزئیات اجرا دریافت نشد'); }
  }, [item.id, item.site_id]);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { setUserId(meId?.toString() || item.owner_id?.toString() || ''); }, [item.id, item.owner_id, meId]);
  const spent = entries.reduce((sum, entry) => sum + entry.minutes, 0);

  async function addDependency() {
    if (!dependencyId) return;
    setBusy(true);
    try { await commandApi.addDependency(item.site_id, item.id, Number(dependencyId)); setDependencyId(''); await refresh(); toast.success('پیش‌نیاز ثبت شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ثبت پیش‌نیاز انجام نشد'); }
    finally { setBusy(false); }
  }
  async function removeDependency(id: number) {
    setBusy(true);
    try { await commandApi.removeDependency(item.site_id, item.id, id); await refresh(); toast.success('پیش‌نیاز برداشته شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'حذف پیش‌نیاز انجام نشد'); }
    finally { setBusy(false); }
  }
  async function logTime() {
    if (!userId || !minutes || !workDate) return;
    setBusy(true);
    try { await commandApi.logTime(item.site_id, item.id, { user_id: Number(userId), minutes: Number(minutes), work_date: workDate, note: note.trim() });
      setMinutes(''); setNote(''); await refresh(); toast.success('زمان انجام کار ثبت شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ثبت زمان انجام نشد'); }
    finally { setBusy(false); }
  }
  async function addChecklist() {
    if (checklistTitle.trim().length < 2) return;
    setBusy(true);
    try { await commandApi.addChecklist(item, checklistTitle.trim()); setChecklistTitle(''); await refresh(); onChanged(); toast.success('مورد چک‌لیست افزوده شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ثبت چک‌لیست انجام نشد'); }
    finally { setBusy(false); }
  }
  async function toggleChecklist(entry: WorkChecklistItem) {
    setBusy(true);
    try { await commandApi.toggleChecklist(item, entry.id, !entry.done); await refresh(); onChanged(); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'تغییر چک‌لیست انجام نشد'); }
    finally { setBusy(false); }
  }
  async function removeChecklist(entry: WorkChecklistItem) {
    setBusy(true);
    try { await commandApi.removeChecklist(item, entry.id); await refresh(); onChanged(); toast.success('مورد برداشته شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'حذف مورد انجام نشد'); }
    finally { setBusy(false); }
  }
  async function toggleLabel(label: WorkLabel) {
    setBusy(true);
    try { if (itemLabels.some((selected) => selected.id === label.id)) await commandApi.removeItemLabel(item, label.id);
      else await commandApi.addItemLabel(item, label.id);
      await refresh(); onChanged(); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'تغییر برچسب انجام نشد'); }
    finally { setBusy(false); }
  }
  async function postComment() {
    if (!commentText.trim()) return;
    setBusy(true);
    try { await commandApi.updateWork(item, { note: commentText.trim() }); setCommentText(''); await refresh(); onChanged();
      toast.success('گفت‌وگو ثبت شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ثبت گفت‌وگو انجام نشد'); }
    finally { setBusy(false); }
  }
  async function saveField(field: WorkCustomValue) {
    const draft = (fieldDrafts[field.id] || '').trim();
    if (field.field_type === 'number' && draft && !Number.isFinite(Number(draft))) {
      toast.error('این فیلد باید عدد باشد'); return;
    }
    const value = draft ? field.field_type === 'number' ? Number(draft) : draft : null;
    setBusy(true);
    try { await commandApi.setItemField(item, field.id, value); await refresh(); onChanged(); toast.success('فیلد کار ذخیره شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ذخیرهٔ فیلد انجام نشد'); }
    finally { setBusy(false); }
  }

  return <div className='space-y-4 border-t pt-4 sm:col-span-2'>
    <div className='space-y-2'><strong className='text-sm'>برچسب‌های کار</strong>
      <div className='flex flex-wrap gap-2'>{projectLabels.map((label) => <button key={label.id} type='button' disabled={!canLogTime || busy} onClick={() => void toggleLabel(label)}
        aria-pressed={itemLabels.some((selected) => selected.id === label.id)}
        className={`rounded-lg border px-2 py-1 text-xs transition-opacity ${itemLabels.some((selected) => selected.id === label.id) ? 'text-white' : 'opacity-60 hover:opacity-100'}`}
        style={itemLabels.some((selected) => selected.id === label.id) ? { backgroundColor: label.color, borderColor: label.color } : { borderColor: label.color }}>
        {label.name}</button>)}{!projectLabels.length && <span className='text-muted-foreground text-xs'>برچسب‌ها را از نوار برد پروژه بسازید.</span>}</div>
    </div>
    <div className='space-y-2 border-t pt-4'><strong className='text-sm'>فیلدهای پروژه</strong>
      {fields.map((field) => <div key={field.id} className='grid items-center gap-2 rounded-lg border p-2 text-xs sm:grid-cols-[140px_1fr_auto]'><label htmlFor={`custom-field-${field.id}`} className='font-medium'>{field.name}</label>
        {field.field_type === 'select' ? <NativeSelect id={`custom-field-${field.id}`} disabled={!canLogTime || busy} value={fieldDrafts[field.id] || ''} onChange={(event) => setFieldDrafts((current) => ({ ...current, [field.id]: event.target.value }))}><NativeSelectOption value=''>انتخاب نشده</NativeSelectOption>{field.options.map((option) => <NativeSelectOption key={option} value={option}>{option}</NativeSelectOption>)}</NativeSelect> :
          <Input id={`custom-field-${field.id}`} disabled={!canLogTime || busy} type={field.field_type === 'number' ? 'number' : field.field_type === 'date' ? 'date' : 'text'} value={fieldDrafts[field.id] || ''} onChange={(event) => setFieldDrafts((current) => ({ ...current, [field.id]: event.target.value }))} />}
        {canLogTime && <Button size='sm' variant='outline' disabled={busy || (fieldDrafts[field.id] || '') === String(field.value ?? '')} onClick={() => void saveField(field)}>ذخیره</Button>}
      </div>)}
      {!fields.length && <p className='text-muted-foreground text-xs'>فیلد اختصاصی برای این پروژه تعریف نشده است.</p>}
    </div>
    <div className='space-y-2'><div className='flex items-center justify-between'><strong className='text-sm'>چک‌لیست انجام کار</strong><span className='text-muted-foreground text-xs'>{number.format(checklist.filter((entry) => entry.done).length)} از {number.format(checklist.length)} انجام‌شده</span></div>
      {checklist.length > 0 && <div className='h-1.5 overflow-hidden rounded-full bg-muted'><div className='h-full bg-emerald-500 transition-all' style={{ width: `${checklist.filter((entry) => entry.done).length / checklist.length * 100}%` }} /></div>}
      {checklist.map((entry) => <div key={entry.id} className='flex items-center gap-2 rounded-lg border p-2 text-xs'><label className='flex min-w-0 flex-1 items-center gap-2'><input type='checkbox' checked={entry.done} disabled={!canLogTime || busy} onChange={() => void toggleChecklist(entry)} /><span className={entry.done ? 'text-muted-foreground line-through' : ''}>{entry.title}</span></label>{canEdit && <Button size='sm' variant='ghost' disabled={busy} onClick={() => void removeChecklist(entry)}>برداشتن</Button>}</div>)}
      {!checklist.length && <p className='text-muted-foreground text-xs'>هنوز گامی برای این کار ثبت نشده است.</p>}
      {canLogTime && <div className='flex gap-2'><Input aria-label='گام جدید چک‌لیست' placeholder='گام بعدی انجام کار' value={checklistTitle} onChange={(event) => setChecklistTitle(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void addChecklist(); }} /><Button size='sm' disabled={busy || checklistTitle.trim().length < 2} onClick={addChecklist}>افزودن</Button></div>}
    </div>
    <div className='space-y-2'><strong className='text-sm'>پیش‌نیازهای این کار</strong>
      <p className='text-muted-foreground text-xs'>تا وقتی پیش‌نیازها تأیید نشده‌اند، این کار نمی‌تواند «تأیید نتیجه» شود.</p>
      {dependencies.map((dep) => <div key={dep.depends_on_id} className='flex items-center justify-between gap-2 rounded-lg border p-2 text-xs'><span>{dep.title} · {dep.status === 'verified' ? 'تأییدشده' : 'در جریان'}</span>{canEdit && <Button size='sm' variant='ghost' disabled={busy} onClick={() => void removeDependency(dep.depends_on_id)}>برداشتن</Button>}</div>)}
      {!dependencies.length && <p className='text-muted-foreground text-xs'>پیش‌نیازی ثبت نشده است.</p>}
      {canEdit && <div className='flex gap-2'><NativeSelect aria-label='انتخاب پیش‌نیاز' value={dependencyId} onChange={(e) => setDependencyId(e.target.value)} className='flex-1'><NativeSelectOption value=''>انتخاب کار پیش‌نیاز</NativeSelectOption>{items.filter((other) => other.site_id === item.site_id && other.id !== item.id && !dependencies.some((dep) => dep.depends_on_id === other.id)).map((other) => <NativeSelectOption key={other.id} value={String(other.id)}>{other.title}</NativeSelectOption>)}</NativeSelect><Button size='sm' disabled={!dependencyId || busy} onClick={addDependency}>افزودن</Button></div>}
    </div>
    <div className='space-y-2 border-t pt-4'><div className='flex items-center justify-between'><strong className='text-sm'>زمان صرف‌شده</strong><span className='text-muted-foreground text-xs'>{number.format(spent / 60)} از {number.format(item.estimated_hours || 0)} ساعت برآوردی</span></div>
      {entries.map((entry) => <div key={entry.id} className='flex justify-between gap-2 rounded-lg border p-2 text-xs'><span>{entry.user_name} · {entry.note || 'کار ثبت‌شده'}</span><span className='text-muted-foreground'>{new Date(entry.work_date).toLocaleDateString('fa-IR')} · {number.format(entry.minutes)} دقیقه</span></div>)}
      {!entries.length && <p className='text-muted-foreground text-xs'>هنوز زمانی ثبت نشده است.</p>}
      {canLogTime && <div className='grid gap-2 sm:grid-cols-2'><NativeSelect disabled={!canLogOthers} aria-label='انجام‌دهندهٔ زمان' value={userId} onChange={(e) => setUserId(e.target.value)}><NativeSelectOption value=''>انتخاب فرد</NativeSelectOption>{people.filter((person) => person.active && (canLogOthers || person.id === meId)).map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect><Input aria-label='زمان به دقیقه' type='number' min={1} max={1440} placeholder='دقیقه' value={minutes} onChange={(e) => setMinutes(e.target.value)} /><Input aria-label='تاریخ کار' type='date' value={workDate} onChange={(e) => setWorkDate(e.target.value)} /><Input aria-label='شرح زمان' placeholder='چه کاری انجام شد؟' value={note} onChange={(e) => setNote(e.target.value)} /><Button size='sm' disabled={busy || !userId || !minutes || !workDate} onClick={logTime}>ثبت زمان</Button></div>}
    </div>
    <div className='space-y-2 border-t pt-4'><strong className='text-sm'>گفت‌وگوی کار</strong>
      {comments.map((comment) => <div key={comment.id} className='rounded-lg border bg-muted/30 p-3 text-xs'><div className='mb-1 flex justify-between gap-2 text-muted-foreground'><span>{comment.actor_username || 'سیستم'}</span><time>{new Date(comment.created_at).toLocaleString('fa-IR')}</time></div><p className='whitespace-pre-wrap leading-5'>{comment.note}</p></div>)}
      {!comments.length && <p className='text-muted-foreground text-xs'>هنوز گفت‌وگویی برای این کار ثبت نشده است.</p>}
      {canLogTime && <div className='flex gap-2'><Input aria-label='پیام گفت‌وگوی کار' placeholder='پرسش، نتیجه یا هماهنگی تیم را بنویسید' value={commentText} maxLength={1000} onChange={(event) => setCommentText(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void postComment(); }} /><Button size='sm' disabled={busy || !commentText.trim()} onClick={() => void postComment()}>ارسال</Button></div>}
    </div>
  </div>;
}
