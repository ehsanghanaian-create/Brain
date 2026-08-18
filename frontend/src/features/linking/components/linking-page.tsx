'use client';

import { KpiCard } from '@/components/seo-brain/kpi-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ApiError, endpoints, type LinkPageStat, type LinkPattern, type LinkSuggestion, type LinkSummary, type Site } from '@/lib/api/client';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

const fa = new Intl.NumberFormat('fa-IR');
const CONF: Record<string, { fa: string; color: string; range: string }> = {
  high: { fa: 'اولویت بالا', color: '#16a34a', range: '۰٫۸۰+' },
  recommended: { fa: 'توصیه‌شده', color: '#2563eb', range: '۰٫۶۰–۰٫۸۰' },
  low: { fa: 'اطمینان کم', color: '#f59e0b', range: '۰٫۴۵–۰٫۶۰' }
};
const STAGE_FA: Record<string, string> = { informational: 'اطلاعاتی', commercial: 'تجاری', service: 'خدمت', conversion: 'تبدیل', hub: 'هاب', unknown: 'نامشخص' };
const COMP_FA: Record<string, string> = { topic: 'موضوع', entities: 'موجودیت', intent: 'سفر کاربر', authority: 'اعتبار', anchor: 'انکر' };
const STATUS_FA: Record<string, string> = { new: 'جدید', accepted: 'پذیرفته', dismissed: 'ردشده', done: 'انجام‌شده' };
const FLAG_FA: Record<string, string> = { orphan: 'یتیم', nav_only_inbound: 'فقط ناوبری', low_inbound: 'ورودی کم', single_source: 'یک منبع', generic_anchors: 'انکر عمومی', over_optimized_anchor: 'انکر تکراری', no_outbound_body: 'بدون خروجی بدنه', links_to_noindex: 'لینک به noindex', too_many_outbound: 'خروجی زیاد', not_indexable: 'غیرقابل ایندکس' };
const healthColor = (h: number) => (h >= 70 ? '#16a34a' : h >= 40 ? '#f59e0b' : '#dc2626');

