'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOptGroup, NativeSelectOption } from '@/components/ui/native-select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { EmptyState, ErrorState, LoadingState, StatChip } from '@/components/seo-brain/states';
import { ApiError, endpoints, type ContentItem, type Site, type WsEstimate, type WsOptions, type WsResult, type WsSpec } from '@/lib/api/client';
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

const fa = new Intl.NumberFormat('fa-IR');
const INTENT_FA: Record<string, string> = { informational: 'اطلاعاتی', navigational: 'ناوبری', commercial: 'تجاری', transactional: 'تراکنشی', local: 'محلی' };
const usd = (v: number | null | undefined) => (typeof v === 'number' ? `${v.toFixed(4)}$` : '—');
const KIND_FA: Record<string, string> = { anthropic: 'Claude', openai: 'ChatGPT', google: 'Gemini', openrouter: 'OpenRouter', ollama: 'Ollama', custom: 'API سفارشی', omniroute: 'OmniRoute', echo: 'Echo' };
const ROUTE_KIND_FA: Record<string, string> = { direct: 'ارائه‌دهنده مستقیم', gateway: 'گیت‌وی مسیریابی', offline: 'آفلاین' };
const routeKindOf = (p: { kind: string; route_kind?: string }) => p.route_kind ?? (p.kind === 'echo' ? 'offline' : p.kind === 'omniroute' ? 'gateway' : 'direct');
const STATUS_FA: Record<string, { fa: string; tone: 'good' | 'warn' | 'bad' | 'default' }> = { connected: { fa: 'متصل', tone: 'good' }, untested: { fa: 'کلید ثبت شده — تست نشده', tone: 'warn' }, error: { fa: 'خطا در اتصال', tone: 'bad' }, missing_credentials: { fa: 'کلید ثبت نشده', tone: 'bad' }, offline_fallback: { fa: 'آفلاین (تست)', tone: 'default' } };
const providerLabel = (p?: { name: string; kind: string } | null) => (!p ? '—' : p.kind === 'echo' ? 'Echo (تست آفلاین)' : `${KIND_FA[p.kind] ?? p.kind} · ${p.name}`);
const DIM_FA: Record<string, string> = { intent: 'تطابق با اینتنت', keywords: 'پوشش کلمات کلیدی', entities: 'پوشش موجودیت‌ها', headings: 'ساختار سرفصل‌ها', links: 'کیفیت لینک داخلی', cta: 'کیفیت CTA', completeness: 'کامل بودن' };

