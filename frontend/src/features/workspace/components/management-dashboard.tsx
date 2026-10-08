'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Textarea } from '@/components/ui/textarea';
import { formatUserDate, formatUserDateTime, useDatePreference } from '@/lib/date-preference';
import { commandApi, type ManagementOverview, type ManagementTask, type ManagementTaskFilters,
  type ManagementTaskLedger, type ProjectSummary, type WorkReport } from '../api';

const number = new Intl.NumberFormat('fa-IR');
type Section = 'today' | 'reviews' | 'team' | 'projects' | 'gantt' | 'tasks' | 'reports';
const sections: { id: Section; label: string }[] = [
  { id: 'today', label: 'نمای امروز' }, { id: 'reviews', label: 'منتظر تأیید' },
  { id: 'team', label: 'کار هر نفر' }, { id: 'projects', label: 'پروژه‌ها' },
  { id: 'gantt', label: 'گانت' }, { id: 'tasks', label: 'همهٔ تسک‌ها' },
  { id: 'reports', label: 'گزارش عملکرد' }
];
const statusText: Record<string, string> = {
  new: 'ورودی', triaged: 'بررسی اولیه', approved: 'آماده', assigned: 'واگذارشده',
  in_progress: 'در حال اجرا', review: 'منتظر تأیید', published: 'منتشرشده',
  measurement_pending: 'در انتظار سنجش', verified: 'تأییدشده', blocked: 'مانع‌دار',
  rejected: 'ردشده', deferred: 'تعویق'
};
const priorityText: Record<string, string> = { critical: 'فوری', high: 'بالا', normal: 'معمولی', low: 'کم' };
const focusOptions: { value: NonNullable<ManagementTaskFilters['focus']>; label: string }[] = [
  { value: 'open', label: 'کارهای باز' }, { value: 'review', label: 'منتظر تأیید' },
  { value: 'overdue', label: 'عقب‌افتاده' }, { value: 'blocked', label: 'مانع‌دار' },
  { value: 'unscheduled', label: 'بی‌موعد' }, { value: 'unassigned', label: 'بی‌مسئول' },
  { value: 'completed', label: 'تأییدشده' }, { value: 'all', label: 'همه' }
];
const taskUrl = (item: Pick<ManagementTask, 'site_id' | 'id'>) =>
  `/dashboard/work?site=${encodeURIComponent(item.site_id)}&task=${item.id}`;
const dateNumber = (value: string) => Date.parse(value.slice(0, 10) + 'T00:00:00Z') / 86_400_000;

async function loadOpenWork() {
  const first = await commandApi.managementTasks({ focus: 'open', limit: 100 });
  const items = [...first.items];
  while (items.length < first.total && items.length < 500) {
    const next = await commandApi.managementTasks({ focus: 'open', limit: 100, offset: items.length });
    if (!next.items.length) break;
    items.push(...next.items);
  }
  return { items, total: first.total, undatedTotal: first.schedule.unscheduled };
}

