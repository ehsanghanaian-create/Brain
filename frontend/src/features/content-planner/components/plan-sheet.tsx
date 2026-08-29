'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { ApiError, endpoints, type ContentPlan, type PlanCategory, type PlanMeta, type WsOptions } from '@/lib/api/client';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ACTION_FA, FUNNEL_FA, GAP_FA, INTENT_FA, PAGE_TYPE_FA, PLAN_STATUS_COLOR, PLAN_STATUS_FA, PRIORITY_FA, ROLE_FA, fa } from '../constants';
import { JalaliDateInput } from '@/features/content/components/jalali-date-input';
import { jalaliLong } from '@/features/content/constants';
import { headingsToText, parseHeadings, parseTags } from '../lib';

const err = (e: unknown) => toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));
const jobStatusFa = (status: string) => ({ prepared: 'زمان‌بندی شد', queued: 'در صف', running: 'در حال تولید', awaiting_approval: 'منتظر تأیید', needs_changes: 'نیازمند اصلاح', approved: 'تأیید شد', wordpress_draft: 'پیش‌نویس وردپرس', scheduled: 'انتشار زمان‌بندی شد', failed: 'ناموفق', retry: 'تلاش مجدد', cancelled: 'لغو شد', done: 'انجام شد' }[status] ?? status);

