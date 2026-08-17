'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Separator } from '@/components/ui/separator';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { ApiError, endpoints, type KeywordDetail, type KeywordsMeta } from '@/lib/api/client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { INTENT_FA, KW_STATUS_FA, OPP_KIND_FA, OPP_STATUS_FA, PRIORITY_FA, num, pct } from '../constants';

export function KeywordEditor({ siteId, kid, meta, onClose, onChanged }: { siteId: string; kid: number | 'new' | null; meta: KeywordsMeta | null; onClose: () => void; onChanged: () => void }) {
  const [d, setD] = useState<KeywordDetail | null>(null);
  const [f, setF] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const open = kid !== null;

  useEffect(() => {
    if (kid === null) return;
    if (kid === 'new') {
      setD(null); setF({ keyword: '', intent: '', topic: '', volume: '', difficulty: '', priority: '', target_url: '', status: 'new', notes: '' });
      return;
    }
    endpoints.keyword(siteId, kid).then((k) => {
      setD(k);
      setF({ keyword: k.keyword, intent: k.intent ?? '', topic: k.topic ?? '', volume: k.volume?.toString() ?? '', difficulty: k.difficulty?.toString() ?? '',
             priority: k.priority ?? '', target_url: k.target_url ?? '', status: k.status, notes: k.notes ?? '' });
    }).catch((e) => toast.error(e instanceof ApiError ? e.message : String(e)));
  }, [siteId, kid]);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setF((s) => ({ ...s, [k]: e.target.value }));

  async function save() {
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        keyword: f.keyword.trim(), intent: f.intent || null, topic: f.topic || null, volume: f.volume ? Number(f.volume) : null,
        difficulty: f.difficulty ? Number(f.difficulty) : null, priority: f.priority || null, target_url: f.target_url || null, status: f.status || 'new', notes: f.notes || null
      };
      if (kid === 'new') await endpoints.createKeyword(siteId, body);
      else if (typeof kid === 'number') {
        const patch = Object.fromEntries(Object.entries(body).filter(([, v]) => v !== null));
        await endpoints.updateKeyword(siteId, kid, patch);
      }
      toast.success('ذخیره شد'); onChanged(); onClose();
    } catch (e) {
      toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));
    } finally { setBusy(false); }
  }
  async function remove() {
    if (typeof kid !== 'number' || !confirm('این کلمه کلیدی و فرصت‌های آن حذف شود؟')) return;
    await endpoints.deleteKeyword(siteId, kid); toast.success('حذف شد'); onChanged(); onClose();
  }

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side='left' className='w-full overflow-y-auto p-4 sm:max-w-md' dir='rtl'>
        <SheetHeader className='p-0'>
          <SheetTitle>{kid === 'new' ? 'افزودن کلمه کلیدی' : d?.keyword ?? '…'}</SheetTitle>
          <SheetDescription>{kid === 'new' ? 'ورودی دستی' : d?.source ?? ''}</SheetDescription>
        </SheetHeader>
        <div className='grid gap-3 py-2 text-sm'>
          <div className='grid gap-1.5'><Label>کلمه کلیدی</Label><Input value={f.keyword ?? ''} onChange={set('keyword')} /></div>
          <div className='grid grid-cols-2 gap-2'>
            <div className='grid gap-1.5'><Label>اینتنت</Label>
              <NativeSelect value={f.intent ?? ''} onChange={set('intent')}><NativeSelectOption value=''>—</NativeSelectOption>{(meta?.intents ?? Object.keys(INTENT_FA)).map((i) => <NativeSelectOption key={i} value={i}>{INTENT_FA[i] ?? i}</NativeSelectOption>)}</NativeSelect></div>
            <div className='grid gap-1.5'><Label>اولویت</Label>
              <NativeSelect value={f.priority ?? ''} onChange={set('priority')}><NativeSelectOption value=''>—</NativeSelectOption>{(meta?.priorities ?? Object.keys(PRIORITY_FA)).map((p) => <NativeSelectOption key={p} value={p}>{PRIORITY_FA[p] ?? p}</NativeSelectOption>)}</NativeSelect></div>
            <div className='grid gap-1.5'><Label>حجم جست‌وجو</Label><Input type='number' value={f.volume ?? ''} onChange={set('volume')} dir='ltr' /></div>
            <div className='grid gap-1.5'><Label>سختی (۰–۱۰۰)</Label><Input type='number' value={f.difficulty ?? ''} onChange={set('difficulty')} dir='ltr' /></div>
            <div className='grid gap-1.5'><Label>وضعیت</Label>
              <NativeSelect value={f.status ?? 'new'} onChange={set('status')}>{(meta?.statuses ?? Object.keys(KW_STATUS_FA)).map((s) => <NativeSelectOption key={s} value={s}>{KW_STATUS_FA[s] ?? s}</NativeSelectOption>)}</NativeSelect></div>
            <div className='grid gap-1.5'><Label>موضوع</Label><Input value={f.topic ?? ''} onChange={set('topic')} placeholder={d?.cluster?.topic ?? ''} /></div>
          </div>
          <div className='grid gap-1.5'><Label>صفحه هدف</Label><Input value={f.target_url ?? ''} onChange={set('target_url')} dir='ltr' placeholder={d?.gsc?.top_page ?? 'https://…'} /></div>
          <div className='grid gap-1.5'><Label>یادداشت</Label><Textarea rows={2} value={f.notes ?? ''} onChange={set('notes')} /></div>
          <div className='flex items-center justify-between'>
            <div>{typeof kid === 'number' && <Button variant='ghost' size='sm' onClick={remove} className='text-destructive'>حذف</Button>}</div>
            <Button onClick={save} disabled={busy || !(f.keyword ?? '').trim()}>{busy ? 'در حال ذخیره…' : 'ذخیره'}</Button>
          </div>
          {d && (
            <>
              <Separator />
              <section>
                <h4 className='mb-1 text-xs font-semibold opacity-70'>Search Console</h4>
                {d.gsc ? (
                  <div className='grid grid-cols-4 gap-2 text-center'>
                    <Metric l='جایگاه' v={num(d.gsc.position, 1)} /><Metric l='CTR' v={pct(d.gsc.ctr)} /><Metric l='ایمپرشن' v={num(d.gsc.impressions)} /><Metric l='کلیک' v={num(d.gsc.clicks)} />
                  </div>
                ) : <p className='text-muted-foreground text-xs'>داده‌ای در Search Console برای این کلمه پیدا نشد.</p>}
                {d.gsc_pages.length > 0 && (
                  <ul className='mt-2 space-y-0.5 text-xs' dir='ltr'>
                    {d.gsc_pages.map((p, i) => <li key={i} className='flex justify-between gap-2'><span className='truncate'>{p.page}</span><span className='shrink-0'>#{Number(p.position).toFixed(1)} · {p.impressions} · {p.clicks}</span></li>)}
                  </ul>
                )}
              </section>
              <Separator />
              <section>
                <h4 className='mb-1 text-xs font-semibold opacity-70'>فرصت‌ها ({d.opportunities.length})</h4>
                {d.opportunities.length === 0 ? <p className='text-muted-foreground text-xs'>فرصتی ثبت نشده — «تحلیل فرصت‌ها» را اجرا کنید.</p> : (
                  <ul className='space-y-1'>
                    {d.opportunities.map((o) => (
                      <li key={o.id} className='rounded border p-2 text-xs'>
                        <div className='flex items-center justify-between'><Badge>{OPP_KIND_FA[o.kind] ?? o.kind}</Badge><span className='text-muted-foreground'>{num(o.score, 2)} · {OPP_STATUS_FA[o.status]}</span></div>
                        <div className='mt-1'>{o.reason}</div>
                        {o.target_url && <div className='text-muted-foreground truncate' dir='ltr'>{o.target_url}</div>}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
              <Link href={`/dashboard/graph?site=${siteId}`} className='text-xs underline'>مشاهده در گراف دانش</Link>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Metric({ l, v }: { l: string; v: string }) {
  return <div className='rounded border p-1'><div className='text-muted-foreground text-[10px]'>{l}</div><div className='font-semibold tabular-nums'>{v}</div></div>;
}