export function LinkingPage({ sites, initialSiteId }: { sites: Site[]; initialSiteId: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [summary, setSummary] = useState<LinkSummary | null>(null);
  const [sugg, setSugg] = useState<{ items: LinkSuggestion[]; total: number } | null>(null);
  const [filters, setFilters] = useState({ status: 'new', kind: '', confidence: '', q: '' });
  const [pages, setPages] = useState<LinkPageStat[]>([]);
  const [pageFlag, setPageFlag] = useState('orphan');
  const [weak, setWeak] = useState<LinkPageStat[]>([]);
  const [patterns, setPatterns] = useState<LinkPattern[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [anchorEdit, setAnchorEdit] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, g, p, w, pt] = await Promise.all([
        endpoints.linksSummary(siteId), endpoints.linkSuggestions(siteId, { ...filters, limit: 200, kind: filters.kind || undefined, status: filters.status || undefined }),
        endpoints.linkPages(siteId, { flag: pageFlag, limit: 100 }),
        endpoints.linkPages(siteId, { sort: 'health_score', order: 'asc', limit: 60 }),
        endpoints.linkPatterns(siteId)
      ]);
      setSummary(s); setSugg(g); setPages(p.items); setWeak(w.items.filter((x) => x.flags.some((f) => ['nav_only_inbound', 'single_source', 'generic_anchors', 'over_optimized_anchor', 'low_inbound', 'links_to_noindex', 'no_outbound_body'].includes(f)))); setPatterns(pt);
    } catch (e) { setError(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)); }
  }, [siteId, filters, pageFlag]);
  useEffect(() => { load(); }, [load]);

  async function analyze() {
    setBusy('analyze');
    try {
      const r = await endpoints.linksAnalyze(siteId);
      if (r.mode === 'job') toast.info(`تحلیل در پس‌زمینه شروع شد (job ${r.run_id}) — چند لحظه بعد صفحه را تازه کنید`);
      else toast.success(`تحلیل انجام شد: ${r.suggestions} پیشنهاد (${Object.entries(r.by_confidence ?? {}).map(([k, v]) => `${CONF[k]?.fa ?? k} ${v}`).join('، ')})، ${r.supports_edges} رابطه SUPPORTS، ${r.stats?.orphans ?? 0} صفحه یتیم`);
      load();
    } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); } finally { setBusy(null); }
  }
  async function setStatus(s: LinkSuggestion, status: string) {
    try { await endpoints.setLinkSuggestion(siteId, s.id, { status, anchor: anchorEdit[s.id] || undefined }); toast.success(`${STATUS_FA[status]}: «${anchorEdit[s.id] || s.anchor}»`); load(); }
    catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
  }
  async function contentTask(s: LinkSuggestion) {
    const title = prompt('عنوان کار محتوایی (مثلاً: راهنمای مشکلات رایج رنو ساندرو):', s.kind === 'supports' ? `مقاله پشتیبان: ${s.anchor ?? ''}` : `لینک‌سازی: ${s.anchor ?? ''} → ${s.target_title ?? ''}`);
    if (!title) return;
    try { const r = await endpoints.linkContentTask(siteId, s.id, { title }); toast.success(`کار محتوایی #${r.content_id} در مغز محتوا (برنامه‌ریزی‌شده) ساخته شد`); load(); }
    catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
  }
  async function setPattern(p: LinkPattern, status: string) {
    try { await endpoints.setLinkPattern(siteId, p.id, status); toast.success(status === 'accepted' ? 'الگو در حافظه Site Brain ذخیره شد' : 'رد شد'); load(); } catch (e) { toast.error(String(e)); }
  }
  const newCount = summary?.by_status.new ?? 0;

  return (
    <div className='flex flex-col gap-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect value={siteId} onChange={(e) => setSiteId(e.target.value)} className='w-44'>{sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>)}</NativeSelect>
        <Button onClick={analyze} disabled={!!busy}>{busy === 'analyze' ? 'در حال تحلیل…' : 'تحلیل لینک‌های داخلی'}</Button>
        <a className='text-xs underline' href={`/api/backend/sites/${encodeURIComponent(siteId)}/links/export.csv`} target='_blank' rel='noreferrer'>خروجی CSV (پذیرفته/انجام‌شده)</a>
        <Link href={`/dashboard/graph?site=${siteId}`} className='text-xs underline'>نقشه لینک داخلی در گراف</Link>
        <span className='text-muted-foreground ms-auto text-xs'>وردپرس تغییر نمی‌کند — فقط تحلیل، پیشنهاد، تأیید، خروجی</span>
      </div>
      {error && <p className='text-destructive text-sm'>{error}</p>}
      <div className='grid grid-cols-2 gap-3 md:grid-cols-6'>
        <KpiCard label='پیشنهادهای جدید' value={summary ? newCount : null} hint={summary ? Object.entries(summary.by_confidence).map(([k, v]) => `${CONF[k]?.fa ?? k} ${v}`).join(' · ') : undefined} />
        <KpiCard label='صفحات یتیم' value={summary?.flags.orphan ?? null} />
        <KpiCard label='لینک ورودی ضعیف' value={summary ? (summary.flags.nav_only_inbound + summary.flags.low_inbound + summary.flags.single_source) : null} hint='فقط ناوبری / کم / یک منبع' />
        <KpiCard label='انکرهای ضعیف' value={summary ? summary.flags.generic_anchors + summary.flags.over_optimized_anchor : null} />
        <KpiCard label='میانگین سلامت لینک' value={summary?.avg_health ?? null} hint='Internal Link Health Score ۰–۱۰۰' />
        <KpiCard label='پذیرفته / انجام‌شده' value={summary ? `${fa.format(summary.by_status.accepted)} / ${fa.format(summary.by_status.done)}` : null} />
      </div>
      <div className='flex flex-wrap gap-2 text-xs'>{Object.entries(CONF).map(([k, v]) => <span key={k} className='flex items-center gap-1'><span className='inline-block h-2.5 w-2.5 rounded-full' style={{ background: v.color }} />{v.fa} ({v.range})</span>)}</div>

      <Tabs defaultValue='suggestions'>
        <TabsList>
          <TabsTrigger value='suggestions'>پیشنهادهای لینک‌سازی {newCount ? <Badge className='ms-1'>{fa.format(newCount)}</Badge> : null}</TabsTrigger>
          <TabsTrigger value='orphans'>صفحات بدون لینک</TabsTrigger>
          <TabsTrigger value='weak'>لینک‌های ضعیف</TabsTrigger>
          <TabsTrigger value='patterns'>الگوهای یادگیری‌شده</TabsTrigger>
        </TabsList>

        <TabsContent value='suggestions' className='flex flex-col gap-2'>
          <div className='flex flex-wrap items-center gap-2'>
            <NativeSelect value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))} className='w-36'><NativeSelectOption value='new'>جدید</NativeSelectOption><NativeSelectOption value='accepted'>پذیرفته</NativeSelectOption><NativeSelectOption value='done'>انجام‌شده</NativeSelectOption><NativeSelectOption value='dismissed'>ردشده</NativeSelectOption><NativeSelectOption value=''>همه</NativeSelectOption></NativeSelect>
            <NativeSelect value={filters.confidence} onChange={(e) => setFilters((f) => ({ ...f, confidence: e.target.value }))} className='w-40'><NativeSelectOption value=''>همه سطوح اطمینان</NativeSelectOption><NativeSelectOption value='high'>اولویت بالا</NativeSelectOption><NativeSelectOption value='recommended'>توصیه‌شده</NativeSelectOption><NativeSelectOption value='low'>اطمینان کم</NativeSelectOption></NativeSelect>
            <NativeSelect value={filters.kind} onChange={(e) => setFilters((f) => ({ ...f, kind: e.target.value }))} className='w-44'><NativeSelectOption value=''>همه انواع</NativeSelectOption><NativeSelectOption value='contextual'>لینک متنی</NativeSelectOption><NativeSelectOption value='supports'>محتوای پشتیبان</NativeSelectOption><NativeSelectOption value='orphan_rescue'>نجات صفحه یتیم</NativeSelectOption><NativeSelectOption value='hub_spoke'>هاب → زیرمجموعه</NativeSelectOption><NativeSelectOption value='anchor_fix'>اصلاح انکر</NativeSelectOption><NativeSelectOption value='content_outbound'>از محتوای برنامه‌ریزی‌شده</NativeSelectOption></NativeSelect>
            <Input value={filters.q} onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))} placeholder='جست‌وجو (عنوان، URL، انکر)…' className='w-56' />
            <span className='text-muted-foreground ms-auto text-xs'>{sugg ? `${fa.format(sugg.total)} پیشنهاد` : ''}</span>
          </div>
          <div className='grid gap-2'>
            {sugg?.items.map((s) => (
              <div key={s.id} className='rounded-lg border p-3 text-sm' style={{ borderInlineStartWidth: 4, borderInlineStartColor: CONF[s.confidence]?.color }}>
                <div className='flex flex-wrap items-center gap-2'>
                  <Badge style={{ background: CONF[s.confidence]?.color }}>{s.confidence_fa} · {s.score.toFixed(2)}</Badge>
                  <Badge variant='outline'>{s.kind_fa}</Badge>
                  <span className='text-muted-foreground text-xs'>{STAGE_FA[s.source_stage ?? 'unknown']} → {STAGE_FA[s.target_stage ?? 'unknown']}</span>
                  {s.status !== 'new' && <Badge variant='secondary'>{STATUS_FA[s.status]}</Badge>}
                  {s.content_task_id && <Link href={`/dashboard/content?site=${siteId}`} className='text-xs underline'>کار محتوایی #{s.content_task_id}</Link>}
                </div>
                <div className='mt-2 grid gap-1 md:grid-cols-[1fr_auto_1fr] md:items-center'>
                  <div><div className='text-muted-foreground text-[10px]'>از</div><div className='font-medium'>{s.source_title ?? s.source_node_id}</div><div className='text-muted-foreground truncate text-[11px]' dir='ltr'>{s.source_url}</div></div>
                  <div className='text-center text-lg'>←</div>
                  <div><div className='text-muted-foreground text-[10px]'>به</div><div className='font-medium'>{s.target_title ?? s.target_node_id}</div><div className='text-muted-foreground truncate text-[11px]' dir='ltr'>{s.target_url}</div></div>
                </div>
                <div className='mt-2 flex flex-wrap items-center gap-2'>
                  <span className='text-xs'>انکر:</span>
                  <Input value={anchorEdit[s.id] ?? s.anchor ?? ''} onChange={(e) => setAnchorEdit((a) => ({ ...a, [s.id]: e.target.value }))} className='h-7 w-64 text-xs' list={`alts-${s.id}`} />
                  <datalist id={`alts-${s.id}`}>{s.anchor_alternatives.map((a) => <option key={a} value={a} />)}</datalist>
                  {s.anchor_alternatives.slice(0, 3).map((a) => <button key={a} className='text-muted-foreground text-[11px] underline' onClick={() => setAnchorEdit((x) => ({ ...x, [s.id]: a }))}>{a}</button>)}
                  {s.placement_hint && <span className='text-muted-foreground text-[11px]'>· {s.placement_hint}</span>}
                </div>
                <div className='mt-2 text-xs'><span className='font-medium'>دلیل: </span>{s.reason_fa}</div>
                {s.kind !== 'anchor_fix' && (
                  <div className='mt-2 flex flex-wrap gap-2 text-[11px]'>
                    {['topic', 'entities', 'intent', 'authority', 'anchor'].map((k) => (
                      <span key={k} className='flex items-center gap-1'><span className='text-muted-foreground'>{COMP_FA[k]}</span><span className='bg-muted inline-block h-1.5 w-16 overflow-hidden rounded'><span className='bg-primary block h-1.5' style={{ width: `${Math.round((s.score_breakdown[k] ?? 0) * 100)}%` }} /></span><span dir='ltr'>{Math.round((s.score_breakdown[k] ?? 0) * 100)}</span></span>
                    ))}
                    {s.evidence?.shared_entities?.length ? <span className='text-muted-foreground'>· موجودیت‌ها: {s.evidence.shared_entities.join('، ')}</span> : null}
                    {s.evidence?.target_health != null ? <span className='text-muted-foreground'>· سلامت لینک هدف: {s.evidence.target_health}</span> : null}
                  </div>
                )}
                <div className='mt-2 flex flex-wrap gap-1'>
                  {s.status === 'new' && (<><Button size='sm' onClick={() => setStatus(s, 'accepted')}>پذیرش</Button><Button size='sm' variant='ghost' onClick={() => setStatus(s, 'dismissed')}>رد</Button></>)}
                  {s.status === 'accepted' && (<><Button size='sm' onClick={() => setStatus(s, 'done')}>انجام شد</Button><Button size='sm' variant='ghost' onClick={() => setStatus(s, 'dismissed')}>رد</Button>{!s.content_task_id && <Button size='sm' variant='outline' onClick={() => contentTask(s)}>ایجاد کار محتوایی</Button>}</>)}
                  {s.status === 'done' && !s.content_task_id && <Button size='sm' variant='outline' onClick={() => contentTask(s)}>ایجاد کار محتوایی</Button>}
                  {s.status === 'dismissed' && <Button size='sm' variant='ghost' onClick={() => setStatus(s, 'new')}>بازگردانی</Button>}
                </div>
              </div>
            ))}
            {sugg && sugg.items.length === 0 && <p className='text-muted-foreground text-sm'>پیشنهادی نیست — «تحلیل لینک‌های داخلی» را اجرا کنید یا فیلترها را تغییر دهید.</p>}
          </div>
        </TabsContent>

        <TabsContent value='orphans' className='flex flex-col gap-2'>
          <div className='flex items-center gap-2'>
            <NativeSelect value={pageFlag} onChange={(e) => setPageFlag(e.target.value)} className='w-52'><NativeSelectOption value='orphan'>یتیم (بدون لینک ورودی)</NativeSelectOption><NativeSelectOption value='low_inbound'>لینک ورودی کم</NativeSelectOption><NativeSelectOption value='nav_only_inbound'>فقط لینک ناوبری</NativeSelectOption><NativeSelectOption value=''>همه صفحات</NativeSelectOption></NativeSelect>
            <span className='text-muted-foreground text-xs'>{fa.format(pages.length)} صفحه</span>
          </div>
          <PagesTable rows={pages} siteId={siteId} suggestions={sugg?.items ?? []} onAccept={setStatus} />
        </TabsContent>

        <TabsContent value='weak' className='flex flex-col gap-2'>
          <p className='text-muted-foreground text-xs'>صفحات با لینک ورودی فقط ناوبری، یک منبع، انکر عمومی/تکراری، لینک به noindex یا بدون لینک خروجی بدنه — به همراه توزیع انکر و امتیاز سلامت.</p>
          <PagesTable rows={weak} siteId={siteId} suggestions={sugg?.items ?? []} onAccept={setStatus} showAnchors />
        </TabsContent>

        <TabsContent value='patterns' className='grid gap-2 md:grid-cols-2'>
          {patterns.map((p) => (
            <div key={p.id} className='rounded-lg border p-3 text-sm'>
              <div className='flex items-center gap-2'><Badge variant='outline'>{p.pattern_key.split(':')[0]}</Badge><span className='text-muted-foreground ms-auto text-xs' dir='ltr'>{Math.round(p.acceptance_rate * 100)}% · n={p.accepted + p.dismissed}</span></div>
              <div className='mt-1'>{p.message_fa}</div>
              <div className='mt-2 flex gap-1'>
                {p.status === 'new' ? (<><Button size='sm' onClick={() => setPattern(p, 'accepted')}>تأیید و ذخیره در حافظه</Button><Button size='sm' variant='ghost' onClick={() => setPattern(p, 'dismissed')}>رد</Button></>) : <Badge variant='secondary'>{p.status === 'accepted' ? `پذیرفته${p.memory_pattern_ref ? ' · در حافظه Site Brain' : ''}` : 'ردشده'}</Badge>}
              </div>
            </div>
          ))}
          {patterns.length === 0 && <p className='text-muted-foreground text-sm md:col-span-2'>هنوز الگویی نیست — با پذیرش/رد چند پیشنهاد، الگوها ساخته می‌شوند (حداقل ۲ تصمیم). هیچ قاعده‌ای خودکار تغییر نمی‌کند.</p>}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function PagesTable({ rows, siteId, suggestions, onAccept, showAnchors }: { rows: LinkPageStat[]; siteId: string; suggestions: LinkSuggestion[]; onAccept: (s: LinkSuggestion, status: string) => void; showAnchors?: boolean }) {
  return (
    <div className='overflow-x-auto rounded-md border'>
      <Table>
        <TableHeader><TableRow><TableHead>صفحه</TableHead><TableHead>مرحله</TableHead><TableHead>سلامت لینک</TableHead><TableHead>ورودی بدنه / ناوبری</TableHead><TableHead>منابع</TableHead><TableHead>خروجی</TableHead><TableHead>پرچم‌ها</TableHead>{showAnchors && <TableHead>توزیع انکر</TableHead>}<TableHead>پیشنهاد منبع</TableHead></TableRow></TableHeader>
        <TableBody>
          {rows.map((p) => {
            const forPage = suggestions.filter((s) => s.target_node_id === p.node_id && s.status === 'new').slice(0, 3);
            return (
              <TableRow key={p.node_id}>
                <TableCell className='font-medium'>{p.title ?? p.node_id}<div className='text-muted-foreground truncate text-[10px]' dir='ltr'>{p.url}</div><Link href={`/dashboard/graph?site=${siteId}`} className='text-[10px] underline'>گراف</Link></TableCell>
                <TableCell>{STAGE_FA[p.stage ?? 'unknown']}</TableCell>
                <TableCell><span className='rounded px-1.5 py-0.5 text-xs font-semibold text-white tabular-nums' style={{ background: healthColor(p.health_score) }} title={Object.entries(p.health_breakdown).map(([k, v]) => `${k}: ${v}`).join(' · ')}>{fa.format(p.health_score)}</span></TableCell>
                <TableCell className='tabular-nums'>{fa.format(p.inbound_body)} / {fa.format(p.inbound_nav_only)}</TableCell>
                <TableCell className='tabular-nums'>{fa.format(p.unique_sources)}</TableCell>
                <TableCell className='tabular-nums'>{fa.format(p.outbound_body)}</TableCell>
                <TableCell><div className='flex flex-wrap gap-1'>{p.flags.map((f) => <Badge key={f} variant='outline' className='text-[10px]'>{FLAG_FA[f] ?? f}</Badge>)}</div></TableCell>
                {showAnchors && <TableCell className='text-xs'>{p.anchor_distribution.slice(0, 4).map((a) => `${a.anchor} (${a.count})`).join('، ') || '—'}{p.exact_match_ratio > 0.6 ? <div className='text-destructive'>انکر دقیق {Math.round(p.exact_match_ratio * 100)}٪</div> : null}</TableCell>}
                <TableCell className='text-xs'>
                  {forPage.length === 0 ? <span className='text-muted-foreground'>—</span> : forPage.map((s) => (
                    <div key={s.id} className='flex items-center gap-1'><span className='inline-block h-2 w-2 rounded-full' style={{ background: CONF[s.confidence]?.color }} /><span className='truncate'>{s.source_title}</span><span className='text-muted-foreground'>«{s.anchor}»</span><button className='text-[10px] underline' onClick={() => onAccept(s, 'accepted')}>پذیرش</button></div>
                  ))}
                </TableCell>
              </TableRow>
            );
          })}
          {rows.length === 0 && <TableRow><TableCell colSpan={showAnchors ? 9 : 8} className='text-muted-foreground text-center'>صفحه‌ای با این شرط نیست (یا هنوز تحلیل اجرا نشده).</TableCell></TableRow>}
        </TableBody>
      </Table>
    </div>
  );
}
