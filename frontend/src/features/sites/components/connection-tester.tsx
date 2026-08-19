'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ApiError, endpoints, type ConnectionKind, type ConnectionResult, type GscProperties } from '@/lib/api/client';
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
  onResult
}: {
  siteId: string;
  kind: ConnectionKind;
  label: string;
  hint: string;
  initialValue?: string | null;
  initialResult?: ConnectionResult;
  onResult?: (r: ConnectionResult) => void;
}) {
  const [value, setValue] = useState(initialValue ?? '');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ConnectionResult | undefined>(initialResult);
  const [error, setError] = useState<string | null>(null);
  const [errorDetail, setErrorDetail] = useState<unknown>(null);
  const [gscProps, setGscProps] = useState<GscProperties | null>(null);

  useEffect(() => {
    if (kind !== 'gsc') return;
    endpoints
      .gscProperties()
      .then(setGscProps)
      .catch((e: ApiError) => setGscProps({ status: 'error', message: e.message, properties: [] }));
  }, [kind]);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const r = await endpoints.testConnection(siteId, kind, value || null);
      setResult(r);
      onResult?.(r);
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
        ) : (
          <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder={hint} dir='ltr' className='md:flex-1' />
        )}
        <Button type='button' onClick={run} disabled={busy} variant='secondary'>
          {busy ? 'در حال تست…' : 'تست دسترسی'}
        </Button>
      </div>
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

type DiagStep = { step: string; fa?: string; url?: string; ok?: boolean; status_code?: number | null; ms?: number | null; content_type?: string; error?: string; hint?: string; auth?: string };

/** Detailed, copyable log of what the backend actually did (normalization → requests → responses). Secrets are redacted server-side. */
function DiagnosticsLog({ kind, result, errorDetail }: { kind: ConnectionKind; result?: ConnectionResult; errorDetail?: unknown }) {
  const detail = (result?.detail ?? {}) as Record<string, unknown>;
  const trace = Array.isArray(detail.trace) ? (detail.trace as string[]) : [];
  const diags = Array.isArray(detail.diagnostics) ? (detail.diagnostics as DiagStep[]) : [];
  const rest = Object.fromEntries(Object.entries(detail).filter(([k]) => !['trace', 'diagnostics', 'message'].includes(k)));
  const text = [`kind: ${kind}`, result ? `status: ${result.status} · ok: ${result.ok} · tested_at: ${result.tested_at}` : '', result ? `message: ${result.message}` : '', ...(trace.length ? ['--- trace', ...trace] : []),
    ...(diags.length ? ['--- diagnostics', ...diags.map((d) => `${d.ok ? 'OK ' : 'FAIL'} ${d.step} ${d.url ?? ''} → ${d.status_code ?? d.error ?? '-'}${d.ms != null ? ` (${d.ms}ms)` : ''}${d.hint ? ` · ${d.hint}` : ''}`)] : []),
    Object.keys(rest).length ? `--- detail ${JSON.stringify(rest)}` : '', errorDetail ? `--- api error ${JSON.stringify(errorDetail)}` : ''].filter(Boolean).join('\n');
  return (
    <details className='mt-2 rounded border text-xs'>
      <summary className='cursor-pointer px-2 py-1 font-medium'>جزئیات فنی / لاگ اتصال {trace.length ? `(${trace.length} مرحله)` : ''}</summary>
      <div className='space-y-2 p-2'>
        {diags.length > 0 && (
          <ul className='space-y-1'>
            {diags.map((d) => (
              <li key={d.step} className='flex flex-wrap items-center gap-1'>
                <span className={`inline-block h-2.5 w-2.5 rounded-full ${d.ok ? 'bg-emerald-500' : 'bg-red-500'}`} />
                <span className='font-medium'>{d.fa ?? d.step}</span>
                <span className='text-muted-foreground' dir='ltr'>{d.url}</span>
                <Badge variant='outline' dir='ltr'>{d.status_code ?? d.error ?? '—'}{d.ms != null ? ` · ${d.ms}ms` : ''}</Badge>
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
