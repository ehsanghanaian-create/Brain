'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { commandApi, type CommandWorkItem } from '../api';

export function TaskChecklistPreview({ item, canToggle, onChanged }: {
  item: CommandWorkItem; canToggle: boolean; onChanged?: () => void | Promise<void>;
}) {
  const [steps, setSteps] = useState(item.checklist || []);
  const [busyId, setBusyId] = useState<number | null>(null);
  useEffect(() => { setSteps(item.checklist || []); }, [item.checklist]);
  if (!steps.length) return null;
  const done = steps.filter((step) => step.done).length;
  async function toggle(id: number, current: boolean) {
    if (!canToggle || busyId !== null) return;
    const next = !current;
    setBusyId(id);
    setSteps((rows) => rows.map((step) => step.id === id ? { ...step, done: next } : step));
    try {
      await commandApi.toggleChecklist(item, id, next);
      if (onChanged) await onChanged();
    } catch (cause) {
      setSteps((rows) => rows.map((step) => step.id === id ? { ...step, done: current } : step));
      toast.error(cause instanceof Error ? cause.message : 'ثبت چک‌لیست انجام نشد');
    } finally { setBusyId(null); }
  }
  return <div className='mt-2 rounded-lg border border-border/70 bg-muted/20 p-2' aria-label={`چک‌لیست ${item.title}`}>
    <div className='mb-1 flex items-center justify-between text-[11px]'><span className='font-medium'>چک‌لیست</span><span className='text-muted-foreground'>{done} از {steps.length}</span></div>
    <div className='space-y-1'>{steps.map((step) => <label key={step.id} className='flex cursor-pointer items-start gap-2 rounded px-1 py-0.5 text-xs hover:bg-muted/50'>
      <input type='checkbox' checked={step.done} disabled={!canToggle || busyId !== null}
        aria-label={`${item.title}: ${step.title}`} onChange={() => void toggle(step.id, step.done)} className='mt-0.5 shrink-0' />
      <span className={`min-w-0 break-words leading-5 ${step.done ? 'text-muted-foreground line-through' : ''}`}>{step.title}</span>
    </label>)}</div>
  </div>;
}