export function AiContentTest({ sites, initialSiteId }: { sites: Site[]; initialSiteId: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [opts, setOpts] = useState<WsOptions | null>(null);
  const [optsError, setOptsError] = useState<unknown>(null);
  const [spec, setSpec] = useState<WsSpec>({ title: '', keyword: '', secondary_keywords: [], intent: 'transactional', content_type: 'article', category: '', audience: '', tone: 'formal', word_count: 1200, instructions: '', provider: null, model: null });
  const [secondary, setSecondary] = useState('');
  const [est, setEst] = useState<WsEstimate | null>(null);
  const [res, setRes] = useState<WsResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<'est' | 'gen' | 'save' | null>(null);
  const [items, setItems] = useState<ContentItem[]>([]);
  const [saveTo, setSaveTo] = useState('');
  const [history, setHistory] = useState<any[]>([]);
  const loadOpts = useCallback(async () => {
    setOptsError(null);
    try {
      const [o, c, h] = await Promise.all([endpoints.wsOptions(siteId), endpoints.contentList(siteId, { limit: 200 }), endpoints.wsHistory(siteId)]);
      setOpts(o); setItems(c.items); setHistory(h);
      // default = Claude Sonnet when Claude is configured; Echo only as offline fallback
      const d = o.default ?? { provider: 'echo', model: 'echo-1', kind: 'echo' };
      setSpec((s) => (s.provider && o.providers.some((p) => p.name === s.provider && p.configured) ? s : { ...s, provider: d.provider, model: d.model }));
    }
    catch (e) { setOptsError(e); }
  }, [siteId]);
  useEffect(() => { loadOpts(); }, [loadOpts]);
  const provider = useMemo(() => opts?.providers.find((p) => p.name === spec.provider) ?? opts?.providers.find((p) => p.name === opts?.default?.provider) ?? opts?.providers[0], [opts, spec.provider]);
  const genLabel = provider ? (provider.kind === 'echo' ? 'Echo' : (KIND_FA[provider.kind] ?? provider.name)) : '…';
  const modelDisplay = (id: string | null | undefined) => provider?.models.find((m) => m.model_id === id)?.display ?? id ?? '—';
  const body = useMemo<WsSpec>(() => ({ ...spec, secondary_keywords: secondary.split(/[,،\n]/).map((s) => s.trim()).filter(Boolean), category: spec.category || null, audience: spec.audience || null, instructions: spec.instructions || null }), [spec, secondary]);
  const ready = spec.title.trim().length > 0 && spec.keyword.trim().length > 0;
  // live estimate (debounced)
  useEffect(() => {
    if (!ready) { setEst(null); return; }
    const t = setTimeout(() => { endpoints.wsEstimate(siteId, body).then(setEst).catch(() => setEst(null)); }, 500);
    return () => clearTimeout(t);
  }, [siteId, body, ready]);
  async function generate() {
    setBusy('gen'); setError(null); setRes(null);
    try { const r = await endpoints.wsGenerate(siteId, body); setRes(r); toast.success(r.meta.placeholder ? 'خروجی نمایشی (Echo) تولید شد' : `تولید با ${KIND_FA[r.meta.provider_kind ?? ''] ?? r.meta.provider} / ${r.meta.model} انجام شد`); endpoints.wsHistory(siteId).then(setHistory).catch(() => null); }
    catch (e) { setError(e); toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)); }
    finally { setBusy(null); }
  }
  async function saveDraft() {
    if (!res || !saveTo) return;
    setBusy('save');
    try { const d = await endpoints.wsSaveDraft(siteId, { content_id: Number(saveTo), markdown: res.result.markdown, title: res.result.title, meta_description: res.result.meta_description, meta: res.meta }); toast.success(`پیش‌نویس v${d.version} برای آیتم #${d.content_id} ذخیره شد — امتیاز/بازبینی/تأیید در مغز محتوا`); }
    catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); } finally { setBusy(null); }
  }
  const budgetTone = est?.budget.state === 'ok' ? 'good' : est?.budget.state === 'warning' ? 'warn' : 'bad';

  return (
    <div className='grid gap-4 xl:grid-cols-[minmax(340px,420px)_1fr]'>
      {/* ------------------------------------------------ left: inputs */}
      <div className='flex flex-col gap-4'>
        <Card size='sm'>
          <CardHeader><CardTitle>مشخصات محتوا</CardTitle><CardDescription>ورودی دستی برای آزمایش تولید؛ حافظه سایت (Site Brain) به‌صورت خودکار به پرامپت تزریق می‌شود.</CardDescription></CardHeader>
          <CardContent className='grid gap-2.5 text-sm'>
            <div className='grid gap-1'><Label>سایت</Label><NativeSelect value={siteId} onChange={(e) => { setSiteId(e.target.value); setRes(null); }}>{sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>)}</NativeSelect></div>
            <div className='grid gap-1'><Label>عنوان *</Label><Input value={spec.title} onChange={(e) => setSpec((s) => ({ ...s, title: e.target.value }))} placeholder='مثلاً: امداد خودرو MVM در تهران' /></div>
            <div className='grid gap-1'><Label>کلمه کلیدی اصلی *</Label><Input value={spec.keyword} onChange={(e) => setSpec((s) => ({ ...s, keyword: e.target.value }))} placeholder='امداد خودرو mvm' /></div>
            <div className='grid gap-1'><Label>کلمات کلیدی ثانویه (با ویرگول)</Label><Input value={secondary} onChange={(e) => setSecondary(e.target.value)} placeholder='یدک کش mvm، امداد خودرو mvm تهران' /></div>
            <div className='grid grid-cols-2 gap-2'>
              <div className='grid gap-1'><Label>اینتنت جستجو</Label><NativeSelect value={spec.intent} onChange={(e) => setSpec((s) => ({ ...s, intent: e.target.value }))}>{(opts?.intents ?? Object.keys(INTENT_FA)).map((i) => <NativeSelectOption key={i} value={i}>{INTENT_FA[i] ?? i}</NativeSelectOption>)}</NativeSelect></div>
              <div className='grid gap-1'><Label>نوع محتوا</Label><NativeSelect value={spec.content_type} onChange={(e) => setSpec((s) => ({ ...s, content_type: e.target.value }))}>{(opts?.content_types ?? [{ key: 'article', fa: 'مقاله' }]).map((c) => <NativeSelectOption key={c.key} value={c.key}>{c.fa}</NativeSelectOption>)}</NativeSelect></div>
              <div className='grid gap-1'><Label>دسته</Label><Input value={spec.category ?? ''} onChange={(e) => setSpec((s) => ({ ...s, category: e.target.value }))} placeholder='MVM' /></div>
              <div className='grid gap-1'><Label>مخاطب هدف</Label><Input value={spec.audience ?? ''} onChange={(e) => setSpec((s) => ({ ...s, audience: e.target.value }))} placeholder='مالکان MVM در تهران' /></div>
              <div className='grid gap-1'><Label>لحن</Label><NativeSelect value={spec.tone} onChange={(e) => setSpec((s) => ({ ...s, tone: e.target.value }))}>{(opts?.tones ?? [{ key: 'formal', fa: 'رسمی' }]).map((t) => <NativeSelectOption key={t.key} value={t.key}>{t.fa}</NativeSelectOption>)}</NativeSelect></div>
              <div className='grid gap-1'><Label>تعداد کلمات</Label><Input type='number' min={150} max={6000} step={50} value={spec.word_count} onChange={(e) => setSpec((s) => ({ ...s, word_count: Number(e.target.value) || 1200 }))} dir='ltr' /></div>
            </div>
          </CardContent>
        </Card>
        <Card size='sm'>
          <CardHeader><CardTitle>دستورالعمل‌های محتوا</CardTitle></CardHeader>
          <CardContent><Textarea rows={4} value={spec.instructions ?? ''} onChange={(e) => setSpec((s) => ({ ...s, instructions: e.target.value }))} placeholder='مثلاً: شماره تماس در پاراگراف اول، جدول مقایسه، اشاره به پوشش غرب تهران…' /></CardContent>
        </Card>
        <Card size='sm'>
          <CardHeader><CardTitle>ارائه‌دهنده و مدل</CardTitle><CardDescription>از لایه انتزاعی AI (Gateway → Router → Prompt Library → MemoryPack) استفاده می‌شود؛ هیچ ارائه‌دهنده‌ای مستقیم صدا زده نمی‌شود.</CardDescription></CardHeader>
          <CardContent className='grid gap-2 text-sm'>
            {optsError ? <ErrorState error={optsError} onRetry={loadOpts} /> : !opts ? <LoadingState rows={2} /> : (
              <>
                <div className='grid grid-cols-2 gap-2'>
                  <div className='grid gap-1'><Label>ارائه‌دهنده</Label>
                    <NativeSelect value={spec.provider ?? opts.default?.provider ?? 'echo'} onChange={(e) => { const p = opts.providers.find((x) => x.name === e.target.value); setSpec((s) => ({ ...s, provider: e.target.value, model: p?.default_model ?? p?.models[0]?.model_id ?? null })); }}>
                      {(['direct', 'gateway', 'offline'] as const).map((rk) => { const grp = opts.providers.filter((p) => routeKindOf(p) === rk); return grp.length ? <NativeSelectOptGroup key={rk} label={ROUTE_KIND_FA[rk]}>{grp.map((p) => <NativeSelectOption key={p.name} value={p.name} disabled={!p.configured}>{providerLabel(p)}{p.configured ? '' : ' — کلید ثبت نشده'}</NativeSelectOption>)}</NativeSelectOptGroup> : null; })}
                    </NativeSelect></div>
                  <div className='grid gap-1'><Label>مدل</Label>
                    <NativeSelect value={spec.model ?? ''} onChange={(e) => setSpec((s) => ({ ...s, model: e.target.value }))}>{(provider?.models ?? []).map((m) => <NativeSelectOption key={m.model_id} value={m.model_id}>{m.display}{m.display !== m.model_id ? ` (${m.model_id})` : ''} · {m.tier}{m.price_out_per_m ? ` · ${m.price_out_per_m}$/M` : ''}</NativeSelectOption>)}</NativeSelect></div>
                </div>
                {provider && provider.kind !== 'echo' && (
                  <div className='flex flex-wrap items-center gap-2 text-xs'>
                    <span className='text-muted-foreground'>وضعیت اتصال:</span>
                    <Badge variant={STATUS_FA[provider.status]?.tone === 'good' ? 'default' : STATUS_FA[provider.status]?.tone === 'bad' ? 'destructive' : 'outline'}>{STATUS_FA[provider.status]?.fa ?? provider.status}</Badge>
                    {provider.last_test?.tested_at && <span className='text-muted-foreground'>آخرین تست {String(provider.last_test.tested_at).slice(0, 16).replace('T', ' ')}</span>}
                    {typeof provider.health?.p50_ms === 'number' && <span className='text-muted-foreground'>· p50 {fa.format(provider.health.p50_ms)}ms</span>}
                    {provider.status === 'missing_credentials' && <Link className='underline' href='/dashboard/ai-models'>ثبت کلید در مدل‌های AI</Link>}
                  </div>
                )}
                {provider?.kind === 'echo' && opts.default?.kind !== 'echo' && <p className='text-muted-foreground text-xs'>Echo فقط برای تست آفلاین است و متن نمایشی می‌سازد؛ برای تولید واقعی «Claude» را انتخاب کنید.</p>}
                <div className='text-muted-foreground text-xs'>مسیر خودکار سیستم برای این وظیفه: <span dir='ltr'>{opts.auto_route.chain[0]?.provider}/{opts.auto_route.chain[0]?.model}</span> — {opts.auto_route.reason}. ارائه‌دهنده‌ها را در <Link className='underline' href='/dashboard/ai-models'>مدل‌های AI</Link> پیکربندی کنید.</div>
                <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
                  <StatChip label='ارائه‌دهنده' value={providerLabel(provider)} />
                  <StatChip label='مدل' value={<span dir='ltr' className='text-sm'>{modelDisplay(est?.model ?? spec.model)}</span>} />
                  <StatChip label='توکن تخمینی' value={est ? <span dir='ltr'>{fa.format(est.input_tokens)} + {fa.format(est.output_tokens)}</span> : '—'} hint={est?.exact ? 'ورودی دقیق (count_tokens) + خروجی تخمینی' : 'ورودی + خروجی (تخمینی)'} />
                  <StatChip label='هزینه تخمینی' value={est ? usd(est.cost_usd) : '—'} tone={est && est.cost_usd > 0.5 ? 'warn' : 'default'} />
                </div>
                {est && <div className='text-muted-foreground text-[11px]'>بودجه {est.budget.month}: {est.budget.spent_usd.toFixed(2)}$ از {est.budget.limit_usd}$ (<span className={budgetTone === 'good' ? 'text-emerald-600' : budgetTone === 'warn' ? 'text-amber-600' : 'text-red-600'}>{est.budget.state}</span>) · پرامپت {est.prompt_ref} · حافظه #{est.memory_snapshot_id} · حداکثر توکن خروجی {fa.format(est.max_tokens)}</div>}
                <Button size='lg' className='mt-1 w-full' onClick={generate} disabled={!ready || busy === 'gen' || est?.budget.state === 'hard_stop'}>{busy === 'gen' ? `در حال تولید با ${genLabel}...` : `تولید محتوا با ${genLabel}`}</Button>
                {!ready && <p className='text-muted-foreground text-xs'>عنوان و کلمه کلیدی اصلی لازم است.</p>}
                <div className='text-muted-foreground flex flex-wrap gap-1 text-[11px]'>مراحل آینده (فاز ۹): {opts.steps.map((s) => <Badge key={s.key} variant={s.implemented ? 'default' : 'outline'} className='text-[10px]'>{s.fa}</Badge>)}</div>
              </>
            )}
          </CardContent>
        </Card>
        {history.length > 0 && (
          <Card size='sm'><CardHeader><CardTitle>اجراهای اخیر</CardTitle></CardHeader>
            <CardContent className='text-xs'><ul className='space-y-1'>{history.slice(0, 8).map((h) => <li key={h.run_id + h.created_at} className='flex flex-wrap items-center gap-1'><Badge variant={h.ok ? 'outline' : 'destructive'} className='text-[10px]'>{h.ok ? 'موفق' : 'ناموفق'}</Badge><span dir='ltr'>{h.provider}/{h.model}</span><span className='text-muted-foreground'>· {fa.format(h.input_tokens ?? 0)}+{fa.format(h.output_tokens ?? 0)} توکن · {usd(h.cost_usd)} · {h.latency_ms}ms · {String(h.created_at).slice(5, 16).replace('T', ' ')}</span></li>)}</ul></CardContent></Card>
        )}
      </div>

      {/* ------------------------------------------------ right: output viewer */}
      <div className='min-w-0'>
        {busy === 'gen' && <Card size='sm'><CardContent><LoadingState label={`در حال تولید با ${genLabel}... (${modelDisplay(spec.model)})`} rows={6} /></CardContent></Card>}
        {!busy && !!error && <ErrorState error={error} title='تولید ناموفق بود' onRetry={generate} />}
        {!busy && !error && !res && <EmptyState icon='sparkles' title='هنوز محتوایی تولید نشده' description='مشخصات را پر کنید، ارائه‌دهنده را انتخاب کنید و «تولید محتوا» را بزنید. خروجی همین‌جا در ۵ نما (پیش‌نمایش، Markdown، تحلیل سئو، پرامپت، متادیتای AI) نمایش داده می‌شود.' />}
        {res && !busy && <OutputViewer res={res} items={items} saveTo={saveTo} setSaveTo={setSaveTo} onSave={saveDraft} saving={busy === 'save'} siteId={siteId} />}
      </div>
    </div>
  );
}

