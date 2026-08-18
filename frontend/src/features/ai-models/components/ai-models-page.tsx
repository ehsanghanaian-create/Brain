'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ApiError, endpoints, type ProviderConfig, type ProviderKind, type Site, type TaskRoute } from '@/lib/api/client';
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
      <Card>
        <CardHeader>
          <CardTitle className='flex items-center justify-between'>ارائه‌دهنده‌ها <Button size='sm' onClick={openNew}>افزودن ارائه‌دهنده</Button></CardTitle>
          <CardDescription>Claude · ChatGPT · Gemini · OpenRouter · مدل محلی (Ollama) · API سفارشی. کلیدها هرگز به مرورگر برنمی‌گردند و در دیتابیس ذخیره نمی‌شوند (رمزنگاری DPAPI روی همین دستگاه؛ فقط ۴ رقم آخر نمایش داده می‌شود).</CardDescription>
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
                    <TableCell><Input value={r.model ?? ''} onChange={(e) => setRoute(r.task_kind, { model: e.target.value || null })} list={`m-${r.task_kind}`} placeholder={providers.find((p) => p.id === r.provider_id)?.default_model ?? ''} dir='ltr' className='h-8 w-44 text-xs' /><datalist id={`m-${r.task_kind}`}>{modelsOf(r.provider_id).map((m) => <option key={m} value={m} />)}</datalist></TableCell>
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
            <div className='grid gap-1.5'><Label>مدل پیش‌فرض</Label><Input value={f.default_model} onChange={(e) => setF((s) => ({ ...s, default_model: e.target.value }))} dir='ltr' list='kind-models' /><datalist id='kind-models'>{(kind?.models ?? []).map((m) => <option key={m} value={m} />)}</datalist></div>
            <div className='flex justify-end gap-2'><Button variant='ghost' onClick={() => setOpen(false)}>انصراف</Button><Button onClick={save} disabled={!!busy || !f.name.trim()}>{busy === 'save' ? '…' : 'ذخیره'}</Button></div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
