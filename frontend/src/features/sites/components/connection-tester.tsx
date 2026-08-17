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
    </div>
  );
}
