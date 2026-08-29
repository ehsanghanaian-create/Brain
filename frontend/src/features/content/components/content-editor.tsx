'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Separator } from '@/components/ui/separator';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { ApiError, endpoints, type ContentBrief, type ContentDetail, type ContentStatus, type KeywordRow, type WordPressCategory, type WordPressPublication } from '@/lib/api/client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { INTENT_FA, PRIORITY_FA, STATUS_COLOR, STATUS_FA, STATUS_ORDER } from '../constants';
import { JalaliDateInput } from './jalali-date-input';
import { DraftPanel } from './draft-panel';

export function ContentEditor({ siteId, cid, onClose, onChanged }: { siteId: string; cid: number | 'new' | null; onClose: () => void; onChanged: () => void }) {
  const [d, setD] = useState<ContentDetail | null>(null);
  const [f, setF] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [kwQuery, setKwQuery] = useState('');
  const [kwOptions, setKwOptions] = useState<KeywordRow[]>([]);
  const [categories, setCategories] = useState<WordPressCategory[]>([]);
  const [publication, setPublication] = useState<WordPressPublication | null>(null);
  const [publishAction, setPublishAction] = useState<'draft' | 'publish' | 'future'>('draft');
  const [tab, setTab] = useState<'fields' | 'brief' | 'draft' | 'publish' | 'history'>('fields');
  const open = cid !== null;

  const load = () => {
    if (typeof cid !== 'number') return;
    endpoints.content(siteId, cid).then((x) => {
      setD(x);
      setTab(x.current_draft_id ? 'draft' : 'fields');
      const wpCats = Array.isArray(x.metadata?.wordpress_category_ids) ? x.metadata.wordpress_category_ids : [];
      setF({ title: x.title, target_keyword: x.target_keyword ?? '', topic: x.topic ?? '', intent: x.intent ?? '', priority: x.priority ?? '', publish_date: x.publish_date ?? '', publish_time: x.publish_time ?? '', wordpress_category_id: String(wpCats[0] ?? ''),
             url: x.url ?? '', ai_provider: x.ai_provider ?? '', ai_model: x.ai_model ?? '', notes: x.notes ?? '' });
      endpoints.contentPublication(siteId, cid, false).then((r) => setPublication(r.publication)).catch(() => setPublication(null));
    }).catch((e) => toast.error(e instanceof ApiError ? e.message : String(e)));
  };
  useEffect(() => {
    if (cid === null) return;
    setTab('fields');
    endpoints.wordpressCategories(siteId).then(setCategories).catch(() => setCategories([]));
    if (cid === 'new') { setD(null); setPublication(null); setF({ title: '', target_keyword: '', topic: '', intent: '', priority: '', publish_date: '', publish_time: '', wordpress_category_id: '', url: '', ai_provider: '', ai_model: '', notes: '' }); return; }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, cid]);
  useEffect(() => {
    if (!kwQuery.trim()) { setKwOptions([]); return; }
    const t = setTimeout(() => endpoints.keywords(siteId, { q: kwQuery, limit: 8 }).then((r) => setKwOptions(r.items)).catch(() => null), 250);
    return () => clearTimeout(t);
  }, [kwQuery, siteId]);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setF((s) => ({ ...s, [k]: e.target.value }));

  async function save() {
    setBusy('save');
    try {
      const metadata = { ...(d?.metadata ?? {}), wordpress_category_ids: f.wordpress_category_id ? [Number(f.wordpress_category_id)] : [] };
      const body: Record<string, unknown> = { title: f.title.trim(), target_keyword: f.target_keyword || undefined, topic: f.topic || undefined, intent: f.intent || undefined, priority: f.priority || undefined, metadata,
        publish_date: f.publish_date || undefined, publish_time: f.publish_time || undefined, url: f.url || undefined, ai_provider: f.ai_provider || undefined, ai_model: f.ai_model || undefined, notes: f.notes || undefined };
      if (cid === 'new') { const it = await endpoints.createContent(siteId, body); toast.success('محتوا ایجاد شد'); onChanged(); onClose(); return void it; }
      if (typeof cid === 'number') { await endpoints.updateContent(siteId, cid, { ...body, clear_date: !f.publish_date }); toast.success('ذخیره شد'); onChanged(); load(); }
    } catch (e) { toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)); } finally { setBusy(null); }
  }
  async function transition(to: ContentStatus) {
    if (typeof cid !== 'number') return;
    setBusy('t');
    try { await endpoints.transitionContent(siteId, cid, to); toast.success(`وضعیت: ${STATUS_FA[to]}`); onChanged(); load(); }
    catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); } finally { setBusy(null); }
  }
  async function brief(useAi: boolean) {
    if (typeof cid !== 'number') return;
    setBusy('brief');
    try { const b = await endpoints.generateBrief(siteId, cid, { use_ai: useAi, mark_ready: true }); toast.success(`بریف نسخه ${b.version} ساخته شد`); onChanged(); load(); setTab('brief'); }
    catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); } finally { setBusy(null); }
  }
  async function remove() {
    if (typeof cid !== 'number' || !confirm('این محتوا با بریف‌ها و تاریخچه حذف شود؟')) return;
    await endpoints.deleteContent(siteId, cid); toast.success('حذف شد'); onChanged(); onClose();
  }

  async function sendToWordPress() {
    if (typeof cid !== 'number') return;
    setBusy('publish');
    try {
      const scheduledAt = publishAction === 'future' ? `${f.publish_date ?? ''}T${f.publish_time ?? ''}` : null;
      if (publishAction === 'future' && (!(f.publish_date ?? '') || !(f.publish_time ?? ''))) throw new Error('برای زمان‌بندی، تاریخ و ساعت را کامل کنید.');
      const result = await endpoints.publishContent(siteId, cid, { action: publishAction, category_ids: f.wordpress_category_id ? [Number(f.wordpress_category_id)] : [], scheduled_at: scheduledAt });
      setPublication(result);
      toast.success(publishAction === 'future' ? `در وردپرس برای ${result.scheduled_at} زمان‌بندی شد` : publishAction === 'publish' ? 'مقاله در وردپرس منتشر شد' : 'پیش‌نویس در وردپرس ذخیره شد');
      onChanged(); load();
    } catch (e) { toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)); } finally { setBusy(null); }
  }

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side='left' className='w-full overflow-y-auto p-4 sm:max-w-4xl xl:max-w-5xl' dir='rtl'>
        <SheetHeader className='p-0'>
          <SheetTitle className='flex items-center gap-2'>{cid === 'new' ? 'محتوای جدید' : d?.title ?? '…'}{d && <Badge style={{ background: STATUS_COLOR[d.status] }}>{d.status_fa}</Badge>}</SheetTitle>
          <SheetDescription>{d?.target_keyword ? `کلمه کلیدی هدف: ${d.target_keyword}` : 'محتوا را به یک کلمه کلیدی وصل کنید تا بریف از داده‌های واقعی ساخته شود'}{d?.metadata?.plan_id ? <> · <a className='underline' href={`/dashboard/content-planner?site=${siteId}&plan=${String(d.metadata.plan_id)}`}>برنامه محتوایی #{String(d.metadata.plan_id)}</a></> : null}</SheetDescription>
        </SheetHeader>
        {d && (
          <div className='mt-2 flex flex-wrap items-center gap-1'>
            {STATUS_ORDER.map((s) => <span key={s} className='rounded px-1.5 py-0.5 text-[10px]' style={{ background: s === d.status ? STATUS_COLOR[s] : `${STATUS_COLOR[s]}22`, color: s === d.status ? '#fff' : undefined }}>{STATUS_FA[s]}</span>)}
          </div>
        )}
        {d && (
          <div className='mt-2 flex flex-wrap gap-1'>
            {d.allowed_transitions.map((t) => (
              <Button key={t} size='sm' variant={STATUS_ORDER.indexOf(t) > STATUS_ORDER.indexOf(d.status) ? 'default' : 'outline'} disabled={!!busy} onClick={() => transition(t)}>
                {STATUS_ORDER.indexOf(t) > STATUS_ORDER.indexOf(d.status) ? '→ ' : '← '}{STATUS_FA[t]}
              </Button>
            ))}
            {d.status === 'approved' && !d.url && <span className='text-muted-foreground text-xs'>برای «منتشرشده» ابتدا URL نهایی را ثبت کنید (انتشار خودکار فعال نیست)</span>}
            {d.status === 'review' && d.review_status !== 'ready' && <span className='text-muted-foreground text-xs'>دروازه بازبینی: برای تأیید، آخرین پیش‌نویس باید «آماده» باشد ({d.review_status === 'changes_requested' ? 'نیاز به اصلاح' : 'بازبینی نشده'})</span>}
          </div>
        )}
        {d && (
          <div className='mt-3 flex gap-1 border-b text-sm'>
            {(['fields', 'brief', 'draft', 'publish', 'history'] as const).map((t) => <button key={t} className={`px-3 py-1 ${tab === t ? 'border-primary border-b-2 font-medium' : 'text-muted-foreground'}`} onClick={() => setTab(t)}>{t === 'fields' ? 'مشخصات' : t === 'brief' ? `بریف${d.brief ? ` (v${d.brief.version})` : ''}` : t === 'draft' ? `پیش‌نویس و امتیاز${d.latest_score != null ? ` (${d.latest_score})` : ''}` : t === 'publish' ? `انتشار وردپرس${d.wp_post_id ? ` (#${d.wp_post_id})` : ''}` : `تاریخچه (${d.events.length})`}</button>)}
          </div>
        )}
        {(tab === 'fields' || !d) && (
          <div className='grid gap-3 py-3 text-sm'>
            <div className='grid gap-1.5'><Label>عنوان</Label><Input value={f.title ?? ''} onChange={set('title')} /></div>
            <div className='grid gap-1.5 relative'>
              <Label>کلمه کلیدی هدف</Label>
              <Input value={f.target_keyword ?? ''} onChange={(e) => { set('target_keyword')(e); setKwQuery(e.target.value); }} placeholder='جست‌وجو در کلمات کلیدی…' />
              {kwOptions.length > 0 && (
                <ul className='bg-popover absolute top-full z-10 mt-1 w-full rounded border shadow'>
                  {kwOptions.map((k) => <li key={k.id}><button className='hover:bg-accent w-full px-2 py-1 text-start text-xs' onClick={() => { setF((s) => ({ ...s, target_keyword: k.keyword, intent: k.intent ?? s.intent, topic: k.topic ?? s.topic, priority: k.priority ?? s.priority })); setKwOptions([]); setKwQuery(''); }}>{k.keyword} {k.gsc?.position != null && <span className='text-muted-foreground' dir='ltr'>#{k.gsc.position.toFixed(1)}</span>}</button></li>)}
                </ul>
              )}
            </div>
            <div className='grid grid-cols-2 gap-2'>
              <div className='grid gap-1.5'><Label>موضوع</Label><Input value={f.topic ?? ''} onChange={set('topic')} /></div>
              <div className='grid gap-1.5'><Label>اینتنت</Label><NativeSelect value={f.intent ?? ''} onChange={set('intent')}><NativeSelectOption value=''>—</NativeSelectOption>{Object.entries(INTENT_FA).map(([k, v]) => <NativeSelectOption key={k} value={k}>{v}</NativeSelectOption>)}</NativeSelect></div>
              <div className='grid gap-1.5'><Label>اولویت</Label><NativeSelect value={f.priority ?? ''} onChange={set('priority')}><NativeSelectOption value=''>—</NativeSelectOption>{Object.entries(PRIORITY_FA).map(([k, v]) => <NativeSelectOption key={k} value={k}>{v}</NativeSelectOption>)}</NativeSelect></div>
              <div className='grid gap-1.5'><Label>تاریخ انتشار (شمسی)</Label><JalaliDateInput value={f.publish_date || null} onChange={(d) => setF((s: any) => ({ ...s, publish_date: d ?? '' }))} /></div>
              <div className='grid gap-1.5'><Label>ساعت</Label><Input type='time' value={f.publish_time ?? ''} onChange={set('publish_time')} dir='ltr' /></div>
              <div className='grid gap-1.5'><Label>دسته‌بندی واقعی وردپرس</Label><NativeSelect value={f.wordpress_category_id ?? ''} onChange={set('wordpress_category_id')}><NativeSelectOption value=''>بدون دسته مشخص</NativeSelectOption>{categories.map((c) => <NativeSelectOption key={c.wordpress_category_id} value={c.wordpress_category_id}>{c.name} ({c.post_count})</NativeSelectOption>)}</NativeSelect>{categories.length === 0 && <span className='text-muted-foreground text-[11px]'>دسته‌ای همگام نشده؛ از تب انتشار همگام‌سازی کنید.</span>}</div>
              <div className='grid gap-1.5'><Label>ارائه‌دهنده AI</Label><Input value={f.ai_provider ?? ''} onChange={set('ai_provider')} placeholder='مثلاً Claude' /></div>
              <div className='grid gap-1.5'><Label>مدل</Label><Input value={f.ai_model ?? ''} onChange={set('ai_model')} dir='ltr' /></div>
            </div>
            <div className='grid gap-1.5'><Label>URL نهایی</Label><Input value={f.url ?? ''} onChange={set('url')} dir='ltr' placeholder='https://…' /></div>
            <div className='grid gap-1.5'><Label>یادداشت</Label><Textarea rows={2} value={f.notes ?? ''} onChange={set('notes')} /></div>
            <div className='flex items-center justify-between'>
              <div className='flex gap-1'>{typeof cid === 'number' && <Button variant='ghost' size='sm' className='text-destructive' onClick={remove}>حذف</Button>}</div>
              <div className='flex gap-1'>
                {typeof cid === 'number' && <Button variant='secondary' disabled={!!busy} onClick={() => brief(false)}>{busy === 'brief' ? '…' : d?.brief ? 'بریف جدید' : 'تولید بریف'}</Button>}
                <Button onClick={save} disabled={!!busy || !(f.title ?? '').trim()}>{busy === 'save' ? '…' : 'ذخیره'}</Button>
              </div>
            </div>
            {d?.keyword && (
              <div className='rounded border p-2 text-xs'>
                <div className='font-medium'>کلمه کلیدی: {d.keyword.keyword} {d.keyword.gsc && <span className='text-muted-foreground' dir='ltr'>· #{d.keyword.gsc.position?.toFixed(1)} · {d.keyword.gsc.impressions} imp · {d.keyword.gsc.clicks} clk</span>}</div>
                <Link href={`/dashboard/keywords?site=${siteId}`} className='underline'>مشاهده در کلمات کلیدی</Link>
              </div>
            )}
          </div>
        )}
        {tab === 'brief' && d && (
          <div className='py-3 text-sm'>
            {!d.brief ? (
              <div className='space-y-2'><p className='text-muted-foreground'>هنوز بریفی ساخته نشده است.</p><Button onClick={() => brief(false)} disabled={!!busy}>تولید بریف از کلمه کلیدی، خوشه، GSC و گراف</Button></div>
            ) : <BriefView b={d.brief} onRegenerate={(ai) => brief(ai)} busy={!!busy} />}
          </div>
        )}
        {tab === 'draft' && d && typeof cid === 'number' && <DraftPanel siteId={siteId} cid={cid} onChanged={() => { onChanged(); load(); }} />}
        {tab === 'publish' && d && typeof cid === 'number' && (
          <div className='grid gap-3 py-3 text-sm'>
            <div className='rounded-md border p-3'>
              <div className='flex flex-wrap items-center gap-2'><b>اتصال انتشار وردپرس</b>{publication?.status && <Badge variant={publication.status === 'publish' ? 'default' : 'secondary'}>{publication.status === 'future' ? 'زمان‌بندی‌شده' : publication.status === 'publish' ? 'منتشرشده' : 'پیش‌نویس'}</Badge>}{publication?.url && <a href={publication.url} target='_blank' rel='noreferrer' className='ms-auto underline' dir='ltr'>مشاهده نوشته ↗</a>}</div>
              <p className='text-muted-foreground mt-1 text-xs'>انتشار با Application Password انجام می‌شود. زمان‌بندی داخل خود WordPress ذخیره می‌شود و با بستن تب یا جابه‌جایی بین صفحات لغو نمی‌شود.</p>
              {publication?.scheduled_at && <p className='mt-1 text-xs' dir='ltr'>Local: {publication.scheduled_at} · UTC: {publication.scheduled_at_utc}</p>}
            </div>
            <div className='grid gap-2 rounded-md border p-3 md:grid-cols-2'>
              <div className='grid gap-1.5'><Label>دسته‌بندی سایت</Label><NativeSelect value={f.wordpress_category_id ?? ''} onChange={set('wordpress_category_id')}><NativeSelectOption value=''>بدون دسته مشخص</NativeSelectOption>{categories.map((c) => <NativeSelectOption key={c.wordpress_category_id} value={c.wordpress_category_id}>{c.name} · {c.post_count} نوشته</NativeSelectOption>)}</NativeSelect></div>
              <div className='grid gap-1.5'><Label>عملیات</Label><NativeSelect value={publishAction} onChange={(e) => setPublishAction(e.target.value as typeof publishAction)}><NativeSelectOption value='draft'>ارسال به‌عنوان پیش‌نویس</NativeSelectOption><NativeSelectOption value='future'>زمان‌بندی انتشار</NativeSelectOption><NativeSelectOption value='publish'>انتشار فوری</NativeSelectOption></NativeSelect></div>
              {publishAction === 'future' && <><div className='grid gap-1.5'><Label>تاریخ سایت</Label><Input type='date' value={f.publish_date ?? ''} onChange={set('publish_date')} dir='ltr' /></div><div className='grid gap-1.5'><Label>ساعت سایت</Label><Input type='time' value={f.publish_time ?? ''} onChange={set('publish_time')} dir='ltr' /></div></>}
              <div className='flex flex-wrap gap-2 md:col-span-2'>
                <Button disabled={!!busy || !d.current_draft_id || (publishAction !== 'draft' && !['approved', 'published'].includes(d.status))} onClick={sendToWordPress}>{busy === 'publish' ? 'در حال ارسال…' : publishAction === 'future' ? 'ثبت زمان‌بندی واقعی' : publishAction === 'publish' ? 'انتشار فوری مقاله' : 'ساخت/به‌روزرسانی پیش‌نویس وردپرس'}</Button>
                <Button variant='outline' disabled={!!busy} onClick={async () => { try { await endpoints.planCategoriesSync(siteId); setCategories(await endpoints.wordpressCategories(siteId)); toast.success('دسته‌های وردپرس به‌روز شد'); } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); } }}>به‌روزرسانی دسته‌ها</Button>
                {d.wp_post_id && <Button variant='ghost' disabled={!!busy} onClick={async () => { try { const r = await endpoints.contentPublication(siteId, cid, true); setPublication(r.publication); toast.success('وضعیت از وردپرس بررسی شد'); load(); } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); } }}>بررسی وضعیت واقعی</Button>}
              </div>
              {!d.current_draft_id && <p className='text-destructive text-xs md:col-span-2'>هنوز پیش‌نویسی برای ارسال وجود ندارد.</p>}
              {publishAction !== 'draft' && !['approved', 'published'].includes(d.status) && <p className='text-destructive text-xs md:col-span-2'>برای انتشار فوری یا زمان‌بندی، محتوا باید ابتدا از مرحله بازبینی تأیید شود. ارسال پیش‌نویس محدودیت ندارد.</p>}
            </div>
          </div>
        )}
        {tab === 'history' && d && (
          <ul className='space-y-1 py-3 text-xs'>
            {d.events.map((e) => (
              <li key={e.id} className='rounded border p-2'>
                <div className='flex justify-between'><span>{e.to_status ? `${e.from_status ? STATUS_FA[e.from_status as ContentStatus] + ' → ' : ''}${STATUS_FA[e.to_status as ContentStatus]}` : 'یادداشت'}</span><span className='text-muted-foreground' dir='ltr'>{e.actor} · {e.created_at.slice(0, 16).replace('T', ' ')}</span></div>
                {e.note && <div className='text-muted-foreground mt-1'>{e.note}</div>}
              </li>
            ))}
          </ul>
        )}
      </SheetContent>
    </Sheet>
  );
}

function BriefView({ b, onRegenerate, busy }: { b: ContentBrief; onRegenerate: (ai: boolean) => void; busy: boolean }) {
  const [showMd, setShowMd] = useState(false);
  const src = b.sources as Record<string, any>;
  return (
    <div className='space-y-3'>
      <div className='flex flex-wrap items-center gap-2 text-xs'>
        <Badge variant='outline'>نسخه {b.version}</Badge>
        <Badge variant='outline'>{String(b.provenance?.generator ?? '')}{b.provenance?.ai_used ? ` + AI ${b.provenance.model}` : ''}</Badge>
        {b.provenance?.note ? <span className='text-muted-foreground'>{String(b.provenance.note)}</span> : null}
        <span className='ms-auto flex gap-1'>
          <Button size='sm' variant='outline' disabled={busy} onClick={() => onRegenerate(false)}>بازتولید</Button>
          <Button size='sm' variant='outline' disabled={busy} onClick={() => onRegenerate(true)} title='با ارائه‌دهنده AI پیکربندی‌شده (در صورت وجود)'>بازتولید با AI</Button>
          <Button size='sm' variant='ghost' onClick={() => setShowMd((v) => !v)}>{showMd ? 'نمای ساختاری' : 'Markdown'}</Button>
        </span>
      </div>
      {showMd ? (
        <pre className='bg-muted max-h-[60vh] overflow-auto rounded p-3 text-xs whitespace-pre-wrap' dir='auto'>{b.markdown}</pre>
      ) : (
        <>
          <Section t='H1 پیشنهادی'><div className='font-semibold'>{b.h1}</div><div className='text-muted-foreground text-xs'>عنوان سئو: {b.seo_title}</div><div className='text-muted-foreground text-xs'>متا: {b.meta_description}</div><div className='text-xs'>اینتنت: {INTENT_FA[b.intent ?? ''] ?? b.intent ?? '—'}</div></Section>
          <Section t={`ساختار سرفصل‌ها (${b.outline.length})`}>
            <ol className='space-y-1 ps-4'>{b.outline.map((o, i) => <li key={i}><span className='font-medium'>H2: {o.h2}</span>{o.h3?.length ? <ul className='ps-4 text-xs'>{o.h3.map((h, j) => <li key={j}>H3: {h}</li>)}</ul> : null}{o.why && <div className='text-muted-foreground text-[11px]'>{o.why}</div>}</li>)}</ol>
          </Section>
          <Section t={`موجودیت‌ها (${b.entities.length})`}><div className='flex flex-wrap gap-1'>{b.entities.map((e) => <Badge key={e.node_id} variant='secondary'>{e.type}: {e.label}</Badge>)}</div></Section>
          <Section t={`سؤالات (${b.questions.length})`}><ul className='space-y-0.5 text-xs'>{b.questions.map((q, i) => <li key={i}>• {q.question} <span className='text-muted-foreground'>({q.source})</span></li>)}</ul></Section>
          <Section t={`لینک‌های داخلی پیشنهادی (${b.internal_links.length})`}><ul className='space-y-0.5 text-xs'>{b.internal_links.map((l, i) => <li key={i}><span dir='ltr' className='break-all'>{l.url}</span> — انکر «{l.anchor}» — {l.reason}</li>)}</ul></Section>
          {Array.isArray(src.existing_pages) && src.existing_pages.length > 0 && (
            <Section t='صفحات موجود'><ul className='space-y-0.5 text-xs'>{src.existing_pages.map((p: any, i: number) => <li key={i}><span dir='ltr'>{p.url}</span> — {p.recommendation}{p.position != null ? ` (جایگاه ${p.position}, ${p.impressions} ایمپرشن)` : ''}</li>)}</ul></Section>
          )}
          <Section t='منابع'><div className='text-muted-foreground text-xs'>کلمه کلیدی: {src.keyword?.keyword ?? '—'} · هم‌خوشه: {src.cluster?.length ?? 0} · کوئری GSC مرتبط: {src.gsc?.related_queries?.length ?? 0} · رقبا: {src.competitors?.available ? 'دارد' : 'در دسترس نیست (حدس زده نشد)'}</div></Section>
        </>
      )}
    </div>
  );
}

function Section({ t, children }: { t: string; children: React.ReactNode }) {
  return <section><h4 className='mb-1 text-xs font-semibold opacity-70'>{t}</h4>{children}<Separator className='mt-2' /></section>;
}
