'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ApiError, endpoints, type AiModel, type GatewayStatus, type ProviderConfig, type ProviderKind, type Site, type TaskRoute } from '@/lib/api/client';
import { StatChip } from '@/components/seo-brain/states';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { InsightsPanel, ModelCatalog, POLICY_FA, PromptLibrary, UsagePanel } from './ai-ops-panels';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { TASK_FA } from '@/features/content/constants';

export function AiModelsPage({ sites = [] }: { sites?: Site[] }) {
  const [kinds, setKinds] = useState<ProviderKind[]>([]);
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [routes, setRoutes] = useState<TaskRoute[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ProviderConfig | null>(null);
  const [f, setF] = useState({ name: '', kind: 'anthropic', api_key: '', base_url: '', default_model: '' });
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [k, p, r] = await Promise.all([endpoints.providerKinds(), endpoints.providerConfigs(), endpoints.taskRoutes()]);
      setKinds(k); setProviders(p); setRoutes(r.routes);
    } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const kind = kinds.find((k) => k.kind === f.kind);
  function openNew() { setEditing(null); setF({ name: '', kind: 'anthropic', api_key: '', base_url: '', default_model: '' }); setOpen(true); }
  function openClaude() { const k = kinds.find((x) => x.kind === 'anthropic'); setEditing(null); setF({ name: 'anthropic', kind: 'anthropic', api_key: '', base_url: k?.base_url ?? 'https://api.anthropic.com', default_model: 'claude-sonnet-5' }); setOpen(true); }
  function openCloudProvider(kindKey: 'groq' | 'cloudflare') { const k = kinds.find((x) => x.kind === kindKey); setEditing(null); setF({ name: kindKey, kind: kindKey, api_key: '', base_url: k?.base_url ?? '', default_model: k?.models[0] ?? '' }); setOpen(true); }
  function openOmni() { const k = kinds.find((x) => x.kind === 'omniroute'); setEditing(null); setF({ name: 'omniroute', kind: 'omniroute', api_key: '', base_url: k?.base_url ?? 'http://127.0.0.1:20128/v1', default_model: 'auto' }); setOpen(true); }
  function openEdit(p: ProviderConfig) { setEditing(p); setF({ name: p.name, kind: p.kind, api_key: '', base_url: p.base_url ?? '', default_model: p.default_model ?? '' }); setOpen(true); }
  async function save() {
    setBusy('save');
    try {
      const body: Record<string, unknown> = { name: f.name.trim(), base_url: f.base_url || undefined, default_model: f.default_model || undefined };
      if (f.api_key) body.api_key = f.api_key;
      if (editing) await endpoints.updateProvider(editing.id, body); else await endpoints.createProvider({ ...body, kind: f.kind });
      toast.success('ذخیره شد — کلید به‌صورت رمزنگاری‌شده روی همین دستگاه نگهداری می‌شود'); setOpen(false); load();
    } catch (e) { toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)); } finally { setBusy(null); }
  }
  async function test(p: ProviderConfig) {
    setBusy(`test-${p.id}`);
    try { const r = await endpoints.testProvider(p.id); (r.ok ? toast.success : toast.error)(r.message); load(); } catch (e) { toast.error(String(e)); } finally { setBusy(null); }
  }
  async function remove(p: ProviderConfig) {
    if (!confirm(`ارائه‌دهنده «${p.name}» و کلید آن حذف شود؟`)) return;
    await endpoints.deleteProvider(p.id); toast.success('حذف شد'); load();
  }
  async function setRoute(kindKey: string, patch: Partial<TaskRoute>) {
    const cur = routes.find((r) => r.task_kind === kindKey)!;
    const body = { provider_id: cur.provider_id, model: cur.model, fallback_provider_id: cur.fallback_provider_id, fallback_model: cur.fallback_model, policy: cur.policy, fallbacks: cur.fallbacks?.map((f) => ({ provider_id: f.provider_id, model: f.model })), ...patch };
    try { await endpoints.setTaskRoute(kindKey, body); load(); } catch (e) { toast.error(String(e)); }
  }
  const modelsOf = (pid: number | null) => providers.find((p) => p.id === pid)?.models ?? [];

  return (
    <div className='flex flex-col gap-4'>
     <Tabs defaultValue='providers'>
      <TabsList className='flex-wrap'><TabsTrigger value='providers'>ارائه‌دهنده‌ها و مسیردهی</TabsTrigger><TabsTrigger value='catalog'>کاتالوگ مدل‌ها</TabsTrigger><TabsTrigger value='usage'>مصرف و بودجه</TabsTrigger><TabsTrigger value='prompts'>پرامپت‌ها</TabsTrigger><TabsTrigger value='insights'>یادگیری AI</TabsTrigger></TabsList>
      <TabsContent value='providers' className='flex flex-col gap-4'>
      <ProviderKindCard kindKey='anthropic' providers={providers} kind={kinds.find((k) => k.kind === 'anthropic')} onConnect={openClaude} onEdit={openEdit} onTest={test} onChanged={load} busy={busy} setBusy={setBusy} />
      <div className='grid gap-4 xl:grid-cols-2'>
        <ProviderKindCard kindKey='groq' providers={providers} kind={kinds.find((k) => k.kind === 'groq')} onConnect={() => openCloudProvider('groq')} onEdit={openEdit} onTest={test} onChanged={load} busy={busy} setBusy={setBusy} />
        <ProviderKindCard kindKey='cloudflare' providers={providers} kind={kinds.find((k) => k.kind === 'cloudflare')} onConnect={() => openCloudProvider('cloudflare')} onEdit={openEdit} onTest={test} onChanged={load} busy={busy} setBusy={setBusy} />
      </div>
      <ProviderKindCard kindKey='omniroute' providers={providers} kind={kinds.find((k) => k.kind === 'omniroute')} onConnect={openOmni} onEdit={openEdit} onTest={test} onChanged={load} busy={busy} setBusy={setBusy} />
      <Card>
        <CardHeader>
          <CardTitle className='flex items-center justify-between'>ارائه‌دهنده‌ها <Button size='sm' onClick={openNew}>افزودن ارائه‌دهنده</Button></CardTitle>
          <CardDescription>Groq و Cloudflare Workers AI برای اجرای ابری با سهمیه رایگان، به‌همراه Claude · ChatGPT · Gemini · OpenRouter · API سفارشی. کلیدها هرگز به مرورگر برنمی‌گردند و فقط ۴ رقم آخر نمایش داده می‌شود.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className='overflow-x-auto rounded-md border'>
            <Table>
              <TableHeader><TableRow><TableHead>نام</TableHead><TableHead>نوع</TableHead><TableHead>مدل پیش‌فرض</TableHead><TableHead>کلید</TableHead><TableHead>آخرین تست</TableHead><TableHead>عملیات</TableHead></TableRow></TableHeader>
              <TableBody>
                {providers.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className='font-medium'>{p.name}{!p.enabled && <Badge variant='outline' className='ms-1'>غیرفعال</Badge>}</TableCell>
                    <TableCell>{p.kind_label}</TableCell><TableCell dir='ltr'>{p.default_model ?? '—'}</TableCell>
                    <TableCell dir='ltr'>{p.has_key ? `••••${p.key_hint}` : <span className='text-muted-foreground'>—</span>}</TableCell>
                    <TableCell className='text-xs'>{p.last_test ? <span className={p.last_test.ok ? 'text-emerald-600' : 'text-muted-foreground'}>{p.last_test.message}</span> : '—'}</TableCell>
                    <TableCell><div className='flex gap-1'>
                      <Button size='sm' variant='secondary' disabled={busy === `test-${p.id}`} onClick={() => test(p)}>{busy === `test-${p.id}` ? '…' : 'تست اتصال'}</Button>
                      <Button size='sm' variant='outline' onClick={() => openEdit(p)}>ویرایش</Button>
                      <Button size='sm' variant='ghost' className='text-destructive' onClick={() => remove(p)}>حذف</Button>
                    </div></TableCell>
                  </TableRow>
                ))}
                {providers.length === 0 && <TableRow><TableCell colSpan={6} className='text-muted-foreground text-center'>هنوز ارائه‌دهنده‌ای ثبت نشده — تا آن زمان بریف‌ها قاعده‌محور ساخته می‌شوند و هیچ فراخوانی خارجی انجام نمی‌شود.</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>مسیردهی وظایف</CardTitle><CardDescription>برای هر نوع وظیفه، مدل اصلی و مدل جایگزین را انتخاب کنید (مثلاً نگارش محتوا → Claude، تحلیل سئو → GPT، تحقیق → Gemini). سیاست «خودکار» یعنی مسیریاب بر اساس سطح/برچسب مدل انتخاب می‌کند؛ «صریح» مدل شما را اجباری می‌کند؛ زنجیره جایگزین‌ها به ترتیب امتحان می‌شود. پیشنهادهای AI برای مسیر فقط پیشنهادند و اینجا با دست اعمال می‌شوند.</CardDescription></CardHeader>
        <CardContent>
          <div className='overflow-x-auto rounded-md border'>
            <Table>
              <TableHeader><TableRow><TableHead>وظیفه</TableHead><TableHead>سیاست</TableHead><TableHead>ارائه‌دهنده</TableHead><TableHead>مدل</TableHead><TableHead>جایگزین</TableHead><TableHead>مدل جایگزین</TableHead><TableHead>زنجیره جایگزین‌ها</TableHead></TableRow></TableHeader>
              <TableBody>
                {routes.map((r) => (
                  <TableRow key={r.task_kind}>
                    <TableCell className='font-medium'>{TASK_FA[r.task_kind] ?? r.task_kind}</TableCell>
                    <TableCell><NativeSelect value={r.policy ?? 'auto'} onChange={(e) => setRoute(r.task_kind, { policy: e.target.value as TaskRoute['policy'] })} className='h-8 w-36 text-xs'>{Object.entries(POLICY_FA).map(([k, v]) => <NativeSelectOption key={k} value={k}>{v}</NativeSelectOption>)}</NativeSelect></TableCell>
                    <TableCell><NativeSelect value={r.provider_id ?? ''} onChange={(e) => setRoute(r.task_kind, { provider_id: e.target.value ? Number(e.target.value) : null, model: null })} className='h-8 w-40 text-xs'><NativeSelectOption value=''>—</NativeSelectOption>{providers.map((p) => <NativeSelectOption key={p.id} value={p.id}>{p.name}</NativeSelectOption>)}</NativeSelect></TableCell>
                    <TableCell><Input aria-label={`مدل اصلی ${TASK_FA[r.task_kind] ?? r.task_kind}`} value={r.model ?? ''} onChange={(e) => setRoute(r.task_kind, { model: e.target.value || null })} list={`m-${r.task_kind}`} placeholder={providers.find((p) => p.id === r.provider_id)?.default_model ?? ''} dir='ltr' className='h-8 w-44 text-xs' /><datalist id={`m-${r.task_kind}`} aria-label='مدل‌های اصلی'>{modelsOf(r.provider_id).map((m) => <option key={m} value={m}>{m}</option>)}</datalist></TableCell>
                    <TableCell><NativeSelect value={r.fallback_provider_id ?? ''} onChange={(e) => setRoute(r.task_kind, { fallback_provider_id: e.target.value ? Number(e.target.value) : null, fallback_model: null })} className='h-8 w-40 text-xs'><NativeSelectOption value=''>—</NativeSelectOption>{providers.map((p) => <NativeSelectOption key={p.id} value={p.id}>{p.name}</NativeSelectOption>)}</NativeSelect></TableCell>
                    <TableCell><Input value={r.fallback_model ?? ''} onChange={(e) => setRoute(r.task_kind, { fallback_model: e.target.value || null })} dir='ltr' className='h-8 w-44 text-xs' /></TableCell>
                    <TableCell className='text-xs'>
                      <div className='flex flex-wrap items-center gap-1'>
                        {(r.fallbacks ?? []).map((f, i) => <Badge key={i} variant='outline' dir='ltr'>{f.provider_name ?? f.provider_id}/{f.model} <button className='ms-1' onClick={() => setRoute(r.task_kind, { fallbacks: (r.fallbacks ?? []).filter((_, j) => j !== i) })}>×</button></Badge>)}
                        <NativeSelect value='' onChange={(e) => { const [pid, model] = e.target.value.split('|'); if (pid) setRoute(r.task_kind, { fallbacks: [...(r.fallbacks ?? []), { provider_id: Number(pid), model }] }); }} className='h-7 w-32 text-xs'><NativeSelectOption value=''>+ افزودن</NativeSelectOption>{providers.flatMap((p) => (p.models.length ? p.models : [p.default_model ?? '']).filter(Boolean).map((m) => <NativeSelectOption key={`${p.id}|${m}`} value={`${p.id}|${m}`}>{p.name}/{m}</NativeSelectOption>))}</NativeSelect>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
      </TabsContent>
      <TabsContent value='catalog'><ModelCatalog /></TabsContent>
      <TabsContent value='usage'><UsagePanel sites={sites} /></TabsContent>
      <TabsContent value='prompts'><PromptLibrary sites={sites} /></TabsContent>
      <TabsContent value='insights'><InsightsPanel sites={sites} /></TabsContent>
     </Tabs>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>{editing ? `ویرایش ${editing.name}` : 'افزودن ارائه‌دهنده'}</DialogTitle><DialogDescription>کلید API فقط برای ذخیره ارسال می‌شود و دیگر قابل مشاهده نیست.</DialogDescription></DialogHeader>
          <div className='grid gap-3 text-sm'>
            <div className='grid gap-1.5'><Label>نام</Label><Input value={f.name} onChange={(e) => setF((s) => ({ ...s, name: e.target.value }))} placeholder='مثلاً Claude اصلی' /></div>
            {!editing && (
              <div className='grid gap-1.5'><Label>نوع</Label>
                <NativeSelect value={f.kind} onChange={(e) => { const k = kinds.find((x) => x.kind === e.target.value); setF((s) => ({ ...s, kind: e.target.value, base_url: k?.base_url ?? '', default_model: k?.models[0] ?? '' })); }}>
                  {kinds.map((k) => <NativeSelectOption key={k.kind} value={k.kind}>{k.label}</NativeSelectOption>)}
                </NativeSelect></div>
            )}
            <div className='grid gap-1.5'><Label>کلید API {kind?.needs_key === false && <span className='text-muted-foreground'>(اختیاری)</span>}</Label><Input type='password' value={f.api_key} onChange={(e) => setF((s) => ({ ...s, api_key: e.target.value }))} placeholder={editing?.has_key ? `فعلی: ••••${editing.key_hint} — برای تغییر وارد کنید` : ''} dir='ltr' autoComplete='off' /></div>
            <div className='grid gap-1.5'><Label>Base URL</Label><Input value={f.base_url} onChange={(e) => setF((s) => ({ ...s, base_url: e.target.value }))} dir='ltr' placeholder={kind?.base_url} /></div>
            <div className='grid gap-1.5'><Label htmlFor='default-model'>مدل پیش‌فرض</Label><Input id='default-model' value={f.default_model} onChange={(e) => setF((s) => ({ ...s, default_model: e.target.value }))} dir='ltr' list='kind-models' /><datalist id='kind-models' aria-label='مدل‌های پیشنهادی'>{(kind?.models ?? []).map((m) => <option key={m} value={m}>{m}</option>)}</datalist></div>
            <div className='flex justify-end gap-2'><Button variant='ghost' onClick={() => setOpen(false)}>انصراف</Button><Button onClick={save} disabled={!!busy || !f.name.trim()}>{busy === 'save' ? '…' : 'ذخیره'}</Button></div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ---------------------------------------------------------------------------- Claude (Anthropic) card
const TIER_FA: Record<string, string> = { balanced: 'متعادل', quality: 'کیفیت', fast: 'سریع', reasoning: 'استدلال' };
type ClaudeStatus = 'connected' | 'missing_credentials' | 'error' | 'untested';
function claudeStatus(p: ProviderConfig | undefined): ClaudeStatus {
  if (!p || !p.has_key) return 'missing_credentials';
  if (!p.last_test) return 'untested';
  return p.last_test.ok ? 'connected' : 'error';
}
const CLAUDE_STATUS_FA: Record<ClaudeStatus, { fa: string; cls: string }> = {
  connected: { fa: 'متصل', cls: 'bg-emerald-600 text-white' }, missing_credentials: { fa: 'کلید ثبت نشده', cls: 'bg-amber-500 text-white' },
  error: { fa: 'خطا', cls: 'bg-red-600 text-white' }, untested: { fa: 'تست نشده', cls: 'bg-slate-500 text-white' },
};

const CARD_META: Record<string, { title: string; wanted: string[]; connectLabel: string; okText: string; needKey: boolean }> = {
  anthropic: { title: 'Claude (Anthropic)', wanted: ['claude-sonnet-5', 'claude-opus-5', 'claude-haiku-4-5'], connectLabel: 'اتصال Claude', needKey: true, okText: 'Claude متصل است. مدل پیش‌فرض Sonnet (متعادل)، Opus برای کیفیت و Haiku برای وظایف سریع. مسیرهای وظایف را با «اعمال مسیرهای پیشنهادی» تنظیم کنید (تغییر مسیر همیشه اقدام انسانی است).' },
  groq: { title: 'Groq Cloud — اجرای رایگان روی سرور', wanted: ['qwen/qwen3.6-27b', 'openai/gpt-oss-120b', 'openai/gpt-oss-20b'], connectLabel: 'اتصال Groq رایگان', needKey: true, okText: 'Groq متصل است. تولید متن روی زیرساخت ابری Groq انجام می‌شود و هیچ مدلی روی کامپیوتر شما اجرا نمی‌شود. خطای محدودیت سهمیه به‌صورت خودکار وارد زنجیره جایگزین می‌شود.' },
  cloudflare: { title: 'Cloudflare Workers AI — جایگزین رایگان', wanted: ['@cf/qwen/qwen3-30b-a3b-fp8', '@cf/openai/gpt-oss-20b'], connectLabel: 'اتصال Workers AI', needKey: true, okText: 'Workers AI متصل است و به‌عنوان مسیر ابری جایگزین هنگام محدودیت یا قطعی Groq قابل استفاده است.' },
  omniroute: { title: 'OmniRoute (گیت‌وی مسیریابی خارجی)', wanted: ['auto', 'auto/fast', 'auto/cheap', 'auto/coding'], connectLabel: 'افزودن OmniRoute', needKey: false, okText: 'OmniRoute متصل است: SEO Brain Gateway → OmniRoute → Claude / OpenAI / Gemini / … . مدل «auto» مسیریابی خود OmniRoute است؛ ids به شکل provider/model هم قابل انتخاب‌اند. بودجه، دفتر مصرف، اعتبارسنجی و مسیریابی SEO Brain همچنان اعمال می‌شود.' },
};

export function ProviderKindCard({ kindKey, providers, kind, onConnect, onEdit, onTest, onChanged, busy, setBusy }: { kindKey: 'anthropic' | 'groq' | 'cloudflare' | 'omniroute'; providers: ProviderConfig[]; kind?: ProviderKind; onConnect: () => void; onEdit: (p: ProviderConfig) => void; onTest: (p: ProviderConfig) => Promise<void>; onChanged: () => void; busy: string | null; setBusy: (v: string | null) => void }) {
  const meta = CARD_META[kindKey];
  const claude = providers.find((p) => p.kind === kindKey);
  const status: ClaudeStatus = kindKey === 'omniroute' ? (!claude ? 'missing_credentials' : !claude.enabled ? 'error' : !claude.last_test ? 'untested' : claude.last_test.ok ? 'connected' : 'error') : claudeStatus(claude);
  const [gw, setGw] = useState<GatewayStatus | null>(null);
  const [models, setModels] = useState<AiModel[]>([]);
  const [health, setHealth] = useState<Record<string, any> | null>(null);
  const [usage, setUsage] = useState<{ calls: number; cost_usd: number; input_tokens: number; output_tokens: number; ok: number } | null>(null);
  const [routesApplied, setRoutesApplied] = useState<number | null>(null);
  const refresh = useCallback(async () => {
    if (!claude) { setModels([]); setHealth(null); setUsage(null); return; }
    try {
      const [m, h, u] = await Promise.all([endpoints.aiModels(claude.id), endpoints.aiHealth(), endpoints.aiUsage({ group_by: 'provider' })]);
      setModels(m.filter((x) => x.enabled)); setHealth(h.providers.find((x: any) => x.provider === claude.name) ?? null); setUsage(u.rows.find((r) => r.key === claude.name) ?? null);
      if (kindKey === 'omniroute') endpoints.gatewayStatus(claude.id).then(setGw).catch(() => setGw(null));
    } catch { /* panels stay empty */ }
  }, [claude]);
  useEffect(() => { refresh(); }, [refresh]);
  async function sync() {
    if (!claude) return; setBusy('sync');
    try { const r = await endpoints.aiModelsSync(claude.id); const x = r[claude.name] ?? {}; toast.success(`همگام‌سازی مدل‌ها: ${x.added ?? 0} جدید، ${x.discovered ?? 0} کشف‌شده${x.error ? ` — ${x.error}` : ''}`); refresh(); onChanged(); }
    catch (e) { toast.error(String(e)); } finally { setBusy(null); }
  }
  async function applyRoutes() {
    if (!claude) return;
    const rec = await endpoints.recommendedRoutes(claude.id);
    const preview = rec.routes.map((r) => `${TASK_FA[r.task_kind] ?? r.task_kind}: ${r.model}${r.fallback_model ? ` → ${r.fallback_model}` : ''}`).join('\n');
    if (!confirm(`مسیرهای پیشنهادی ${meta.title} روی مسیردهی سراسری اعمال شود؟ مسیرهای فعلی بازنویسی می‌شوند.\n\n${preview}`)) return;
    setBusy('routes');
    try { const r = await endpoints.applyRecommendedRoutes(claude.id, {}); setRoutesApplied(r.applied); toast.success(`${r.applied} مسیر اعمال شد`); onChanged(); }
    catch (e) { toast.error(String(e)); } finally { setBusy(null); }
  }
  const st = CLAUDE_STATUS_FA[status];
  const wanted = meta.wanted;
  const shown = [...models].sort((a, b) => (wanted.indexOf(a.model_id) === -1 ? 9 : wanted.indexOf(a.model_id)) - (wanted.indexOf(b.model_id) === -1 ? 9 : wanted.indexOf(b.model_id)));
  return (
    <Card className='border-primary/30'>
      <CardHeader>
        <CardTitle className='flex flex-wrap items-center gap-2'>
          <span>{meta.title}</span>
          <span className={`rounded-full px-2 py-0.5 text-xs ${st.cls}`}>{st.fa}</span>
          {claude && <Badge variant='outline' dir='ltr'>{claude.name} · {claude.default_model ?? '—'}</Badge>}
          <span className='ms-auto flex flex-wrap gap-1'>
            {claude ? (<>
              <Button size='sm' variant='secondary' disabled={busy === `test-${claude.id}`} onClick={() => onTest(claude).then(refresh)}>{busy === `test-${claude.id}` ? '…' : 'تست اتصال'}</Button>
              <Button size='sm' variant='outline' disabled={busy === 'sync' || (meta.needKey && !claude.has_key)} onClick={sync}>{busy === 'sync' ? '…' : 'همگام‌سازی مدل‌ها'}</Button>
              <Button size='sm' variant='outline' disabled={busy === 'routes' || (meta.needKey && !claude.has_key)} onClick={applyRoutes}>{busy === 'routes' ? '…' : 'اعمال مسیرهای پیشنهادی'}</Button>
              <Button size='sm' variant='ghost' onClick={() => onEdit(claude)}>{claude.has_key ? 'تغییر کلید' : meta.needKey ? 'ثبت کلید' : 'ویرایش / کلید (اختیاری)'}</Button>
            </>) : <Button size='sm' onClick={onConnect}>{meta.connectLabel}</Button>}
          </span>
        </CardTitle>
        <CardDescription>
          {status === 'missing_credentials' && kindKey === 'omniroute' ? (
            <span className='block space-y-1'>
              <span className='block font-medium text-foreground'>OmniRoute هنوز به‌عنوان ارائه‌دهنده ثبت نشده است.</span>
              <span className='block'>{kind?.setup?.fa}</span>
              <span className='block' dir='ltr'>1) npm i -g omniroute → omniroute (port 20128) &nbsp; 2) «افزودن OmniRoute» (endpoint {kind?.base_url}) &nbsp; 3) تست اتصال → همگام‌سازی مدل‌ها</span>
            </span>
          ) : status === 'missing_credentials' ? (
            <span className='block space-y-1'>
              <span className='block font-medium text-foreground'>برای تولید واقعی محتوا، کلید API کلود لازم است.</span>
              <span className='block'>{kind?.setup?.fa ?? 'کلید API را از کنسول Anthropic بسازید و اینجا وارد کنید.'}</span>
              <span className='block' dir='ltr'>1) <a className='underline' href={kind?.setup?.console_url ?? 'https://platform.claude.com/settings/keys'} target='_blank' rel='noreferrer'>کنسول ارائه‌دهنده</a> → Create Key &nbsp; 2) «{claude ? 'ثبت کلید' : meta.connectLabel}» → paste {kind?.setup?.key_prefix ? `(${kind.setup.key_prefix}…)` : ''} &nbsp; 3) تست اتصال</span>
              <span className='block'>کلید و اجرای مدل فقط روی سرور انجام می‌شود؛ چیزی روی کامپیوتر شما نصب یا اجرا نمی‌شود.</span>
            </span>
          ) : status === 'error' ? `آخرین تست ناموفق: ${claude?.last_test?.message ?? '—'} — کلید را بررسی/تعویض کنید یا دوباره تست بگیرید.`
          : status === 'untested' ? 'کلید ثبت شده است؛ برای تأیید دسترسی «تست اتصال» را بزنید (فقط فهرست مدل‌ها خوانده می‌شود، پرامپتی ارسال نمی‌شود).'
          : meta.okText}
        </CardDescription>
      </CardHeader>
      {claude && (
        <CardContent className='grid gap-3 text-sm md:grid-cols-3'>
          <div className='rounded-md border p-2'>
            <div className='mb-1 text-xs font-medium'>مدل‌ها ({shown.length})</div>
            <ul className='space-y-1 text-xs'>{shown.slice(0, 8).map((m) => <li key={m.id} className='flex items-center gap-1'><span dir='ltr' className='font-medium'>{m.display ?? m.model_id}</span><Badge variant='outline' className='text-[10px]'>{TIER_FA[m.tier] ?? m.tier}</Badge><span className='text-muted-foreground ms-auto' dir='ltr'>{m.price_in_per_m}$/{m.price_out_per_m}$ per M</span></li>)}{shown.length === 0 && <li className='text-muted-foreground'>مدلی ثبت نشده — «همگام‌سازی مدل‌ها»</li>}</ul>
          </div>
          <div className='rounded-md border p-2'>
            <div className='mb-1 text-xs font-medium'>سلامت و آخرین تست</div>
            <div className='grid grid-cols-2 gap-1'>
              <StatChip label='فراخوانی' value={health?.calls ?? 0} /><StatChip label='خطا' value={health?.failures ?? 0} tone={(health?.failures ?? 0) > 0 ? 'warn' : 'default'} />
              <StatChip label='p50' value={health?.p50_ms != null ? `${health.p50_ms} ms` : '—'} /><StatChip label='مدار قطع' value={health?.breaker_open_until ? 'باز' : 'بسته'} tone={health?.breaker_open_until ? 'bad' : 'good'} />
            </div>
            <div className='text-muted-foreground mt-1 text-[11px]'>{claude.last_test ? <span className={claude.last_test.ok ? 'text-emerald-600' : 'text-red-600'}>{claude.last_test.message} · {String(claude.last_test.tested_at).slice(0, 16).replace('T', ' ')}</span> : 'هنوز تست نشده'}{health?.last_error && !claude.last_test?.ok && <span> · {health.last_error}</span>}</div>
          </div>
          <div className='rounded-md border p-2'>
            <div className='mb-1 text-xs font-medium'>مصرف (همه سایت‌ها)</div>
            <div className='grid grid-cols-2 gap-1'>
              <StatChip label='فراخوانی موفق' value={`${usage?.ok ?? 0} / ${usage?.calls ?? 0}`} /><StatChip label='هزینه' value={`${(usage?.cost_usd ?? 0).toFixed(4)}$`} />
              <StatChip label='توکن ورودی' value={usage?.input_tokens ?? 0} /><StatChip label='توکن خروجی' value={usage?.output_tokens ?? 0} />
            </div>
            <div className='text-muted-foreground mt-1 text-[11px]'>کلید: {claude.has_key ? `••••${claude.key_hint}` : meta.needKey ? '—' : 'بدون کلید (اختیاری)'} (SecretStore رمزنگاری‌شده روی سرور){routesApplied != null && ` · ${routesApplied} مسیر اعمال شد`}</div>
          </div>
          {kindKey === 'omniroute' && (
            <div className='rounded-md border p-2 md:col-span-3'>
              <div className='mb-1 text-xs font-medium'>وضعیت مسیریابی و جایگزین (SEO Brain Gateway → OmniRoute)</div>
              {!gw ? <p className='text-muted-foreground text-xs'>—</p> : (
                <div className='grid gap-2 text-xs md:grid-cols-3'>
                  <div><span className='text-muted-foreground'>endpoint:</span> <span dir='ltr'>{gw.endpoint_url}</span> · <span className='text-muted-foreground'>وضعیت:</span> {gw.status}{gw.breaker_open ? ' · مدار قطع باز' : ''}<br /><span className='text-muted-foreground'>مدل‌های در دسترس:</span> {gw.routing.models_available} · <span className='text-muted-foreground'>auto:</span> <span dir='ltr'>{gw.routing.auto_models.join(', ')}</span></div>
                  <div><span className='text-muted-foreground'>مسیر اصلی برای:</span> {gw.routing.primary_for.length ? gw.routing.primary_for.map((k) => TASK_FA[k] ?? k).join('، ') : 'هیچ وظیفه‌ای (فقط انتخاب دستی)'}<br /><span className='text-muted-foreground'>آخرین تصمیم OmniRoute:</span> <span dir='ltr'>{gw.routing.last_decision ? (gw.routing.last_decision.decision ?? JSON.stringify(gw.routing.last_decision)) : '—'}</span></div>
                  <div><span className='text-muted-foreground'>جایگزین برای:</span> {gw.fallback.fallback_for.length ? gw.fallback.fallback_for.map((k) => TASK_FA[k] ?? k).join('، ') : '—'}<br /><span className='text-muted-foreground'>زنجیره جایگزین:</span> {gw.fallback.chain_fallback}<br /><span className='text-muted-foreground'>جایگزین بالادستی:</span> {gw.fallback.upstream ?? '—'}</div>
                  {gw.recent_calls.length > 0 && <div className='md:col-span-3'><span className='text-muted-foreground'>آخرین فراخوانی‌ها:</span> {gw.recent_calls.slice(0, 5).map((c) => <Badge key={c.id} variant={c.ok ? 'outline' : 'destructive'} className='me-1 text-[10px]' dir='ltr'>{c.model} · {c.latency_ms}ms · {c.cost_usd.toFixed(4)}$</Badge>)}</div>}
                </div>
              )}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
