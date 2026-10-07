'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { formatUserDate, formatUserDateTime, useDatePreference } from '@/lib/date-preference';
import { commandApi, type CommandOverview, type ManagementOverview, type ManagementPerson, type ProjectSummary, type WorkReport } from '../api';

const number = new Intl.NumberFormat('fa-IR');
const activeStatus = new Set(['new', 'triaged', 'approved', 'assigned', 'in_progress', 'review', 'published', 'measurement_pending', 'blocked']);
const statusLabel: Record<string, string> = { new: 'جدید', triaged: 'بررسی', approved: 'تأییدشده', assigned: 'واگذارشده',
  in_progress: 'در حال اجرا', review: 'بازبینی', published: 'منتشرشده', measurement_pending: 'در انتظار سنجش',
  blocked: 'مسدود', verified: 'نهایی', rejected: 'ردشده', deferred: 'تعویق' };
const activityLabel: Record<string, string> = { created: 'کار ساخت', updated: 'کار را ویرایش کرد', deleted: 'کار را حذف کرد',
  restored: 'کار را برگرداند', comment: 'یادداشت گذاشت', handoff: 'کار را ارجاع داد',
  checklist_updated: 'چک‌لیست را به‌روز کرد' };

function personProgress(person: ManagementPerson) {
  const considered = person.open_tasks + person.completed_tasks;
  return considered ? Math.round(person.completed_tasks / considered * 100) : 0;
}

