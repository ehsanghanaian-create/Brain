'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ApiError, endpoints, type AiModel, type Budget, type ContentItem, type GenEstimate, type GenerationRun, type Site } from '@/lib/api/client';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

const fa = new Intl.NumberFormat('fa-IR');
const AGENT_FA: Record<string, string> = { research: 'تحقیق', outline: 'ساختار', writer: 'نگارش (هر بخش)', fact_check: 'راستی‌آزمایی', seo: 'سئو', linking: 'لینک‌سازی', reviewer: 'بازبینی' };
const AGENTS = ['research', 'outline', 'writer', 'fact_check', 'seo', 'linking', 'reviewer'];
const STEP_FA: Record<string, string> = { research: 'تحقیق', outline: 'ساختار', assembly: 'مونتاژ', seo: 'سئو', linking: 'لینک‌سازی', review: 'بازبینی AI', draft: 'ثبت پیش‌نویس + امتیاز' };
const BUDGET_FA: Record<string, string> = { ok: 'عادی', warning: 'هشدار ۸۰٪', soft_limit: 'حد نرم ۱۰۰٪', hard_stop: 'توقف سخت ۱۲۰٪' };
const budgetColor = (s: string) => (s === 'ok' ? '#16a34a' : s === 'warning' ? '#f59e0b' : '#dc2626');
const usd = (v: number | undefined | null) => (typeof v === 'number' ? `${v.toFixed(4)}$` : '—');

