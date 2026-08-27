'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ApiError, endpoints, type PlanRecommendation } from '@/lib/api/client';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ACTION_FA, GAP_FA, INTENT_FA, PAGE_TYPE_FA, PRIORITY_FA, fa } from '../constants';

const err = (e: unknown) => toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));

export function PlanKeywordMapping({ siteId, onOpen, onChanged, refreshKey }: { siteId: string; onOpen: (pid: number) => void; onChanged: () => void; refreshKey: number }) {
  const [status, setStatus] = useState<'unmapped' | 'mapped' | 'all'>('unmapped');
  const [q, setQ] = useState('');
  const [data, setData] = useState<Awaited<ReturnType<typeof endpoints.planKeywordMapping>> | null>(null);
  const [recs, setRecs] = useState<Record<number, { recommendation: PlanRecommendation; recommendation_id: number | null; category: any }>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const load = useCallback(async () => { try { setData(await endpoints.planKeywordMapping(siteId, status, q || undefined)); } catch (e) { err(e); } }, [siteId, status, q]);
  useEffect(() => { load(); }, [load, refreshKey]);
  async function suggest(ids?: number[]) {
    setBusy('s');
    try { const r = await endpoints.planKeywordSuggest(siteId, ids, 100); setRecs((m) => { const n = { ...m }; r.items.forEach((it) => { n[it.keyword.id] = { recommendation: it.recommendation, recommendation_id: it.recommendation_id, category: it.category }; }); return n; }); toast.success(`${r.count} پیشنهاد مغز محاسبه و ذخیره شد`); }
    catch (e) { err(e); } finally { setBusy(null); }
  }
  async function apply(items: { keyword_id: number; plan_id?: number | 'new'; role?: string; recommendation_id?: number | null }[]) {
    setBusy('a');
    try { const r = await endpoints.planKeywordApply(siteId, items); toast.success(`${r.created.length} برنامه جدید · ${r.attached.length} اتصال${r.errors.length ? ` · ${r.errors.length} خطا` : ''}`); setSel(new Set()); load(); onChanged(); if (r.created.length === 1) onOpen(r.created[0].plan_id); }
    catch (e) { err(e); } finally { setBusy(null); }
  }
  return (
    <div className='flex flex-col gap-2 text-sm'>
      <div className='flex flex-wrap items-center gap-1 text-xs'>
        <NativeSelect value={status} onChange={(e) => setStatus(e.target.value as any)} className='h-8 w-40'><NativeSelectOption value='unmapped'>نگاشت‌نشده</NativeSelectOption><NativeSelectOption value='mapped'>نگاشت‌شده</NativeSelectOption><NativeSelectOption value='all'>همه</NativeSelectOption></NativeSelect>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder='جستجوی کلمه…' className='h-8 w-48' />
        <Button size='sm' disabled={!!busy} onClick={() => suggest(sel.size ? [...sel] : undefined)}>{busy === 's' ? '…' : sel.size ? `پیشنهاد مغز برای ${fa.format(sel.size)} کلمه` : 'پیشنهاد مغز برای همه (تا ۱۰۰)'}</Button>
        {sel.size > 0 && <Button size='sm' variant='secondary' disabled={!!busy} onClick={() => apply([...sel].map((k) => ({ keyword_id: k, plan_id: recs[k]?.recommendation?.mapping?.type === 'attach' ? recs[k].recommendation.mapping!.plan_id : 'new', role: recs[k]?.recommendation?.mapping?.role, recommendation_id: recs[k]?.recommendation_id })))}>اعمال پیشنهاد برای انتخاب‌شده‌ها</Button>}
        {data && <span className='text-muted-foreground ms-auto'>{fa.format(data.counts.keywords)} کلمه · {fa.format(data.counts.mapped)} نگاشت‌شده · {fa.format(data.counts.plans)} برنامه</span>}
      </div>
      <div className='overflow-auto rounded-md border' style={{ maxHeight: '70vh' }}>
        <table className='w-full text-xs'>
          <thead className='bg-muted/60 sticky top-0'><tr><th className='w-8 p-1'><input aria-label='انتخاب همه کلمات' type='checkbox' checked={!!data?.items.length && data.items.every((i) => sel.has(i.id))} onChange={(e) => setSel(e.target.checked ? new Set(data?.items.map((i) => i.id)) : new Set())} /></th><th className='p-1.5 text-start'>کلمه کلیدی</th><th className='p-1.5 text-start'>اینتنت</th><th className='p-1.5 text-start'>حجم</th><th className='p-1.5 text-start'>خوشه</th><th className='p-1.5 text-start'>GSC</th><th className='p-1.5 text-start'>پیشنهاد مغز</th><th className='p-1.5 text-start'>عملیات</th></tr></thead>
          <tbody>
            {(data?.items ?? []).map((k) => { const r = recs[k.id]?.recommendation; return (
              <tr key={k.id} className='border-t align-top'>
                <td className='p-1 text-center'><input aria-label={`انتخاب ${k.keyword}`} type='checkbox' checked={sel.has(k.id)} onChange={(e) => setSel((s) => { const n = new Set(s); e.target.checked ? n.add(k.id) : n.delete(k.id); return n; })} /></td>
                <td className='p-1.5 font-medium'>{k.keyword}{k.mapped && <div className='text-muted-foreground font-normal'>{(k.plans ?? []).map((p: any) => <button key={p.plan_id} className='underline' onClick={() => onOpen(p.plan_id)}>{p.title ?? `#${p.plan_id}`} ({p.role})</button>)}</div>}</td>
                <td className='p-1.5'>{INTENT_FA[k.intent] ?? k.intent ?? '—'}</td><td className='p-1.5' dir='ltr'>{k.volume ?? '—'}</td><td className='p-1.5'>{k.cluster_id ? `${k.topic ?? k.cluster_id} (${k.cluster_size})` : '—'}</td>
                <td className='p-1.5' dir='ltr'>{k.gsc ? `pos ${k.gsc.position ?? '—'} · ${k.gsc.impressions} imp` : '—'}</td>
                <td className='p-1.5'>{r ? (
                  <div className='max-w-md'>
                    <div className='flex flex-wrap gap-1'><Badge>{r.action_fa ?? ACTION_FA[r.action]}</Badge>{r.page_type && <Badge variant='outline'>{PAGE_TYPE_FA[r.page_type]}</Badge>}{r.intent && <Badge variant='outline'>{INTENT_FA[r.intent]}</Badge>}{recs[k.id].category?.suggested && <Badge variant='secondary'>دسته: {recs[k.id].category.suggested.name}</Badge>}{r.priority && <Badge variant='outline' style={{ borderColor: r.priority === 'high' ? '#dc2626' : undefined }}>اولویت {PRIORITY_FA[r.priority]} {r.priority_score}</Badge>}{r.content_gap && <Badge variant='outline'>شکاف {GAP_FA[r.content_gap]}</Badge>}</div>
                    {r.ranking_url && <div className='text-muted-foreground mt-0.5 truncate' dir='ltr'>صفحه موجود: {r.ranking_url} (pos {r.ranking_position})</div>}
                    {!r.ranking_url && <div className='text-muted-foreground mt-0.5'>صفحه موجود: ندارد</div>}
                    <ul className='mt-0.5 list-disc ps-4'>{(r.reasons_fa ?? []).slice(0, 4).map((x, i) => <li key={i}>{x}</li>)}</ul>
                    {r.title && <div className='mt-0.5'>عنوان پیشنهادی: <b>{r.title}</b></div>}
                  </div>) : <Button size='sm' variant='ghost' onClick={() => suggest([k.id])}>محاسبه</Button>}</td>
                <td className='p-1.5'><div className='flex flex-col gap-1'>
                  <Button size='sm' disabled={!!busy} onClick={() => apply([{ keyword_id: k.id, plan_id: 'new', recommendation_id: recs[k.id]?.recommendation_id }])}>ساخت برنامه</Button>
                  {r?.mapping?.type === 'attach' && <Button size='sm' variant='secondary' disabled={!!busy} onClick={() => apply([{ keyword_id: k.id, plan_id: r.mapping!.plan_id, role: r.mapping!.role, recommendation_id: recs[k.id]?.recommendation_id }])}>اتصال به «{r.mapping.plan_title}» ({r.mapping.role})</Button>}
                  <AttachSelect siteId={siteId} onPick={(pid, role) => apply([{ keyword_id: k.id, plan_id: pid, role }])} />
                </div></td>
              </tr>); })}
            {data && data.items.length === 0 && <tr><td colSpan={8} className='text-muted-foreground p-6 text-center'>کلمه‌ای در این فیلتر نیست — از «کلمات کلیدی» تحقیق را وارد کنید.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AttachSelect({ siteId, onPick }: { siteId: string; onPick: (pid: number, role: string) => void }) {
  const [plans, setPlans] = useState<{ id: number; title: string }[] | null>(null);
  const [role, setRole] = useState('secondary');
  return (
    <div className='flex gap-1'>
      <NativeSelect value='' onFocus={() => { if (!plans) endpoints.plans(siteId, { limit: 300, sort: 'title', order: 'asc' }).then((r) => setPlans(r.items.map((p) => ({ id: p.id, title: p.title })))).catch(() => setPlans([])); }} onChange={(e) => e.target.value && onPick(Number(e.target.value), role)} className='h-7 w-40 text-xs'><NativeSelectOption value=''>اتصال به برنامه…</NativeSelectOption>{(plans ?? []).map((p) => <NativeSelectOption key={p.id} value={p.id}>{p.title}</NativeSelectOption>)}</NativeSelect>
      <NativeSelect value={role} onChange={(e) => setRole(e.target.value)} className='h-7 w-24 text-xs'><NativeSelectOption value='secondary'>ثانویه</NativeSelectOption><NativeSelectOption value='supporting'>پشتیبان</NativeSelectOption><NativeSelectOption value='question'>پرسش</NativeSelectOption><NativeSelectOption value='primary'>اصلی</NativeSelectOption></NativeSelect>
    </div>
  );
}
