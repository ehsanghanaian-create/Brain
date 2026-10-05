'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { closestCorners, DndContext, DragOverlay, KeyboardSensor, PointerSensor, useDroppable, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import type { WorkStatus } from '@/features/reports/types';
import { commandApi, type BoardViewConfig, type CommandWorkItem, type ProjectMember, type SavedBoardView, type WorkCustomField, type WorkLabel, type WorkPerson, type WorkPriority } from '../api';

type Lane = { key: string; title: string; status: WorkStatus; statuses: WorkStatus[]; color: string };
const lanes: Lane[] = [
  { key: 'inbox', title: 'ورودی', status: 'new', statuses: ['new', 'triaged'], color: 'bg-slate-500' },
  { key: 'ready', title: 'آمادهٔ اجرا', status: 'assigned', statuses: ['approved', 'assigned'], color: 'bg-violet-500' },
  { key: 'doing', title: 'در حال اجرا', status: 'in_progress', statuses: ['in_progress'], color: 'bg-sky-500' },
  { key: 'review', title: 'بازبینی و سنجش', status: 'review', statuses: ['review', 'published', 'measurement_pending'], color: 'bg-amber-500' },
  { key: 'blocked', title: 'مسدود', status: 'blocked', statuses: ['blocked'], color: 'bg-rose-500' },
  { key: 'done', title: 'نهایی', status: 'verified', statuses: ['verified', 'rejected', 'deferred'], color: 'bg-emerald-500' }
];
const priorityText: Record<WorkPriority, string> = { critical: 'فوری', high: 'بالا', normal: 'معمولی', low: 'پایین' };
const priorityColor: Record<WorkPriority, string> = { critical: 'bg-rose-500', high: 'bg-orange-500', normal: 'bg-sky-500', low: 'bg-slate-500' };
const number = new Intl.NumberFormat('fa-IR');
const laneOf = (status: WorkStatus) => lanes.find((lane) => lane.statuses.includes(status))!;
const ordered = (rows: CommandWorkItem[]) => [...rows].sort((a, b) => (a.board_order ?? a.id * 1024) - (b.board_order ?? b.id * 1024) || a.id - b.id);
const dateInput = (value: string | null) => value ? new Date(value).toISOString().slice(0, 10) : '';

