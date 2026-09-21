'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ApiError, endpoints, type ProviderConfig } from '@/lib/api/client';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

export const WRITER_KINDS = [
  { kind: 'anthropic', label: 'Claude', role: 'نویسندهٔ اصلی', prefix: 'sk-ant-', console: 'https://platform.claude.com/settings/keys', defaultTtl: '7' },
  { kind: 'xai', label: 'Grok', role: 'نویسندهٔ جایگزین', prefix: 'xai-', console: 'https://console.x.ai', defaultTtl: '0' },
  { kind: 'google', label: 'Gemini', role: 'نویسندهٔ رایگان (Google AI Studio)', prefix: 'AIza', console: 'https://aistudio.google.com/apikey', defaultTtl: '0' }
] as const;
const fa = new Intl.NumberFormat('fa-IR');

export function keyStatus(p?: ProviderConfig): { text: string; tone: 'ok' | 'warn' | 'bad' } {
  if (!p || !p.has_key) return { text: 'کلید ثبت نشده', tone: 'bad' };
  if (p.key_expired) return { text: 'کلید منقضی شده', tone: 'bad' };
  if (p.last_test && !p.last_test.ok) return { text: 'اتصال ناموفق', tone: 'warn' };
  if (typeof p.key_days_left === 'number') return { text: `${fa.format(Math.ceil(p.key_days_left))} روز مانده`, tone: p.key_days_left < 2 ? 'warn' : 'ok' };
  return { text: 'متصل', tone: 'ok' };
}
export const TONE_COLOR = { ok: '#16a34a', warn: '#f59e0b', bad: '#dc2626' } as const;

export function AiKeysDialog({ open, onClose, onChanged }: { open: boolean; onClose: () => void; onChanged?: () => void }) {
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [ttl, setTtl] = useState<Record<string, string>>(Object.fromEntries(WRITER_KINDS.map((k) => [k.kind, k.defaultTtl])));
  const [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(() => endpoints.providerConfigs().then(setProviders).catch(() => setProviders([])), []);
  useEffect(() => { if (open) load(); }, [open, load]);
  const byKind = (kind: string) => providers.find((p) => p.kind === kind);

  async function save(kind: string) {
    const key = (keys[kind] ?? '').trim();
    if (key.length < 8) { toast.error('کلید را کامل وارد کنید'); return; }
    setBusy(kind);
    try {
      const existing = byKind(kind);
      const days = Number(ttl[kind] || 0);
      const body: Record<string, unknown> = days > 0 ? { api_key: key, key_ttl_days: days } : { api_key: key };
      const saved = existing ? await endpoints.updateProvider(existing.id, body) : await endpoints.createProvider({ name: kind, kind, ...body });
      setKeys((k) => ({ ...k, [kind]: '' }));
      if (!existing) await endpoints.applyRecommendedRoutes(saved.id).catch(() => null);
      await test(saved.id, true);
      await load(); onChanged?.();
    } catch (e) { toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)); } finally { setBusy(null); }
  }
  async function test(pid: number, afterSave = false) {
    const t = await endpoints.testProvider(pid).catch(() => null);
    if (t?.ok) { toast.success(t.message); await endpoints.aiModelsSync(pid).catch(() => null); return; }
    const msg = t?.message ?? 'تست اتصال انجام نشد';
    const network = /Connect|Timeout|اتصال برقرار نشد|proxy|Proxy/i.test(msg);
    toast.warning(`${afterSave ? 'کلید ذخیره شد ولی ' : ''}${msg}${network ? ' — به‌نظر مشکل شبکه است: اینترنت یا VPN این سیستم را بررسی کنید (Brain اگر تونل SSH بسته باشد خودش مستقیم وصل می‌شود)؛ بعد «تست» را دوباره بزنید.' : ''}`, { duration: 9000 });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent className='sm:max-w-xl' dir='rtl'>
        <DialogHeader>
          <DialogTitle>کلیدهای نویسندهٔ هوش مصنوعی</DialogTitle>
          <DialogDescription>کلید را هر بار همین‌جا وارد کنید؛ رمزنگاری‌شده ذخیره می‌شود و هرگز نمایش داده نمی‌شود. کلید موقت (مثلاً ۷ روزه) بعد از انقضا خودکار کنار گذاشته می‌شود و نوشتن به نویسندهٔ جایگزین می‌رود.</DialogDescription>
        </DialogHeader>
        <div className='grid gap-4'>
          {WRITER_KINDS.map((k) => {
            const p = byKind(k.kind);
            const st = keyStatus(p);
            return (
              <div key={k.kind} className='rounded-lg border p-3'>
                <div className='mb-2 flex flex-wrap items-center gap-2 text-sm'>
                  <b>{k.label}</b><span className='text-muted-foreground text-xs'>{k.role}</span>
                  <Badge style={{ background: TONE_COLOR[st.tone] }}>{st.text}</Badge>
                  {p?.key_hint && <span className='text-muted-foreground text-[11px]' dir='ltr'>…{p.key_hint}</span>}
                  {p?.has_key && !p.key_expired && <Button type='button' size='sm' variant='ghost' className='h-6 px-2 text-[11px]' disabled={!!busy} onClick={() => { setBusy(`test-${k.kind}`); test(p.id).finally(() => { setBusy(null); load(); }); }}>{busy === `test-${k.kind}` ? '…' : 'تست'}</Button>}
                  {p?.last_test?.tested_at && <span className='text-muted-foreground ms-auto text-[10px]' dir='ltr'>{String(p.last_test.tested_at).slice(0, 16).replace('T', ' ')}</span>}
                </div>
                <form className='grid gap-2 sm:grid-cols-[1fr_auto_auto]' onSubmit={(e) => { e.preventDefault(); save(k.kind); }}>
                  <Input type='password' autoComplete='off' value={keys[k.kind] ?? ''} onChange={(e) => setKeys((s) => ({ ...s, [k.kind]: e.target.value }))} placeholder={`${k.prefix}…`} dir='ltr' disabled={!!busy} />
                  <NativeSelect value={ttl[k.kind]} onChange={(e) => setTtl((s) => ({ ...s, [k.kind]: e.target.value }))} className='w-32' disabled={!!busy}>
                    <NativeSelectOption value='7'>۷ روزه</NativeSelectOption>
                    <NativeSelectOption value='30'>۳۰ روزه</NativeSelectOption>
                    <NativeSelectOption value='90'>۹۰ روزه</NativeSelectOption>
                    <NativeSelectOption value='0'>بدون انقضا</NativeSelectOption>
                  </NativeSelect>
                  <Button type='submit' size='sm' disabled={!!busy || !(keys[k.kind] ?? '').trim()}>{busy === k.kind ? 'در حال تست…' : p?.has_key ? 'جایگزینی کلید' : 'ذخیره و تست'}</Button>
                </form>
                <p className='text-muted-foreground mt-1 text-[11px]'>کلید را از <a className='underline' href={k.console} target='_blank' rel='noreferrer' dir='ltr'>{k.console.replace('https://', '')}</a> بگیرید.</p>
              </div>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}
