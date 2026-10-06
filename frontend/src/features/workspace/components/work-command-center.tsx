'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { motion, useReducedMotion } from 'motion/react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Textarea } from '@/components/ui/textarea';
import { api, type PortfolioOverview } from '@/lib/api/client';
import type { WorkStatus } from '@/features/reports/types';
import { commandApi, type CommandFilters, type CommandOverview, type CommandWorkItem, type WorkPerson,
  type WorkPriority, type WorkTeam, type ProjectSummary } from '../api';
import { WorkGraph } from './work-graph';
import { ProjectExecution } from './project-execution';
import { TeamPlanner } from './team-planner';
import { TeamBoard } from './team-board';
import { TaskExecutionDetails } from './task-execution-details';
import { TaskDiscussion } from './task-discussion';
import { UserDateInput } from '@/components/user-date-input';
import { formatUserDate, formatUserDateTime, useDatePreference } from '@/lib/date-preference';

const num = new Intl.NumberFormat('fa-IR');
const statusLabel: Record<WorkStatus, string> = {
  new: 'جدید', triaged: 'نیازمند بررسی', approved: 'تأییدشده', assigned: 'واگذار شده',
  in_progress: 'در حال اجرا', review: 'بازبینی', published: 'منتشر شده',
  measurement_pending: 'در انتظار سنجش', verified: 'تأیید نتیجه', blocked: 'مسدود',
  rejected: 'رد شده', deferred: 'تعویق'
};
const priorityLabel: Record<WorkPriority, string> = { critical: 'فوری', high: 'بالا', normal: 'معمولی', low: 'پایین' };
const closedStatuses = new Set<WorkStatus>(['verified', 'rejected', 'deferred']);
type View = 'command' | 'mine' | 'assigned' | 'archive' | 'projects' | 'planner' | 'sheet' | 'kanban' | 'timeline' | 'graph' | 'teams';
type Focus = 'all' | 'overdue' | 'unassigned' | 'blocked' | 'due_week' | 'hours';
type TaskForm = { site_id: string; title: string; description: string; url: string; status: WorkStatus;
  priority: WorkPriority; owner_id: string; team_id: string; due_at: string; estimated_hours: string;
  start_at: string; progress_percent: string; parent_id: string; milestone_id: string;
  blocked_reason: string; verification_note: string; note: string };
const blankForm: TaskForm = { site_id: '', title: '', description: '', url: '', status: 'new', priority: 'normal',
  owner_id: '', team_id: '', due_at: '', start_at: '', progress_percent: '0', parent_id: '', milestone_id: '',
  estimated_hours: '', blocked_reason: '', verification_note: '', note: '' };