function BoardCard({ item, people, canUpdate, canLead, busy, selected, onSelect, onOpen, onQuickSave }: {
  item: CommandWorkItem; people: WorkPerson[]; canUpdate: boolean; canLead: boolean; busy: boolean;
  selected: boolean; onSelect: () => void;
  onOpen: () => void; onQuickSave: (patch: Record<string, unknown>) => Promise<boolean>;
}) {
  const [quick, setQuick] = useState(false);
  const [owner, setOwner] = useState(item.owner_id?.toString() || '');
  const [due, setDue] = useState(dateInput(item.due_at));
  const [priority, setPriority] = useState<WorkPriority>(item.priority);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: `card:${item.id}`, disabled: !canUpdate || busy });
  const overdue = Boolean(item.due_at && !['verified', 'rejected', 'deferred'].includes(item.status) && Date.parse(item.due_at) < Date.now());
  return <article ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className={`rounded-xl border bg-card p-3 shadow-sm transition-shadow hover:shadow-md ${isDragging ? 'opacity-40' : ''} ${overdue ? 'border-rose-500/50' : ''} ${selected ? 'ring-2 ring-primary/50' : ''}`}>
    <div className='flex items-start justify-between gap-2'>{canLead && <input type='checkbox' aria-label={`انتخاب ${item.title}`} checked={selected} onChange={onSelect} className='mt-1' />}<button type='button' onClick={onOpen} className='min-w-0 flex-1 text-right'><strong className='block text-sm leading-6'>{item.title}</strong><span className='text-muted-foreground mt-1 block truncate text-[11px]'>{item.site_name}{item.parent_id ? ' · زیرکار' : ''}</span></button>{canUpdate && <button type='button' {...attributes} {...listeners} aria-label={`جابه‌جایی ${item.title}`} className='touch-none rounded-md border px-2 py-1 text-muted-foreground hover:bg-muted' title='گرفتن و جابه‌جایی'>⠿</button>}</div>
    {!!item.labels?.length && <div className='mt-2 flex flex-wrap gap-1'>{item.labels.map((label) => <span key={label.id} className='rounded-md px-1.5 py-0.5 text-[10px] text-white' style={{ backgroundColor: label.color }}>{label.name}</span>)}</div>}
    {!!item.custom_fields?.length && <div className='mt-2 space-y-1 text-[10px] text-muted-foreground'>{item.custom_fields.slice(0, 2).map((field) => <p key={field.id} className='truncate'>{field.name}: <span className='text-foreground'>{String(field.value)}</span></p>)}</div>}
    <div className='mt-3 flex flex-wrap gap-1.5'><Badge variant='outline' className={item.priority === 'critical' ? 'border-rose-500/40 text-rose-600' : ''}>{priorityText[item.priority]}</Badge>{overdue && <Badge variant='destructive'>عقب‌افتاده</Badge>}{item.checklist_total > 0 && <Badge variant='secondary'>☑ {number.format(item.checklist_done)}/{number.format(item.checklist_total)}</Badge>}</div>
    <div className='text-muted-foreground mt-3 flex items-center justify-between gap-2 text-[11px]'><span className='truncate'>{item.owner_name || 'بی‌مسئول'}</span><span>{item.due_at ? new Date(item.due_at).toLocaleDateString('fa-IR', { month: 'short', day: 'numeric' }) : 'بی‌موعد'}</span></div>
    {(item.progress_percent || 0) > 0 && <div className='mt-2 h-1 overflow-hidden rounded-full bg-muted'><div className='h-full rounded-full bg-emerald-500' style={{ width: `${item.progress_percent || 0}%` }} /></div>}
    {canLead && <div className='mt-2 border-t pt-2'><button type='button' onClick={() => { setOwner(item.owner_id?.toString() || ''); setDue(dateInput(item.due_at)); setPriority(item.priority); setQuick((value) => !value); }} className='text-primary text-[11px] hover:underline'>{quick ? 'بستن ویرایش سریع' : 'واگذاری و موعد'}</button>{quick && <div className='mt-2 space-y-2'><NativeSelect aria-label={`مسئول ${item.title}`} value={owner} onChange={(event) => setOwner(event.target.value)}><NativeSelectOption value=''>بی‌مسئول</NativeSelectOption>{people.map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect><Input aria-label={`موعد ${item.title}`} type='date' value={due} onChange={(event) => setDue(event.target.value)} /><NativeSelect aria-label={`اولویت ${item.title}`} value={priority} onChange={(event) => setPriority(event.target.value as WorkPriority)}>{(Object.keys(priorityText) as WorkPriority[]).map((key) => <NativeSelectOption key={key} value={key}>{priorityText[key]}</NativeSelectOption>)}</NativeSelect><Button size='sm' disabled={busy} onClick={() => void onQuickSave({ owner_id: owner ? Number(owner) : null, due_at: due ? new Date(`${due}T12:00:00`).toISOString() : null, priority }).then((saved) => { if (saved) setQuick(false); })}>ذخیره</Button></div>}</div>}
  </article>;
}

function BoardLane({ lane, items, children, fullscreen, grow }: { lane: Lane; items: CommandWorkItem[]; children: ReactNode; fullscreen: boolean; grow: boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: `lane:${lane.key}` });
  return <section ref={setNodeRef} className={`flex min-h-80 min-w-[300px] shrink-0 flex-col rounded-2xl border bg-muted/30 ${grow ? 'grow' : 'w-[300px]'} ${fullscreen ? 'h-[calc(100vh-150px)]' : 'max-h-[72vh]'} ${isOver ? 'ring-2 ring-primary/50' : ''}`}><div className='flex items-center justify-between gap-2 border-b px-3 py-3'><div className='flex items-center gap-2'><span className={`size-2.5 rounded-full ${lane.color}`} /><h3 className='text-sm font-bold'>{lane.title}</h3></div><Badge variant='secondary'>{number.format(items.length)}</Badge></div><div className='min-h-20 flex-1 space-y-2 overflow-y-auto p-2'><SortableContext items={items.map((item) => `card:${item.id}`)} strategy={verticalListSortingStrategy}>{children}</SortableContext></div></section>;
}

