'use client';

import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { commandApi, type CommandWorkItem, type TaskDependency, type TaskTimeEntry, type WorkPerson } from '../api';

const number = new Intl.NumberFormat('fa-IR');

export function TaskExecutionDetails({ item, items, people, canEdit, canLogTime, canLogOthers, meId }: {
  item: CommandWorkItem; items: CommandWorkItem[]; people: WorkPerson[]; canEdit: boolean; canLogTime: boolean; canLogOthers: boolean; meId: number | null;
}) {
  const [dependencies, setDependencies] = useState<TaskDependency[]>([]);
  const [entries, setEntries] = useState<TaskTimeEntry[]>([]);
  const [dependencyId, setDependencyId] = useState('');
  const [userId, setUserId] = useState(meId?.toString() || item.owner_id?.toString() || '');
  const [minutes, setMinutes] = useState('');
  const [workDate, setWorkDate] = useState(new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try { const [deps, time] = await Promise.all([
      commandApi.dependencies(item.site_id, item.id), commandApi.timeEntries(item.site_id, item.id)
    ]); setDependencies(deps); setEntries(time); }
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

  return <div className='space-y-4 border-t pt-4 sm:col-span-2'>
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
  </div>;
}
