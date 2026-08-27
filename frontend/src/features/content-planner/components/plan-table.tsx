'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ApiError, endpoints, type ContentPlan, type PlanCategory, type PlanColumn, type PlanImportResult, type PlanList, type PlanMeta } from '@/lib/api/client';
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef, type SortingState } from '@tanstack/react-table';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { ACTION_FA, GAP_FA, PLAN_STATUS_COLOR, PRIORITY_COLOR, fa, optionFa } from '../constants';
import { parseTags } from '../lib';

const err = (e: unknown) => toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));
const DEFAULT_VISIBLE = ['title', 'status', 'primary_keyword', 'category_id', 'page_type', 'intent', 'priority', 'publish_date', 'search_volume', 'content_gap', 'recommendation', 'content_score', 'link_targets', 'seo_title'];
type Filters = { status: string; category_id: string; page_type: string; intent: string; priority: string; q: string };

export function PlanTable({ siteId, meta, categories, onOpen, refreshKey, onChanged }: { siteId: string; meta: PlanMeta | null; categories: PlanCategory[]; onOpen: (pid: number) => void; refreshKey: number; onChanged: () => void }) {
  const [data, setData] = useState<PlanList | null>(null);
  const [filters, setFilters] = useState<Filters>({ status: '', category_id: '', page_type: '', intent: '', priority: '', q: '' });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'updated_at', desc: true }]);
  const [page, setPage] = useState(0);
  const [visible, setVisible] = useState<string[]>(() => { if (typeof window === 'undefined') return DEFAULT_VISIBLE; try { return JSON.parse(localStorage.getItem(`planner-cols-${siteId}`) || 'null') ?? DEFAULT_VISIBLE; } catch { return DEFAULT_VISIBLE; } });
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [editing, setEditing] = useState<{ id: number; key: string } | null>(null);
  const [colsOpen, setColsOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const limit = 100;
  const load = useCallback(async () => {
    try { setData(await endpoints.plans(siteId, { ...filters, sort: sorting[0]?.id ?? 'updated_at', order: sorting[0]?.desc === false ? 'asc' : 'desc', limit, offset: page * limit })); } catch (e) { err(e); }
  }, [siteId, filters, sorting, page]);
  useEffect(() => { load(); }, [load, refreshKey]);
  useEffect(() => { localStorage.setItem(`planner-cols-${siteId}`, JSON.stringify(visible)); }, [visible, siteId]);
  const catName = useMemo(() => Object.fromEntries(categories.map((c) => [c.id, c.name])), [categories]);

  async function patch(id: number, key: string, value: unknown) {
    try { await endpoints.planPatch(siteId, id, { [key]: value }); setData((d) => d && { ...d, items: d.items.map((it) => (it.id === id ? { ...it, [key]: value } as ContentPlan : it)) }); onChanged(); load(); }
    catch (e) { err(e); }
  }
  const cols = useMemo<ColumnDef<ContentPlan>[]>(() => {
    const defs: ColumnDef<ContentPlan>[] = (meta?.columns ?? []).filter((c) => visible.includes(c.key)).map((c: PlanColumn) => ({
      id: c.key, accessorFn: (r) => (r as any)[c.key], header: c.fa, enableSorting: !['existing_pages', 'link_targets', 'recommendation', 'heading_structure', 'secondary_keywords', 'parent_category'].includes(c.key),
      cell: ({ row }) => <Cell plan={row.original} col={c} editing={editing?.id === row.original.id && editing.key === c.key} onEdit={() => c.editable && setEditing({ id: row.original.id, key: c.key })} onDone={() => setEditing(null)} onPatch={(v) => patch(row.original.id, c.key, v)} meta={meta} categories={categories} catName={catName} onOpen={() => onOpen(row.original.id)} />,
    }));
    return defs;
  }, [meta, visible, editing, categories, catName]);  // eslint-disable-line react-hooks/exhaustive-deps
  const table = useReactTable({ data: data?.items ?? [], columns: cols, getCoreRowModel: getCoreRowModel(), state: { sorting }, onSortingChange: setSorting, manualSorting: true });
  const allIds = data?.items.map((i) => i.id) ?? [];
  const bulk = async (patchBody: Record<string, unknown>) => { if (!selected.size) return; try { const r = await endpoints.planBulk(siteId, [...selected], patchBody); toast.success(`${fa.format(r.updated.length)} مورد به‌روزرسانی شد${r.errors.length ? ` · ${r.errors.length} خطا` : ''}`); setSelected(new Set()); load(); onChanged(); } catch (e) { err(e); } };

  return (
    <div className='flex flex-col gap-2'>
      {/* toolbar */}
      <div className='flex flex-wrap items-center gap-1 text-xs'>
        <Input placeholder='جستجو (عنوان، کلمه، URL)…' value={filters.q} onChange={(e) => { setFilters((f) => ({ ...f, q: e.target.value })); setPage(0); }} className='h-8 w-52' />
        <NativeSelect value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))} className='h-8 w-36'><NativeSelectOption value=''>همه وضعیت‌ها</NativeSelectOption>{(meta?.statuses ?? []).map((s) => <NativeSelectOption key={s.key} value={s.key}>{s.fa}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect value={filters.category_id} onChange={(e) => setFilters((f) => ({ ...f, category_id: e.target.value }))} className='h-8 w-36'><NativeSelectOption value=''>همه دسته‌ها</NativeSelectOption>{categories.map((c) => <NativeSelectOption key={c.id} value={c.id}>{c.name}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect value={filters.page_type} onChange={(e) => setFilters((f) => ({ ...f, page_type: e.target.value }))} className='h-8 w-32'><NativeSelectOption value=''>نوع صفحه</NativeSelectOption>{(meta?.page_types ?? []).map((s) => <NativeSelectOption key={s.key} value={s.key}>{s.fa}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect value={filters.intent} onChange={(e) => setFilters((f) => ({ ...f, intent: e.target.value }))} className='h-8 w-28'><NativeSelectOption value=''>اینتنت</NativeSelectOption>{(meta?.intents ?? []).map((s) => <NativeSelectOption key={s.key} value={s.key}>{s.fa}</NativeSelectOption>)}</NativeSelect>
        <NativeSelect value={filters.priority} onChange={(e) => setFilters((f) => ({ ...f, priority: e.target.value }))} className='h-8 w-24'><NativeSelectOption value=''>اولویت</NativeSelectOption>{(meta?.priorities ?? []).map((s) => <NativeSelectOption key={s.key} value={s.key}>{s.fa}</NativeSelectOption>)}</NativeSelect>
        <Button size='sm' variant='ghost' onClick={() => setFilters({ status: '', category_id: '', page_type: '', intent: '', priority: '', q: '' })}>پاک‌کردن</Button>
        <span className='ms-auto flex flex-wrap gap-1'>
          <Button size='sm' variant='outline' onClick={() => setColsOpen(true)}>ستون‌ها ({visible.length})</Button>
          <Button size='sm' variant='outline' onClick={() => setImportOpen(true)}>ورود CSV/XLSX/Sheet</Button>
          <Button size='sm' variant='outline' nativeButton={false} render={<a href={endpoints.planExportUrl(siteId, 'csv', { status: filters.status, category_id: filters.category_id, page_type: filters.page_type, intent: filters.intent, priority: filters.priority, q: filters.q, columns: visible.join(',') })} aria-label='دریافت خروجی CSV' />}>خروجی CSV</Button>
          <Button size='sm' variant='outline' nativeButton={false} render={<a href={endpoints.planExportUrl(siteId, 'xlsx', { status: filters.status, category_id: filters.category_id, columns: visible.join(',') })} aria-label='دریافت خروجی XLSX' />}>خروجی XLSX</Button>
          <Button size='sm' variant='secondary' onClick={async () => { try { const r = await endpoints.planAnalyzeAll(siteId); toast.success(r.mode === 'job' ? `تحلیل در پس‌زمینه (${r.run_id})` : `تحلیل ${r.analyzed} برنامه و ${r.categories} دسته انجام شد`); load(); onChanged(); } catch (e) { err(e); } }}>تحلیل همه با مغز</Button>
        </span>
      </div>
      {/* quick add */}
      <form className='flex gap-1' onSubmit={async (e) => { e.preventDefault(); if (!newTitle.trim()) return; try { await endpoints.planCreate(siteId, { title: newTitle.trim(), primary_keyword: newTitle.trim() }); setNewTitle(''); toast.success('برنامه ساخته و تحلیل شد'); load(); onChanged(); } catch (er) { err(er); } }}>
        <Input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder='+ افزودن سریع: عنوان یا کلمه کلیدی (مغز بقیه را پیشنهاد می‌دهد)…' className='h-8' />
        <Button size='sm' type='submit' disabled={!newTitle.trim()}>افزودن</Button>
      </form>
      {/* bulk bar */}
      {selected.size > 0 && (
        <div className='bg-accent flex flex-wrap items-center gap-1 rounded-md p-1 text-xs'>
          <span className='font-medium'>{fa.format(selected.size)} انتخاب‌شده:</span>
          <NativeSelect value='' onChange={(e) => e.target.value && bulk({ status: e.target.value })} className='h-7 w-32'><NativeSelectOption value=''>تغییر وضعیت…</NativeSelectOption>{(meta?.statuses ?? []).map((s) => <NativeSelectOption key={s.key} value={s.key}>{s.fa}</NativeSelectOption>)}</NativeSelect>
          <NativeSelect value='' onChange={(e) => e.target.value && bulk({ priority: e.target.value })} className='h-7 w-28'><NativeSelectOption value=''>اولویت…</NativeSelectOption>{(meta?.priorities ?? []).map((s) => <NativeSelectOption key={s.key} value={s.key}>{s.fa}</NativeSelectOption>)}</NativeSelect>
          <NativeSelect value='' onChange={(e) => e.target.value && bulk({ category_id: Number(e.target.value) })} className='h-7 w-32'><NativeSelectOption value=''>دسته…</NativeSelectOption>{categories.map((c) => <NativeSelectOption key={c.id} value={c.id}>{c.name}</NativeSelectOption>)}</NativeSelect>
          <NativeSelect value='' onChange={(e) => e.target.value && bulk({ page_type: e.target.value })} className='h-7 w-32'><NativeSelectOption value=''>نوع صفحه…</NativeSelectOption>{(meta?.page_types ?? []).map((s) => <NativeSelectOption key={s.key} value={s.key}>{s.fa}</NativeSelectOption>)}</NativeSelect>
          <Input type='date' className='h-7 w-36' dir='ltr' onChange={(e) => e.target.value && bulk({ publish_date: e.target.value })} />
          <Button size='sm' variant='secondary' onClick={async () => { try { await endpoints.planAnalyzeAll(siteId, [...selected]); toast.success('تحلیل شد'); load(); } catch (e) { err(e); } }}>تحلیل</Button>
          <Button size='sm' variant='secondary' onClick={async () => { let n = 0; for (const id of selected) { try { await endpoints.planBrief(siteId, id); n++; } catch { /* skip */ } } toast.success(`${n} بریف ساخته شد`); setSelected(new Set()); load(); onChanged(); }}>ساخت بریف</Button>
          <Button size='sm' variant='ghost' className='text-destructive' onClick={async () => { if (!confirm(`${selected.size} برنامه حذف شود؟`)) return; await endpoints.planBulkDelete(siteId, [...selected]); setSelected(new Set()); load(); onChanged(); }}>حذف</Button>
          <Button size='sm' variant='ghost' onClick={() => setSelected(new Set())}>لغو</Button>
        </div>
      )}
      {/* grid */}
      <div className='overflow-auto rounded-md border' style={{ maxHeight: '70vh' }}>
        <table className='w-full text-xs' style={{ minWidth: 900 }}>
          <thead className='bg-muted/60 sticky top-0 z-10'>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                <th className='w-8 p-1'><input aria-label='انتخاب همه برنامه‌ها' type='checkbox' checked={allIds.length > 0 && allIds.every((i) => selected.has(i))} onChange={(e) => setSelected(e.target.checked ? new Set(allIds) : new Set())} /></th>
                {hg.headers.map((h) => (
                  <th key={h.id} className='whitespace-nowrap p-1.5 text-start font-medium select-none' onClick={h.column.getCanSort() ? () => setSorting([{ id: h.column.id, desc: sorting[0]?.id === h.column.id ? !sorting[0].desc : true }]) : undefined} style={{ cursor: h.column.getCanSort() ? 'pointer' : 'default' }}>
                    {flexRender(h.column.columnDef.header, h.getContext())}{sorting[0]?.id === h.column.id ? (sorting[0].desc ? ' ↓' : ' ↑') : ''}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className={`border-t ${selected.has(row.original.id) ? 'bg-accent/40' : 'hover:bg-accent/20'}`}>
                <td className='p-1 text-center'><input aria-label={`انتخاب ${row.original.title}`} type='checkbox' checked={selected.has(row.original.id)} onChange={(e) => setSelected((s) => { const n = new Set(s); e.target.checked ? n.add(row.original.id) : n.delete(row.original.id); return n; })} /></td>
                {row.getVisibleCells().map((cell) => <td key={cell.id} className='max-w-72 p-1 align-top'>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}
              </tr>
            ))}
            {data && data.items.length === 0 && <tr><td colSpan={cols.length + 1} className='text-muted-foreground p-6 text-center'>برنامه‌ای نیست — با «افزودن سریع»، ورود فایل، یا از تب «نگاشت کلمات کلیدی» شروع کنید.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className='text-muted-foreground flex items-center gap-2 text-xs'>
        <span>{data ? `${fa.format(data.total)} برنامه` : '…'}</span>
        <Button size='sm' variant='ghost' disabled={page === 0} onClick={() => setPage((p) => p - 1)}>قبلی</Button><span>صفحه {fa.format(page + 1)}</span><Button size='sm' variant='ghost' disabled={!data || (page + 1) * limit >= data.total} onClick={() => setPage((p) => p + 1)}>بعدی</Button>
        <span className='ms-auto'>روی سلول دوبار کلیک کنید تا ویرایش شود · Enter ذخیره · Esc انصراف</span>
      </div>
      {/* columns dialog */}
      <Dialog open={colsOpen} onOpenChange={setColsOpen}>
        <DialogContent><DialogHeader><DialogTitle>ستون‌های جدول</DialogTitle><DialogDescription>ستون‌ها را انتخاب کنید (در این مرورگر برای هر سایت ذخیره می‌شود).</DialogDescription></DialogHeader>
          {(['basic', 'seo', 'advanced'] as const).map((g) => <div key={g} className='mb-2'><div className='mb-1 text-xs font-medium'>{g === 'basic' ? 'پایه' : g === 'seo' ? 'هوش سئو' : 'برنامه‌ریزی پیشرفته'}</div><div className='flex flex-wrap gap-1'>{(meta?.columns ?? []).filter((c) => c.group === g).map((c) => <label key={c.key} className='flex items-center gap-1 rounded border px-2 py-0.5 text-xs'><input type='checkbox' checked={visible.includes(c.key)} onChange={(e) => setVisible((v) => (e.target.checked ? [...v, c.key] : v.filter((x) => x !== c.key)))} />{c.fa}</label>)}</div></div>)}
          <div className='flex justify-end gap-1'><Button size='sm' variant='ghost' onClick={() => setVisible(DEFAULT_VISIBLE)}>پیش‌فرض</Button><Button size='sm' onClick={() => setColsOpen(false)}>بستن</Button></div>
        </DialogContent>
      </Dialog>
      <ImportDialog siteId={siteId} open={importOpen} onClose={() => setImportOpen(false)} onDone={() => { load(); onChanged(); }} />
    </div>
  );
}

// ---------------------------------------------------------------- cell renderer with inline editing
function Cell({ plan, col, editing, onEdit, onDone, onPatch, meta, categories, catName, onOpen }: { plan: ContentPlan; col: PlanColumn; editing: boolean; onEdit: () => void; onDone: () => void; onPatch: (v: unknown) => void; meta: PlanMeta | null; categories: PlanCategory[]; catName: Record<number, string>; onOpen: () => void }) {
  const v = (plan as any)[col.key];
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (editing) ref.current?.focus(); }, [editing]);
  if (col.key === 'title') return <button className='text-start font-medium hover:underline' onClick={onOpen} onDoubleClick={(e) => { e.stopPropagation(); onEdit(); }}>{editing ? <InlineText value={v} onSave={onPatch} onDone={onDone} /> : v}</button>;
  if (col.key === 'status') return <NativeSelect value={v} onChange={(e) => onPatch(e.target.value)} className='h-7 text-xs' style={{ borderColor: PLAN_STATUS_COLOR[plan.status] }}>{(meta?.statuses ?? []).map((s) => <NativeSelectOption key={s.key} value={s.key} disabled={s.key !== plan.status && !plan.allowed_transitions.includes(s.key)}>{s.fa}</NativeSelectOption>)}</NativeSelect>;
  if (col.key === 'category_id') return <NativeSelect value={v ?? ''} onChange={(e) => onPatch(e.target.value ? Number(e.target.value) : null)} className='h-7 text-xs' title={plan.category_suggested && !v ? `پیشنهاد: ${plan.category_suggested.name}` : undefined}><NativeSelectOption value=''>{plan.category_suggested && !v ? `پیشنهاد: ${plan.category_suggested.name}` : '—'}</NativeSelectOption>{categories.map((c) => <NativeSelectOption key={c.id} value={c.id}>{c.name}</NativeSelectOption>)}</NativeSelect>;
  if (col.type === 'select' && col.editable) return <NativeSelect value={v ?? ''} onChange={(e) => onPatch(e.target.value || null)} className='h-7 text-xs'><NativeSelectOption value=''>—</NativeSelectOption>{(col.options ?? []).map((o) => <NativeSelectOption key={o} value={o}>{optionFa(col.key, o)}</NativeSelectOption>)}</NativeSelect>;
  if (col.type === 'date') return <input type='date' value={v ?? ''} onChange={(e) => onPatch(e.target.value || null)} className='h-7 rounded border bg-transparent px-1' dir='ltr' />;
  if (col.key === 'priority') return <NativeSelect value={v ?? ''} onChange={(e) => onPatch(e.target.value || null)} className='h-7 text-xs' style={{ borderColor: PRIORITY_COLOR[v] }}><NativeSelectOption value=''>—</NativeSelectOption>{(meta?.priorities ?? []).map((s) => <NativeSelectOption key={s.key} value={s.key}>{s.fa}</NativeSelectOption>)}</NativeSelect>;
  if (col.key === 'recommendation') { const r = v as any; return r?.action ? <span title={(r.reasons_fa ?? []).join('\n')} className='cursor-help'><Badge variant='outline'>{r.action_fa ?? ACTION_FA[r.action]}</Badge>{r.priority_score != null && <span className='text-muted-foreground'> {r.priority_score}</span>}</span> : <span className='text-muted-foreground'>—</span>; }
  if (col.key === 'content_gap') return v ? <Badge variant={v === 'full' ? 'default' : 'outline'}>{GAP_FA[v]}</Badge> : <span className='text-muted-foreground'>—</span>;
  if (col.key === 'existing_pages' || col.key === 'link_targets') { const arr = (v ?? []) as any[]; return <span title={arr.map((x) => x.title ?? x.url).join('\n')} className='cursor-help'>{arr.length ? `${fa.format(arr.length)} مورد` : '—'}</span>; }
  if (col.key === 'secondary_keywords') return editing ? <InlineText value={(v ?? []).join(', ')} onSave={(s) => onPatch(parseTags(String(s)))} onDone={onDone} /> : <span onDoubleClick={onEdit} className='cursor-text' title={(v ?? []).join(', ')}>{(v ?? []).slice(0, 3).join('، ')}{(v ?? []).length > 3 ? ' …' : ''}{!(v ?? []).length && <span className='text-muted-foreground'>—</span>}</span>;
  if (col.key === 'heading_structure') return <span title={(v ?? []).map((h: any) => `H${h.level}: ${h.text}`).join('\n')} className='cursor-help' onDoubleClick={onOpen}>{(v ?? []).length ? `${fa.format((v ?? []).length)} سرفصل` : <span className='text-muted-foreground'>—</span>}</span>;
  if (col.key === 'content_score') return v != null ? <span style={{ color: v >= 80 ? '#16a34a' : v >= 60 ? '#f59e0b' : '#dc2626' }}>{fa.format(v)}</span> : <span className='text-muted-foreground'>—</span>;
  if (col.key === 'parent_category') return <span>{plan.parent_category ?? '—'}</span>;
  if (col.key === 'primary_keyword') return editing ? <InlineText value={v} onSave={onPatch} onDone={onDone} /> : <span onDoubleClick={onEdit} className='cursor-text'>{v ?? <span className='text-muted-foreground'>—</span>}{plan.primary_keyword_id ? '' : v ? <span className='text-muted-foreground' title='در پایگاه کلمات کلیدی نیست'> ?</span> : null}</span>;
  if (col.editable && (col.type === 'text' || col.type === 'url' || col.type === 'number')) return editing ? <InlineText value={v} type={col.type === 'number' ? 'number' : 'text'} onSave={(s) => onPatch(col.type === 'number' ? (s === '' ? null : Number(s)) : (s || null))} onDone={onDone} /> : <span onDoubleClick={onEdit} className='block max-w-64 cursor-text truncate' dir={col.type === 'url' ? 'ltr' : 'auto'} title={String(v ?? '')}>{v ?? <span className='text-muted-foreground'>—</span>}</span>;
  if (typeof v === 'number') return <span dir='ltr'>{col.key === 'cannibalization_risk' ? v : fa.format(Math.round(v * 10) / 10)}</span>;
  return <span className='block max-w-64 truncate' dir={col.type === 'url' ? 'ltr' : 'auto'} title={String(v ?? '')}>{v == null || v === '' ? <span className='text-muted-foreground'>—</span> : String(v)}</span>;
}

function InlineText({ value, onSave, onDone, type = 'text' }: { value: unknown; onSave: (v: string) => void; onDone: () => void; type?: string }) {
  const [v, setV] = useState(value == null ? '' : String(value));
  return <input aria-label='ویرایش مقدار' type={type} value={v} onChange={(e) => setV(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { onSave(v); onDone(); } if (e.key === 'Escape') onDone(); }} onBlur={() => { onSave(v); onDone(); }} className='h-7 w-full rounded border bg-background px-1' dir='auto' />;
}

// ---------------------------------------------------------------- import dialog (file + Google Sheet source)
function ImportDialog({ siteId, open, onClose, onDone }: { siteId: string; open: boolean; onClose: () => void; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<PlanImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [sheetUrl, setSheetUrl] = useState('');
  const [sources, setSources] = useState<any[]>([]);
  useEffect(() => { if (open) endpoints.planSources(siteId).then(setSources).catch(() => null); }, [open, siteId]);
  async function run(dry: boolean) { if (!file) return; setBusy(true); try { const r = await endpoints.planImport(siteId, file, dry); setRes(r); if (!dry) { toast.success(`ورود انجام شد: ${r.created} جدید · ${r.updated} به‌روزرسانی · ${r.skipped} ردشده`); onDone(); } } catch (e) { err(e); } finally { setBusy(false); } }
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-w-2xl'>
        <DialogHeader><DialogTitle>ورود برنامه محتوایی</DialogTitle><DialogDescription>CSV / TSV / XLSX با سرستون‌های فارسی یا انگلیسی؛ ابتدا «پیش‌نمایش» تا نگاشت ستون‌ها بررسی شود. کلید به‌روزرسانی: URL → کلمه کلیدی اصلی → عنوان. <a className='underline' href={endpoints.planTemplateUrl(siteId)}>دانلود قالب</a></DialogDescription></DialogHeader>
        <div className='grid gap-2 text-sm'>
          <input type='file' accept='.csv,.tsv,.txt,.xlsx' onChange={(e) => { setFile(e.target.files?.[0] ?? null); setRes(null); }} />
          <div className='flex gap-1'><Button size='sm' variant='secondary' disabled={!file || busy} onClick={() => run(true)}>پیش‌نمایش (dry-run)</Button><Button size='sm' disabled={!file || busy || !res} onClick={() => run(false)}>اعمال</Button></div>
          {res && (
            <div className='rounded border p-2 text-xs'>
              <div>قالب: {res.format} · ردیف‌ها: {res.rows} · جدید: {res.created} · به‌روزرسانی: {res.updated} · ردشده: {res.skipped}</div>
              <div className='mt-1'>نگاشت: {Object.entries(res.mapping).map(([c, f]) => <Badge key={c} variant='outline' className='me-1'>{c} → {f}</Badge>)}{res.unmapped_columns.length > 0 && <span className='text-muted-foreground'>· نادیده: {res.unmapped_columns.join('، ')}</span>}</div>
              {res.errors.length > 0 && <details className='mt-1'><summary className='cursor-pointer'>هشدارها/خطاها ({res.errors.length})</summary><ul className='list-disc ps-4'>{res.errors.slice(0, 20).map((e: any, i: number) => <li key={i}>ردیف {e.row}: {e.error ?? ''} {(e.warnings ?? []).join(' · ')}</li>)}</ul></details>}
              {res.preview?.length > 0 && <details className='mt-1'><summary className='cursor-pointer'>پیش‌نمایش ({res.preview.length})</summary><ul className='list-disc ps-4'>{res.preview.slice(0, 20).map((p: any) => <li key={p.row}>{p.action === 'create' ? 'جدید' : `به‌روزرسانی #${p.existing_id}`}: {p.fields.title ?? p.fields.primary_keyword}</li>)}</ul></details>}
            </div>
          )}
          <div className='mt-2 rounded border p-2'>
            <div className='mb-1 text-xs font-medium'>منبع Google Sheet (همگام‌سازی آینده‌نگر — فعلاً خروجی CSV عمومی شیت)</div>
            <div className='flex gap-1'><Input value={sheetUrl} onChange={(e) => setSheetUrl(e.target.value)} placeholder='https://docs.google.com/spreadsheets/d/…/edit#gid=0' dir='ltr' className='h-8' /><Button size='sm' variant='secondary' disabled={!sheetUrl} onClick={async () => { try { const s = await endpoints.planSourceCreate(siteId, { name: 'Google Sheet', kind: 'google_sheet', url: sheetUrl }); setSources((x) => [...x, s]); setSheetUrl(''); } catch (e) { err(e); } }}>افزودن منبع</Button></div>
            <ul className='mt-1 space-y-1 text-xs'>{sources.map((s) => <li key={s.id} className='flex flex-wrap items-center gap-1'><span className='font-medium'>{s.name}</span><span className='text-muted-foreground truncate' dir='ltr'>{s.url}</span><span className='text-muted-foreground'>{s.status ?? '—'}{s.last_sync_at ? ` · ${s.last_sync_at.slice(0, 16)}` : ''}</span><Button size='sm' variant='outline' onClick={async () => { try { const r = await endpoints.planSourceSync(siteId, s.id, true); toast.info(`پیش‌نمایش: ${r.created} جدید · ${r.updated} به‌روزرسانی`); } catch (e) { err(e); } }}>پیش‌نمایش</Button><Button size='sm' onClick={async () => { try { const r = await endpoints.planSourceSync(siteId, s.id, false); toast.success(`همگام شد: ${r.created} جدید · ${r.updated} به‌روزرسانی`); onDone(); setSources(await endpoints.planSources(siteId)); } catch (e) { err(e); } }}>همگام‌سازی</Button><Button size='sm' variant='ghost' onClick={async () => { await endpoints.planSourceDelete(siteId, s.id); setSources((x) => x.filter((y) => y.id !== s.id)); }}>حذف</Button></li>)}</ul>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
