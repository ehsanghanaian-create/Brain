'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { api, type Site } from '@/lib/api/client';
import { IconArrowDown, IconArrowUp, IconRefresh } from '@tabler/icons-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { toast } from 'sonner';

type RankSettings = {
  enabled: boolean;
  provider: 'serpkite' | 'serpapi' | 'dataforseo';
  provider_ready: boolean;
  market: string;
  language: string;
  device: 'mobile' | 'desktop';
  depth: 10 | 20 | 30 | 50;
  daily_hour: number;
  max_keywords_per_run: number;
  timezone: string;
};
type RankRun = {
  id: number;
  local_date: string;
  provider: string;
  device: string;
  requested_depth: number;
  status: string;
  keywords_total: number;
  keywords_checked: number;
  keywords_failed: number;
  provider_requests: number;
  finished_at: string | null;
  error_code: string | null;
};
type RankKeyword = {
  keyword_id: number;
  keyword: string;
  priority: string | null;
  target_url: string | null;
  status: string | null;
  organic_position: number | null;
  absolute_position: number | null;
  ranking_url: string | null;
  returned_organic_count: number | null;
  checked_at: string | null;
  local_date: string | null;
  provider: string | null;
  previous_position: number | null;
  delta: number | null;
  action: string | null;
  competitors: { position: number; url: string; domain: string }[];
  history: { local_date: string; organic_position: number | null; status: string }[];
};
type RankOverview = {
  settings: RankSettings;
  keywords_total: number;
  latest_run: RankRun | null;
  runs: RankRun[];
  keywords: RankKeyword[];
  generated_at: string;
};

const number = new Intl.NumberFormat('fa-IR');
const date = (value: string | null | undefined) => value ? new Intl.DateTimeFormat('fa-IR', {
  dateStyle: 'medium', timeZone: 'Asia/Tehran'
}).format(new Date(value.length === 10 ? `${value}T00:00:00+03:30` : value)) : '—';
const statusFa: Record<string, string> = {
  queued: 'در صف', running: 'در حال بررسی', succeeded: 'کامل', partial: 'پوشش بخشی', blocked: 'متوقف'
};
const actionFa: Record<string, string> = {
  review_target_page: 'صفحهٔ رتبه‌دار با صفحهٔ هدف فرق دارد؛ هم‌خوانی محتوا و لینک‌های داخلی را بررسی کنید.',
  review_snippet_and_links: 'نزدیک سه رتبهٔ نخست: عنوان، توضیح، کیفیت پاسخ و لینک‌های داخلی را بررسی کنید.',
  check_rank_drop: 'افت نسبت به مشاهدهٔ قبلی؛ چند روز روند و تغییرات صفحه و رقبا را بررسی کنید.',
  review_indexing_and_intent: 'در نتایج دریافت‌شده دیده نشد؛ ایندکس، نیت جست‌وجو و عمق دریافت را بررسی کنید.'
};

function Stat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <Card><CardHeader className='pb-2'><CardDescription>{label}</CardDescription><CardTitle className='text-2xl tabular-nums'>{value}</CardTitle></CardHeader>
    <CardContent><p className='text-muted-foreground text-xs leading-5'>{detail}</p></CardContent></Card>;
}

