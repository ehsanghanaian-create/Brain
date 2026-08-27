'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { ApiError, endpoints, type ContentPlan, type PlanCategory, type PlanMeta } from '@/lib/api/client';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ACTION_FA, FUNNEL_FA, GAP_FA, INTENT_FA, PAGE_TYPE_FA, PLAN_STATUS_COLOR, PLAN_STATUS_FA, PRIORITY_FA, ROLE_FA, fa } from '../constants';
import { headingsToText, parseHeadings, parseTags } from '../lib';

const err = (e: unknown) => toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));

export function PlanSheet({ siteId, pid, meta, categories, onClose, onChanged }: { siteId: string; pid: number | null; meta: PlanMeta | null; categories: PlanCategory[]; onClose: () => void; onChanged: () => void }) {
  const [p, setP] = useState<ContentPlan | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [f, setF] = useState<Record<string, any>>({});
  const load = useCallback(async () => { if (!pid) return; try { const d = await endpoints.plan(siteId, pid); setP(d); setF({ title: d.title, url: d.url ?? '', seo_title: d.seo_title ?? '', meta_description: d.meta_description ?? '', secondary_keywords: (d.secondary_keywords ?? []).join(', '), heading_structure: (d.heading_structure ?? []).map((h) => `H${h.level}: ${h.text}`).join('\n'), target_audience: d.target_audience ?? '', notes: d.notes ?? '', business_value: d.business_value ?? '' }); } catch (e) { err(e); } }, [siteId, pid]);
  useEffect(() => { load(); }, [load]);
  const open = pid !== null;
  async function run(key: string, fn: () => Promise<unknown>, ok?: string) { setBusy(key); try { await fn(); if (ok) toast.success(ok); await load(); onChanged(); } catch (e) { err(e); } finally { setBusy(null); } }
  const rec = (p?.recommendation ?? {}) as any;
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side='left' className='w-full overflow-y-auto p-4 sm:max-w-2xl' dir='rtl'>
        <SheetHeader className='p-0'>
          <SheetTitle className='flex flex-wrap items-center gap-2'>{p?.title ?? '…'}{p && <Badge style={{ background: PLAN_STATUS_COLOR[p.status] }}>{PLAN_STATUS_FA[p.status]}</Badge>}{p?.priority && <Badge variant='outline'>اولویت {PRIORITY_FA[p.priority]} · {p.priority_score ?? '—'}</Badge>}</SheetTitle>
          <SheetDescription>{p ? `${p.primary_keyword ?? 'بدون کلمه کلیدی'} · ${p.page_type ? PAGE_TYPE_FA[p.page_type] : '—'} · ${p.intent ? INTENT_FA[p.intent] : '—'} · ${p.category?.name ?? 'بدون دسته'}` : ''}</SheetDescription>
        </SheetHeader>
        {p && (
          <div className='mt-3 grid gap-3 text-sm'>
            {/* workflow */}
            <div className='flex flex-wrap items-center gap-1 rounded-md border p-2 text-xs'>
              <span className='font-medium'>گردش کار:</span>
              {p.allowed_transitions.map((s) => <Button key={s} size='sm' variant='outline' disabled={!!busy} onClick={() => run('t', () => endpoints.planTransition(siteId, p.id, s), `وضعیت → ${PLAN_STATUS_FA[s]}`)}>→ {PLAN_STATUS_FA[s]}</Button>)}
              <span className='text-muted-foreground ms-auto'>{p.content_item ? <>آیتم محتوا #{p.content_item.id} · {p.content_item.status}{p.content_item.latest_score != null ? ` · امتیاز ${p.content_item.latest_score}` : ''} · <Link className='underline' href={`/dashboard/content?site=${siteId}`}>مغز محتوا</Link></> : 'هنوز آیتم محتوا ندارد (با بریف/تولید ساخته می‌شود)'}</span>
            </div>
            {/* actions */}
            <div className='flex flex-wrap gap-1'>
              <Button size='sm' disabled={!!busy} onClick={() => run('a', () => endpoints.planAnalyze(siteId, p.id), 'تحلیل مجدد انجام شد')}>{busy === 'a' ? '…' : 'تحلیل مغز'}</Button>
              <Button size='sm' variant='secondary' disabled={!!busy || !(p.primary_keyword || p.primary_keyword_id)} onClick={() => run('b', () => endpoints.planBrief(siteId, p.id), 'بریف ساخته شد')} title='ساخت بریف Phase-6 با نکات برنامه (سرفصل‌ها، کلمات ثانویه، اهداف لینک)'>{busy === 'b' ? '…' : 'ساخت بریف'}</Button>
              <Button size='sm' variant='secondary' disabled={!!busy} onClick={() => run('l', () => endpoints.planLinkPrep(siteId, p.id), 'لینک‌های داخلی آماده شد')}>آماده‌سازی لینک داخلی</Button>
              <Button size='sm' variant='outline' disabled={!!busy} onClick={() => run('g', async () => { const j = await endpoints.planGenPrepare(siteId, p.id, 'article'); toast.info(j.note); }, 'کار تولید AI آماده شد (بدون اجرا)')} title='برنامه → کار تولید → آیتم محتوا → پیش‌نویس؛ اجرا فقط در استودیوی AI با تأیید انسانی'>آماده‌سازی تولید AI</Button>
              {p.content_item && <Button size='sm' variant='outline' nativeButton={false} render={<Link href={`/dashboard/ai-studio?site=${siteId}&content=${p.content_item.id}`} aria-label='باز کردن استودیوی AI' />}>استودیوی AI</Button>}
              {p.content_item && <Button size='sm' variant='outline' nativeButton={false} render={<Link href={`/dashboard/graph?site=${siteId}`} aria-label='باز کردن گراف دانش' />}>گراف دانش</Button>}
              <Button size='sm' variant='ghost' className='text-destructive ms-auto' disabled={!!busy} onClick={() => { if (confirm('این برنامه حذف شود؟ (آیتم محتوا حفظ می‌شود)')) run('d', async () => { await endpoints.planDelete(siteId, p.id); onClose(); }, 'حذف شد'); }}>حذف</Button>
            </div>
            {/* recommendation card */}
            <div className='rounded-md border p-2'>
              <div className='flex flex-wrap items-center gap-2 text-xs'>
                <span className='font-medium'>پیشنهاد مغز:</span><Badge>{rec.action_fa ?? ACTION_FA[rec.action] ?? '—'}</Badge>
                {rec.confidence != null && <span className='text-muted-foreground'>اطمینان {Math.round(rec.confidence * 100)}٪ · موتور {rec.engine ?? 'rules-v1'}</span>}
                <span className='ms-auto flex flex-wrap gap-1'>
                  <Badge variant='outline'>شکاف: {GAP_FA[p.content_gap ?? ''] ?? '—'}</Badge><Badge variant='outline'>هم‌نوع‌خواری: {p.cannibalization_risk ?? '—'}</Badge><Badge variant='outline'>فرصت ترافیک: {p.traffic_opportunity != null ? fa.format(Math.round(p.traffic_opportunity)) : '—'}</Badge><Badge variant='outline'>AI: {p.ai_priority ?? '—'}</Badge><Badge variant='outline'>قیف: {FUNNEL_FA[p.funnel_stage ?? ''] ?? '—'}</Badge>
                </span>
              </div>
              <ul className='mt-1 list-disc ps-5 text-xs'>{(rec.reasons_fa ?? []).map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
              {rec.gaps_fa?.length > 0 && <div className='mt-1 text-xs'><span className='font-medium text-amber-600'>کمبودها:</span> {rec.gaps_fa.join(' · ')}</div>}
              {p.ranking_url && <div className='mt-1 text-xs' dir='ltr'>ranking: {p.ranking_url} (pos {p.ranking_position})</div>}
              {p.category_suggested && !p.category_id && <div className='mt-1 flex items-center gap-2 text-xs'>دسته پیشنهادی: <b>{p.category_suggested.name}</b> <span className='text-muted-foreground'>{p.category_suggested.reason}</span><Button size='sm' variant='secondary' onClick={() => run('c', () => endpoints.planPatch(siteId, p.id, { category_id: p.category_suggested!.id }), 'دسته تنظیم شد')}>پذیرش</Button></div>}
              {p.cannibalization?.length > 0 && <details className='mt-1 text-xs'><summary className='cursor-pointer'>موارد هم‌نوع‌خواری ({p.cannibalization.length})</summary><ul className='list-disc ps-5'>{p.cannibalization.map((c: any, i: number) => <li key={i}>{c.kind}: {c.title ?? c.url} {c.position ? `(pos ${c.position})` : ''}</li>)}</ul></details>}
            </div>
            {/* editable fields */}
            <div className='grid gap-2 md:grid-cols-2'>
              <div className='grid gap-1'><Label>عنوان</Label><Input value={f.title ?? ''} onChange={(e) => setF((s) => ({ ...s, title: e.target.value }))} /></div>
              <div className='grid gap-1'><Label>URL</Label><Input value={f.url ?? ''} onChange={(e) => setF((s) => ({ ...s, url: e.target.value }))} dir='ltr' /></div>
              <div className='grid gap-1'><Label>اینتنت</Label><NativeSelect value={p.intent ?? ''} onChange={(e) => run('i', () => endpoints.planPatch(siteId, p.id, { intent: e.target.value || null }))}><NativeSelectOption value=''>—</NativeSelectOption>{(meta?.intents ?? []).map((o) => <NativeSelectOption key={o.key} value={o.key}>{o.fa}</NativeSelectOption>)}</NativeSelect></div>
              <div className='grid gap-1'><Label>نوع صفحه</Label><NativeSelect value={p.page_type ?? ''} onChange={(e) => run('pt', () => endpoints.planPatch(siteId, p.id, { page_type: e.target.value || null }))}><NativeSelectOption value=''>—</NativeSelectOption>{(meta?.page_types ?? []).map((o) => <NativeSelectOption key={o.key} value={o.key}>{o.fa}</NativeSelectOption>)}</NativeSelect></div>
              <div className='grid gap-1'><Label>دسته</Label><NativeSelect value={p.category_id ?? ''} onChange={(e) => run('cat', () => endpoints.planPatch(siteId, p.id, { category_id: e.target.value ? Number(e.target.value) : null }))}><NativeSelectOption value=''>—</NativeSelectOption>{categories.map((c) => <NativeSelectOption key={c.id} value={c.id}>{c.name} ({c.source_fa})</NativeSelectOption>)}</NativeSelect></div>
              <div className='grid gap-1'><Label>اولویت</Label><NativeSelect value={p.priority ?? ''} onChange={(e) => run('pr', () => endpoints.planPatch(siteId, p.id, { priority: e.target.value || null }))}><NativeSelectOption value=''>—</NativeSelectOption>{(meta?.priorities ?? []).map((o) => <NativeSelectOption key={o.key} value={o.key}>{o.fa}</NativeSelectOption>)}</NativeSelect></div>
              <div className='grid gap-1'><Label>تاریخ انتشار</Label><Input type='date' value={p.publish_date ?? ''} onChange={(e) => run('pd', () => endpoints.planPatch(siteId, p.id, { publish_date: e.target.value || null }))} dir='ltr' /></div>
              <div className='grid gap-1'><Label>مرحله قیف</Label><NativeSelect value={p.funnel_stage ?? ''} onChange={(e) => run('fs', () => endpoints.planPatch(siteId, p.id, { funnel_stage: e.target.value || null }))}><NativeSelectOption value=''>—</NativeSelectOption>{(meta?.funnel_stages ?? []).map((o) => <NativeSelectOption key={o.key} value={o.key}>{o.fa}</NativeSelectOption>)}</NativeSelect></div>
              <div className='grid gap-1'><Label>عنوان سئو</Label><Input value={f.seo_title ?? ''} onChange={(e) => setF((s) => ({ ...s, seo_title: e.target.value }))} /></div>
              <div className='grid gap-1'><Label>توضیحات متا</Label><Input value={f.meta_description ?? ''} onChange={(e) => setF((s) => ({ ...s, meta_description: e.target.value }))} /></div>
              <div className='grid gap-1'><Label>کلمات کلیدی ثانویه (با ویرگول)</Label><Input value={f.secondary_keywords ?? ''} onChange={(e) => setF((s) => ({ ...s, secondary_keywords: e.target.value }))} /></div>
              <div className='grid gap-1'><Label>مخاطب هدف</Label><Input value={f.target_audience ?? ''} onChange={(e) => setF((s) => ({ ...s, target_audience: e.target.value }))} /></div>
              <div className='grid gap-1'><Label>ارزش کسب‌وکار (۰–۱۰۰)</Label><Input type='number' value={f.business_value ?? ''} onChange={(e) => setF((s) => ({ ...s, business_value: e.target.value }))} dir='ltr' /></div>
              <div className='grid gap-1 md:col-span-2'><Label>ساختار سرفصل‌ها (هر خط: H2: … یا H3: …)</Label><Textarea rows={4} value={f.heading_structure ?? ''} onChange={(e) => setF((s) => ({ ...s, heading_structure: e.target.value }))} /></div>
              <div className='grid gap-1 md:col-span-2'><Label>یادداشت</Label><Textarea rows={2} value={f.notes ?? ''} onChange={(e) => setF((s) => ({ ...s, notes: e.target.value }))} /></div>
            </div>
            <div className='flex justify-end'><Button size='sm' disabled={!!busy} onClick={() => run('save', () => endpoints.planPatch(siteId, p.id, { title: f.title, url: f.url || null, seo_title: f.seo_title || null, meta_description: f.meta_description || null, target_audience: f.target_audience || null, notes: f.notes || null,
              business_value: f.business_value === '' ? null : Number(f.business_value), secondary_keywords: parseTags(String(f.secondary_keywords)),
              heading_structure: String(f.heading_structure).split('\n').map((l: string) => l.trim()).filter(Boolean).map((l: string) => { const m = l.match(/^h?([23])[:.\-)\s]+(.*)$/i); return m ? { level: Number(m[1]), text: m[2] } : { level: 2, text: l }; }) }), 'ذخیره شد')}>ذخیره فیلدها</Button></div>
            {/* keywords */}
            <div className='rounded-md border p-2 text-xs'>
              <div className='font-medium'>کلمات کلیدی ({p.keywords.length})</div>
              <div className='mt-1 flex flex-wrap gap-1'>{p.keywords.map((k) => <Badge key={k.id} variant={k.role === 'primary' ? 'default' : 'outline'} title={`${ROLE_FA[k.role]} · حجم ${k.volume ?? '—'}`}>{k.keyword} <span className='opacity-70'>· {ROLE_FA[k.role]}</span>{k.role !== 'primary' && <button className='ms-1' onClick={() => run('rk', () => endpoints.planKeywordRemove(siteId, p.id, k.id))}>×</button>}</Badge>)}</div>
            </div>
            {/* existing pages + link targets */}
            <div className='grid gap-2 md:grid-cols-2 text-xs'>
              <div className='rounded-md border p-2'><div className='font-medium'>صفحات مرتبط موجود ({p.existing_pages.length})</div><ul className='mt-1 space-y-0.5'>{p.existing_pages.slice(0, 8).map((e, i) => <li key={i} className='truncate' dir='auto'>{e.title}{e.position ? ` (pos ${e.position})` : ''} <span className='text-muted-foreground'>· {e.relation}</span></li>)}</ul></div>
              <div className='rounded-md border p-2'><div className='font-medium'>اهداف لینک داخلی ({p.link_targets.length})</div><ul className='mt-1 space-y-0.5'>{p.link_targets.slice(0, 10).map((l, i) => <li key={i} className='truncate' dir='auto'>{l.direction === 'from' ? '←' : '→'} {l.title} <span className='text-muted-foreground'>· {l.reason_fa} · {l.score}</span></li>)}</ul></div>
            </div>
            {/* generation jobs + publishing metadata + events */}
            <details className='rounded-md border p-2 text-xs'><summary className='cursor-pointer'>کارهای تولید AI ({p.generation_jobs?.length ?? 0}) · متادیتای انتشار (غیرفعال) · رویدادها ({p.events?.length ?? 0})</summary>
              <ul className='mt-1 space-y-0.5'>{(p.generation_jobs ?? []).map((j: any) => <li key={j.id}>#{j.id} {j.kind} · {j.status}{j.generation_run_id ? ` · run ${j.generation_run_id}` : ''} · {j.created_at.slice(0, 16)}</li>)}</ul>
              <div className='mt-2 flex flex-wrap items-end gap-2'><div className='grid gap-1'><Label>وضعیت هدف در وردپرس</Label><NativeSelect value={p.publishing?.wp_status ?? ''} onChange={(e) => run('pub', () => endpoints.planPublishing(siteId, p.id, { target: 'wordpress', wp_status: e.target.value }), 'متادیتای انتشار ذخیره شد (انتشار انجام نمی‌شود)')}><NativeSelectOption value=''>—</NativeSelectOption><NativeSelectOption value='draft'>پیش‌نویس</NativeSelectOption><NativeSelectOption value='pending'>در انتظار بازبینی</NativeSelectOption><NativeSelectOption value='future'>زمان‌بندی‌شده</NativeSelectOption></NativeSelect></div><span className='text-muted-foreground'>انتشار غیرفعال است — این فقط متادیتاست.</span></div>
              <ul className='text-muted-foreground mt-2 space-y-0.5'>{(p.events ?? []).slice(0, 15).map((e: any) => <li key={e.id}>{e.created_at.slice(0, 16).replace('T', ' ')} · {e.event}{e.to_value ? ` → ${e.to_value}` : ''} · {e.actor}</li>)}</ul>
            </details>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