function ManagerGantt({ items, total, calendar }: {
  items: ManagementTask[]; total: number;
  calendar: ReturnType<typeof useDatePreference>['calendar'];
}) {
  const [horizon, setHorizon] = useState(30);
  const today = new Date().toISOString().slice(0, 10);
  const origin = dateNumber(today) - 7;
  const span = horizon + 7;
  const scheduled = items.filter((task) => task.start_at || task.due_at);
  const undated = items.filter((task) => !task.due_at);
  const rows = scheduled.filter((task) => {
    const start = dateNumber(task.start_at || task.due_at!);
    const end = dateNumber(task.due_at || task.start_at!);
    return start <= origin + span && end >= origin;
  }).toSorted((a, b) => dateNumber(a.due_at || a.start_at!) - dateNumber(b.due_at || b.start_at!));
  const ticks = [0, .25, .5, .75, 1].map((fraction) =>
    formatUserDate(new Date((origin + Math.round(span * fraction)) * 86_400_000), calendar));
  const position = (value: number) => Math.max(0, Math.min(100, (value - origin) / span * 100));

  return <div className='space-y-4'>
    <Card><CardHeader className='flex flex-row flex-wrap items-start justify-between gap-3'>
      <div><CardTitle>گانت کارهای تیم</CardTitle><CardDescription className='mt-1'>نوار از شروع ثبت‌شده تا موعد ثبت‌شده است. تاریخ‌هایی که هنوز وارد نشده‌اند حدس زده نمی‌شوند.</CardDescription></div>
      <div className='flex gap-2'><Button size='sm' variant={horizon === 30 ? 'default' : 'outline'} onClick={() => setHorizon(30)}>۳۰ روز</Button>
        <Button size='sm' variant={horizon === 90 ? 'default' : 'outline'} onClick={() => setHorizon(90)}>۹۰ روز</Button></div>
    </CardHeader><CardContent className='space-y-3'>
      <div className='flex flex-wrap gap-2 text-xs'><Badge variant='outline'>{number.format(scheduled.length)} کار دارای تاریخ</Badge>
        <Badge variant='outline'>{number.format(undated.length)} کار بی‌موعد</Badge>
        {total > items.length && <Badge variant='secondary'>نمایش {number.format(items.length)} کار از {number.format(total)} کار باز</Badge>}</div>
      {rows.length ? <div className='max-h-[600px] overflow-auto rounded-xl border'><div className='min-w-[830px]'>
        <div className='grid grid-cols-[260px_minmax(560px,1fr)] border-b bg-muted/50 text-xs'><span className='p-3'>تسک · مسئول · پروژه</span>
          <div className='flex items-center justify-between px-3' dir='ltr'>{ticks.map((tick, index) => <span key={index}>{tick}</span>)}</div></div>
        {rows.map((task) => {
          const start = dateNumber(task.start_at || task.due_at!);
          const end = dateNumber(task.due_at || task.start_at!);
          const left = position(start);
          const right = position(end);
          const width = Math.max(1.5, right - left);
          const color = task.status === 'review' ? 'bg-amber-500' : task.status === 'blocked' ? 'bg-rose-500' : 'bg-sky-500';
          return <div key={task.id} className='grid grid-cols-[260px_minmax(560px,1fr)] border-b last:border-0 hover:bg-muted/30'>
            <Link href={taskUrl(task)} className='min-w-0 p-2.5 text-xs hover:text-primary'><strong className='block truncate'>{task.title}</strong>
              <span className='text-muted-foreground block truncate'>{task.owner_name || 'بی‌مسئول'} · {task.site_name}</span></Link>
            <div className='relative mx-3 my-3 h-7 rounded-md bg-muted/40' dir='ltr' style={{ backgroundImage: 'linear-gradient(to right, transparent 49.8%, var(--border) 50%, transparent 50.2%)' }}>
              <span className='absolute inset-y-0 border-r-2 border-dashed border-foreground/30' style={{ left: `${position(dateNumber(today))}%` }} title='امروز' />
              <span className={`absolute top-2 h-3 rounded-full ${color}`} style={{ left: `${left}%`, width: `${width}%` }}
                title={`${task.start_at ? formatUserDate(task.start_at, calendar) : 'شروع ثبت نشده'} ← ${task.due_at ? formatUserDate(task.due_at, calendar) : 'موعد ثبت نشده'}`} />
            </div></div>;
        })}</div></div> : <p className='rounded-xl border border-dashed p-5 text-sm text-muted-foreground'>در بازهٔ انتخابی، کاری با تاریخ ثبت‌شده وجود ندارد. کارهای بدون تاریخ در بخش زیر قابل پیگیری‌اند.</p>}
    </CardContent></Card>
    <Card><CardHeader><CardTitle>کارهای منتظر تعیین موعد</CardTitle>
      <CardDescription>این کارها انجام می‌شوند اما هنوز موعد ندارند؛ با بازکردن کارت می‌توانید تاریخ واقعی ثبت کنید.</CardDescription></CardHeader>
      <CardContent className='grid gap-2 md:grid-cols-2 xl:grid-cols-3'>{undated.map((task) => <Link key={task.id} href={taskUrl(task)}
        className='rounded-lg border p-3 text-xs transition-colors hover:border-primary/50 hover:bg-muted/30'><strong className='block truncate text-sm'>{task.title}</strong>
        <span className='text-muted-foreground mt-1 block truncate'>{task.owner_name || 'بی‌مسئول'} · {task.site_name}</span>
        <Badge variant='outline' className='mt-2'>{statusText[task.status]}</Badge></Link>)}
        {!undated.length && <p className='text-sm text-muted-foreground'>همهٔ کارهای باز حداقل یک تاریخ دارند.</p>}
      </CardContent></Card>
  </div>;
}

