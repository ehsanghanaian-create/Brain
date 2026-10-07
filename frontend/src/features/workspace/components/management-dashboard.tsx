'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { formatUserDate, formatUserDateTime, useDatePreference } from '@/lib/date-preference';
import { commandApi, type ManagementOverview, type ManagementTask, type ManagementTaskFilters,
  type ManagementTaskLedger, type ProjectSummary, type WorkPriority, type WorkReport } from '../api';
import type { WorkStatus } from '@/features/reports/types';

const number = new Intl.NumberFormat('fa-IR');
const openStatuses = new Set(['new', 'triaged', 'approved', 'assigned', 'in_progress', 'review',
  'published', 'measurement_pending', 'blocked']);
const statusLabels: Record<WorkStatus, string> = {
  new: 'جدید', triaged: 'بررسی', approved: 'آمادهٔ اجرا', assigned: 'واگذارشده',
  in_progress: 'در حال اجرا', review: 'بازبینی', published: 'منتشرشده',
  measurement_pending: 'در انتظار سنجش', blocked: 'مسدود', verified: 'تکمیل‌شده',
  rejected: 'ردشده', deferred: 'تعویق'
};
const priorityLabels: Record<WorkPriority, string> = {
  critical: 'فوری', high: 'بالا', normal: 'معمولی', low: 'کم'
};
const focusOptions: { value: NonNullable<ManagementTaskFilters['focus']>; label: string }[] = [
  { value: 'open', label: 'کارهای باز' }, { value: 'all', label: 'همهٔ کارها' },
  { value: 'overdue', label: 'عقب‌افتاده' }, { value: 'due_week', label: 'موعد ۷ روز آینده' },
  { value: 'blocked', label: 'مسدود' }, { value: 'unassigned', label: 'بی‌مسئول' },
  { value: 'unscheduled', label: 'بی‌موعد' }, { value: 'completed', label: 'تکمیل‌شده' }
];
const activityLabels: Record<string, string> = {
  created: 'ایجاد کرد', updated: 'ویرایش کرد', deleted: 'به آرشیو برد',
  restored: 'بازیابی کرد', comment: 'پیام گذاشت', handoff: 'ارجاع داد',
  checklist_updated: 'چک‌لیست را تغییر داد'
};

function dayIndex(value: string, origin: string): number {
  return Math.round((Date.parse(value.slice(0, 10) + 'T00:00:00Z') -
    Date.parse(origin + 'T00:00:00Z')) / 86_400_000);
}

function taskUrl(task: ManagementTask): string {
  return `/dashboard/work?site=${encodeURIComponent(task.site_id)}&task=${task.id}`;
}

