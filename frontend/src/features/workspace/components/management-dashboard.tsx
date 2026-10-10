'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { IconActivity, IconAlertTriangle, IconArrowLeft, IconCalendarOff, IconChartBar, IconChecklist, IconClock, IconFolders, IconLayoutDashboard, IconListDetails, IconRefresh, IconTimeline, IconUsersGroup } from '@tabler/icons-react';
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
import { TaskDiscussion } from './task-discussion';

const number = new Intl.NumberFormat('fa-IR');
type Section = 'today' | 'reviews' | 'team' | 'projects' | 'gantt' | 'tasks' | 'reports';
const sections = [
  { id: 'today', label: 'نمای مدیر', icon: IconLayoutDashboard },
  { id: 'reviews', label: 'صف تأیید', icon: IconChecklist },
  { id: 'team', label: 'تیم', icon: IconUsersGroup },
  { id: 'projects', label: 'پروژه‌ها', icon: IconFolders },
  { id: 'gantt', label: 'زمان‌بندی', icon: IconTimeline },
  { id: 'tasks', label: 'همهٔ کارها', icon: IconListDetails },
  { id: 'reports', label: 'گزارش‌ها', icon: IconChartBar }
] as const;
const statusText: Record<string, string> = {
  new: 'ورودی', triaged: 'بررسی اولیه', approved: 'آماده', assigned: 'واگذارشده',
  in_progress: 'در حال اجرا', review: 'منتظر تأیید', published: 'منتشرشده',
  measurement_pending: 'در انتظار سنجش', verified: 'تأییدشده', blocked: 'مانع‌دار',
  rejected: 'ردشده', deferred: 'تعویق'
};
const priorityText: Record<string, string> = { critical: 'فوری', high: 'بالا', normal: 'معمولی', low: 'کم' };
const activityText: Record<string, string> = {
  created: 'کار را ایجاد کرد', updated: 'کار را ویرایش کرد', comment: 'در گفت‌وگو پیام گذاشت',
  comment_edited: 'پیام خود را ویرایش کرد', status_changed: 'مرحلهٔ کار را تغییر داد',
  review_approved: 'نتیجه را تأیید کرد', review_changes_requested: 'درخواست اصلاح داد',
  deleted: 'کار را به آرشیو برد', restored: 'کار را بازیابی کرد'
};
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
  return { items, total: first.total, undatedTotal: first.schedule.unscheduled, stages: first.stages };
}

function Initials({ name, tone = 'sky' }: { name: string; tone?: 'sky' | 'amber' | 'violet' }) {
  const color = tone === 'amber' ? 'bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200'
    : tone === 'violet' ? 'bg-violet-100 text-violet-800 dark:bg-violet-500/20 dark:text-violet-200'
      : 'bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-200';
  return <span aria-hidden='true' className={`inline-flex size-9 shrink-0 items-center justify-center rounded-xl text-sm font-bold ${color}`}>
    {name.trim().slice(0, 1).toUpperCase() || '؟'}
  </span>;
}

function ManagerGantt({ items, total, calendar, onTask }: {
  items: ManagementTask[]; total: number;
  calendar: ReturnType<typeof useDatePreference>['calendar'];
  onTask: (task: ManagementTask) => void;
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
            <button type='button' onClick={() => onTask(task)} className='min-w-0 p-2.5 text-right text-xs hover:text-primary'><strong className='block truncate'>{task.title}</strong>
              <span className='text-muted-foreground block truncate'>{task.owner_name || 'بی‌مسئول'} · {task.site_name}</span></button>
            <div className='relative mx-3 my-3 h-7 rounded-md bg-muted/40' dir='ltr' style={{ backgroundImage: 'linear-gradient(to right, transparent 49.8%, var(--border) 50%, transparent 50.2%)' }}>
              <span className='absolute inset-y-0 border-r-2 border-dashed border-foreground/30' style={{ left: `${position(dateNumber(today))}%` }} title='امروز' />
              <span className={`absolute top-2 h-3 rounded-full ${color}`} style={{ left: `${left}%`, width: `${width}%` }}
                title={`${task.start_at ? formatUserDate(task.start_at, calendar) : 'شروع ثبت نشده'} ← ${task.due_at ? formatUserDate(task.due_at, calendar) : 'موعد ثبت نشده'}`} />
            </div></div>;
        })}</div></div> : <p className='rounded-xl border border-dashed p-5 text-sm text-muted-foreground'>در بازهٔ انتخابی، کاری با تاریخ ثبت‌شده وجود ندارد. کارهای بدون تاریخ در بخش زیر قابل پیگیری‌اند.</p>}
    </CardContent></Card>
    <Card><CardHeader><CardTitle>کارهای منتظر تعیین موعد</CardTitle>
      <CardDescription>این کارها انجام می‌شوند اما هنوز موعد ندارند؛ با بازکردن کارت می‌توانید تاریخ واقعی ثبت کنید.</CardDescription></CardHeader>
      <CardContent className='grid gap-2 md:grid-cols-2 xl:grid-cols-3'>{undated.map((task) => <button key={task.id} type='button' onClick={() => onTask(task)}
        className='rounded-lg border p-3 text-right text-xs transition-colors hover:border-primary/50 hover:bg-muted/30'><strong className='block truncate text-sm'>{task.title}</strong>
        <span className='text-muted-foreground mt-1 block truncate'>{task.owner_name || 'بی‌مسئول'} · {task.site_name}</span>
        <Badge variant='outline' className='mt-2'>{statusText[task.status]}</Badge></button>)}
        {!undated.length && <p className='text-sm text-muted-foreground'>همهٔ کارهای باز حداقل یک تاریخ دارند.</p>}
      </CardContent></Card>
  </div>;
}

