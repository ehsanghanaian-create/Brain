'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { endpoints, type PhoneReplaceResult, type PhoneScan } from '@/lib/api/client';
import { IconAlertTriangle, IconCheck, IconCopy, IconPhone, IconSearch, IconWand } from '@tabler/icons-react';
import { useState } from 'react';
import { toast } from 'sonner';

const fa = new Intl.NumberFormat('fa-IR');
const FIELD_FA: Record<string, string> = { content_html: 'متن صفحه', title: 'عنوان', excerpt: 'خلاصه' };
const STATUS_FA: Record<string, string> = {
  would_change: 'آمادهٔ تغییر',
  changed: 'تغییر کرد',
  read_failed: 'خواندن ناموفق',
  write_failed: 'نوشتن ناموفق',
  nothing_in_rest: 'در نسخهٔ قابل‌ویرایش نبود',
  error: 'خطا'
};

/** «شمارهٔ تماس» — شمارهٔ فعلی را روی سایت پیدا می‌کند، پیش‌نمایش می‌دهد و با تأیید شما از همین‌جا عوضش می‌کند.
 *  هرچه از راه وردپرس قابل نوشتن نباشد (هدر، المنتور، فایل قالب) صادقانه گزارش و دستورالعملش داده می‌شود. */
export function PhoneTab({ siteId }: { siteId: string }) {
  const [oldPhone, setOldPhone] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [scan, setScan] = useState<PhoneScan | null>(null);
  const [result, setResult] = useState<PhoneReplaceResult | null>(null);
  const [busy, setBusy] = useState<'scan' | 'preview' | 'apply' | null>(null);
  const [confirming, setConfirming] = useState(false);

  const ready = oldPhone.replace(/\D/g, '').length >= 8;
  const bothReady = ready && newPhone.replace(/\D/g, '').length >= 8;

  async function run(kind: 'scan' | 'preview' | 'apply') {
    setBusy(kind);
    try {
      if (kind === 'scan') {
        const s = await endpoints.phoneScan(siteId, oldPhone);
        setScan(s);
        setResult(null);
        toast.success(s.pages_total ? `${fa.format(s.pages_total)} صفحه با این شماره پیدا شد` : 'در صفحه‌های همگام‌شده پیدا نشد');
      } else {
        const r = await endpoints.phoneReplace(siteId, { old_phone: oldPhone, new_phone: newPhone, dry_run: kind === 'preview' });
        setResult(r);
        setConfirming(false);
        if (r.status === 'applied') toast.success(`${fa.format(r.changed)} صفحه روی سایت تغییر کرد`);
        else if (r.status === 'preview') toast.info(`${fa.format(r.pages_targeted)} صفحه آمادهٔ تغییر است`);
        else toast.warning(r.message ?? 'انجام نشد');
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'عملیات ناموفق بود');
    } finally {
      setBusy(null);
    }
  }

  const rows = result?.results ?? scan?.pages.map((p) => ({ wp_id: p.wp_id, url: p.url, title: p.title, hits: p.total, fields: Object.keys(p.hits), status: 'found' })) ?? [];
  const leftover = result?.remaining.template_or_elementor ?? scan?.template.outside_content ?? 0;

  return (
    <div className='space-y-4'>
      <Card>
        <CardHeader>
          <CardTitle className='flex items-center gap-2'><IconPhone className='size-4' /> تغییر شمارهٔ تماس از داخل Brain</CardTitle>
          <CardDescription>
            شمارهٔ قدیمی را جست‌وجو کنید، پیش‌نمایش بگیرید و بعد تغییر دهید. Brain هر جا که از راه وردپرس قابل نوشتن باشد
            (متن، عنوان و خلاصهٔ صفحه‌ها و نوشته‌ها) را خودش عوض می‌کند و هر هفت شکل شماره را می‌گیرد: لاتین، فارسی، با فاصله،
            با خط تیره و شکل اسکیپ‌شدهٔ المنتور.
          </CardDescription>
        </CardHeader>
        <CardContent className='space-y-3'>
          <div className='grid gap-3 sm:grid-cols-2'>
            <div className='space-y-1'>
              <Label htmlFor='ph-old'>شمارهٔ فعلی (قدیمی)</Label>
              <Input id='ph-old' dir='ltr' inputMode='numeric' placeholder='02122477005' value={oldPhone} onChange={(e) => { setOldPhone(e.target.value); setScan(null); setResult(null); }} />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='ph-new'>شمارهٔ جدید</Label>
              <Input id='ph-new' dir='ltr' inputMode='numeric' placeholder='02122144279' value={newPhone} onChange={(e) => { setNewPhone(e.target.value); setResult(null); }} />
            </div>
          </div>
          <div className='flex flex-wrap items-center gap-2'>
            <Button size='sm' variant='outline' onClick={() => run('scan')} disabled={!ready || busy !== null}>
              <IconSearch className='size-3.5' /> {busy === 'scan' ? 'در حال جست‌وجو…' : 'کجاها هست؟'}
            </Button>
            <Button size='sm' variant='outline' onClick={() => run('preview')} disabled={!bothReady || busy !== null}>
              <IconWand className='size-3.5' /> پیش‌نمایش تغییر
            </Button>
            {!confirming ? (
              <Button size='sm' onClick={() => setConfirming(true)} disabled={!bothReady || busy !== null}>
                <IconCheck className='size-3.5' /> تغییر روی سایت
              </Button>
            ) : (
              <span className='flex items-center gap-2 rounded-lg border border-amber-500/50 px-2 py-1 text-xs'>
                <IconAlertTriangle className='size-3.5 text-amber-500' />
                روی سایت واقعی نوشته می‌شود. مطمئنید؟
                <Button size='sm' variant='destructive' onClick={() => run('apply')} disabled={busy !== null}>بله، انجام بده</Button>
                <Button size='sm' variant='ghost' onClick={() => setConfirming(false)}>انصراف</Button>
              </span>
            )}
            {scan && <span className='text-muted-foreground text-xs'>{fa.format(scan.occurrences)} مورد در {fa.format(scan.pages_total)} صفحه</span>}
          </div>
          {scan && (
            <div className='flex flex-wrap gap-1.5 text-[11px]'>
              {scan.forms.map((f) => <span key={f} className='rounded-full border px-2 py-0.5' dir='ltr'>{f}</span>)}
            </div>
          )}
        </CardContent>
      </Card>

      {rows.length > 0 && (
        <Card>
          <CardHeader className='pb-2'>
            <CardTitle className='text-base'>صفحه‌هایی که Brain خودش عوض می‌کند</CardTitle>
            <CardDescription>{result?.status === 'applied' ? `${fa.format(result.changed)} صفحه نوشته شد` : 'هنوز چیزی روی سایت نوشته نشده است'}</CardDescription>
          </CardHeader>
          <CardContent className='p-0'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>صفحه</TableHead>
                  <TableHead>محل</TableHead>
                  <TableHead>تعداد</TableHead>
                  <TableHead>وضعیت</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.wp_id}>
                    <TableCell className='max-w-[22rem] truncate'>
                      <a href={r.url ?? '#'} target='_blank' rel='noreferrer' className='hover:underline'>{r.title || r.url}</a>
                    </TableCell>
                    <TableCell className='text-xs'>{(r.fields ?? []).map((f) => FIELD_FA[f] ?? f).join('، ')}</TableCell>
                    <TableCell className='tabular-nums'>{fa.format(r.hits ?? 0)}</TableCell>
                    <TableCell className='text-xs'>
                      <Badge variant={r.status === 'changed' ? 'default' : r.status?.includes('failed') || r.status === 'error' ? 'destructive' : 'secondary'}>
                        {STATUS_FA[r.status ?? ''] ?? 'پیدا شد'}
                      </Badge>
                      {'message' in r && r.message ? <span className='text-muted-foreground ms-2'>{r.message}</span> : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {(scan || result) && (
        <Card>
          <CardHeader className='pb-2'>
            <CardTitle className='flex items-center gap-2 text-base'><IconAlertTriangle className='size-4 text-amber-500' /> بخشی که از راه وردپرس قابل تغییر نیست</CardTitle>
            <CardDescription>
              {leftover > 0
                ? `${fa.format(leftover)} مورد بیرون از متن صفحه‌ها (هدر، دکمهٔ تماس فوری، دیتای المنتور یا فایل قالب) پیدا شد. اینها را باید روی هاست عوض کرد.`
                : scan?.template.home_read === false
                  ? 'صفحهٔ اصلی سایت خوانده نشد، پس دربارهٔ هدر و قالب نمی‌شود قضاوت کرد.'
                  : 'بیرون از متن صفحه‌ها چیزی پیدا نشد.'}
            </CardDescription>
          </CardHeader>
          {result?.runbook && (
            <CardContent className='space-y-2'>
              <div className='flex items-center gap-2'>
                <Button size='sm' variant='outline' onClick={() => { navigator.clipboard.writeText(result.runbook!).then(() => toast.success('دستورالعمل کپی شد'), () => toast.error('کپی نشد')); }}>
                  <IconCopy className='size-3.5' /> کپی دستورالعمل هاست
                </Button>
                <span className='text-muted-foreground text-xs'>برای اپراتور یا ایجنتی که به دایرکت‌ادمین دسترسی دارد</span>
              </div>
              <textarea readOnly dir='rtl' value={result.runbook} className='bg-muted/40 h-56 w-full rounded-lg border p-2 font-mono text-[11px] leading-6' onFocus={(e) => e.currentTarget.select()} />
            </CardContent>
          )}
        </Card>
      )}

      {result?.status === 'applied' && (
        <p className='text-muted-foreground text-xs'>{result.next_step}</p>
      )}
    </div>
  );
}
