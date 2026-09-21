'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOptGroup, NativeSelectOption } from '@/components/ui/native-select';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { JalaliDateInput } from '@/features/content/components/jalali-date-input';
import { jalaliLong } from '@/features/content/constants';
import { PLAN_STATUS_COLOR, PLAN_STATUS_FA } from '@/features/content-planner/constants';
import { parseTags } from '@/features/content-planner/lib';
import { ApiError, endpoints, type ContentPlan, type PlanCategory, type PlanStatus, type WsOptions } from '@/lib/api/client';
import { safeHref } from '@/lib/utils';
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

type Form = { title: string; primary_keyword: string; secondary_keywords: string; category_id: string; publish_date: string | null; publish_time: string; seo_title: string; meta_description: string; provider: string; model: string; tone: string; word_count: string; prompt: string };
import type { EditorTarget } from './article-editor-sheet';

type Props = { siteId: string; pid: number | 'new' | null; defaultDate: string | null; categories: PlanCategory[]; opts: WsOptions | null; onClose: () => void; onChanged: () => void; onOpenEditor: (target: EditorTarget) => void };

const EMPTY: Form = { title: '', primary_keyword: '', secondary_keywords: '', category_id: '', publish_date: null, publish_time: '09:00', seo_title: '', meta_description: '', provider: '', model: '', tone: '', word_count: '', prompt: '' };
const SIMPLE_STATUSES: PlanStatus[] = ['planned', 'writing', 'review', 'approved', 'published'];
const err = (e: unknown) => toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const isFuture = (date: string | null, time: string) => !!date && new Date(`${date}T${time || '09:00'}:00+03:30`).getTime() > Date.now();

function fromPlan(p: ContentPlan): Form {
  const ai = (p.metadata?.ai ?? {}) as Record<string, unknown>;
  return { title: p.title, primary_keyword: p.primary_keyword ?? '', secondary_keywords: (p.secondary_keywords ?? []).join('، '), category_id: p.category_id ? String(p.category_id) : '', publish_date: p.publish_date, publish_time: p.publish_time ?? '09:00', seo_title: p.seo_title ?? '', meta_description: p.meta_description ?? '', provider: String(ai.provider ?? ''), model: String(ai.model ?? ''), tone: String(ai.tone ?? ''), word_count: ai.word_count ? String(ai.word_count) : '', prompt: String(ai.prompt ?? '') };
}

function toBody(f: Form, existing: ContentPlan | null) {
  const ai: Record<string, unknown> = {};
  if (f.provider) ai.provider = f.provider;
  if (f.model) ai.model = f.model;
  if (f.tone) ai.tone = f.tone;
  if (f.word_count) ai.word_count = Number(f.word_count);
  if (f.prompt.trim()) ai.prompt = f.prompt.trim();
  const body: Record<string, unknown> = { title: f.title.trim(), secondary_keywords: parseTags(f.secondary_keywords), seo_title: f.seo_title.trim(), meta_description: f.meta_description.trim(), metadata: { ...(existing?.metadata ?? {}), ai } };
  if (f.primary_keyword.trim()) body.primary_keyword = f.primary_keyword.trim();
  if (f.category_id) body.category_id = Number(f.category_id);
  if (f.publish_date) { body.publish_date = f.publish_date; body.publish_time = f.publish_time || '09:00'; }
  return body;
}

async function pollJob(runId: string) {
  for (let i = 0; i < 120; i += 1) {
    await sleep(2500);
    const r = await endpoints.job(runId);
    if (r.status === 'succeeded' || r.status === 'failed') return r;
  }
  return null;
}