function OutputViewer({ res, items, saveTo, setSaveTo, onSave, saving, siteId }: { res: WsResult; items: ContentItem[]; saveTo: string; setSaveTo: (v: string) => void; onSave: () => void; saving: boolean; siteId: string }) {
  const r = res.result; const m = res.meta; const seo = res.seo;
  const total = seo.score?.total;
  return (
    <Card>
      <CardHeader>
        <CardTitle className='flex flex-wrap items-center gap-2'>{r.title}{m.placeholder && <Badge variant='secondary'>نمایشی — Echo</Badge>}<Badge variant='outline' dir='ltr'>{KIND_FA[m.provider_kind ?? ''] ?? m.provider}/{m.model}</Badge>{typeof total === 'number' && <Badge style={{ background: total >= 80 ? '#16a34a' : total >= 60 ? '#f59e0b' : '#dc2626' }}>امتیاز {fa.format(total)}</Badge>}</CardTitle>
        <CardDescription className='flex flex-wrap gap-x-3 gap-y-1'>
          <span>{fa.format(r.word_count)} کلمه</span><span>· {fa.format(seo.h2.length)} H2 · {fa.format(seo.h3_count)} H3</span><span>· {fa.format((r.faq ?? []).length)} پرسش</span><span>· {fa.format((r.internal_links ?? []).length)} لینک پیشنهادی</span>
          <span dir='ltr'>· {fa.format(m.input_tokens)}+{fa.format(m.output_tokens)} tokens</span><span>· {usd(m.cost_usd)}</span><span>· {fa.format(m.elapsed_ms)} ms</span>
        </CardDescription>
        <div className='flex flex-wrap items-center gap-2 pt-1 text-xs'>
          <NativeSelect value={saveTo} onChange={(e) => setSaveTo(e.target.value)} className='h-8 w-64'><NativeSelectOption value=''>ذخیره به‌عنوان پیش‌نویس در آیتم محتوا…</NativeSelectOption>{items.map((i) => <NativeSelectOption key={i.id} value={i.id}>{i.title} · {i.status_fa}</NativeSelectOption>)}</NativeSelect>
          <Button size='sm' variant='secondary' disabled={!saveTo || saving} onClick={onSave}>{saving ? '…' : 'ذخیره پیش‌نویس (اقدام انسانی)'}</Button>
          <Button size='sm' variant='ghost' onClick={() => { navigator.clipboard.writeText(r.markdown); toast.success('Markdown کپی شد'); }}>کپی Markdown</Button>
          <Link className='text-muted-foreground ms-auto underline' href={`/dashboard/content?site=${siteId}`}>مغز محتوا</Link>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue='preview'>
          <TabsList className='flex-wrap'><TabsTrigger value='preview'>پیش‌نمایش</TabsTrigger><TabsTrigger value='markdown'>Markdown</TabsTrigger><TabsTrigger value='seo'>تحلیل سئو</TabsTrigger><TabsTrigger value='prompt'>پرامپت استفاده‌شده</TabsTrigger><TabsTrigger value='meta'>متادیتای AI</TabsTrigger></TabsList>
          <TabsContent value='preview'>
            <article className='prose-sm max-w-3xl leading-7' dir='rtl'>
              <h1 className='mb-1 text-2xl font-bold'>{r.h1 ?? r.title}</h1>
              {r.meta_description && <p className='text-muted-foreground mb-4 rounded border-s-2 ps-3 text-sm'>{r.meta_description}</p>}
              {r.sections.map((s, i) => (
                <section key={i} className='mb-4'>
                  <h2 className='mt-4 mb-2 text-lg font-semibold'>{s.h2}</h2>
                  {(s.paragraphs ?? []).map((p, j) => <p key={j} className='mb-2 text-[15px]'>{p}</p>)}
                  {(s.h3 ?? []).map((h, j) => typeof h === 'string' ? <h3 key={j} className='mt-2 mb-1 text-base font-medium'>{h}</h3> : <div key={j}><h3 className='mt-2 mb-1 text-base font-medium'>{h.text ?? h.h3}</h3>{(h.paragraphs ?? []).map((p: string, k: number) => <p key={k} className='mb-2 text-[15px]'>{p}</p>)}</div>)}
                </section>
              ))}
              {(r.faq ?? []).length > 0 && <section className='mb-4'><h2 className='mt-4 mb-2 text-lg font-semibold'>سؤالات متداول</h2>{r.faq!.map((q, i) => <details key={i} className='mb-1 rounded border p-2'><summary className='cursor-pointer font-medium'>{q.question}</summary><p className='mt-1 text-[15px]'>{q.answer}</p></details>)}</section>}
              {(r.internal_links ?? []).length > 0 && <section className='rounded-md border p-3 text-sm'><div className='mb-1 font-medium'>لینک‌های داخلی پیشنهادی</div><ul className='list-disc ps-5'>{r.internal_links!.map((l, i) => <li key={i}><b>{l.anchor}</b> → {l.target_topic ?? l.target}</li>)}</ul></section>}
              {(r.keywords_used ?? []).length > 0 && <div className='mt-3 flex flex-wrap gap-1 text-xs'><span className='text-muted-foreground'>کلمات استفاده‌شده:</span>{r.keywords_used!.map((k) => <Badge key={k} variant='outline'>{k}</Badge>)}</div>}
            </article>
          </TabsContent>
          <TabsContent value='markdown'><pre className='bg-muted max-h-[70vh] overflow-auto rounded-md p-3 text-xs whitespace-pre-wrap' dir='auto'>{r.markdown}</pre></TabsContent>
          <TabsContent value='seo'>
            <div className='grid gap-3 md:grid-cols-2'>
              <div className='rounded-md border p-3'>
                <div className='mb-2 flex items-center justify-between text-sm font-medium'><span>چک‌لیست سئو</span><Badge variant='outline'>{fa.format(seo.passed)} / {fa.format(seo.total_checks)}</Badge></div>
                <ul className='space-y-1 text-sm'>{seo.checks.map((c) => <li key={c.key} className='flex items-center gap-2'><span className={`inline-block h-2.5 w-2.5 rounded-full ${c.ok ? 'bg-emerald-500' : 'bg-red-500'}`} />{c.fa}{c.value != null && <span className='text-muted-foreground text-xs' dir='ltr'>({c.value})</span>}</li>)}</ul>
                <div className='text-muted-foreground mt-2 text-xs'>چگالی کلمه کلیدی: {seo.keyword_density}٪ · کلمات ثانویه: {seo.secondary_keywords.map((s) => <Badge key={s.keyword} variant={s.used ? 'default' : 'outline'} className='me-1 text-[10px]'>{s.keyword}</Badge>)}{seo.forbidden_claims_found.length > 0 && <div className='text-destructive mt-1'>ادعاهای ممنوع یافت‌شده: {seo.forbidden_claims_found.join('، ')}</div>}</div>
              </div>
              <div className='rounded-md border p-3'>
                <div className='mb-2 text-sm font-medium'>امتیاز موتور امتیازدهی (score-v1){typeof total === 'number' && <span className='ms-2 text-lg tabular-nums'>{fa.format(total)} / ۱۰۰</span>}</div>
                {seo.score?.dims ? <div className='grid gap-1'>{Object.entries(seo.score.dims).map(([k, v]) => <div key={k} className='flex items-center gap-2 text-xs'><span className='w-32 shrink-0'>{DIM_FA[k] ?? k}</span><div className='bg-muted h-2 flex-1 overflow-hidden rounded'><div className='h-2 rounded' style={{ width: `${v}%`, background: v >= 80 ? '#16a34a' : v >= 50 ? '#f59e0b' : '#dc2626' }} /></div><span className='w-8 text-end tabular-nums'>{fa.format(v)}</span></div>)}</div> : <p className='text-muted-foreground text-xs'>امتیاز محاسبه نشد.</p>}
                {(seo.score?.failed ?? []).length > 0 && <details className='mt-2 text-xs'><summary className='cursor-pointer'>قواعد ردشده ({seo.score!.failed!.length})</summary><ul className='mt-1 list-disc ps-4'>{seo.score!.failed!.slice(0, 12).map((x: any, i: number) => <li key={i}>{x.evidence ?? x.rule} — <span className='text-emerald-600'>{x.fix_fa}</span></li>)}</ul></details>}
                <div className='text-muted-foreground mt-2 text-xs'>سرفصل‌ها: {seo.h2.join(' · ')}</div>
              </div>
            </div>
          </TabsContent>
          <TabsContent value='prompt'>
            <div className='grid gap-2 text-xs'>
              <div className='text-muted-foreground'>پرامپت {res.prompt.ref} (نسخه #{res.prompt.prompt_version_id ?? '—'}) · Memory Snapshot #{res.prompt.memory_snapshot_id} · ویرایش نسخه‌ها در «مدل‌های AI › پرامپت‌ها»</div>
              <details open className='rounded-md border p-2'><summary className='cursor-pointer font-medium'>پیام کاربر (با حافظه سایت تزریق‌شده)</summary><pre className='bg-muted mt-1 max-h-[50vh] overflow-auto rounded p-2 whitespace-pre-wrap' dir='auto'>{res.prompt.user}</pre></details>
              <details className='rounded-md border p-2'><summary className='cursor-pointer font-medium'>پیام سیستم</summary><pre className='bg-muted mt-1 max-h-60 overflow-auto rounded p-2 whitespace-pre-wrap' dir='auto'>{res.prompt.system}</pre></details>
              <details className='rounded-md border p-2'><summary className='cursor-pointer font-medium'>اسکیمای JSON خروجی</summary><pre className='bg-muted mt-1 overflow-auto rounded p-2' dir='ltr'>{JSON.stringify(res.prompt.schema, null, 1)}</pre></details>
            </div>
          </TabsContent>
          <TabsContent value='meta'>
            <div className='grid grid-cols-2 gap-2 text-xs sm:grid-cols-4'>
              <StatChip label='ارائه‌دهنده' value={<span dir='ltr'>{m.provider_kind ?? m.provider}</span>} hint={m.provider !== (m.provider_kind ?? m.provider) ? m.provider : undefined} /><StatChip label='مدل' value={<span dir='ltr' className='text-sm'>{m.model}</span>} /><StatChip label='توکن ورودی' value={fa.format(m.input_tokens)} /><StatChip label='توکن خروجی' value={fa.format(m.output_tokens)} />
              <StatChip label='هزینه' value={usd(m.cost_usd)} /><StatChip label='تأخیر ارائه‌دهنده' value={`${fa.format(m.latency_ms)} ms`} /><StatChip label='زمان کل تولید' value={`${fa.format(m.elapsed_ms)} ms`} /><StatChip label='حالت' value={m.placeholder ? 'نمایشی (Echo)' : m.streamed ? 'واقعی (استریم)' : 'واقعی'} tone={m.placeholder ? 'warn' : 'good'} />
              {m.gateway_decision && <StatChip label='تصمیم گیت‌وی' value={<span dir='ltr' className='text-[11px]'>{m.gateway_decision.decision ?? JSON.stringify(m.gateway_decision)}</span>} hint={m.served_model ? `served: ${m.served_model}` : undefined} />}
              <StatChip label='run_id' value={<span dir='ltr' className='text-xs'>{m.run_id}</span>} /><StatChip label='نسخه پرامپت' value={<span dir='ltr' className='text-xs'>{m.prompt_version ?? res.prompt.ref}</span>} /><StatChip label='Memory Snapshot' value={`#${m.memory_snapshot_id ?? res.prompt.memory_snapshot_id}`} /><StatChip label='stop_reason' value={<span dir='ltr' className='text-xs'>{m.stop_reason ?? '—'}</span>} />
            </div>
            <div className='text-muted-foreground mt-2 text-xs'>run {m.run_id} · وظیفه {m.task_kind} · سیاست مسیردهی: {m.policy} — {m.route_reason} · بودجه {m.budget.month}: {m.budget.spent_usd.toFixed(3)}$ از {m.budget.limit_usd}$ ({m.budget.state})</div>
            <div className='mt-2 rounded-md border p-2 text-xs'><div className='font-medium'>زنجیره مسیر و تلاش‌ها</div><ul className='mt-1 list-disc ps-4'>{m.route.map((s: any, i: number) => <li key={i} dir='ltr'>{s.provider}/{s.model} — <span dir='rtl'>{s.reason}</span></li>)}</ul>{m.attempts.length > 0 && <ul className='mt-1 list-disc ps-4'>{m.attempts.map((a: any, i: number) => <li key={i} dir='ltr'>{a.provider}/{a.model} · {a.ok ? 'ok' : `error: ${a.error}`} · {a.latency_ms}ms</li>)}</ul>}</div>
            {m.raw_excerpt && <details className='mt-2 text-xs'><summary className='cursor-pointer'>خروجی خام (۴۰۰ نویسه)</summary><pre className='bg-muted mt-1 rounded p-2 whitespace-pre-wrap' dir='auto'>{m.raw_excerpt}</pre></details>}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
