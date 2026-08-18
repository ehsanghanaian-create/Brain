'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import { ApiError, endpoints, type AiInsight, type AiModel, type Prompt, type PromptVersion, type Site, type Usage } from '@/lib/api/client';
import { TASK_FA } from '@/features/content/constants';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

const fa = new Intl.NumberFormat('fa-IR');
const TIER_FA: Record<string, string> = { fast: 'سریع/ارزان', balanced: 'متعادل', quality: 'کیفیت', reasoning: 'استدلال' };
const BUDGET_FA: Record<string, string> = { ok: 'عادی', warning: 'هشدار ۸۰٪', soft_limit: 'حد نرم ۱۰۰٪', hard_stop: 'توقف سخت ۱۲۰٪' };
const err = (e: unknown) => toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));

// ---------------------------------------------------------------- model catalog + health
export function ModelCatalog() {
  const [models, setModels] = useState<AiModel[]>([]);
  const [health, setHealth] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => { try { const [m, h] = await Promise.all([endpoints.aiModels(), endpoints.aiHealth()]); setModels(m); setHealth(h.providers); } catch (e) { err(e); } }, []);
  useEffect(() => { load(); }, [load]);
  async function sync() { setBusy(true); try { const r = await endpoints.aiModelsSync(); toast.success(`همگام‌سازی کاتالوگ: ${JSON.stringify(r.added ?? r)}`); load(); } catch (e) { err(e); } finally { setBusy(false); } }
  async function patch(m: AiModel, body: Record<string, unknown>) { try { await endpoints.aiModelUpdate(m.id, body); load(); } catch (e) { err(e); } }
  return (
    <Card>
      <CardHeader><CardTitle className='flex items-center justify-between'>کاتالوگ مدل‌ها و سلامت ارائه‌دهنده‌ها <Button size='sm' variant='secondary' onClick={sync} disabled={busy}>{busy ? '…' : 'همگام‌سازی کاتالوگ'}</Button></CardTitle>
        <CardDescription>مدل‌های هر ارائه‌دهنده با سطح (tier)، برچسب‌ها و قیمت به ازای هر میلیون توکن. مسیریاب خودکار از این جدول برای انتخاب مدل استفاده می‌کند. مدار قطع (circuit breaker): ۳ خطای پیاپی → ۵ دقیقه توقف.</CardDescription></CardHeader>
      <CardContent className='grid gap-3'>
        <div className='flex flex-wrap gap-2 text-xs'>
          {health.map((h) => { const open = h.breaker_open_until && h.breaker_open_until > new Date().toISOString(); return <Badge key={h.provider} variant={open ? 'destructive' : h.consecutive_failures ? 'secondary' : 'outline'}>{h.provider} · {open ? `مدار قطع تا ${String(h.breaker_open_until).slice(11, 19)}` : 'سالم'} · {h.calls} فراخوانی · {h.failures} خطا · پیاپی {h.consecutive_failures}{h.p50_ms ? ` · p50 ${h.p50_ms}ms` : ''}{h.last_error ? ` · ${String(h.last_error).slice(0, 40)}` : ''}</Badge>; })}
          {health.length === 0 && <span className='text-muted-foreground'>ارائه‌دهنده‌ای ثبت نشده.</span>}
        </div>
        <div className='overflow-x-auto rounded-md border'>
          <Table>
            <TableHeader><TableRow><TableHead>ارائه‌دهنده</TableHead><TableHead>مدل</TableHead><TableHead>سطح</TableHead><TableHead>برچسب‌ها</TableHead><TableHead>ورودی $/M</TableHead><TableHead>خروجی $/M</TableHead><TableHead>Context</TableHead><TableHead>فعال</TableHead></TableRow></TableHeader>
            <TableBody>
              {models.map((m) => (
                <TableRow key={m.id}>
                  <TableCell>{m.provider}</TableCell><TableCell dir='ltr' className='font-mono text-xs'>{m.model_id}</TableCell>
                  <TableCell><NativeSelect value={m.tier} onChange={(e) => patch(m, { tier: e.target.value })} className='h-7 text-xs'>{Object.entries(TIER_FA).map(([k, v]) => <NativeSelectOption key={k} value={k}>{v}</NativeSelectOption>)}</NativeSelect></TableCell>
                  <TableCell className='text-xs'>{m.tags.join('، ') || '—'}</TableCell>
                  <TableCell><Input type='number' step='0.01' defaultValue={m.price_in_per_m} onBlur={(e) => Number(e.target.value) !== m.price_in_per_m && patch(m, { price_in_per_m: Number(e.target.value) })} dir='ltr' className='h-7 w-20 text-xs' /></TableCell>
                  <TableCell><Input type='number' step='0.01' defaultValue={m.price_out_per_m} onBlur={(e) => Number(e.target.value) !== m.price_out_per_m && patch(m, { price_out_per_m: Number(e.target.value) })} dir='ltr' className='h-7 w-20 text-xs' /></TableCell>
                  <TableCell dir='ltr' className='text-xs'>{m.context_tokens ? fa.format(m.context_tokens) : '—'}</TableCell>
                  <TableCell><input type='checkbox' checked={m.enabled} onChange={(e) => patch(m, { enabled: e.target.checked })} /></TableCell>
                </TableRow>
              ))}
              {models.length === 0 && <TableRow><TableCell colSpan={8} className='text-muted-foreground text-center'>کاتالوگ خالی است — با افزودن ارائه‌دهنده به‌طور خودکار پر می‌شود.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------- usage + budget
export function UsagePanel({ sites }: { sites: Site[] }) {
  const [siteId, setSiteId] = useState(sites[0]?.site_id ?? '');
  const [groupBy, setGroupBy] = useState('model');
  const [u, setU] = useState<Usage | null>(null);
  const [limit, setLimit] = useState('');
  useEffect(() => { if (!siteId) return; endpoints.aiUsage({ site_id: siteId, group_by: groupBy }).then((r) => { setU(r); setLimit(String(r.budget.limit_usd)); }).catch(err); }, [siteId, groupBy]);
  async function saveBudget() {
    try { await endpoints.aiBudgetSet(siteId, Number(limit)); toast.success('بودجه ماهانه ذخیره شد'); setU(await endpoints.aiUsage({ site_id: siteId, group_by: groupBy })); } catch (e) { err(e); }
  }
  const b = u?.budget;
  return (
    <Card>
      <CardHeader><CardTitle>مصرف و بودجه</CardTitle><CardDescription>دفتر کل تمام فراخوانی‌ها (توکن، هزینه، تأخیر). بودجه پیش‌فرض ۲۰ دلار/سایت/ماه — هشدار ۸۰٪، حد نرم ۱۰۰٪ (ادامه با هشدار)، توقف سخت ۱۲۰٪ (اجرا مسدود می‌شود).</CardDescription></CardHeader>
      <CardContent className='grid gap-3 text-sm'>
        <div className='flex flex-wrap items-end gap-2'>
          <div className='grid gap-1'><Label>سایت</Label><NativeSelect value={siteId} onChange={(e) => setSiteId(e.target.value)}>{sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>)}</NativeSelect></div>
          <div className='grid gap-1'><Label>گروه‌بندی</Label><NativeSelect value={groupBy} onChange={(e) => setGroupBy(e.target.value)}><NativeSelectOption value='model'>مدل</NativeSelectOption><NativeSelectOption value='provider'>ارائه‌دهنده</NativeSelectOption><NativeSelectOption value='task_kind'>نوع وظیفه</NativeSelectOption><NativeSelectOption value='agent'>عامل</NativeSelectOption></NativeSelect></div>
          <div className='grid gap-1'><Label>بودجه ماهانه (USD)</Label><div className='flex gap-1'><Input value={limit} onChange={(e) => setLimit(e.target.value)} type='number' dir='ltr' className='w-24' /><Button size='sm' variant='secondary' onClick={saveBudget}>ذخیره</Button></div></div>
        </div>
        {b && (
          <div className='rounded border p-2'>
            <div className='flex justify-between text-xs'><span>{b.month} · {BUDGET_FA[b.state]}</span><span dir='ltr'>{b.spent_usd.toFixed(3)} / {b.limit_usd} USD ({Math.round(b.ratio * 100)}%)</span></div>
            <div className='bg-muted mt-1 h-2 w-full overflow-hidden rounded'><div className='h-2' style={{ width: `${Math.min(100, b.ratio * 100)}%`, background: b.state === 'ok' ? '#16a34a' : b.state === 'warning' ? '#f59e0b' : '#dc2626' }} /></div>
          </div>
        )}
        <div className='overflow-x-auto rounded-md border'>
          <Table>
            <TableHeader><TableRow><TableHead>کلید</TableHead><TableHead>فراخوانی</TableHead><TableHead>موفق</TableHead><TableHead>توکن ورودی</TableHead><TableHead>توکن خروجی</TableHead><TableHead>هزینه</TableHead><TableHead>میانگین تأخیر</TableHead></TableRow></TableHeader>
            <TableBody>
              {(u?.rows ?? []).map((r) => <TableRow key={r.key}><TableCell dir='ltr'>{r.key}</TableCell><TableCell>{fa.format(r.calls)}</TableCell><TableCell>{fa.format(r.ok)}</TableCell><TableCell>{fa.format(r.input_tokens)}</TableCell><TableCell>{fa.format(r.output_tokens)}</TableCell><TableCell dir='ltr'>{r.cost_usd.toFixed(4)}$</TableCell><TableCell>{Math.round(r.avg_latency_ms)}ms</TableCell></TableRow>)}
              {(u?.rows.length ?? 0) === 0 && <TableRow><TableCell colSpan={7} className='text-muted-foreground text-center'>فراخوانی ثبت نشده.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------- prompt library
export function PromptLibrary({ sites }: { sites: Site[] }) {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [sel, setSel] = useState<Prompt | null>(null);
  const [siteId, setSiteId] = useState(sites[0]?.site_id ?? '');
  const [draft, setDraft] = useState(''); const [changelog, setChangelog] = useState('');
  const [preview, setPreview] = useState<string | null>(null);
  const [testOut, setTestOut] = useState<any | null>(null);
  const [cmp, setCmp] = useState<[number | null, number | null]>([null, null]);
  const load = useCallback(async () => { try { const p = await endpoints.aiPrompts(); setPrompts(p); if (sel) setSel(await endpoints.aiPrompt(sel.id)); } catch (e) { err(e); } }, [sel?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  async function open(p: Prompt) { const full = await endpoints.aiPrompt(p.id); setSel(full); const v = full.versions.find((x) => x.is_active) ?? full.versions[0]; setDraft(v?.template ?? ''); setPreview(null); setTestOut(null); setCmp([null, null]); }
  const active = sel?.versions.find((v) => v.is_active);
  return (
    <Card>
      <CardHeader><CardTitle>کتابخانه پرامپت (نسخه‌بندی‌شده در دیتابیس)</CardTitle><CardDescription>هر پرامپت چند نسخه دارد: متغیرها، فعال‌سازی، تأیید و کارایی (امتیاز/رتبه/هزینه). همه قالب‌های عامل‌ها باید <code dir='ltr'>{'{{memory_pack}}'}</code> داشته باشند تا حافظه سایت تزریق شود. فعال‌سازی نسخه فقط دستی است.</CardDescription></CardHeader>
      <CardContent className='grid gap-3 md:grid-cols-[260px_1fr]'>
        <div className='grid content-start gap-1 text-sm'>
          {prompts.map((p) => <button key={p.id} onClick={() => open(p)} className={`rounded border p-2 text-start ${sel?.id === p.id ? 'bg-accent' : 'hover:bg-accent/50'}`}><div className='font-medium'>{p.title}</div><div className='text-muted-foreground text-xs' dir='ltr'>{p.key} · v{p.versions.find((v) => v.is_active)?.version ?? p.active_version ?? '?'} · {p.versions.length} نسخه</div></button>)}
        </div>
        {sel ? (
          <div className='grid gap-3 text-sm'>
            <div className='flex flex-wrap items-center gap-2'><span className='font-medium'>{sel.title}</span><Badge variant='outline'>{sel.scope}</Badge>{sel.tags.map((t) => <Badge key={t} variant='secondary'>{t}</Badge>)}<span className='text-muted-foreground text-xs'>{sel.description}</span></div>
            <div className='overflow-x-auto rounded border'>
              <Table>
                <TableHeader><TableRow><TableHead>نسخه</TableHead><TableHead>متغیرها</TableHead><TableHead>وضعیت</TableHead><TableHead>تأیید</TableHead><TableHead>کارایی</TableHead><TableHead>تغییرات</TableHead><TableHead>عملیات</TableHead></TableRow></TableHeader>
                <TableBody>
                  {sel.versions.map((v) => { const perf = sel.performance?.find((x) => x.version_id === v.id); return (
                    <TableRow key={v.id}>
                      <TableCell>v{v.version}</TableCell><TableCell className='text-xs' dir='ltr'>{v.variables.join(', ')}</TableCell>
                      <TableCell>{v.is_active ? <Badge>فعال</Badge> : <Badge variant='outline'>غیرفعال</Badge>}</TableCell>
                      <TableCell><Badge variant={v.approval === 'approved' ? 'default' : v.approval === 'rejected' ? 'destructive' : 'secondary'}>{v.approval === 'approved' ? 'تأییدشده' : v.approval === 'rejected' ? 'ردشده' : 'در انتظار'}</Badge></TableCell>
                      <TableCell className='text-xs'>{perf && perf.tests ? `${perf.tests} تست · امتیاز ${perf.avg_score ?? '—'} · رتبه ${perf.avg_rating ?? '—'} · ${perf.avg_cost_usd?.toFixed(4) ?? '—'}$` : '—'}</TableCell>
                      <TableCell className='text-xs'>{v.changelog ?? '—'}</TableCell>
                      <TableCell><div className='flex flex-wrap gap-1'>
                        <Button size='sm' variant='ghost' onClick={() => { setDraft(v.template); setPreview(null); }}>بارگذاری</Button>
                        {!v.is_active && <Button size='sm' variant='secondary' onClick={async () => { try { await endpoints.aiPromptPatchVersion(v.id, { activate: true }); toast.success(`v${v.version} فعال شد`); load(); } catch (e) { err(e); } }}>فعال‌سازی</Button>}
                        {v.approval !== 'approved' && <Button size='sm' variant='outline' onClick={async () => { await endpoints.aiPromptPatchVersion(v.id, { approval: 'approved', approved_by: 'human' }); load(); }}>تأیید</Button>}
                        <Button size='sm' variant='ghost' onClick={async () => { const r = await endpoints.aiPromptPreview(v.id, { site_id: siteId }); setPreview(r.rendered + (r.missing.length ? `\n\n[متغیرهای بدون مقدار: ${r.missing.join(', ')}]` : '')); }}>پیش‌نمایش</Button>
                        <Button size='sm' variant='ghost' onClick={async () => { try { const r = await endpoints.aiPromptTest(v.id, { site_id: siteId }); setTestOut(r); toast.success('تست اجرا شد'); load(); } catch (e) { err(e); } }}>تست</Button>
                        <Button size='sm' variant='ghost' onClick={() => setCmp(([a, b]) => (a === null ? [v.id, b] : [a, v.id]))}>مقایسه</Button>
                      </div></TableCell>
                    </TableRow>); })}
                </TableBody>
              </Table>
            </div>
            <div className='grid gap-1'><Label>قالب نسخه جدید (از نسخه فعال v{active?.version})</Label><Textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={10} dir='auto' className='font-mono text-xs' /></div>
            <div className='flex flex-wrap items-end gap-2'>
              <div className='grid gap-1'><Label>توضیح تغییر</Label><Input value={changelog} onChange={(e) => setChangelog(e.target.value)} className='w-64' /></div>
              <div className='grid gap-1'><Label>سایت برای پیش‌نمایش/تست</Label><NativeSelect value={siteId} onChange={(e) => setSiteId(e.target.value)}>{sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>)}</NativeSelect></div>
              <Button size='sm' onClick={async () => { try { const v = await endpoints.aiPromptAddVersion(sel.id, { template: draft, changelog: changelog || undefined }); toast.success(`نسخه v${v.version} ثبت شد (غیرفعال — پس از تست فعال کنید)`); setChangelog(''); load(); } catch (e) { err(e); } }} disabled={!draft.trim()}>ثبت به‌عنوان نسخه جدید</Button>
            </div>
            {preview && <details open><summary className='cursor-pointer text-xs'>پیش‌نمایش رندرشده (با حافظه سایت)</summary><pre className='bg-muted max-h-72 overflow-auto rounded p-2 text-xs whitespace-pre-wrap' dir='auto'>{preview}</pre></details>}
            {testOut && <details open><summary className='cursor-pointer text-xs'>نتیجه تست — {testOut.provider}/{testOut.model} · {testOut.cost_usd?.toFixed?.(4)}$ · {testOut.latency_ms}ms {testOut.placeholder ? '· نمایشی' : ''}</summary><pre className='bg-muted max-h-72 overflow-auto rounded p-2 text-xs whitespace-pre-wrap' dir='auto'>{typeof testOut.output === 'string' ? testOut.output : JSON.stringify(testOut.output, null, 1)}</pre>
              {testOut.test_id && <div className='mt-1 flex items-center gap-1 text-xs'>رتبه انسانی: {[1, 2, 3, 4, 5].map((n) => <button key={n} className='rounded border px-2' onClick={async () => { await endpoints.aiPromptRateTest(testOut.test_id, { human_rating: n }); toast.success('ثبت شد'); load(); }}>{n}</button>)}</div>}</details>}
            {cmp[0] !== null && cmp[1] !== null && (
              <div className='grid gap-2 md:grid-cols-2'>{cmp.map((id) => { const v = sel.versions.find((x) => x.id === id)!; return <div key={id} className='rounded border p-2'><div className='mb-1 text-xs font-medium'>v{v.version} · {v.approval}{v.is_active ? ' · فعال' : ''}</div><pre className='bg-muted max-h-64 overflow-auto rounded p-2 text-xs whitespace-pre-wrap' dir='auto'>{v.template}</pre></div>; })}</div>
            )}
          </div>
        ) : <p className='text-muted-foreground text-sm'>یک پرامپت انتخاب کنید.</p>}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------- AI insights (recommendation only)
export function InsightsPanel({ sites }: { sites: Site[] }) {
  const [siteId, setSiteId] = useState(sites[0]?.site_id ?? '');
  const [rows, setRows] = useState<AiInsight[]>([]);
  const load = useCallback(async () => { try { setRows(await endpoints.aiInsights(siteId || undefined)); } catch (e) { err(e); } }, [siteId]);
  useEffect(() => { load(); }, [load]);
  return (
    <Card>
      <CardHeader><CardTitle className='flex items-center justify-between'>یادگیری AI (پیشنهاد؛ بدون تغییر خودکار) <Button size='sm' variant='secondary' onClick={async () => { const r = await endpoints.aiInsightsLearn(siteId || undefined); toast.success(`تحلیل انجام شد: ${r.created ?? 0} بینش جدید`); load(); }}>تحلیل بازخوردها</Button></CardTitle>
        <CardDescription>از رتبه‌ها و برچسب‌های انسانی، امتیازها و هزینه هر مدل/پرامپت الگو استخراج می‌شود (حداقل ۵ نمونه). پذیرش شما فقط الگو را در حافظه سایت ذخیره می‌کند؛ مسیردهی و پرامپت‌ها هرگز خودکار عوض نمی‌شوند.</CardDescription></CardHeader>
      <CardContent className='grid gap-2 text-sm'>
        <NativeSelect value={siteId} onChange={(e) => setSiteId(e.target.value)} className='w-60'><NativeSelectOption value=''>همه سایت‌ها</NativeSelectOption>{sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>)}</NativeSelect>
        {rows.map((i) => (
          <div key={i.id} className='flex flex-wrap items-center gap-2 rounded border p-2'>
            <Badge variant={i.status === 'accepted' ? 'default' : i.status === 'dismissed' ? 'outline' : 'secondary'}>{i.status === 'accepted' ? 'پذیرفته' : i.status === 'dismissed' ? 'ردشده' : 'جدید'}</Badge>
            <Badge variant='outline'>{i.category}</Badge>
            <span className='flex-1'>{i.message_fa}</span>
            <span className='text-muted-foreground text-xs'>n={i.n} · اثر {i.effect > 0 ? '+' : ''}{i.effect}{i.recommendation?.action ? ` · پیشنهاد: ${i.recommendation.action_fa ?? i.recommendation.action}` : ''}</span>
            {i.status === 'new' && <><Button size='sm' onClick={async () => { await endpoints.aiInsightStatus(i.id, 'accepted'); toast.success('پذیرفته شد و در حافظه سایت ثبت شد'); load(); }}>پذیرش</Button><Button size='sm' variant='ghost' onClick={async () => { await endpoints.aiInsightStatus(i.id, 'dismissed'); load(); }}>رد</Button></>}
          </div>
        ))}
        {rows.length === 0 && <p className='text-muted-foreground'>بینشی نیست — با ثبت بازخورد روی پیش‌نویس‌ها (رتبه ۱–۵ + برچسب) داده جمع می‌شود.</p>}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------- route policy/fallback editor helpers
export const POLICY_FA: Record<string, string> = { auto: 'خودکار (سیاست وظیفه)', explicit: 'صریح (مدل انتخابی)', echo: 'Echo (بدون فراخوانی)' };
export function taskLabel(k: string) { return TASK_FA[k] ?? k; }
export type { PromptVersion };