export function TeamBoard({ items, sites, people, preferredSiteId, meId, canLead, canUpdate, onOpen, onPrepareStatus, onSiteChange, onChanged }: {
  items: CommandWorkItem[]; sites: { site_id: string; name: string }[]; people: WorkPerson[]; preferredSiteId?: string;
  meId: number | null; canLead: (siteId: string) => boolean; canUpdate: (item: CommandWorkItem) => boolean;
  onOpen: (item: CommandWorkItem) => void; onPrepareStatus: (item: CommandWorkItem, status: WorkStatus) => void;
  onSiteChange: (siteId: string) => void; onChanged: () => Promise<void>;
}) {
  const [siteId, setSiteId] = useState(preferredSiteId || sites[0]?.site_id || '');
  const [localItems, setLocalItems] = useState(items);
  const [query, setQuery] = useState('');
  const [ownerFilter, setOwnerFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [labelFilter, setLabelFilter] = useState<number | null>(null);
  const [mine, setMine] = useState(false);
  const [groupBy, setGroupBy] = useState<BoardViewConfig['group_by']>('status');
  const [labels, setLabels] = useState<WorkLabel[]>([]);
  const [labelName, setLabelName] = useState('');
  const [labelColor, setLabelColor] = useState('#0ea5e9');
  const [fields, setFields] = useState<WorkCustomField[]>([]);
  const [fieldName, setFieldName] = useState('');
  const [fieldType, setFieldType] = useState<WorkCustomField['field_type']>('text');
  const [fieldOptions, setFieldOptions] = useState('');
  const [views, setViews] = useState<SavedBoardView[]>([]);
  const [activeViewId, setActiveViewId] = useState('');
  const [viewName, setViewName] = useState('');
  const [showViewSave, setShowViewSave] = useState(false);
  const [showLabelManager, setShowLabelManager] = useState(false);
  const [showFieldManager, setShowFieldManager] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [bulkOwner, setBulkOwner] = useState('');
  const [bulkDue, setBulkDue] = useState('');
  const [bulkPriority, setBulkPriority] = useState('');
  const [draftLane, setDraftLane] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [draftOwner, setDraftOwner] = useState('');
  const [draftDue, setDraftDue] = useState('');
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [busy, setBusy] = useState(false);
  const [boardLoading, setBoardLoading] = useState(false);
  const [dragged, setDragged] = useState<CommandWorkItem | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  useEffect(() => { if (!siteId) return; let active = true; setBoardLoading(true);
    void (async () => { try { const all: CommandWorkItem[] = []; let cursor = 0;
      do { const page = await commandApi.boardPage(siteId, cursor); all.push(...page.items);
        cursor = page.next_after_id || 0; } while (cursor && active);
      if (active) setLocalItems((current) => [...current.filter((item) => item.site_id !== siteId), ...all]);
    } catch (cause) { if (active) toast.error(cause instanceof Error ? cause.message : 'بارگیری کامل برد انجام نشد'); }
    finally { if (active) setBoardLoading(false); } })();
    return () => { active = false; };
  }, [items, siteId]);
  useEffect(() => { if (!fullscreen) return; const previous = document.body.style.overflow; document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, [fullscreen]);
  useEffect(() => { if (preferredSiteId) setSiteId(preferredSiteId); else if (!siteId && sites[0]) setSiteId(sites[0].site_id); }, [preferredSiteId, siteId, sites]);
  useEffect(() => { if (!siteId) return; let active = true; setMembers([]); setSelectedIds([]); setActiveViewId('');
    void Promise.all([commandApi.projectMembers(siteId), commandApi.labels(siteId), commandApi.savedViews(siteId), commandApi.customFields(siteId)])
      .then(([memberRows, labelRows, viewRows, fieldRows]) => { if (active) { setMembers(memberRows); setLabels(labelRows); setViews(viewRows); setFields(fieldRows); } })
      .catch(() => { if (active) { setMembers([]); setLabels([]); setViews([]); setFields([]); } });
    return () => { active = false; };
  }, [siteId]);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const siteItems = useMemo(() => localItems.filter((item) => item.site_id === siteId), [localItems, siteId]);
  const eligiblePeople = people.filter((person) => person.active && (person.role === 'admin' || members.some((member) => member.user_id === person.id && member.responsibility !== 'viewer')));
  const filtered = siteItems.filter((item) => (!query || `${item.title} ${item.description || ''} ${item.url || ''}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())) &&
    (!ownerFilter || item.owner_id?.toString() === ownerFilter) && (!priorityFilter || item.priority === priorityFilter) &&
    (!labelFilter || item.labels?.some((label) => label.id === labelFilter)) && (!mine || item.owner_id === meId));
  const activeLanes: Lane[] = groupBy === 'status' ? lanes : groupBy === 'priority' ?
    (Object.keys(priorityText) as WorkPriority[]).map((key) => ({ key, title: priorityText[key], status: 'new' as WorkStatus, statuses: [], color: priorityColor[key] })) :
    [{ key: 'unassigned', title: 'بی‌مسئول', status: 'new' as WorkStatus, statuses: [], color: 'bg-slate-500' },
      ...people.filter((person) => eligiblePeople.some((eligible) => eligible.id === person.id) || siteItems.some((item) => item.owner_id === person.id))
        .map((person) => ({ key: `owner:${person.id}`, title: person.full_name, status: 'new' as WorkStatus, statuses: [], color: 'bg-violet-500' }))];
  const belongsToLane = (item: CommandWorkItem, lane: Lane) => groupBy === 'status' ? lane.statuses.includes(item.status) :
    groupBy === 'priority' ? item.priority === lane.key : lane.key === (item.owner_id ? `owner:${item.owner_id}` : 'unassigned');
  const rowsFor = (lane: Lane) => ordered(filtered.filter((item) => belongsToLane(item, lane)));

  async function createCard(lane: Lane) {
    if (!draftTitle.trim() || !siteId) return;
    if (lane.key !== 'inbox' && (!draftOwner || !draftDue)) { toast.error('برای کار فعال، مسئول و موعد را مشخص کنید'); return; }
    setBusy(true);
    try { await commandApi.createWork(siteId, { title: draftTitle.trim(), status: lane.status,
      owner_id: draftOwner ? Number(draftOwner) : null, due_at: draftDue ? new Date(`${draftDue}T12:00:00`).toISOString() : null });
      setDraftTitle(''); setDraftOwner(''); setDraftDue(''); setDraftLane(null); await onChanged(); toast.success('کارت به برد اضافه شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ثبت کارت انجام نشد'); }
    finally { setBusy(false); }
  }
  async function quickSave(item: CommandWorkItem, patch: Record<string, unknown>): Promise<boolean> {
    setBusy(true);
    try { await commandApi.updateWork(item, patch); await onChanged(); toast.success('کارت به‌روز شد'); return true; }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ویرایش کارت انجام نشد'); return false; }
    finally { setBusy(false); }
  }
  function applyView(view: SavedBoardView) {
    setActiveViewId(String(view.id)); setQuery(view.config.query); setOwnerFilter(view.config.owner_filter);
    setPriorityFilter(view.config.priority_filter); setLabelFilter(view.config.label_id);
    setMine(view.config.mine); setGroupBy(view.config.group_by); setSelectedIds([]);
  }
  async function saveView() {
    if (viewName.trim().length < 2) { toast.error('برای نما نام مشخص کنید'); return; }
    setBusy(true);
    try {
      const created = await commandApi.createSavedView(siteId, viewName.trim(), {
        query, owner_filter: ownerFilter, priority_filter: priorityFilter as WorkPriority | '',
        label_id: labelFilter, mine, group_by: groupBy
      });
      setViews((current) => [...current, created].sort((a, b) => a.name.localeCompare(b.name)));
      setActiveViewId(String(created.id)); setViewName(''); setShowViewSave(false); toast.success('نمای شخصی ذخیره شد');
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ذخیرهٔ نما انجام نشد'); }
    finally { setBusy(false); }
  }
  async function removeView() {
    if (!activeViewId) return;
    setBusy(true);
    try { await commandApi.deleteSavedView(siteId, Number(activeViewId));
      setViews((current) => current.filter((view) => view.id !== Number(activeViewId)));
      setActiveViewId(''); toast.success('نما حذف شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'حذف نما انجام نشد'); }
    finally { setBusy(false); }
  }
  async function createLabel() {
    if (labelName.trim().length < 2) return;
    setBusy(true);
    try { const created = await commandApi.createLabel(siteId, { name: labelName.trim(), color: labelColor });
      setLabels((current) => [...current, created].sort((a, b) => a.name.localeCompare(b.name)));
      setLabelName(''); toast.success('برچسب پروژه ساخته شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ساخت برچسب انجام نشد'); }
    finally { setBusy(false); }
  }
  async function removeLabel(label: WorkLabel) {
    if (!window.confirm(`برچسب «${label.name}» از همهٔ کارت‌های این پروژه حذف شود؟`)) return;
    setBusy(true);
    try { await commandApi.deleteLabel(siteId, label.id); setLabels((current) => current.filter((row) => row.id !== label.id));
      if (labelFilter === label.id) setLabelFilter(null); await onChanged(); toast.success('برچسب حذف شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'حذف برچسب انجام نشد'); }
    finally { setBusy(false); }
  }
  async function createField() {
    if (fieldName.trim().length < 2) return;
    const options = fieldType === 'select' ? fieldOptions.split(',').map((value) => value.trim()).filter(Boolean) : [];
    if (fieldType === 'select' && !options.length) { toast.error('گزینه‌های فیلد انتخابی را بنویسید'); return; }
    setBusy(true);
    try { const created = await commandApi.createCustomField(siteId, { name: fieldName.trim(), field_type: fieldType, options });
      setFields((current) => [...current, created]); setFieldName(''); setFieldOptions('');
      toast.success('فیلد پروژه ساخته شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ساخت فیلد انجام نشد'); }
    finally { setBusy(false); }
  }
  async function removeField(field: WorkCustomField) {
    if (!window.confirm(`فیلد «${field.name}» و مقدار آن در همهٔ کارت‌های این پروژه حذف شود؟`)) return;
    setBusy(true);
    try { await commandApi.deleteCustomField(siteId, field.id);
      setFields((current) => current.filter((row) => row.id !== field.id)); await onChanged(); toast.success('فیلد حذف شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'حذف فیلد انجام نشد'); }
    finally { setBusy(false); }
  }
  async function applyBulk() {
    const patch: { owner_id?: number | null; due_at?: string | null; priority?: WorkPriority } = {};
    if (bulkOwner) patch.owner_id = bulkOwner === 'unassigned' ? null : Number(bulkOwner);
    if (bulkDue) patch.due_at = new Date(`${bulkDue}T12:00:00`).toISOString();
    if (bulkPriority) patch.priority = bulkPriority as WorkPriority;
    if (!Object.keys(patch).length) { toast.error('تغییری برای کارت‌های انتخابی مشخص کنید'); return; }
    setBusy(true);
    try { const result = await commandApi.bulkUpdate(siteId, selectedIds, patch);
      await onChanged(); setSelectedIds([]); setBulkOwner(''); setBulkDue(''); setBulkPriority('');
      toast.success(`${number.format(result.updated)} کار به‌روزرسانی شد`); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ویرایش گروهی انجام نشد'); }
    finally { setBusy(false); }
  }
  async function handleDragEnd(event: DragEndEvent) {
    setDragged(null);
    const activeId = Number(String(event.active.id).replace('card:', ''));
    const item = localItems.find((row) => row.id === activeId);
    const target = event.over?.id ? String(event.over.id) : '';
    if (!item || !target || !canUpdate(item)) return;
    const overCard = target.startsWith('card:') ? localItems.find((row) => row.id === Number(target.slice(5))) : null;
    const targetLane = overCard ? activeLanes.find((lane) => belongsToLane(overCard, lane)) : activeLanes.find((lane) => `lane:${lane.key}` === target);
    if (!targetLane || (overCard && overCard.id === item.id)) return;
    const nextStatus = groupBy === 'status' && laneOf(item.status).key !== targetLane.key ? targetLane.status : item.status;
    const nextOwner = groupBy === 'owner' ? (targetLane.key === 'unassigned' ? null : Number(targetLane.key.slice(6))) : item.owner_id;
    const nextPriority = groupBy === 'priority' ? targetLane.key as WorkPriority : item.priority;
    if (groupBy === 'status' && (nextStatus === 'blocked' || nextStatus === 'verified')) { setFullscreen(false); onPrepareStatus(item, nextStatus); return; }
    if (groupBy === 'status' && nextStatus !== item.status && ['approved', 'assigned', 'in_progress', 'review', 'published', 'measurement_pending'].includes(nextStatus) && (!item.owner_id || !item.due_at)) {
      setFullscreen(false); onPrepareStatus(item, nextStatus); toast.info('برای انتقال به این مرحله، مسئول و موعد را تکمیل کنید'); return;
    }
    if (groupBy === 'owner' && nextOwner === null && ['approved', 'assigned', 'in_progress', 'review', 'published', 'measurement_pending', 'blocked'].includes(item.status)) {
      toast.error('کار فعال باید مسئول داشته باشد'); return;
    }
    const siblings = ordered(localItems.filter((row) => row.site_id === siteId && belongsToLane(row, targetLane) && row.id !== item.id));
    const index = overCard ? siblings.findIndex((row) => row.id === overCard.id) : siblings.length;
    const insertion = index < 0 ? siblings.length : index;
    const previous = siblings[insertion - 1]?.board_order;
    const next = siblings[insertion]?.board_order;
    const order = previous !== undefined && next !== undefined ? (previous + next) / 2 :
      previous !== undefined ? previous + 1024 : next !== undefined ? next - 1024 : 1024;
    if (nextStatus === item.status && nextOwner === item.owner_id && nextPriority === item.priority && order === item.board_order) return;
    const before = localItems;
    setLocalItems((current) => current.map((row) => row.id === item.id ? { ...row, status: nextStatus, owner_id: nextOwner,
      owner_name: eligiblePeople.find((person) => person.id === nextOwner)?.full_name || null, priority: nextPriority, board_order: order } : row));
    setBusy(true);
    try { await commandApi.updateWork(item, { status: nextStatus, owner_id: nextOwner, priority: nextPriority,
      board_order: order }); await onChanged(); toast.success('جای کارت ذخیره شد'); }
    catch (cause) { setLocalItems(before); toast.error(cause instanceof Error ? cause.message : 'جابه‌جایی کارت انجام نشد'); }
    finally { setBusy(false); }
  }

  return <div className={fullscreen ? 'fixed inset-0 z-[60] space-y-3 overflow-y-auto bg-background p-4' : 'space-y-3'} dir='rtl'>
    <div className='flex flex-wrap items-center gap-2 rounded-xl border bg-card p-3'>
      <strong className='ml-2 text-sm'>برد پروژه</strong>
      <NativeSelect aria-label='پروژهٔ برد' value={siteId} onChange={(event) => { setSiteId(event.target.value); onSiteChange(event.target.value); }} className='min-w-44'>{sites.map((site) => <NativeSelectOption key={site.site_id} value={site.site_id}>{site.name}</NativeSelectOption>)}</NativeSelect>
      <NativeSelect aria-label='گروه‌بندی برد' value={groupBy} onChange={(event) => { setGroupBy(event.target.value as BoardViewConfig['group_by']); setSelectedIds([]); }} className='w-36'><NativeSelectOption value='status'>بر اساس مرحله</NativeSelectOption><NativeSelectOption value='owner'>بر اساس مسئول</NativeSelectOption><NativeSelectOption value='priority'>بر اساس اولویت</NativeSelectOption></NativeSelect>
      <Input aria-label='جست‌وجوی کارت در برد' placeholder='جست‌وجوی کارت…' value={query} onChange={(event) => setQuery(event.target.value)} className='min-w-40 flex-1' />
      <NativeSelect aria-label='فیلتر مسئول برد' value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)} className='w-36'><NativeSelectOption value=''>همهٔ مسئولان</NativeSelectOption>{people.filter((person) => person.active).map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect>
      <NativeSelect aria-label='فیلتر اولویت برد' value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)} className='w-28'><NativeSelectOption value=''>همهٔ اولویت‌ها</NativeSelectOption>{(Object.keys(priorityText) as WorkPriority[]).map((key) => <NativeSelectOption key={key} value={key}>{priorityText[key]}</NativeSelectOption>)}</NativeSelect>
      <NativeSelect aria-label='فیلتر برچسب برد' value={labelFilter?.toString() || ''} onChange={(event) => setLabelFilter(event.target.value ? Number(event.target.value) : null)} className='w-36'><NativeSelectOption value=''>همهٔ برچسب‌ها</NativeSelectOption>{labels.map((label) => <NativeSelectOption key={label.id} value={String(label.id)}>{label.name}</NativeSelectOption>)}</NativeSelect>
      <Button size='sm' variant={mine ? 'default' : 'outline'} onClick={() => setMine((value) => !value)}>فقط کارهای من</Button>
      <Button size='sm' variant='outline' onClick={() => setFullscreen((value) => !value)}>{fullscreen ? 'خروج از تمام‌صفحه' : 'نمای تمام‌صفحه'}</Button>
    </div>
    <div className='flex flex-wrap items-center gap-2 rounded-xl border bg-card p-2'>
      <NativeSelect aria-label='نمای ذخیره‌شده' value={activeViewId} onChange={(event) => { const selected = views.find((view) => view.id === Number(event.target.value)); if (selected) applyView(selected); else setActiveViewId(''); }} className='w-44'><NativeSelectOption value=''>نمای دلخواه</NativeSelectOption>{views.map((view) => <NativeSelectOption key={view.id} value={String(view.id)}>{view.name}</NativeSelectOption>)}</NativeSelect>
      <Button size='sm' variant='outline' onClick={() => setShowViewSave((value) => !value)}>ذخیرهٔ نمای فعلی</Button>
      {showViewSave && <><Input aria-label='نام نمای جدید' placeholder='نام نمای جدید' value={viewName} onChange={(event) => setViewName(event.target.value)} className='w-40' /><Button size='sm' disabled={busy || viewName.trim().length < 2} onClick={() => void saveView()}>ثبت نما</Button></>}
      {activeViewId && <Button size='sm' variant='ghost' disabled={busy} onClick={() => void removeView()}>حذف نمای من</Button>}
      {canLead(siteId) && <><span className='mx-1 h-6 border-r' /><Button size='sm' variant='outline' onClick={() => setShowLabelManager((value) => !value)}>برچسب‌های پروژه ({number.format(labels.length)})</Button><Button size='sm' variant='outline' onClick={() => setShowFieldManager((value) => !value)}>فیلدهای پروژه ({number.format(fields.length)})</Button></>}
    </div>
    {showLabelManager && canLead(siteId) && <div className='flex flex-wrap items-center gap-2 rounded-xl border bg-card p-3'><Input aria-label='نام برچسب پروژه' placeholder='برچسب جدید' value={labelName} onChange={(event) => setLabelName(event.target.value)} className='w-40' /><input aria-label='رنگ برچسب' type='color' value={labelColor} onChange={(event) => setLabelColor(event.target.value)} className='h-8 w-10 cursor-pointer' /><Button size='sm' disabled={busy || labelName.trim().length < 2} onClick={() => void createLabel()}>ساخت برچسب</Button><span className='mx-1 h-6 border-r' />{labels.map((label) => <span key={label.id} className='inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-white' style={{ backgroundColor: label.color }}>{label.name}<button type='button' aria-label={`حذف برچسب ${label.name}`} disabled={busy} onClick={() => void removeLabel(label)}>×</button></span>)}</div>}
    {showFieldManager && canLead(siteId) && <div className='flex flex-wrap items-center gap-2 rounded-xl border bg-card p-3'><Input aria-label='نام فیلد پروژه' placeholder='نام فیلد جدید' value={fieldName} onChange={(event) => setFieldName(event.target.value)} className='w-40' /><NativeSelect aria-label='نوع فیلد پروژه' value={fieldType} onChange={(event) => setFieldType(event.target.value as WorkCustomField['field_type'])} className='w-36'><NativeSelectOption value='text'>متن</NativeSelectOption><NativeSelectOption value='number'>عدد</NativeSelectOption><NativeSelectOption value='date'>تاریخ</NativeSelectOption><NativeSelectOption value='select'>انتخابی</NativeSelectOption></NativeSelect>{fieldType === 'select' && <Input aria-label='گزینه‌های فیلد پروژه' placeholder='گزینه‌ها، جدا با ویرگول' value={fieldOptions} onChange={(event) => setFieldOptions(event.target.value)} className='w-56' />}<Button size='sm' disabled={busy || fieldName.trim().length < 2} onClick={() => void createField()}>ساخت فیلد</Button><span className='mx-1 h-6 border-r' />{fields.map((field) => <Badge key={field.id} variant='secondary' className='gap-1'>{field.name}<button type='button' aria-label={`حذف فیلد ${field.name}`} disabled={busy} onClick={() => void removeField(field)}>×</button></Badge>)}</div>}
    {!!selectedIds.length && <div className='flex flex-wrap items-center gap-2 rounded-xl border border-primary/40 bg-primary/5 p-3 text-xs'><strong>{number.format(selectedIds.length)} کارت انتخاب شد</strong>
      <NativeSelect aria-label='مسئول گروهی' value={bulkOwner} onChange={(event) => setBulkOwner(event.target.value)} className='w-40'><NativeSelectOption value=''>مسئول: بدون تغییر</NativeSelectOption><NativeSelectOption value='unassigned'>حذف مسئول</NativeSelectOption>{eligiblePeople.map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect>
      <Input aria-label='موعد گروهی' type='date' value={bulkDue} onChange={(event) => setBulkDue(event.target.value)} className='w-40' />
      <NativeSelect aria-label='اولویت گروهی' value={bulkPriority} onChange={(event) => setBulkPriority(event.target.value)} className='w-36'><NativeSelectOption value=''>اولویت: بدون تغییر</NativeSelectOption>{(Object.keys(priorityText) as WorkPriority[]).map((key) => <NativeSelectOption key={key} value={key}>{priorityText[key]}</NativeSelectOption>)}</NativeSelect>
      <Button size='sm' disabled={busy || (!bulkOwner && !bulkDue && !bulkPriority)} onClick={() => void applyBulk()}>اعمال روی همه</Button><Button size='sm' variant='ghost' onClick={() => setSelectedIds([])}>لغو انتخاب</Button>
    </div>}
    <div className='text-muted-foreground flex flex-wrap items-center justify-between gap-2 text-xs'><span>{boardLoading ? 'در حال دریافت همهٔ کارت‌های پروژه… · ' : ''}{number.format(filtered.length)} کارت در این نما · کارت را از دستهٔ ⠿ بگیرید و جابه‌جا کنید؛ جابه‌جایی خودکار ذخیره می‌شود.</span><span>برای علت مانع یا تأیید نتیجه، فرم کارت باز می‌شود.</span></div>
    <DndContext sensors={sensors} collisionDetection={closestCorners} onDragStart={(event) => setDragged(localItems.find((item) => `card:${item.id}` === String(event.active.id)) || null)} onDragEnd={(event) => void handleDragEnd(event)} onDragCancel={() => setDragged(null)}><div className='flex gap-3 overflow-x-auto pb-4' dir='rtl'>{activeLanes.map((lane) => <BoardLane key={lane.key} lane={lane} items={rowsFor(lane)} fullscreen={fullscreen} grow={activeLanes.length <= 3}>
      {rowsFor(lane).map((item) => <BoardCard key={item.id} item={item} people={eligiblePeople} canUpdate={canUpdate(item)} canLead={canLead(item.site_id)} busy={busy} selected={selectedIds.includes(item.id)} onSelect={() => setSelectedIds((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} onOpen={() => { setFullscreen(false); onOpen(item); }} onQuickSave={(patch) => quickSave(item, patch)} />)}
      {!rowsFor(lane).length && <p className='text-muted-foreground rounded-lg border border-dashed p-5 text-center text-xs'>کارتی در این ستون نیست</p>}
      {groupBy === 'status' && canLead(siteId) && !['blocked', 'done'].includes(lane.key) && <div className='border-t pt-2'>{draftLane === lane.key ? <div className='space-y-2'><Input autoFocus aria-label={`عنوان کارت جدید ${lane.title}`} placeholder='عنوان کار جدید' value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void createCard(lane); }} />{lane.key !== 'inbox' && <><NativeSelect aria-label='مسئول کارت جدید' value={draftOwner} onChange={(event) => setDraftOwner(event.target.value)}><NativeSelectOption value=''>انتخاب مسئول</NativeSelectOption>{eligiblePeople.map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect><Input aria-label='موعد کارت جدید' type='date' value={draftDue} onChange={(event) => setDraftDue(event.target.value)} /></>}<div className='flex gap-2'><Button size='sm' disabled={busy || draftTitle.trim().length < 3} onClick={() => void createCard(lane)}>افزودن</Button><Button size='sm' variant='ghost' onClick={() => setDraftLane(null)}>انصراف</Button></div></div> : <button type='button' onClick={() => { setDraftLane(lane.key); setDraftTitle(''); setDraftOwner(''); setDraftDue(''); }} className='text-primary w-full rounded-lg p-2 text-right text-xs hover:bg-muted'>＋ افزودن کارت</button>}</div>}
    </BoardLane>)}</div><DragOverlay>{dragged && <div className='w-[280px] rotate-2 rounded-xl border bg-card p-3 shadow-xl'><strong className='text-sm'>{dragged.title}</strong><span className='text-muted-foreground mt-1 block text-xs'>{dragged.owner_name || 'بی‌مسئول'}</span></div>}</DragOverlay></DndContext>
  </div>;
}