export function ManagementDashboard() {
  const { calendar } = useDatePreference();
  const [data, setData] = useState<ManagementOverview | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [teamReport, setTeamReport] = useState<WorkReport | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tasks, setTasks] = useState<CommandOverview | null>(null);
  const [report, setReport] = useState<WorkReport | null>(null);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState('');
  const [teamId, setTeamId] = useState('');
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const selected = data?.people.find((person) => person.id === selectedId) || null;

  useEffect(() => {
    let active = true;
    setLoading(true);
    void Promise.all([commandApi.management(selectedId || undefined), commandApi.projects(),
      commandApi.report('week', new Date().toISOString().slice(0, 10))]).then(([result, projectRows, weekly]) => {
      if (active) { setData(result); setProjects(projectRows); setTeamReport(weekly); setError(''); }
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : 'داشبورد مدیریت بارگیری نشد');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectedId, revision]);

  useEffect(() => {
    if (selectedId === null) { setTasks(null); setReport(null); return; }
    let active = true;
    setDetailLoading(true);
    const anchor = new Date().toISOString().slice(0, 10);
    void Promise.all([commandApi.overview({ owner_id: selectedId, limit: 50, offset }),
      commandApi.report('week', anchor, undefined, selectedId)]).then(([work, weekly]) => {
      if (active) { setTasks(work); setReport(weekly); setError(''); }
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : 'جزئیات همکار بارگیری نشد');
    }).finally(() => { if (active) setDetailLoading(false); });
    return () => { active = false; };
  }, [selectedId, offset, revision]);

  const visiblePeople = useMemo(() => (data?.people || []).filter((person) =>
    (!teamId || person.team_id?.toString() === teamId) &&
    (!query || `${person.full_name} ${person.username} ${person.team_name || ''}`.toLowerCase().includes(query.trim().toLowerCase()))),
  [data, teamId, query]);
  const teams = useMemo(() => Array.from(new Map((data?.people || []).filter((person) => person.team_id && person.team_name)
    .map((person) => [person.team_id, person.team_name] as const)).entries()), [data]);
  const taskRows = tasks?.items || [];
  const week = report?.totals;
  const summary = data?.summary;

  return <div className='space-y-4' dir='rtl'>
    <section className='flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-sky-500/20 bg-gradient-to-l from-sky-500/10 via-background to-emerald-500/10 p-5'>
      <div><Badge variant='outline'>ویژهٔ مدیر کل</Badge><h2 className='mt-2 text-xl font-bold'>وضعیت اجرای کل تیم</h2>
        <p className='text-muted-foreground mt-1 text-sm'>مسئول هر کار، مسیر پروژه و آخرین فعالیت را از یک جا دنبال کنید.</p></div>
      <div className='flex flex-wrap gap-2'><Button variant='outline' onClick={() => setRevision((value) => value + 1)} disabled={loading || detailLoading}>به‌روزرسانی</Button>
        <Button variant='outline' render={<Link href='/dashboard/users' />}>کاربران و دسترسی‌ها</Button>
        <Button render={<Link href='/dashboard/work?view=teams' />}>مدیریت تیم‌ها و تسک‌ها</Button></div>
    </section>
    {error && <div role='alert' className='rounded-xl border border-rose-500/40 p-3 text-sm text-rose-600'>{error}</div>}
    {!data && loading && <div className='rounded-xl border p-12 text-center text-sm text-muted-foreground'>در حال آماده‌سازی تصویر تیم…</div>}
    {summary && <section className='grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6' aria-label='شاخص‌های تیم'>
      {([['همکار فعال', summary.active_people], ['کار باز', summary.open_tasks], ['عقب‌افتاده', summary.overdue_tasks],
        ['مسدود', summary.blocked_tasks], ['بی‌مسئول', summary.unassigned_tasks], ['کل کارها', summary.total_tasks]] as const)
        .map(([label, value]) => <Card key={label}><CardContent className='p-4'><span className='text-muted-foreground text-xs'>{label}</span>
          <strong className='mt-1 block text-2xl tabular-nums'>{number.format(value)}</strong></CardContent></Card>)}
    </section>}
    {data && <section className='grid gap-4 xl:grid-cols-2'>
      <Card><CardHeader><CardTitle>بار کاری تیم</CardTitle><CardDescription>تعداد کارهای باز و عقب‌افتادهٔ هر نفر؛ برای جزئیات از فهرست اعضا انتخاب کنید.</CardDescription></CardHeader>
        <CardContent className='h-64' dir='ltr'>{data.people.some((person) => person.open_tasks) ? <ResponsiveContainer width='100%' height='100%'>
          <BarChart data={[...data.people].filter((person) => person.active).sort((a, b) => b.open_tasks - a.open_tasks).slice(0, 10)} margin={{ left: 8, right: 8 }}>
            <CartesianGrid strokeDasharray='3 3' opacity={.2} /><XAxis dataKey='full_name' tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} /><Tooltip /><Legend />
            <Bar dataKey='open_tasks' name='باز' fill='#0ea5e9' radius={[4, 4, 0, 0]} /><Bar dataKey='overdue_tasks' name='عقب‌افتاده' fill='#f43f5e' radius={[4, 4, 0, 0]} />
          </BarChart></ResponsiveContainer> : <p className='text-muted-foreground py-20 text-center text-sm'>کار بازی ثبت نشده است.</p>}</CardContent></Card>
      <Card><CardHeader><CardTitle>روند اجرای این هفته</CardTitle><CardDescription>کارهای ایجادشده و نهایی‌شده از تاریخچهٔ واقعی تیم.</CardDescription></CardHeader>
        <CardContent className='h-64' dir='ltr'>{teamReport?.daily.length ? <ResponsiveContainer width='100%' height='100%'><BarChart data={teamReport.daily} margin={{ left: 8, right: 8 }}>
          <CartesianGrid strokeDasharray='3 3' opacity={.2} /><XAxis dataKey='day' tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} /><Tooltip /><Legend />
          <Bar dataKey='created' name='ایجاد' fill='#6366f1' radius={[4, 4, 0, 0]} /><Bar dataKey='completed' name='نهایی' fill='#10b981' radius={[4, 4, 0, 0]} />
        </BarChart></ResponsiveContainer> : <p className='text-muted-foreground py-20 text-center text-sm'>در این هفته فعالیتی ثبت نشده است.</p>}</CardContent></Card>
    </section>}
    {projects.length > 0 && <Card><CardHeader><CardTitle>مسیر پروژه‌ها</CardTitle><CardDescription>پیشرفت و ریسک پروژه‌ها بر اساس کارهای ثبت‌شده.</CardDescription></CardHeader>
      <CardContent className='grid gap-2 md:grid-cols-2 xl:grid-cols-3'>{[...projects].sort((a, b) => b.overdue_tasks - a.overdue_tasks || b.open_tasks - a.open_tasks).map((project) =>
        <Link key={project.site_id} href={`/dashboard/work?site=${encodeURIComponent(project.site_id)}&view=projects`} className='rounded-xl border p-3 transition-colors hover:bg-muted/50'>
          <span className='flex items-start justify-between gap-2'><strong className='truncate text-sm'>{project.name}</strong><Badge variant='outline'>{number.format(project.progress_percent)}٪</Badge></span>
          <span className='text-muted-foreground mt-1 block text-xs'>راهبر: {project.lead_name || 'تعیین نشده'} · {number.format(project.members)} عضو</span>
          <span className='mt-3 block h-1.5 overflow-hidden rounded-full bg-muted'><span className='block h-full rounded-full bg-emerald-500' style={{ width: `${project.progress_percent}%` }} /></span>
          <span className='mt-2 flex gap-3 text-xs'><span>{number.format(project.open_tasks)} باز</span><span className={project.overdue_tasks ? 'text-rose-600' : 'text-muted-foreground'}>{number.format(project.overdue_tasks)} عقب‌افتاده</span><span>{number.format(project.blocked_tasks)} مسدود</span></span>
        </Link>)}</CardContent></Card>}
    {data && <div className='grid gap-4 xl:grid-cols-[330px_minmax(0,1fr)]'>
      <Card className='min-w-0'><CardHeader><CardTitle>اعضای تیم</CardTitle><CardDescription>هر نفر را انتخاب کنید تا پروژه‌ها، کارها و فعالیتش دیده شود.</CardDescription></CardHeader>
        <CardContent className='space-y-3'><div className='flex gap-2'><Input aria-label='جست‌وجوی همکار' placeholder='نام یا نام کاربری…' value={query} onChange={(event) => setQuery(event.target.value)} />
          <NativeSelect aria-label='فیلتر تیم' value={teamId} onChange={(event) => setTeamId(event.target.value)} className='w-32'><NativeSelectOption value=''>همهٔ تیم‌ها</NativeSelectOption>
            {teams.map(([id, name]) => <NativeSelectOption key={id} value={String(id)}>{name}</NativeSelectOption>)}</NativeSelect></div>
          <div className='max-h-[760px] space-y-2 overflow-y-auto'>{visiblePeople.map((person) => <button key={person.id} type='button' aria-pressed={selectedId === person.id}
            onClick={() => { setSelectedId(person.id); setOffset(0); }} className={`w-full rounded-xl border p-3 text-right transition-colors hover:bg-muted/60 ${selectedId === person.id ? 'border-sky-500/60 bg-sky-500/10' : ''}`}>
            <span className='flex items-center justify-between gap-2'><strong className='truncate text-sm'>{person.full_name}</strong><Badge variant={person.active ? 'secondary' : 'outline'}>{person.active ? 'فعال' : 'غیرفعال'}</Badge></span>
            <span className='text-muted-foreground mt-1 block text-xs'>@{person.username} · {person.team_name || 'بدون تیم'}</span>
            <span className='mt-2 flex flex-wrap gap-2 text-xs'><span>{number.format(person.open_tasks)} کار باز</span>
              <span className={person.overdue_tasks ? 'text-rose-600' : 'text-muted-foreground'}>{number.format(person.overdue_tasks)} عقب‌افتاده</span>
              <span>{number.format(person.events_week)} فعالیت در ۷ روز</span></span>
            <span className='mt-2 block h-1.5 overflow-hidden rounded-full bg-muted'><span className='block h-full rounded-full bg-emerald-500' style={{ width: `${personProgress(person)}%` }} /></span>
          </button>)}{!visiblePeople.length && <p className='text-muted-foreground p-4 text-center text-sm'>همکاری با این فیلتر پیدا نشد.</p>}</div>
        </CardContent></Card>
      <div className='min-w-0 space-y-4'>
        {selected ? <>
          <Card><CardHeader className='flex flex-row flex-wrap items-start justify-between gap-3'><div><CardTitle>{selected.full_name}</CardTitle><CardDescription className='mt-1'>@{selected.username} · {selected.team_name || 'بدون تیم'} · آخرین فعالیت تسک: {selected.last_task_activity_at ? formatUserDateTime(selected.last_task_activity_at, calendar) : 'ثبت نشده'}</CardDescription></div>
            <Button size='sm' variant='outline' render={<Link href={`/dashboard/work?owner_id=${selected.id}`} />}>دیدن در میز عملیات</Button></CardHeader>
            <CardContent className='space-y-4'><div className='grid grid-cols-2 gap-2 md:grid-cols-4'>{[
              ['باز', selected.open_tasks], ['عقب‌افتاده', selected.overdue_tasks], ['مسدود', selected.blocked_tasks], ['موعد این هفته', selected.due_week_tasks]
            ].map(([label, value]) => <div key={label} className='rounded-lg border bg-muted/30 p-3'><span className='text-muted-foreground block text-xs'>{label}</span><strong className='text-xl'>{number.format(Number(value))}</strong></div>)}</div>
              <div><strong className='text-sm'>پروژه‌های سپرده‌شده</strong><div className='mt-2 flex flex-wrap gap-2'>{selected.projects.map((project) => <Link key={project.site_id} href={`/dashboard/work?site=${encodeURIComponent(project.site_id)}&view=projects`} className='rounded-lg border px-3 py-1.5 text-xs hover:bg-muted'>{project.name} · {project.responsibility === 'lead' ? 'راهبر' : project.responsibility === 'contributor' ? 'مجری' : 'ناظر'}</Link>)}
                {!selected.projects.length && <span className='text-muted-foreground text-xs'>پروژه‌ای به این نفر سپرده نشده است.</span>}</div></div>
              {week && <div className='rounded-xl border bg-muted/20 p-3'><strong className='text-sm'>کارکرد همین هفته</strong><p className='text-muted-foreground mt-1 text-xs'>بر اساس تاریخچهٔ واقعی تسک‌ها، از شنبه تا امروز</p>
                <div className='mt-3 grid grid-cols-2 gap-2 text-sm md:grid-cols-4'><span>{number.format(week.created)} ایجاد</span><span>{number.format(week.completed)} تکمیل</span><span>{number.format(week.handoffs)} ارجاع</span><span>{number.format(Math.round(week.minutes / 60 * 10) / 10)} ساعت ثبت‌شده</span></div></div>}
            </CardContent></Card>
          <Card><CardHeader className='flex flex-row flex-wrap items-center justify-between gap-2'><div><CardTitle>کارهای در مسئولیت {selected.full_name}</CardTitle><CardDescription>برای ویرایش کامل، کارت را باز کنید.</CardDescription></div><Badge variant='outline'>{number.format(tasks?.summary.total || 0)} کار</Badge></CardHeader>
            <CardContent>{detailLoading && <p className='text-muted-foreground py-4 text-sm'>در حال خواندن کارها…</p>}
              {!detailLoading && <div className='overflow-x-auto rounded-lg border'><table className='w-full min-w-[690px] text-right text-xs'><thead className='bg-muted/50'><tr><th className='p-3'>کار و پروژه</th><th>مرحله</th><th>پیشرفت</th><th>موعد</th><th>آخرین تغییر</th><th>اقدام</th></tr></thead><tbody>
                {taskRows.map((task) => <tr key={task.id} className='border-t'><td className='p-3'><strong className='block max-w-64 truncate'>{task.title}</strong><span className='text-muted-foreground'>{task.site_name}</span></td>
                  <td><Badge variant={task.status === 'blocked' ? 'destructive' : 'outline'}>{statusLabel[task.status] || task.status}</Badge></td>
                  <td>{number.format(task.progress_percent || (task.status === 'verified' ? 100 : 0))}٪{task.checklist_total > 0 && <span className='text-muted-foreground block'>{number.format(task.checklist_done)}/{number.format(task.checklist_total)} چک‌لیست</span>}</td>
                  <td className={task.due_at && activeStatus.has(task.status) && Date.parse(task.due_at) < Date.now() ? 'text-rose-600' : ''}>{task.due_at ? formatUserDate(task.due_at, calendar) : 'بی‌موعد'}</td>
                  <td>{formatUserDateTime(task.updated_at, calendar)}</td>
                  <td><Link className='text-primary hover:underline' href={`/dashboard/work?site=${encodeURIComponent(task.site_id)}&task=${task.id}`}>باز کردن و ویرایش</Link></td></tr>)}
              </tbody></table>{!taskRows.length && <p className='text-muted-foreground p-6 text-center text-sm'>کاری برای این همکار ثبت نشده است.</p>}</div>}
              <div className='mt-3 flex items-center justify-between text-xs'><span>نمایش {number.format(offset + (taskRows.length ? 1 : 0))} تا {number.format(offset + taskRows.length)}</span><div className='flex gap-2'><Button size='sm' variant='outline' disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>قبلی</Button><Button size='sm' variant='outline' disabled={taskRows.length < 50} onClick={() => setOffset(offset + 50)}>بعدی</Button></div></div>
            </CardContent></Card>
        </> : <Card><CardContent className='p-10 text-center text-muted-foreground'>از فهرست سمت راست یک همکار را انتخاب کنید تا کارها، پروژه‌ها و روند پیشرفت او را ببینید.</CardContent></Card>}
        <Card><CardHeader><CardTitle>آخرین فعالیت‌های {selected ? selected.full_name : 'تیم'}</CardTitle><CardDescription>رخدادهای واقعی ثبت‌شده روی تسک‌ها؛ انتخاب همکار این فهرست را فیلتر می‌کند.</CardDescription></CardHeader><CardContent className='space-y-2'>
          {data.recent.map((event) => <div key={event.id} className='flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-xs'><div><span className='font-medium'>{event.actor_username || 'سیستم'}</span> {activityLabel[event.event_type] || 'تغییری ثبت کرد'}: <Link className='text-primary hover:underline' href={`/dashboard/work?site=${encodeURIComponent(event.site_id)}&task=${event.work_item_id}`}>{event.task_title}</Link><span className='text-muted-foreground'> · {event.project_name}</span></div><time className='text-muted-foreground'>{formatUserDateTime(event.created_at, calendar)}</time></div>)}
          {!data.recent.length && <p className='text-muted-foreground text-sm'>فعالیتی ثبت نشده است.</p>}
        </CardContent></Card>
      </div>
    </div>}
  </div>;
}