function Timeline({ items, horizon, calendar, onHorizonChange }: {
  items: ManagementTask[]; horizon: number; calendar: ReturnType<typeof useDatePreference>['calendar'];
  onHorizonChange: (days: number) => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const rows = items.filter((item) => item.due_at && openStatuses.has(item.status) &&
    dayIndex(item.due_at, today) >= 0 && dayIndex(item.due_at, today) <= horizon)
    .toSorted((a, b) => (a.owner_name || 'zzz').localeCompare(b.owner_name || 'zzz') ||
      (a.due_at || '').localeCompare(b.due_at || ''));
  const firstUnscheduled = items.find((item) => openStatuses.has(item.status) && !item.due_at);
  const markers = [0, .25, .5, .75, 1].map((fraction) => {
    const date = new Date(Date.parse(today + 'T00:00:00Z') + Math.round(horizon * fraction) * 86_400_000);
    return formatUserDate(date.toISOString(), calendar);
  });
  return <Card>
    <CardHeader><CardTitle>جزئیات زمان‌بندی این صفحه</CardTitle>
      <CardDescription>موعد کارهای همین صفحه در {number.format(horizon)} روز آینده. نوار فقط وقتی نمایش داده می‌شود که تاریخ شروع ثبت شده باشد؛ در غیر این صورت نشانگر، موعد کار است.</CardDescription>
    </CardHeader>
    <CardContent>
      <div className='mb-3 flex gap-2'>
        <Button size='sm' variant={horizon === 35 ? 'default' : 'outline'} onClick={() => onHorizonChange(35)}>۵ هفته</Button>
        <Button size='sm' variant={horizon === 91 ? 'default' : 'outline'} onClick={() => onHorizonChange(91)}>۱۳ هفته</Button>
      </div>
      {rows.length ? <div className='max-h-[460px] overflow-auto rounded-xl border'>
        <div className='min-w-[800px]'>
          <div className='grid grid-cols-[250px_minmax(550px,1fr)] border-b bg-muted/40 text-xs'>
            <span className='p-3'>مسئول · کار · پروژه</span>
            <div className='flex items-center justify-between px-3' dir='ltr'>{markers.map((marker, index) => <span key={index}>{marker}</span>)}</div>
          </div>
          {rows.map((task) => {
            const due = dayIndex(task.due_at!, today);
            const start = task.start_at ? dayIndex(task.start_at, today) : null;
            const left = Math.max(0, Math.min(100, due / horizon * 100));
            const first = start !== null && start <= due ? Math.max(0, start / horizon * 100) : left;
            const width = start !== null && start <= due ? Math.max(0.8, left - first) : 0;
            return <div key={task.id} className='grid grid-cols-[250px_minmax(550px,1fr)] border-b last:border-b-0 hover:bg-muted/30'>
              <Link href={`/dashboard/work?site=${encodeURIComponent(task.site_id)}&task=${task.id}`} className='min-w-0 p-2.5 text-xs hover:text-primary'>
                <strong className='block truncate'>{task.title}</strong>
                <span className='text-muted-foreground block truncate'>{task.owner_name || 'بی‌مسئول'} · {task.site_name}</span>
              </Link>
              <div className='relative mx-3 my-2.5 h-8 rounded-md bg-muted/30' dir='ltr'
                style={{ backgroundImage: 'linear-gradient(to right, transparent 24.8%, var(--border) 25%, transparent 25.2%, transparent 49.8%, var(--border) 50%, transparent 50.2%, transparent 74.8%, var(--border) 75%, transparent 75.2%)' }}>
                {width > 0 && <span className='absolute top-3 h-2 rounded-full bg-sky-500/70'
                  style={{ left: `${first}%`, width: `${width}%` }} />}
                <span className='absolute top-1.5 size-5 -translate-x-1/2 rounded-full border-2 border-background bg-sky-600 shadow-sm'
                  style={{ left: `${left}%` }} title={`موعد: ${formatUserDate(task.due_at!, calendar)}`} />
              </div>
            </div>;
          })}
        </div>
      </div> : <div className='text-muted-foreground rounded-xl border border-dashed p-7 text-center text-sm'>برای کارهای این صفحه در بازهٔ انتخابی موعدی ثبت نشده است.
        {firstUnscheduled && <Link href={taskUrl(firstUnscheduled)} className='text-primary mt-2 block hover:underline'>باز کردن «{firstUnscheduled.title}» و تعیین موعد</Link>}
      </div>}
    </CardContent>
  </Card>;
}

function PortfolioMatrix({ ledger, people, projects, weeks, calendar, onWeeksChange,
  onPersonSelect, onProjectSelect }: {
  ledger: ManagementTaskLedger; people: ManagementOverview['people']; projects: ProjectSummary[];
  weeks: number; calendar: ReturnType<typeof useDatePreference>['calendar'];
  onWeeksChange: (weeks: number) => void;
  onPersonSelect: (id: number | null, focus?: 'overdue' | 'unscheduled') => void;
  onProjectSelect: (siteId: string, focus?: 'overdue' | 'unscheduled') => void;
}) {
  const [groupBy, setGroupBy] = useState<'person' | 'project'>('person');
  const rows = useMemo(() => {
    const grouped = new Map<string, { key: string; label: string; personId: number | null;
      siteId: string | null; counts: number[]; overdue: number; unscheduled: number; total: number }>();
    for (const point of ledger.timeline) {
      const key = groupBy === 'person' ? `person:${point.user_id ?? 'none'}` : `project:${point.site_id}`;
      const label = groupBy === 'person'
        ? people.find((person) => person.id === point.user_id)?.full_name || 'بی‌مسئول'
        : projects.find((project) => project.site_id === point.site_id)?.name || point.site_id;
      const row = grouped.get(key) || { key, label, personId: point.user_id,
        siteId: groupBy === 'project' ? point.site_id : null, counts: Array(13).fill(0) as number[],
        overdue: 0, unscheduled: 0, total: 0 };
      if (point.week_index >= 0 && point.week_index < 13) {
        row.counts[point.week_index] += point.count;
      } else if (point.week_index === -1) row.overdue += point.count;
      else if (point.week_index === -2) row.unscheduled += point.count;
      row.total += point.count;
      grouped.set(key, row);
    }
    return [...grouped.values()].toSorted((a, b) => b.total - a.total || a.label.localeCompare(b.label));
  }, [ledger.timeline, groupBy, people, projects]);
  const today = new Date().toISOString().slice(0, 10);
  const choose = (row: (typeof rows)[number], focus?: 'overdue' | 'unscheduled') =>
    groupBy === 'person' ? onPersonSelect(row.personId, focus) : onProjectSelect(row.siteId!, focus);
  return <Card><CardHeader className='flex flex-row flex-wrap items-start justify-between gap-3'>
    <div><CardTitle>نقشهٔ زمان‌بندی کل تیم</CardTitle>
      <CardDescription className='mt-1'>همهٔ تسک‌های باز، مستقل از صفحه‌بندی جدول؛ عقب‌افتاده‌ها و کارهای بی‌موعد نیز کنار هفته‌ها دیده می‌شوند.</CardDescription></div>
    <div className='flex flex-wrap gap-1.5'>
      <Button size='sm' variant={groupBy === 'person' ? 'default' : 'outline'} onClick={() => setGroupBy('person')}>بر اساس نفر</Button>
      <Button size='sm' variant={groupBy === 'project' ? 'default' : 'outline'} onClick={() => setGroupBy('project')}>بر اساس پروژه</Button>
      <Button size='sm' variant={weeks === 5 ? 'default' : 'outline'} onClick={() => onWeeksChange(5)}>۵ هفته</Button>
      <Button size='sm' variant={weeks === 13 ? 'default' : 'outline'} onClick={() => onWeeksChange(13)}>۱۳ هفته</Button>
    </div></CardHeader>
    <CardContent>{rows.length ? <div className='overflow-x-auto rounded-xl border'>
      <div className='min-w-[950px]'>
        <div className='grid items-center border-b bg-muted/40 text-[11px]'
          style={{ gridTemplateColumns: `180px 75px repeat(${weeks}, minmax(42px, 1fr)) 75px 65px` }}>
          <span className='p-2'>مسئول / پروژه</span>
          <span className='text-center text-rose-600'>گذشته</span>
          {Array.from({ length: weeks }, (_, index) => {
            const date = new Date(Date.parse(today + 'T00:00:00Z') + index * 7 * 86_400_000);
            return <span key={index} className='text-center'>{formatUserDate(date.toISOString(), calendar)}</span>;
          })}
          <span className='text-center text-amber-600'>بی‌موعد</span>
          <span className='text-center'>جمع</span>
        </div>
        <div className='max-h-[420px] overflow-y-auto'>{rows.map((row) =>
          <div key={row.key} className='grid items-center border-b last:border-0 hover:bg-muted/30'
            style={{ gridTemplateColumns: `180px 75px repeat(${weeks}, minmax(42px, 1fr)) 75px 65px` }}>
            <button type='button' className='truncate p-2 text-right text-xs font-medium hover:text-primary'
              title={row.label} onClick={() => choose(row)}>
              {row.label}
            </button>
            <button type='button' disabled={!row.overdue} onClick={() => choose(row, 'overdue')}
              className='m-1 rounded-md bg-rose-500/10 py-2 text-center text-xs text-rose-600 enabled:hover:bg-rose-500/20'>
              {row.overdue ? number.format(row.overdue) : '·'}
            </button>
            {row.counts.slice(0, weeks).map((count, index) =>
              <button key={index} type='button' disabled={!count}
                title={`${row.label}: ${count} موعد در هفتهٔ ${index + 1}`}
                onClick={() => choose(row)}
                className={`m-1 rounded-md py-2 text-center text-xs tabular-nums transition-transform enabled:hover:scale-105
                  ${count >= 5 ? 'bg-sky-600 text-white' : count >= 3 ? 'bg-sky-500/60 text-foreground' :
                    count ? 'bg-sky-500/20 text-sky-700 dark:text-sky-200' : 'text-muted-foreground/50'}`}>
                {count ? number.format(count) : '·'}
              </button>)}
            <button type='button' disabled={!row.unscheduled} onClick={() => choose(row, 'unscheduled')}
              className='m-1 rounded-md bg-amber-500/10 py-2 text-center text-xs text-amber-600 enabled:hover:bg-amber-500/20'>
              {row.unscheduled ? number.format(row.unscheduled) : '·'}
            </button>
            <strong className='text-center text-xs'>{number.format(row.overdue + row.unscheduled +
              row.counts.slice(0, weeks).reduce((sum, value) => sum + value, 0))}</strong>
          </div>)}</div>
      </div>
    </div> : <p className='text-muted-foreground rounded-xl border border-dashed p-7 text-center text-sm'>کاری در محدودهٔ فیلترها ثبت نشده است.</p>}
    </CardContent>
  </Card>;
}

export function ManagementDashboard() {
  const { calendar } = useDatePreference();
  const [overview, setOverview] = useState<ManagementOverview | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [report, setReport] = useState<WorkReport | null>(null);
  const [ledger, setLedger] = useState<ManagementTaskLedger | null>(null);
  const [teamId, setTeamId] = useState('');
  const [ownerId, setOwnerId] = useState('');
  const [siteId, setSiteId] = useState('');
  const [focus, setFocus] = useState<NonNullable<ManagementTaskFilters['focus']>>('open');
  const [priority, setPriority] = useState<WorkPriority | ''>('');
  const [status, setStatus] = useState<WorkStatus | ''>('');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [period, setPeriod] = useState<'week' | 'month'>('week');
  const [horizon, setHorizon] = useState(35);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [ledgerLoading, setLedgerLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const timer = window.setTimeout(() => { setQuery(search.trim()); setOffset(0); }, 350);
    return () => window.clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    void Promise.all([commandApi.management(), commandApi.projects()]).then(([team, projectRows]) => {
      if (active) { setOverview(team); setProjects(projectRows); setError(''); }
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : 'داشبورد مدیریت بارگیری نشد');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);
  useEffect(() => {
    let active = true;
    void commandApi.report(period, new Date().toISOString().slice(0, 10)).then((value) => {
      if (active) setReport(value);
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : 'گزارش فعالیت بارگیری نشد');
    });
    return () => { active = false; };
  }, [period, revision]);
  useEffect(() => {
    let active = true;
    setLedgerLoading(true);
    void commandApi.managementTasks({
      site_id: siteId || undefined, owner_id: ownerId ? Number(ownerId) : undefined,
      team_id: teamId ? Number(teamId) : undefined, priority: priority || undefined,
      status: status || undefined, focus, q: query || undefined, offset, limit: 100
    }).then((value) => {
      if (active) { setLedger(value); setError(''); }
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : 'فهرست کارهای تیم بارگیری نشد');
    }).finally(() => { if (active) setLedgerLoading(false); });
    return () => { active = false; };
  }, [siteId, ownerId, teamId, priority, status, focus, query, offset, revision]);

  const teams = useMemo(() => Array.from(new Map((overview?.people || [])
    .filter((person) => person.team_id && person.team_name)
    .map((person) => [person.team_id!, person.team_name!] as const)).entries()), [overview]);
  const people = useMemo(() => (overview?.people || []).filter((person) =>
    (!teamId || String(person.team_id) === teamId) &&
    (!siteId || person.projects.some((project) => project.site_id === siteId) ||
      ledger?.workload.some((row) => row.user_id === person.id))), [overview, teamId, siteId, ledger]);
  const workload = useMemo(() => new Map((ledger?.workload || []).map((row) => [row.user_id, row])), [ledger]);
  const activity = useMemo(() => new Map((report?.by_person || []).map((row) => [row.user_id, row])), [report]);
  const visibleProjects = useMemo(() => [...projects].filter((project) => !siteId || project.site_id === siteId)
    .toSorted((a, b) => b.overdue_tasks - a.overdue_tasks || b.open_tasks - a.open_tasks), [projects, siteId]);
  const chartPeople = useMemo(() => (ledger?.workload || []).filter((row) => row.user_id !== null)
    .slice(0, 12), [ledger]);
  const selectedPerson = overview?.people.find((person) => String(person.id) === ownerId);
  const resetOffset = () => setOffset(0);
  const summary = overview?.summary;

  return <div className='space-y-5' dir='rtl'>
    <section className='flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-sky-500/20 bg-gradient-to-l from-sky-500/10 via-background to-violet-500/10 p-5'>
      <div><Badge variant='outline'>فقط حساب مدیر کل</Badge>
        <h2 className='mt-2 text-2xl font-bold'>اتاق مدیریت اجرای تیم</h2>
        <p className='text-muted-foreground mt-1 text-sm'>از کل پروژه‌ها تا مسئول، مرحله، موعد و سابقهٔ هر تسک در یک مسیر قابل پیگیری.</p>
      </div>
      <div className='flex flex-wrap gap-2'>
        <Button variant='outline' disabled={loading || ledgerLoading} onClick={() => setRevision((value) => value + 1)}>به‌روزرسانی داده‌ها</Button>
        <Link href='/dashboard/users' className={buttonVariants({ variant: 'outline' })}>مدیریت اعضا</Link>
        <Link href='/dashboard/work?view=teams' className={buttonVariants()}>میز عملیات</Link>
      </div>
    </section>
    {error && <div role='alert' className='rounded-xl border border-rose-500/40 p-3 text-sm text-rose-600'>{error}</div>}
    {!overview && loading && <p className='rounded-xl border p-12 text-center text-muted-foreground'>در حال بارگیری تصویر تیم…</p>}
    {summary && <section className='grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6' aria-label='وضعیت کل تیم'>
      {([['همکار فعال', summary.active_people], ['کل تسک‌ها', summary.total_tasks],
        ['کار باز', summary.open_tasks], ['عقب‌افتاده', summary.overdue_tasks],
        ['مسدود', summary.blocked_tasks], ['بی‌مسئول', summary.unassigned_tasks]] as const)
        .map(([label, value]) => <Card key={label}><CardContent className='p-4'>
          <span className='text-muted-foreground text-xs'>{label}</span>
          <strong className='mt-2 block text-2xl tabular-nums'>{number.format(value)}</strong>
        </CardContent></Card>)}
    </section>}

    <Card><CardHeader><CardTitle>همهٔ کارها، با یک فیلتر مشترک</CardTitle>
      <CardDescription>فیلترها روی بار کاری، موعدها و تسک‌ها اعمال می‌شوند؛ نوع فهرست فقط جدول را محدود می‌کند. شاخص‌ها و نمودار فعالیتِ کل تیم مستقل از فیلترها هستند.</CardDescription></CardHeader>
      <CardContent className='space-y-3'>
        <div className='grid gap-2 md:grid-cols-2 xl:grid-cols-4'>
          <Input aria-label='جست‌وجوی تسک' placeholder='جست‌وجو در کار، پروژه، مسئول…' value={search} onChange={(event) => setSearch(event.target.value)} />
          <NativeSelect aria-label='پروژه' value={siteId} onChange={(event) => { setSiteId(event.target.value); resetOffset(); }}>
            <NativeSelectOption value=''>همهٔ پروژه‌ها</NativeSelectOption>
            {projects.map((project) => <NativeSelectOption key={project.site_id} value={project.site_id}>{project.name}</NativeSelectOption>)}
          </NativeSelect>
          <NativeSelect aria-label='تیم' value={teamId} onChange={(event) => { setTeamId(event.target.value); setOwnerId(''); resetOffset(); }}>
            <NativeSelectOption value=''>همهٔ تیم‌ها</NativeSelectOption>
            {teams.map(([id, name]) => <NativeSelectOption key={id} value={String(id)}>{name}</NativeSelectOption>)}
          </NativeSelect>
          <NativeSelect aria-label='مسئول' value={ownerId} onChange={(event) => { setOwnerId(event.target.value); resetOffset(); }}>
            <NativeSelectOption value=''>همهٔ مسئولان</NativeSelectOption>
            {people.map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}
          </NativeSelect>
          <NativeSelect aria-label='نوع فهرست' value={focus} onChange={(event) => { setFocus(event.target.value as typeof focus); setStatus(''); resetOffset(); }}>
            {focusOptions.map((option) => <NativeSelectOption key={option.value} value={option.value}>{option.label}</NativeSelectOption>)}
          </NativeSelect>
          <NativeSelect aria-label='مرحلهٔ کار' value={status} onChange={(event) => {
            const value = event.target.value as WorkStatus | '';
            setStatus(value);
            if (value && !openStatuses.has(value)) setFocus('all');
            resetOffset();
          }}>
            <NativeSelectOption value=''>همهٔ مرحله‌ها</NativeSelectOption>
            {Object.entries(statusLabels).map(([key, label]) => <NativeSelectOption key={key} value={key}>{label}</NativeSelectOption>)}
          </NativeSelect>
          <NativeSelect aria-label='اولویت' value={priority} onChange={(event) => { setPriority(event.target.value as WorkPriority | ''); resetOffset(); }}>
            <NativeSelectOption value=''>همهٔ اولویت‌ها</NativeSelectOption>
            {Object.entries(priorityLabels).map(([key, label]) => <NativeSelectOption key={key} value={key}>{label}</NativeSelectOption>)}
          </NativeSelect>
          <Button variant='outline' onClick={() => { setSiteId(''); setTeamId(''); setOwnerId(''); setFocus('open'); setStatus(''); setPriority(''); setSearch(''); setQuery(''); resetOffset(); }}>پاک‌کردن فیلترها</Button>
        </div>
        <div className='flex flex-wrap items-center gap-2 text-xs'>
          <Badge variant='secondary'>{number.format(ledger?.total || 0)} کار در فهرست</Badge>
          {selectedPerson && <span className='text-muted-foreground'>مسئول: {selectedPerson.full_name}</span>}
          {siteId && <span className='text-muted-foreground'>پروژه: {projects.find((project) => project.site_id === siteId)?.name}</span>}
          {ledgerLoading && <span className='text-muted-foreground'>در حال اعمال فیلتر…</span>}
        </div>
      </CardContent>
    </Card>

    {ledger && <section className='grid grid-cols-2 gap-2 md:grid-cols-5' aria-label='برنامهٔ موعدها'>
      {([['عقب‌افتاده', ledger.schedule.overdue, 'overdue'], ['۷ روز آینده', ledger.schedule.due_week, 'due_week'],
        ['۸ تا ۳۰ روز', ledger.schedule.due_month, 'open'], ['بعد از ۳۰ روز', ledger.schedule.later, 'open'],
        ['بی‌موعد', ledger.schedule.unscheduled, 'unscheduled']] as const).map(([label, count, target]) =>
        <button key={label} type='button' onClick={() => { setFocus(target); setStatus(''); resetOffset(); }}
          className='rounded-xl border p-3 text-right transition-colors hover:border-sky-500/50 hover:bg-muted/40'>
          <span className='text-muted-foreground block text-xs'>{label}</span>
          <strong className={`mt-1 block text-xl ${label === 'عقب‌افتاده' && count ? 'text-rose-600' : ''}`}>{number.format(count)}</strong>
        </button>)}
    </section>}

    <section className='grid gap-4 xl:grid-cols-2'>
      <Card><CardHeader><CardTitle>بار کاری به تفکیک مسئول</CardTitle>
        <CardDescription>تعداد تسک‌های باز، عقب‌افتاده و مسدود در محدودهٔ فیلترها.</CardDescription></CardHeader>
        <CardContent className='h-72' dir='ltr'>
          {chartPeople.length ? <ResponsiveContainer width='100%' height='100%'><BarChart data={chartPeople} layout='vertical' margin={{ left: 10, right: 14 }}>
            <CartesianGrid strokeDasharray='3 3' opacity={.2} /><XAxis type='number' allowDecimals={false} />
            <YAxis dataKey='name' type='category' width={95} tick={{ fontSize: 11 }} /><Tooltip /><Legend />
            <Bar dataKey='open' name='باز' fill='#0ea5e9' radius={[0, 4, 4, 0]} />
            <Bar dataKey='overdue' name='عقب‌افتاده' fill='#f43f5e' radius={[0, 4, 4, 0]} />
            <Bar dataKey='blocked' name='مسدود' fill='#f59e0b' radius={[0, 4, 4, 0]} />
          </BarChart></ResponsiveContainer> : <p className='text-muted-foreground py-24 text-center text-sm'>کاری در این محدوده ثبت نشده است.</p>}
        </CardContent></Card>
      <Card><CardHeader className='flex flex-row flex-wrap items-start justify-between gap-3'><div>
        <CardTitle>روند واقعی انجام کار</CardTitle><CardDescription className='mt-1'>از رویدادهای ثبت‌شده؛ ایجاد و تکمیل تسک‌ها.</CardDescription></div>
        <NativeSelect aria-label='بازهٔ گزارش فعالیت' value={period} onChange={(event) => setPeriod(event.target.value as 'week' | 'month')} className='w-32'>
          <NativeSelectOption value='week'>این هفته</NativeSelectOption><NativeSelectOption value='month'>این ماه</NativeSelectOption>
        </NativeSelect></CardHeader>
        <CardContent className='h-72' dir='ltr'>
          {report?.daily.length ? <ResponsiveContainer width='100%' height='100%'><AreaChart data={report.daily} margin={{ left: 6, right: 10 }}>
            <CartesianGrid strokeDasharray='3 3' opacity={.2} /><XAxis dataKey='day' tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} />
            <Tooltip /><Legend /><Area dataKey='created' name='ایجاد' stroke='#6366f1' fill='#6366f1' fillOpacity={.13} />
            <Area dataKey='completed' name='تکمیل' stroke='#10b981' fill='#10b981' fillOpacity={.16} />
          </AreaChart></ResponsiveContainer> : <p className='text-muted-foreground py-24 text-center text-sm'>در این بازه رویدادی ثبت نشده است.</p>}
        </CardContent></Card>
    </section>

    {ledger && <Card><CardHeader><CardTitle>مرحله‌های جریان کار</CardTitle>
      <CardDescription>از تمام تسک‌های محدودهٔ فیلترها، شامل کارهای تکمیل‌شده؛ انتخاب هر مرحله فهرست را محدود می‌کند.</CardDescription></CardHeader>
      <CardContent className='flex flex-wrap gap-2'>{ledger.stages.map((stage) =>
        <button key={stage.key} type='button' onClick={() => { setStatus(stage.key); setFocus('all'); resetOffset(); }}
          className={`rounded-lg border px-3 py-2 text-xs transition-colors hover:bg-muted ${status === stage.key ? 'border-sky-500 bg-sky-500/10' : ''}`}>
          {statusLabels[stage.key]} <strong className='mr-1'>{number.format(stage.count)}</strong>
        </button>)}
        {!ledger.stages.length && <span className='text-muted-foreground text-sm'>هنوز کاری ثبت نشده است.</span>}
      </CardContent></Card>}

    <Card><CardHeader><CardTitle>جدول مسئولیت‌های تیم</CardTitle>
      <CardDescription>تسک‌های هر نفر در محدودهٔ فیلترها؛ فعالیت و زمان ثبت‌شده از گزارش {period === 'week' ? 'هفتگی' : 'ماهانه'}.</CardDescription></CardHeader>
      <CardContent className='overflow-x-auto'><table className='w-full min-w-[940px] text-right text-xs'>
        <thead className='bg-muted/50'><tr><th className='rounded-r-lg p-3'>عضو تیم</th><th>پروژه‌ها</th><th>باز</th><th>عقب‌افتاده</th><th>مسدود</th><th>بی‌موعد</th><th>انجام‌شده</th><th>فعالیت</th><th>زمان ثبت‌شده</th><th>آخرین تغییر</th><th>پیگیری</th></tr></thead>
        <tbody>{people.map((person) => {
          const work = workload.get(person.id);
          const workActivity = activity.get(person.id);
          return <tr key={person.id} className='border-t hover:bg-muted/30'>
            <td className='p-3'><strong className='block'>{person.full_name}</strong><span className='text-muted-foreground'>@{person.username} · {person.team_name || 'بدون تیم'}</span></td>
            <td>{number.format(person.projects.length)}</td><td className='font-semibold'>{number.format(work?.open || 0)}</td>
            <td className={work?.overdue ? 'font-semibold text-rose-600' : ''}>{number.format(work?.overdue || 0)}</td>
            <td>{number.format(work?.blocked || 0)}</td><td>{number.format(work?.unscheduled || 0)}</td>
            <td>{number.format(work?.completed || 0)}</td>
            <td>{number.format((workActivity?.created || 0) + (workActivity?.completed || 0) + (workActivity?.updates || 0) + (workActivity?.handoffs || 0))}</td>
            <td>{number.format(Math.round((workActivity?.minutes || 0) / 6) / 10)} ساعت</td>
            <td className='text-muted-foreground'>{person.last_task_activity_at ? formatUserDateTime(person.last_task_activity_at, calendar) : 'ثبت نشده'}</td>
            <td><Button size='sm' variant='outline' onClick={() => { setOwnerId(String(person.id)); resetOffset(); }}>دیدن کارها</Button></td>
          </tr>;
        })}</tbody>
      </table>{!people.length && <p className='text-muted-foreground p-6 text-center text-sm'>عضوی در این محدوده پیدا نشد.</p>}
      </CardContent></Card>

    {selectedPerson && <Card><CardHeader><CardTitle>پروندهٔ اجرایی {selectedPerson.full_name}</CardTitle>
      <CardDescription>پروژه‌های سپرده‌شده، مسئولیت و کارکرد ثبت‌شده در {period === 'week' ? 'این هفته' : 'این ماه'}.</CardDescription></CardHeader>
      <CardContent className='grid gap-4 lg:grid-cols-[1.5fr_1fr]'>
        <div><strong className='text-sm'>پروژه‌ها و نقش</strong>
          <div className='mt-2 flex flex-wrap gap-2'>{selectedPerson.projects.map((project) =>
            <button type='button' key={project.site_id} onClick={() => { setSiteId(project.site_id); resetOffset(); }}
              className='rounded-lg border px-3 py-2 text-right text-xs hover:bg-muted/50'>
              {project.name} · {project.responsibility === 'lead' ? 'راهبر' : project.responsibility === 'contributor' ? 'مجری' : 'ناظر'}
            </button>)}
            {!selectedPerson.projects.length && <span className='text-muted-foreground text-xs'>پروژه‌ای به این عضو سپرده نشده است.</span>}
          </div>
        </div>
        <div className='grid grid-cols-2 gap-2 text-xs'>
          <div className='rounded-lg border p-3'><span className='text-muted-foreground block'>کار باز</span><strong className='text-lg'>{number.format(workload.get(selectedPerson.id)?.open || 0)}</strong></div>
          <div className='rounded-lg border p-3'><span className='text-muted-foreground block'>عقب‌افتاده</span><strong className='text-lg'>{number.format(workload.get(selectedPerson.id)?.overdue || 0)}</strong></div>
          <div className='rounded-lg border p-3'><span className='text-muted-foreground block'>کار ایجادشده</span><strong className='text-lg'>{number.format(activity.get(selectedPerson.id)?.created || 0)}</strong></div>
          <div className='rounded-lg border p-3'><span className='text-muted-foreground block'>کار تکمیل‌شده</span><strong className='text-lg'>{number.format(activity.get(selectedPerson.id)?.completed || 0)}</strong></div>
        </div>
      </CardContent></Card>}

    {ledger && <PortfolioMatrix ledger={ledger} people={overview?.people || []} projects={projects}
      weeks={horizon === 35 ? 5 : 13} calendar={calendar}
      onWeeksChange={(value) => setHorizon(value === 5 ? 35 : 91)}
      onPersonSelect={(id, bucket) => { if (id === null) { setFocus('unassigned'); setOwnerId(''); }
        else { setOwnerId(String(id)); setFocus(bucket || 'open'); } setStatus(''); resetOffset(); }}
      onProjectSelect={(id, bucket) => { setSiteId(id); setFocus(bucket || 'open'); setStatus(''); resetOffset(); }} />}
    {ledger && <Timeline items={ledger.items} horizon={horizon} calendar={calendar} onHorizonChange={setHorizon} />}

    <Card><CardHeader className='flex flex-row flex-wrap items-start justify-between gap-3'><div>
      <CardTitle>فهرست یکپارچهٔ تسک‌ها</CardTitle><CardDescription className='mt-1'>هر سطر به کارت اصلی می‌رود؛ مدیر کل می‌تواند همان‌جا جزئیات، مسئول و زمان‌بندی را ویرایش کند.</CardDescription></div>
      <Badge variant='outline'>{number.format(ledger?.total || 0)} نتیجه</Badge></CardHeader>
      <CardContent>{ledgerLoading && <p className='text-muted-foreground py-3 text-sm'>در حال بارگیری کارها…</p>}
        <div className='overflow-x-auto rounded-xl border'><table className='w-full min-w-[1100px] text-right text-xs'>
          <thead className='bg-muted/50'><tr><th className='p-3'>تسک / پروژه</th><th>مسئول</th><th>مرحله / اولویت</th><th>شروع</th><th>موعد</th><th>پیشرفت</th><th>ایجادکننده</th><th>آخرین تغییر</th><th>کارت</th></tr></thead>
          <tbody>{ledger?.items.map((task) => {
            const overdue = task.due_at && openStatuses.has(task.status) && Date.parse(task.due_at) < Date.now();
            return <tr key={task.id} className='border-t hover:bg-muted/30'>
              <td className='max-w-[280px] p-3'><Link href={taskUrl(task)} className='block truncate font-semibold hover:text-primary'>{task.title}</Link>
                <span className='text-muted-foreground block truncate'>{task.site_name}{task.parent_id ? ' · زیرتسک' : ''}</span></td>
              <td>{task.owner_name || <span className='text-amber-600'>بی‌مسئول</span>}</td>
              <td><Badge variant={task.status === 'blocked' ? 'destructive' : 'outline'}>{statusLabels[task.status]}</Badge>
                <span className={`mr-1 ${task.priority === 'critical' ? 'text-rose-600' : 'text-muted-foreground'}`}>{priorityLabels[task.priority]}</span></td>
              <td>{task.start_at ? formatUserDate(task.start_at, calendar) : '—'}</td>
              <td className={overdue ? 'font-semibold text-rose-600' : ''}>{task.due_at ? formatUserDate(task.due_at, calendar) : 'بی‌موعد'}</td>
              <td><span className='font-medium'>{number.format(task.status === 'verified' ? 100 : task.progress_percent)}٪</span>
                {task.checklist_total > 0 && <span className='text-muted-foreground block'>{number.format(task.checklist_done)}/{number.format(task.checklist_total)} چک‌لیست</span>}
                {task.subtasks > 0 && <span className='text-muted-foreground block'>{number.format(task.subtasks)} زیرتسک</span>}</td>
              <td>{task.created_by_name || 'نامشخص'}</td><td className='text-muted-foreground'>{formatUserDateTime(task.updated_at, calendar)}</td>
              <td><Link href={taskUrl(task)} className='text-primary hover:underline'>باز کردن</Link></td>
            </tr>;
          })}</tbody>
        </table>{!ledgerLoading && !ledger?.items.length && <p className='text-muted-foreground p-7 text-center text-sm'>تسکی با این فیلترها پیدا نشد.</p>}</div>
        <div className='mt-3 flex flex-wrap items-center justify-between gap-2 text-xs'>
          <span>نمایش {number.format(ledger?.items.length ? offset + 1 : 0)} تا {number.format(offset + (ledger?.items.length || 0))} از {number.format(ledger?.total || 0)}</span>
          <div className='flex gap-2'><Button size='sm' variant='outline' disabled={offset === 0 || ledgerLoading} onClick={() => setOffset(Math.max(0, offset - 100))}>صفحهٔ قبل</Button>
            <Button size='sm' variant='outline' disabled={ledgerLoading || offset + 100 >= (ledger?.total || 0)} onClick={() => setOffset(offset + 100)}>صفحهٔ بعد</Button></div>
        </div>
      </CardContent></Card>

    <section className='grid gap-4 xl:grid-cols-2'>
      <Card><CardHeader><CardTitle>پیشرفت پروژه‌ها</CardTitle><CardDescription>سایت‌ها و پروژه‌های دستی؛ راهبر، اعضا و وضعیت اجرا.</CardDescription></CardHeader>
        <CardContent className='max-h-[430px] space-y-2 overflow-y-auto'>{visibleProjects.map((project) =>
          <button key={project.site_id} type='button' onClick={() => { setSiteId(project.site_id); resetOffset(); }}
            className='block w-full rounded-xl border p-3 text-right transition-colors hover:bg-muted/40'>
            <span className='flex justify-between gap-2'><strong className='truncate text-sm'>{project.name}</strong><Badge variant='outline'>{number.format(project.progress_percent)}٪</Badge></span>
            <span className='text-muted-foreground mt-1 block text-xs'>راهبر: {project.lead_name || 'تعیین نشده'} · {number.format(project.members)} عضو · {number.format(project.open_tasks)} کار باز</span>
            <span className='mt-2 block h-1.5 rounded-full bg-muted'><span className='block h-full rounded-full bg-emerald-500' style={{ width: `${project.progress_percent}%` }} /></span>
            {(project.overdue_tasks > 0 || project.blocked_tasks > 0) && <span className='mt-2 block text-xs text-rose-600'>{number.format(project.overdue_tasks)} عقب‌افتاده · {number.format(project.blocked_tasks)} مسدود</span>}
          </button>)}
          {!visibleProjects.length && <p className='text-muted-foreground text-sm'>پروژه‌ای ثبت نشده است.</p>}
        </CardContent></Card>
      <Card><CardHeader><CardTitle>آخرین فعالیت‌های ثبت‌شده</CardTitle><CardDescription>تاریخچهٔ واقعی تغییرات تسک‌ها، نه صرفاً تاریخ آخرین بارگذاری صفحه.</CardDescription></CardHeader>
        <CardContent className='max-h-[430px] space-y-2 overflow-y-auto'>{(overview?.recent || [])
          .filter((event) => !siteId || event.site_id === siteId)
          .map((event) => <div key={event.id} className='rounded-lg border p-3 text-xs'>
            <span className='font-medium'>{event.actor_username || 'سیستم'}</span> {activityLabels[event.event_type] || 'تغییر داد'}: {' '}
            <Link href={`/dashboard/work?site=${encodeURIComponent(event.site_id)}&task=${event.work_item_id}`} className='text-primary hover:underline'>{event.task_title}</Link>
            <span className='text-muted-foreground'> · {event.project_name}</span>
            <time className='text-muted-foreground mt-1 block'>{formatUserDateTime(event.created_at, calendar)}</time>
          </div>)}
          {!overview?.recent.length && <p className='text-muted-foreground text-sm'>فعالیتی ثبت نشده است.</p>}
        </CardContent></Card>
    </section>
  </div>;
}
