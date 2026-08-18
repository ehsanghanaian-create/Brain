'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ApiError, endpoints, type AnalyticsOverview, type AnalyticsSettings, type ContentInsight, type ScoringSettings } from '@/lib/api/client';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { faNum } from '../constants';

const CAT_FA: Record<string, string> = { heading_structure: 'ساختار سرفصل', faq: 'FAQ', entity_coverage: 'پوشش موجودیت', cta: 'CTA', local_seo: 'سئوی محلی', title: 'عنوان', length: 'طول محتوا' };
const DIM_FA: Record<string, string> = { intent: 'اینتنت', keywords: 'کلمات کلیدی', entities: 'موجودیت‌ها', headings: 'سرفصل‌ها', links: 'لینک داخلی', cta: 'CTA', completeness: 'کامل بودن' };
const pct = (v: number | null | undefined) => (typeof v === 'number' ? `${(v * 100).toFixed(1)}٪` : '—');

/** Analytics feedback (GSC → patterns) + human-confirmed insights → Site Brain memory + scoring/gate settings. */
export function AnalyticsPanel({ siteId, onOpen }: { siteId: string; onOpen: (cid: number) => void }) {
  const [ov, setOv] = useState<AnalyticsOverview | null>(null);
  const [ins, setIns] = useState<ContentInsight[]>([]);
  const [scoring, setScoring] = useState<ScoringSettings | null>(null);
  const [an, setAn] = useState<AnalyticsSettings | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [insFilter, setInsFilter] = useState('new');

  const load = useCallback(async () => {
    try {
      const [o, i, s, a] = await Promise.all([endpoints.analyticsOverview(siteId), endpoints.contentInsights(siteId, insFilter || undefined), endpoints.scoringSettings(siteId), endpoints.analyticsSettings(siteId)]);
      setOv(o); setIns(i); setScoring(s); setAn(a);
    } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
  }, [siteId, insFilter]);
  useEffect(() => { load(); }, [load]);

  const run = async (name: string, fn: () => Promise<unknown>, msg: (r: any) => string) => {
    setBusy(name);
    try { const r = await fn(); toast.success(msg(r)); load(); } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); } finally { setBusy(null); }
  };
  async function setInsight(id: number, status: string) {
    try { await endpoints.setInsightStatus(siteId, id, status); toast.success(status === 'accepted' ? 'الگو به حافظه سایت (Site Brain) اضافه شد' : 'رد شد'); load(); } catch (e) { toast.error(String(e)); }
  }
  async function saveScoring(patch: Partial<ScoringSettings>) {
    try { setScoring(await endpoints.putScoringSettings(siteId, patch)); toast.success('تنظیمات امتیازدهی ذخیره شد'); } catch (e) { toast.error(String(e)); }
  }
  async function saveAn(patch: Partial<AnalyticsSettings>) {
    try { setAn(await endpoints.putAnalyticsSettings(siteId, patch)); toast.success('آستانه‌های تحلیل ذخیره شد'); } catch (e) { toast.error(String(e)); }
  }

  return (
    <div className='grid gap-4'>
      <Card>
        <CardHeader>
          <CardTitle className='flex flex-wrap items-center justify-between gap-2'>عملکرد محتوا (Search Console، ۲۸ روز)
            <span className='flex gap-2'>
              <Button size='sm' variant='secondary' disabled={!!busy} onClick={() => run('snap', () => endpoints.analyticsSnapshot(siteId), (r) => `${r.snapshots} اسنپ‌شات برای ${r.items} محتوا (${r.source})`)}>{busy === 'snap' ? '…' : 'گرفتن اسنپ‌شات'}</Button>
              <Button size='sm' disabled={!!busy} onClick={() => run('learn', () => endpoints.analyticsLearn(siteId), (r) => `${r.samples} نمونه، ${r.insights.length} الگو (${r.skipped.young} محتوای جوان رد شد)`)}>{busy === 'learn' ? '…' : 'یادگیری الگوها'}</Button>
            </span>
          </CardTitle>
          <CardDescription>فقط از داده واقعی GSC؛ الگو فقط وقتی ساخته می‌شود که نمونه به آستانه‌ها برسد (حداقل {an ? faNum.format(an.min_impressions) : '—'} ایمپرشن، {an ? faNum.format(an.min_clicks) : '—'} کلیک، {an ? faNum.format(an.min_age_days) : '—'} روز عمر). هیچ وزنی خودکار تغییر نمی‌کند.</CardDescription>
        </CardHeader>
        <CardContent>
          {ov && (
            <div className='mb-2 flex flex-wrap gap-3 text-xs'>
              <span>محتواهای دارای داده: <b>{faNum.format(ov.totals.contents)}</b></span><span>کلیک: <b>{faNum.format(ov.totals.clicks)}</b></span><span>ایمپرشن: <b>{faNum.format(ov.totals.impressions)}</b></span><span>CTR: <b>{pct(ov.totals.ctr)}</b></span>
            </div>
          )}
          <div className='overflow-x-auto rounded-md border'>
            <Table>
              <TableHeader><TableRow><TableHead>عنوان</TableHead><TableHead>وضعیت</TableHead><TableHead>کلیک</TableHead><TableHead>ایمپرشن</TableHead><TableHead>CTR</TableHead><TableHead>جایگاه</TableHead><TableHead>Δ نسبت به اسنپ‌شات قبلی</TableHead><TableHead>کوئری‌های برتر</TableHead></TableRow></TableHeader>
              <TableBody>
                {ov?.rows.map((r) => (
                  <TableRow key={r.content_id} className='cursor-pointer' onClick={() => onOpen(r.content_id)}>
                    <TableCell className='font-medium'>{r.title}<div className='text-muted-foreground truncate text-[10px]' dir='ltr'>{r.url}</div></TableCell>
                    <TableCell><Badge variant='outline'>{r.status}</Badge></TableCell>
                    <TableCell className='tabular-nums'>{faNum.format(r.clicks)}</TableCell><TableCell className='tabular-nums'>{faNum.format(r.impressions)}</TableCell><TableCell>{pct(r.ctr)}</TableCell><TableCell className='tabular-nums'>{r.position ?? '—'}</TableCell>
                    <TableCell className='text-xs' dir='ltr'>{r.delta && Object.keys(r.delta).length ? `clicks ${r.delta.clicks ?? 0 >= 0 ? '+' : ''}${r.delta.clicks ?? 0} · pos ${r.delta.position ?? '—'}` : '—'}</TableCell>
                    <TableCell className='text-xs'>{r.top_queries.map((q) => q.query).join('، ')}</TableCell>
                  </TableRow>
                ))}
                {ov && ov.rows.length === 0 && <TableRow><TableCell colSpan={8} className='text-muted-foreground text-center'>هنوز اسنپ‌شاتی نیست — محتوای منتشرشده با URL لازم است؛ سپس «گرفتن اسنپ‌شات».</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className='flex items-center justify-between'>الگوهای یادگرفته‌شده (حافظه دانش محتوا)
            <NativeSelect value={insFilter} onChange={(e) => setInsFilter(e.target.value)} className='h-8 w-36 text-xs'><NativeSelectOption value='new'>جدید</NativeSelectOption><NativeSelectOption value='accepted'>پذیرفته</NativeSelectOption><NativeSelectOption value='dismissed'>ردشده</NativeSelectOption><NativeSelectOption value=''>همه</NativeSelectOption></NativeSelect>
          </CardTitle>
          <CardDescription>الگو ← تأیید شما ← ذخیره در حافظه Site Brain (successful_patterns) و استفاده در بریف/بازبینی‌های بعدی. وزن امتیازدهی تغییر نمی‌کند.</CardDescription>
        </CardHeader>
        <CardContent className='grid gap-2 md:grid-cols-2'>
          {ins.map((x) => (
            <div key={x.id} className='rounded-md border p-2 text-sm'>
              <div className='flex items-center gap-2'><Badge variant='outline'>{CAT_FA[x.category] ?? x.category}</Badge><Badge variant='secondary'>{x.metric === 'ctr' ? 'CTR' : 'جایگاه'}</Badge><span className='text-muted-foreground ms-auto text-xs'>اطمینان {x.confidence != null ? Math.round(x.confidence * 100) : '—'}٪</span></div>
              <div className='mt-1'>{x.message_fa}</div>
              <div className='text-muted-foreground mt-1 text-xs' dir='ltr'>effect {x.effect > 0 ? '+' : ''}{x.effect} · n={x.n} · {x.impressions} imp · {x.clicks} clk</div>
              <div className='mt-2 flex gap-1'>
                {x.status === 'new' ? (<><Button size='sm' onClick={() => setInsight(x.id, 'accepted')}>تأیید و ذخیره در حافظه</Button><Button size='sm' variant='ghost' onClick={() => setInsight(x.id, 'dismissed')}>رد</Button></>) : <Badge variant='outline'>{x.status === 'accepted' ? `پذیرفته${x.memory_pattern_ref ? ' · در حافظه' : ''}` : 'ردشده'}</Badge>}
              </div>
            </div>
          ))}
          {ins.length === 0 && <p className='text-muted-foreground text-sm md:col-span-2'>الگویی نیست — با داده کافی، «یادگیری الگوها» را اجرا کنید.</p>}
        </CardContent>
      </Card>

      <div className='grid gap-4 lg:grid-cols-2'>
        <Card>
          <CardHeader><CardTitle>تنظیمات امتیازدهی و دروازه بازبینی</CardTitle><CardDescription>وزن ابعاد (جمع دلخواه)، آستانه‌ها و حالت دروازه. حالت «سخت‌گیرانه» تأیید بدون پیش‌نویس آماده را مسدود می‌کند.</CardDescription></CardHeader>
          <CardContent className='grid gap-2 text-sm'>
            {scoring && (
              <>
                <div className='grid grid-cols-2 gap-2 md:grid-cols-4'>
                  {Object.entries(scoring.weights).map(([k, v]) => (
                    <div key={k} className='grid gap-1'><Label className='text-xs'>{DIM_FA[k] ?? k}</Label><Input type='number' defaultValue={v} onBlur={(e) => Number(e.target.value) !== v && saveScoring({ weights: { [k]: Number(e.target.value) } })} dir='ltr' className='h-8' /></div>
                  ))}
                </div>
                <div className='grid grid-cols-3 gap-2'>
                  <div className='grid gap-1'><Label className='text-xs'>آستانه «آماده»</Label><Input type='number' defaultValue={scoring.thresholds.ready} onBlur={(e) => saveScoring({ thresholds: { ...scoring.thresholds, ready: Number(e.target.value) } })} dir='ltr' className='h-8' /></div>
                  <div className='grid gap-1'><Label className='text-xs'>آستانه «نیاز به بهبود»</Label><Input type='number' defaultValue={scoring.thresholds.needs_work} onBlur={(e) => saveScoring({ thresholds: { ...scoring.thresholds, needs_work: Number(e.target.value) } })} dir='ltr' className='h-8' /></div>
                  <div className='grid gap-1'><Label className='text-xs'>دروازه بازبینی</Label><NativeSelect value={scoring.review_gate} onChange={(e) => saveScoring({ review_gate: e.target.value as 'strict' | 'advisory' })} className='h-8'><NativeSelectOption value='strict'>سخت‌گیرانه (پیش‌فرض)</NativeSelectOption><NativeSelectOption value='advisory'>مشاوره‌ای</NativeSelectOption></NativeSelect></div>
                </div>
                <div className='grid gap-1'><Label className='text-xs'>حداقل لینک داخلی</Label><Input type='number' defaultValue={scoring.min_internal_links} onBlur={(e) => saveScoring({ min_internal_links: Number(e.target.value) })} dir='ltr' className='h-8 w-24' /></div>
              </>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>آستانه‌های تحلیل (محافظه‌کارانه)</CardTitle><CardDescription>هیچ الگویی از نمونه‌های کوچک ساخته نمی‌شود.</CardDescription></CardHeader>
          <CardContent className='grid grid-cols-3 gap-2 text-sm'>
            {an && (
              <>
                <div className='grid gap-1'><Label className='text-xs'>حداقل ایمپرشن</Label><Input type='number' defaultValue={an.min_impressions} onBlur={(e) => saveAn({ min_impressions: Number(e.target.value) })} dir='ltr' className='h-8' /></div>
                <div className='grid gap-1'><Label className='text-xs'>حداقل کلیک</Label><Input type='number' defaultValue={an.min_clicks} onBlur={(e) => saveAn({ min_clicks: Number(e.target.value) })} dir='ltr' className='h-8' /></div>
                <div className='grid gap-1'><Label className='text-xs'>حداقل عمر (روز)</Label><Input type='number' defaultValue={an.min_age_days} onBlur={(e) => saveAn({ min_age_days: Number(e.target.value) })} dir='ltr' className='h-8' /></div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
