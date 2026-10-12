'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ChartContainer, ChartTooltip, ChartTooltipContent } from '@/components/ui/chart';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog';
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
import { Textarea } from '@/components/ui/textarea';
import { ApiError, api, type Site } from '@/lib/api/client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { toast } from 'sonner';

type ReferralSource = {
  platform: string;
  sessions: number;
  engaged_sessions: number;
  transactions: number | null;
  purchase_revenue: number | null;
};
type ReferralLanding = {
  landing_page: string;
  sessions: number;
  transactions: number | null;
  purchase_revenue: number | null;
};
type OfficialPlatform = {
  platform: string;
  impressions: number | null;
  citations: number | null;
  page_impressions: number | null;
  page_citations: number | null;
  records: number;
  latest_date: string;
};
type Summary = {
  period: { start: string; end: string; days: number };
  referrals: {
    status: string;
    coverage: string;
    last_sync: string | null;
    sessions: number | null;
    engaged_sessions: number | null;
    transactions: number | null;
    purchase_revenue: number | null;
    currency: string | null;
    sources: ReferralSource[];
    landing_pages: ReferralLanding[];
    daily: { date: string; sessions: number }[];
  };
  official: { status: string; platforms: OfficialPlatform[] };
  prompts: {
    active: number;
    samples: number;
    assessed: number;
    mentions: number;
    mention_rate: number | null;
    citations: number;
    own_citations: number;
  };
};
type Prompt = {
  id: number;
  question: string;
  topic: string;
  target_url: string;
  intent: string;
  locale: string;
  market: string;
  active: number;
  samples: number;
  last_observed_at: string | null;
};
type Observation = {
  id: number;
  prompt_id: number;
  question: string;
  target_url: string;
  provider: string;
  model: string;
  observed_at: string;
  capture_method: string;
  answer_text: string;
  brand_mentioned: number | null;
  run_status: string;
  competitors: string[];
  citations: { url: string; domain: string; citation_kind: string; is_own_domain: number }[];
};
type Suggestion = {
  query: string;
  page: string;
  clicks: number;
  impressions: number;
  position: number | null;
};

const fa = new Intl.NumberFormat('fa-IR');
const number = (value: number | null | undefined) => (value == null ? '—' : fa.format(value));
const PLATFORM_FA: Record<string, string> = {
  chatgpt: 'ChatGPT',
  perplexity: 'Perplexity',
  claude: 'Claude',
  gemini: 'Gemini',
  copilot: 'Copilot',
  poe: 'Poe',
  you: 'You.com',
  phind: 'Phind',
  grok: 'Grok',
  mistral: 'Mistral',
  google_ai_search: 'Google AI در جست‌وجو',
  google_ai_discover: 'Google AI در دیسکاور',
  bing_ai: 'Bing AI'
};

function metric(value: number | null, label: string, detail: string) {
  return (
    <Card>
      <CardHeader className='pb-2'>
        <CardDescription>{label}</CardDescription>
        <CardTitle className='text-2xl tabular-nums'>{number(value)}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className='text-muted-foreground text-xs leading-5'>{detail}</p>
      </CardContent>
    </Card>
  );
}

function parseOfficialRows(input: string, platform: string) {
  const lines = input
    .trim()
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const rows: {
    date: string;
    platform: string;
    page_url?: string;
    impressions?: number;
    citations?: number;
  }[] = [];
  for (const [index, line] of lines.entries()) {
    const delimiter = line.includes('\t') ? '\t' : ',';
    const cells = line.split(delimiter).map((part) => part.trim().replace(/^"|"$/g, ''));
    if (index === 0 && /^(date|تاریخ)$/i.test(cells[0])) continue;
    if (cells.length !== 2 && cells.length !== 3)
      throw new Error(`ردیف ${index + 1}: قالب باید «تاریخ، تعداد» یا «تاریخ، URL، تعداد» باشد.`);
    const [date, middle, last] = cells;
    const count = Number(cells.length === 2 ? middle : last);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isSafeInteger(count) || count < 0)
      throw new Error(`ردیف ${index + 1}: تاریخ ISO یا تعداد نامعتبر است.`);
    if (cells.length === 3 && !/^https?:\/\//.test(middle))
      throw new Error(`ردیف ${index + 1}: URL معتبر نیست.`);
    rows.push({
      date,
      platform,
      ...(cells.length === 3 ? { page_url: middle } : {}),
      ...(platform === 'bing_ai' ? { citations: count } : { impressions: count })
    });
  }
  if (!rows.length) throw new Error('حداقل یک ردیف داده وارد کنید.');
  if (rows.length > 2000) throw new Error('هر بار حداکثر ۲۰۰۰ ردیف وارد کنید.');
  return rows;
}

