'use client';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Progress } from '@/components/ui/progress';
import { GoogleAccountCard } from '@/features/sites/components/google-account-card';
import { GoogleSearchConsoleConnectionCard } from '@/features/sites/components/gsc-service-account-card';
import { cn } from '@/lib/utils';
import {
  ApiError,
  endpoints,
  type GoogleAccountStatus,
  type IntegrationBlock,
  type SaGscStatus
} from '@/lib/api/client';
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconArrowRight,
  IconBrandGoogle,
  IconBrandWordpress,
  IconChartDots3,
  IconCheck,
  IconCircleCheck,
  IconDatabase,
  IconPlayerPlay,
  IconRefresh,
  IconShieldCheck,
  IconSparkles,
  IconWorld
} from '@tabler/icons-react';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import {
  findExistingSiteByDomain,
  mergeDiscovery,
  normalizeWebsiteUrl,
  siteSlug,
  SYNC_BADGE_FA,
  type DiscoveredSite
} from '../lib';

const STEPS = [
  { title: 'اتصال داده', description: 'Search Console', icon: IconBrandGoogle },
  { title: 'انتخاب سایت', description: 'دامنه‌های قابل دسترس', icon: IconWorld },
  { title: 'اتصال محتوا', description: 'وردپرس، اختیاری', icon: IconBrandWordpress },
  { title: 'شروع تحلیل', description: 'دریافت داده زنده', icon: IconChartDots3 }
] as const;

type Created = { site_id: string; domain: string; wp_url?: string; existing: boolean };
type PropertyOption = { property_id: string; display_name: string | null };

function messageOf(error: unknown, fallback: string) {
  const message =
    error instanceof ApiError ? error.message : error instanceof Error ? error.message : '';
  if (/ProxyError|TransportError|oauth2\.googleapis\.com|502 Bad Gateway/i.test(message)) {
    return 'ارتباط سرور با Google برقرار نشد. شبکه یا VPN مربوط به Docker را بررسی و دوباره تلاش کنید.';
  }
  return message && message.length <= 240 ? message : fallback;
}

