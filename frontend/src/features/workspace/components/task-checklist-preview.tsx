'use client';

import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { commandApi, type CommandWorkItem } from '../api';

export function TaskChecklistPreview({ item, canToggle, onChanged }: {
  item: CommandWorkItem; canToggle: boolean; onChanged?: () => void | Promise<void>;
}) {
  const [steps, setSteps] = useState(item.checklist || []);
  const pendingSteps = useRef(new Set<number>());
  const [pendingIds, setPendingIds] = useState<Set<number>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  useEffect(() => { setSteps(item.checklist || []); }, [item.checklist]);
  if (!steps.length) return null;
  const done = steps.filter((step) => step.done).length;
  async function toggle(id: number, current: boolean) {
    if (!canToggle || pendingSteps.current.has(id) || bulkBusy) return;
    const next = !current;
    pendingSteps.current.add(id); setPendingIds(new Set(pendingSteps.current));
    setSteps((rows) => rows.map((step) => step.id === id ? { ...step, done: next } : step));
    try {
      const saved = await commandApi.toggleChecklist(item, id, next);
      setSteps((rows) => rows.map((step) => step.id === id ? { ...step, done: saved.done } : step));
      void Promise.resolve(onChanged?.()).catch(() => {});
    } catch (cause) {
      setSteps((rows) => rows.map((step) => step.id === id ? { ...step, done: current } : step));
      toast.error(cause instanceof Error ? cause.message : 'ثبت چک‌لیست انجام نشد');
    } finally { pendingSteps.current.delete(id); setPendingIds(new Set(pendingSteps.current)); }
  }
  async function toggleAll() {
    if (!canToggle || pendingSteps.current.size || bulkBusy) return;
    const next = done !== steps.length;
    const previous = steps;
    setBulkBusy(true);
    setSteps((rows) => rows.map((step) => ({ ...step, done: next })));
    try {
      const result = await commandApi.setAllChecklist(item, next);
      setSteps(result.items);
      void Promise.resolve(onChanged?.()).catch(() => {});
    } catch (cause) {
      setSteps(previous);
      toast.error(cause instanceof Error ? cause.message : 'ثبت گروهی چک‌لیست انجام نشد');
    } finally { setBulkBusy(false); }
  }
  return <div className='mt-2 rounded-lg border border-border/70 bg-muted/20 p-2' aria-label={`چک‌لیست ${item.title}`}>
    <div className='mb-1 flex items-center justify-between text-[11px]'><span className='font-medium'>چک‌لیست</span><span className='text-muted-foreground'>{done} از {steps.length}</span></div>
    {canToggle && <label className='mb-1 flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-xs font-medium'>
      <input type='checkbox' checked={done === steps.length} disabled={pendingIds.size > 0 || bulkBusy}
        ref={(node) => { if (node) node.indeterminate = done > 0 && done < steps.length; }}
        aria-label={`تیک همهٔ چک‌لیست ${item.title}`} onChange={() => void toggleAll()} />تیک همه
    </label>}
    <div className='space-y-1'>{steps.map((step) => <label key={step.id} className='flex cursor-pointer items-start gap-2 rounded px-1 py-0.5 text-xs hover:bg-muted/50'>
      <input type='checkbox' checked={step.done} disabled={!canToggle || pendingIds.has(step.id) || bulkBusy}
        aria-label={`${item.title}: ${step.title}`} onChange={() => void toggle(step.id, step.done)} className='mt-0.5 shrink-0' />
      <span className={`min-w-0 break-words leading-5 ${step.done ? 'text-muted-foreground line-through' : ''}`}>{step.title}</span>
    </label>)}</div>
  </div>;
}