export function ManagementDashboard() {
  const { calendar } = useDatePreference();
  const [section, setSection] = useState<Section>('today');
  const [overview, setOverview] = useState<ManagementOverview | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [openWork, setOpenWork] = useState<{ items: ManagementTask[]; total: number; undatedTotal: number } | null>(null);
  const [reviews, setReviews] = useState<ManagementTaskLedger | null>(null);
  const [ledger, setLedger] = useState<ManagementTaskLedger | null>(null);
  const [report, setReport] = useState<WorkReport | null>(null);
  const [period, setPeriod] = useState<'week' | 'month'>('week');
  const [siteId, setSiteId] = useState('');
  const [ownerId, setOwnerId] = useState('');
  const [teamId, setTeamId] = useState('');
  const [focus, setFocus] = useState<NonNullable<ManagementTaskFilters['focus']>>('open');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [personId, setPersonId] = useState<number | null>(null);
  const [decision, setDecision] = useState<{ task: ManagementTask; value: 'approve' | 'changes_requested' } | null>(null);
  const [decisionNote, setDecisionNote] = useState('');
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { const timer = window.setTimeout(() => { setQuery(search.trim()); setOffset(0); }, 300);
    return () => window.clearTimeout(timer); }, [search]);
  useEffect(() => {
    let active = true; setLoading(true);
    void Promise.all([commandApi.management(), commandApi.projects(), loadOpenWork(),
      commandApi.managementTasks({ focus: 'review', limit: 100 })])
      .then(([team, projectRows, openRows, reviewRows]) => {
        if (active) { setOverview(team); setProjects(projectRows); setOpenWork(openRows); setReviews(reviewRows); setError(''); }
      }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'داده‌های مدیریت بارگیری نشد'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);
  useEffect(() => {
    if (section !== 'tasks') return;
    let active = true; setLedgerLoading(true);
    void commandApi.managementTasks({ site_id: siteId || undefined, owner_id: ownerId ? Number(ownerId) : undefined,
      team_id: teamId ? Number(teamId) : undefined, focus, q: query || undefined, offset, limit: 50 })
      .then((result) => { if (active) { setLedger(result); setError(''); } })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'فهرست کارها بارگیری نشد'); })
      .finally(() => { if (active) setLedgerLoading(false); });
    return () => { active = false; };
  }, [section, siteId, ownerId, teamId, focus, query, offset, revision]);
  useEffect(() => {
    if (section !== 'reports') return;
    let active = true;
    void commandApi.report(period, new Date().toISOString().slice(0, 10))
      .then((result) => { if (active) setReport(result); })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'گزارش بارگیری نشد'); });
    return () => { active = false; };
  }, [section, period, revision]);

  const people = useMemo(() => [...(overview?.people || [])].filter((person) => person.active)
    .toSorted((a, b) => b.review_tasks - a.review_tasks || b.open_tasks - a.open_tasks || a.full_name.localeCompare(b.full_name)), [overview]);
  const projectRows = useMemo(() => [...projects].toSorted((a, b) => b.overdue_tasks - a.overdue_tasks || b.open_tasks - a.open_tasks), [projects]);
  const teams = useMemo(() => [...new Map(people.filter((person) => person.team_id && person.team_name)
    .map((person) => [person.team_id!, person.team_name!] as const)).entries()], [people]);
  const personTasks = useMemo(() => (openWork?.items || []).filter((item) => item.owner_id === personId), [openWork, personId]);
  const summary = overview?.summary;
  const undatedCount = openWork?.undatedTotal || 0;

  const showTasks = (filters: { site?: string; owner?: number; focus?: typeof focus } = {}) => {
    setSiteId(filters.site || ''); setOwnerId(filters.owner ? String(filters.owner) : '');
    setTeamId(''); setFocus(filters.focus || 'open'); setSearch(''); setQuery(''); setOffset(0); setSection('tasks');
  };
  const openDecision = (task: ManagementTask, value: 'approve' | 'changes_requested') => {
    setDecision({ task, value }); setDecisionNote('');
  };
  const saveDecision = async () => {
    if (!decision || decisionBusy) return;
    if (decision.value === 'changes_requested' && decisionNote.trim().length < 3) {
      toast.error('دلیل اصلاح را برای مسئول کار بنویسید'); return;
    }
    setDecisionBusy(true);
    try {
      await commandApi.reviewTask(decision.task, decision.value, decisionNote);
      toast.success(decision.value === 'approve' ? 'نتیجهٔ کار تأیید شد' : 'کار با توضیح برای اصلاح برگشت');
      setDecision(null); setDecisionNote(''); setRevision((value) => value + 1);
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ثبت تصمیم انجام نشد؛ داده‌ها را تازه کنید'); }
    finally { setDecisionBusy(false); }
  };
  const reviewCard = (task: ManagementTask) => <article key={task.id} className='rounded-xl border bg-card p-4'>
    <div className='flex flex-wrap items-start justify-between gap-3'><div className='min-w-0 flex-1'>
      <div className='flex flex-wrap items-center gap-2'><Badge variant='outline' className='border-amber-500/30 text-amber-700'>منتظر تأیید</Badge>
        <span className='text-muted-foreground text-xs'>{task.site_name} · {task.owner_name || 'بی‌مسئول'}</span></div>
      <Link href={taskUrl(task)} className='mt-2 block font-semibold leading-6 hover:text-primary'>{task.title}</Link>
      {task.description && <p className='text-muted-foreground mt-1 line-clamp-2 text-xs leading-5'>{task.description}</p>}
      <div className='text-muted-foreground mt-2 flex flex-wrap gap-3 text-xs'>
        <span>چک‌لیست {number.format(task.checklist_done)}/{number.format(task.checklist_total)}</span>
        <span>پیشرفت ثبت‌شده {number.format(task.progress_percent)}٪</span>
        <span>آخرین تغییر {formatUserDateTime(task.updated_at, calendar)}</span></div>
    </div><div className='flex shrink-0 flex-wrap gap-2'><Link href={taskUrl(task)} className='rounded-md border px-3 py-1.5 text-xs hover:bg-muted'>جزئیات و گفت‌وگو</Link>
      <Button size='sm' variant='outline' onClick={() => openDecision(task, 'changes_requested')}>درخواست اصلاح</Button>
      <Button size='sm' onClick={() => openDecision(task, 'approve')}>تأیید نتیجه</Button></div></div>
  </article>;

  return <div className='space-y-5' dir='rtl'>
    <header className='rounded-2xl border bg-gradient-to-l from-sky-500/10 via-background to-violet-500/10 p-5'>
      <div className='flex flex-wrap items-center justify-between gap-4'><div><Badge variant='outline'>مدیر کل · همهٔ پروژه‌ها</Badge>
        <h2 className='mt-2 text-2xl font-bold'>اتاق هدایت تیم</h2>
        <p className='text-muted-foreground mt-1 text-sm'>تصمیم‌های منتظر شما، کار هر نفر و وضعیت پروژه‌ها در یک مسیر روشن.</p></div>
        <Button variant='outline' disabled={loading} onClick={() => setRevision((value) => value + 1)}>به‌روزرسانی</Button></div>
      <nav className='mt-5 flex flex-wrap gap-2' aria-label='بخش‌های مدیریت'>
        {sections.map((entry) => <Button key={entry.id} size='sm' variant={section === entry.id ? 'default' : 'outline'}
          aria-pressed={section === entry.id} onClick={() => setSection(entry.id)}>{entry.label}{entry.id === 'reviews' && summary?.review_tasks ? ` · ${number.format(summary.review_tasks)}` : ''}</Button>)}
      </nav>
    </header>
    {error && <div role='alert' className='rounded-xl border border-rose-500/40 p-3 text-sm text-rose-600'>{error}</div>}
    {loading && !overview && <p className='rounded-xl border p-10 text-center text-sm text-muted-foreground'>در حال دریافت کارهای تیم…</p>}
    {summary && <section className='grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5' aria-label='وضعیت همهٔ پروژه‌ها'>
      {([['منتظر تأیید', summary.review_tasks, 'reviews'], ['کار باز', summary.open_tasks, 'tasks'],
        ['بی‌موعد', undatedCount, 'gantt'], ['مانع‌دار', summary.blocked_tasks, 'tasks'],
        ['همکار فعال', summary.active_people, 'team']] as const).map(([label, value, target]) =>
        <button key={label} type='button' onClick={() => { if (target === 'tasks' && label === 'مانع‌دار') showTasks({ focus: 'blocked' }); else setSection(target); }}
          className='rounded-xl border bg-card p-4 text-right transition-colors hover:border-primary/40 hover:bg-muted/30'>
          <span className='text-muted-foreground block text-xs'>{label}</span><strong className='mt-2 block text-2xl'>{number.format(value)}</strong></button>)}
    </section>}

    {section === 'today' && <div className='space-y-5'>
      <Card><CardHeader className='flex flex-row flex-wrap items-center justify-between gap-3'><div><CardTitle>اول تأیید این کارها</CardTitle>
        <CardDescription>کارهایی که همکاران در مرحلهٔ بازبینی گذاشته‌اند. جزئیات و گفت‌وگو را باز کنید، سپس تأیید یا اصلاح را ثبت کنید.</CardDescription></div>
        <Button size='sm' variant='outline' onClick={() => setSection('reviews')}>دیدن همهٔ {number.format(reviews?.total || 0)} کار</Button></CardHeader>
        <CardContent className='space-y-2'>{reviews?.items.slice(0, 5).map(reviewCard)}
          {!reviews?.total && <p className='text-muted-foreground rounded-lg border border-dashed p-5 text-sm'>کاری منتظر تأیید نیست.</p>}
        </CardContent></Card>
      <div className='grid gap-4 xl:grid-cols-2'>
        <Card><CardHeader><CardTitle>الان هر نفر چه می‌کند؟</CardTitle><CardDescription>تعداد کارها از تسک‌های واقعی همهٔ پروژه‌هاست.</CardDescription></CardHeader>
          <CardContent className='space-y-2'>{people.map((person) => <button key={person.id} type='button'
            onClick={() => { setPersonId(person.id); setSection('team'); }} className='flex w-full items-center justify-between gap-3 rounded-lg border p-3 text-right hover:bg-muted/40'>
            <span><strong className='block text-sm'>{person.full_name}</strong><span className='text-muted-foreground text-xs'>@{person.username} · {person.team_name || 'بدون تیم'}</span></span>
            <span className='flex gap-2 text-xs'><Badge variant='outline'>{number.format(person.open_tasks)} باز</Badge>
              {person.review_tasks > 0 && <Badge variant='outline' className='border-amber-500/40'>{number.format(person.review_tasks)} بازبینی</Badge>}</span>
          </button>)}</CardContent></Card>
        <Card><CardHeader><CardTitle>پروژه‌های در جریان</CardTitle><CardDescription>پیشرفت و کارهای باز؛ انتخاب پروژه، همهٔ تسک‌های آن را نشان می‌دهد.</CardDescription></CardHeader>
          <CardContent className='max-h-[450px] space-y-2 overflow-y-auto'>{projectRows.filter((project) => project.open_tasks > 0).slice(0, 10).map((project) =>
            <button key={project.site_id} type='button' onClick={() => showTasks({ site: project.site_id })}
              className='flex w-full items-center justify-between gap-3 rounded-lg border p-3 text-right hover:bg-muted/40'>
              <span className='min-w-0'><strong className='block truncate text-sm'>{project.name}</strong>
                <span className='text-muted-foreground text-xs'>راهبر: {project.lead_name || 'تعیین نشده'} · {number.format(project.open_tasks)} کار باز</span></span>
              <Badge variant='outline'>{number.format(project.progress_percent)}٪</Badge></button>)}
            {!projectRows.some((project) => project.open_tasks > 0) && <p className='text-muted-foreground text-sm'>پروژه‌ای با کار باز ثبت نشده است.</p>}
          </CardContent></Card>
      </div>
      {undatedCount > 0 && <button type='button' onClick={() => setSection('gantt')} className='w-full rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-right text-sm hover:bg-amber-500/10'>
        <strong>{number.format(undatedCount)} کار باز هنوز موعد ندارد.</strong><span className='text-muted-foreground mr-2'>در گانت، این‌ها جدا و با نام مسئول دیده می‌شوند تا زمان‌بندی‌شان مشخص شود.</span></button>}
    </div>}

    {section === 'reviews' && <Card><CardHeader><CardTitle>صف تأیید مدیر</CardTitle>
      <CardDescription>{number.format(reviews?.total || 0)} کار در مرحلهٔ بازبینی. تصمیم شما در تاریخچهٔ کار ثبت و به مسئول آن اعلام می‌شود.</CardDescription></CardHeader>
      <CardContent className='space-y-2'>{reviews?.items.map(reviewCard)}
        {!reviews?.total && <p className='text-muted-foreground rounded-lg border border-dashed p-6 text-sm'>همهٔ کارهای بازبینی‌شده تعیین تکلیف شده‌اند.</p>}
        {(reviews?.total || 0) > (reviews?.items.length || 0) && <Button variant='outline' onClick={() => showTasks({ focus: 'review' })}>دیدن ادامهٔ صف در فهرست کامل</Button>}
      </CardContent></Card>}

    {section === 'team' && <div className='grid gap-4 xl:grid-cols-[330px_minmax(0,1fr)]'>
      <Card><CardHeader><CardTitle>اعضای تیم</CardTitle><CardDescription>برای دیدن کارهای یک نفر، نام او را انتخاب کنید.</CardDescription></CardHeader>
        <CardContent className='max-h-[620px] space-y-2 overflow-y-auto'>{people.map((person) =>
          <button key={person.id} type='button' onClick={() => setPersonId(person.id)}
            className={`w-full rounded-lg border p-3 text-right hover:bg-muted/40 ${personId === person.id ? 'border-primary bg-primary/5' : ''}`}>
            <strong className='block text-sm'>{person.full_name}</strong><span className='text-muted-foreground block text-xs'>@{person.username} · {person.team_name || 'بدون تیم'}</span>
            <span className='mt-2 flex flex-wrap gap-1 text-xs'><Badge variant='outline'>{number.format(person.open_tasks)} باز</Badge>
              <Badge variant='outline'>{number.format(person.review_tasks)} بازبینی</Badge>
              <Badge variant='outline'>{number.format(person.completed_tasks)} تأییدشده</Badge></span></button>)}
        </CardContent></Card>
      <Card><CardHeader><CardTitle>{people.find((person) => person.id === personId)?.full_name || 'همهٔ اعضا'}</CardTitle>
        <CardDescription>{personId ? 'کارهای باز این نفر در همهٔ پروژه‌ها؛ هر سطر به کارت و گفت‌وگوی همان کار می‌رود.' : 'یکی از اعضا را انتخاب کنید تا پروژه‌ها و کارهای فعلی‌اش را ببینید.'}</CardDescription></CardHeader>
        <CardContent className='space-y-3'>{personId && <>
          <div className='flex flex-wrap gap-2'>{people.find((person) => person.id === personId)?.projects.map((project) =>
            <button key={project.site_id} type='button' onClick={() => showTasks({ site: project.site_id, owner: personId })}
              className='rounded-md border px-2 py-1 text-xs hover:bg-muted'>{project.name} · {project.responsibility === 'lead' ? 'راهبر' : project.responsibility === 'contributor' ? 'مجری' : 'ناظر'}</button>)}</div>
          <div className='max-h-[600px] space-y-2 overflow-y-auto'>{personTasks.map((task) => <Link key={task.id} href={taskUrl(task)}
            className='block rounded-lg border p-3 hover:border-primary/40 hover:bg-muted/30'><div className='flex flex-wrap items-center justify-between gap-2'>
              <strong className='text-sm'>{task.title}</strong><Badge variant='outline'>{statusText[task.status]}</Badge></div>
              <span className='text-muted-foreground mt-1 block text-xs'>{task.site_name} · {task.due_at ? `موعد ${formatUserDate(task.due_at, calendar)}` : 'بی‌موعد'} · چک‌لیست {number.format(task.checklist_done)}/{number.format(task.checklist_total)}</span>
          </Link>)}{!personTasks.length && <p className='text-muted-foreground text-sm'>کار بازی برای این نفر ثبت نشده است.</p>}</div>
          <Button size='sm' variant='outline' onClick={() => showTasks({ owner: personId })}>همهٔ سوابق این نفر</Button>
        </>}</CardContent></Card>
    </div>}

    {section === 'projects' && <Card><CardHeader><CardTitle>همهٔ پروژه‌ها</CardTitle>
      <CardDescription>سایت‌ها و پروژه‌های دستی، راهبر و حجم کار واقعی. برای بازکردن برد کامل، وارد پروژه شوید.</CardDescription></CardHeader>
      <CardContent className='grid gap-3 md:grid-cols-2 xl:grid-cols-3'>{projectRows.map((project) => <article key={project.site_id} className='rounded-xl border p-4'>
        <div className='flex items-start justify-between gap-2'><strong className='text-sm'>{project.name}</strong><Badge variant='outline'>{number.format(project.progress_percent)}٪</Badge></div>
        <p className='text-muted-foreground mt-2 text-xs'>راهبر: {project.lead_name || 'تعیین نشده'} · {number.format(project.members)} عضو</p>
        <div className='mt-3 flex flex-wrap gap-2 text-xs'><Badge variant='secondary'>{number.format(project.open_tasks)} باز</Badge>
          {project.blocked_tasks > 0 && <Badge variant='destructive'>{number.format(project.blocked_tasks)} مانع</Badge>}
          {project.overdue_tasks > 0 && <Badge variant='outline'>{number.format(project.overdue_tasks)} عقب‌افتاده</Badge>}</div>
        <div className='mt-3 h-1.5 rounded-full bg-muted'><div className='h-full rounded-full bg-emerald-500' style={{ width: `${Math.min(100, project.progress_percent)}%` }} /></div>
        <div className='mt-4 flex flex-wrap gap-2'><Button size='sm' variant='outline' onClick={() => showTasks({ site: project.site_id })}>تسک‌ها</Button>
          <Link href={`/dashboard/work?view=kanban&site=${encodeURIComponent(project.site_id)}`} className='rounded-md border px-3 py-1.5 text-xs hover:bg-muted'>برد پروژه</Link></div>
      </article>)}{!projectRows.length && <p className='text-muted-foreground text-sm'>پروژه‌ای ثبت نشده است.</p>}
      </CardContent></Card>}

    {section === 'gantt' && openWork && <ManagerGantt items={openWork.items} total={openWork.total} calendar={calendar} />}

    {section === 'tasks' && <Card><CardHeader><CardTitle>فهرست کامل تسک‌ها</CardTitle>
      <CardDescription>نتیجه‌ها صفحه‌بندی می‌شوند؛ فیلترها فقط روی این فهرست اعمال می‌شوند و شاخص‌های بالای صفحه همچنان کل تیم را نشان می‌دهند.</CardDescription></CardHeader>
      <CardContent className='space-y-3'><div className='grid gap-2 md:grid-cols-2 xl:grid-cols-5'>
        <Input aria-label='جست‌وجوی کار' placeholder='عنوان، پروژه یا مسئول…' value={search} onChange={(event) => setSearch(event.target.value)} />
        <NativeSelect aria-label='پروژه' value={siteId} onChange={(event) => { setSiteId(event.target.value); setOffset(0); }}><NativeSelectOption value=''>همهٔ پروژه‌ها</NativeSelectOption>
          {projects.map((project) => <NativeSelectOption key={project.site_id} value={project.site_id}>{project.name}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect aria-label='مسئول' value={ownerId} onChange={(event) => { setOwnerId(event.target.value); setOffset(0); }}><NativeSelectOption value=''>همهٔ مسئولان</NativeSelectOption>
          {people.map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect aria-label='تیم' value={teamId} onChange={(event) => { setTeamId(event.target.value); setOffset(0); }}><NativeSelectOption value=''>همهٔ تیم‌ها</NativeSelectOption>
          {teams.map(([id, name]) => <NativeSelectOption key={id} value={String(id)}>{name}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect aria-label='مرحله' value={focus} onChange={(event) => { setFocus(event.target.value as typeof focus); setOffset(0); }}>
          {focusOptions.map((option) => <NativeSelectOption key={option.value} value={option.value}>{option.label}</NativeSelectOption>)}</NativeSelect>
      </div><div className='flex items-center justify-between gap-2 text-xs'><span>{number.format(ledger?.total || 0)} نتیجه {ledgerLoading ? '· در حال بارگیری…' : ''}</span>
        <Button size='sm' variant='ghost' onClick={() => { setSiteId(''); setOwnerId(''); setTeamId(''); setSearch(''); setFocus('open'); setOffset(0); }}>پاک‌کردن فیلترها</Button></div>
      <div className='overflow-x-auto rounded-xl border'><table className='w-full min-w-[900px] text-right text-xs'><thead className='bg-muted/50'><tr>
        <th className='p-3'>تسک / پروژه</th><th>مسئول</th><th>مرحله</th><th>اولویت</th><th>موعد</th><th>پیشرفت</th><th>کارت</th>
      </tr></thead><tbody>{ledger?.items.map((task) => <tr key={task.id} className='border-t hover:bg-muted/30'>
        <td className='max-w-[300px] p-3'><strong className='block truncate'>{task.title}</strong><span className='text-muted-foreground block truncate'>{task.site_name}</span></td>
        <td>{task.owner_name || 'بی‌مسئول'}</td><td><Badge variant='outline'>{statusText[task.status]}</Badge></td><td>{priorityText[task.priority]}</td>
        <td>{task.due_at ? formatUserDate(task.due_at, calendar) : 'بی‌موعد'}</td>
        <td>{number.format(task.status === 'verified' ? 100 : task.progress_percent)}٪ · {number.format(task.checklist_done)}/{number.format(task.checklist_total)}</td>
        <td><Link href={taskUrl(task)} className='text-primary hover:underline'>بازکردن</Link></td>
      </tr>)}</tbody></table>{!ledgerLoading && !ledger?.items.length && <p className='text-muted-foreground p-6 text-center text-sm'>تسکی با این فیلترها پیدا نشد.</p>}</div>
      <div className='flex items-center justify-between text-xs'><span>{number.format(offset + (ledger?.items.length || 0))} از {number.format(ledger?.total || 0)}</span>
        <div className='flex gap-2'><Button size='sm' variant='outline' disabled={offset === 0 || ledgerLoading} onClick={() => setOffset(Math.max(0, offset - 50))}>قبلی</Button>
          <Button size='sm' variant='outline' disabled={ledgerLoading || offset + 50 >= (ledger?.total || 0)} onClick={() => setOffset(offset + 50)}>بعدی</Button></div></div>
      </CardContent></Card>}

    {section === 'reports' && <div className='space-y-4'><Card><CardHeader className='flex flex-row flex-wrap items-center justify-between gap-3'>
      <div><CardTitle>گزارش کار ثبت‌شده</CardTitle><CardDescription>ایجاد، تکمیل و زمان ثبت‌شده از تاریخچهٔ واقعی تسک‌ها خوانده می‌شود.</CardDescription></div>
      <NativeSelect aria-label='بازهٔ گزارش' value={period} onChange={(event) => setPeriod(event.target.value as 'week' | 'month')} className='w-36'>
        <NativeSelectOption value='week'>این هفته</NativeSelectOption><NativeSelectOption value='month'>این ماه</NativeSelectOption></NativeSelect></CardHeader>
      <CardContent><div className='grid gap-3 md:grid-cols-3'>{([['ایجادشده', report?.totals.created || 0], ['تکمیل‌شده', report?.totals.completed || 0],
        ['زمان ثبت‌شده', Math.round((report?.totals.minutes || 0) / 6) / 10]] as const).map(([label, value]) =>
        <div key={label} className='rounded-lg border p-4 text-sm'><span className='text-muted-foreground block'>{label}</span><strong className='mt-1 block text-xl'>{number.format(value)}{label === 'زمان ثبت‌شده' ? ' ساعت' : ''}</strong></div>)}</div>
        <div className='mt-4 h-64' dir='ltr'>{report?.daily.length ? <ResponsiveContainer width='100%' height='100%'><BarChart data={report.daily}>
          <CartesianGrid strokeDasharray='3 3' opacity={.2} /><XAxis dataKey='day' tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} /><Tooltip />
          <Bar dataKey='created' name='ایجاد' fill='#6366f1' /><Bar dataKey='completed' name='تکمیل' fill='#10b981' />
        </BarChart></ResponsiveContainer> : <p className='text-muted-foreground pt-16 text-center text-sm'>در این بازه رویدادی ثبت نشده است.</p>}</div>
      </CardContent></Card>
      <Card><CardHeader><CardTitle>عملکرد افراد و پروژه‌ها</CardTitle><CardDescription>عددها فعالیت ثبت‌شده در بازهٔ انتخابی هستند، نه ارزیابی کیفیت کار.</CardDescription></CardHeader>
        <CardContent className='grid gap-5 xl:grid-cols-2'><div className='space-y-2'><h3 className='text-sm font-semibold'>افراد</h3>
          {report?.by_person.map((person) => <div key={person.user_id ?? person.name} className='flex justify-between rounded-lg border p-3 text-xs'>
            <span>{person.name}</span><span>{number.format(person.created)} ایجاد · {number.format(person.completed)} تکمیل · {number.format(Math.round(person.minutes / 6) / 10)} ساعت</span></div>)}
        </div><div className='space-y-2'><h3 className='text-sm font-semibold'>پروژه‌ها</h3>
          {report?.by_project.map((project) => <div key={project.site_id} className='flex justify-between rounded-lg border p-3 text-xs'>
            <span>{project.name}</span><span>{number.format(project.created)} ایجاد · {number.format(project.completed)} تکمیل</span></div>)}
        </div></CardContent></Card>
    </div>}

    <Dialog open={decision !== null} onOpenChange={(open) => { if (!open && !decisionBusy) setDecision(null); }}>
      <DialogContent dir='rtl'><DialogHeader><DialogTitle>{decision?.value === 'approve' ? 'تأیید نتیجهٔ کار' : 'بازگرداندن برای اصلاح'}</DialogTitle>
        <DialogDescription>{decision?.task.title} · {decision?.task.owner_name || 'بی‌مسئول'} · {decision?.task.site_name}</DialogDescription></DialogHeader>
        {decision && <div className='space-y-3'><p className='text-muted-foreground text-xs'>پیش از تصمیم، <Link href={taskUrl(decision.task)} target='_blank' className='text-primary underline'>کارت، چک‌لیست و گفت‌وگو</Link> را بررسی کنید.</p>
          {decision.task.verification_note && <p className='rounded-lg border p-3 text-xs'>مدرک ثبت‌شده: {decision.task.verification_note}</p>}
          <Textarea aria-label='توضیح تصمیم' rows={4} maxLength={2000} value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)}
            placeholder={decision.value === 'approve' ? 'یادداشت تأیید (اختیاری)' : 'چه چیزی باید اصلاح شود؟ این توضیح در تاریخچه می‌ماند.'} />
          <div className='flex gap-2'><Button disabled={decisionBusy || (decision.value === 'changes_requested' && decisionNote.trim().length < 3)} onClick={() => void saveDecision()}>
            {decisionBusy ? 'در حال ثبت…' : decision.value === 'approve' ? 'ثبت تأیید' : 'بازگرداندن به اجرا'}</Button>
            <Button variant='outline' disabled={decisionBusy} onClick={() => setDecision(null)}>انصراف</Button></div>
        </div>}
      </DialogContent>
    </Dialog>
  </div>;
}
