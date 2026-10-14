'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ChartContainer, ChartTooltip, ChartTooltipContent } from '@/components/ui/chart';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { api, type Site } from '@/lib/api/client';
import { IconArrowUpRight, IconRefresh } from '@tabler/icons-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { toast } from 'sonner';

type Candidate = {
  query: string;
  impressions: number;
  clicks: number;
  previous_impressions: number;
  position: number | null;
  top_page: string | null;
  signal: 'new_in_sample' | 'growing_in_sample' | 'observed';
  is_question: boolean;
};
type TrackedPrompt = {
  id: number;
  question: string;
  topic: string;
  target_url: string;
  active: number;
  samples: number;
  last_observed_at: string | null;
};
type CompetitorPage = {
  id: number;
  url: string;
  focus_query: string;
  own_url: string;
  status: 'pending' | 'queued' | 'ready' | 'error';
  error_code: string;
  title: string;
  meta_description: string;
  h1: string[];
  h2: string[];
  review_headings: string[];
  canonical: string;
  word_count: number | null;
  last_checked_at: string | null;
  own_page: {
    title: string | null;
    meta_description: string | null;
    h1: string[];
    h2: string[];
    word_count: number | null;
    last_crawled: string | null;
  } | null;
};
type ResearchOverview = {
  generated_at: string;
  period: { start: string; end: string; days: number } | null;
  gsc: {
    latest_date: string | null;
    latest_sync: { status: string; finished_at: string | null } | null;
    current_days: number;
    previous_days: number;
    coverage: string;
    daily: { date: string; impressions: number; clicks: number }[];
    candidates: Candidate[];
    candidate_limit: number;
    query_scan_limit: number;
  };
  questions: {
    observed_search_questions: {
      query: string;
      impressions: number;
      clicks: number;
      top_page: string | null;
      source: string;
    }[];
    modeled_buyer_questions: {
      query: string;
      question: string;
      impressions: number;
      top_page: string | null;
      source: string;
    }[];
    tracked_prompts: TrackedPrompt[];
    scope: string;
  };
  competitors: {
    tracked_pages: CompetitorPage[];
    ai_citation_domains: {
      domain: string;
      mentions: number;
      last_observed_at: string;
      example_url: string;
    }[];
    scope: string;
  };
};

const fa = new Intl.NumberFormat('fa-IR');
const n = (value: number | null | undefined) => (value == null ? '—' : fa.format(value));
const dateLabel = (value: string | null | undefined) =>
  value
    ? new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium' }).format(new Date(value))
    : 'نامشخص';
const signalLabel: Record<Candidate['signal'], string> = {
  new_in_sample: 'تازه در نمونه',
  growing_in_sample: 'رشد در نمونه',
  observed: 'دیده‌شده'
};

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <Card>
      <CardHeader className='pb-2'>
        <CardDescription>{label}</CardDescription>
        <CardTitle className='text-2xl tabular-nums'>{value}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className='text-muted-foreground text-xs leading-5'>{detail}</p>
      </CardContent>
    </Card>
  );
}

