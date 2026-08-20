'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ApiError, endpoints, type ConnectionKind, type ConnectionResult, type Ga4Properties, type GscProperties, type WpAuthStatus } from '@/lib/api/client';
import { toast } from 'sonner';
import { queueMessage } from '../wp-sync';
import { useEffect, useState } from 'react';
import { CONNECTION_STATUS_FA } from '../constants';

export function StatusBadge({ status }: { status?: string }) {
  if (!status) return <Badge variant='outline'>تست نشده</Badge>;
  const variant = status === 'ok' ? 'default' : status === 'not_configured' ? 'secondary' : 'destructive';
  return <Badge variant={variant}>{CONNECTION_STATUS_FA[status] ?? status}</Badge>;
}

/**
 * One connection row: input (or dropdown for GSC), "test" button, live result.
 * `onResult` lets the parent (wizard / site page) keep the last result.
 */
export function ConnectionTester({
  siteId,
  kind,
  label,
  hint,
  initialValue,
  initialResult,
  initialAuth,
  onResult
}: {
  siteId: string;
  kind: ConnectionKind;
  label: string;
  hint: string;
  initialValue?: string | null;
  initialResult?: ConnectionResult;
  initialAuth?: WpAuthStatus | null;
  onResult?: (r: ConnectionResult) => void;
}) {
  const [value, setValue] = useState(initialValue ?? '');
  const [wpUser, setWpUser] = useState(initialAuth?.username ?? '');
  const [wpPass, setWpPass] = useState('');
  const [authInfo, setAuthInfo] = useState<WpAuthStatus | null>(initialAuth ?? null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ConnectionResult | undefined>(initialResult);
  const [error, setError] = useState<string | null>(null);
  const [errorDetail, setErrorDetail] = useState<unknown>(null);
  const [gscProps, setGscProps] = useState<GscProperties | null>(null);
  const [ga4Props, setGa4Props] = useState<Ga4Properties | null>(null);

  useEffect(() => {
    if (kind === 'gsc') {
      endpoints
        .gscProperties()
        .then(setGscProps)
        .catch((e: ApiError) => setGscProps({ status: 'error', message: e.message, properties: [] }));
    }
    if (kind === 'ga4') {
      endpoints
        .ga4Properties()
        .then(setGa4Props)
        .catch((e: ApiError) => setGa4Props({ status: 'error', message: e.message, properties: [] }));
    }
  }, [kind]);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const extra = kind === 'wordpress' && wpUser && wpPass ? { wp_username: wpUser.trim(), wp_app_password: wpPass } : undefined;
      const r = await endpoints.testConnection(siteId, kind, value || null, extra);
      setResult(r);
      onResult?.(r);
      if (kind === 'gsc' || kind === 'ga4') {
        const sj = r.detail?.sync_job as { status?: string; job_id?: string | null; error?: string | null } | undefined;
        if (sj) { const m = queueMessage(sj); (m.ok ? toast.success : toast.error)(`${kind === 'gsc' ? 'همگام‌سازی Search Console' : 'همگام‌سازی GA4'}: ${m.text}`); }
      }
      if (kind === 'wordpress') {
        const a = r.detail?.auth as { configured?: boolean; status?: string; username?: string; key_hint?: string; source?: WpAuthStatus['source'] } | undefined;
        if (a?.configured) setAuthInfo({ configured: true, username: a.username ?? wpUser, key_hint: a.key_hint ?? null, source: a.source ?? 'site' });
        setWpPass(''); // never keep the password in component state after the request
        const sj = r.detail?.sync_job as { status?: string; job_id?: string | null; error?: string | null } | undefined;
        if (sj) { const m = queueMessage(sj); (m.ok ? toast.success : toast.error)(`همگام‌سازی وردپرس → گراف: ${m.text}`); }
      }
    } catch (e) {
      setError(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));
      setErrorDetail(e instanceof ApiError ? { code: e.code, status: e.status, details: e.details, request_id: e.requestId } : { error: String(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className='rounded-md border p-3'>
      <div className='mb-2 flex items-center justify-between gap-2'>
        <Label className='font-medium'>{label}</Label>
        <StatusBadge status={result?.status} />
      </div>
      <div className='flex flex-col gap-2 md:flex-row'>
        {kind === 'gsc' && gscProps?.status === 'ok' && gscProps.properties.length > 0 ? (
          <NativeSelect value={value} onChange={(e) => setValue(e.target.value)} className='md:flex-1' dir='ltr'>
            <NativeSelectOption value=''>— انتخاب property —</NativeSelectOption>
            {gscProps.properties.map((p) => (
              <NativeSelectOption key={p.property} value={p.property}>
                {p.property} ({p.permission})
              </NativeSelectOption>
            ))}
          </NativeSelect>
        ) : kind === 'ga4' && ga4Props?.status === 'ok' && ga4Props.properties.length > 0 ? (
          <NativeSelect value={value} onChange={(e) => setValue(e.target.value)} className='md:flex-1' dir='ltr' data-testid='ga4-property-select'>
            <NativeSelectOption value=''>— انتخاب property —</NativeSelectOption>
            {ga4Props.properties.map((p) => (
              <NativeSelectOption key={p.property_id} value={p.property_id}>
                {p.display_name ?? p.property_id} — {p.property_id}{p.account ? ` (${p.account})` : ''}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        ) : (
          <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder={hint} dir='ltr' className='md:flex-1' />
        )}
        <Button type='button' onClick={run} disabled={busy} variant='secondary'>
          {busy ? 'در حال تست…' : 'تست دسترسی'}
        </Button>
      </div>
      {kind === 'wordpress' && (
        <div className='mt-2 rounded-md border border-dashed p-2'>
          <div className='mb-1 flex flex-wrap items-center justify-between gap-2 text-xs'>
            <span className='font-medium'>احراز هویت با Application Password (اختیاری — فقط‌خواندنی)</span>
            {authInfo?.configured ? <Badge variant='default' dir='ltr'>{authInfo.username} · ••••{authInfo.key_hint}{authInfo.source === 'env' ? ' · .env' : ''}</Badge> : <Badge variant='outline'>تنظیم نشده</Badge>}
          </div>
          <div className='flex flex-col gap-2 md:flex-row'>
            <Input value={wpUser} onChange={(e) => setWpUser(e.target.value)} placeholder='نام‌کاربری وردپرس' dir='ltr' className='md:w-48' autoComplete='off' />
            <Input type='password' value={wpPass} onChange={(e) => setWpPass(e.target.value)} placeholder='xxxx xxxx xxxx xxxx xxxx xxxx (Application Password)' dir='ltr' className='md:flex-1' autoComplete='new-password' />
            {authInfo?.configured && authInfo.source !== 'env' && (
              <Button type='button' variant='ghost' size='sm' disabled={busy} onClick={async () => { setBusy(true); try { const r = await endpoints.testConnection(siteId, kind, value || null, { clear_wp_credentials: true }); setResult(r); setAuthInfo({ configured: false, username: null, key_hint: null, source: null }); setWpUser(''); } catch (e) { setError(String(e)); } finally { setBusy(false); } }}>حذف اعتبارنامه</Button>
            )}
          </div>
          <p className='text-muted-foreground mt-1 text-[11px]'>وردپرس → کاربران → پروفایل → Application Passwords → یک رمز بسازید و اینجا وارد کنید. فقط برای «تست دسترسی» ارسال می‌شود؛ با SecretStore رمزنگاری شده ذخیره می‌شود، هرگز در لاگ/پاسخ ظاهر نمی‌شود و SEO Brain هیچ‌گاه در وردپرس چیزی نمی‌نویسد.</p>
        </div>
      )}
      {kind === 'ga4' && ga4Props && ga4Props.status !== 'ok' && (
        <p className='text-muted-foreground mt-1 text-xs'>{ga4Props.message ?? 'فهرست propertyهای GA4 در دسترس نیست — می‌توانید Property ID را دستی وارد کنید'}</p>
      )}
      {kind === 'gsc' && gscProps && gscProps.status !== 'ok' && (
        <p className='text-muted-foreground mt-1 text-xs'>{gscProps.message ?? 'فهرست property های Google در دسترس نیست'} — می‌توانید property را دستی وارد کنید.</p>
      )}
      {result && (
        <p className={`mt-2 text-sm ${result.ok ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}>
          {result.message}
          {result.detail?.permission ? <span dir='ltr'> · {String(result.detail.permission)}</span> : null}
        </p>
      )}
      {error && <p className='text-destructive mt-2 text-sm'>{error}</p>}
      {(result || error) && <DiagnosticsLog kind={kind} result={result} errorDetail={errorDetail} />}
    </div>
  );
}

type DiagStep = { step: string; stage?: 'public' | 'auth'; fa?: string; url?: string; ok?: boolean | null; status_code?: number | null; ms?: number | null; content_type?: string; error?: string; hint?: string; skipped?: boolean; username?: string };
const AUTH_FA: Record<string, string> = { ok: 'متصل — کاربر شناسایی شد', not_authorized: 'نام‌کاربری یا Application Password اشتباه است (401)', forbidden: 'دسترسی رد شد — مجوز کاربر یا افزونه امنیتی (403)', timeout: 'مشکل اتصال (timeout)', error: 'خطا', not_configured: 'بدون احراز هویت (اختیاری)' };

/** Detailed, copyable log of what the backend actually did (normalization → requests → responses). Secrets are redacted server-side. */
function DiagnosticsLog({ kind, result, errorDetail }: { kind: ConnectionKind; result?: ConnectionResult; errorDetail?: unknown }) {
  const detail = (result?.detail ?? {}) as Record<string, unknown>;
  const trace = Array.isArray(detail.trace) ? (detail.trace as string[]) : [];
  const diags = Array.isArray(detail.diagnostics) ? (detail.diagnostics as DiagStep[]) : [];
  const rest = Object.fromEntries(Object.entries(detail).filter(([k]) => !['trace', 'diagnostics', 'message'].includes(k)));
  const text = [`kind: ${kind}`, result ? `status: ${result.status} · ok: ${result.ok} · tested_at: ${result.tested_at}` : '', result ? `message: ${result.message}` : '', ...(trace.length ? ['--- trace', ...trace] : []),
    ...(diags.length ? ['--- diagnostics', ...diags.map((d) => `${d.skipped ? 'SKIP' : d.ok ? 'OK  ' : 'FAIL'} [${d.stage ?? '-'}] ${d.step} ${d.url ?? ''} → ${d.status_code ?? d.error ?? '-'}${d.ms != null ? ` (${d.ms}ms)` : ''}${d.hint ? ` · ${d.hint}` : ''}`)] : []),
    Object.keys(rest).length ? `--- detail ${JSON.stringify(rest)}` : '', errorDetail ? `--- api error ${JSON.stringify(errorDetail)}` : ''].filter(Boolean).join('\n');
  return (
    <details className='mt-2 rounded border text-xs'>
      <summary className='cursor-pointer px-2 py-1 font-medium'>جزئیات فنی / لاگ اتصال {trace.length ? `(${trace.length} مرحله)` : ''}</summary>
      <div className='space-y-2 p-2'>
        {kind === 'wordpress' && diags.length > 0 && (() => { const pub = diags.filter((d) => d.stage === 'public'); const au = diags.find((d) => d.stage === 'auth'); const a = (detail.auth ?? {}) as { status?: string; message?: string; user_name?: string; roles?: string[] };
          return (
            <div className='grid gap-1 sm:grid-cols-2'>
              <div className='rounded border p-2'><div className='text-muted-foreground mb-1'>مرحله ۱ — REST API عمومی</div><div className='flex items-center gap-1'><span className={`inline-block h-2.5 w-2.5 rounded-full ${pub.every((d) => d.ok) ? 'bg-emerald-500' : 'bg-red-500'}`} />{pub.every((d) => d.ok) ? 'OK — وردپرس شناسایی شد' : 'ناموفق'}</div></div>
              <div className='rounded border p-2'><div className='text-muted-foreground mb-1'>مرحله ۲ — احراز هویت (Application Password)</div><div className='flex items-center gap-1'><span className={`inline-block h-2.5 w-2.5 rounded-full ${au?.skipped ? 'bg-slate-400' : au?.ok ? 'bg-emerald-500' : 'bg-red-500'}`} />{au?.skipped ? 'اجرا نشد (اعتبارنامه وارد نشده)' : `${AUTH_FA[a.status ?? ''] ?? a.message ?? '—'}${a.user_name ? ` · ${a.user_name}` : ''}${a.roles?.length ? ` (${a.roles.join(', ')})` : ''}`}</div></div>
            </div>
          ); })()}
        {diags.length > 0 && (
          <ul className='space-y-1'>
            {diags.map((d) => (
              <li key={d.step} className='flex flex-wrap items-center gap-1'>
                <span className={`inline-block h-2.5 w-2.5 rounded-full ${d.skipped ? 'bg-slate-400' : d.ok ? 'bg-emerald-500' : 'bg-red-500'}`} />
                <span className='font-medium'>{d.fa ?? d.step}</span>
                <span className='text-muted-foreground' dir='ltr'>{d.url}</span>
                <Badge variant='outline' dir='ltr'>{d.skipped ? 'skipped' : (d.status_code ?? d.error ?? '—')}{d.ms != null ? ` · ${d.ms}ms` : ''}</Badge>
                {d.hint && <span className='text-muted-foreground w-full ps-4'>{d.hint}</span>}
              </li>
            ))}
          </ul>
        )}
        {trace.length > 0 && <pre className='bg-muted max-h-56 overflow-auto rounded p-2 text-[11px] leading-5 whitespace-pre-wrap' dir='ltr'>{trace.join('\n')}</pre>}
        {Object.keys(rest).length > 0 && <pre className='bg-muted max-h-40 overflow-auto rounded p-2 text-[11px]' dir='ltr'>{JSON.stringify(rest, null, 1)}</pre>}
        {!!errorDetail && <pre className='bg-muted max-h-40 overflow-auto rounded p-2 text-[11px] text-destructive' dir='ltr'>{JSON.stringify(errorDetail, null, 1)}</pre>}
        <Button type='button' size='sm' variant='ghost' onClick={() => { navigator.clipboard.writeText(text); }}>کپی لاگ</Button>
      </div>
    </details>
  );
}