export function RankTrackingDashboard({ sites, initialSiteId }: { sites: Site[]; initialSiteId: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [data, setData] = useState<RankOverview | null>(null);
  const [draft, setDraft] = useState<RankSettings | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [filter, setFilter] = useState('');
  const [onlyActions, setOnlyActions] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(100);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const path = `/sites/${encodeURIComponent(siteId)}/rank-tracking`;
  const load = useCallback(async () => {
    try {
      const response = await api<RankOverview>(`${path}/overview`);
      setData(response);
      setDraft((current) => current ?? response.settings);
      setError(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
  }, [path]);
  useEffect(() => { setData(null); setDraft(null); setSelected(null); void load(); }, [load]);
  useEffect(() => {
    if (data?.latest_run?.status !== 'running' && data?.latest_run?.status !== 'queued') return;
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void load(); }, 10000);
    return () => window.clearInterval(timer);
  }, [data?.latest_run?.status, load]);
  const rows = useMemo(() => (data?.keywords ?? []).filter((row) =>
    row.keyword.includes(filter.trim()) && (!onlyActions || !!row.action)), [data, filter, onlyActions]);
  const shown = rows.slice(0, displayLimit);
  const focus = data?.keywords.find((row) => row.keyword_id === selected) ?? null;
  const found = data?.keywords.filter((row) => row.status === 'found').length ?? 0;
  const actions = data?.keywords.filter((row) => !!row.action).length ?? 0;
  const dailyRequests = data?.keywords_total ?? 0;
  const plannedDaily = Math.min(dailyRequests, draft?.max_keywords_per_run ?? 0);
  const estimatedMonthlyCredits = plannedDaily * Math.ceil((draft?.depth ?? 10) / 10) * 31;
  const rotationDays = draft?.max_keywords_per_run ? Math.ceil(dailyRequests / draft.max_keywords_per_run) : 0;

  async function saveSettings() {
    if (!draft) return;
    setBusy(true);
    try {
      const response = await api<RankSettings>(`${path}/settings`, { method: 'PUT', json: {
        enabled: draft.enabled, provider: draft.provider, device: draft.device,
        depth: draft.depth, max_keywords_per_run: draft.max_keywords_per_run
      } });
      setDraft(response);
      toast.success('تنظیمات پایش ذخیره شد.');
      await load();
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ذخیره نشد.'); }
    finally { setBusy(false); }
  }

  async function runNow() {
    setBusy(true);
    try {
      const response = await api<{ status: string }>(`${path}/run`, { method: 'POST' });
      toast.success(response.status === 'queued' ? 'پایش رتبه در صف قرار گرفت.' : 'اجرای امروز قبلاً ثبت شده است.');
      await load();
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : 'اجرای پایش ممکن نشد.'); }
    finally { setBusy(false); }
  }

  return <div className='space-y-5'>
    <div className='flex flex-wrap items-center gap-3'>
      <Label htmlFor='rank-site'>سایت</Label>
      <NativeSelect id='rank-site' value={siteId} onChange={(event) => setSiteId(event.target.value)} className='w-48'>
        {sites.map((site) => <NativeSelectOption key={site.site_id} value={site.site_id}>{site.name}</NativeSelectOption>)}
      </NativeSelect>
      <Badge variant='outline'>ایران · فارسی · {draft?.device === 'desktop' ? 'دسکتاپ' : 'موبایل'}</Badge>
      <span className='text-muted-foreground text-sm'>اجرا: هر روز ساعت ۶:۰۰ تهران</span>
      <Button variant='outline' size='sm' onClick={() => void load()} className='ms-auto gap-2'><IconRefresh size={16} /> تازه‌سازی</Button>
    </div>

    {error && <p role='alert' className='text-destructive rounded-md border border-destructive/30 p-3 text-sm'>{error}</p>}
    {!data && !error && <p className='text-muted-foreground py-8 text-center'>در حال دریافت داده‌های پایش…</p>}
    {data && <>
      {!draft?.provider_ready && <Card className='border-amber-500/40 bg-amber-500/5'>
        <CardHeader><CardTitle className='text-lg'>منبع رتبهٔ زنده هنوز متصل نیست</CardTitle>
          <CardDescription>SEO Brain جایگاه سرچ کنسول را به‌جای رتبهٔ مستقل نشان نمی‌دهد. برای شروع، کلید {draft?.provider === 'dataforseo' ? 'DataForSEO' : draft?.provider === 'serpapi' ? 'SerpApi' : 'SerpKite'} باید به‌صورت امن روی سرور تنظیم شود.</CardDescription></CardHeader>
        <CardContent className='space-y-2 text-sm'>
          <p>برای {number.format(dailyRequests)} کلمه، سنجش روزانهٔ همهٔ آن‌ها در ماه ۳۱ روزه دست‌کم {number.format(dailyRequests * 31)} جست‌وجو می‌خواهد. سهمیهٔ رایگان ماهانهٔ SerpKite برابر ۱٬۰۰۰ اعتبار است؛ جست‌وجوی ۱۰ نتیجه‌ای یک اعتبار مصرف می‌کند. سقف پیش‌فرض ۳۰ کلمه در روز، کل فهرست را به‌صورت چرخشی پوشش می‌دهد.</p>
          <p className='text-muted-foreground'>پس از اتصال، رتبه‌های ارگانیک با تاریخ، کشور، زبان، دستگاه و عمق نتیجه ثبت می‌شوند. هیچ عددی پیش از مشاهدهٔ واقعی ساخته نمی‌شود.</p>
        </CardContent>
      </Card>}
      <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-4'>
        <Stat label='کلمات فعال' value={number.format(data.keywords_total)} detail='همهٔ کلمات ذخیره‌شده به‌جز نادیده‌گرفته‌شده‌ها' />
        <Stat label='دارای رتبهٔ ثبت‌شده' value={data.latest_run ? number.format(found) : '—'} detail={`از آخرین مشاهدهٔ هر کلمه؛ عمق بررسی ${data.latest_run?.requested_depth ?? draft?.depth ?? 10} نتیجه`} />
        <Stat label='نیازمند بررسی' value={data.latest_run ? number.format(actions) : '—'} detail='پیشنهادهای توضیح‌پذیر؛ تغییر سایت خودکار انجام نمی‌شود' />
        <Stat label='آخرین اجرا' value={data.latest_run ? date(data.latest_run.local_date) : 'هنوز اجرا نشده'} detail={data.latest_run ? `${statusFa[data.latest_run.status] ?? data.latest_run.status} · ${number.format(data.latest_run.keywords_checked)} از ${number.format(data.latest_run.keywords_total)}` : 'پس از اتصال منبع، اجرای روزانه آغاز می‌شود'} />
      </div>

      <Card><CardHeader><CardTitle className='text-lg'>تنظیم پایش</CardTitle><CardDescription>رتبه به کشور، زبان، دستگاه و عمق بررسی وابسته است. تغییر تنظیمات از اجرای روز بعد اعمال می‌شود.</CardDescription></CardHeader>
        <CardContent className='flex flex-wrap items-end gap-3'>
          <div className='space-y-1'><Label htmlFor='rank-provider'>منبع</Label><NativeSelect id='rank-provider' value={draft?.provider ?? 'serpkite'} onChange={(e) => setDraft((old) => old && { ...old, provider: e.target.value as RankSettings['provider'], provider_ready: false })} className='w-40'><NativeSelectOption value='serpkite'>SerpKite</NativeSelectOption><NativeSelectOption value='serpapi'>SerpApi</NativeSelectOption><NativeSelectOption value='dataforseo'>DataForSEO</NativeSelectOption></NativeSelect></div>
          <div className='space-y-1'><Label htmlFor='rank-device'>دستگاه</Label><NativeSelect id='rank-device' value={draft?.device ?? 'mobile'} onChange={(e) => setDraft((old) => old && { ...old, device: e.target.value as RankSettings['device'] })} className='w-32'><NativeSelectOption value='mobile'>موبایل</NativeSelectOption><NativeSelectOption value='desktop'>دسکتاپ</NativeSelectOption></NativeSelect></div>
          <div className='space-y-1'><Label htmlFor='rank-depth'>عمق ارگانیک</Label><NativeSelect id='rank-depth' value={draft?.depth ?? 20} onChange={(e) => setDraft((old) => old && { ...old, depth: Number(e.target.value) as RankSettings['depth'] })} className='w-28'>{[10,20,30,50].map((depth) => <NativeSelectOption key={depth} value={depth}>{depth} نتیجه</NativeSelectOption>)}</NativeSelect></div>
          <div className='space-y-1'><Label htmlFor='rank-cap'>سقف درخواست روزانه</Label><Input id='rank-cap' type='number' min={1} max={5000} className='w-28' value={draft?.max_keywords_per_run ?? 500} onChange={(e) => setDraft((old) => old && { ...old, max_keywords_per_run: Number(e.target.value) })} /></div>
          <Button disabled={busy || !draft} onClick={() => void saveSettings()}>ذخیره</Button>
          <Button variant='outline' disabled={busy || !draft?.provider_ready || !draft.enabled} onClick={() => void runNow()}>اجرای امروز</Button>
          {draft?.provider === 'serpkite' && <p className='w-full text-xs text-muted-foreground'>با این تنظیمات، حداکثر {number.format(plannedDaily)} کلمه در روز و حدود {number.format(estimatedMonthlyCredits)} اعتبار در ۳۱ روز مصرف می‌شود. پوشش چرخشی کل فهرست حدود {number.format(rotationDays)} روز طول می‌کشد. {estimatedMonthlyCredits > 1000 ? 'این میزان از سهمیهٔ رایگان ماهانه بیشتر است.' : 'این میزان در محدودهٔ ۱٬۰۰۰ اعتبار ماهانه است.'}</p>}
        </CardContent>
      </Card>

      {data.latest_run && data.latest_run.status !== 'succeeded' && <p className='rounded-md border border-amber-500/40 p-3 text-sm' role='status'>آخرین اجرا {statusFa[data.latest_run.status] ?? data.latest_run.status} است؛ {number.format(data.latest_run.keywords_checked)} از {number.format(data.latest_run.keywords_total)} کلمه بررسی شد و {number.format(data.latest_run.keywords_failed)} خطا ثبت شد. {data.latest_run.error_code === 'daily_request_cap_reached' ? 'سقف روزانهٔ تنظیم‌شده رسید؛ کلمات باقی‌مانده در نوبت‌های بعدی بررسی می‌شوند.' : data.latest_run.error_code ? `خطای منبع: ${data.latest_run.error_code}` : ''} دادهٔ ناموجود رتبهٔ صفر محسوب نمی‌شود.</p>}

      <Card><CardHeader><CardTitle className='text-lg'>کلمات و مسیر اقدام</CardTitle><CardDescription>رتبهٔ ارگانیک مشاهده‌شده برای ایران، فارسی و دستگاه انتخاب‌شده. جابه‌جایی یک روزه ممکن است نوسان باشد؛ پیش از تغییر محتوا روند و شواهد را بررسی کنید.</CardDescription></CardHeader>
        <CardContent className='space-y-3'>
          <div className='flex flex-wrap items-center gap-2'><Label htmlFor='rank-filter'>جست‌وجو</Label><Input id='rank-filter' value={filter} onChange={(e) => setFilter(e.target.value)} placeholder='کلمهٔ کلیدی…' className='w-56' /><Button variant={onlyActions ? 'default' : 'outline'} size='sm' onClick={() => setOnlyActions((value) => !value)}>فقط نیازمند بررسی</Button><span className='text-muted-foreground ms-auto text-sm'>{number.format(rows.length)} نتیجه؛ نمایش {number.format(shown.length)} مورد اول</span></div>
          <div className='overflow-x-auto rounded-md border'><Table><TableHeader><TableRow><TableHead>کلمه</TableHead><TableHead>رتبه</TableHead><TableHead>آخرین سنجش</TableHead><TableHead>تغییر</TableHead><TableHead>صفحهٔ رتبه‌دار</TableHead><TableHead>اقدام پیشنهادی</TableHead></TableRow></TableHeader><TableBody>
            {shown.map((row) => <TableRow key={row.keyword_id} className='cursor-pointer' onClick={() => setSelected(row.keyword_id)} aria-selected={selected === row.keyword_id}>
              <TableCell className='font-medium'>{row.keyword}</TableCell>
              <TableCell className='tabular-nums'>{row.status === 'found' ? `#${number.format(row.organic_position ?? 0)}` : row.status === 'not_found_in_results' ? `دیده نشد (${number.format(row.returned_organic_count ?? 0)} نتیجه)` : '—'}</TableCell>
              <TableCell className='whitespace-nowrap text-xs'>{date(row.local_date)}</TableCell>
              <TableCell>{row.delta == null || row.delta === 0 ? '—' : <span className={`inline-flex items-center gap-1 ${row.delta > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}`}>{row.delta > 0 ? <IconArrowUp size={14} /> : <IconArrowDown size={14} />}{number.format(Math.abs(row.delta))}</span>}</TableCell>
              <TableCell className='max-w-48 truncate text-xs' dir='ltr' title={row.ranking_url ?? ''}>{row.ranking_url ? new URL(row.ranking_url).pathname : '—'}</TableCell>
              <TableCell className='max-w-64 text-xs'>{row.action ? actionFa[row.action] : '—'}</TableCell>
            </TableRow>)}
            {shown.length === 0 && <TableRow><TableCell colSpan={6} className='text-muted-foreground py-8 text-center'>کلمه‌ای با این فیلتر پیدا نشد.</TableCell></TableRow>}
          </TableBody></Table></div>
          {rows.length > shown.length && <Button variant='outline' size='sm' onClick={() => setDisplayLimit((current) => current + 100)}>نمایش {number.format(Math.min(100, rows.length - shown.length))} کلمهٔ بعدی</Button>}
        </CardContent></Card>

      {focus && <Card><CardHeader><CardTitle className='text-lg'>{focus.keyword}</CardTitle><CardDescription>{focus.local_date ? `آخرین مشاهده: ${date(focus.local_date)} · ${focus.provider ?? data.latest_run?.provider ?? 'SERP'}` : 'هنوز مشاهده‌ای ثبت نشده است'}</CardDescription></CardHeader>
        <CardContent className='space-y-4'>
          <div className='grid gap-3 text-sm md:grid-cols-3'><div><span className='text-muted-foreground'>صفحهٔ هدف: </span><span dir='ltr' className='break-all'>{focus.target_url ?? 'تعریف نشده'}</span></div><div><span className='text-muted-foreground'>صفحهٔ دیده‌شده: </span><span dir='ltr' className='break-all'>{focus.ranking_url ?? 'دیده نشد'}</span></div><div><span className='text-muted-foreground'>رتبهٔ قبلی: </span>{focus.previous_position ? `#${number.format(focus.previous_position)}` : '—'}</div></div>
          {focus.history.length > 1 && <div className='h-48' role='img' aria-label={`روند رتبهٔ ارگانیک ${focus.keyword}`}><ResponsiveContainer width='100%' height='100%'><LineChart data={focus.history}><CartesianGrid strokeDasharray='3 3' /><XAxis dataKey='local_date' tickFormatter={(value: string) => value.slice(5)} /><YAxis reversed domain={[1, 'dataMax + 3']} allowDecimals={false} /><Tooltip formatter={(value) => [`رتبه ${value}`, 'ارگانیک']} /><Line type='monotone' dataKey='organic_position' connectNulls={false} stroke='var(--primary)' strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div>}
          {focus.action && <p className='rounded-md bg-muted p-3 text-sm'><strong>بررسی پیشنهادی: </strong>{actionFa[focus.action]}</p>}
          {!!focus.competitors.length && <div className='text-sm'><strong>رقبای دیده‌شده در همین نمونه:</strong><ul className='mt-2 space-y-1'>{focus.competitors.map((item) => <li key={`${item.position}-${item.url}`} className='flex gap-2'><span className='tabular-nums'>#{number.format(item.position)}</span><span dir='ltr' className='truncate'>{item.domain}</span></li>)}</ul></div>}
        </CardContent></Card>}

      <p className='text-muted-foreground text-xs leading-5'>منبع این جدول نمونهٔ مستقل نتایج ارگانیک ارائه‌دهنده است. رتبه با مکان، دستگاه، زمان و شخصی‌سازی تغییر می‌کند؛ «دیده نشد» فقط به نتایج دریافت‌شده اشاره دارد. میانگین جایگاه سرچ کنسول در بخش جداگانه باقی می‌ماند.</p>
    </>}
  </div>;
}