export function OnboardingWizard() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [sites, setSites] = useState<DiscoveredSite[] | null>(null);
  const [ga4All, setGa4All] = useState<PropertyOption[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [ga4Pick, setGa4Pick] = useState<Record<string, string>>({});
  const [created, setCreated] = useState<Created[]>([]);
  const [wpUrls, setWpUrls] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const selectedCount = Object.values(picked).filter(Boolean).length;

  const prepareSelectedSites = async () => {
    const chosen = (sites ?? []).filter((site) => picked[site.domain]);
    if (!chosen.length) return toast.error('حداقل یک سایت را انتخاب کنید');
    setBusy(true);
    try {
      const current = await endpoints.sites();
      const prepared: Created[] = [];
      for (const site of chosen) {
        const existing = findExistingSiteByDomain(current, site.domain);
        const ga4 = ga4Pick[site.domain] ?? site.ga4?.property_id ?? '';
        const id = existing?.site_id ?? siteSlug(site.domain);
        if (existing) {
          await endpoints.updateSite(id, {
            gsc_property: site.gsc_property,
            ...(ga4 ? { ga4_property: ga4 } : {})
          });
        } else {
          await endpoints.createSite({
            site_id: id,
            timezone: 'Asia/Tehran',
            name: site.domain,
            canonical_url: `https://${site.domain}/`,
            language: 'fa-IR',
            country: 'IR',
            mode: 'manual',
            gsc_property: site.gsc_property,
            ...(ga4 ? { ga4_property: ga4 } : {})
          });
        }
        await endpoints.initializeSite(id);
        prepared.push({ site_id: id, domain: site.domain, existing: Boolean(existing) });
      }
      setCreated(prepared);
      setWpUrls(
        Object.fromEntries(prepared.map((item) => [item.site_id, `https://${item.domain}`]))
      );
      setStep(2);
      toast.success(`${prepared.length} سایت برای راه‌اندازی آماده شد`);
    } catch (error) {
      toast.error(messageOf(error, 'آماده‌سازی سایت‌ها انجام نشد؛ دوباره تلاش کنید'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className='mx-auto grid w-full max-w-[calc(100vw-2rem)] gap-6 lg:max-w-[calc(100vw-11rem)] 2xl:max-w-6xl'>
      <section className='relative overflow-hidden rounded-2xl border bg-gradient-to-l from-primary/10 via-card to-card p-6 shadow-sm md:p-8'>
        <div className='pointer-events-none absolute -left-16 -top-20 size-56 rounded-full bg-primary/10 blur-3xl' />
        <div className='relative flex flex-col justify-between gap-5 lg:flex-row lg:items-end'>
          <div className='max-w-2xl space-y-3'>
            <Badge variant='secondary' className='gap-1.5'>
              <IconSparkles className='size-3.5' /> راه‌اندازی هوشمند
            </Badge>
            <div>
              <h2 className='text-2xl font-bold tracking-tight md:text-3xl'>
                داده‌های واقعی سایت را وارد چرخه تحلیل کنید
              </h2>
              <p className='mt-2 text-sm leading-7 text-muted-foreground md:text-base'>
                اتصال‌ها فقط برای خواندن آمار و محتوا هستند. هیچ تغییری در سایت یا حساب گوگل شما
                ایجاد نمی‌شود.
              </p>
            </div>
          </div>
          <div className='min-w-52 rounded-xl border bg-background/70 p-4 backdrop-blur'>
            <div className='mb-2 flex items-center justify-between text-sm'>
              <span>پیشرفت راه‌اندازی</span>
              <b>{step + 1} از ۴</b>
            </div>
            <Progress value={(step + 1) * 25} className='[&_[data-slot=progress-track]]:h-2' />
          </div>
        </div>
      </section>

      <nav className='grid grid-cols-2 gap-2 lg:grid-cols-4' aria-label='مراحل راه‌اندازی'>
        {STEPS.map((item, index) => {
          const Icon = item.icon;
          const active = index === step;
          const complete = index < step;
          return (
            <button
              key={item.title}
              type='button'
              disabled={!complete}
              onClick={() => complete && setStep(index)}
              className={cn(
                'flex items-center gap-3 rounded-xl border p-3 text-right transition-colors',
                active && 'border-primary bg-primary/10',
                complete && 'cursor-pointer bg-muted/40 hover:bg-muted',
                !active && !complete && 'opacity-60'
              )}
            >
              <span
                className={cn(
                  'grid size-10 shrink-0 place-items-center rounded-lg border bg-background',
                  active && 'border-primary text-primary',
                  complete && 'border-emerald-500/40 text-emerald-500'
                )}
              >
                {complete ? <IconCheck className='size-5' /> : <Icon className='size-5' />}
              </span>
              <span className='min-w-0'>
                <b className='block text-sm'>
                  {index + 1}. {item.title}
                </b>
                <small className='block truncate text-muted-foreground'>{item.description}</small>
              </span>
            </button>
          );
        })}
      </nav>

      <div className='grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_280px]'>
        <main>
          {step === 0 && <StepGoogle onReady={() => setStep(1)} />}
          {step === 1 && (
            <StepPick
              sites={sites}
              setSites={setSites}
              ga4All={ga4All}
              setGa4All={setGa4All}
              picked={picked}
              setPicked={setPicked}
              ga4Pick={ga4Pick}
              setGa4Pick={setGa4Pick}
              busy={busy}
              onBack={() => setStep(0)}
              onNext={() => void prepareSelectedSites()}
            />
          )}
          {step === 2 && (
            <StepWordPress
              created={created}
              wpUrls={wpUrls}
              setWpUrls={setWpUrls}
              onBack={() => setStep(1)}
              onNext={() => setStep(3)}
            />
          )}
          {step === 3 && (
            <StepLaunch
              created={created}
              onDone={() =>
                router.push(
                  created[0]
                    ? `/dashboard/sites/${created[0].site_id}?tab=connections`
                    : '/dashboard/overview'
                )
              }
            />
          )}
        </main>

        <aside className='grid gap-3 lg:sticky lg:top-20'>
          <Card>
            <CardHeader className='pb-3'>
              <CardTitle className='text-base'>خلاصه راه‌اندازی</CardTitle>
            </CardHeader>
            <CardContent className='grid gap-3 text-sm'>
              <SummaryRow
                icon={IconWorld}
                label='سایت انتخاب‌شده'
                value={selectedCount ? String(selectedCount) : 'هنوز انتخاب نشده'}
                ok={selectedCount > 0}
              />
              <SummaryRow
                icon={IconDatabase}
                label='فضای داده'
                value={created.length ? 'آماده' : 'پس از انتخاب ساخته می‌شود'}
                ok={created.length > 0}
              />
              <SummaryRow
                icon={IconBrandWordpress}
                label='وردپرس'
                value={step < 2 ? 'در مرحله بعد' : 'اختیاری'}
              />
            </CardContent>
          </Card>
          <Alert className='bg-emerald-500/5 text-right'>
            <IconShieldCheck className='text-emerald-500' />
            <AlertTitle>دسترسی امن و فقط‌خواندنی</AlertTitle>
            <AlertDescription>
              SEO Brain فقط داده لازم برای گزارش و تحلیل را دریافت می‌کند.
            </AlertDescription>
          </Alert>
        </aside>
      </div>
    </div>
  );
}

function SummaryRow({
  icon: Icon,
  label,
  value,
  ok = false
}: {
  icon: typeof IconWorld;
  label: string;
  value: string;
  ok?: boolean;
}) {
  return (
    <div className='flex items-center gap-3 rounded-lg border p-3'>
      <Icon className={cn('size-5 shrink-0 text-muted-foreground', ok && 'text-emerald-500')} />
      <div className='min-w-0'>
        <span className='block text-muted-foreground'>{label}</span>
        <b className='block truncate text-xs'>{value}</b>
      </div>
    </div>
  );
}

function StepGoogle({ onReady }: { onReady: () => void }) {
  const [status, setStatus] = useState<GoogleAccountStatus | null>(null);
  const [sa, setSa] = useState<SaGscStatus | null>(null);
  const [showOAuth, setShowOAuth] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    const [googleResult, saResult] = await Promise.allSettled([
      endpoints.googleStatus(),
      endpoints.saGscStatus()
    ]);
    if (googleResult.status === 'fulfilled') setStatus(googleResult.value);
    if (saResult.status === 'fulfilled') setSa(saResult.value);
    if (googleResult.status === 'rejected' && saResult.status === 'rejected')
      setError('وضعیت اتصال قابل دریافت نیست. سرویس را بررسی و دوباره تلاش کنید.');
    setLoading(false);
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const saReady = Boolean(sa?.configured && sa.accessible_properties.length > 0);
  const canContinue = Boolean(status?.connected) || saReady;

  return (
    <Card className='overflow-hidden'>
      <CardHeader className='border-b bg-muted/25'>
        <div className='flex flex-wrap items-start justify-between gap-3'>
          <div>
            <CardTitle className='text-xl'>اتصال منبع آمار جستجو</CardTitle>
            <CardDescription className='mt-2 leading-6'>
              روش پیشنهادی فعال است؛ فقط کافی است دسترسی Search Console تأیید شود.
            </CardDescription>
          </div>
          <Badge
            variant={canContinue ? 'secondary' : 'outline'}
            className={cn('gap-1.5', canContinue && 'text-emerald-500')}
          >
            {canContinue ? (
              <IconCircleCheck className='size-4' />
            ) : (
              <IconBrandGoogle className='size-4' />
            )}
            {canContinue ? 'متصل و آماده' : loading ? 'در حال بررسی' : 'نیازمند اتصال'}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className='grid gap-5 p-5 md:p-6'>
        {error && (
          <Alert variant='destructive'>
            <IconAlertTriangle />
            <AlertTitle>بررسی اتصال ناموفق بود</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {sa?.configured && (
          <GoogleSearchConsoleConnectionCard onSelect={onReady} onChecked={() => void refresh()} />
        )}
        {!sa?.configured || showOAuth ? (
          <GoogleAccountCard simple onChange={() => void refresh()} />
        ) : (
          <button
            type='button'
            onClick={() => setShowOAuth(true)}
            className='w-full rounded-xl border border-dashed p-4 text-right text-sm transition-colors hover:bg-muted/40'
            data-testid='show-oauth'
          >
            <b className='block'>روش جایگزین: ورود مستقیم با حساب گوگل</b>
            <span className='mt-1 block text-muted-foreground'>
              اگر نمی‌خواهید از ایمیل سرویس استفاده کنید، OAuth را باز کنید.
            </span>
          </button>
        )}
        <StepActions
          onNext={onReady}
          nextDisabled={!canContinue || loading}
          nextLabel={canContinue ? 'ادامه و انتخاب سایت‌ها' : 'ابتدا اتصال را کامل کنید'}
          extra={
            error ? (
              <Button variant='outline' onClick={() => void refresh()}>
                <IconRefresh /> تلاش دوباره
              </Button>
            ) : undefined
          }
        />
      </CardContent>
    </Card>
  );
}

function StepPick({
  sites,
  setSites,
  ga4All,
  setGa4All,
  picked,
  setPicked,
  ga4Pick,
  setGa4Pick,
  busy,
  onBack,
  onNext
}: {
  sites: DiscoveredSite[] | null;
  setSites: (value: DiscoveredSite[]) => void;
  ga4All: PropertyOption[];
  setGa4All: (value: PropertyOption[]) => void;
  picked: Record<string, boolean>;
  setPicked: (value: Record<string, boolean>) => void;
  ga4Pick: Record<string, string>;
  setGa4Pick: (value: Record<string, string>) => void;
  busy: boolean;
  onBack: () => void;
  onNext: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [ga4Warning, setGa4Warning] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setGa4Warning(null);
    const serviceAccount = await endpoints.saGscStatus().catch(() => null);
    const serviceProperties = serviceAccount?.accessible_properties ?? [];
    const [gsc, ga4] = await Promise.allSettled([
      serviceProperties.length
        ? Promise.resolve({ status: 'ok', properties: serviceProperties })
        : endpoints.gscProperties(),
      endpoints.ga4Properties()
    ]);
    const gscItems =
      gsc.status === 'fulfilled' && gsc.value.status === 'ok' ? gsc.value.properties : [];
    if (!gscItems.length) {
      const reason =
        gsc.status === 'rejected'
          ? gsc.reason
          : new Error(
              gsc.status === 'fulfilled' && 'message' in gsc.value
                ? String(gsc.value.message ?? '')
                : ''
            );
      setError(messageOf(reason, 'هیچ دامنه قابل دسترسی در Search Console پیدا نشد.'));
      setLoading(false);
      return;
    }
    const ga4Items =
      ga4.status === 'fulfilled' && ga4.value.status === 'ok' ? ga4.value.properties : [];
    if (ga4.status === 'rejected' || ga4.value.status !== 'ok')
      setGa4Warning(
        'Google Analytics در دسترس نیست؛ می‌توانید بدون آن ادامه دهید و بعداً متصلش کنید.'
      );
    setGa4All(ga4Items);
    const merged = mergeDiscovery(gscItems, ga4Items);
    setSites(merged);
    if (merged.filter((item) => item.verified).length === 1)
      setPicked({ ...picked, [merged.find((item) => item.verified)!.domain]: true });
    setLoading(false);
  }, [picked, setGa4All, setPicked, setSites]);
  useEffect(() => {
    if (!sites) void load();
  }, [sites, load]);
  const count = useMemo(() => Object.values(picked).filter(Boolean).length, [picked]);

  return (
    <Card>
      <CardHeader className='border-b bg-muted/25'>
        <div className='flex flex-wrap items-start justify-between gap-3'>
          <div>
            <CardTitle className='text-xl'>سایت‌های قابل تحلیل</CardTitle>
            <CardDescription className='mt-2'>
              فقط سایت‌هایی را انتخاب کنید که باید وارد پنل مدیریتی شوند.
            </CardDescription>
          </div>
          <Badge variant='outline'>{count} انتخاب</Badge>
        </div>
      </CardHeader>
      <CardContent className='grid gap-4 p-5 md:p-6'>
        {error && (
          <Alert variant='destructive'>
            <IconAlertTriangle />
            <AlertTitle>دریافت سایت‌ها ناموفق بود</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {ga4Warning && (
          <Alert>
            <IconAlertTriangle className='text-amber-500' />
            <AlertTitle>ادامه بدون Analytics</AlertTitle>
            <AlertDescription>{ga4Warning}</AlertDescription>
          </Alert>
        )}
        {loading && (
          <div className='grid min-h-40 place-items-center rounded-xl border border-dashed text-sm text-muted-foreground'>
            در حال دریافت دامنه‌های Search Console…
          </div>
        )}
        {!loading && !error && sites?.length === 0 && (
          <div className='grid min-h-40 place-items-center rounded-xl border border-dashed text-center'>
            <div>
              <IconWorld className='mx-auto mb-2 size-8 text-muted-foreground' />
              <b>دامنه‌ای پیدا نشد</b>
              <p className='mt-1 text-sm text-muted-foreground'>
                دسترسی Search Console را در مرحله قبل بررسی کنید.
              </p>
            </div>
          </div>
        )}
        <div className='grid gap-3 md:grid-cols-2'>
          {sites?.map((site) => (
            <label
              key={site.domain}
              data-testid={`site-card-${site.domain}`}
              className={cn(
                'relative grid cursor-pointer gap-3 rounded-xl border p-4 transition-colors hover:bg-muted/30',
                picked[site.domain] && 'border-primary bg-primary/5',
                !site.verified && 'cursor-not-allowed opacity-55'
              )}
            >
              <div className='flex items-start gap-3'>
                <input
                  type='checkbox'
                  className='mt-1 size-4 accent-primary'
                  checked={Boolean(picked[site.domain])}
                  disabled={!site.verified}
                  onChange={(event) =>
                    setPicked({ ...picked, [site.domain]: event.target.checked })
                  }
                />
                <span className='grid size-10 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary'>
                  <IconWorld className='size-5' />
                </span>
                <div className='min-w-0'>
                  <b className='block truncate' dir='ltr'>
                    {site.domain}
                  </b>
                  <span className='mt-1 block text-xs text-muted-foreground'>
                    {site.verified
                      ? 'دسترسی Search Console تأیید شده'
                      : 'دسترسی این دامنه تأیید نشده'}
                  </span>
                </div>
              </div>
              {ga4All.length > 0 ? (
                <NativeSelect
                  value={ga4Pick[site.domain] ?? site.ga4?.property_id ?? ''}
                  onChange={(event) =>
                    setGa4Pick({ ...ga4Pick, [site.domain]: event.target.value })
                  }
                >
                  <NativeSelectOption value=''>بدون Google Analytics</NativeSelectOption>
                  {ga4All.map((item) => (
                    <NativeSelectOption key={item.property_id} value={item.property_id}>
                      {item.display_name ?? item.property_id}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              ) : (
                <Badge variant='outline' className='w-fit'>
                  Analytics فعلاً متصل نیست
                </Badge>
              )}
            </label>
          ))}
        </div>
        <StepActions
          onBack={onBack}
          onNext={onNext}
          nextDisabled={!count || busy || Boolean(error)}
          nextLabel={busy ? 'در حال آماده‌سازی…' : `آماده‌سازی ${count || ''} سایت`}
          extra={
            error ? (
              <Button variant='outline' onClick={() => void load()}>
                <IconRefresh /> تلاش دوباره
              </Button>
            ) : undefined
          }
        />
      </CardContent>
    </Card>
  );
}

function StepWordPress({
  created,
  wpUrls,
  setWpUrls,
  onBack,
  onNext
}: {
  created: Created[];
  wpUrls: Record<string, string>;
  setWpUrls: (value: Record<string, string>) => void;
  onBack: () => void;
  onNext: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { ok: boolean; message: string }>>({});
  const test = async (siteId: string) => {
    const url = normalizeWebsiteUrl(wpUrls[siteId] ?? '');
    if (!url)
      return setResults((value) => ({
        ...value,
        [siteId]: { ok: false, message: 'آدرس معتبر وارد کنید؛ مثال: example.com' }
      }));
    setWpUrls({ ...wpUrls, [siteId]: url });
    setBusy(siteId);
    try {
      const result = await endpoints.testConnection(siteId, 'wordpress', url);
      setResults((value) => ({
        ...value,
        [siteId]: {
          ok: result.ok,
          message: result.ok
            ? 'اتصال برقرار شد و دریافت محتوا در دسترس است.'
            : 'وردپرس یا REST API سایت پاسخ معتبر نداد.'
        }
      }));
    } catch (error) {
      setResults((value) => ({
        ...value,
        [siteId]: {
          ok: false,
          message: messageOf(error, 'اتصال برقرار نشد؛ بعداً هم می‌توانید تلاش کنید.')
        }
      }));
    } finally {
      setBusy(null);
    }
  };
  return (
    <Card>
      <CardHeader className='border-b bg-muted/25'>
        <CardTitle className='text-xl'>دریافت محتوا از وردپرس</CardTitle>
        <CardDescription className='mt-2 leading-6'>
          این مرحله اختیاری است. برای محتوای عمومی سایت به نام کاربری یا رمز نیاز نداریم.
        </CardDescription>
      </CardHeader>
      <CardContent className='grid gap-4 p-5 md:p-6'>
        {created.map((item) => (
          <div key={item.site_id} className='grid gap-3 rounded-xl border p-4'>
            <div className='flex items-center justify-between gap-3'>
              <div>
                <b dir='ltr'>{item.domain}</b>
                <p className='mt-1 text-xs text-muted-foreground'>
                  {item.existing ? 'سایت موجود به‌روزرسانی شد' : 'فضای این سایت ساخته شد'}
                </p>
              </div>
              <IconBrandWordpress className='size-7 text-muted-foreground' />
            </div>
            <div className='flex flex-col gap-2 sm:flex-row'>
              <Input
                dir='ltr'
                value={wpUrls[item.site_id] ?? ''}
                placeholder='https://example.com'
                onChange={(event) => setWpUrls({ ...wpUrls, [item.site_id]: event.target.value })}
              />
              <Button
                variant='outline'
                disabled={busy === item.site_id}
                onClick={() => void test(item.site_id)}
              >
                {busy === item.site_id ? 'در حال بررسی…' : 'بررسی اتصال'}
              </Button>
            </div>
            {results[item.site_id] && (
              <p
                className={cn(
                  'flex items-center gap-2 text-sm',
                  results[item.site_id].ok ? 'text-emerald-500' : 'text-destructive'
                )}
              >
                {results[item.site_id].ok ? (
                  <IconCircleCheck className='size-4' />
                ) : (
                  <IconAlertTriangle className='size-4' />
                )}
                {results[item.site_id].message}
              </p>
            )}
          </div>
        ))}
        <StepActions
          onBack={onBack}
          onNext={onNext}
          nextLabel='ادامه به شروع تحلیل'
          extra={
            <span className='text-xs text-muted-foreground'>
              می‌توانید بدون اتصال وردپرس ادامه دهید.
            </span>
          }
        />
      </CardContent>
    </Card>
  );
}

function StepLaunch({ created, onDone }: { created: Created[]; onDone: () => void }) {
  const [started, setStarted] = useState(false);
  const [starting, setStarting] = useState(false);
  const [state, setState] = useState<Record<string, IntegrationBlock[]>>({});
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const poll = useCallback(async () => {
    const updates: Record<string, IntegrationBlock[]> = {};
    await Promise.all(
      created.map(async (item) => {
        try {
          updates[item.site_id] = (await endpoints.integrations(item.site_id)).integrations;
        } catch {
          /* retain last successful snapshot */
        }
      })
    );
    setState((value) => ({ ...value, ...updates }));
  }, [created]);
  useEffect(() => {
    if (!started) return;
    void poll();
    const timer = window.setInterval(() => void poll(), 4000);
    return () => window.clearInterval(timer);
  }, [started, poll]);

  const start = async () => {
    setStarting(true);
    const nextErrors: Record<string, string[]> = {};
    let launched = 0;
    for (const item of created) {
      const issues: string[] = [];
      try {
        await endpoints.initializeSite(item.site_id);
      } catch (error) {
        issues.push(messageOf(error, 'فضای داده آماده نشد'));
      }
      let integrations: IntegrationBlock[] = [];
      try {
        integrations = (await endpoints.integrations(item.site_id)).integrations;
      } catch (error) {
        issues.push(messageOf(error, 'وضعیت اتصال‌ها دریافت نشد'));
      }
      const gsc = integrations.find((value) => value.kind === 'gsc');
      const ga4 = integrations.find((value) => value.kind === 'ga4');
      const wordpress = integrations.find((value) => value.kind === 'wordpress');
      try {
        if (!gsc || !['queued', 'running', 'succeeded'].includes(gsc.sync.status)) {
          await endpoints.gscSyncStart(item.site_id, { days: 30 });
          launched++;
        }
      } catch (error) {
        issues.push(`Search Console: ${messageOf(error, 'شروع نشد')}`);
      }
      try {
        if (ga4?.configured && !['queued', 'running', 'succeeded'].includes(ga4.sync.status)) {
          await endpoints.ga4SyncStart(item.site_id, { days: 30 });
          launched++;
        }
      } catch (error) {
        issues.push(`Analytics: ${messageOf(error, 'شروع نشد')}`);
      }
      try {
        if (
          wordpress?.configured &&
          !['queued', 'running', 'succeeded'].includes(wordpress.sync.status)
        ) {
          await endpoints.wpSyncStart(item.site_id);
          launched++;
        }
      } catch (error) {
        issues.push(`وردپرس: ${messageOf(error, 'شروع نشد')}`);
      }
      if (issues.length) nextErrors[item.site_id] = issues;
    }
    setErrors(nextErrors);
    setStarted(launched > 0 || Object.keys(state).length > 0);
    setStarting(false);
    await poll();
    if (launched) toast.success('دریافت داده‌ها شروع شد و در پس‌زمینه ادامه دارد');
    else if (Object.keys(nextErrors).length)
      toast.error('شروع تحلیل کامل نشد؛ خطاهای هر سایت را بررسی کنید');
    else {
      setStarted(true);
      toast.success('داده‌های این سایت‌ها از قبل آماده یا در حال دریافت هستند');
    }
  };

  return (
    <Card>
      <CardHeader className='border-b bg-muted/25'>
        <div className='flex items-start justify-between gap-3'>
          <div>
            <CardTitle className='text-xl'>شروع دریافت داده‌های زنده</CardTitle>
            <CardDescription className='mt-2 leading-6'>
              ۳۰ روز اخیر Search Console دریافت می‌شود؛ منابع اختیاری فقط در صورت اتصال اجرا می‌شوند.
            </CardDescription>
          </div>
          <IconPlayerPlay className='size-8 text-primary' />
        </div>
      </CardHeader>
      <CardContent className='grid gap-4 p-5 md:p-6'>
        {created.map((item) => (
          <div key={item.site_id} className='grid gap-3 rounded-xl border p-4'>
            <div className='flex items-center justify-between'>
              <b dir='ltr'>{item.domain}</b>
              <Badge variant='outline'>{item.existing ? 'سایت موجود' : 'سایت جدید'}</Badge>
            </div>
            <div className='grid gap-2 sm:grid-cols-3'>
              {(state[item.site_id] ?? []).map((integration) => {
                const failed = ['failed', 'not_authorized', 'completed_with_errors'].includes(
                  integration.sync.status
                );
                const done = integration.sync.status === 'succeeded';
                return (
                  <div key={integration.kind} className='rounded-lg border bg-muted/20 p-3'>
                    <div className='mb-2 flex items-center justify-between text-xs'>
                      <span>{integration.label}</span>
                      <span
                        className={cn(done && 'text-emerald-500', failed && 'text-destructive')}
                      >
                        {SYNC_BADGE_FA[integration.sync.status] ?? integration.sync.status}
                      </span>
                    </div>
                    <Progress
                      value={integration.sync.progress ?? (done ? 100 : 0)}
                      className='[&_[data-slot=progress-track]]:h-1.5'
                    />
                    {integration.sync.step_fa && (
                      <p className='mt-2 truncate text-xs text-muted-foreground'>
                        {integration.sync.step_fa}
                      </p>
                    )}
                  </div>
                );
              })}
              {started && !state[item.site_id] && (
                <div className='col-span-full rounded-lg border border-dashed p-3 text-sm text-muted-foreground'>
                  در حال خواندن وضعیت اتصال‌ها…
                </div>
              )}
            </div>
            {errors[item.site_id]?.length ? (
              <Alert variant='destructive'>
                <IconAlertTriangle />
                <AlertTitle>بعضی منابع شروع نشدند</AlertTitle>
                <AlertDescription>{errors[item.site_id].join(' • ')}</AlertDescription>
              </Alert>
            ) : null}
          </div>
        ))}
        <div className='flex flex-col-reverse justify-between gap-3 border-t pt-4 sm:flex-row sm:items-center'>
          <p className='text-xs leading-5 text-muted-foreground'>
            بستن این صفحه، دریافت داده‌ها را متوقف نمی‌کند.
          </p>
          <div className='flex gap-2'>
            {started && (
              <Button variant='outline' onClick={() => void start()} disabled={starting}>
                <IconRefresh /> تلاش مجدد
              </Button>
            )}
            {!started ? (
              <Button
                onClick={() => void start()}
                disabled={starting}
                data-testid='onboarding-start'
              >
                <IconPlayerPlay /> {starting ? 'در حال شروع…' : 'شروع تحلیل سئو'}
              </Button>
            ) : (
              <Button onClick={onDone} data-testid='onboarding-done'>
                رفتن به داشبورد <IconArrowLeft />
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function StepActions({
  onBack,
  onNext,
  nextLabel,
  nextDisabled = false,
  extra
}: {
  onBack?: () => void;
  onNext: () => void;
  nextLabel: string;
  nextDisabled?: boolean;
  extra?: React.ReactNode;
}) {
  return (
    <div className='flex flex-col-reverse gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between'>
      <div className='flex items-center gap-2'>
        {onBack && (
          <Button variant='ghost' onClick={onBack}>
            <IconArrowRight /> بازگشت
          </Button>
        )}
        {extra}
      </div>
      <Button onClick={onNext} disabled={nextDisabled} data-testid='onboarding-next'>
        {nextLabel} <IconArrowLeft />
      </Button>
    </div>
  );
}