export function ManagementDashboard() {
  const { calendar } = useDatePreference();
  const reduceMotion = useReducedMotion();
  const [section, setSection] = useState<Section>('today');
  const [overview, setOverview] = useState<ManagementOverview | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [openWork, setOpenWork] = useState<Awaited<ReturnType<typeof loadOpenWork>> | null>(null);
  const [reviews, setReviews] = useState<ManagementTaskLedger | null>(null);
  const [ledger, setLedger] = useState<ManagementTaskLedger | null>(null);
  const [report, setReport] = useState<WorkReport | null>(null);
  const [period, setPeriod] = useState<'week' | 'month'>('week');
  const [siteId, setSiteId] = useState('');
  const [ownerId, setOwnerId] = useState('');
  const [teamId, setTeamId] = useState('');
  const [focus, setFocus] = useState<NonNullable<ManagementTaskFilters['focus']>>('open');
  const [statusFilter, setStatusFilter] = useState<ManagementTaskFilters['status']>();
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [personId, setPersonId] = useState<number | null>(null);
  const [panelTaskId, setPanelTaskId] = useState<number | null>(null);
  const [panelTask, setPanelTask] = useState<ManagementTask | null>(null);
  const [panelLoading, setPanelLoading] = useState(false);
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
      team_id: teamId ? Number(teamId) : undefined, focus, status: statusFilter,
      q: query || undefined, offset, limit: 50 })
      .then((result) => { if (active) { setLedger(result); setError(''); } })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'فهرست کارها بارگیری نشد'); })
      .finally(() => { if (active) setLedgerLoading(false); });
    return () => { active = false; };
  }, [section, siteId, ownerId, teamId, focus, statusFilter, query, offset, revision]);
  useEffect(() => {
    if (section !== 'reports') return;
    let active = true;
    void commandApi.report(period, new Date().toISOString().slice(0, 10))
      .then((result) => { if (active) setReport(result); })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'گزارش بارگیری نشد'); });
    return () => { active = false; };
  }, [section, period, revision]);
  useEffect(() => {
    if (panelTaskId === null) return;
    let active = true; setPanelLoading(true);
    void commandApi.managementTask(panelTaskId)
      .then((task) => { if (active) setPanelTask(task); })
      .catch((cause) => {
        if (active) {
          toast.error(cause instanceof Error ? cause.message : 'جزئیات کار دریافت نشد');
          setPanelTaskId(null); setPanelTask(null);
        }
      }).finally(() => { if (active) setPanelLoading(false); });
    return () => { active = false; };
  }, [panelTaskId, revision]);

  const people = useMemo(() => [...(overview?.people || [])].filter((person) => person.active)
    .toSorted((a, b) => b.review_tasks - a.review_tasks || b.open_tasks - a.open_tasks || a.full_name.localeCompare(b.full_name)), [overview]);
  const projectRows = useMemo(() => [...projects].toSorted((a, b) => b.overdue_tasks - a.overdue_tasks || b.open_tasks - a.open_tasks), [projects]);
  const teams = useMemo(() => [...new Map(people.filter((person) => person.team_id && person.team_name)
    .map((person) => [person.team_id!, person.team_name!] as const)).entries()], [people]);
  const selectedPersonId = personId ?? people[0]?.id ?? null;
  const selectedPerson = people.find((person) => person.id === selectedPersonId);
  const personTasks = useMemo(() => (openWork?.items || []).filter((item) => item.owner_id === selectedPersonId), [openWork, selectedPersonId]);
  const summary = overview?.summary;
  const undatedCount = openWork?.undatedTotal || 0;
  const verifiedCount = openWork?.stages.find((row) => row.key === 'verified')?.count || 0;
  const verifiedRate = summary?.total_tasks ? Math.round(verifiedCount / summary.total_tasks * 100) : 0;
  const activeProjects = projectRows.filter((project) => project.open_tasks > 0);
  const stageRows = (openWork?.stages || []).filter((row) => row.count > 0 && !['verified', 'rejected', 'deferred'].includes(row.key)).toSorted((a, b) => b.count - a.count);
  const maxStage = Math.max(1, ...stageRows.map((row) => row.count));

  const showTasks = (filters: { site?: string; owner?: number; focus?: typeof focus; status?: ManagementTaskFilters['status'] } = {}) => {
    setSiteId(filters.site || ''); setOwnerId(filters.owner ? String(filters.owner) : '');
    setTeamId(''); setFocus(filters.focus || 'open'); setStatusFilter(filters.status); setSearch(''); setQuery(''); setOffset(0); setSection('tasks');
  };
  const openTaskPanel = (task: ManagementTask | number) => {
    const id = typeof task === 'number' ? task : task.id;
    setPanelTask(typeof task === 'number' ? null : task);
    setPanelTaskId(id); setDecisionNote('');
  };
  const closeTaskPanel = () => { if (!decisionBusy) { setPanelTaskId(null); setPanelTask(null); setDecisionNote(''); } };
  const saveDecision = async (value: 'approve' | 'changes_requested') => {
    if (!panelTask || panelTask.status !== 'review' || decisionBusy || panelLoading) return;
    if (value === 'changes_requested' && decisionNote.trim().length < 3) {
      toast.error('دلیل اصلاح را برای مسئول کار بنویسید'); return;
    }
    setDecisionBusy(true);
    try {
      await commandApi.reviewTask(panelTask, value, decisionNote);
      toast.success(value === 'approve' ? 'نتیجهٔ کار تأیید شد' : 'کار با توضیح برای اصلاح برگشت');
      setPanelTaskId(null); setPanelTask(null); setDecisionNote(''); setRevision((current) => current + 1);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'ثبت تصمیم انجام نشد؛ داده‌ها را تازه کنید');
      setRevision((current) => current + 1);
    }
    finally { setDecisionBusy(false); }
  };
  const reviewCard = (task: ManagementTask) => <article key={task.id}
    className='group rounded-2xl border border-border/70 bg-card p-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-amber-400/60 hover:shadow-md sm:p-5'>
    <div className='flex flex-wrap items-start justify-between gap-3'>
      <div className='flex min-w-0 items-start gap-3'>
        <Initials name={task.owner_name || task.site_name} tone='amber' />
        <div className='min-w-0'><span className='text-muted-foreground text-xs'>{task.site_name} <span aria-hidden='true'>/</span> {task.owner_name || 'بی‌مسئول'}</span>
          <button type='button' onClick={() => openTaskPanel(task)} className='mt-1 block text-right text-sm font-bold leading-6 transition-colors hover:text-primary sm:text-base'>{task.title}</button>
          {task.description && <p className='text-muted-foreground mt-1 line-clamp-2 max-w-2xl text-xs leading-5'>{task.description}</p>}
        </div>
      </div>
      <Badge variant='outline' className='border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200'>نیازمند تصمیم</Badge>
    </div>
    <div className='mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-border/60 pt-3 text-xs text-muted-foreground'>
      <span>چک‌لیست <strong className='text-foreground'>{number.format(task.checklist_done)}/{number.format(task.checklist_total)}</strong></span>
      <span>پیشرفت <strong className='text-foreground'>{number.format(task.progress_percent)}٪</strong></span>
      <span>آخرین تغییر {formatUserDateTime(task.updated_at, calendar)}</span>
    </div>
    <div className='mt-4 flex flex-wrap items-center gap-2'>
      <Button size='sm' onClick={() => openTaskPanel(task)}>بازبینی و گفت‌وگو <IconArrowLeft size={15} /></Button>
      <span className='text-muted-foreground text-xs'>تصمیم و پیام، هر دو در همین پنجره</span>
    </div>
  </article>;

  return <div className='space-y-5 pb-10' dir='rtl'>
    <header className='relative isolate overflow-hidden rounded-[28px] bg-gradient-to-bl from-[#112b4a] via-[#10243d] to-[#064c4c] p-5 text-white shadow-lg shadow-slate-950/10 sm:p-6'>
      <div aria-hidden='true' className='pointer-events-none absolute -left-12 -top-24 size-72 rounded-full bg-sky-400/20 blur-3xl' />
      <div aria-hidden='true' className='pointer-events-none absolute -bottom-32 right-1/3 size-72 rounded-full bg-teal-400/20 blur-3xl' />
      <div className='relative flex flex-wrap items-start justify-between gap-6'>
        <div className='max-w-2xl'>
          <span className='inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-medium text-teal-100'>
            <span className='size-2 rounded-full bg-teal-300 shadow-[0_0_12px_#5eead4]' /> نمای زندهٔ مدیریت · {formatUserDate(new Date(), calendar)}
          </span>
          <h2 className='mt-3 text-2xl font-black tracking-tight sm:text-3xl'>تیم امروز کجای کار است؟</h2>
          <p className='mt-1 max-w-xl text-sm leading-6 text-slate-200'>از اینجا کارهای منتظر تصمیم، مسئولیت هر نفر و وضعیت پروژه‌ها را ببینید و مستقیم سراغ همان کار بروید.</p>
          <div className='mt-4 flex flex-wrap gap-2'>
            <Button className='bg-teal-300 text-slate-950 hover:bg-teal-200' onClick={() => setSection('reviews')}>
              {number.format(summary?.review_tasks || 0)} کار منتظر تأیید <IconArrowLeft size={16} />
            </Button>
            <Button variant='outline' className='border-white/30 bg-white/5 text-white hover:bg-white/15 hover:text-white' onClick={() => setSection('team')}>دیدن کار افراد</Button>
          </div>
        </div>
        <div className='flex flex-col items-start gap-4'>
          <button type='button' disabled={loading} onClick={() => setRevision((value) => value + 1)}
            className='inline-flex items-center gap-2 rounded-xl border border-white/20 bg-white/10 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-white/20 disabled:opacity-50'>
            <IconRefresh size={16} className={loading ? 'animate-spin' : ''} /> تازه‌سازی داده‌ها
          </button>
          <button type='button' aria-label='نمایش کارهای تأییدشده' onClick={() => showTasks({ focus: 'completed' })}
            className='hidden items-center gap-4 rounded-2xl border border-white/15 bg-white/10 p-3 text-right transition-colors hover:bg-white/20 lg:flex'>
            <span className='flex size-16 shrink-0 items-center justify-center rounded-full p-1.5'
              style={{ background: `conic-gradient(#5eead4 ${verifiedRate}%, rgba(255,255,255,.18) 0)` }}>
              <span className='flex size-full items-center justify-center rounded-full bg-[#143349] text-sm font-bold'>{number.format(verifiedRate)}٪</span>
            </span>
            <span><strong className='block text-sm'>کارهای تأییدشده</strong><span className='mt-1 block text-xs text-slate-200'>{number.format(verifiedCount)} از {number.format(summary?.total_tasks || 0)} کار ثبت‌شده</span></span>
          </button>
        </div>
      </div>
      <div className='relative mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-white/15 pt-3 text-xs text-slate-200'>
        <span><strong className='text-lg text-white'>{number.format(summary?.active_people || 0)}</strong> همکار فعال</span>
        <span><strong className='text-lg text-white'>{number.format(activeProjects.length)}</strong> پروژه در جریان</span>
        <span><strong className='text-lg text-white'>{number.format(summary?.open_tasks || 0)}</strong> کار باز</span>
      </div>
    </header>
    <nav className='flex gap-1 overflow-x-auto rounded-2xl border border-border/70 bg-card/80 p-1.5 shadow-sm' aria-label='بخش‌های مدیریت'>
      {sections.map((entry) => <button key={entry.id} type='button' aria-pressed={section === entry.id} onClick={() => setSection(entry.id)}
        className={`inline-flex shrink-0 items-center gap-2 rounded-xl px-3 py-2.5 text-xs font-semibold transition-all duration-200 focus-visible:outline-2 focus-visible:outline-primary sm:px-4 ${section === entry.id ? 'bg-slate-900 text-white shadow-sm dark:bg-slate-100 dark:text-slate-900' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}>
        <entry.icon size={17} stroke={1.8} /> {entry.label}
        {entry.id === 'reviews' && !!summary?.review_tasks && <span className={`rounded-full px-1.5 py-0.5 text-[10px] ${section === entry.id ? 'bg-white/20 text-white dark:bg-slate-900/10 dark:text-slate-900' : 'bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200'}`}>{number.format(summary.review_tasks)}</span>}
      </button>)}
    </nav>
    {error && <div role='alert' className='rounded-xl border border-rose-500/40 p-3 text-sm text-rose-600'>{error}</div>}
    {loading && !overview && <div className='grid gap-3 md:grid-cols-3' aria-label='در حال دریافت داده‌ها'>{[0, 1, 2].map((item) => <div key={item} className='h-28 animate-pulse rounded-2xl bg-muted' />)}</div>}
    {summary && <section className='grid grid-cols-2 gap-3 md:grid-cols-4' aria-label='شاخص‌های قابل پیگیری تیم'>
      {([
        { label: 'منتظر تصمیم شما', value: summary.review_tasks, hint: 'بازبینی کارها', icon: IconChecklist, tone: 'amber', action: () => setSection('reviews') },
        { label: 'عقب‌افتاده', value: summary.overdue_tasks, hint: 'موعد گذشته', icon: IconClock, tone: 'rose', action: () => showTasks({ focus: 'overdue' }) },
        { label: 'مانع‌دار', value: summary.blocked_tasks, hint: 'نیازمند پیگیری', icon: IconAlertTriangle, tone: 'violet', action: () => showTasks({ focus: 'blocked' }) },
        { label: 'بدون موعد', value: undatedCount, hint: 'نیازمند برنامه‌ریزی', icon: IconCalendarOff, tone: 'sky', action: () => showTasks({ focus: 'unscheduled' }) }
      ] as const).map((item) => <button key={item.label} type='button' onClick={item.action}
        className='group relative overflow-hidden rounded-2xl border border-border/70 bg-card p-4 text-right shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md sm:p-5'>
        <span className={`absolute inset-y-0 right-0 w-1 ${item.tone === 'amber' ? 'bg-amber-400' : item.tone === 'rose' ? 'bg-rose-400' : item.tone === 'violet' ? 'bg-violet-400' : 'bg-sky-400'}`} />
        <span className='flex items-start justify-between gap-2'><span className='text-muted-foreground text-xs font-medium'>{item.label}</span>
          <item.icon size={20} className={item.tone === 'amber' ? 'text-amber-500' : item.tone === 'rose' ? 'text-rose-500' : item.tone === 'violet' ? 'text-violet-500' : 'text-sky-500'} stroke={1.7} /></span>
        <strong className='mt-2 block text-3xl font-black tabular-nums'>{number.format(item.value)}</strong>
        <span className='mt-2 flex items-center justify-between text-xs text-muted-foreground'><span>{item.hint}</span><IconArrowLeft size={15} className='opacity-0 transition-all group-hover:-translate-x-1 group-hover:opacity-100' /></span>
      </button>)}
    </section>}

    {section === 'today' && <motion.div initial={reduceMotion ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .28 }} className='space-y-4'>
      <div className='grid gap-4 xl:grid-cols-12'>
        <Card className='overflow-hidden border-border/70 shadow-sm xl:col-span-8'>
          <CardHeader className='border-b border-border/60 bg-gradient-to-l from-amber-50/80 to-background dark:from-amber-500/10'>
            <div className='flex flex-wrap items-start justify-between gap-3'><div>
              <div className='flex items-center gap-2'><span className='rounded-xl bg-amber-100 p-2 text-amber-700 dark:bg-amber-500/20 dark:text-amber-200'><IconChecklist size={21} /></span>
                <div><CardTitle className='text-lg'>میز تأیید شما</CardTitle><CardDescription className='mt-1'>کارهایی که همکاران برای تصمیم شما آماده کرده‌اند</CardDescription></div></div>
            </div><Button size='sm' variant='outline' onClick={() => setSection('reviews')}>کل صف · {number.format(reviews?.total || 0)} <IconArrowLeft size={15} /></Button></div>
          </CardHeader>
          <CardContent className='space-y-3 pt-5'>{reviews?.items.slice(0, 3).map(reviewCard)}
            {!reviews?.total && <div className='rounded-2xl border border-dashed p-8 text-center'><strong className='block text-sm'>فعلاً کاری منتظر تأیید نیست</strong><p className='text-muted-foreground mt-1 text-xs'>وقتی عضوی کاری را به بازبینی ببرد، همین‌جا ظاهر می‌شود.</p></div>}
          </CardContent>
        </Card>
        <Card className='overflow-hidden border-border/70 shadow-sm xl:col-span-4'>
          <CardHeader><div className='flex items-center gap-2'><span className='rounded-xl bg-violet-100 p-2 text-violet-700 dark:bg-violet-500/20 dark:text-violet-200'><IconActivity size={21} /></span>
            <div><CardTitle className='text-lg'>آخرین حرکت‌های تیم</CardTitle><CardDescription className='mt-1'>تغییرات ثبت‌شده روی کارها</CardDescription></div></div></CardHeader>
          <CardContent className='space-y-1'>
            {overview?.recent.slice(0, 6).map((event) => <button key={event.id} type='button' aria-label={`باز کردن ${event.task_title}`}
              onClick={() => openTaskPanel(event.work_item_id)}
              className='group flex w-full gap-3 rounded-xl p-2.5 text-right transition-colors hover:bg-muted/50'>
              <span className='relative mt-1.5 flex size-2 shrink-0 rounded-full bg-violet-500 ring-4 ring-violet-500/10' />
              <span className='min-w-0 flex-1'><span className='block text-xs leading-5'><strong>{event.actor_username || 'سیستم'}</strong> {activityText[event.event_type] || 'کاری را به‌روز کرد'}</span>
                <span className='mt-0.5 block truncate text-xs font-medium text-foreground group-hover:text-primary'>{event.task_title}</span>
                <span className='text-muted-foreground mt-0.5 block truncate text-[11px]'>{event.project_name} · {formatUserDateTime(event.created_at, calendar)}</span></span>
            </button>)}
            {!overview?.recent.length && <p className='text-muted-foreground rounded-xl border border-dashed p-5 text-center text-xs'>هنوز فعالیتی روی کارها ثبت نشده است.</p>}
            {!!summary?.unassigned_tasks && <button type='button' onClick={() => showTasks({ focus: 'unassigned' })}
              className='mt-2 flex w-full items-center gap-2 rounded-xl border border-amber-300/60 bg-amber-50/70 p-3 text-right text-xs font-semibold text-amber-900 transition-colors hover:bg-amber-100 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200'>
              <IconAlertTriangle size={17} /> {number.format(summary.unassigned_tasks)} کار بی‌مسئول؛ تعیین تکلیف کنید <IconArrowLeft size={15} className='mr-auto' />
            </button>}
          </CardContent>
        </Card>
      </div>
      <div className='grid gap-4 xl:grid-cols-12'>
        <Card className='border-border/70 shadow-sm xl:col-span-7'><CardHeader className='flex flex-row flex-wrap items-center justify-between gap-3'>
          <div><CardTitle className='flex items-center gap-2 text-lg'><IconUsersGroup size={20} className='text-sky-600' /> بار کاری تیم</CardTitle>
            <CardDescription className='mt-1'>روی نام هر نفر بزنید تا تسک‌های خودش را ببینید.</CardDescription></div>
          <Button size='sm' variant='ghost' onClick={() => setSection('team')}>همهٔ اعضا <IconArrowLeft size={15} /></Button></CardHeader>
          <CardContent className='space-y-2'>{people.slice(0, 6).map((person) => <button key={person.id} type='button'
            onClick={() => { setPersonId(person.id); setSection('team'); }} className='group flex w-full items-center gap-3 rounded-xl border border-border/60 p-3 text-right transition-colors hover:border-primary/30 hover:bg-muted/30'>
            <Initials name={person.full_name} /><span className='min-w-0 flex-1'><strong className='block truncate text-sm'>{person.full_name}</strong>
              <span className='text-muted-foreground block truncate text-xs'>{person.team_name || 'بدون تیم'} · {person.projects.length} پروژه</span></span>
            <span className='hidden w-24 sm:block'><span className='block h-1.5 overflow-hidden rounded-full bg-muted'><span className='block h-full rounded-full bg-sky-500' style={{ width: `${Math.min(100, person.open_tasks / Math.max(1, ...people.map((row) => row.open_tasks)) * 100)}%` }} /></span></span>
            <span className='min-w-12 text-center text-xs'><strong className='block text-base'>{number.format(person.open_tasks)}</strong><span className='text-muted-foreground'>باز</span></span>
            {person.review_tasks > 0 && <span className='rounded-full bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-800 dark:bg-amber-500/20 dark:text-amber-200'>{number.format(person.review_tasks)} بازبینی</span>}
            <IconArrowLeft size={16} className='text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100' />
          </button>)}{!people.length && <p className='text-muted-foreground py-8 text-center text-sm'>عضو فعالی ثبت نشده است.</p>}</CardContent></Card>
        <Card className='border-border/70 shadow-sm xl:col-span-5'><CardHeader className='flex flex-row flex-wrap items-center justify-between gap-3'>
          <div><CardTitle className='flex items-center gap-2 text-lg'><IconFolders size={20} className='text-teal-600' /> پروژه‌های در جریان</CardTitle>
            <CardDescription className='mt-1'>پیشرفت ثبت‌شده و مسئول اصلی هر پروژه</CardDescription></div>
          <Button size='sm' variant='ghost' onClick={() => setSection('projects')}>همه <IconArrowLeft size={15} /></Button></CardHeader>
          <CardContent className='space-y-2'>{activeProjects.slice(0, 5).map((project) => <button key={project.site_id} type='button' aria-label={`کارهای پروژهٔ ${project.name}`} onClick={() => showTasks({ site: project.site_id })}
            className='group block w-full rounded-xl border border-border/60 p-3 text-right transition-colors hover:border-primary/30 hover:bg-muted/30'>
            <span className='flex items-start justify-between gap-2'><span className='min-w-0'><strong className='block truncate text-sm'>{project.name}</strong>
              <span className='text-muted-foreground mt-1 block truncate text-xs'>راهبر: {project.lead_name || 'تعیین نشده'} · {number.format(project.open_tasks)} کار باز</span></span>
              <span className='text-xs font-bold text-teal-700 dark:text-teal-300'>{number.format(project.progress_percent)}٪</span></span>
            <span className='mt-3 block h-1.5 overflow-hidden rounded-full bg-muted'><span className='block h-full rounded-full bg-teal-500 transition-[width] duration-500' style={{ width: `${Math.min(100, project.progress_percent)}%` }} /></span>
          </button>)}{!activeProjects.length && <p className='text-muted-foreground py-8 text-center text-sm'>پروژه‌ای با کار باز ثبت نشده است.</p>}</CardContent></Card>
      </div>
      {!!stageRows.length && <Card className='border-border/70 shadow-sm'><CardHeader className='flex flex-row flex-wrap items-center justify-between gap-3'>
        <div><CardTitle className='text-lg'>کارها در چه مرحله‌ای هستند؟</CardTitle><CardDescription className='mt-1'>نمای کلی مراحل کارهای باز؛ انتخاب هر مرحله، تسک‌های آن را باز می‌کند.</CardDescription></div>
        <Button size='sm' variant='ghost' onClick={() => showTasks()}>فهرست کارها <IconArrowLeft size={15} /></Button></CardHeader>
        <CardContent className='grid gap-3 sm:grid-cols-2 xl:grid-cols-4'>{stageRows.map((row) => <button key={row.key} type='button' aria-label={`نمایش کارهای مرحلهٔ ${statusText[row.key] || row.key}`} onClick={() => showTasks({ focus: 'all', status: row.key })}
          className='rounded-xl border border-border/60 p-3 text-right transition-colors hover:border-primary/30 hover:bg-muted/30'>
          <span className='flex justify-between text-xs'><span>{statusText[row.key] || row.key}</span><strong>{number.format(row.count)}</strong></span>
          <span className='mt-3 block h-1.5 overflow-hidden rounded-full bg-muted'><span className='block h-full rounded-full bg-gradient-to-l from-sky-500 to-teal-400' style={{ width: `${row.count / maxStage * 100}%` }} /></span>
        </button>)}</CardContent></Card>}
    </motion.div>}

    {section === 'reviews' && <Card><CardHeader><CardTitle>صف تأیید مدیر</CardTitle>
      <CardDescription>{number.format(reviews?.total || 0)} کار در مرحلهٔ بازبینی. تصمیم شما در تاریخچهٔ کار ثبت و به مسئول آن اعلام می‌شود.</CardDescription></CardHeader>
      <CardContent className='space-y-2'>{reviews?.items.map(reviewCard)}
        {!reviews?.total && <p className='text-muted-foreground rounded-lg border border-dashed p-6 text-sm'>همهٔ کارهای بازبینی‌شده تعیین تکلیف شده‌اند.</p>}
        {(reviews?.total || 0) > (reviews?.items.length || 0) && <Button variant='outline' onClick={() => showTasks({ focus: 'review' })}>دیدن ادامهٔ صف در فهرست کامل</Button>}
      </CardContent></Card>}

    {section === 'team' && <div className='grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]'>
      <Card className='border-border/70 shadow-sm'><CardHeader><CardTitle className='flex items-center gap-2'><IconUsersGroup size={20} className='text-sky-600' /> اعضای تیم</CardTitle>
        <CardDescription>انتخاب هر نفر، کارهای واقعی او را باز می‌کند.</CardDescription></CardHeader>
        <CardContent className='max-h-[680px] space-y-2 overflow-y-auto'>{people.map((person) =>
          <button key={person.id} type='button' onClick={() => setPersonId(person.id)} aria-pressed={selectedPersonId === person.id}
            className={`flex w-full items-center gap-3 rounded-xl border p-3 text-right transition-all ${selectedPersonId === person.id ? 'border-sky-500/50 bg-sky-500/10 shadow-sm' : 'border-border/60 hover:border-primary/30 hover:bg-muted/40'}`}>
            <Initials name={person.full_name} /><span className='min-w-0 flex-1'><strong className='block truncate text-sm'>{person.full_name}</strong>
              <span className='text-muted-foreground block truncate text-xs'>{person.team_name || 'بدون تیم'}</span></span>
            <span className='rounded-lg bg-muted px-2 py-1 text-xs font-bold'>{number.format(person.open_tasks)}</span>
          </button>)}{!people.length && <p className='text-muted-foreground py-8 text-center text-sm'>عضوی ثبت نشده است.</p>}
        </CardContent></Card>
      <Card className='border-border/70 shadow-sm'><CardHeader className='border-b border-border/60'>
        <div className='flex flex-wrap items-center justify-between gap-3'><div className='flex items-center gap-3'>
          <Initials name={selectedPerson?.full_name || '؟'} tone='violet' /><div><CardTitle>{selectedPerson?.full_name || 'عضوی انتخاب نشده است'}</CardTitle>
            <CardDescription className='mt-1'>@{selectedPerson?.username || '—'} · {selectedPerson?.team_name || 'بدون تیم'}</CardDescription></div></div>
          {selectedPersonId && <Button size='sm' variant='outline' onClick={() => showTasks({ owner: selectedPersonId })}>همهٔ کارهای این نفر <IconArrowLeft size={15} /></Button>}
        </div></CardHeader>
        <CardContent className='space-y-4 pt-5'>{selectedPerson && <>
          <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>{([
            ['باز', selectedPerson.open_tasks, 'bg-sky-500'], ['منتظر تأیید', selectedPerson.review_tasks, 'bg-amber-500'],
            ['عقب‌افتاده', selectedPerson.overdue_tasks, 'bg-rose-500'], ['تأییدشده', selectedPerson.completed_tasks, 'bg-teal-500']
          ] as const).map(([label, value, color]) => <div key={label} className='rounded-xl border border-border/70 p-3'>
            <span className='text-muted-foreground flex items-center gap-1.5 text-xs'><span className={`size-2 rounded-full ${color}`} />{label}</span>
            <strong className='mt-1 block text-xl'>{number.format(value)}</strong></div>)}</div>
          <div className='flex flex-wrap gap-2'>{selectedPerson.projects.map((project) =>
            <button key={project.site_id} type='button' onClick={() => showTasks({ site: project.site_id, owner: selectedPersonId })}
              className='rounded-full border border-border/70 px-3 py-1.5 text-xs transition-colors hover:border-primary/40 hover:bg-muted'>{project.name} · {project.responsibility === 'lead' ? 'راهبر' : project.responsibility === 'contributor' ? 'مجری' : 'ناظر'}</button>)}
          </div>
          <div><h3 className='mb-2 text-sm font-semibold'>کارهای باز این نفر</h3><div className='max-h-[520px] space-y-2 overflow-y-auto'>{personTasks.map((task) => <button key={task.id} type='button' onClick={() => openTaskPanel(task)}
            className='group flex w-full items-center gap-3 rounded-xl border border-border/70 p-3 text-right transition-colors hover:border-primary/40 hover:bg-muted/30'>
            <span className={`size-2 shrink-0 rounded-full ${task.status === 'review' ? 'bg-amber-500' : task.status === 'blocked' ? 'bg-rose-500' : 'bg-sky-500'}`} />
            <span className='min-w-0 flex-1'><strong className='block truncate text-sm'>{task.title}</strong>
              <span className='text-muted-foreground mt-1 block truncate text-xs'>{task.site_name} · {task.due_at ? `موعد ${formatUserDate(task.due_at, calendar)}` : 'بی‌موعد'} · چک‌لیست {number.format(task.checklist_done)}/{number.format(task.checklist_total)}</span></span>
            <Badge variant='outline'>{statusText[task.status]}</Badge><IconArrowLeft size={16} className='text-muted-foreground opacity-0 group-hover:opacity-100' />
          </button>)}{!personTasks.length && <p className='text-muted-foreground rounded-xl border border-dashed p-5 text-sm'>کار بازی برای این نفر ثبت نشده است.</p>}</div></div>
        </>}</CardContent></Card>
    </div>}

    {section === 'projects' && <Card className='border-border/70 shadow-sm'><CardHeader><CardTitle className='flex items-center gap-2'><IconFolders size={22} className='text-teal-600' /> پروژه‌ها</CardTitle>
      <CardDescription>پیشرفت، راهبر و موارد نیازمند توجه در هر پروژه. از همین‌جا برد یا فهرست کارهای آن را باز کنید.</CardDescription></CardHeader>
      <CardContent className='grid gap-3 md:grid-cols-2 xl:grid-cols-3'>{projectRows.map((project) => <article key={project.site_id}
        className='group rounded-2xl border border-border/70 bg-card p-5 transition-all duration-200 hover:-translate-y-0.5 hover:border-teal-500/40 hover:shadow-md'>
        <div className='flex items-start gap-3'><span className='rounded-xl bg-teal-100 p-2.5 text-teal-700 dark:bg-teal-500/20 dark:text-teal-200'><IconFolders size={21} /></span>
          <span className='min-w-0 flex-1'><strong className='block truncate text-sm'>{project.name}</strong><span className='text-muted-foreground mt-1 block text-xs'>راهبر: {project.lead_name || 'تعیین نشده'} · {number.format(project.members)} عضو</span></span>
          <span className='text-sm font-bold text-teal-700 dark:text-teal-300'>{number.format(project.progress_percent)}٪</span></div>
        <div className='mt-5 h-2 overflow-hidden rounded-full bg-muted'><div className='h-full rounded-full bg-gradient-to-l from-teal-500 to-sky-400 transition-[width] duration-500' style={{ width: `${Math.min(100, project.progress_percent)}%` }} /></div>
        <div className='mt-4 grid grid-cols-3 gap-2 text-center'><div className='rounded-xl bg-muted/50 p-2'><strong className='block text-base'>{number.format(project.open_tasks)}</strong><span className='text-muted-foreground text-[11px]'>کار باز</span></div>
          <div className='rounded-xl bg-rose-500/5 p-2'><strong className='block text-base text-rose-600'>{number.format(project.overdue_tasks)}</strong><span className='text-muted-foreground text-[11px]'>عقب‌افتاده</span></div>
          <div className='rounded-xl bg-violet-500/5 p-2'><strong className='block text-base text-violet-600'>{number.format(project.blocked_tasks)}</strong><span className='text-muted-foreground text-[11px]'>مانع‌دار</span></div></div>
        <div className='mt-4 flex flex-wrap gap-2'><Button size='sm' variant='outline' onClick={() => showTasks({ site: project.site_id })}>فهرست کارها</Button>
          <Link href={`/dashboard/work?view=kanban&site=${encodeURIComponent(project.site_id)}`} className='inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted'>برد پروژه <IconArrowLeft size={14} /></Link></div>
      </article>)}{!projectRows.length && <p className='text-muted-foreground text-sm'>پروژه‌ای ثبت نشده است.</p>}
      </CardContent></Card>}

    {section === 'gantt' && openWork && <ManagerGantt items={openWork.items} total={openWork.total} calendar={calendar} onTask={openTaskPanel} />}

    {section === 'tasks' && <Card><CardHeader><CardTitle>فهرست کامل تسک‌ها</CardTitle>
      <CardDescription>نتیجه‌ها صفحه‌بندی می‌شوند؛ فیلترها فقط روی این فهرست اعمال می‌شوند و شاخص‌های بالای صفحه همچنان کل تیم را نشان می‌دهند.</CardDescription></CardHeader>
      <CardContent className='space-y-3'><div className='grid gap-2 md:grid-cols-2 xl:grid-cols-6'>
        <Input aria-label='جست‌وجوی کار' placeholder='عنوان، پروژه یا مسئول…' value={search} onChange={(event) => setSearch(event.target.value)} />
        <NativeSelect aria-label='پروژه' value={siteId} onChange={(event) => { setSiteId(event.target.value); setOffset(0); }}><NativeSelectOption value=''>همهٔ پروژه‌ها</NativeSelectOption>
          {projects.map((project) => <NativeSelectOption key={project.site_id} value={project.site_id}>{project.name}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect aria-label='مسئول' value={ownerId} onChange={(event) => { setOwnerId(event.target.value); setOffset(0); }}><NativeSelectOption value=''>همهٔ مسئولان</NativeSelectOption>
          {people.map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect aria-label='تیم' value={teamId} onChange={(event) => { setTeamId(event.target.value); setOffset(0); }}><NativeSelectOption value=''>همهٔ تیم‌ها</NativeSelectOption>
          {teams.map(([id, name]) => <NativeSelectOption key={id} value={String(id)}>{name}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect aria-label='وضعیت کار' value={focus} onChange={(event) => { setFocus(event.target.value as typeof focus); setStatusFilter(undefined); setOffset(0); }}>
          {focusOptions.map((option) => <NativeSelectOption key={option.value} value={option.value}>{option.label}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect aria-label='مرحلهٔ دقیق' value={statusFilter || ''} onChange={(event) => { setStatusFilter((event.target.value || undefined) as ManagementTaskFilters['status']); setFocus('all'); setOffset(0); }}>
          <NativeSelectOption value=''>همهٔ مراحل</NativeSelectOption>
          {Object.entries(statusText).map(([value, label]) => <NativeSelectOption key={value} value={value}>{label}</NativeSelectOption>)}</NativeSelect>
      </div><div className='flex items-center justify-between gap-2 text-xs'><span>{number.format(ledger?.total || 0)} نتیجه {ledgerLoading ? '· در حال بارگیری…' : ''}</span>
        <Button size='sm' variant='ghost' onClick={() => { setSiteId(''); setOwnerId(''); setTeamId(''); setSearch(''); setFocus('open'); setStatusFilter(undefined); setOffset(0); }}>پاک‌کردن فیلترها</Button></div>
      <div className='overflow-x-auto rounded-xl border'><table className='w-full min-w-[900px] text-right text-xs'><thead className='bg-muted/50'><tr>
        <th className='p-3'>تسک / پروژه</th><th>مسئول</th><th>مرحله</th><th>اولویت</th><th>موعد</th><th>پیشرفت</th><th>کارت</th>
      </tr></thead><tbody>{ledger?.items.map((task) => <tr key={task.id} className='border-t hover:bg-muted/30'>
        <td className='max-w-[300px] p-3'><strong className='block truncate'>{task.title}</strong><span className='text-muted-foreground block truncate'>{task.site_name}</span></td>
        <td>{task.owner_name || 'بی‌مسئول'}</td><td><Badge variant='outline'>{statusText[task.status]}</Badge></td><td>{priorityText[task.priority]}</td>
        <td>{task.due_at ? formatUserDate(task.due_at, calendar) : 'بی‌موعد'}</td>
        <td>{number.format(task.status === 'verified' ? 100 : task.progress_percent)}٪ · {number.format(task.checklist_done)}/{number.format(task.checklist_total)}</td>
        <td><button type='button' onClick={() => openTaskPanel(task)} className='text-primary hover:underline'>بازبینی</button></td>
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

    <Dialog open={panelTaskId !== null} onOpenChange={(open) => { if (!open) closeTaskPanel(); }}>
      <DialogContent className='max-h-[94vh] overflow-y-auto sm:max-w-6xl' dir='rtl'>
        <DialogHeader className='border-b border-border/60 pb-4 pr-10'>
          <DialogTitle className='text-lg font-bold leading-7'>{panelTask?.title || 'در حال دریافت جزئیات کار…'}</DialogTitle>
          <DialogDescription>{panelTask ? `${panelTask.site_name} · مسئول: ${panelTask.owner_name || 'بی‌مسئول'} · سازنده: ${panelTask.created_by_name || 'سیستم'}` : 'اطلاعات کار در همین صفحه باز می‌شود.'}</DialogDescription>
        </DialogHeader>
        {panelTask ? <div className='grid gap-4 md:grid-cols-[minmax(0,0.88fr)_minmax(0,1.12fr)]'>
          <section className='space-y-4 md:max-h-[65vh] md:overflow-y-auto md:pl-1' aria-label='جزئیات کار'>
            <div className='flex flex-wrap gap-2'><Badge variant='outline' className={panelTask.status === 'review' ? 'border-amber-400 bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-200' : ''}>{statusText[panelTask.status] || panelTask.status}</Badge>
              <Badge variant='outline'>اولویت: {priorityText[panelTask.priority]}</Badge>
              <Badge variant='secondary'>پیشرفت {number.format(panelTask.progress_percent)}٪</Badge></div>
            <div className='rounded-2xl border border-border/70 bg-muted/20 p-4'><h3 className='text-sm font-semibold'>شرح و نتیجهٔ مورد انتظار</h3>
              <p className='mt-2 whitespace-pre-wrap break-words text-sm leading-7'>{panelTask.description || 'توضیحی برای این کار ثبت نشده است.'}</p></div>
            <div className='grid gap-2 sm:grid-cols-2'>{([
              ['موعد', panelTask.due_at ? formatUserDateTime(panelTask.due_at, calendar) : 'ثبت نشده'],
              ['شروع', panelTask.start_at ? formatUserDateTime(panelTask.start_at, calendar) : 'ثبت نشده'],
              ['چک‌لیست', `${number.format(panelTask.checklist_done)} از ${number.format(panelTask.checklist_total)} انجام‌شده`],
              ['آخرین تغییر', formatUserDateTime(panelTask.updated_at, calendar)]
            ] as const).map(([label, value]) => <div key={label} className='rounded-xl border border-border/70 p-3 text-xs'>
              <span className='text-muted-foreground block'>{label}</span><strong className='mt-1 block font-medium'>{value}</strong></div>)}</div>
            {panelTask.verification_note && <div className='rounded-xl border border-teal-500/30 bg-teal-500/5 p-3 text-sm'><strong className='block text-xs'>مدرک یا نتیجهٔ ثبت‌شده</strong>
              <p className='mt-1 whitespace-pre-wrap break-words leading-6'>{panelTask.verification_note}</p></div>}
            {panelTask.blocked_reason && <div className='rounded-xl border border-rose-500/30 bg-rose-500/5 p-3 text-sm'><strong className='block text-xs'>دلیل مانع</strong>
              <p className='mt-1 whitespace-pre-wrap break-words leading-6'>{panelTask.blocked_reason}</p></div>}
            <Link href={taskUrl(panelTask)} className='text-muted-foreground inline-flex items-center gap-1 text-xs underline-offset-4 hover:text-primary hover:underline'>باز کردن ویرایشگر کامل تسک <IconArrowLeft size={14} /></Link>
          </section>
          <div className='md:max-h-[65vh] md:overflow-y-auto md:pl-1'>
            <TaskDiscussion key={panelTask.id} item={panelTask} embedded canEdit={false} canComment canModerate meId={null}
              onChanged={() => setRevision((current) => current + 1)} />
          </div>
        </div> : <div className='rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground'>در حال دریافت جزئیات و گفت‌وگو…</div>}
        {panelTask?.status === 'review' && <div className='sticky -bottom-4 -mx-4 -mb-4 space-y-3 border-t bg-popover/95 p-4 shadow-[0_-8px_24px_rgba(0,0,0,.06)] backdrop-blur'>
          <div className='flex flex-wrap items-center justify-between gap-2'><strong className='text-sm'>تصمیم بازبینی</strong>
            <span className='text-muted-foreground text-xs'>برای گفت‌وگو با مسئول، از کادر پیام بالا استفاده کنید.</span></div>
          <Textarea aria-label='یادداشت تصمیم بازبینی' rows={2} maxLength={2000} value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)}
            placeholder='یادداشت تأیید اختیاری است؛ برای درخواست اصلاح، دلیل را همین‌جا بنویسید.' />
          <div className='flex flex-wrap items-center gap-2'><Button disabled={decisionBusy || panelLoading} onClick={() => void saveDecision('approve')}>
            {decisionBusy ? 'در حال ثبت…' : 'تأیید نتیجه'}</Button>
            <Button variant='outline' disabled={decisionBusy || panelLoading || decisionNote.trim().length < 3} onClick={() => void saveDecision('changes_requested')}>درخواست اصلاح با دلیل</Button>
            <span className='text-muted-foreground text-xs'>تصمیم و توضیح آن برای مسئول ثبت و اعلان می‌شود.</span></div>
        </div>}
      </DialogContent>
    </Dialog>
  </div>;
}
