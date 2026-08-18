'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ApiError, endpoints, type PlanSuggestion } from '@/lib/api/client';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ACTION_FA, INTENT_FA, PAGE_TYPE_FA, PRIORITY_FA, fa } from '../constants';

const err = (e: unknown) => toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));

export function PlanSuggestions({ siteId, onOpen, onChanged, refreshKey }: { siteId: string; onOpen: (pid: number) => void; onChanged: () => void; refreshKey: number }) {
  const [status, setStatus] = useState('new');
  const [kind, setKind] = useState('');
  const [rows, setRows] = useState<PlanSuggestion[]>([]);
  const [insights, setInsights] = useState<any[]>([]);
  const load = useCallback(async () => { try { setRows(await endpoints.planSuggestions(siteId, status, kind || undefined)); setInsights(await endpoints.planInsights(siteId)); } catch (e) { err(e); } }, [siteId, status, kind]);
  useEffect(() => { load(); }, [load, refreshKey]);
  async function decide(r: PlanSuggestion, s: 'accepted' | 'dismissed') {
    try { const out = await endpoints.planSuggestionDecide(siteId, r.id, s); toast.success(s === 'accepted' ? (out.created_plan ? `برنامه «${out.created_plan.title}» ساخته شد` : 'پذیرفته شد') : 'رد شد'); load(); onChanged(); if (out.created_plan) onOpen(out.created_plan.id); }
    catch (e) { err(e); }
  }
  return (
    <div className='flex flex-col gap-3 text-sm'>
      <div className='flex flex-wrap items-center gap-1 text-xs'>
        <NativeSelect value={status} onChange={(e) => setStatus(e.target.value)} className='h-8 w-32'><NativeSelectOption value='new'>جدید</NativeSelectOption><NativeSelectOption value='accepted,applied'>پذیرفته/اعمال‌شده</NativeSelectOption><NativeSelectOption value='dismissed'>ردشده</NativeSelectOption><NativeSelectOption value='superseded'>منسوخ</NativeSelectOption></NativeSelect>
        <NativeSelect value={kind} onChange={(e) => setKind(e.target.value)} className='h-8 w-40'><NativeSelectOption value=''>همه انواع</NativeSelectOption>{Object.entries(ACTION_FA).map(([k, v]) => <NativeSelectOption key={k} value={k}>{v}</NativeSelectOption>)}</NativeSelect>
        <Button size='sm' variant='secondary' onClick={async () => { try { const r = await endpoints.planAnalyzeAll(siteId); toast.success(r.mode === 'job' ? 'در پس‌زمینه' : `تحلیل ${r.analyzed} برنامه و ${r.categories} دسته`); load(); } catch (e) { err(e); } }}>تحلیل مجدد همه</Button>
        <span className='text-muted-foreground ms-auto'>پیشنهادها دائمی و نسخه‌دار ذخیره می‌شوند؛ پذیرش شما برنامه می‌سازد یا دسته را تنظیم می‌کند — هیچ چیز خودکار اعمال نمی‌شود.</span>
      </div>
      <div className='grid gap-1'>
        {rows.map((r) => (
          <div key={r.id} className='flex flex-wrap items-start gap-2 rounded-md border p-2 text-xs'>
            <Badge>{r.kind_fa}</Badge>
            <div className='flex-1'>
              <div className='font-medium'>{r.title ?? r.payload?.keyword ?? r.payload?.category ?? '—'}{r.plan_title && <span className='text-muted-foreground'> · برنامه: <button className='underline' onClick={() => r.plan_id && onOpen(r.plan_id)}>{r.plan_title}</button></span>}</div>
              <div className='text-muted-foreground mt-0.5 flex flex-wrap gap-1'>{r.page_type && <Badge variant='outline'>{PAGE_TYPE_FA[r.page_type] ?? r.page_type}</Badge>}{r.intent && <Badge variant='outline'>{INTENT_FA[r.intent] ?? r.intent}</Badge>}{r.priority && <Badge variant='outline'>اولویت {PRIORITY_FA[r.priority]} {r.priority_score ?? ''}</Badge>}{r.payload?.category?.name && <Badge variant='secondary'>دسته: {r.payload.category.name}</Badge>}{r.payload?.category && typeof r.payload.category === 'string' && <Badge variant='secondary'>دسته: {r.payload.category}</Badge>}{r.confidence != null && <span>اطمینان {Math.round(r.confidence * 100)}٪</span>}<span>· v{r.version} · {r.engine}</span></div>
              <ul className='mt-0.5 list-disc ps-4'>{r.reasons.slice(0, 5).map((x, i) => <li key={i}>{x}</li>)}</ul>
            </div>
            {r.status === 'new' && <div className='flex gap-1'><Button size='sm' onClick={() => decide(r, 'accepted')}>پذیرش</Button><Button size='sm' variant='ghost' onClick={() => decide(r, 'dismissed')}>رد</Button></div>}
            {r.status !== 'new' && <Badge variant='outline'>{r.status}</Badge>}
          </div>
        ))}
        {rows.length === 0 && <p className='text-muted-foreground'>پیشنهادی نیست — «تحلیل مجدد همه» یا در تب نگاشت کلمات «پیشنهاد مغز» را بزنید.</p>}
      </div>
      <div className='rounded-md border p-2 text-xs'>
        <div className='flex items-center justify-between'><span className='font-medium'>یادگیری برنامه‌ریز (الگوهای موفق از عملکرد واقعی GSC)</span><Button size='sm' variant='secondary' onClick={async () => { try { const r = await endpoints.planInsightsLearn(siteId); toast.success(`نمونه‌ها: ${r.samples} · بینش‌ها: ${r.insights.length}`); load(); } catch (e) { err(e); } }}>تحلیل</Button></div>
        <ul className='mt-1 space-y-1'>{insights.map((i) => <li key={i.id} className='flex flex-wrap items-center gap-1'><Badge variant={i.status === 'accepted' ? 'default' : 'outline'}>{i.status}</Badge><span>{i.message_fa}</span>{i.status === 'new' && <><Button size='sm' onClick={async () => { await endpoints.planInsightStatus(siteId, i.id, 'accepted'); toast.success('در حافظه سایت ثبت شد'); load(); }}>پذیرش → حافظه</Button><Button size='sm' variant='ghost' onClick={async () => { await endpoints.planInsightStatus(siteId, i.id, 'dismissed'); load(); }}>رد</Button></>}</li>)}{insights.length === 0 && <li className='text-muted-foreground'>هنوز بینشی نیست (حداقل ۵ برنامه منتشرشده با داده GSC کافی لازم است).</li>}</ul>
      </div>
    </div>
  );
}