export function AiVisibilityDashboard({
  sites,
  initialSiteId
}: {
  sites: Site[];
  initialSiteId: string;
}) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [days, setDays] = useState(28);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [suggestionDate, setSuggestionDate] = useState<string | null>(null);
  const [probeAvailable, setProbeAvailable] = useState(false);
  const [promptOpen, setPromptOpen] = useState(false);
  const [recordPrompt, setRecordPrompt] = useState<Prompt | null>(null);
  const [reviewTarget, setReviewTarget] = useState<Observation | null>(null);
  const [reviewMention, setReviewMention] = useState('yes');
  const [reviewCompetitors, setReviewCompetitors] = useState('');
  const [saving, setSaving] = useState(false);
  const [question, setQuestion] = useState('');
  const [topic, setTopic] = useState('');
  const [targetUrl, setTargetUrl] = useState('');
  const [intent, setIntent] = useState('commercial');
  const [provider, setProvider] = useState('ChatGPT');
  const [model, setModel] = useState('');
  const [observedAt, setObservedAt] = useState(new Date().toISOString().slice(0, 10));
  const [answer, setAnswer] = useState('');
  const [mentioned, setMentioned] = useState('unknown');
  const [citations, setCitations] = useState('');
  const [competitors, setCompetitors] = useState('');
  const [officialPlatform, setOfficialPlatform] = useState('google_ai_search');
  const [officialLabel, setOfficialLabel] = useState('');
  const [officialRows, setOfficialRows] = useState('');

  const path = useMemo(() => `/sites/${encodeURIComponent(siteId)}/ai-visibility`, [siteId]);
  const reload = useCallback(() => setRefresh((value) => value + 1), []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    Promise.all([
      api<Summary>(`${path}/summary?days=${days}`),
      api<{ items: Prompt[]; probe_available: boolean }>(`${path}/prompts`),
      api<{ items: Observation[] }>(`${path}/observations?limit=80`),
      api<{ items: Suggestion[]; date_to: string | null }>(`${path}/prompt-suggestions`)
    ])
      .then(([nextSummary, nextPrompts, nextObservations, nextSuggestions]) => {
        if (!active) return;
        setSummary(nextSummary);
        setPrompts(nextPrompts.items);
        setProbeAvailable(nextPrompts.probe_available);
        setObservations(nextObservations.items);
        setSuggestions(nextSuggestions.items);
        setSuggestionDate(nextSuggestions.date_to);
      })
      .catch((cause) => {
        if (active) setError(cause instanceof Error ? cause.message : 'داده‌های AEO بارگیری نشد.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [path, days, refresh]);

  async function savePrompt(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await api(`${path}/prompts`, {
        method: 'POST',
        json: { question, topic, target_url: targetUrl || null, intent }
      });
      setPromptOpen(false);
      setQuestion('');
      setTopic('');
      setTargetUrl('');
      reload();
      toast.success('پرسش به پایلوت اضافه شد.');
    } catch (cause) {
      toast.error(cause instanceof ApiError ? cause.message : 'ثبت پرسش ناموفق بود.');
    } finally {
      setSaving(false);
    }
  }

  async function saveObservation(event: React.FormEvent) {
    event.preventDefault();
    if (!recordPrompt) return;
    setSaving(true);
    try {
      const urls = citations
        .split(/\r?\n/)
        .map((url) => url.trim())
        .filter(Boolean);
      await api(`${path}/prompts/${recordPrompt.id}/observations`, {
        method: 'POST',
        json: {
          provider,
          model,
          observed_at: observedAt,
          answer_text: answer,
          brand_mentioned: mentioned === 'unknown' ? null : mentioned === 'yes',
          competitors: competitors
            .split(',')
            .map((name) => name.trim())
            .filter(Boolean),
          citations: urls.map((url) => ({ url, kind: 'source' }))
        }
      });
      setRecordPrompt(null);
      setAnswer('');
      setCitations('');
      setCompetitors('');
      reload();
      toast.success('پاسخ خام و شواهد آن ثبت شد.');
    } catch (cause) {
      toast.error(cause instanceof ApiError ? cause.message : 'ثبت مشاهده ناموفق بود.');
    } finally {
      setSaving(false);
    }
  }

  async function importOfficial(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      const rows = parseOfficialRows(officialRows, officialPlatform);
      await api(`${path}/official-import`, {
        method: 'POST',
        json: { source_label: officialLabel, rows }
      });
      setOfficialRows('');
      reload();
      toast.success(`${fa.format(rows.length)} ردیف با برچسب منبع ثبت شد.`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'ورود گزارش ناموفق بود.');
    } finally {
      setSaving(false);
    }
  }

  async function probePrompt(prompt: Prompt) {
    setSaving(true);
    try {
      await api(`${path}/prompts/${prompt.id}/probe`, { method: 'POST' });
      reload();
      toast.success('نمونهٔ API همراه پاسخ خام و استنادها ثبت شد؛ ذکر برند را بازبینی کنید.');
    } catch (cause) {
      toast.error(cause instanceof ApiError ? cause.message : 'نمونه‌گیری انجام نشد.');
    } finally {
      setSaving(false);
    }
  }

  function openReview(row: Observation) {
    setReviewTarget(row);
    setReviewMention(row.brand_mentioned === 0 ? 'no' : 'yes');
    setReviewCompetitors(row.competitors.join('، '));
  }

  async function saveReview(event: React.FormEvent) {
    event.preventDefault();
    if (!reviewTarget) return;
    setSaving(true);
    try {
      await api(`${path}/observations/${reviewTarget.id}/review`, {
        method: 'PATCH',
        json: {
          brand_mentioned: reviewMention === 'yes',
          competitors: reviewCompetitors
            .split(/[,،]/)
            .map((name) => name.trim())
            .filter(Boolean)
        }
      });
      setReviewTarget(null);
      reload();
      toast.success('ارزیابی پاسخ ثبت شد.');
    } catch (cause) {
      toast.error(cause instanceof ApiError ? cause.message : 'ثبت ارزیابی ناموفق بود.');
    } finally {
      setSaving(false);
    }
  }

  function startFromSuggestion(row: Suggestion) {
    setQuestion(row.query.length >= 8 ? row.query : `برای «${row.query}» چه گزینه‌هایی مناسب‌اند؟`);
    setTopic(row.query);
    setTargetUrl(row.page);
    setPromptOpen(true);
  }

  const google = summary?.official.platforms.find((row) => row.platform === 'google_ai_search');
  const bing = summary?.official.platforms.find((row) => row.platform === 'bing_ai');
  const site = sites.find((item) => item.site_id === siteId);
  const untestedPrompt = prompts.find((row) => row.active && row.samples === 0);
  const unreviewed = observations.find((row) => row.brand_mentioned == null);
  const missedPrompt = prompts.find(
    (row) =>
      row.active &&
      observations.find((observation) => observation.prompt_id === row.id)?.brand_mentioned === 0
  );
  return (
    <div className='space-y-5'>
      <div className='flex flex-wrap items-center gap-3'>
        <Label htmlFor='ai-site'>سایت</Label>
        <NativeSelect
          id='ai-site'
          value={siteId}
          onChange={(event) => setSiteId(event.target.value)}
        >
          <>
            {sites.map((item) => (
              <NativeSelectOption key={item.site_id} value={item.site_id}>
                {item.name}
              </NativeSelectOption>
            ))}
          </>
        </NativeSelect>
        <Label htmlFor='ai-period'>بازه</Label>
        <NativeSelect
          id='ai-period'
          value={days}
          onChange={(event) => setDays(Number(event.target.value))}
        >
          <>
            <NativeSelectOption value={7}>۷ روز</NativeSelectOption>
            <NativeSelectOption value={28}>۲۸ روز</NativeSelectOption>
            <NativeSelectOption value={90}>۹۰ روز</NativeSelectOption>
          </>
        </NativeSelect>
        <Button variant='outline' size='sm' onClick={reload} disabled={loading}>
          به‌روزرسانی
        </Button>
        {summary && (
          <span className='text-muted-foreground text-xs'>
            بازهٔ داده: {summary.period.start} تا {summary.period.end}
          </span>
        )}
      </div>
      {error && (
        <Card className='border-destructive/40'>
          <CardContent className='py-4 text-sm text-destructive'>{error}</CardContent>
        </Card>
      )}
      {loading && !summary && (
        <p role='status' className='text-muted-foreground py-8 text-sm'>
          در حال بارگیری شواهد جست‌وجوی AI…
        </p>
      )}
      {summary && (
        <>
          <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-5'>
            {metric(
              google?.impressions ?? null,
              'نمایش در Google AI',
              google?.impressions == null
                ? 'گزارش رسمیِ مجموع سایت وارد نشده است.'
                : 'Search Console؛ مجموع رسمی سایت'
            )}
            {metric(
              bing?.citations ?? null,
              'استناد در Bing AI',
              bing?.citations == null
                ? 'گزارش رسمیِ مجموع سایت وارد نشده است.'
                : 'Bing Webmaster؛ استناد، نه بازدید'
            )}
            {metric(
              summary.referrals.sessions,
              'ورودی قابل انتساب AI',
              summary.referrals.coverage === 'full_window'
                ? 'GA4؛ منابع ارجاع شناخته‌شده'
                : 'پوشش GA4 این بازه کامل یا مشخص نیست.'
            )}
            {metric(
              summary.referrals.transactions,
              'خرید گزارش‌شده از AI',
              summary.referrals.transactions == null
                ? 'دادهٔ خرید GA4 در این بازه قابل اتکا یا در دسترس نیست.'
                : 'گزارش GA4؛ صحت رهگیری خرید باید جدا تأیید شود.'
            )}
            {metric(
              summary.referrals.purchase_revenue,
              'درآمد قابل انتساب',
              summary.referrals.purchase_revenue == null
                ? 'درآمد GA4 در دسترس نیست یا واحد پول یکسان نیست.'
                : `GA4 · ${summary.referrals.currency ?? 'واحد پول نامشخص'}`
            )}
          </div>
          <Card className='border-primary/20 bg-primary/[0.035]'>
            <CardContent className='py-4 text-sm leading-7'>
              <strong>چطور این صفحه را بخوانیم؟</strong> نمایش گوگل، استناد بینگ، ارجاع GA4 و
              پاسخ‌های آزمایشی چهار سنجهٔ متفاوت‌اند. پاسخ آزمایشیِ مدل، تعداد کاربران یا رتبهٔ واقعی را
              نشان نمی‌دهد. نبود داده با صفر یکی نیست.
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>قدم‌های بعدی براساس شاهد</CardTitle>
              <CardDescription>
                هر پیشنهاد از دادهٔ همین سایت می‌آید؛ نتیجهٔ نمونهٔ AI باید توسط تیم بازبینی شود.
              </CardDescription>
            </CardHeader>
            <CardContent className='grid gap-3 lg:grid-cols-2'>
              {suggestions.length > 0 && prompts.length === 0 && (
                <div className='rounded-lg border p-3'>
                  <p className='font-medium text-sm'>از تقاضای ثبت‌شده در GSC شروع کنید</p>
                  <p className='text-muted-foreground my-2 text-xs'>
                    {number(suggestions[0].impressions)} نمایش برای «{suggestions[0].query}»؛ آن را
                    به پرسش ثابت و صفحهٔ هدف وصل کنید.
                  </p>
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() => startFromSuggestion(suggestions[0])}
                  >
                    ساخت پرسش
                  </Button>
                </div>
              )}
              {untestedPrompt && (
                <div className='rounded-lg border p-3'>
                  <p className='font-medium text-sm'>پرسش بدون پاسخ آزمایشی</p>
                  <p className='text-muted-foreground my-2 text-xs'>{untestedPrompt.question}</p>
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() => setRecordPrompt(untestedPrompt)}
                  >
                    ثبت نخستین پاسخ
                  </Button>
                </div>
              )}
              {unreviewed && (
                <div className='rounded-lg border p-3'>
                  <p className='font-medium text-sm'>پاسخ در انتظار ارزیابی انسانی</p>
                  <p className='text-muted-foreground my-2 text-xs'>
                    پاسخ {unreviewed.provider} برای «{unreviewed.question}» هنوز در نرخ ذکر برند
                    حساب نشده است.
                  </p>
                  <Button size='sm' variant='outline' onClick={() => openReview(unreviewed)}>
                    بازبینی پاسخ
                  </Button>
                </div>
              )}
              {missedPrompt && (
                <div className='rounded-lg border p-3'>
                  <p className='font-medium text-sm'>خلأ ذکر برند در یک نمونه</p>
                  <p className='text-muted-foreground my-2 text-xs'>
                    پاسخ ارزیابی‌شده برای «{missedPrompt.question}» برند را ذکر نکرده است. صفحهٔ هدف و
                    منابع رقیب را بررسی کنید؛ این حکم دربارهٔ کل بازار نیست.
                  </p>
                  {missedPrompt.target_url && (
                    <a
                      href={missedPrompt.target_url}
                      target='_blank'
                      rel='noopener noreferrer'
                      className='text-primary text-xs underline underline-offset-2'
                    >
                      باز کردن صفحهٔ هدف
                    </a>
                  )}
                </div>
              )}
              {summary.official.status === 'not_imported' && (
                <div className='rounded-lg border p-3'>
                  <p className='font-medium text-sm'>دادهٔ رسمی هنوز وارد نشده است</p>
                  <p className='text-muted-foreground mt-2 text-xs'>
                    برای سنجش نمایش واقعی Google AI یا استناد Bing AI، گزارش همان کنسول را در تب
                    «گزارش رسمی» وارد کنید.
                  </p>
                </div>
              )}
              {summary.referrals.coverage !== 'full_window' && (
                <div className='rounded-lg border p-3'>
                  <p className='font-medium text-sm'>پوشش ارجاع GA4 کامل نیست</p>
                  <p className='text-muted-foreground mt-2 text-xs'>
                    آخرین همگام‌سازی: {summary.referrals.last_sync ?? 'ناموجود'}؛ برای این بازه عدد
                    صفر نتیجه‌گیری نمی‌شود.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
          <Tabs defaultValue='measurement' className='space-y-4'>
            <TabsList className='h-auto flex-wrap'>
              <TabsTrigger value='measurement'>ورودی و فروش</TabsTrigger>
              <TabsTrigger value='prompts'>پرسش‌های خریدار</TabsTrigger>
              <TabsTrigger value='official'>گزارش رسمی</TabsTrigger>
            </TabsList>
            <TabsContent value='measurement' className='space-y-4'>
              <div className='grid gap-4 xl:grid-cols-[1.4fr_1fr]'>
                <Card>
                  <CardHeader>
                    <CardTitle>روند ارجاع قابل شناسایی</CardTitle>
                    <CardDescription>
                      نشست‌های گزارش‌شده در GA4؛ سایر ورودی‌های AI ممکن است بدون ارجاع قابل تشخیص
                      باشند.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {summary.referrals.daily.length ? (
                      <ChartContainer
                        config={{ sessions: { label: 'نشست', color: 'var(--chart-1)' } }}
                        className='aspect-auto h-56 w-full'
                      >
                        <AreaChart data={summary.referrals.daily} accessibilityLayer>
                          <CartesianGrid vertical={false} />
                          <XAxis dataKey='date' tickFormatter={(value: string) => value.slice(5)} />
                          <YAxis allowDecimals={false} width={32} />
                          <ChartTooltip content={<ChartTooltipContent />} />
                          <Area
                            type='monotone'
                            dataKey='sessions'
                            stroke='var(--color-sessions)'
                            fill='var(--color-sessions)'
                            fillOpacity={0.15}
                            isAnimationActive={false}
                          />
                        </AreaChart>
                      </ChartContainer>
                    ) : (
                      <p className='text-muted-foreground py-10 text-center text-sm'>
                        هنوز نشست قابل شناسایی برای این بازه ثبت نشده است؛ وضعیت پوشش را بررسی کنید.
                      </p>
                    )}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle>منبع‌های ارجاع</CardTitle>
                    <CardDescription>
                      فقط دامنه‌هایی که بتوان با اطمینان به یک ابزار AI نسبت داد.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className='space-y-3'>
                    {summary.referrals.sources.length ? (
                      summary.referrals.sources.map((row) => (
                        <div
                          key={row.platform}
                          className='flex items-center justify-between rounded-lg border px-3 py-2 text-sm'
                        >
                          <span>{PLATFORM_FA[row.platform] ?? row.platform}</span>
                          <strong>{number(row.sessions)} نشست</strong>
                        </div>
                      ))
                    ) : (
                      <p className='text-muted-foreground text-sm'>
                        داده‌ای برای منبع‌های شناخته‌شده ثبت نشده است.
                      </p>
                    )}
                    <p className='text-muted-foreground text-xs'>
                      آخرین همگام‌سازی: {summary.referrals.last_sync ?? 'انجام نشده'} · وضعیت:{' '}
                      {summary.referrals.status === 'error'
                        ? 'خطا'
                        : summary.referrals.coverage === 'full_window'
                          ? 'پوشش کامل'
                          : 'پوشش نامشخص/جزئی'}
                    </p>
                  </CardContent>
                </Card>
              </div>
              <Card>
                <CardHeader>
                  <CardTitle>صفحه‌های فرود</CardTitle>
                  <CardDescription>
                    کدام صفحه‌ها از ارجاع‌های قابل شناسایی AI بازدید گرفته‌اند؟
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className='overflow-x-auto'>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>صفحه</TableHead>
                          <TableHead>نشست</TableHead>
                          <TableHead>خرید GA4</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {summary.referrals.landing_pages.map((row) => (
                          <TableRow key={row.landing_page}>
                            <TableCell
                              className='max-w-[440px] truncate font-mono text-xs'
                              dir='ltr'
                            >
                              {row.landing_page}
                            </TableCell>
                            <TableCell>{number(row.sessions)}</TableCell>
                            <TableCell>{number(row.transactions)}</TableCell>
                          </TableRow>
                        ))}
                        {!summary.referrals.landing_pages.length && (
                          <TableRow>
                            <TableCell colSpan={3} className='text-muted-foreground text-center'>
                              هنوز صفحهٔ فرودی در این بازه ثبت نشده است.
                            </TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
            <TabsContent value='prompts' className='space-y-4'>
              <Card>
                <CardHeader className='flex flex-row flex-wrap items-center justify-between gap-3'>
                  <div>
                    <CardTitle>پایلوت پرسش‌های خریدار</CardTitle>
                    <CardDescription>
                      پرسش ثابت، بازار مشخص، پاسخ خام و منبع استناد؛ برای مقایسهٔ دوره‌ای.
                    </CardDescription>
                  </div>
                  <Button onClick={() => setPromptOpen(true)}>افزودن پرسش</Button>
                </CardHeader>
                <CardContent>
                  <div className='grid gap-3 sm:grid-cols-3'>
                    <div className='rounded-lg border p-3'>
                      <p className='text-muted-foreground text-xs'>پرسش فعال</p>
                      <strong className='text-lg'>{number(summary.prompts.active)}</strong>
                    </div>
                    <div className='rounded-lg border p-3'>
                      <p className='text-muted-foreground text-xs'>پاسخ ثبت‌شده</p>
                      <strong className='text-lg'>{number(summary.prompts.samples)}</strong>
                    </div>
                    <div className='rounded-lg border p-3'>
                      <p className='text-muted-foreground text-xs'>نرخ ذکر در نمونه</p>
                      <strong className='text-lg'>
                        {summary.prompts.mention_rate == null
                          ? '—'
                          : `${number(Math.round(summary.prompts.mention_rate * 100))}٪`}
                      </strong>
                      <span className='text-muted-foreground me-2 text-xs'>
                        از {number(summary.prompts.assessed)} پاسخ ارزیابی‌شده
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>فهرست پرسش‌ها</CardTitle>
                  <CardDescription>
                    هر پرسش را به یک موضوع و در صورت امکان به صفحهٔ هدف وصل کنید. نمونهٔ API هزینهٔ
                    سرویس دارد و تنها با کلیک شما اجرا می‌شود.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className='overflow-x-auto'>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>پرسش</TableHead>
                          <TableHead>موضوع / بازار</TableHead>
                          <TableHead>نمونه</TableHead>
                          <TableHead>اقدام</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {prompts.map((row) => (
                          <TableRow key={row.id}>
                            <TableCell className='max-w-[380px]'>
                              <div className='font-medium'>{row.question}</div>
                              {row.target_url && (
                                <a
                                  href={row.target_url}
                                  target='_blank'
                                  rel='noopener noreferrer'
                                  className='text-primary text-xs hover:underline'
                                >
                                  {row.target_url}
                                </a>
                              )}
                              {!row.active && (
                                <Badge variant='secondary' className='me-2'>
                                  غیرفعال
                                </Badge>
                              )}
                            </TableCell>
                            <TableCell>
                              {row.topic || '—'} · {row.locale}/{row.market}
                            </TableCell>
                            <TableCell>{number(row.samples)}</TableCell>
                            <TableCell>
                              <div className='flex flex-wrap gap-2'>
                                <Button
                                  size='sm'
                                  variant='outline'
                                  onClick={() => setRecordPrompt(row)}
                                >
                                  ثبت دستی
                                </Button>
                                <Button
                                  size='sm'
                                  variant='secondary'
                                  disabled={!probeAvailable || !row.active || saving}
                                  onClick={() => probePrompt(row)}
                                >
                                  نمونهٔ API
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                        {!prompts.length && (
                          <TableRow>
                            <TableCell colSpan={4} className='text-muted-foreground text-center'>
                              برای شروع، چند سؤال واقعیِ خریداران را ثبت کنید.
                            </TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </div>
                  {!probeAvailable && (
                    <p className='text-muted-foreground mt-3 text-xs'>
                      برای نمونهٔ خودکار، اتصال OpenAI را در تنظیمات AI فعال کنید.
                    </p>
                  )}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>سرنخ‌های واقعی از Search Console</CardTitle>
                  <CardDescription>
                    پرسش‌های پرنمایش در آخرین دادهٔ GSC ({suggestionDate ?? 'داده‌ای نیست'})؛ این‌ها
                    نمایش AI را ثابت نمی‌کنند.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className='grid gap-2 md:grid-cols-2'>
                    {suggestions.map((row) => (
                      <div
                        key={row.query + row.page}
                        className='flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3'
                      >
                        <div className='min-w-0'>
                          <p className='font-medium text-sm'>{row.query}</p>
                          <p className='text-muted-foreground text-xs'>
                            {number(row.impressions)} نمایش · {number(row.clicks)} کلیک · جایگاه{' '}
                            {number(row.position)}
                          </p>
                        </div>
                        <Button
                          size='sm'
                          variant='outline'
                          onClick={() => startFromSuggestion(row)}
                        >
                          تبدیل به پرسش
                        </Button>
                      </div>
                    ))}
                    {!suggestions.length && (
                      <p className='text-muted-foreground text-sm'>
                        دادهٔ GSC تازه یا پرسش واجد شرایط ثبت نشده است.
                      </p>
                    )}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>پاسخ‌ها و استنادهای ثبت‌شده</CardTitle>
                  <CardDescription>
                    متن خام و لینک‌ها برای بازبینی نگهداری می‌شوند؛ امتیاز تنها بدون شاهد ساخته
                    نمی‌شود.
                  </CardDescription>
                </CardHeader>
                <CardContent className='space-y-3'>
                  {observations.map((row) => (
                    <article key={row.id} className='space-y-2 rounded-xl border p-4'>
                      <div className='flex flex-wrap items-center gap-2'>
                        <strong className='text-sm'>{row.question}</strong>
                        <Badge variant='secondary'>{row.provider}</Badge>
                        <span className='text-muted-foreground text-xs'>{row.observed_at}</span>
                        <Badge variant='outline'>
                          {row.brand_mentioned == null
                            ? 'ذکر ارزیابی نشده'
                            : row.brand_mentioned
                              ? 'نام برند دیده شد'
                              : 'نام برند دیده نشد'}
                        </Badge>
                        <Badge variant='outline'>
                          {row.capture_method === 'provider_api'
                            ? 'نمونهٔ API؛ نه ترافیک واقعی'
                            : 'ثبت دستی'}
                        </Badge>
                        <Button size='sm' variant='ghost' onClick={() => openReview(row)}>
                          ارزیابی ذکر برند
                        </Button>
                      </div>
                      <p className='text-muted-foreground whitespace-pre-wrap text-sm'>
                        {row.answer_text}{' '}
                        {row.citations.map((citation, index) => (
                          <a
                            key={citation.url + citation.citation_kind}
                            href={citation.url}
                            target='_blank'
                            rel='noopener noreferrer'
                            className='text-primary underline underline-offset-2'
                            aria-label={`منبع ${index + 1}: ${citation.domain}`}
                          >
                            [{index + 1}]
                          </a>
                        ))}
                      </p>
                      {!!row.competitors.length && (
                        <p className='text-muted-foreground text-xs'>
                          رقبای ذکرشده: {row.competitors.join('، ')}
                        </p>
                      )}
                      <div className='flex flex-wrap gap-2'>
                        {row.citations.map((citation) => (
                          <a
                            key={citation.url + citation.citation_kind}
                            href={citation.url}
                            target='_blank'
                            rel='noopener noreferrer'
                            className={`rounded-md border px-2 py-1 text-xs hover:underline ${citation.is_own_domain ? 'border-primary/40 text-primary' : 'text-muted-foreground'}`}
                          >
                            {citation.domain}
                          </a>
                        ))}
                      </div>
                    </article>
                  ))}
                  {!observations.length && (
                    <p className='text-muted-foreground text-sm'>
                      هنوز پاسخی ثبت نشده است. نتیجهٔ هر آزمایش را همراه با متن و لینک‌های منبع وارد
                      کنید.
                    </p>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
            <TabsContent value='official' className='grid gap-4 xl:grid-cols-[1fr_1fr]'>
              <Card>
                <CardHeader>
                  <CardTitle>دادهٔ رسمی واردشده</CardTitle>
                  <CardDescription>
                    مجموع سایت و ردیف‌های صفحه‌ای جدا نمایش داده می‌شوند تا دوباره‌شماری رخ ندهد.
                  </CardDescription>
                </CardHeader>
                <CardContent className='space-y-3'>
                  {summary.official.platforms.map((row) => (
                    <div key={row.platform} className='rounded-lg border p-3 text-sm'>
                      <div className='flex justify-between'>
                        <strong>{PLATFORM_FA[row.platform] ?? row.platform}</strong>
                        <span className='text-muted-foreground'>تا {row.latest_date}</span>
                      </div>
                      <p className='mt-2'>
                        مجموع رسمی سایت:{' '}
                        {number(row.platform === 'bing_ai' ? row.citations : row.impressions)}
                      </p>
                      <p className='text-muted-foreground text-xs'>
                        جمع ردیف‌های صفحه‌ای:{' '}
                        {number(
                          row.platform === 'bing_ai' ? row.page_citations : row.page_impressions
                        )}
                        ؛ این عدد جای مجموع رسمی را نمی‌گیرد.
                      </p>
                    </div>
                  ))}
                  {!summary.official.platforms.length && (
                    <p className='text-muted-foreground text-sm'>
                      دادهٔ رسمی AI برای این بازه وارد نشده است.
                    </p>
                  )}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>ورود داده از کنسول‌ها</CardTitle>
                  <CardDescription>
                    فقط عددی را وارد کنید که از گزارش AI در Search Console یا Bing Webmaster
                    برداشته‌اید.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <form onSubmit={importOfficial} className='space-y-3'>
                    <div className='grid gap-3 sm:grid-cols-2'>
                      <div className='space-y-1'>
                        <Label htmlFor='official-platform'>منبع</Label>
                        <NativeSelect
                          id='official-platform'
                          value={officialPlatform}
                          onChange={(event) => setOfficialPlatform(event.target.value)}
                        >
                          <>
                            <NativeSelectOption value='google_ai_search'>
                              Google AI Search؛ نمایش
                            </NativeSelectOption>
                            <NativeSelectOption value='google_ai_discover'>
                              Google AI Discover؛ نمایش
                            </NativeSelectOption>
                            <NativeSelectOption value='bing_ai'>Bing AI؛ استناد</NativeSelectOption>
                          </>
                        </NativeSelect>
                      </div>
                      <div className='space-y-1'>
                        <Label htmlFor='official-label'>نام فایل یا گزارش</Label>
                        <Input
                          id='official-label'
                          required
                          value={officialLabel}
                          onChange={(event) => setOfficialLabel(event.target.value)}
                          placeholder='مثلاً خروجی GSC AI، مهر ۱۴۰۵'
                        />
                      </div>
                    </div>
                    <div className='space-y-1'>
                      <Label htmlFor='official-rows'>ردیف‌ها</Label>
                      <Textarea
                        id='official-rows'
                        required
                        value={officialRows}
                        onChange={(event) => setOfficialRows(event.target.value)}
                        rows={6}
                        dir='ltr'
                        placeholder={'2026-10-10,42\n2026-10-11,https://example.com/blog/a,8'}
                      />
                      <p className='text-muted-foreground text-xs'>
                        هر خط: تاریخ میلادی، تعداد؛ یا تاریخ، URL همان سایت، تعداد. مجموع سایت و
                        جزئیات صفحه را می‌توانید جدا وارد کنید.
                      </p>
                    </div>
                    <Button type='submit' disabled={saving}>
                      ثبت گزارش با منبع
                    </Button>
                  </form>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </>
      )}
      <Dialog open={promptOpen} onOpenChange={setPromptOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>پرسش جدید خریدار</DialogTitle>
            <DialogDescription>
              یک سؤال طبیعی و ثابت برای مقایسهٔ پاسخ‌ها در طول زمان بنویسید.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={savePrompt} className='space-y-3'>
            <div className='space-y-1'>
              <Label htmlFor='prompt-question'>پرسش</Label>
              <Textarea
                id='prompt-question'
                required
                minLength={8}
                maxLength={600}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder='مثلاً برای شلوار بگ مردانه چه کفشی مناسب است؟'
              />
            </div>
            <div className='grid gap-3 sm:grid-cols-2'>
              <div className='space-y-1'>
                <Label htmlFor='prompt-topic'>موضوع</Label>
                <Input
                  id='prompt-topic'
                  value={topic}
                  onChange={(event) => setTopic(event.target.value)}
                  placeholder='استایل مردانه'
                />
              </div>
              <div className='space-y-1'>
                <Label htmlFor='prompt-intent'>قصد جست‌وجو</Label>
                <NativeSelect
                  id='prompt-intent'
                  value={intent}
                  onChange={(event) => setIntent(event.target.value)}
                >
                  <>
                    <NativeSelectOption value='commercial'>بررسی برای خرید</NativeSelectOption>
                    <NativeSelectOption value='transactional'>خرید</NativeSelectOption>
                    <NativeSelectOption value='informational'>اطلاعاتی</NativeSelectOption>
                  </>
                </NativeSelect>
              </div>
            </div>
            <div className='space-y-1'>
              <Label htmlFor='prompt-target'>صفحهٔ هدف در {site?.name ?? 'سایت'} (اختیاری)</Label>
              <Input
                id='prompt-target'
                type='url'
                value={targetUrl}
                onChange={(event) => setTargetUrl(event.target.value)}
                placeholder={site?.canonical_url ?? 'https://example.com/page'}
              />
            </div>
            <Button type='submit' disabled={saving}>
              ثبت پرسش
            </Button>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog
        open={!!recordPrompt}
        onOpenChange={(open) => {
          if (!open) setRecordPrompt(null);
        }}
      >
        <DialogContent className='max-h-[90vh] overflow-y-auto'>
          <DialogHeader>
            <DialogTitle>ثبت پاسخ آزمایشی</DialogTitle>
            <DialogDescription>
              {recordPrompt?.question} — متن و لینک‌های واقعی پاسخ را ثبت کنید.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={saveObservation} className='space-y-3'>
            <div className='grid gap-3 sm:grid-cols-2'>
              <div className='space-y-1'>
                <Label htmlFor='observation-provider'>ابزار</Label>
                <NativeSelect
                  id='observation-provider'
                  value={provider}
                  onChange={(event) => setProvider(event.target.value)}
                >
                  <>
                    <NativeSelectOption value='ChatGPT'>ChatGPT</NativeSelectOption>
                    <NativeSelectOption value='Perplexity'>Perplexity</NativeSelectOption>
                    <NativeSelectOption value='Gemini'>Gemini</NativeSelectOption>
                    <NativeSelectOption value='Claude'>Claude</NativeSelectOption>
                    <NativeSelectOption value='Copilot'>Copilot</NativeSelectOption>
                  </>
                </NativeSelect>
              </div>
              <div className='space-y-1'>
                <Label htmlFor='observation-date'>تاریخ مشاهده</Label>
                <Input
                  id='observation-date'
                  type='date'
                  required
                  value={observedAt}
                  onChange={(event) => setObservedAt(event.target.value)}
                />
              </div>
            </div>
            <div className='space-y-1'>
              <Label htmlFor='observation-model'>مدل یا نسخه (اگر معلوم است)</Label>
              <Input
                id='observation-model'
                value={model}
                onChange={(event) => setModel(event.target.value)}
              />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='observation-answer'>متن پاسخ</Label>
              <Textarea
                id='observation-answer'
                required
                rows={6}
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
              />
            </div>
            <div className='grid gap-3 sm:grid-cols-2'>
              <div className='space-y-1'>
                <Label htmlFor='observation-mention'>آیا نام برند در پاسخ بود؟</Label>
                <NativeSelect
                  id='observation-mention'
                  value={mentioned}
                  onChange={(event) => setMentioned(event.target.value)}
                >
                  <>
                    <NativeSelectOption value='unknown'>ارزیابی نشده</NativeSelectOption>
                    <NativeSelectOption value='yes'>بله</NativeSelectOption>
                    <NativeSelectOption value='no'>خیر</NativeSelectOption>
                  </>
                </NativeSelect>
              </div>
              <div className='space-y-1'>
                <Label htmlFor='observation-competitors'>رقبای ذکرشده (با ویرگول)</Label>
                <Input
                  id='observation-competitors'
                  value={competitors}
                  onChange={(event) => setCompetitors(event.target.value)}
                />
              </div>
            </div>
            <div className='space-y-1'>
              <Label htmlFor='observation-citations'>لینک‌های استناد؛ هر خط یک URL</Label>
              <Textarea
                id='observation-citations'
                rows={3}
                dir='ltr'
                value={citations}
                onChange={(event) => setCitations(event.target.value)}
              />
            </div>
            <Button type='submit' disabled={saving}>
              ثبت پاسخ و شواهد
            </Button>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog
        open={!!reviewTarget}
        onOpenChange={(open) => {
          if (!open) setReviewTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>ارزیابی پاسخ</DialogTitle>
            <DialogDescription>
              براساس متن خام، ذکر برند و رقبای واقعی را مشخص کنید؛ نمونهٔ API خودکار ارزیابی نمی‌شود.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={saveReview} className='space-y-3'>
            <p className='max-h-40 overflow-y-auto rounded-lg border p-3 text-sm whitespace-pre-wrap'>
              {reviewTarget?.answer_text}
            </p>
            <div className='space-y-1'>
              <Label htmlFor='review-mention'>نام برند ذکر شده است؟</Label>
              <NativeSelect
                id='review-mention'
                value={reviewMention}
                onChange={(event) => setReviewMention(event.target.value)}
              >
                <>
                  <NativeSelectOption value='yes'>بله</NativeSelectOption>
                  <NativeSelectOption value='no'>خیر</NativeSelectOption>
                </>
              </NativeSelect>
            </div>
            <div className='space-y-1'>
              <Label htmlFor='review-competitors'>رقبای ذکرشده (با ویرگول)</Label>
              <Input
                id='review-competitors'
                value={reviewCompetitors}
                onChange={(event) => setReviewCompetitors(event.target.value)}
              />
            </div>
            <Button type='submit' disabled={saving}>
              ثبت ارزیابی
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
