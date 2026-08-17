'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ApiError, endpoints, type ImportResult } from '@/lib/api/client';
import { useState } from 'react';
import { toast } from 'sonner';
import { FIELD_FA } from '../constants';

const FIELDS = ['keyword', 'intent', 'cluster', 'topic', 'volume', 'difficulty', 'priority', 'target_url', 'status', 'notes'];

export function ImportDialog({ siteId, open, onOpenChange, onDone }: { siteId: string; open: boolean; onOpenChange: (o: boolean) => void; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function dryRun(f: File, mp?: Record<string, string>) {
    setBusy(true);
    try {
      const r = await endpoints.importKeywords(siteId, f, { dryRun: true, mapping: mp });
      setPreview(r);
      setMapping(r.mapping);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function commit() {
    if (!file) return;
    setBusy(true);
    try {
      const r = await endpoints.importKeywords(siteId, file, { dryRun: false, mapping });
      toast.success(`ورود انجام شد: ${r.rows_imported} جدید، ${r.rows_updated} به‌روزرسانی، ${r.rows_skipped} ردشده`);
      onOpenChange(false);
      setFile(null); setPreview(null);
      onDone();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const remap = (col: string, field: string) => {
    const mp = { ...mapping };
    Object.keys(mp).forEach((k) => { if (mp[k] === field && k !== col) delete mp[k]; });   // a field maps once
    if (field) mp[col] = field; else delete mp[col];
    setMapping(mp);
    if (file) dryRun(file, mp);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>ورود کلمات کلیدی</DialogTitle>
          <DialogDescription>
            CSV / TSV / Excel (xlsx) یا خروجی Google Sheet (File → Download → CSV/XLSX). ستون‌ها به‌صورت خودکار شناسایی می‌شوند؛ می‌توانید نگاشت را تغییر دهید. ابتدا پیش‌نمایش، سپس تأیید.
            <a className='ms-2 underline' href={`/api/backend/sites/${encodeURIComponent(siteId)}/keywords/template.csv`} target='_blank' rel='noreferrer'>دانلود قالب CSV</a>
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-3'>
          <input
            type='file'
            accept='.csv,.tsv,.txt,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f); setPreview(null);
              if (f) dryRun(f);
            }}
            className='text-sm'
          />
          {busy && <p className='text-muted-foreground text-xs'>در حال پردازش…</p>}
          {preview && (
            <>
              <div className='flex flex-wrap gap-2 text-xs'>
                <Badge variant='outline'>قالب: {preview.format}</Badge>
                <Badge variant='outline'>ردیف‌ها: {preview.rows_total}</Badge>
                <Badge variant={preview.rows_valid ? 'default' : 'destructive'}>معتبر: {preview.rows_valid}</Badge>
                {preview.rows_skipped > 0 && <Badge variant='secondary'>ردشده: {preview.rows_skipped}</Badge>}
                {preview.errors_count > 0 && <Badge variant='destructive'>خطا: {preview.errors_count}</Badge>}
              </div>
              <div className='rounded-md border'>
                <table className='w-full text-xs'>
                  <thead className='bg-muted/50'><tr><th className='p-2 text-start'>ستون فایل</th><th className='p-2 text-start'>فیلد</th></tr></thead>
                  <tbody>
                    {preview.columns.map((col) => (
                      <tr key={col} className='border-t'>
                        <td className='p-2' dir='auto'>{col}</td>
                        <td className='p-2'>
                          <NativeSelect value={mapping[col] ?? ''} onChange={(e) => remap(col, e.target.value)} className='h-8 w-48 text-xs'>
                            <NativeSelectOption value=''>— نادیده —</NativeSelectOption>
                            {FIELDS.map((f) => <NativeSelectOption key={f} value={f}>{FIELD_FA[f]}</NativeSelectOption>)}
                          </NativeSelect>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {preview.errors.length > 0 && (
                <ul className='max-h-24 overflow-y-auto rounded border p-2 text-xs text-destructive'>
                  {preview.errors.slice(0, 20).map((e, i) => <li key={i}>ردیف {e.row}: {e.error}</li>)}
                </ul>
              )}
              {preview.preview.length > 0 && (
                <div className='max-h-56 overflow-auto rounded-md border'>
                  <table className='w-full text-xs'>
                    <thead className='bg-muted/50'><tr>{['keyword', 'intent', 'topic', 'volume', 'priority', 'target_url', 'status'].map((f) => <th key={f} className='p-2 text-start'>{FIELD_FA[f]}</th>)}</tr></thead>
                    <tbody>
                      {preview.preview.slice(0, 15).map((r, i) => (
                        <tr key={i} className='border-t'>
                          <td className='p-2'>{String(r.keyword ?? '')}</td><td className='p-2'>{String(r.intent ?? '—')}</td><td className='p-2'>{String(r.topic ?? '—')}</td>
                          <td className='p-2'>{String(r.volume ?? '—')}</td><td className='p-2'>{String(r.priority ?? '—')}</td>
                          <td className='p-2 truncate' dir='ltr'>{String(r.target_url ?? '—')}</td><td className='p-2'>{String(r.status ?? '')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
          <div className='flex justify-end gap-2'>
            <Button variant='ghost' onClick={() => onOpenChange(false)}>انصراف</Button>
            <Button onClick={commit} disabled={!preview || preview.rows_valid === 0 || busy}>ورود {preview?.rows_valid ?? 0} کلمه کلیدی</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
