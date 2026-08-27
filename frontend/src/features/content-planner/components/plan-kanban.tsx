'use client';

import { Badge } from '@/components/ui/badge';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ApiError, endpoints, type ContentPlan, type PlanCategory, type PlanStatus } from '@/lib/api/client';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { PAGE_TYPE_FA, PLAN_STATUS_COLOR, PLAN_STATUS_FA, PRIORITY_COLOR, fa } from '../constants';

export function PlanKanban({ siteId, categories, onOpen, refreshKey, onChanged }: { siteId: string; categories: PlanCategory[]; onOpen: (pid: number) => void; refreshKey: number; onChanged: () => void }) {
  const [cols, setCols] = useState<{ status: PlanStatus; status_fa: string; items: ContentPlan[] }[]>([]);
  const [cat, setCat] = useState('');
  const [drag, setDrag] = useState<ContentPlan | null>(null);
  const load = useCallback(async () => { try { setCols((await endpoints.planBoard(siteId, cat ? Number(cat) : undefined)).columns); } catch (e) { toast.error(String(e)); } }, [siteId, cat]);
  useEffect(() => { load(); }, [load, refreshKey]);
  async function drop(status: PlanStatus) {
    if (!drag || drag.status === status) return;
    try { await endpoints.planTransition(siteId, drag.id, status); toast.success(`${drag.title} → ${PLAN_STATUS_FA[status]}`); load(); onChanged(); }
    catch (e) { toast.error(e instanceof ApiError ? `${e.message}` : String(e)); }
    setDrag(null);
  }
  return (
    <div className='flex flex-col gap-2'>
      <div className='flex items-center gap-2 text-xs'><NativeSelect value={cat} onChange={(e) => setCat(e.target.value)} className='h-8 w-44'><NativeSelectOption value=''>همه دسته‌ها</NativeSelectOption>{categories.map((c) => <NativeSelectOption key={c.id} value={c.id}>{c.name}</NativeSelectOption>)}</NativeSelect><span className='text-muted-foreground'>کارت‌ها را بین ستون‌ها بکشید — گذارها همان قواعد گردش کار انسانی هستند (تأیید نیازمند بازبینی آماده؛ انتشار فقط با URL و توسط انسان).</span></div>
      <div className='grid gap-2 overflow-x-auto' style={{ gridTemplateColumns: `repeat(${cols.length || 7}, minmax(190px, 1fr))` }}>
        {cols.map((c) => (
          <div key={c.status} className='bg-muted/40 min-h-64 rounded-md p-1' onDragOver={(e) => e.preventDefault()} onDrop={() => drop(c.status)}>
            <div className='mb-1 flex items-center justify-between px-1 text-xs font-medium'><span className='flex items-center gap-1'><span className='inline-block h-2.5 w-2.5 rounded-full' style={{ background: PLAN_STATUS_COLOR[c.status] }} />{c.status_fa}</span><span className='text-muted-foreground'>{fa.format(c.items.length)}</span></div>
            <div className='flex flex-col gap-1'>
              {c.items.map((p) => (
                <div key={p.id} role='button' tabIndex={0} draggable onDragStart={() => setDrag(p)} onClick={() => onOpen(p.id)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onOpen(p.id); }} className='bg-card cursor-pointer rounded border p-1.5 text-xs shadow-sm hover:shadow' style={{ borderInlineStartWidth: 3, borderInlineStartColor: PRIORITY_COLOR[p.priority ?? ''] ?? '#e5e7eb' }}>
                  <div className='font-medium'>{p.title}</div>
                  <div className='text-muted-foreground mt-0.5 flex flex-wrap gap-1'>{p.primary_keyword && <span>🔑 {p.primary_keyword}</span>}{p.page_type && <span>· {PAGE_TYPE_FA[p.page_type]}</span>}{p.category && <span>· {p.category.name}</span>}</div>
                  <div className='mt-1 flex flex-wrap items-center gap-1'>{p.publish_date && <Badge variant='outline' dir='ltr' className='text-[10px]'>{p.publish_date}</Badge>}{p.priority_score != null && <Badge variant='outline' className='text-[10px]'>اولویت {p.priority_score}</Badge>}{p.content_item?.latest_score != null && <Badge variant='secondary' className='text-[10px]'>امتیاز {p.content_item.latest_score}</Badge>}{p.content_gap === 'full' && <Badge className='text-[10px]'>شکاف</Badge>}{(p.cannibalization_risk ?? 0) >= 0.5 && <Badge variant='destructive' className='text-[10px]'>هم‌نوع‌خواری</Badge>}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
