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
import { commandApi, type CommandWorkItem, type ProjectMember, type WorkPerson, type WorkPriority } from '../api';

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
const number = new Intl.NumberFormat('fa-IR');
const laneOf = (status: WorkStatus) => lanes.find((lane) => lane.statuses.includes(status))!;
const ordered = (rows: CommandWorkItem[]) => [...rows].sort((a, b) => (a.board_order ?? a.id * 1024) - (b.board_order ?? b.id * 1024) || a.id - b.id);
const dateInput = (value: string | null) => value ? new Date(value).toISOString().slice(0, 10) : '';

function BoardCard({ item, people, canUpdate, canLead, busy, onOpen, onQuickSave }: {
  item: CommandWorkItem; people: WorkPerson[]; canUpdate: boolean; canLead: boolean; busy: boolean;
  onOpen: () => void; onQuickSave: (patch: Record<string, unknown>) => Promise<boolean>;
}) {
  const [quick, setQuick] = useState(false);
  const [owner, setOwner] = useState(item.owner_id?.toString() || '');
  const [due, setDue] = useState(dateInput(item.due_at));
  const [priority, setPriority] = useState<WorkPriority>(item.priority);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: `card:${item.id}`, disabled: !canUpdate || busy });
  const overdue = Boolean(item.due_at && !['verified', 'rejected', 'deferred'].includes(item.status) && Date.parse(item.due_at) < Date.now());
  return <article ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className={`rounded-xl border bg-card p-3 shadow-sm transition-shadow hover:shadow-md ${isDragging ? 'opacity-40' : ''} ${overdue ? 'border-rose-500/50' : ''}`}>
    <div className='flex items-start justify-between gap-2'><button type='button' onClick={onOpen} className='min-w-0 flex-1 text-right'><strong className='block text-sm leading-6'>{item.title}</strong><span className='text-muted-foreground mt-1 block truncate text-[11px]'>{item.site_name}{item.parent_id ? ' · زیرکار' : ''}</span></button>{canUpdate && <button type='button' {...attributes} {...listeners} aria-label={`جابه‌جایی ${item.title}`} className='touch-none rounded-md border px-2 py-1 text-muted-foreground hover:bg-muted' title='گرفتن و جابه‌جایی'>⠿</button>}</div>
    <div className='mt-3 flex flex-wrap gap-1.5'><Badge variant='outline' className={item.priority === 'critical' ? 'border-rose-500/40 text-rose-600' : ''}>{priorityText[item.priority]}</Badge>{overdue && <Badge variant='destructive'>عقب‌افتاده</Badge>}{item.checklist_total > 0 && <Badge variant='secondary'>☑ {number.format(item.checklist_done)}/{number.format(item.checklist_total)}</Badge>}</div>
    <div className='text-muted-foreground mt-3 flex items-center justify-between gap-2 text-[11px]'><span className='truncate'>{item.owner_name || 'بی‌مسئول'}</span><span>{item.due_at ? new Date(item.due_at).toLocaleDateString('fa-IR', { month: 'short', day: 'numeric' }) : 'بی‌موعد'}</span></div>
    {(item.progress_percent || 0) > 0 && <div className='mt-2 h-1 overflow-hidden rounded-full bg-muted'><div className='h-full rounded-full bg-emerald-500' style={{ width: `${item.progress_percent || 0}%` }} /></div>}
    {canLead && <div className='mt-2 border-t pt-2'><button type='button' onClick={() => { setOwner(item.owner_id?.toString() || ''); setDue(dateInput(item.due_at)); setPriority(item.priority); setQuick((value) => !value); }} className='text-primary text-[11px] hover:underline'>{quick ? 'بستن ویرایش سریع' : 'واگذاری و موعد'}</button>{quick && <div className='mt-2 space-y-2'><NativeSelect aria-label={`مسئول ${item.title}`} value={owner} onChange={(event) => setOwner(event.target.value)}><NativeSelectOption value=''>بی‌مسئول</NativeSelectOption>{people.map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect><Input aria-label={`موعد ${item.title}`} type='date' value={due} onChange={(event) => setDue(event.target.value)} /><NativeSelect aria-label={`اولویت ${item.title}`} value={priority} onChange={(event) => setPriority(event.target.value as WorkPriority)}>{(Object.keys(priorityText) as WorkPriority[]).map((key) => <NativeSelectOption key={key} value={key}>{priorityText[key]}</NativeSelectOption>)}</NativeSelect><Button size='sm' disabled={busy} onClick={() => void onQuickSave({ owner_id: owner ? Number(owner) : null, due_at: due ? new Date(`${due}T12:00:00`).toISOString() : null, priority }).then((saved) => { if (saved) setQuick(false); })}>ذخیره</Button></div>}</div>}
  </article>;
}