const views: { key: View; label: string }[] = [
  { key: 'kanban', label: 'برد من و پروژه‌ها' }, { key: 'mine', label: 'به من واگذار شده' }, { key: 'assigned', label: 'من واگذار کرده‌ام' }, { key: 'archive', label: 'آرشیو' }, { key: 'projects', label: 'پروژه‌ها' }, { key: 'planner', label: 'برنامهٔ تیم' }, { key: 'sheet', label: 'شیت کارها' },
  { key: 'command', label: 'فرماندهی' }, { key: 'timeline', label: 'تایم‌لاین' },
  { key: 'graph', label: 'گراف مسیر' }, { key: 'teams', label: 'تیم‌ها' }
];
async function allBoardPages(page: (afterId: number) => Promise<{ items: CommandWorkItem[]; next_after_id: number | null }>) {
  const rows: CommandWorkItem[] = [];
  let cursor = 0;
  do { const result = await page(cursor); rows.push(...result.items); cursor = result.next_after_id || 0; } while (cursor);
  return rows;
}
const dateTimeInput = (value?: string | null) => {
  if (!value) return '';
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
const isOverdue = (item: CommandWorkItem) => Boolean(item.due_at && !closedStatuses.has(item.status) && Date.parse(item.due_at) < Date.now());
const statusTone = (status: WorkStatus) => status === 'blocked' ? 'border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300' :
  status === 'verified' ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' :
  status === 'in_progress' ? 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300' : '';

export function WorkCommandCenter() {
  const [data, setData] = useState<CommandOverview | null>(null);
  const [personalItems, setPersonalItems] = useState<CommandWorkItem[]>([]);
  const [createdItems, setCreatedItems] = useState<CommandWorkItem[]>([]);
  const [archiveKind, setArchiveKind] = useState<'completed' | 'deleted'>('completed');
  const [archiveItems, setArchiveItems] = useState<CommandWorkItem[]>([]);
  const [assignedSite, setAssignedSite] = useState('');
  const [assignedOwner, setAssignedOwner] = useState('');
  const [people, setPeople] = useState<WorkPerson[]>([]);
  const [teams, setTeams] = useState<WorkTeam[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioOverview | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [meId, setMeId] = useState<number | null>(null);
  const [role, setRole] = useState<'admin' | 'analyst' | 'call_center'>('analyst');
  const [filters, setFilters] = useState<CommandFilters>({ limit: 500 });
  const [search, setSearch] = useState('');
  const requestId = useRef(0);
  const [focus, setFocus] = useState<Focus>('all');
  const [view, setView] = useState<View>('kanban');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState<CommandWorkItem | 'new' | null>(null);
  const [showExecutionDetails, setShowExecutionDetails] = useState(false);
  const [form, setForm] = useState<TaskForm>(blankForm);
  const [saving, setSaving] = useState(false);
  const [milestones, setMilestones] = useState<Awaited<ReturnType<typeof commandApi.milestones>>>([]);
  const [teamName, setTeamName] = useState('');
  const [teamColor, setTeamColor] = useState('#1abb9c');
  const [teamDescription, setTeamDescription] = useState('');
  const [teamSaving, setTeamSaving] = useState(false);
  const [editingTeamId, setEditingTeamId] = useState<number | null>(null);
  const [teamEdit, setTeamEdit] = useState({ name: '', description: '', color: '#1abb9c', active: true });
  const reduced = useReducedMotion();
  const { calendar } = useDatePreference();
  const dateText = (value: string | null) => value ? formatUserDate(value, calendar) : 'بدون موعد';
  const canEdit = role === 'admin';

  const refresh = useCallback(async (quiet = false) => {
    const currentRequest = ++requestId.current;
    if (!quiet) setLoading(true);
    try {
      const [overview, teamRows, personRows, me, portfolioRows, projectRows] = await Promise.all([
        commandApi.overview(filters), commandApi.teams(), commandApi.people(),
        commandApi.me(), api<PortfolioOverview>('/portfolio/overview'), commandApi.projects()
      ]);
      if (currentRequest === requestId.current) {
        setData(overview); setTeams(teamRows); setPeople(personRows); setRole(me.role); setMeId(me.id); setProjects(projectRows); setPortfolio(portfolioRows); setError('');
        void Promise.all([allBoardPages(commandApi.personalBoardPage), allBoardPages(commandApi.createdBoardPage)])
          .then(([personal, created]) => { if (currentRequest === requestId.current) { setPersonalItems(personal); setCreatedItems(created); } })
          .catch(() => { if (currentRequest === requestId.current) { setPersonalItems([]); setCreatedItems([]); } });
      }
    } catch (cause) { if (currentRequest === requestId.current) setError(cause instanceof Error ? cause.message : 'دریافت داده انجام نشد'); }
    finally { if (currentRequest === requestId.current) setLoading(false); }
  }, [filters]);
  useEffect(() => { void refresh(); const timer = setInterval(() => void refresh(true), 30000); return () => clearInterval(timer); }, [refresh]);
  useEffect(() => { const timer = setTimeout(() => setFilters((previous) => {
    const q = search.trim() || undefined;
    return previous.q === q ? previous : { ...previous, q };
  }), 300); return () => clearTimeout(timer); }, [search]);
  useEffect(() => { if (view !== 'archive') return;
    void commandApi.archive(archiveKind).then(setArchiveItems).catch(() => setArchiveItems([]));
  }, [view, archiveKind, data]);
  useEffect(() => { if (!editing || !form.site_id) return; let active = true;
    void commandApi.milestones(form.site_id)
      .then((rows) => { if (active) setMilestones(rows); })
      .catch(() => { if (active) setMilestones([]); });
    return () => { active = false; };
  }, [editing, form.site_id]);

  const items = useMemo(() => (data?.items ?? []).filter((item) => {
    if (focus === 'overdue') return isOverdue(item);
    if (focus === 'unassigned') return !item.owner_id && !closedStatuses.has(item.status);
    if (focus === 'blocked') return item.status === 'blocked';
    if (focus === 'due_week') return Boolean(item.due_at && !closedStatuses.has(item.status) &&
      Date.parse(item.due_at) >= Date.now() && Date.parse(item.due_at) < Date.now() + 7 * 86400000);
    if (focus === 'hours') return Boolean(item.estimated_hours && !closedStatuses.has(item.status));
    return true;
  }), [data, focus]);
  const ownerBars = useMemo(() => (data?.by_owner ?? []).slice(0, 8).map((row) => ({ name: row.name, باز: row.open, عقب‌افتاده: row.overdue })), [data]);
  const dueSeries = useMemo(() => { const days = new Map(data?.due_days.map((row) => [row.day, row.count]) ?? []);
    return Array.from({ length: 21 }, (_, index) => { const date = new Date(); date.setUTCHours(12, 0, 0, 0); date.setUTCDate(date.getUTCDate() + index);
      return { day: formatUserDate(date, calendar, { month: 'short', day: 'numeric' }), count: days.get(date.toISOString().slice(0, 10)) || 0 }; }); }, [data, calendar]);
  const statusChart = useMemo(() => (data?.by_status ?? []).map((row) => ({ name: statusLabel[row.key], value: row.count })), [data]);
  const displayCount = data?.summary.total ?? 0;
  const projectRole = (siteId: string) => projects.find((project) => project.site_id === siteId)?.my_responsibility;
  const canLead = (siteId: string) => canEdit || projectRole(siteId) === 'lead';
  const canUpdate = (item: CommandWorkItem) => meId !== null && (canLead(item.site_id) || Boolean(projectRole(item.site_id))) &&
    (item.owner_id !== null ? item.owner_id === meId : item.created_by_id !== null ? item.created_by_id === meId : canLead(item.site_id));
  const canManageEditing = editing === 'new' ? canLead(form.site_id) : editing ? canUpdate(editing) : false;
  const canAssignEditing = editing === 'new' ? canLead(form.site_id) : Boolean(editing && editing.owner_id === null && canUpdate(editing));
  const canUpdateEditing = editing !== null && (editing === 'new' ? canManageEditing : canUpdate(editing));
  const myItems = useMemo(() => personalItems.filter((item) => item.owner_id === meId && !closedStatuses.has(item.status))
    .toSorted((a, b) => (a.status === 'blocked' ? -1 : b.status === 'blocked' ? 1 : 0) ||
      (isOverdue(a) ? -1 : isOverdue(b) ? 1 : 0) ||
      (a.due_at || '9999').localeCompare(b.due_at || '9999')), [personalItems, meId]);
  const assignedItems = useMemo(() => createdItems.filter((item) =>
    (!assignedSite || item.site_id === assignedSite) && (!assignedOwner || item.owner_id?.toString() === assignedOwner)),
    [createdItems, assignedSite, assignedOwner]);

  function openTask(item: CommandWorkItem | 'new') {
    setShowExecutionDetails(false); setEditing(item);
    setForm(item === 'new' ? { ...blankForm, site_id: (filters.site_id && canLead(filters.site_id) ? filters.site_id : projects.find((project) => canLead(project.site_id))?.site_id) || '' } : {
      site_id: item.site_id, title: item.title, description: item.description, url: item.url || '',
      status: item.status, priority: item.priority, owner_id: item.owner_id?.toString() || '',
      team_id: item.team_id?.toString() || '', due_at: dateTimeInput(item.due_at),
      start_at: dateTimeInput(item.start_at), progress_percent: String(item.progress_percent ?? 0),
      parent_id: item.parent_id?.toString() || '', milestone_id: item.milestone_id?.toString() || '',
      estimated_hours: item.estimated_hours?.toString() || '', blocked_reason: item.blocked_reason || '',
      verification_note: item.verification_note || '', note: ''
    });
  }
  async function saveTask() {
    if (!editing) return;
    if (form.title.trim().length < 3 || !form.site_id) { toast.error('پروژه و عنوان کار را مشخص کنید'); return; }
    setSaving(true);
    const body = { title: form.title.trim(), description: form.description.trim(), url: form.url.trim() || null,
      status: form.status, priority: form.priority, owner_id: form.owner_id ? Number(form.owner_id) : null,
      team_id: form.team_id ? Number(form.team_id) : null, due_at: form.due_at ? new Date(form.due_at).toISOString() : null,
      start_at: form.start_at ? new Date(form.start_at).toISOString() : null,
      progress_percent: Number(form.progress_percent || 0), parent_id: form.parent_id ? Number(form.parent_id) : null,
      milestone_id: form.milestone_id ? Number(form.milestone_id) : null,
      estimated_hours: form.estimated_hours ? Number(form.estimated_hours) : null,
      blocked_reason: form.blocked_reason.trim() || null, verification_note: form.verification_note.trim() || null,
      note: form.note.trim() || null };
    try {
      if (editing === 'new') await commandApi.createWork(form.site_id, body);
      else {
        const permitted = editing.owner_id === null ? body : Object.fromEntries(Object.entries(body).filter(([key]) => key !== 'owner_id'));
        const changed = Object.fromEntries(Object.entries(permitted).filter(([key, value]) => {
          if (key === 'note') return Boolean(value);
          const previous = editing[key as keyof CommandWorkItem];
          if (key === 'due_at' || key === 'start_at') return (value ? Date.parse(String(value)) : null) !==
            (previous ? Date.parse(String(previous)) : null);
          return value !== previous;
        }));
        if (!Object.keys(changed).length) { setEditing(null); return; }
        await commandApi.updateWork(editing, changed);
      }
      setEditing(null); await refresh(true); toast.success('کار و تاریخچهٔ آن ذخیره شد');
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ذخیره انجام نشد'); }
    finally { setSaving(false); }
  }
  async function completeTask(item: CommandWorkItem) {
    try { await commandApi.updateWork(item, { status: 'verified' }); setEditing(null); await refresh(true); toast.success('کار انجام شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'تکمیل کار انجام نشد'); }
  }
  async function quickTaskPatch(item: CommandWorkItem, patch: Record<string, unknown>) {
    try { await commandApi.updateWork(item, patch); await refresh(true); toast.success('کار به‌روز شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ویرایش سریع انجام نشد'); }
  }
  async function deleteTask(item: CommandWorkItem) {
    if (!window.confirm(`کار «${item.title}» به آرشیو حذف‌شده‌ها منتقل شود؟`)) return;
    try { await commandApi.deleteWork(item); setEditing(null); await refresh(true); toast.success('کار به آرشیو حذف‌شده‌ها منتقل شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'حذف کار انجام نشد'); }
  }
  async function createTeam() {
    if (teamName.trim().length < 2) return;
    setTeamSaving(true);
    try { await commandApi.createTeam({ name: teamName.trim(), color: teamColor, description: teamDescription.trim() });
      setTeamName(''); setTeamDescription(''); await refresh(true); toast.success('تیم ایجاد شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ثبت تیم انجام نشد'); }
    finally { setTeamSaving(false); }
  }
  async function assignMember(person: WorkPerson, teamId: string) {
    try { await commandApi.assignMember(person.id, teamId ? Number(teamId) : null);
      await refresh(true); toast.success('عضویت تیم به‌روز شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'تغییر تیم انجام نشد'); }
  }
  async function saveTeam() {
    if (editingTeamId === null || teamEdit.name.trim().length < 2) return;
    setTeamSaving(true);
    try { await commandApi.updateTeam(editingTeamId, { ...teamEdit, name: teamEdit.name.trim() });
      setEditingTeamId(null); await refresh(true); toast.success('تیم به‌روز شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ویرایش تیم انجام نشد'); }
    finally { setTeamSaving(false); }
  }
  async function turnRecommendationIntoWork(siteId: string, title: string) {
    try { await commandApi.createWork(siteId, { title, kind: 'manual', priority: 'high', status: 'new',
      description: 'از اقدام پیشنهادی نمای سبد سایت‌ها به میز عملیات اضافه شد.' });
      await refresh(true); toast.success('پیشنهاد به کار قابل پیگیری تبدیل شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ثبت کار انجام نشد'); }
  }

  return <div className='space-y-3'>
    <section className='flex flex-wrap items-center justify-between gap-2 rounded-xl border border-emerald-500/20 bg-gradient-to-l from-emerald-500/10 via-background to-sky-500/5 p-3'>
      <div className='flex items-center gap-2'><Badge variant='outline'>میز عملیات SEO</Badge><span className='text-muted-foreground text-xs'>به‌روزرسانی خودکار هر ۳۰ ثانیه</span></div>
      <div className='flex gap-2'>{(canEdit || projects.some((project) => project.my_responsibility === 'lead')) && <Button size='sm' onClick={() => openTask('new')}>＋ کار جدید</Button>}
        <Button size='sm' variant='outline' onClick={() => void refresh()} disabled={loading}>به‌روزرسانی</Button></div>
    </section>

    {error && <Card className='border-rose-500/40'><CardContent className='pt-5 text-sm text-rose-600'>{error} <Button variant='outline' size='sm' onClick={() => void refresh()}>تلاش دوباره</Button></CardContent></Card>}
    {loading && !data && <div className='text-muted-foreground rounded-xl border p-12 text-center text-sm'>در حال خواندن کارهای همهٔ سایت‌ها…</div>}
    {data && <>
      {view === 'command' && <section className='grid grid-cols-2 gap-2 md:grid-cols-3 2xl:grid-cols-6' aria-label='شاخص‌های عملیات'>
        {([
          ['کار باز', data.summary.open, 'all', 'text-sky-600'],
          ['عقب‌افتاده', data.summary.overdue, 'overdue', 'text-rose-600'],
          ['بی‌مسئول', data.summary.unassigned, 'unassigned', 'text-amber-600'],
          ['مسدود', data.summary.blocked, 'blocked', 'text-orange-600'],
          ['موعد این هفته', data.summary.due_week, 'due_week', 'text-violet-600'],
          ['ساعت برآوردی باز', data.summary.hours_open, 'hours', 'text-emerald-600']
        ] as const).map(([label, value, key, tone], index) => <motion.button key={label} initial={reduced ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * .045 }}
          onClick={() => setFocus(key)} aria-pressed={focus === key} className={`rounded-xl border bg-card p-3 text-right shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md ${focus === key ? 'border-emerald-500/60 ring-1 ring-emerald-500/20' : 'border-border/70'}`}>
          <span className='text-muted-foreground text-xs'>{label}</span><strong className={`mt-1 block text-xl tabular-nums ${tone}`}>{num.format(value)}</strong>
        </motion.button>)}
      </section>}

      {(view === 'command' || view === 'sheet') && <div className='flex flex-wrap items-center gap-2 rounded-xl border bg-card p-3'>
        <Input aria-label='جست‌وجوی کار' value={search} onChange={(e) => setSearch(e.target.value)} placeholder='جست‌وجو در عنوان، URL و توضیح…' className='min-w-48 flex-1' />
        <NativeSelect aria-label='فیلتر پروژه' value={filters.site_id || ''} onChange={(e) => setFilters((f) => ({ ...f, site_id: e.target.value || undefined }))} className='w-40'><NativeSelectOption value=''>همهٔ پروژه‌ها</NativeSelectOption>{projects.map((project) => <NativeSelectOption key={project.site_id} value={project.site_id}>{project.name}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect aria-label='فیلتر تیم' value={filters.team_id || ''} onChange={(e) => setFilters((f) => ({ ...f, team_id: e.target.value ? Number(e.target.value) : undefined }))} className='w-36'><NativeSelectOption value=''>همهٔ تیم‌ها</NativeSelectOption>{teams.map((team) => <NativeSelectOption key={team.id} value={String(team.id)}>{team.name}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect aria-label='فیلتر مسئول' value={filters.owner_id || ''} onChange={(e) => setFilters((f) => ({ ...f, owner_id: e.target.value ? Number(e.target.value) : undefined }))} className='w-40'><NativeSelectOption value=''>همهٔ مسئولان</NativeSelectOption>{people.filter((person) => person.active).map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect aria-label='فیلتر وضعیت' value={filters.status || ''} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value || undefined }))} className='w-40'><NativeSelectOption value=''>همهٔ وضعیت‌ها</NativeSelectOption>{(Object.keys(statusLabel) as WorkStatus[]).map((status) => <NativeSelectOption key={status} value={status}>{statusLabel[status]}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect aria-label='فیلتر اولویت' value={filters.priority || ''} onChange={(e) => setFilters((f) => ({ ...f, priority: e.target.value || undefined }))} className='w-32'><NativeSelectOption value=''>همهٔ اولویت‌ها</NativeSelectOption>{(Object.keys(priorityLabel) as WorkPriority[]).map((priority) => <NativeSelectOption key={priority} value={priority}>{priorityLabel[priority]}</NativeSelectOption>)}</NativeSelect>
      </div>}

      <div className='flex flex-nowrap gap-1.5 overflow-x-auto border-b pb-2' role='tablist' aria-label='نماهای میز عملیات'>
        {views.map((entry) => <Button key={entry.key} size='sm' className='shrink-0' variant={view === entry.key ? 'default' : 'ghost'} role='tab' aria-selected={view === entry.key} onClick={() => setView(entry.key)}>{entry.label}</Button>)}
        {focus !== 'all' && <Button size='sm' variant='outline' onClick={() => setFocus('all')}>حذف تمرکز</Button>}
      </div>
      {view === 'command' && displayCount > data.items.length && <p className='rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs'>از {num.format(displayCount)} کار مطابق فیلتر، {num.format(data.items.length)} کار نخست نمایش داده می‌شود. برای دیدن بقیه، فیلترها را محدودتر کنید.</p>}

      {view === 'command' && <div className='grid gap-4 xl:grid-cols-[1.55fr_1fr]'>
        {portfolio && <Card className='xl:col-span-2'><CardHeader><CardTitle>نقشهٔ اقدام سایت‌ها</CardTitle><CardDescription>پیشنهادهای این بخش از وضعیت اتصال، داده و گراف هر سایت می‌آیند. مدیر می‌تواند آن‌ها را به کارِ قابل پیگیری تبدیل کند.</CardDescription></CardHeader><CardContent className='grid gap-3 md:grid-cols-2 xl:grid-cols-3'>
          {portfolio.sites.map((site) => { const exists = data.items.some((item) => item.site_id === site.site_id && item.title === site.next_action && !closedStatuses.has(item.status)); return <div key={site.site_id} className='rounded-xl border bg-background/70 p-3'><div className='flex items-center justify-between gap-2'><strong className='text-sm'>{site.name}</strong><Badge variant='outline'>{site.state === 'ready' ? 'آماده' : site.state === 'attention' ? 'نیازمند بررسی' : site.state === 'running' ? 'در حال اجرا' : 'راه‌اندازی ناقص'}</Badge></div><p className='text-muted-foreground mt-2 min-h-10 text-xs leading-5'>{site.state_reason}</p><p className='mt-2 text-sm font-medium'>قدم بعدی: {site.next_action}</p><div className='mt-3 flex gap-2'><Link className='text-primary self-center text-xs hover:underline' href={`/dashboard/reports?site=${encodeURIComponent(site.site_id)}`}>گزارش سایت</Link>{canEdit && site.next_action && <Button size='sm' variant='outline' disabled={exists} onClick={() => void turnRecommendationIntoWork(site.site_id, site.next_action)}>{exists ? 'در میز کار' : 'تبدیل به کار'}</Button>}</div></div>; })}
          {!portfolio.sites.length && <p className='text-muted-foreground text-sm'>سایتی ثبت نشده است.</p>}
        </CardContent></Card>}
        <Card><CardHeader><CardTitle>صف اقدام‌های فوری</CardTitle><CardDescription>مسدودها، موعدگذشته‌ها و کارهای بی‌مسئول در اولویت بررسی‌اند.</CardDescription></CardHeader><CardContent className='space-y-2'>
          {items.filter((item) => item.status === 'blocked' || isOverdue(item) || (!item.owner_id && !closedStatuses.has(item.status))).slice(0, 8).map((item) =>
            <button key={item.id} onClick={() => openTask(item)} className='flex w-full items-start justify-between gap-3 rounded-lg border p-3 text-right transition-colors hover:bg-muted/50'>
              <span><strong className='block text-sm'>{item.title}</strong><span className='text-muted-foreground mt-1 block text-xs'>{item.site_name} · {item.owner_name || 'بی‌مسئول'} · {dateText(item.due_at)}</span></span>
              <Badge variant='outline' className={statusTone(item.status)}>{item.status === 'blocked' ? 'مانع' : isOverdue(item) ? 'عقب‌افتاده' : 'بی‌مسئول'}</Badge>
            </button>)}
          {!items.length && <p className='text-muted-foreground py-10 text-center text-sm'>هنوز کاری ثبت نشده است. از «کار جدید» اولین مسیر اجرایی را بسازید.</p>}
          {items.length > 0 && !items.some((item) => item.status === 'blocked' || isOverdue(item) || !item.owner_id) && <p className='text-muted-foreground py-10 text-center text-sm'>در فیلتر فعلی کار فوری دیده نمی‌شود.</p>}
        </CardContent></Card>
        <div className='space-y-4'><Card><CardHeader><CardTitle>بار کاری مسئولان</CardTitle><CardDescription>تعداد کارهای باز و عقب‌افتاده، نه ساعات واقعی صرف‌شده.</CardDescription></CardHeader><CardContent><div className='h-60'>
          {ownerBars.length ? <ResponsiveContainer width='100%' height='100%'><BarChart data={ownerBars} layout='vertical' margin={{ left: 8, right: 8 }}><CartesianGrid strokeDasharray='3 3' horizontal={false} opacity={.25} /><XAxis type='number' allowDecimals={false} /><YAxis type='category' dataKey='name' width={92} tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey='باز' fill='#1abb9c' radius={[0, 5, 5, 0]} /><Bar dataKey='عقب‌افتاده' fill='#f97373' radius={[0, 5, 5, 0]} /></BarChart></ResponsiveContainer> : <p className='text-muted-foreground pt-20 text-center text-sm'>دادهٔ کار موجود نیست.</p>}
        </div></CardContent></Card>
        <Card><CardHeader><CardTitle>پوشش سایت‌ها</CardTitle><CardDescription>از وضعیت کل سبد به جزئیات هر سایت بروید.</CardDescription></CardHeader><CardContent className='space-y-2'>
          {data.by_site.map((site) => <button key={site.key} onClick={() => setFilters((f) => ({ ...f, site_id: site.key }))} className='flex w-full items-center justify-between rounded-lg border p-2.5 text-sm hover:bg-muted/50'><span>{site.name}</span><span className='text-muted-foreground text-xs'>{num.format(site.open)} باز · {num.format(site.overdue)} عقب‌افتاده</span></button>)}
          {!data.by_site.length && <p className='text-muted-foreground text-sm'>هنوز کار سایتی ثبت نشده است.</p>}
        </CardContent></Card></div>
        <Card className='xl:col-span-2'><CardHeader><CardTitle>جریان اخیر اجرا</CardTitle><CardDescription>ثبت و تغییر وضعیت‌ها از دفتر تاریخچهٔ کارها خوانده می‌شود.</CardDescription></CardHeader><CardContent className='grid gap-2 md:grid-cols-2 xl:grid-cols-3'>
          {data.recent.map((event) => <div key={event.id} className='rounded-lg border p-3'><div className='text-xs text-muted-foreground'>{formatUserDateTime(event.created_at, calendar)} · {event.site_name}</div><div className='mt-1 font-medium text-sm'>{event.title}</div><div className='text-muted-foreground mt-1 text-xs'>{event.event_type === 'created' ? 'ثبت شد' : event.event_type === 'comment' ? 'یادداشت گذاشت' : 'تغییر کرد'} · {event.actor_username || 'سیستم'}{event.note ? ` · ${event.note}` : ''}</div></div>)}
          {!data.recent.length && <p className='text-muted-foreground text-sm'>هنوز رویدادی ثبت نشده است.</p>}
        </CardContent></Card>
        <Card><CardHeader><CardTitle>توزیع مراحل کار</CardTitle><CardDescription>مبنای نمودار، تعداد کارهای ثبت‌شده در فیلتر فعلی است.</CardDescription></CardHeader><CardContent><div className='h-64'>{statusChart.length ? <ResponsiveContainer width='100%' height='100%'><PieChart><Pie data={statusChart} dataKey='value' nameKey='name' innerRadius={58} outerRadius={86} paddingAngle={4} animationDuration={850}>{statusChart.map((row, index) => <Cell key={row.name} fill={['#1abb9c', '#38bdf8', '#a78bfa', '#f59e0b', '#ef4444', '#64748b'][index % 6]} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer> : <p className='text-muted-foreground pt-20 text-center text-sm'>هنوز مرحله‌ای ثبت نشده است.</p>}</div><div className='flex flex-wrap gap-2'>{statusChart.map((row) => <Badge key={row.name} variant='outline'>{row.name} · {num.format(row.value)}</Badge>)}</div></CardContent></Card>
        <Card><CardHeader><CardTitle>بار تیم‌ها</CardTitle><CardDescription>کار باز هر تیم برای توزیع بهتر مسئولیت.</CardDescription></CardHeader><CardContent><div className='h-64'>{data.by_team.length ? <ResponsiveContainer width='100%' height='100%'><BarChart data={data.by_team.slice(0, 8)} margin={{ left: 8, right: 8 }}><CartesianGrid strokeDasharray='3 3' opacity={.2} /><XAxis dataKey='name' tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey='open' name='کار باز' fill='#8b5cf6' radius={[6, 6, 0, 0]} animationDuration={850} /></BarChart></ResponsiveContainer> : <p className='text-muted-foreground pt-20 text-center text-sm'>با تعریف تیم و واگذاری کار، نمودار شکل می‌گیرد.</p>}</div></CardContent></Card>
      </div>}

      {view === 'mine' && <div className='grid gap-4 xl:grid-cols-[1.5fr_1fr]'>
        <Card><CardHeader><CardTitle>تسک‌هایی که به من سپرده شده</CardTitle><CardDescription>فقط تسک‌هایی که مسئولشان شما هستید؛ برنامه‌ریزی و تغییرشان در اختیار شماست.</CardDescription></CardHeader><CardContent className='space-y-2'>
          {myItems.map((item) => <div key={item.id} className='flex items-start justify-between gap-3 rounded-xl border p-3 transition-colors hover:bg-muted/50'><button onClick={() => openTask(item)} className='min-w-0 flex-1 text-right'><strong className='block truncate text-sm'>{item.title}</strong><span className='text-muted-foreground mt-1 block text-xs'>{item.site_name} · واگذارکننده: {item.created_by_name || 'سیستم'} · {dateText(item.due_at)}</span><Badge variant='outline' className='mt-1'>{priorityLabel[item.priority]}</Badge></button><div className='flex flex-col items-end gap-2'><Badge variant='outline' className={statusTone(item.status)}>{isOverdue(item) ? 'عقب‌افتاده' : statusLabel[item.status]}</Badge><Button size='sm' variant='outline' onClick={() => void completeTask(item)}>✓ انجام شد</Button></div></div>)}
          {!myItems.length && <p className='text-muted-foreground py-10 text-center text-sm'>کار بازی به شما واگذار نشده است. راهبر پروژه می‌تواند از بخش پروژه‌ها شما را عضو و مسئول کار کند.</p>}
        </CardContent></Card>
        <div className='space-y-4'><Card><CardHeader><CardTitle>وضعیت شخصی</CardTitle></CardHeader><CardContent className='grid grid-cols-2 gap-3 text-center text-sm'><div className='rounded-lg bg-muted p-4'><strong className='block text-2xl'>{num.format(myItems.length)}</strong>کار باز</div><div className='rounded-lg bg-rose-500/10 p-4'><strong className='block text-2xl text-rose-600'>{num.format(myItems.filter(isOverdue).length)}</strong>عقب‌افتاده</div><div className='rounded-lg bg-amber-500/10 p-4'><strong className='block text-2xl text-amber-600'>{num.format(myItems.filter((item) => item.status === 'blocked').length)}</strong>مانع‌دار</div><div className='rounded-lg bg-sky-500/10 p-4'><strong className='block text-2xl text-sky-600'>{num.format(myItems.reduce((sum, item) => sum + (item.estimated_hours || 0), 0))}</strong>ساعت برآوردی باز</div></CardContent></Card>
          <Card><CardHeader><CardTitle>پروژه‌های من</CardTitle></CardHeader><CardContent className='space-y-2'>{projects.filter((project) => project.my_responsibility || canEdit).map((project) => <button key={project.site_id} onClick={() => { setFilters((current) => ({ ...current, site_id: project.site_id })); setView('projects'); }} className='flex w-full justify-between rounded-lg border p-3 text-sm hover:bg-muted/50'><span>{project.name}</span><span className='text-muted-foreground'>{canEdit || project.my_responsibility === 'admin' ? 'مدیر' : project.my_responsibility === 'lead' ? 'راهبر' : project.my_responsibility === 'contributor' ? 'مجری' : 'ناظر'}</span></button>)}{!projects.some((project) => project.my_responsibility || canEdit) && <p className='text-muted-foreground text-xs'>عضویت پروژه‌ای ثبت نشده است.</p>}</CardContent></Card>
        </div>
      </div>}

      {view === 'assigned' && <Card><CardHeader><CardTitle>تسک‌هایی که من ساخته‌ام</CardTitle><CardDescription>پیش از واگذاری می‌توانید ویرایش کنید؛ پس از واگذاری، مسئول تسک آن را پیش می‌برد و شما روندش را می‌بینید.</CardDescription></CardHeader><CardContent className='space-y-3'>
        <div className='flex flex-wrap gap-2'><NativeSelect aria-label='فیلتر پروژهٔ واگذاری' value={assignedSite} onChange={(e) => setAssignedSite(e.target.value)} className='min-w-44'><NativeSelectOption value=''>همهٔ پروژه‌ها</NativeSelectOption>{projects.map((project) => <NativeSelectOption key={project.site_id} value={project.site_id}>{project.name}</NativeSelectOption>)}</NativeSelect><NativeSelect aria-label='فیلتر مسئول واگذاری' value={assignedOwner} onChange={(e) => setAssignedOwner(e.target.value)} className='min-w-44'><NativeSelectOption value=''>همهٔ مسئولان</NativeSelectOption>{people.filter((person) => person.active).map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect></div>
        {assignedItems.map((item) => <button key={item.id} onClick={() => openTask(item)} className='flex w-full flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-right hover:bg-muted/50'><span><strong className='block text-sm'>{item.title}</strong><span className='text-muted-foreground text-xs'>{item.site_name} · {item.owner_name || 'بی‌مسئول'} · {dateText(item.due_at)}</span></span><span className='flex gap-1'><Badge variant='outline'>{priorityLabel[item.priority]}</Badge><Badge variant='outline'>{statusLabel[item.status]}</Badge></span></button>)}
        {!assignedItems.length && <p className='text-muted-foreground py-8 text-center text-sm'>واگذاری مطابق فیلتر فعلی پیدا نشد.</p>}
      </CardContent></Card>}

      {view === 'archive' && <Card><CardHeader><CardTitle>آرشیو کارها</CardTitle><CardDescription>کارهای انجام‌شده و حذف‌شده جدا هستند؛ حذف، داده و تاریخچه را پاک نمی‌کند.</CardDescription></CardHeader><CardContent className='space-y-3'>
        <div className='flex gap-2'><Button size='sm' variant={archiveKind === 'completed' ? 'default' : 'outline'} onClick={() => setArchiveKind('completed')}>انجام‌شده‌ها</Button><Button size='sm' variant={archiveKind === 'deleted' ? 'default' : 'outline'} onClick={() => setArchiveKind('deleted')}>حذف‌شده‌ها</Button></div>
        {archiveItems.map((item) => <div key={item.id} className='flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3'><span><strong className='block text-sm'>{item.title}</strong><span className='text-muted-foreground text-xs'>{item.site_name} · {item.owner_name || 'بی‌مسئول'} · {dateText(item.deleted_at || item.updated_at)}</span></span><div className='flex gap-2'>{archiveKind === 'completed' && <Button size='sm' variant='outline' onClick={() => openTask(item)}>جزئیات</Button>}{archiveKind === 'deleted' && canUpdate(item) && <Button size='sm' variant='outline' onClick={() => void commandApi.restoreWork(item).then(() => refresh(true)).then(() => toast.success('کار بازیابی شد')).catch((cause) => toast.error(cause instanceof Error ? cause.message : 'بازیابی انجام نشد'))}>بازیابی</Button>}</div></div>)}
        {!archiveItems.length && <p className='text-muted-foreground py-8 text-center text-sm'>در این بخش کاری نیست.</p>}
      </CardContent></Card>}

      {view === 'projects' && <ProjectExecution items={data.items} people={people} canEdit={canEdit} preferredSiteId={filters.site_id} onTask={openTask} />}

      {view === 'planner' && <TeamPlanner items={items} people={people} onTask={openTask} />}

      {view === 'sheet' && <Card><CardHeader><CardTitle>شیت مدیریت کارها</CardTitle><CardDescription>مرور همهٔ سایت‌ها، مسئولیت، موعد، اولویت و مرحلهٔ اجرا. برای تغییر هر ردیف، آن را باز کنید.</CardDescription></CardHeader><CardContent>
        <div className='overflow-x-auto rounded-lg border'><table className='w-full min-w-[1050px] text-right text-sm'><thead className='bg-muted/50 text-xs'><tr><th className='p-3'>کار / منبع</th><th>سایت</th><th>تیم</th><th>مسئول</th><th>اولویت</th><th>وضعیت</th><th>موعد</th><th>ساعت</th><th className='p-3'>جزئیات</th></tr></thead><tbody>
          {items.map((item) => <tr key={item.id} className='border-t transition-colors hover:bg-muted/40'>
            <td className='max-w-64 p-3'><strong className='block truncate'>{item.title}</strong><span className='text-muted-foreground block text-[11px]'>واگذارکننده: {item.created_by_name || 'سیستم'}</span></td>
            <td>{item.site_name}</td><td>{item.team_name || '—'}</td>
            <td>{canLead(item.site_id) ? <NativeSelect aria-label={`مسئول ${item.title}`} value={item.owner_id?.toString() || ''} onChange={(event) => void quickTaskPatch(item, { owner_id: event.target.value ? Number(event.target.value) : null })} className='min-w-32'><NativeSelectOption value=''>بی‌مسئول</NativeSelectOption>{people.filter((person) => person.active && person.role !== 'call_center').map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect> : item.owner_name || 'بی‌مسئول'}</td>
            <td>{canLead(item.site_id) ? <NativeSelect aria-label={`اولویت ${item.title}`} value={item.priority} onChange={(event) => void quickTaskPatch(item, { priority: event.target.value })} className='w-28'>{(Object.keys(priorityLabel) as WorkPriority[]).map((key) => <NativeSelectOption key={key} value={key}>{priorityLabel[key]}</NativeSelectOption>)}</NativeSelect> : <Badge variant='outline'>{priorityLabel[item.priority]}</Badge>}</td>
            <td>{canUpdate(item) ? <NativeSelect aria-label={`وضعیت ${item.title}`} value={item.status} onChange={(event) => void quickTaskPatch(item, { status: event.target.value })} className='w-32'>{(Object.keys(statusLabel) as WorkStatus[]).filter((status) => canLead(item.site_id) || !['approved','assigned','rejected','deferred'].includes(status)).map((status) => <NativeSelectOption key={status} value={status}>{statusLabel[status]}</NativeSelectOption>)}</NativeSelect> : <Badge variant='outline' className={statusTone(item.status)}>{statusLabel[item.status]}</Badge>}</td>
            <td className={isOverdue(item) ? 'text-rose-600' : ''}>{dateText(item.due_at)}</td><td>{item.estimated_hours ?? '—'}</td>
            <td className='p-3'><Button size='sm' variant='outline' onClick={() => openTask(item)}>جزئیات</Button></td>
          </tr>)}
        </tbody></table></div>{!items.length && <p className='text-muted-foreground py-10 text-center text-sm'>کاری مطابق فیلتر پیدا نشد.</p>}
      </CardContent></Card>}

      {view === 'kanban' && <TeamBoard items={data.items} sites={projects.filter((project) => canEdit || project.my_responsibility).map((project) => ({ site_id: project.site_id, name: project.name }))} people={people} preferredSiteId={filters.site_id} meId={meId}
        canLead={canLead} canUpdate={canUpdate} onOpen={openTask}
        onSiteChange={(siteId) => setFilters((current) => ({ ...current, site_id: siteId || undefined }))}
        onChanged={async () => { await refresh(true); }} />}

      {view === 'timeline' && <div className='grid gap-4 xl:grid-cols-[1fr_1.3fr]'>
        <Card><CardHeader><CardTitle>موعدهای ۲۱ روز آینده</CardTitle><CardDescription>بار برنامه‌ریزی‌شدهٔ کارهای باز بر اساس روز سررسید.</CardDescription></CardHeader><CardContent><div className='h-72'>{dueSeries.length ? <ResponsiveContainer width='100%' height='100%'><AreaChart data={dueSeries}><defs><linearGradient id='dueGradient' x1='0' y1='0' x2='0' y2='1'><stop offset='0%' stopColor='#1abb9c' stopOpacity={.42} /><stop offset='100%' stopColor='#1abb9c' stopOpacity={.02} /></linearGradient></defs><CartesianGrid strokeDasharray='3 3' opacity={.2} /><XAxis dataKey='day' tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} /><Tooltip /><Area type='monotone' dataKey='count' name='کار' stroke='#1abb9c' strokeWidth={3} fill='url(#dueGradient)' animationDuration={900} /></AreaChart></ResponsiveContainer> : <p className='text-muted-foreground pt-24 text-center text-sm'>در ۲۱ روز آینده موعدی ثبت نشده است.</p>}</div></CardContent></Card>
        <Card><CardHeader><CardTitle>تقویم تحویل</CardTitle><CardDescription>زمان، مسئول و مرحلهٔ هر کار را در یک ردیف ببینید.</CardDescription></CardHeader><CardContent className='max-h-[490px] space-y-2 overflow-y-auto'>
          {items.filter((item) => item.due_at && !closedStatuses.has(item.status)).toSorted((a, b) => (a.due_at || '').localeCompare(b.due_at || '')).map((item) => <button key={item.id} onClick={() => openTask(item)} className='flex w-full items-center gap-3 rounded-lg border p-3 text-right hover:bg-muted/50'><span className={`w-24 shrink-0 text-xs ${isOverdue(item) ? 'text-rose-600' : 'text-muted-foreground'}`}>{dateText(item.due_at)}</span><span className='min-w-0 flex-1'><strong className='block truncate text-sm'>{item.title}</strong><span className='text-muted-foreground text-xs'>{item.site_name} · {item.owner_name || 'بی‌مسئول'}</span></span><Badge variant='outline' className={statusTone(item.status)}>{statusLabel[item.status]}</Badge></button>)}
          {!items.some((item) => item.due_at && !closedStatuses.has(item.status)) && <p className='text-muted-foreground py-10 text-center text-sm'>کاری با موعد در این فیلتر نیست.</p>}
        </CardContent></Card>
      </div>}

      {view === 'graph' && <Card><CardHeader><CardTitle>گراف واگذاری و اجرا</CardTitle><CardDescription>پروژه را انتخاب کنید تا فقط کارهای همان پروژه و جهت واگذاری تا اجرا دیده شود.</CardDescription></CardHeader><CardContent><WorkGraph items={items} projects={projects} onWork={openTask} /></CardContent></Card>}

      {view === 'teams' && <div className='grid gap-4 xl:grid-cols-[1fr_1.4fr]'><div className='space-y-4'>
        <Card><CardHeader><CardTitle>تیم‌های اجرایی</CardTitle><CardDescription>ظرفیت کاری و عضویت هر تیم به کارهای واقعی وصل می‌شود.</CardDescription></CardHeader><CardContent className='space-y-2'>
          {teams.map((team) => <div key={team.id} className='rounded-lg border p-3'><div className='flex items-center justify-between gap-3'><span className='flex items-center gap-2'><span className='size-3 rounded-full' style={{ background: team.color }} /><span><strong className='block text-sm'>{team.name} {!team.active && <Badge variant='outline'>غیرفعال</Badge>}</strong><span className='text-muted-foreground text-xs'>{team.description || 'بدون توضیح'}</span></span></span><span className='text-muted-foreground text-xs'>{num.format(team.members)} عضو · {num.format(team.open_work)} کار باز</span>{canEdit && <Button size='sm' variant='ghost' onClick={() => { setEditingTeamId(editingTeamId === team.id ? null : team.id); setTeamEdit({ name: team.name, description: team.description, color: team.color, active: team.active }); }}>ویرایش</Button>}</div>
            {editingTeamId === team.id && <div className='mt-3 grid gap-2 border-t pt-3'><Input aria-label='نام ویرایش تیم' value={teamEdit.name} onChange={(e) => setTeamEdit((v) => ({ ...v, name: e.target.value }))} /><Input aria-label='شرح ویرایش تیم' value={teamEdit.description} onChange={(e) => setTeamEdit((v) => ({ ...v, description: e.target.value }))} /><div className='flex items-center gap-3'><Input aria-label='رنگ ویرایش تیم' type='color' className='h-9 w-18 p-1' value={teamEdit.color} onChange={(e) => setTeamEdit((v) => ({ ...v, color: e.target.value }))} /><label className='flex items-center gap-2 text-xs'><input type='checkbox' checked={teamEdit.active} onChange={(e) => setTeamEdit((v) => ({ ...v, active: e.target.checked }))} /> فعال</label><Button size='sm' disabled={teamSaving} onClick={saveTeam}>ذخیره</Button></div></div>}
          </div>)}
          {!teams.length && <p className='text-muted-foreground py-6 text-center text-sm'>هنوز تیمی تعریف نشده است.</p>}
        </CardContent></Card>
        {canEdit && <Card><CardHeader><CardTitle>تیم جدید</CardTitle></CardHeader><CardContent className='space-y-3'><Input aria-label='نام تیم' placeholder='مثلاً سئو فنی' value={teamName} onChange={(e) => setTeamName(e.target.value)} /><Input aria-label='توضیح تیم' placeholder='حوزهٔ مسئولیت تیم' value={teamDescription} onChange={(e) => setTeamDescription(e.target.value)} /><label className='flex items-center gap-2 text-xs'>رنگ تیم <Input aria-label='رنگ تیم' type='color' value={teamColor} onChange={(e) => setTeamColor(e.target.value)} className='h-10 w-20 p-1' /></label><Button onClick={createTeam} disabled={teamSaving || teamName.trim().length < 2}>ایجاد تیم</Button></CardContent></Card>}
      </div><Card><CardHeader><CardTitle>اعضا و مسئولیت‌ها</CardTitle><CardDescription>مدیر می‌تواند عضو را به تیم اختصاص دهد. نقش دسترسی کاربر از صفحهٔ مدیریت کاربران تنظیم می‌شود.</CardDescription></CardHeader><CardContent className='space-y-2'>
        {people.filter((person) => person.active).map((person) => <div key={person.id} className='flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3'><span><strong className='block text-sm'>{person.full_name}</strong><span className='text-muted-foreground text-xs'>{person.role === 'admin' ? 'مدیر' : person.role === 'analyst' ? 'تحلیل‌گر' : 'اپراتور کال‌سنتر'}</span></span><NativeSelect disabled={!canEdit} aria-label={`تیم ${person.full_name}`} value={person.team_id?.toString() || ''} onChange={(e) => void assignMember(person, e.target.value)} className='w-44'><NativeSelectOption value=''>بدون تیم</NativeSelectOption>{teams.filter((team) => team.active).map((team) => <NativeSelectOption key={team.id} value={String(team.id)}>{team.name}</NativeSelectOption>)}</NativeSelect></div>)}
        {canEdit && <Link className='text-primary mt-3 inline-block text-xs hover:underline' href='/dashboard/users'>مدیریت نقش و حساب کاربران ←</Link>}
      </CardContent></Card></div>}
    </>}

    <Dialog open={editing !== null} onOpenChange={(open) => { if (!open) setEditing(null); }}><DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-4xl' dir='rtl'><DialogHeader><DialogTitle>{editing === 'new' ? 'کار جدید' : editing?.title}</DialogTitle><DialogDescription>{editing && editing !== 'new' ? `ثبت‌شده در ${formatUserDateTime(editing.created_at, calendar)} · سازنده: ${editing.created_by_name || 'سیستم'} · مسئول: ${editing.owner_name || 'هنوز واگذار نشده'}` : 'عنوان، پروژه و مسئول کافی است؛ جزئیات دیگر اختیاری‌اند.'}</DialogDescription></DialogHeader>
      {editing && editing !== 'new' && !canUpdate(editing) ? <div className='space-y-4'>
        <div className='flex flex-wrap gap-2'><Badge variant='outline'>{statusLabel[editing.status]}</Badge><Badge variant='outline'>{priorityLabel[editing.priority]}</Badge><Badge variant='secondary'>{editing.site_name}</Badge></div>
        <div className='grid gap-2 text-sm sm:grid-cols-2'><p><span className='text-muted-foreground'>مسئول: </span>{editing.owner_name || 'بی‌مسئول'}</p><p><span className='text-muted-foreground'>موعد: </span>{dateText(editing.due_at)}</p></div>
        <div className='min-h-20 whitespace-pre-wrap rounded-lg border bg-muted/20 p-3 text-sm leading-7'>{editing.description || 'توضیحی برای این تسک ثبت نشده است.'}</div>
        {editing.url && <a className='text-primary block break-all text-sm underline' href={editing.url} target='_blank' rel='noreferrer'>{editing.url}</a>}
        <TaskDiscussion key={editing.id} item={editing} canEdit={false} onOpenTask={openTask} onChanged={() => void refresh(true)} />
      </div> : editing && <div className='grid gap-3 sm:grid-cols-2'>
        <label className='space-y-1 text-xs'>پروژه<NativeSelect disabled={editing !== 'new'} value={form.site_id} onChange={(e) => setForm((f) => ({ ...f, site_id: e.target.value }))}><NativeSelectOption value=''>انتخاب پروژه</NativeSelectOption>{projects.filter((project) => canLead(project.site_id) || editing !== 'new').map((project) => <NativeSelectOption key={project.site_id} value={project.site_id}>{project.name}</NativeSelectOption>)}</NativeSelect></label>
        <label className='space-y-1 text-xs'>عنوان<Input disabled={!canManageEditing} value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} /></label>
        <label className='space-y-1 text-xs'>مسئول<NativeSelect disabled={!canAssignEditing} value={form.owner_id} onChange={(e) => { const person = people.find((row) => row.id === Number(e.target.value)); setForm((f) => ({ ...f, owner_id: e.target.value, team_id: f.team_id || person?.team_id?.toString() || '' })); }}><NativeSelectOption value=''>بی‌مسئول</NativeSelectOption>{people.filter((person) => person.active && person.role !== 'call_center' && (!form.team_id || person.team_id?.toString() === form.team_id || person.id.toString() === form.owner_id)).map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect></label>
        <label className='space-y-1 text-xs'>وضعیت<NativeSelect disabled={!canUpdateEditing} value={form.status} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as WorkStatus }))}>{(Object.keys(statusLabel) as WorkStatus[]).filter((status) => canManageEditing || !['verified', 'rejected', 'deferred', 'approved', 'assigned'].includes(status)).map((status) => <NativeSelectOption key={status} value={status}>{statusLabel[status]}</NativeSelectOption>)}</NativeSelect></label>
        <label className='space-y-1 text-xs'>اولویت<NativeSelect disabled={!canManageEditing} value={form.priority} onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value as WorkPriority }))}>{(Object.keys(priorityLabel) as WorkPriority[]).map((priority) => <NativeSelectOption key={priority} value={priority}>{priorityLabel[priority]}</NativeSelectOption>)}</NativeSelect></label>
        <label className='space-y-1 text-xs'>موعد اختیاری<UserDateInput label='موعد کار' mode='datetime-local' disabled={!canManageEditing} value={form.due_at} onChange={(value) => setForm((f) => ({ ...f, due_at: value }))} /></label>
        <details className='sm:col-span-2 rounded-lg border p-3'><summary className='cursor-pointer text-sm font-medium'>جزئیات بیشتر · شرح، لینک، زمان‌بندی و زیرکار</summary><div className='mt-3 grid gap-3 sm:grid-cols-2'>
        <label className='space-y-1 text-xs sm:col-span-2'>شرح کار<Textarea disabled={!canManageEditing} value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} /></label>
        <label className='space-y-1 text-xs sm:col-span-2'>URL مرتبط<Input disabled={!canManageEditing} dir='ltr' value={form.url} onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))} /></label>
        <label className='space-y-1 text-xs'>تیم<NativeSelect disabled={!canManageEditing} value={form.team_id} onChange={(e) => setForm((f) => ({ ...f, team_id: e.target.value }))}><NativeSelectOption value=''>بدون تیم</NativeSelectOption>{teams.filter((team) => team.active).map((team) => <NativeSelectOption key={team.id} value={String(team.id)}>{team.name}</NativeSelectOption>)}</NativeSelect></label>
        <label className='space-y-1 text-xs'>شروع<UserDateInput label='شروع کار' mode='datetime-local' disabled={!canManageEditing} value={form.start_at} onChange={(value) => setForm((f) => ({ ...f, start_at: value }))} /></label>
        <label className='space-y-1 text-xs'>ساعت برآوردی<Input disabled={!canManageEditing} type='number' min={0} max={1000} step={.5} value={form.estimated_hours} onChange={(e) => setForm((f) => ({ ...f, estimated_hours: e.target.value }))} /></label>
        <label className='space-y-1 text-xs'>درصد پیشرفت<Input disabled={!canUpdateEditing} type='number' min={0} max={100} value={form.progress_percent} onChange={(e) => setForm((f) => ({ ...f, progress_percent: e.target.value }))} /></label>
        <label className='space-y-1 text-xs'>زیرکارِ<NativeSelect disabled={!canManageEditing} value={form.parent_id} onChange={(e) => setForm((f) => ({ ...f, parent_id: e.target.value }))}><NativeSelectOption value=''>کار اصلی</NativeSelectOption>{(data?.items || []).filter((item) => item.site_id === form.site_id && (editing === 'new' || item.id !== editing.id)).map((item) => <NativeSelectOption key={item.id} value={String(item.id)}>{item.title}</NativeSelectOption>)}</NativeSelect></label>
        <label className='space-y-1 text-xs'>مایلستون<NativeSelect disabled={!canManageEditing} value={form.milestone_id} onChange={(e) => setForm((f) => ({ ...f, milestone_id: e.target.value }))}><NativeSelectOption value=''>بدون مایلستون</NativeSelectOption>{milestones.map((entry) => <NativeSelectOption key={entry.id} value={String(entry.id)}>{entry.title}</NativeSelectOption>)}</NativeSelect></label>
        </div></details>
        {form.status === 'blocked' && <label className='space-y-1 text-xs sm:col-span-2'>دلیل مانع<Textarea disabled={!canUpdateEditing} value={form.blocked_reason} onChange={(e) => setForm((f) => ({ ...f, blocked_reason: e.target.value }))} /></label>}
        {form.status === 'verified' && <label className='space-y-1 text-xs sm:col-span-2'>نتیجهٔ سنجش<Textarea disabled={!canManageEditing} value={form.verification_note} onChange={(e) => setForm((f) => ({ ...f, verification_note: e.target.value }))} /></label>}
        {canUpdateEditing && <label className='space-y-1 text-xs sm:col-span-2'>یادداشت این تغییر<Input value={form.note} onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} placeholder='پیشرفت، مانع یا تصمیم انجام‌شده را ثبت کنید' /></label>}
        <div className='flex flex-wrap gap-2 sm:col-span-2'>{canUpdateEditing && <Button onClick={saveTask} disabled={saving}>{saving ? 'در حال ذخیره…' : 'ذخیرهٔ کار'}</Button>}{editing !== 'new' && canUpdate(editing) && editing.status !== 'verified' && <Button variant='outline' onClick={() => void completeTask(editing)}>✓ انجام شد</Button>}{editing !== 'new' && canUpdate(editing) && <Button variant='outline' onClick={() => void deleteTask(editing)}>حذف کار</Button>}</div>
        {editing !== 'new' && <TaskDiscussion key={editing.id} item={editing} canEdit={canUpdate(editing)} onOpenTask={openTask} onChanged={() => void refresh(true)} />}
        {editing !== 'new' && <details key={editing.id} onToggle={(event) => setShowExecutionDetails(event.currentTarget.open)} className='sm:col-span-2 rounded-lg border p-3'><summary className='cursor-pointer text-sm font-medium'>جزئیات اجرایی · چک‌لیست، وابستگی و زمان</summary>{showExecutionDetails && <div className='mt-3'><TaskExecutionDetails item={editing} items={data?.items || []} people={people} canEdit={canManageEditing} canLogTime={canUpdate(editing)} canLogOthers={false} meId={meId} onChanged={() => void refresh(true)} /></div>}</details>}
      </div>}
    </DialogContent></Dialog>
  </div>;
}