export function ResearchDashboard({
  sites,
  initialSiteId
}: {
  sites: Site[];
  initialSiteId: string;
}) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [days, setDays] = useState(28);
  const [data, setData] = useState<ResearchOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [busy, setBusy] = useState(false);
  const [competitorUrl, setCompetitorUrl] = useState('');
  const [focusQuery, setFocusQuery] = useState('');
  const [ownUrl, setOwnUrl] = useState('');
  const loadSequence = useRef(0);
  const path = `/sites/${encodeURIComponent(siteId)}/research`;

  const load = useCallback(async () => {
    const sequence = ++loadSequence.current;
    setError(null);
    try {
      const result = await api<ResearchOverview>(
        `/sites/${encodeURIComponent(siteId)}/research/overview?days=${days}`
      );
      if (sequence === loadSequence.current) setData(result);
    } catch (cause) {
      if (sequence === loadSequence.current)
        setError(cause instanceof Error ? cause.message : 'دادهٔ پژوهش بارگیری نشد.');
    } finally {
      if (sequence === loadSequence.current) setLoading(false);
    }
  }, [siteId, days]);

  useEffect(() => {
    setData(null);
    setLoading(true);
    void load();
  }, [load]);
  useEffect(() => {
    if (!data?.competitors.tracked_pages.some((item) => item.status === 'queued')) return;
    const timer = window.setInterval(() => {
      void load();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [data, load]);
  useEffect(() => {
    const timer = window.setInterval(
      () => {
        if (document.visibilityState === 'visible') void load();
      },
      10 * 60 * 1000
    );
    return () => window.clearInterval(timer);
  }, [load]);

  const candidates = useMemo(
    () => data?.gsc.candidates.filter((row) => row.query.includes(filter.trim())) ?? [],
    [data, filter]
  );
  const recent = data?.gsc.latest_date
    ? Math.floor((Date.now() - new Date(`${data.gsc.latest_date}T00:00:00Z`).getTime()) / 86400000)
    : null;
  const gscReady =
    recent != null &&
    recent <= 4 &&
    ['succeeded', 'completed'].includes(data?.gsc.latest_sync?.status ?? '');
  const newlySeen =
    data?.gsc.candidates.filter((row) => row.signal === 'new_in_sample').length ?? 0;
  const seenQuestions = data?.questions.observed_search_questions.length ?? 0;

  async function saveKeyword(row: Candidate) {
    setBusy(true);
    try {
      await api(`/sites/${encodeURIComponent(siteId)}/keywords/discover/gsc/decision`, {
        method: 'POST',
        json: { keyword: row.query, action: 'save' }
      });
      toast.success('عبارت با منبع GSC ثبت شد.');
      await load();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'ثبت کلمه انجام نشد.');
    } finally {
      setBusy(false);
    }
  }

  async function saveQuestion(question: string, topic: string, targetUrl: string | null) {
    setBusy(true);
    try {
      await api(`/sites/${encodeURIComponent(siteId)}/ai-visibility/prompts`, {
        method: 'POST',
        json: { question, topic, target_url: targetUrl || null, intent: 'commercial' }
      });
      toast.success('پرسش برای پایش ثبت شد؛ این ثبت، ترافیک AI را اثبات نمی‌کند.');
      await load();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'ثبت پرسش انجام نشد.');
    } finally {
      setBusy(false);
    }
  }

  async function addCompetitor(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api(`${path}/competitors`, {
        method: 'POST',
        json: {
          url: competitorUrl,
          focus_query: focusQuery,
          own_url: ownUrl || null
        }
      });
      setCompetitorUrl('');
      setFocusQuery('');
      setOwnUrl('');
      toast.success('صفحهٔ رقیب ثبت شد و بررسی در صف قرار گرفت.');
      await load();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'ثبت رقیب انجام نشد.');
    } finally {
      setBusy(false);
    }
  }

  async function refreshCompetitor(id: number) {
    setBusy(true);
    try {
      await api(`${path}/competitors/${id}/refresh`, { method: 'POST' });
      toast.success('بازخوانی صفحه در صف قرار گرفت.');
      await load();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'بازخوانی انجام نشد.');
    } finally {
      setBusy(false);
    }
  }

  async function removeCompetitor(id: number) {
    if (!window.confirm('این صفحه از فهرست پایش حذف شود؟')) return;
    setBusy(true);
    try {
      await api(`${path}/competitors/${id}`, { method: 'DELETE' });
      toast.success('صفحه از پایش حذف شد.');
      await load();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'حذف انجام نشد.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className='space-y-5' dir='rtl'>
      <div className='flex flex-wrap items-center gap-2'>
        <Label htmlFor='research-site'>سایت</Label>
        <NativeSelect
          id='research-site'
          value={siteId}
          onChange={(event) => setSiteId(event.target.value)}
          className='w-48'
        >
          {sites.map((site) => (
            <NativeSelectOption key={site.site_id} value={site.site_id}>
              {site.name}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <Label htmlFor='research-days'>بازه</Label>
        <NativeSelect
          id='research-days'
          value={String(days)}
          onChange={(event) => setDays(Number(event.target.value))}
          className='w-32'
        >
          {[7, 28, 90].map((day) => (
            <NativeSelectOption key={day} value={String(day)}>
              {n(day)} روز
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <Button variant='outline' size='sm' onClick={() => void load()} disabled={loading}>
          <IconRefresh size={16} aria-hidden='true' /> تازه‌سازی نمایش
        </Button>
        {data && (
          <span className='text-muted-foreground me-auto text-xs'>
            آخرین دادهٔ جست‌وجو: {dateLabel(data.gsc.latest_date)} · همگام‌سازی:{' '}
            {data.gsc.latest_sync?.status ?? 'نامشخص'}
          </span>
        )}
      </div>
      {error && (
        <Card className='border-destructive/40'>
          <CardContent className='py-4 text-sm text-destructive' role='alert'>
            {error}
          </CardContent>
        </Card>
      )}
      {loading && !data && (
        <p role='status' className='text-muted-foreground py-12 text-center'>
          در حال بارگذاری پژوهش بازار…
        </p>
      )}
      {data && (
        <>
          <Card
            className={
              gscReady
                ? 'border-primary/20 bg-primary/[0.035]'
                : 'border-amber-500/35 bg-amber-500/[0.04]'
            }
          >
            <CardContent className='flex flex-wrap items-start justify-between gap-3 py-4 text-sm'>
              <div>
                <strong>{gscReady ? 'دادهٔ GSC به‌روز است' : 'پوشش داده نیاز به بررسی دارد'}</strong>
                <p className='text-muted-foreground mt-1 leading-6'>
                  {data.gsc.latest_date
                    ? `آخرین روز ${dateLabel(data.gsc.latest_date)}؛ پوشش ${n(data.gsc.current_days)} از ${n(days)} روز در بازهٔ انتخابی.`
                    : 'هنوز دادهٔ query/page وارد نشده است.'}{' '}
                  ردیف‌های GSC محدود به داده‌های نگه‌داشته‌شده‌اند و حجم کل بازار یا همهٔ جست‌وجوها نیستند.
                </p>
              </div>
              <a
                href='/dashboard/sites'
                className='text-primary inline-flex items-center gap-1 text-xs font-medium underline-offset-4 hover:underline'
              >
                وضعیت اتصال و همگام‌سازی <IconArrowUpRight size={15} aria-hidden='true' />
              </a>
            </CardContent>
          </Card>
          <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-4'>
            <Metric
              label='عبارت‌های بررسی‌نشده'
              value={n(data.gsc.candidates.length)}
              detail={`حداکثر ${n(data.gsc.candidate_limit)} عبارت برتر؛ از ردیف‌های GSC این سایت`}
            />
            <Metric
              label='تازه در نمونه'
              value={
                data.gsc.previous_days >= Math.max(7, Math.floor(days / 2)) ? n(newlySeen) : '—'
              }
              detail={`پوشش بازهٔ قبل: ${n(data.gsc.previous_days)} روز؛ نبود در نمونه، نبود تقاضا نیست`}
            />
            <Metric
              label='جست‌وجوهای پرسشی'
              value={n(seenQuestions)}
              detail='متن مشاهده‌شده در Google Search؛ پرسش خصوصیِ ابزارهای AI نیست'
            />
            <Metric
              label='صفحات رقیب در پایش'
              value={n(data.competitors.tracked_pages.length)}
              detail='URLهای انتخاب‌شده توسط تیم؛ تازه‌سازی خودکار هر ۲۴ ساعت'
            />
          </div>
          <div className='grid gap-4 xl:grid-cols-[1.6fr_1fr]'>
            <Card>
              <CardHeader>
                <CardTitle>روند دیده‌شدن عبارت‌های ثبت‌شده</CardTitle>
                <CardDescription>
                  ایمپرشن و کلیک از ردیف‌های query/page در GSC؛ این نمودار ترافیک کل سایت نیست.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {data.gsc.daily.length ? (
                  <ChartContainer
                    config={{
                      impressions: { label: 'نمایش', color: 'var(--chart-1)' },
                      clicks: { label: 'کلیک', color: 'var(--chart-2)' }
                    }}
                    className='aspect-auto h-64 w-full'
                  >
                    <AreaChart data={data.gsc.daily} accessibilityLayer>
                      <CartesianGrid vertical={false} />
                      <XAxis dataKey='date' tickFormatter={(value: string) => value.slice(5)} />
                      <YAxis width={40} allowDecimals={false} />
                      <ChartTooltip content={<ChartTooltipContent />} />
                      <Area
                        type='monotone'
                        dataKey='impressions'
                        stroke='var(--color-impressions)'
                        fill='var(--color-impressions)'
                        fillOpacity={0.15}
                        isAnimationActive={false}
                      />
                      <Area
                        type='monotone'
                        dataKey='clicks'
                        stroke='var(--color-clicks)'
                        fill='var(--color-clicks)'
                        fillOpacity={0.08}
                        isAnimationActive={false}
                      />
                    </AreaChart>
                  </ChartContainer>
                ) : (
                  <p className='text-muted-foreground py-12 text-center text-sm'>
                    دادهٔ روزانهٔ GSC برای این سایت موجود نیست.
                  </p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>از داده تا اقدام</CardTitle>
                <CardDescription>هر مرحله صاحب منبع و صفحهٔ مقصد است.</CardDescription>
              </CardHeader>
              <CardContent className='space-y-3 text-sm'>
                <div className='rounded-lg border p-3'>
                  <strong>۱. انتخاب عبارت</strong>
                  <p className='text-muted-foreground mt-1'>
                    عبارت‌های جدید را از جدول پایین بررسی و به فهرست کلمات اضافه کنید.
                  </p>
                </div>
                <div className='rounded-lg border p-3'>
                  <strong>۲. بررسی قصد و رقیب</strong>
                  <p className='text-muted-foreground mt-1'>
                    صفحهٔ رقیب و صفحهٔ خودی را کنار هم ببینید؛ تعداد کلمات به‌تنهایی امتیاز کیفیت نیست.
                  </p>
                </div>
                <div className='rounded-lg border p-3'>
                  <strong>۳. پایش پرسش و محتوا</strong>
                  <p className='text-muted-foreground mt-1'>
                    پرسش‌های مناسب را برای پایش ثبت کنید و به برنامهٔ محتوا ببرید.
                  </p>
                </div>
                <div className='flex flex-wrap gap-2'>
                  <a
                    className='text-primary underline-offset-4 hover:underline'
                    href='/dashboard/keywords'
                  >
                    فهرست کلمات
                  </a>
                  <a
                    className='text-primary underline-offset-4 hover:underline'
                    href='/dashboard/ai-visibility'
                  >
                    پایش AI
                  </a>
                  <a
                    className='text-primary underline-offset-4 hover:underline'
                    href='/dashboard/calendar'
                  >
                    تقویم محتوا
                  </a>
                </div>
              </CardContent>
            </Card>
          </div>
          <Tabs defaultValue='keywords' className='space-y-3'>
            <TabsList className='h-auto flex-wrap'>
              <TabsTrigger value='keywords'>کشف کلیدواژه</TabsTrigger>
              <TabsTrigger value='questions'>پرسش‌های خریدار</TabsTrigger>
              <TabsTrigger value='competitors'>تحلیل رقبا</TabsTrigger>
            </TabsList>
            <TabsContent value='keywords' className='space-y-3'>
              <Card>
                <CardHeader>
                  <CardTitle>عبارت‌های تازه برای بررسی</CardTitle>
                  <CardDescription>
                    اولویت بر اساس نمایش در سایت خودمان است. «تازه» فقط یعنی در بازهٔ قبلیِ دادهٔ
                    نگه‌داشته‌شده مشاهده نشده است.
                  </CardDescription>
                </CardHeader>
                <CardContent className='space-y-3'>
                  <Input
                    aria-label='جست‌وجوی عبارت'
                    placeholder='جست‌وجو در عبارت‌ها…'
                    value={filter}
                    onChange={(event) => setFilter(event.target.value)}
                    className='max-w-sm'
                  />
                  <div className='overflow-x-auto rounded-lg border'>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>عبارت</TableHead>
                          <TableHead>سیگنال</TableHead>
                          <TableHead>نمایش</TableHead>
                          <TableHead>بازهٔ قبل</TableHead>
                          <TableHead>کلیک</TableHead>
                          <TableHead>جایگاه</TableHead>
                          <TableHead>صفحهٔ دیده‌شده</TableHead>
                          <TableHead>تصمیم</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {candidates.map((row) => (
                          <TableRow key={row.query}>
                            <TableCell className='min-w-44 font-medium'>{row.query}</TableCell>
                            <TableCell>
                              <Badge variant='outline'>{signalLabel[row.signal]}</Badge>
                            </TableCell>
                            <TableCell>{n(row.impressions)}</TableCell>
                            <TableCell>
                              {data.gsc.previous_days ? n(row.previous_impressions) : '—'}
                            </TableCell>
                            <TableCell>{n(row.clicks)}</TableCell>
                            <TableCell>{row.position == null ? '—' : n(row.position)}</TableCell>
                            <TableCell
                              className='max-w-56 truncate text-xs'
                              dir='ltr'
                              title={row.top_page ?? ''}
                            >
                              {row.top_page ?? '—'}
                            </TableCell>
                            <TableCell>
                              <Button
                                size='sm'
                                variant='outline'
                                disabled={busy}
                                onClick={() => void saveKeyword(row)}
                              >
                                ثبت کلمه
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                        {!candidates.length && (
                          <TableRow>
                            <TableCell
                              colSpan={8}
                              className='text-muted-foreground py-8 text-center'
                            >
                              عبارت ثبت‌نشده‌ای برای این فیلتر پیدا نشد؛ اتصال GSC و بازه را بررسی
                              کنید.
                            </TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </div>
                  <p className='text-muted-foreground text-xs'>
                    حداکثر {n(data.gsc.query_scan_limit)} عبارت از ردیف‌های نگه‌داشته‌شده بررسی و{' '}
                    {n(data.gsc.candidate_limit)} نامزد نمایش داده می‌شود؛ معیار «تازه» فقط با پوشش
                    کافیِ بازهٔ قبل فعال است.
                  </p>
                </CardContent>
              </Card>
            </TabsContent>
            <TabsContent value='questions' className='space-y-3'>
              <Card className='border-primary/20'>
                <CardContent className='py-4 text-sm leading-7'>
                  <strong>مرز داده:</strong> متن گفت‌وگوی خصوصی کاربران ChatGPT، Gemini و سایر
                  ابزارها در اختیار سایت نیست. این بخش پرسش‌های مشاهده‌شده در جست‌وجوی گوگل، فرضیه‌های
                  پرسشی ساخته‌شده از همان عبارت‌ها و پرسش‌های ثبت‌شده توسط تیم را جدا نشان می‌دهد. نمونهٔ
                  پاسخ AI فقط در صفحهٔ پایش AI ثبت می‌شود.
                </CardContent>
              </Card>
              <div className='grid gap-4 xl:grid-cols-2'>
                <Card>
                  <CardHeader>
                    <CardTitle>پرسش‌های مشاهده‌شده در Google Search</CardTitle>
                    <CardDescription>
                      متن خودِ query در GSC؛ منبع و صفحهٔ دیده‌شده محفوظ است.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className='space-y-2'>
                    {data.questions.observed_search_questions.map((row) => (
                      <div
                        key={row.query}
                        className='flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3'
                      >
                        <div>
                          <strong className='text-sm'>{row.query}</strong>
                          <p className='text-muted-foreground text-xs'>
                            {n(row.impressions)} نمایش · {row.top_page || 'صفحه نامشخص'}
                          </p>
                        </div>
                        <Button
                          size='sm'
                          variant='outline'
                          disabled={busy || row.query.length < 8}
                          onClick={() => void saveQuestion(row.query, row.query, row.top_page)}
                        >
                          ثبت برای پایش
                        </Button>
                      </div>
                    ))}
                    {!data.questions.observed_search_questions.length && (
                      <p className='text-muted-foreground text-sm'>
                        پرسش صریحی در ردیف‌های نگه‌داشته‌شده دیده نشد.
                      </p>
                    )}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle>فرضیه‌های پرسشی برای بررسی</CardTitle>
                    <CardDescription>
                      از عبارت‌های GSC ساخته شده‌اند؛ شواهدِ تقاضای همین جمله یا سؤال AI محسوب نمی‌شوند.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className='space-y-2'>
                    {data.questions.modeled_buyer_questions.map((row) => (
                      <div
                        key={row.query}
                        className='flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3'
                      >
                        <div>
                          <strong className='text-sm'>{row.question}</strong>
                          <p className='text-muted-foreground text-xs'>
                            برگرفته از «{row.query}» · {n(row.impressions)} نمایش در GSC
                          </p>
                        </div>
                        <Button
                          size='sm'
                          variant='outline'
                          disabled={busy}
                          onClick={() => void saveQuestion(row.question, row.query, row.top_page)}
                        >
                          ثبت برای پایش
                        </Button>
                      </div>
                    ))}
                    {!data.questions.modeled_buyer_questions.length && (
                      <p className='text-muted-foreground text-sm'>
                        برای ساخت فرضیه، ابتدا دادهٔ GSC لازم است.
                      </p>
                    )}
                  </CardContent>
                </Card>
              </div>
              <Card>
                <CardHeader>
                  <CardTitle>پرسش‌های در حال پایش</CardTitle>
                  <CardDescription>تعداد نمونه‌ها، تعداد کاربران واقعی نیست.</CardDescription>
                </CardHeader>
                <CardContent className='space-y-2'>
                  {data.questions.tracked_prompts.map((row) => (
                    <div
                      key={row.id}
                      className='flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm'
                    >
                      <span>{row.question}</span>
                      <span className='text-muted-foreground text-xs'>
                        {n(row.samples)} نمونه · آخرین مشاهده: {dateLabel(row.last_observed_at)}
                      </span>
                    </div>
                  ))}
                  {!data.questions.tracked_prompts.length && (
                    <p className='text-muted-foreground text-sm'>هنوز پرسشی ثبت نشده است.</p>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
            <TabsContent value='competitors' className='space-y-3'>
              <Card>
                <CardHeader>
                  <CardTitle>افزودن صفحهٔ رقیب</CardTitle>
                  <CardDescription>
                    یک URL عمومیِ HTTPS را برای مقایسهٔ عنوان، توضیح، تیترها و حجم تقریبی متن انتخاب
                    کنید. سرویس هر ۲۴ ساعت آن را بازخوانی می‌کند.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <form
                    onSubmit={(event) => void addCompetitor(event)}
                    className='grid gap-3 md:grid-cols-2 xl:grid-cols-[1.3fr_1fr_1.3fr_auto] xl:items-end'
                  >
                    <div className='space-y-1'>
                      <Label htmlFor='competitor-url'>URL صفحهٔ رقیب</Label>
                      <Input
                        id='competitor-url'
                        type='url'
                        required
                        placeholder='https://example.com/category/...'
                        dir='ltr'
                        value={competitorUrl}
                        onChange={(event) => setCompetitorUrl(event.target.value)}
                      />
                    </div>
                    <div className='space-y-1'>
                      <Label htmlFor='focus-query'>عبارت مورد مقایسه</Label>
                      <Input
                        id='focus-query'
                        value={focusQuery}
                        onChange={(event) => setFocusQuery(event.target.value)}
                        placeholder='مثلاً شلوار راسته مردانه'
                      />
                    </div>
                    <div className='space-y-1'>
                      <Label htmlFor='own-url'>صفحهٔ خودمان (اختیاری)</Label>
                      <Input
                        id='own-url'
                        type='url'
                        dir='ltr'
                        value={ownUrl}
                        onChange={(event) => setOwnUrl(event.target.value)}
                        placeholder='https://salimore.com/...'
                      />
                    </div>
                    <Button type='submit' disabled={busy}>
                      افزودن به پایش
                    </Button>
                  </form>
                </CardContent>
              </Card>
              <div className='grid gap-4 xl:grid-cols-2'>
                {data.competitors.tracked_pages.map((row) => (
                  <Card key={row.id}>
                    <CardHeader className='space-y-2'>
                      <div className='flex flex-wrap items-center justify-between gap-2'>
                        <CardTitle className='text-base'>
                          {row.title || new URL(row.url).hostname}
                        </CardTitle>
                        <Badge variant='outline'>
                          {row.status === 'ready'
                            ? 'بررسی‌شده'
                            : row.status === 'queued'
                              ? 'در صف'
                              : row.status === 'error'
                                ? 'خطای واکشی'
                                : 'در انتظار'}
                        </Badge>
                      </div>
                      <CardDescription dir='ltr' className='truncate' title={row.url}>
                        {row.url}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className='space-y-3 text-sm'>
                      <div className='flex flex-wrap gap-2 text-xs'>
                        <Badge variant='secondary'>عبارت: {row.focus_query || 'تعیین نشده'}</Badge>
                        <span className='text-muted-foreground'>
                          آخرین بررسی: {dateLabel(row.last_checked_at)}
                        </span>
                      </div>
                      {row.status === 'error' && (
                        <p className='text-destructive text-xs'>
                          بازخوانی ناموفق: {row.error_code || 'نامشخص'}
                        </p>
                      )}
                      {row.status === 'ready' && (
                        <>
                          <div className='grid gap-3 rounded-lg border p-3 sm:grid-cols-2'>
                            <div>
                              <strong>صفحهٔ رقیب</strong>
                              <p className='text-muted-foreground mt-2'>
                                عنوان: {row.title || 'ثبت نشده'}
                              </p>
                              <p className='text-muted-foreground'>
                                H1: {row.h1.join('، ') || 'ثبت نشده'}
                              </p>
                              <p className='text-muted-foreground'>
                                H2: {n(row.h2.length)} · واژهٔ تقریبی: {n(row.word_count)}
                              </p>
                              <p className='text-muted-foreground line-clamp-3'>
                                توضیح: {row.meta_description || 'ثبت نشده'}
                              </p>
                            </div>
                            <div>
                              <strong>صفحهٔ خودمان</strong>
                              {row.own_page ? (
                                <>
                                  <p className='text-muted-foreground mt-2'>
                                    عنوان: {row.own_page.title || 'ثبت نشده'}
                                  </p>
                                  <p className='text-muted-foreground'>
                                    H1: {row.own_page.h1.join('، ') || 'ثبت نشده'}
                                  </p>
                                  <p className='text-muted-foreground'>
                                    H2: {n(row.own_page.h2.length)} · واژهٔ تقریبی:{' '}
                                    {n(row.own_page.word_count)}
                                  </p>
                                  <p className='text-muted-foreground line-clamp-3'>
                                    توضیح: {row.own_page.meta_description || 'ثبت نشده'}
                                  </p>
                                </>
                              ) : (
                                <p className='text-muted-foreground mt-2'>
                                  صفحهٔ خودی تعیین نشده یا هنوز خزش نشده است.
                                </p>
                              )}
                            </div>
                          </div>
                          {!!row.review_headings.length && (
                            <div className='rounded-lg border border-primary/20 bg-primary/[0.035] p-3'>
                              <strong>تیترهای رقیب برای بررسی</strong>
                              <p className='text-muted-foreground mt-1 text-xs'>
                                این تیترها در H2 صفحهٔ خودمان با همین متن دیده نشدند؛ پیش از افزودن
                                به محتوا، ارتباطشان با نیاز خریدار را بررسی کنید.
                              </p>
                              <ul className='mt-2 list-inside list-disc space-y-1 text-xs'>
                                {row.review_headings.map((heading) => (
                                  <li key={heading}>{heading}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </>
                      )}
                      <div className='flex flex-wrap gap-2'>
                        <Button
                          size='sm'
                          variant='outline'
                          disabled={busy || row.status === 'queued'}
                          onClick={() => void refreshCompetitor(row.id)}
                        >
                          بازخوانی
                        </Button>
                        <a
                          href={row.url}
                          target='_blank'
                          rel='noopener noreferrer'
                          className='inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-xs hover:bg-muted'
                        >
                          بازکردن صفحه <IconArrowUpRight size={14} aria-hidden='true' />
                        </a>
                        <Button
                          size='sm'
                          variant='ghost'
                          disabled={busy}
                          onClick={() => void removeCompetitor(row.id)}
                        >
                          حذف از پایش
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
                {!data.competitors.tracked_pages.length && (
                  <Card>
                    <CardContent className='text-muted-foreground py-10 text-center text-sm'>
                      هنوز صفحهٔ رقیبی ثبت نشده است. از یک عبارت مهم شروع کنید و صفحهٔ خودی و رقیب را
                      کنار هم بگذارید.
                    </CardContent>
                  </Card>
                )}
              </div>
              <Card>
                <CardHeader>
                  <CardTitle>دامنه‌های دیده‌شده در نمونه‌های پاسخ AI</CardTitle>
                  <CardDescription>
                    فقط از استنادهایی که تیم ثبت یا در نمونهٔ API مشاهده کرده است؛ جایگاه گوگل یا سهم
                    بازار نیست.
                  </CardDescription>
                </CardHeader>
                <CardContent className='space-y-2'>
                  {data.competitors.ai_citation_domains.map((row) => (
                    <div
                      key={row.domain}
                      className='flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm'
                    >
                      <span dir='ltr'>{row.domain}</span>
                      <span className='text-muted-foreground text-xs'>
                        {n(row.mentions)} استناد در نمونه‌ها · {dateLabel(row.last_observed_at)}
                      </span>
                    </div>
                  ))}
                  {!data.competitors.ai_citation_domains.length && (
                    <p className='text-muted-foreground text-sm'>
                      هنوز استناد بیرونیِ ثبت‌شده‌ای وجود ندارد. این به معنی نبود رقیب نیست.
                    </p>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}