function BoardLane({ lane, items, children, fullscreen }: { lane: Lane; items: CommandWorkItem[]; children: ReactNode; fullscreen: boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: `lane:${lane.key}` });
  return <section ref={setNodeRef} className={`flex min-h-80 w-[300px] shrink-0 flex-col rounded-2xl border bg-muted/30 ${fullscreen ? 'h-[calc(100vh-150px)]' : 'max-h-[72vh]'} ${isOver ? 'ring-2 ring-primary/50' : ''}`}><div className='flex items-center justify-between gap-2 border-b px-3 py-3'><div className='flex items-center gap-2'><span className={`size-2.5 rounded-full ${lane.color}`} /><h3 className='text-sm font-bold'>{lane.title}</h3></div><Badge variant='secondary'>{number.format(items.length)}</Badge></div><div className='min-h-20 flex-1 space-y-2 overflow-y-auto p-2'><SortableContext items={items.map((item) => `card:${item.id}`)} strategy={verticalListSortingStrategy}>{children}</SortableContext></div></section>;
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
  const [mine, setMine] = useState(false);
  const [draftLane, setDraftLane] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [draftOwner, setDraftOwner] = useState('');
  const [draftDue, setDraftDue] = useState('');
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragged, setDragged] = useState<CommandWorkItem | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  useEffect(() => { setLocalItems(items); }, [items]);
  useEffect(() => { if (!fullscreen) return; const previous = document.body.style.overflow; document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, [fullscreen]);
  useEffect(() => { if (preferredSiteId) setSiteId(preferredSiteId); else if (!siteId && sites[0]) setSiteId(sites[0].site_id); }, [preferredSiteId, siteId, sites]);
  useEffect(() => { if (!siteId) return; let active = true; setMembers([]);
    void commandApi.projectMembers(siteId).then((rows) => { if (active) setMembers(rows); }).catch(() => { if (active) setMembers([]); });
    return () => { active = false; };
  }, [siteId]);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const siteItems = useMemo(() => localItems.filter((item) => item.site_id === siteId), [localItems, siteId]);
  const eligiblePeople = people.filter((person) => person.active && (person.role === 'admin' || members.some((member) => member.user_id === person.id && member.responsibility !== 'viewer')));
  const filtered = siteItems.filter((item) => (!query || `${item.title} ${item.description || ''} ${item.url || ''}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())) &&
    (!ownerFilter || item.owner_id?.toString() === ownerFilter) && (!priorityFilter || item.priority === priorityFilter) && (!mine || item.owner_id === meId));
  const rowsFor = (lane: Lane) => ordered(filtered.filter((item) => lane.statuses.includes(item.status)));

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
  async function handleDragEnd(event: DragEndEvent) {
    setDragged(null);
    const activeId = Number(String(event.active.id).replace('card:', ''));
    const item = localItems.find((row) => row.id === activeId);
    const target = event.over?.id ? String(event.over.id) : '';
    if (!item || !target || !canUpdate(item)) return;
    const overCard = target.startsWith('card:') ? localItems.find((row) => row.id === Number(target.slice(5))) : null;
    const targetLane = overCard ? laneOf(overCard.status) : lanes.find((lane) => `lane:${lane.key}` === target);
    if (!targetLane || (overCard && overCard.id === item.id)) return;
    const nextStatus = laneOf(item.status).key === targetLane.key ? item.status : targetLane.status;
    if (nextStatus === 'blocked' || nextStatus === 'verified') { setFullscreen(false); onPrepareStatus(item, nextStatus); return; }
    if (nextStatus !== item.status && ['approved', 'assigned', 'in_progress', 'review', 'published', 'measurement_pending'].includes(nextStatus) && (!item.owner_id || !item.due_at)) {
      setFullscreen(false); onPrepareStatus(item, nextStatus); toast.info('برای انتقال به این مرحله، مسئول و موعد را تکمیل کنید'); return;
    }
    const siblings = ordered(localItems.filter((row) => row.site_id === siteId && targetLane.statuses.includes(row.status) && row.id !== item.id));
    const index = overCard ? siblings.findIndex((row) => row.id === overCard.id) : siblings.length;
    const insertion = index < 0 ? siblings.length : index;
    const previous = siblings[insertion - 1]?.board_order;
    const next = siblings[insertion]?.board_order;
    const order = previous !== undefined && next !== undefined ? (previous + next) / 2 :
      previous !== undefined ? previous + 1024 : next !== undefined ? next - 1024 : 1024;
    if (nextStatus === item.status && order === item.board_order) return;
    const before = localItems;
    setLocalItems((current) => current.map((row) => row.id === item.id ? { ...row, status: nextStatus, board_order: order } : row));
    setBusy(true);
    try { await commandApi.updateWork(item, { status: nextStatus, board_order: order }); await onChanged(); toast.success('جای کارت ذخیره شد'); }
    catch (cause) { setLocalItems(before); toast.error(cause instanceof Error ? cause.message : 'جابه‌جایی کارت انجام نشد'); }
    finally { setBusy(false); }
  }

  return <div className={fullscreen ? 'fixed inset-0 z-[60] space-y-3 overflow-y-auto bg-background p-4' : 'space-y-3'} dir='rtl'>
    <div className='flex flex-wrap items-center gap-2 rounded-xl border bg-card p-3'><strong className='ml-2 text-sm'>برد پروژه</strong><NativeSelect aria-label='پروژهٔ برد' value={siteId} onChange={(event) => { setSiteId(event.target.value); onSiteChange(event.target.value); }} className='min-w-44'>{sites.map((site) => <NativeSelectOption key={site.site_id} value={site.site_id}>{site.name}</NativeSelectOption>)}</NativeSelect><Input aria-label='جست‌وجوی کارت در برد' placeholder='جست‌وجوی کارت…' value={query} onChange={(event) => setQuery(event.target.value)} className='min-w-40 flex-1' /><NativeSelect aria-label='فیلتر مسئول برد' value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)} className='w-36'><NativeSelectOption value=''>همهٔ مسئولان</NativeSelectOption>{people.filter((person) => person.active).map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect><NativeSelect aria-label='فیلتر اولویت برد' value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)} className='w-28'><NativeSelectOption value=''>همهٔ اولویت‌ها</NativeSelectOption>{(Object.keys(priorityText) as WorkPriority[]).map((key) => <NativeSelectOption key={key} value={key}>{priorityText[key]}</NativeSelectOption>)}</NativeSelect><Button size='sm' variant={mine ? 'default' : 'outline'} onClick={() => setMine((value) => !value)}>فقط کارهای من</Button><Button size='sm' variant='outline' onClick={() => setFullscreen((value) => !value)}>{fullscreen ? 'خروج از تمام‌صفحه' : 'نمای تمام‌صفحه'}</Button></div>
    <div className='text-muted-foreground flex flex-wrap items-center justify-between gap-2 text-xs'><span>{number.format(filtered.length)} کارت در این نما · کارت را از دستهٔ ⠿ بگیرید و جابه‌جا کنید؛ جابه‌جایی خودکار ذخیره می‌شود.</span><span>برای علت مانع یا تأیید نتیجه، فرم کارت باز می‌شود.</span></div>
    <DndContext sensors={sensors} collisionDetection={closestCorners} onDragStart={(event) => setDragged(localItems.find((item) => `card:${item.id}` === String(event.active.id)) || null)} onDragEnd={(event) => void handleDragEnd(event)} onDragCancel={() => setDragged(null)}><div className='flex gap-3 overflow-x-auto pb-4' dir='rtl'>{lanes.map((lane) => <BoardLane key={lane.key} lane={lane} items={rowsFor(lane)} fullscreen={fullscreen}>
      {rowsFor(lane).map((item) => <BoardCard key={item.id} item={item} people={eligiblePeople} canUpdate={canUpdate(item)} canLead={canLead(item.site_id)} busy={busy} onOpen={() => { setFullscreen(false); onOpen(item); }} onQuickSave={(patch) => quickSave(item, patch)} />)}
      {!rowsFor(lane).length && <p className='text-muted-foreground rounded-lg border border-dashed p-5 text-center text-xs'>کارتی در این ستون نیست</p>}
      {canLead(siteId) && !['blocked', 'done'].includes(lane.key) && <div className='border-t pt-2'>{draftLane === lane.key ? <div className='space-y-2'><Input autoFocus aria-label={`عنوان کارت جدید ${lane.title}`} placeholder='عنوان کار جدید' value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void createCard(lane); }} />{lane.key !== 'inbox' && <><NativeSelect aria-label='مسئول کارت جدید' value={draftOwner} onChange={(event) => setDraftOwner(event.target.value)}><NativeSelectOption value=''>انتخاب مسئول</NativeSelectOption>{eligiblePeople.map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect><Input aria-label='موعد کارت جدید' type='date' value={draftDue} onChange={(event) => setDraftDue(event.target.value)} /></>}<div className='flex gap-2'><Button size='sm' disabled={busy || draftTitle.trim().length < 3} onClick={() => void createCard(lane)}>افزودن</Button><Button size='sm' variant='ghost' onClick={() => setDraftLane(null)}>انصراف</Button></div></div> : <button type='button' onClick={() => { setDraftLane(lane.key); setDraftTitle(''); setDraftOwner(''); setDraftDue(''); }} className='text-primary w-full rounded-lg p-2 text-right text-xs hover:bg-muted'>＋ افزودن کارت</button>}</div>}
    </BoardLane>)}</div><DragOverlay>{dragged && <div className='w-[280px] rotate-2 rounded-xl border bg-card p-3 shadow-xl'><strong className='text-sm'>{dragged.title}</strong><span className='text-muted-foreground mt-1 block text-xs'>{dragged.owner_name || 'بی‌مسئول'}</span></div>}</DragOverlay></DndContext>
  </div>;
}
