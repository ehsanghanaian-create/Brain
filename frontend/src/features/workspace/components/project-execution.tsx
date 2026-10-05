'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Progress } from '@/components/ui/progress';
import { commandApi, type CommandWorkItem, type ProjectMember, type ProjectMilestone,
  type ProjectSummary, type WorkPerson } from '../api';

const number = new Intl.NumberFormat('fa-IR');
const dateLabel = (value: string | null) => value ? new Date(value).toLocaleDateString('fa-IR', { month: 'short', day: 'numeric' }) : 'بی‌موعد';
const active = (item: CommandWorkItem) => !['verified', 'rejected', 'deferred'].includes(item.status);

export function ProjectExecution({ items, people, canEdit, preferredSiteId, onTask }: {
  items: CommandWorkItem[]; people: WorkPerson[]; canEdit: boolean; preferredSiteId?: string; onTask: (item: CommandWorkItem) => void;
}) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [siteId, setSiteId] = useState('');
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [milestones, setMilestones] = useState<ProjectMilestone[]>([]);
  const [memberId, setMemberId] = useState('');
  const [responsibility, setResponsibility] = useState<ProjectMember['responsibility']>('contributor');
  const [milestoneTitle, setMilestoneTitle] = useState('');
  const [milestoneDue, setMilestoneDue] = useState('');
  const [editingMilestone, setEditingMilestone] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshProjects = useCallback(async () => {
    try { const rows = await commandApi.projects(); setProjects(rows); setSiteId((current) => current || rows[0]?.site_id || ''); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'پروژه‌ها دریافت نشدند'); }
  }, []);
  const refreshDetail = useCallback(async () => {
    if (!siteId) return;
    try { const [membersResult, milestonesResult] = await Promise.all([commandApi.projectMembers(siteId), commandApi.milestones(siteId)]);
      setMembers(membersResult); setMilestones(milestonesResult); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'جزئیات پروژه دریافت نشد'); }
  }, [siteId]);
  useEffect(() => { void refreshProjects(); }, [refreshProjects, items]);
  useEffect(() => { if (preferredSiteId) setSiteId(preferredSiteId); }, [preferredSiteId]);
  useEffect(() => { void refreshDetail(); }, [refreshDetail]);

  const project = projects.find((row) => row.site_id === siteId);
  const canPlan = canEdit || project?.my_responsibility === 'lead';
  const siteTasks = useMemo(() => items.filter((row) => row.site_id === siteId), [items, siteId]);
  const parents = siteTasks.filter((row) => !row.parent_id);
  const scheduled = siteTasks.filter((row) => row.start_at || row.due_at).toSorted((a, b) =>
    (a.start_at || a.due_at || '').localeCompare(b.start_at || b.due_at || ''));
  const spanStart = scheduled.length ? Math.min(...scheduled.map((row) => Date.parse(row.start_at || row.due_at || ''))) : 0;
  const spanEnd = scheduled.length ? Math.max(...scheduled.map((row) => Date.parse(row.due_at || row.start_at || ''))) : 0;
  const span = Math.max(86400000, spanEnd - spanStart);

  async function assign() {
    if (!memberId || !siteId) return;
    setBusy(true);
    try { await commandApi.assignProjectMember(siteId, Number(memberId), responsibility);
      setMemberId(''); await Promise.all([refreshProjects(), refreshDetail()]); toast.success('مسئولیت سایت ثبت شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'تخصیص سایت انجام نشد'); }
    finally { setBusy(false); }
  }
  async function remove(userId: number) {
    setBusy(true);
    try { await commandApi.removeProjectMember(siteId, userId); await Promise.all([refreshProjects(), refreshDetail()]); toast.success('عضویت پروژه برداشته شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'حذف عضویت انجام نشد'); }
    finally { setBusy(false); }
  }
  async function changeResponsibility(userId: number, next: ProjectMember['responsibility']) {
    setBusy(true);
    try { await commandApi.assignProjectMember(siteId, userId, next); await refreshDetail(); toast.success('مسئولیت به‌روز شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'تغییر مسئولیت انجام نشد'); }
    finally { setBusy(false); }
  }
  async function createMilestone() {
    if (!milestoneTitle.trim() || !siteId) return;
    setBusy(true);
    try { const payload = { title: milestoneTitle.trim(), description: '',
      due_at: milestoneDue ? new Date(milestoneDue).toISOString() : null };
      if (editingMilestone === null) await commandApi.createMilestone(siteId, payload);
      else await commandApi.updateMilestone(siteId, editingMilestone, { title: payload.title, due_at: payload.due_at });
      setMilestoneTitle(''); setMilestoneDue(''); setEditingMilestone(null);
      await Promise.all([refreshProjects(), refreshDetail()]); toast.success('مایلستون ذخیره شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ثبت مایلستون انجام نشد'); }
    finally { setBusy(false); }
  }

  return <div className='space-y-4'>
    <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-3'>
      {projects.map((row) => <button key={row.site_id} onClick={() => setSiteId(row.site_id)}
        className={`rounded-xl border bg-card p-4 text-right transition-all hover:-translate-y-0.5 hover:shadow-md ${siteId === row.site_id ? 'border-emerald-500/70 ring-1 ring-emerald-500/20' : ''}`}>
        <span className='flex items-center justify-between gap-2'><strong>{row.name}</strong><Badge variant='outline'>{number.format(row.members)} عضو</Badge></span>
        <span className='text-muted-foreground mt-1 block truncate text-xs' dir='ltr'>{row.canonical_url}</span>
        <span className='mt-4 flex items-center justify-between text-xs'><span>پیشرفت کارها</span><strong>{number.format(row.progress_percent)}٪</strong></span>
        <Progress value={row.progress_percent} className='mt-1.5 h-2' />
        <span className='text-muted-foreground mt-3 flex justify-between text-xs'><span>{number.format(row.open_tasks)} باز · {number.format(row.overdue_tasks)} عقب‌افتاده</span><span>{number.format(row.spent_hours)} / {number.format(row.estimated_hours)} ساعت</span></span>
      </button>)}
      {!projects.length && <p className='text-muted-foreground rounded-xl border border-dashed p-8 text-sm'>برای ایجاد پروژه، ابتدا یک سایت به SEO Brain اضافه کنید.</p>}
    </div>
    {project && <>
      <div className='flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-muted/30 p-4'><div><h3 className='font-bold'>پروژهٔ {project.name}</h3>
        <p className='text-muted-foreground mt-1 text-xs'>هر سایت یک پروژه است؛ پیشرفت از کارهای نهایی و درصد تکمیل زیرکارها محاسبه می‌شود.</p></div>
        <Link href={`/dashboard/reports?site=${encodeURIComponent(siteId)}`} className='text-primary text-xs hover:underline'>مشاهدهٔ گزارش سئوی این سایت ←</Link></div>
      <div className='grid gap-4 xl:grid-cols-[1.4fr_1fr]'>
        <Card><CardHeader><CardTitle>ساختار کار و زیرکار</CardTitle><CardDescription>با باز کردن هر کار می‌توانید آن را ریزتر کنید، زمان‌بندی بدهید و وابستگی تعریف کنید.</CardDescription></CardHeader><CardContent className='space-y-2'>
          {parents.map((parent) => { const children = siteTasks.filter((row) => row.parent_id === parent.id);
            return <div key={parent.id} className='rounded-lg border p-3'><button className='flex w-full items-center justify-between gap-2 text-right' onClick={() => onTask(parent)}><strong className='text-sm'>{parent.title}</strong><span className='text-muted-foreground text-xs'>{number.format(parent.progress_percent || 0)}٪ · {parent.owner_name || 'بی‌مسئول'}</span></button>
              {!!children.length && <div className='mt-3 space-y-1.5 border-r-2 border-emerald-500/30 pr-3'>{children.map((child) => <button key={child.id} onClick={() => onTask(child)} className='flex w-full justify-between rounded-md bg-muted/40 p-2 text-right text-xs hover:bg-muted'><span>{child.title}</span><span className='text-muted-foreground'>{child.owner_name || 'بی‌مسئول'} · {dateLabel(child.due_at)}</span></button>)}</div>}
            </div>; })}
          {!parents.length && <p className='text-muted-foreground py-8 text-center text-sm'>برای این سایت هنوز کاری ثبت نشده است.</p>}
        </CardContent></Card>
        <div className='space-y-4'><Card><CardHeader><CardTitle>مسئولان سایت</CardTitle><CardDescription>نقش پروژه جدا از سطح دسترسی حساب پنل ثبت می‌شود.</CardDescription></CardHeader><CardContent className='space-y-2'>
          {members.map((person) => <div key={person.user_id} className='flex items-center justify-between gap-2 rounded-lg border p-2.5 text-xs'><span><strong className='block'>{person.full_name}</strong><span className='text-muted-foreground'>{number.format(siteTasks.filter((task) => task.owner_id === person.user_id && active(task)).length)} کار باز</span></span><div className='flex items-center gap-1'>{canEdit ? <NativeSelect disabled={busy} aria-label={`مسئولیت ${person.full_name}`} value={person.responsibility} onChange={(e) => void changeResponsibility(person.user_id, e.target.value as ProjectMember['responsibility'])} className='w-24'><NativeSelectOption value='lead'>راهبر</NativeSelectOption><NativeSelectOption value='contributor'>مجری</NativeSelectOption><NativeSelectOption value='viewer'>ناظر</NativeSelectOption></NativeSelect> : <span className='text-muted-foreground'>{person.responsibility === 'lead' ? 'راهبر' : person.responsibility === 'contributor' ? 'مجری' : 'ناظر'}</span>}{canEdit && <Button size='sm' variant='ghost' disabled={busy} onClick={() => void remove(person.user_id)}>برداشتن</Button>}</div></div>)}
          {!members.length && <p className='text-muted-foreground text-xs'>هنوز کسی به این سایت تخصیص ندارد.</p>}
          {canEdit && <div className='flex flex-wrap gap-2 border-t pt-3'><NativeSelect aria-label='انتخاب عضو پروژه' value={memberId} onChange={(e) => setMemberId(e.target.value)} className='min-w-36 flex-1'><NativeSelectOption value=''>انتخاب همکار</NativeSelectOption>{people.filter((person) => person.active && (person.role !== 'call_center' || responsibility === 'viewer') && !members.some((row) => row.user_id === person.id)).map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect><NativeSelect aria-label='مسئولیت پروژه' value={responsibility} onChange={(e) => { setResponsibility(e.target.value as ProjectMember['responsibility']); setMemberId(''); }} className='w-24'><NativeSelectOption value='lead'>راهبر</NativeSelectOption><NativeSelectOption value='contributor'>مجری</NativeSelectOption><NativeSelectOption value='viewer'>ناظر</NativeSelectOption></NativeSelect><Button size='sm' disabled={!memberId || busy} onClick={assign}>افزودن</Button></div>}
        </CardContent></Card>
        <Card><CardHeader><CardTitle>مایلستون‌ها</CardTitle><CardDescription>نقاط تحویل پروژه و تعداد کارهای تأییدشدهٔ هر کدام.</CardDescription></CardHeader><CardContent className='space-y-2'>
          {milestones.map((entry) => <div key={entry.id} className='rounded-lg border p-2.5 text-xs'><div className='flex justify-between'><strong>{entry.title}</strong><span className='text-muted-foreground'>{dateLabel(entry.due_at)}</span></div><div className='mt-1 flex items-center justify-between gap-2'><span className='text-muted-foreground'>{number.format(entry.verified_tasks)} از {number.format(entry.tasks)} کار تأیید شده</span>{canPlan && <Button size='sm' variant='ghost' onClick={() => { setEditingMilestone(entry.id); setMilestoneTitle(entry.title); setMilestoneDue(entry.due_at ? new Date(new Date(entry.due_at).getTime() - new Date(entry.due_at).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : ''); }}>ویرایش</Button>}</div></div>)}
          {!milestones.length && <p className='text-muted-foreground text-xs'>مایلستونی ثبت نشده است.</p>}
          {canPlan && <div className='grid gap-2 border-t pt-3'><Input aria-label='عنوان مایلستون' placeholder='مثلاً پایان فاز سئوی فنی' value={milestoneTitle} onChange={(e) => setMilestoneTitle(e.target.value)} /><Input aria-label='موعد مایلستون' type='datetime-local' value={milestoneDue} onChange={(e) => setMilestoneDue(e.target.value)} /><div className='flex gap-2'><Button size='sm' disabled={milestoneTitle.trim().length < 2 || busy} onClick={createMilestone}>{editingMilestone === null ? 'ثبت مایلستون' : 'ذخیرهٔ ویرایش'}</Button>{editingMilestone !== null && <Button size='sm' variant='outline' onClick={() => { setEditingMilestone(null); setMilestoneTitle(''); setMilestoneDue(''); }}>انصراف</Button>}</div></div>}
        </CardContent></Card></div>
      </div>
      <Card><CardHeader><CardTitle>خط زمانی پروژه</CardTitle><CardDescription>بازهٔ شروع تا تحویل کارهای زمان‌بندی‌شده؛ رنگ قرمز نشان‌دهندهٔ مانع است.</CardDescription></CardHeader><CardContent className='space-y-2'>
        {scheduled.map((item) => { const start = Date.parse(item.start_at || item.due_at || ''); const end = Date.parse(item.due_at || item.start_at || '');
          const left = Math.max(0, (start - spanStart) / span * 100); const width = Math.max(2, (end - start) / span * 100);
          return <button key={item.id} onClick={() => onTask(item)} className='grid w-full grid-cols-[minmax(150px,1fr)_2fr_85px] items-center gap-3 rounded-md p-2 text-right hover:bg-muted/50'><span className='truncate text-xs'>{item.title}</span><span className='relative h-5 rounded-full bg-muted'><span className={`absolute top-1 h-3 rounded-full ${item.status === 'blocked' ? 'bg-rose-500' : active(item) ? 'bg-emerald-500' : 'bg-sky-500'}`} style={{ right: `${left}%`, width: `${width}%` }} /></span><span className='text-muted-foreground text-[11px]'>{dateLabel(item.due_at)}</span></button>; })}
        {!scheduled.length && <p className='text-muted-foreground py-8 text-center text-sm'>برای دیدن خط زمانی، تاریخ شروع یا موعد کارها را ثبت کنید.</p>}
      </CardContent></Card>
    </>}
  </div>;
}