export function AiStudio({ sites, initialSiteId, initialContentId }: { sites: Site[]; initialSiteId: string; initialContentId?: number }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [site, setSite] = useState<Site | undefined>(sites.find((s) => s.site_id === initialSiteId));
  const [items, setItems] = useState<ContentItem[]>([]);
  const [cid, setCid] = useState<number | null>(initialContentId ?? null);
  const [mode, setMode] = useState<'manual' | 'assisted'>('assisted');
  const [models, setModels] = useState<AiModel[]>([]);
  const [overrides, setOverrides] = useState<Record<string, { provider: string; model: string } | undefined>>({});
  const [routing, setRouting] = useState<Record<string, { provider: string; model: string; reason: string; policy: string }>>({});
  const [memory, setMemory] = useState<{ id: number; hash: string; rendered: string } | null>(null);
  const [est, setEst] = useState<GenEstimate | null>(null);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [runs, setRuns] = useState<GenerationRun[]>([]);
  const [run, setRun] = useState<GenerationRun | null>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [compare, setCompare] = useState<[GenerationRun | null, GenerationRun | null]>([null, null]);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => { setSite(sites.find((s) => s.site_id === siteId)); setMode(sites.find((s) => s.site_id === siteId)?.mode === 'manual' ? 'manual' : 'assisted'); }, [siteId, sites]);
  const load = useCallback(async () => {
    try {
      const [c, m, mem, b, r] = await Promise.all([endpoints.contentList(siteId, { limit: 200 }), endpoints.aiModels(), endpoints.genMemoryPreview(siteId), endpoints.aiBudget(siteId), endpoints.genRuns(siteId)]);
      setItems(c.items); setModels(m.filter((x) => x.enabled)); setMemory(mem); setBudget(b); setRuns(r);
      if (!cid && c.items.length) setCid(initialContentId ?? c.items[0].id);
    } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
  }, [siteId, cid, initialContentId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    // routing preview per agent (why this model)
    const kinds: Record<string, string> = { research: 'research', outline: 'outline', writer: 'article_section', fact_check: 'fact_check', seo: 'seo_review', linking: 'internal_linking', reviewer: 'seo_review' };
    Promise.all(AGENTS.map(async (a) => { const o = overrides[a]; const d = await endpoints.aiRoutingPreview({ task_kind: kinds[a], site_id: siteId, provider: o?.provider, model: o?.model }); return [a, { ...d.chain[0], reason: d.reason, policy: d.policy }] as const; }))
      .then((rs) => setRouting(Object.fromEntries(rs))).catch(() => null);
  }, [siteId, overrides, models]);
  useEffect(() => {
    if (!cid) return;
    const body = Object.keys(overrides).length ? { models: Object.fromEntries(Object.entries(overrides).filter(([, v]) => v)) } : {};
    endpoints.genEstimate(siteId, cid, body).then(setEst).catch(() => setEst(null));
  }, [siteId, cid, overrides]);

  function attachStream(runId: string) {
    esRef.current?.close(); setEvents([]);
    const es = new EventSource(`/api/backend/sites/${encodeURIComponent(siteId)}/generation/runs/${runId}/stream`);
    esRef.current = es;
    const push = (e: MessageEvent) => { try { const d = JSON.parse(e.data); setEvents((ev) => [...ev, d]); } catch { /* ignore */ } };
    ['start', 'plan', 'step_start', 'step_done', 'done', 'failed', 'cancelled', 'keepalive', 'message'].forEach((t) => es.addEventListener(t, push as any));
    const finish = async () => { es.close(); const r = await endpoints.genRun(siteId, runId); setRun(r); load(); };
    es.addEventListener('done', finish as any); es.addEventListener('failed', finish as any); es.addEventListener('cancelled', finish as any);
    es.onerror = () => { es.close(); endpoints.genRun(siteId, runId).then((r) => setRun(r)).catch(() => null); };
  }
  useEffect(() => () => esRef.current?.close(), []);

  async function start() {
    if (!cid) return;
    setBusy('start');
    try {
      const body: Record<string, unknown> = { mode };
      const ov = Object.fromEntries(Object.entries(overrides).filter(([, v]) => v)); if (Object.keys(ov).length) body.models = ov;
      const r = await endpoints.genStart(siteId, cid, body);
      setRun(r); toast.success(`تولید شروع شد (${r.run_id}) — حالت ${mode === 'manual' ? 'دستی: فقط پیشنهاد' : 'نیمه‌خودکار: پیش‌نویس ساخته می‌شود'}`); attachStream(r.run_id);
    } catch (e) { toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)); } finally { setBusy(null); }
  }
  async function accept(r: GenerationRun) {
    try { const a = await endpoints.genAccept(siteId, r.run_id); toast.success(`پیش‌نویس v${a.version ?? ''} ساخته شد — امتیاز ${a.score ?? '—'} · ${a.review_status ?? ''}`); setRun(await endpoints.genRun(siteId, r.run_id)); load(); }
    catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
  }
  const item = items.find((i) => i.id === cid);
  const providerModels = (p: string) => models.filter((m) => m.provider === p);
  const providers = [...new Set(models.map((m) => m.provider).filter(Boolean))] as string[];

  return (
    <div className='grid gap-4 lg:grid-cols-[320px_1fr]'>
      <div className='flex flex-col gap-3'>
        <Card><CardHeader><CardTitle className='text-base'>ورودی</CardTitle></CardHeader>
          <CardContent className='grid gap-2 text-sm'>
            <div className='grid gap-1'><Label>سایت</Label><NativeSelect value={siteId} onChange={(e) => { setSiteId(e.target.value); setCid(null); }}>{sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>)}</NativeSelect></div>
            <div className='grid gap-1'><Label>محتوا (کلمه کلیدی هدف · وضعیت)</Label><NativeSelect value={cid ?? ''} onChange={(e) => setCid(Number(e.target.value))}>{items.map((i) => <NativeSelectOption key={i.id} value={i.id}>{i.title} · {i.target_keyword ?? '—'} · {i.status_fa}{i.has_brief ? ' · بریف✓' : ' · بدون بریف'}</NativeSelectOption>)}</NativeSelect>
              {item && !item.has_brief && <span className='text-destructive text-xs'>این محتوا بریف ندارد — ابتدا در مغز محتوا بریف بسازید (ساختار از بریف گرفته می‌شود).</span>}</div>
            <div className='grid gap-1'><Label>حالت کنترل انسانی</Label>
              <NativeSelect value={mode} onChange={(e) => setMode(e.target.value as 'manual' | 'assisted')}><NativeSelectOption value='manual'>دستی — AI فقط پیشنهاد می‌دهد (پیش‌نویس با کلیک شما)</NativeSelectOption><NativeSelectOption value='assisted'>نیمه‌خودکار — پیش‌نویس ساخته و امتیاز/بازبینی می‌شود</NativeSelectOption></NativeSelect>
              <span className='text-muted-foreground text-[11px]'>خودکار (autopilot): رزروشده — غیرفعال. هیچ انتشاری انجام نمی‌شود.</span></div>
          </CardContent></Card>
        <Card><CardHeader><CardTitle className='text-base'>ارائه‌دهنده و مدل هر عامل</CardTitle><CardDescription>پیش‌فرض: مسیردهی خودکار (با دلیل). تغییر مسیر دائمی فقط از «مدل‌های AI».</CardDescription></CardHeader>
          <CardContent className='grid gap-2 text-xs'>
            {AGENTS.map((a) => { const r = routing[a]; const o = overrides[a]; return (
              <div key={a} className='rounded border p-2'>
                <div className='flex items-center justify-between'><span className='font-medium'>{AGENT_FA[a]}</span>{r && <Badge variant='outline'>{r.policy === 'echo' ? 'Echo (بدون ارائه‌دهنده)' : `${r.provider} / ${r.model}`}</Badge>}</div>
                {r?.reason && <div className='text-muted-foreground mt-0.5'>{r.reason}</div>}
                <div className='mt-1 flex gap-1'>
                  <NativeSelect value={o?.provider ?? ''} onChange={(e) => { const p = e.target.value; setOverrides((s) => ({ ...s, [a]: p ? { provider: p, model: providerModels(p)[0]?.model_id ?? '' } : undefined })); }} className='h-7 text-xs'><NativeSelectOption value=''>خودکار</NativeSelectOption>{providers.map((p) => <NativeSelectOption key={p} value={p}>{p}</NativeSelectOption>)}</NativeSelect>
                  {o && <NativeSelect value={o.model} onChange={(e) => setOverrides((s) => ({ ...s, [a]: { provider: o.provider, model: e.target.value } }))} className='h-7 text-xs'>{providerModels(o.provider).map((m) => <NativeSelectOption key={m.id} value={m.model_id}>{m.model_id} · {m.tier} · {m.price_out_per_m}$/M</NativeSelectOption>)}</NativeSelect>}
                </div>
              </div>); })}
            {providers.length === 0 && <p className='text-muted-foreground'>هیچ ارائه‌دهنده‌ای با کلید ثبت نشده — خروجی نمایشی (Echo) خواهد بود. <Link href='/dashboard/ai-models' className='underline'>مدل‌های AI</Link></p>}
          </CardContent></Card>
        <Card><CardHeader><CardTitle className='text-base'>برآورد و بودجه</CardTitle></CardHeader>
          <CardContent className='text-sm'>
            {budget && <div className='mb-2 flex items-center gap-2 text-xs'><span className='inline-block h-2.5 w-2.5 rounded-full' style={{ background: budgetColor(budget.state) }} />بودجه {budget.month}: {budget.spent_usd.toFixed(2)}$ از {budget.limit_usd}$ ({Math.round(budget.ratio * 100)}٪) — {BUDGET_FA[budget.state]}</div>}
            {est ? (<>
              <div className='flex justify-between font-medium'><span>کل ({est.sections} بخش)</span><span dir='ltr'>{fa.format(est.total.input_tokens)} in · {fa.format(est.total.output_tokens)} out · {usd(est.total.cost_usd)}</span></div>
              <ul className='text-muted-foreground mt-1 space-y-0.5 text-xs'>{Object.entries(est.per_agent).map(([a, v]) => <li key={a} className='flex justify-between'><span>{AGENT_FA[a] ?? a}{v.sections ? ` ×${v.sections}` : ''}</span><span dir='ltr'>{v.route?.[0]?.model ?? '—'} · {usd(v.cost_usd)}</span></li>)}</ul>
              <div className='text-muted-foreground mt-1 text-[11px]'>Memory Snapshot #{est.memory_snapshot_id}</div>
            </>) : <p className='text-muted-foreground text-xs'>محتوا انتخاب کنید.</p>}
            <Button className='mt-3 w-full' onClick={start} disabled={!cid || !!busy || budget?.state === 'hard_stop'}>{busy === 'start' ? '…' : mode === 'manual' ? 'اجرای عامل‌ها (پیشنهاد)' : 'تولید پیش‌نویس با AI'}</Button>
            {budget?.state === 'hard_stop' && <p className='text-destructive mt-1 text-xs'>بودجه ماهانه به حد سخت رسیده — در تنظیمات افزایش دهید.</p>}
          </CardContent></Card>
      </div>

      <div className='flex flex-col gap-3'>
        <Tabs defaultValue='progress'>
          <TabsList><TabsTrigger value='progress'>پیشرفت تولید</TabsTrigger><TabsTrigger value='prompt'>پیش‌نمایش پرامپت و حافظه</TabsTrigger><TabsTrigger value='compare'>مقایسه خروجی‌ها</TabsTrigger><TabsTrigger value='runs'>اجراهای قبلی ({runs.length})</TabsTrigger></TabsList>
          <TabsContent value='progress'>
            {!run ? <p className='text-muted-foreground text-sm'>هنوز اجرایی شروع نشده.</p> : (
              <Card><CardHeader><CardTitle className='flex flex-wrap items-center gap-2 text-base'>اجرا {run.run_id} <Badge variant={run.status === 'succeeded' ? 'default' : run.status === 'failed' ? 'destructive' : 'secondary'}>{run.status}</Badge><Badge variant='outline'>{run.mode === 'manual' ? 'دستی' : 'نیمه‌خودکار'}</Badge>{run.draft_id && <Badge>پیش‌نویس #{run.draft_id} · امتیاز {run.score}</Badge>}</CardTitle>
                <CardDescription>Memory Snapshot #{run.memory_snapshot_id} · مدل‌ها: {Object.entries(run.models).map(([a, m]) => `${AGENT_FA[a] ?? a}=${m.model}`).join('، ') || 'خودکار'} · هزینه واقعی {usd(run.actual?.cost_usd)}</CardDescription></CardHeader>
                <CardContent>
                  <ol className='space-y-1 text-sm'>
                    {(run.steps.length ? run.steps : events.filter((e) => e.type === 'step_start').map((e) => ({ key: e.step, agent: e.agent, status: 'running' }))).map((s: any, i: number) => {
                      const ev = events.filter((e) => e.step === s.key); const done = ev.find((e) => e.type === 'step_done');
                      return <li key={i} className='flex flex-wrap items-center gap-2 rounded border p-1.5'><span className='inline-block h-2.5 w-2.5 rounded-full' style={{ background: s.status === 'succeeded' ? '#16a34a' : s.status === 'failed' ? '#dc2626' : '#f59e0b' }} /><span className='font-medium'>{s.key.startsWith('section:') ? `بخش ${s.key.split(':')[1]}` : STEP_FA[s.key] ?? s.key}</span><span className='text-muted-foreground text-xs'>{AGENT_FA[s.agent] ?? s.agent}{s.provenance?.model ? ` · ${s.provenance.model}` : ''}{s.words ? ` · ${s.words} کلمه` : ''}{s.validation_ok === false ? ' · اعتبارسنجی: نیاز به اصلاح' : ''}{s.fact_check ? ` · راستی‌آزمایی: ${s.fact_check}` : ''}{done?.cost_usd != null ? ` · ${usd(done.cost_usd)}` : ''}{s.error ? ` · ${s.error}` : ''}</span></li>;
                    })}
                  </ol>
                  {run.status === 'running' && <p className='text-muted-foreground mt-2 text-xs'>در حال اجرا… (SSE زنده) — <button className='underline' onClick={async () => { await endpoints.genCancel(siteId, run.run_id); toast.info('لغو شد'); }}>لغو</button></p>}
                  {run.status === 'succeeded' && (
                    <div className='mt-3 flex flex-wrap gap-2'>
                      {run.mode === 'manual' && !run.draft_id && <Button onClick={() => accept(run)}>ساخت پیش‌نویس از این خروجی (تأیید انسانی)</Button>}
                      {run.draft_id && <Button variant='secondary' render={<Link href={`/dashboard/content?site=${siteId}`} />}>باز کردن در مغز محتوا (امتیاز/بازبینی/تأیید)</Button>}
                      <Button variant='outline' onClick={() => setCompare(([a, b]) => (a ? [a, run] : [run, b]))}>افزودن به مقایسه</Button>
                    </div>
                  )}
                  {run.artifacts && (
                    <details className='mt-3'><summary className='cursor-pointer text-xs'>خروجی عامل‌ها ({run.artifacts.length})</summary>
                      {run.artifacts.map((a) => <details key={a.id} className='mt-1 rounded border p-2 text-xs'><summary className='cursor-pointer'>{a.step} · {AGENT_FA[a.agent] ?? a.agent}{a.provenance?.model ? ` · ${a.provenance.model}` : ''}{a.provenance?.placeholder ? ' · نمایشی' : ''}</summary><pre className='bg-muted mt-1 max-h-64 overflow-auto rounded p-2 whitespace-pre-wrap' dir='auto'>{a.step === 'assembly' ? a.payload.markdown : JSON.stringify(a.payload, null, 1)}</pre></details>)}
                    </details>
                  )}
                </CardContent></Card>
            )}
          </TabsContent>
          <TabsContent value='prompt'>
            <Card><CardHeader><CardTitle className='text-base'>حافظه سایت تزریق‌شده (Memory Snapshot #{memory?.id})</CardTitle><CardDescription>این متن دقیقاً در هر پرامپت عامل‌ها قرار می‌گیرد — «بدون نوشتار عمومی». ویرایش از «سایت‌ها › مغز سایت». نسخه‌های پرامپت از «مدل‌های AI › پرامپت‌ها».</CardDescription></CardHeader>
              <CardContent><pre className='bg-muted max-h-[60vh] overflow-auto rounded p-3 text-xs whitespace-pre-wrap' dir='auto'>{memory?.rendered}</pre></CardContent></Card>
          </TabsContent>
          <TabsContent value='compare'>
            <div className='grid gap-3 md:grid-cols-2'>
              {[0, 1].map((i) => { const r = compare[i]; return (
                <Card key={i}><CardHeader><CardTitle className='text-base'>{r ? `${r.run_id} · ${Object.values(r.models).map((m) => m.model).filter((v, j, arr) => arr.indexOf(v) === j).join('/') || 'echo'}` : `خروجی ${i + 1}`}</CardTitle>
                  {r && <CardDescription>امتیاز {r.score ?? '—'} · {r.review_status ?? '—'} · هزینه {usd(r.actual?.cost_usd)} · {fa.format((r.actual?.input_tokens ?? 0) + (r.actual?.output_tokens ?? 0))} توکن</CardDescription>}</CardHeader>
                  <CardContent>{r ? <pre className='bg-muted max-h-[50vh] overflow-auto rounded p-2 text-xs whitespace-pre-wrap' dir='auto'>{r.artifacts?.find((a) => a.step === 'assembly')?.payload.markdown ?? '—'}</pre> : <NativeSelect value='' onChange={async (e) => { if (!e.target.value) return; const full = await endpoints.genRun(siteId, e.target.value); setCompare((c) => (i === 0 ? [full, c[1]] : [c[0], full])); }}><NativeSelectOption value=''>انتخاب اجرا…</NativeSelectOption>{runs.filter((x) => x.status === 'succeeded').map((x) => <NativeSelectOption key={x.run_id} value={x.run_id}>{x.run_id} · امتیاز {x.score ?? '—'}</NativeSelectOption>)}</NativeSelect>}
                    {r && r.mode === 'manual' && !r.draft_id && <Button className='mt-2' size='sm' onClick={() => accept(r)}>برگزیدن → ساخت پیش‌نویس</Button>}</CardContent></Card>); })}
            </div>
          </TabsContent>
          <TabsContent value='runs'>
            <div className='grid gap-1 text-sm'>
              {runs.map((r) => <button key={r.run_id} className='hover:bg-accent flex flex-wrap items-center gap-2 rounded border p-2 text-start' onClick={async () => { setRun(await endpoints.genRun(siteId, r.run_id)); }}><Badge variant={r.status === 'succeeded' ? 'default' : r.status === 'failed' ? 'destructive' : 'secondary'}>{r.status}</Badge><span className='font-mono text-xs' dir='ltr'>{r.run_id}</span><span>{items.find((i) => i.id === r.content_id)?.title ?? `#${r.content_id}`}</span><span className='text-muted-foreground text-xs'>{r.mode === 'manual' ? 'دستی' : 'نیمه‌خودکار'} · {usd(r.actual?.cost_usd)} · {r.score != null ? `امتیاز ${r.score}` : ''} · {r.created_at.slice(0, 16).replace('T', ' ')}</span></button>)}
              {runs.length === 0 && <p className='text-muted-foreground'>اجرایی ثبت نشده.</p>}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