export function ArticleSheet({ siteId, pid, defaultDate, categories, opts, onClose, onChanged, onOpenEditor }: Props) {
  const [id, setIdState] = useState<number | null>(null);
  const idRef = useRef<number | null>(null);
  const setId = (v: number | null) => { idRef.current = v; setIdState(v); };
  const [p, setP] = useState<ContentPlan | null>(null);
  const [f, setF] = useState<Form>(EMPTY);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const open = pid !== null;

  const load = useCallback(async (planId: number) => { try { const d = await endpoints.plan(siteId, planId); setP(d); setF(fromPlan(d)); } catch (e) { err(e); } }, [siteId]);
  useEffect(() => {
    if (pid === null) return;
    if (pid === 'new') { setP(null); setId(null); setF({ ...EMPTY, publish_date: defaultDate }); return; }
    setId(pid); load(pid);
  }, [pid, defaultDate, load]);

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setF((s) => ({ ...s, [k]: e.target.value }));
  const wpCategories = categories.filter((c) => c.wordpress_category_id);
  const providers = (opts?.providers ?? []).filter((x) => x.name !== 'echo');
  const pub = (p?.publishing ?? {}) as Record<string, any>;
  const draftCount = p?.content_item?.draft_count ?? 0;

  async function persist(): Promise<number> {
    if (!f.title.trim()) throw new Error('عنوان مقاله لازم است');
    const body = toBody(f, p);
    if (id === null) { const created = await endpoints.planCreate(siteId, body); setId(created.id); return created.id; }
    await endpoints.planPatch(siteId, id, body);
    return id;
  }
  async function run(key: string, fn: () => Promise<unknown>, ok?: string) {
    setBusy(key);
    try { await fn(); if (ok) toast.success(ok); }
    catch (e) { err(e); }
    finally {
      setBusy(null); setNote(null);
      if (idRef.current !== null) await load(idRef.current).catch(() => null);
      onChanged();
    }
  }
  const save = () => run('save', async () => { const planId = await persist(); await load(planId); }, 'ذخیره شد');
  const writeWithAi = () => run('gen', async () => {
    const planId = await persist();
    const r = await endpoints.planGenerate(siteId, planId);
    setNote('هوش مصنوعی در حال نوشتن مقاله است — معمولاً ۱ تا ۳ دقیقه…');
    const job = await pollJob(r.job_id);
    if (!job) throw new Error('زمان انتظار تمام شد — کمی بعد دوباره باز کنید');
    const res = (job.result ?? {}) as Record<string, any>;
    if (job.status === 'failed' || res.status !== 'generated') throw new Error(res.message || job.error || 'نوشتن مقاله ناموفق بود');
    toast.success(`مقاله نوشته شد — ${res.word_count ?? '—'} کلمه · امتیاز سئو ${res.seo_score ?? '—'} · ${res.provider ?? ''}`);
    await load(planId);
  });
  const publish = () => {
    if (!p) return;
    const future = isFuture(f.publish_date, f.publish_time);
    const when = f.publish_date ? `${jalaliLong(f.publish_date)} ساعت ${f.publish_time || '09:00'}` : 'همین حالا';
    if (!confirm(future ? `مقاله در وردپرس زمان‌بندی شود و رأس ${when} منتشر گردد؟` : `مقاله همین حالا در وردپرس منتشر شود؟ (تاریخ: ${when})`)) return;
    run('pub', async () => {
      const planId = await persist();
      const r = await endpoints.planPublish(siteId, planId);
      setNote(future ? 'در حال ارسال به وردپرس برای زمان‌بندی…' : 'در حال انتشار در وردپرس…');
      const job = await pollJob(r.job_id);
      if (!job) throw new Error('زمان انتظار تمام شد — وضعیت را بعداً بررسی کنید');
      const res = (job.result ?? {}) as Record<string, any>;
      const out = (res.publish ?? res) as Record<string, any>;
      if (job.status === 'failed' || out.status !== 'published') throw new Error(out.message || res.message || job.error || 'انتشار ناموفق بود');
      toast.success(out.wp_status === 'future' ? `در وردپرس زمان‌بندی شد — رأس ${when} منتشر می‌شود` : 'در وردپرس منتشر شد');
    });
  };
  const remove = () => { if (id !== null && confirm('این مقاله از تقویم حذف شود؟ (متن نوشته‌شده حفظ می‌شود)')) run('del', async () => { await endpoints.planDelete(siteId, id); onClose(); }, 'حذف شد'); };

  return (
    <Sheet open={open} onOpenChange={(o) => !o && !busy && onClose()}>
      <SheetContent side='left' className='overflow-y-auto p-4 data-[side=left]:w-full data-[side=left]:sm:max-w-xl' dir='rtl'>
        <SheetHeader className='p-0'>
          <SheetTitle className='flex flex-wrap items-center gap-2'>
            {p ? p.title : 'مقالهٔ جدید'}
            {p && <Badge style={{ background: PLAN_STATUS_COLOR[p.status] }}>{PLAN_STATUS_FA[p.status]}</Badge>}
          </SheetTitle>
          <SheetDescription>
            {p ? (draftCount ? `${draftCount} نسخه پیش‌نویس${p.content_item?.latest_score != null ? ` · امتیاز سئو ${p.content_item.latest_score}` : ''}` : 'هنوز متنی نوشته نشده — «نوشتن با هوش مصنوعی» را بزنید') : 'عنوان و کلمهٔ کلیدی را بنویسید؛ بقیه را هوش مصنوعی انجام می‌دهد.'}
          </SheetDescription>
        </SheetHeader>

        {pub.wp_post_id && (
          <div className='mt-3 rounded-md border border-emerald-500/40 bg-emerald-500/5 p-2 text-xs'>
            {pub.wp_status === 'future'
              ? <>زمان‌بندی‌شده در وردپرس — رأس {pub.scheduled_for ? `${jalaliLong(String(pub.scheduled_for).slice(0, 10))} ساعت ${String(pub.scheduled_for).slice(11, 16)}` : 'تاریخ تقویم'} منتشر می‌شود</>
              : <>منتشرشده در وردپرس</>}
            {pub.link && <a className='ms-2 underline' href={safeHref(pub.link)} target='_blank' rel='noreferrer' dir='ltr'>پست #{pub.wp_post_id} ↗</a>}
          </div>
        )}

        <div className='mt-3 grid gap-3 text-sm'>
          <div className='grid gap-1'><Label>عنوان مقاله</Label><Input value={f.title} onChange={set('title')} placeholder='مثلاً: راهنمای کامل تعمیر گیربکس اتوماتیک' autoFocus={pid === 'new'} /></div>
          <div className='grid gap-2 md:grid-cols-2'>
            <div className='grid gap-1'><Label>کلمهٔ کلیدی اصلی</Label><Input value={f.primary_keyword} onChange={set('primary_keyword')} placeholder='تعمیر گیربکس اتوماتیک' /></div>
            <div className='grid gap-1'><Label>کلمات کلیدی ثانویه (با ویرگول)</Label><Input value={f.secondary_keywords} onChange={set('secondary_keywords')} placeholder='هزینه تعمیر گیربکس، علائم خرابی گیربکس' /></div>
            <div className='grid gap-1'>
              <Label>دستهٔ وردپرس</Label>
              <NativeSelect value={f.category_id} onChange={set('category_id')}>
                <NativeSelectOption value=''>بدون دسته</NativeSelectOption>
                {wpCategories.map((c) => <NativeSelectOption key={c.id} value={String(c.id)}>{c.name}</NativeSelectOption>)}
              </NativeSelect>
              {wpCategories.length === 0 && <span className='text-muted-foreground text-[11px]'>دسته‌ای از وردپرس همگام نشده — از کارت وردپرس سایت همگام‌سازی کنید.</span>}
            </div>
            <div className='grid gap-1'>
              <Label>وضعیت</Label>
              {p ? (
                <NativeSelect value={p.status} disabled={!!busy} onChange={(e) => run('status', () => endpoints.planTransition(siteId, p.id, e.target.value), `وضعیت → ${PLAN_STATUS_FA[e.target.value as PlanStatus]}`)}>
                  {[p.status, ...p.allowed_transitions].filter((s, i, a) => SIMPLE_STATUSES.includes(s) && a.indexOf(s) === i).map((s) => <NativeSelectOption key={s} value={s}>{PLAN_STATUS_FA[s]}</NativeSelectOption>)}
                </NativeSelect>
              ) : <Input value={PLAN_STATUS_FA.planned} disabled />}
            </div>
            <div className='grid gap-1'><Label>تاریخ انتشار (شمسی)</Label><JalaliDateInput value={f.publish_date} onChange={(d) => setF((s) => ({ ...s, publish_date: d }))} /></div>
            <div className='grid gap-1'><Label>ساعت انتشار</Label><Input type='time' value={f.publish_time} onChange={set('publish_time')} dir='ltr' /></div>
            <div className='grid gap-1 md:col-span-2'>
              <Label>نویسندهٔ هوش مصنوعی و مدل</Label>
              <NativeSelect value={f.provider ? `${f.provider}::${f.model}` : ''} onChange={(e) => { const [prov, mod] = e.target.value.split('::'); setF((s) => ({ ...s, provider: prov ?? '', model: mod ?? '' })); }}>
                <NativeSelectOption value=''>پیش‌فرض{opts?.default?.provider ? ` — ${opts.default.provider}${opts.default.model ? ` / ${opts.default.model}` : ''}` : ''}</NativeSelectOption>
                {providers.filter((p) => p.configured).map((p) => (
                  <NativeSelectOptGroup key={p.name} label={`${p.kind_label ?? p.kind} · ${p.name}`}>
                    <NativeSelectOption value={`${p.name}::`}>مدل پیش‌فرض{p.default_model ? ` (${p.default_model})` : ''}</NativeSelectOption>
                    {p.models.slice(0, 8).map((m) => <NativeSelectOption key={m.model_id} value={`${p.name}::${m.model_id}`}>{m.display || m.model_id}{m.tier ? ` · ${m.tier}` : ''}</NativeSelectOption>)}
                  </NativeSelectOptGroup>
                ))}
              </NativeSelect>
              {providers.filter((p) => p.configured).length === 0 && <span className='text-[11px] text-amber-600'>هیچ نویسنده‌ای کلید ندارد — با دکمهٔ «کلیدها» بالای تقویم، کلید Claude یا Grok را وارد کنید.</span>}
            </div>
            <div className='grid gap-1'><Label>عنوان سئو (اختیاری)</Label><Input value={f.seo_title} onChange={set('seo_title')} /></div>
            <div className='grid gap-1'><Label>توضیحات متا (اختیاری)</Label><Input value={f.meta_description} onChange={set('meta_description')} /><span className='text-muted-foreground text-[10px]'>{f.meta_description.length} نویسه</span></div>
          </div>

          <details className='rounded-md border p-2'>
            <summary className='cursor-pointer text-xs font-medium'>تنظیمات نویسندهٔ هوش مصنوعی</summary>
            <div className='mt-2 grid gap-2 md:grid-cols-2'>
              <div className='grid gap-1'><Label>لحن</Label><NativeSelect value={f.tone} onChange={set('tone')}><NativeSelectOption value=''>رسمی (پیش‌فرض)</NativeSelectOption>{(opts?.tones ?? []).map((t) => <NativeSelectOption key={t.key} value={t.key}>{t.fa}</NativeSelectOption>)}</NativeSelect></div>
              <div className='grid gap-1'><Label>تعداد کلمات</Label><Input type='number' min={300} max={6000} value={f.word_count} onChange={set('word_count')} dir='ltr' placeholder='1200' /></div>
              <div className='grid gap-1 md:col-span-2'><Label>دستور اضافه برای نویسنده</Label><Textarea rows={3} value={f.prompt} onChange={set('prompt')} placeholder='مثلاً: از مثال‌های واقعی تهران استفاده کن؛ شماره تماس را در پاراگراف اول بیاور…' /></div>
            </div>
          </details>

          {note && <p className='text-muted-foreground animate-pulse text-xs'>{note}</p>}

          <div className='flex flex-wrap items-center gap-1'>
            <Button size='sm' variant='outline' disabled={!!busy || !f.title.trim()} onClick={save}>{busy === 'save' ? '…' : 'ذخیره'}</Button>
            <Button size='sm' disabled={!!busy || !f.title.trim()} onClick={writeWithAi}>{busy === 'gen' ? 'در حال نوشتن…' : draftCount ? 'بازنویسی با هوش مصنوعی' : 'نوشتن با هوش مصنوعی'}</Button>
            {p?.content_item && <Button size='sm' variant='secondary' disabled={!!busy} onClick={() => { const t: EditorTarget = { cid: p.content_item!.id, planId: p.id, title: p.title, keyword: p.primary_keyword ?? undefined, featured: (p.metadata?.featured_media as EditorTarget['featured']) ?? null }; onClose(); onOpenEditor(t); }}>ویرایش متن</Button>}
            {p && p.allowed_transitions.includes('approved') && <Button size='sm' variant='secondary' disabled={!!busy} onClick={() => run('ok', () => endpoints.planTransition(siteId, p.id, 'approved'), 'تأیید شد')}>تأیید</Button>}
            {p?.content_item && !pub.wp_post_id && <Button size='sm' variant='secondary' disabled={!!busy || !draftCount} onClick={publish}>{busy === 'pub' ? '…' : isFuture(f.publish_date, f.publish_time) ? 'زمان‌بندی در وردپرس' : 'انتشار در وردپرس'}</Button>}
            {p && <Button size='sm' variant='ghost' className='text-destructive ms-auto' disabled={!!busy} onClick={remove}>حذف</Button>}
          </div>
          {p && !p.content_item && <p className='text-muted-foreground text-[11px]'>بعد از نوشتن با هوش مصنوعی، دکمه‌های «ویرایش متن» و «انتشار» فعال می‌شوند.</p>}
        </div>
      </SheetContent>
    </Sheet>
  );
}