export function PlanSheet({ siteId, pid, meta, categories, onClose, onChanged }: { siteId: string; pid: number | null; meta: PlanMeta | null; categories: PlanCategory[]; onClose: () => void; onChanged: () => void }) {
  const [p, setP] = useState<ContentPlan | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [f, setF] = useState<Record<string, any>>({});
  const [ai, setAi] = useState<Record<string, any>>({});
  const [opts, setOpts] = useState<WsOptions | null>(null);
  const [schedule, setSchedule] = useState({ scheduled_at: '', publish_at: '', publish_action: 'none', approval_mode: 'human', category_id: '', min_score: '85' });
  const load = useCallback(async () => { if (!pid) return; try { const d = await endpoints.plan(siteId, pid); setP(d); setF({ title: d.title, url: d.url ?? '', seo_title: d.seo_title ?? '', meta_description: d.meta_description ?? '', secondary_keywords: (d.secondary_keywords ?? []).join(', '), heading_structure: (d.heading_structure ?? []).map((h) => `H${h.level}: ${h.text}`).join('\n'), target_audience: d.target_audience ?? '', notes: d.notes ?? '', business_value: d.business_value ?? '' }); setAi({ ...((d.metadata as any)?.ai ?? {}) }); setSchedule((s) => ({ ...s, publish_at: s.publish_at || (d.publish_date ? `${d.publish_date}T${d.publish_time || '09:00'}` : ''), category_id: s.category_id || String(categories.find((c) => c.id === d.category_id)?.wordpress_category_id ?? '') })); } catch (e) { err(e); } }, [siteId, pid, categories]);
  useEffect(() => { load(); }, [load]);
  const open = pid !== null;
  useEffect(() => { if (open) endpoints.wsOptions(siteId).then(setOpts).catch(() => setOpts(null)); }, [open, siteId]);
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
              <Button size='sm' variant='outline' disabled={!!busy || !(p.primary_keyword || p.primary_keyword_id)} onClick={() => run('g', async () => { const j = await endpoints.planGenPrepare(siteId, p.id, 'article', { run_now: true, approval_mode: 'human', publish_action: 'none' }); toast.info(j.note); }, 'تولید مقاله در پس‌زمینه شروع شد')} title='کار روی سرور و در صف پایدار اجرا می‌شود؛ خروج از صفحه آن را متوقف نمی‌کند'>تولید مقاله در پس‌زمینه</Button>
              {p.content_item && <Button size='sm' variant='outline' nativeButton={false} render={<Link href={`/dashboard/ai-studio?site=${siteId}&content=${p.content_item.id}`} aria-label='باز کردن استودیوی AI' />}>استودیوی AI</Button>}
              {p.content_item && <Button size='sm' variant='outline' nativeButton={false} render={<Link href={`/dashboard/graph?site=${siteId}`} aria-label='باز کردن گراف دانش' />}>گراف دانش</Button>}
              <Button size='sm' variant='ghost' className='text-destructive ms-auto' disabled={!!busy} onClick={() => { if (confirm('این برنامه حذف شود؟ (آیتم محتوا حفظ می‌شود)')) run('d', async () => { await endpoints.planDelete(siteId, p.id); onClose(); }, 'حذف شد'); }}>حذف</Button>
            </div>
            {/* durable generation schedule */}
            <div className='rounded-xl border bg-muted/20 p-3'>
              <div className='mb-3'><div className='font-medium'>تولید و انتشار زمان‌بندی‌شده</div><p className='mt-1 text-xs leading-5 text-muted-foreground'>کار روی سرور ذخیره می‌شود و با بستن صفحه یا جابه‌جایی بین بخش‌ها ادامه پیدا می‌کند. حالت امن پیش‌فرض بعد از تولید منتظر تأیید شما می‌ماند.</p></div>
              <div className='grid gap-2 sm:grid-cols-2'>
                <div className='grid gap-1'><Label>شروع تولید</Label><Input type='datetime-local' value={schedule.scheduled_at} onChange={(e) => setSchedule((s) => ({ ...s, scheduled_at: e.target.value }))} dir='ltr' /></div>
                <div className='grid gap-1'><Label>روش تأیید</Label><NativeSelect value={schedule.approval_mode} onChange={(e) => setSchedule((s) => ({ ...s, approval_mode: e.target.value }))}><NativeSelectOption value='human'>تأیید انسانی (پیشنهادی)</NativeSelectOption><NativeSelectOption value='score_gate'>خودکار با کنترل امتیاز</NativeSelectOption></NativeSelect></div>
                <div className='grid gap-1'><Label>عملیات وردپرس بعد از تأیید</Label><NativeSelect value={schedule.publish_action} onChange={(e) => setSchedule((s) => ({ ...s, publish_action: e.target.value }))}><NativeSelectOption value='none'>فقط داخل پنل</NativeSelectOption><NativeSelectOption value='draft'>ساخت پیش‌نویس وردپرس</NativeSelectOption><NativeSelectOption value='future'>زمان‌بندی واقعی در وردپرس</NativeSelectOption></NativeSelect></div>
                <div className='grid gap-1'><Label>دسته وردپرس</Label><NativeSelect value={schedule.category_id} onChange={(e) => setSchedule((s) => ({ ...s, category_id: e.target.value }))}><NativeSelectOption value=''>بدون دسته</NativeSelectOption>{categories.filter((c) => c.wordpress_category_id).map((c) => <NativeSelectOption key={c.id} value={String(c.wordpress_category_id)}>{c.name}</NativeSelectOption>)}</NativeSelect></div>
                {schedule.publish_action === 'future' && <div className='grid gap-1'><Label>زمان انتشار در وردپرس</Label><Input type='datetime-local' value={schedule.publish_at} onChange={(e) => setSchedule((s) => ({ ...s, publish_at: e.target.value }))} dir='ltr' /></div>}
                {schedule.approval_mode === 'score_gate' && <div className='grid gap-1'><Label>حداقل امتیاز کیفیت</Label><Input type='number' min={0} max={100} value={schedule.min_score} onChange={(e) => setSchedule((s) => ({ ...s, min_score: e.target.value }))} dir='ltr' /></div>}
              </div>
              {schedule.approval_mode === 'score_gate' && <p className='mt-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-700 dark:text-amber-300'>انتشار خودکار فقط وقتی انجام می‌شود که بازبینی «آماده» باشد و امتیاز از حد تعیین‌شده کمتر نباشد. اتصال Application Password وردپرس نیز باید معتبر باشد.</p>}
              <div className='mt-3 flex justify-end'><Button size='sm' disabled={!!busy || !schedule.scheduled_at || (schedule.publish_action === 'future' && !schedule.publish_at)} onClick={() => run('schedule', () => endpoints.planGenPrepare(siteId, p.id, 'article', { scheduled_at: schedule.scheduled_at, publish_at: schedule.publish_at || null, publish_action: schedule.publish_action, approval_mode: schedule.approval_mode, category_ids: schedule.category_id ? [Number(schedule.category_id)] : [], min_score: Number(schedule.min_score || 85) }), 'زمان‌بندی روی سرور ذخیره شد')}>ثبت زمان‌بندی</Button></div>
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
              <div className='grid gap-1'><Label>تاریخ انتشار (شمسی)</Label><JalaliDateInput value={p.publish_date} onChange={(d) => run('pd', () => endpoints.planPatch(siteId, p.id, { publish_date: d }))} /></div>
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
            {/* AI generation + WordPress publish — same parameters as «آزمایش تولید محتوا», stored per-plan in metadata.ai */}
            <div className='rounded-md border p-2'>
              <div className='flex flex-wrap items-center gap-2 text-xs'>
                <span className='font-medium'>تولید با هوش مصنوعی و انتشار در وردپرس</span>
                <span className='text-muted-foreground'>فقط تایتل و کلمات کلیدی را وارد کنید — بقیه با همان موتور «آزمایش تولید محتوا» ساخته می‌شود و دقیقاً در تاریخ تقویم با دسته انتخابی منتشر می‌شود.</span>
              </div>
              <div className='mt-2 grid gap-2 md:grid-cols-3'>
                <div className='grid gap-1'><Label>ارائه‌دهنده</Label><NativeSelect value={ai.provider ?? ''} onChange={(e) => setAi((s) => ({ ...s, provider: e.target.value || null, model: null }))}><NativeSelectOption value=''>پیش‌فرض ({opts?.default?.provider ?? 'auto'})</NativeSelectOption>{(opts?.providers ?? []).filter((x) => x.name !== 'echo').map((x) => <NativeSelectOption key={x.name} value={x.name}>{x.name} ({x.kind_label ?? x.kind})</NativeSelectOption>)}</NativeSelect></div>
                <div className='grid gap-1'><Label>مدل</Label><Input value={ai.model ?? ''} onChange={(e) => setAi((s) => ({ ...s, model: e.target.value || null }))} list='plan-ai-models' dir='ltr' placeholder={(opts?.providers ?? []).find((x) => x.name === ai.provider)?.default_model ?? opts?.default?.model ?? ''} /><datalist id='plan-ai-models'>{((opts?.providers ?? []).find((x) => x.name === ai.provider)?.models ?? []).map((m) => <option key={m.model_id} value={m.model_id}>{m.display}</option>)}</datalist></div>
                <div className='grid gap-1'><Label>لحن</Label><NativeSelect value={ai.tone ?? ''} onChange={(e) => setAi((s) => ({ ...s, tone: e.target.value || null }))}><NativeSelectOption value=''>رسمی (پیش‌فرض)</NativeSelectOption>{(opts?.tones ?? []).map((t) => <NativeSelectOption key={t.key} value={t.key}>{t.fa}</NativeSelectOption>)}</NativeSelect></div>
                <div className='grid gap-1'><Label>نوع محتوا</Label><NativeSelect value={ai.content_type ?? ''} onChange={(e) => setAi((s) => ({ ...s, content_type: e.target.value || null }))}><NativeSelectOption value=''>مقاله (پیش‌فرض)</NativeSelectOption>{(opts?.content_types ?? []).map((t) => <NativeSelectOption key={t.key} value={t.key}>{t.fa}</NativeSelectOption>)}</NativeSelect></div>
                <div className='grid gap-1'><Label>تعداد کلمات</Label><Input type='number' min={150} max={6000} value={ai.word_count ?? ''} onChange={(e) => setAi((s) => ({ ...s, word_count: e.target.value ? Number(e.target.value) : null }))} dir='ltr' placeholder='1200' /></div>
                <div className='grid gap-1'><Label>مخاطب (اختیاری، جای «مخاطب هدف»)</Label><Input value={ai.audience ?? ''} onChange={(e) => setAi((s) => ({ ...s, audience: e.target.value || null }))} placeholder={p.target_audience ?? ''} /></div>
                <div className='grid gap-1 md:col-span-3'><Label>پرامپت دستی (دستورالعمل اضافه برای مدل)</Label><Textarea rows={3} value={ai.prompt ?? ''} onChange={(e) => setAi((s) => ({ ...s, prompt: e.target.value || null }))} placeholder='مثلاً: از مثال‌های واقعی تهران استفاده کن؛ شماره تماس را در پاراگراف اول بیاور…' /></div>
              </div>
              <div className='mt-2 flex flex-wrap items-center gap-1'>
                <Button size='sm' variant='outline' disabled={!!busy} onClick={() => run('ai-save', () => endpoints.planPatch(siteId, p.id, { metadata: { ...(p.metadata ?? {}), ai: Object.fromEntries(Object.entries(ai).filter(([, v]) => v !== null && v !== '')) } }), 'تنظیمات AI ذخیره شد')}>{busy === 'ai-save' ? '…' : 'ذخیره تنظیمات AI'}</Button>
                <Button size='sm' disabled={!!busy} onClick={() => run('gen', async () => { await endpoints.planPatch(siteId, p.id, { metadata: { ...(p.metadata ?? {}), ai: Object.fromEntries(Object.entries(ai).filter(([, v]) => v !== null && v !== '')) } }); const r = await endpoints.planGenerate(siteId, p.id); toast.info(`تولید پیش‌نویس در صف اجرا قرار گرفت (${r.job_id}) — نتیجه در رویدادها و مغز محتوا ظاهر می‌شود`); })}>{busy === 'gen' ? '…' : 'تولید پیش‌نویس'}</Button>
                <Button size='sm' variant='secondary' disabled={!!busy} onClick={() => { if (confirm(`محتوای این برنامه در وردپرس سایت منتشر شود؟${p.publish_date ? `\nتاریخ انتشار: ${jalaliLong(p.publish_date)}${p.publish_time ? ` ساعت ${p.publish_time}` : ''}` : ''}${p.category?.name ? `\nدسته: ${p.category.name}` : ''}\n(اگر پیش‌نویسی نباشد، اول تولید می‌شود)`)) run('pub-now', async () => { const r = await endpoints.planPublish(siteId, p.id); toast.info(`انتشار در صف اجرا قرار گرفت (${r.job_id})`); }); }}>{busy === 'pub-now' ? '…' : 'انتشار در وردپرس'}</Button>
                {p.publishing?.wp_post_id && <Badge variant='outline' dir='ltr'><a className='underline' href={p.publishing.link} target='_blank' rel='noreferrer'>منتشرشده · پست #{p.publishing.wp_post_id}</a></Badge>}
                <Button size='sm' variant='ghost' disabled={!!busy} onClick={() => run('cap', async () => { const r = await endpoints.wpPublishCapability(siteId); (r.can_publish ? toast.success : toast.warning)(r.message); })}>{busy === 'cap' ? '…' : 'بررسی دسترسی وردپرس'}</Button>
              </div>
              <p className='text-muted-foreground mt-1 text-xs'>انتشار خودکار در تاریخ تقویم فقط وقتی انجام می‌شود که حالت سایت «خودکار» باشد؛ دکمه «انتشار در وردپرس» همیشه با کلیک شما (تأیید انسانی) کار می‌کند.</p>
            </div>
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
            <details className='rounded-md border p-2 text-xs'><summary className='cursor-pointer'>کارهای تولید AI ({p.generation_jobs?.length ?? 0}) · تنظیمات انتشار · رویدادها ({p.events?.length ?? 0})</summary>
              <ul className='mt-2 space-y-1'>{(p.generation_jobs ?? []).map((j: any) => <li key={j.id} className='rounded-md border p-2'><div className='flex flex-wrap items-center gap-2'><b>#{j.id}</b><Badge variant={j.status === 'failed' || j.status === 'needs_changes' ? 'destructive' : 'secondary'}>{jobStatusFa(j.status)}</Badge><span>{j.kind}</span>{j.scheduled_at && <span className='text-muted-foreground' dir='ltr'>{j.scheduled_at.slice(0, 16)}</span>}{j.status === 'awaiting_approval' && <Button size='sm' onClick={() => run(`approve-${j.id}`, () => endpoints.planGenApprove(siteId, j.id), 'محتوا تأیید و مرحله بعد انجام شد')}>تأیید و ادامه</Button>}{['failed', 'needs_changes'].includes(j.status) && <Button size='sm' variant='outline' onClick={() => run(`retry-${j.id}`, () => endpoints.planGenRun(siteId, j.id, true), 'اجرای مجدد در صف قرار گرفت')}>تلاش دوباره</Button>}</div>{j.generation_run_id && <div className='mt-1 text-muted-foreground' dir='ltr'>run {j.generation_run_id}</div>}{j.last_error && <div className='mt-1 text-destructive'>{j.last_error}</div>}</li>)}</ul>
              <div className='mt-2 flex flex-wrap items-end gap-2'><div className='grid gap-1'><Label>وضعیت هدف در وردپرس</Label><NativeSelect value={p.publishing?.wp_status ?? ''} onChange={(e) => run('pub', () => endpoints.planPublishing(siteId, p.id, { target: 'wordpress', wp_status: e.target.value }), 'تنظیم انتشار ذخیره شد')}><NativeSelectOption value=''>—</NativeSelectOption><NativeSelectOption value='draft'>پیش‌نویس</NativeSelectOption><NativeSelectOption value='publish'>انتشار فوری</NativeSelectOption><NativeSelectOption value='future'>زمان‌بندی‌شده</NativeSelectOption></NativeSelect></div>{p.content_item ? <Link className='underline' href={`/dashboard/content?site=${siteId}`}>باز کردن آیتم محتوا و انتشار واقعی</Link> : <span className='text-muted-foreground'>ابتدا آیتم محتوا/پیش‌نویس را بسازید.</span>}</div>
              <ul className='text-muted-foreground mt-2 space-y-0.5'>{(p.events ?? []).slice(0, 15).map((e: any) => <li key={e.id}>{e.created_at.slice(0, 16).replace('T', ' ')} · {e.event}{e.to_value ? ` → ${e.to_value}` : ''} · {e.actor}</li>)}</ul>
            </details>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
