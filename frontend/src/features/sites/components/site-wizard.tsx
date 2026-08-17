'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ApiError, endpoints, type ConnectionResult, type InitializeResult, type Site } from '@/lib/api/client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';
import { BUSINESS_CATEGORIES, COUNTRIES, LANGUAGES, normalizeUrl, slugifyDomain } from '../constants';
import { ConnectionTester } from './connection-tester';

type Step = 1 | 2 | 3;
const STEPS: { n: Step; title: string; desc: string }[] = [
  { n: 1, title: 'اطلاعات سایت', desc: 'نام، دامنه، حوزه کسب‌وکار، زبان و مکان' },
  { n: 2, title: 'اتصال‌ها', desc: 'Search Console، GA4، وردپرس و تست مجوزها' },
  { n: 3, title: 'ایجاد فضای کاری', desc: 'فضای کاری، حافظه سایت و فضای نام گراف' }
];

export function SiteWizard() {
  const router = useRouter();
  const [step, setStep] = useState<Step>(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; details?: unknown } | null>(null);

  // step 1
  const [name, setName] = useState('');
  const [domain, setDomain] = useState('');
  const [siteId, setSiteId] = useState('');
  const [siteIdTouched, setSiteIdTouched] = useState(false);
  const [category, setCategory] = useState('auto-service');
  const [language, setLanguage] = useState('fa-IR');
  const [country, setCountry] = useState('IR');
  const derivedId = useMemo(() => slugifyDomain(domain), [domain]);
  const effectiveId = siteIdTouched ? siteId : derivedId;

  // created site + step 2/3 state
  const [site, setSite] = useState<Site | null>(null);
  const [results, setResults] = useState<Partial<Record<'gsc' | 'ga4' | 'wordpress', ConnectionResult>>>({});
  const [init, setInit] = useState<InitializeResult | null>(null);

  const step1Valid = name.trim().length >= 2 && /^[a-z0-9][a-z0-9-]{1,62}$/.test(effectiveId) && normalizeUrl(domain).startsWith('http');

  async function createSite() {
    setBusy(true);
    setError(null);
    try {
      const body = {
        site_id: effectiveId,
        name: name.trim(),
        canonical_url: normalizeUrl(domain),
        wp_url: normalizeUrl(domain).replace(/\/$/, ''),
        business_type: category,
        language,
        country,
        timezone: COUNTRIES.find((c) => c.value === country)?.tz ?? 'Asia/Tehran',
        mode: 'manual' as const
      };
      const created = await endpoints.createSite(body);
      setSite(created);
      setStep(2);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        // already exists → continue with it (wizard is resumable)
        try {
          const existing = await endpoints.site(effectiveId);
          setSite(existing);
          setStep(2);
          return;
        } catch {
          /* fallthrough */
        }
      }
      setError(e instanceof ApiError ? { message: e.message, details: e.details } : { message: String(e) });
    } finally {
      setBusy(false);
    }
  }

  async function initialize() {
    if (!site) return;
    setBusy(true);
    setError(null);
    try {
      const out = await endpoints.initializeSite(site.site_id);
      setInit(out);
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? { message: e.message, details: e.details } : { message: String(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className='flex flex-col gap-4'>
      <ol className='grid gap-2 md:grid-cols-3'>
        {STEPS.map((s) => (
          <li key={s.n} className={`rounded-md border p-3 ${step === s.n ? 'border-primary bg-primary/5' : step > s.n ? 'opacity-70' : 'opacity-50'}`}>
            <div className='flex items-center gap-2 text-sm font-medium'>
              <Badge variant={step > s.n ? 'default' : 'outline'}>{step > s.n ? '✓' : s.n}</Badge> {s.title}
            </div>
            <p className='text-muted-foreground mt-1 text-xs'>{s.desc}</p>
          </li>
        ))}
      </ol>

      {error && (
        <div className='border-destructive/50 text-destructive rounded-md border p-3 text-sm'>
          {error.message}
          {Array.isArray(error.details) && (
            <ul className='mt-1 list-disc ps-5 text-xs'>
              {(error.details as { loc?: unknown[]; msg?: string }[]).map((d, i) => (
                <li key={i} dir='ltr'>
                  {(d.loc ?? []).slice(-1).join('.')}: {d.msg}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle>مرحله ۱ — اطلاعات سایت</CardTitle>
            <CardDescription>شناسه سایت از دامنه ساخته می‌شود و بعداً تغییر نمی‌کند.</CardDescription>
          </CardHeader>
          <CardContent className='grid gap-4 md:grid-cols-2'>
            <div className='grid gap-1.5'>
              <Label htmlFor='name'>نام سایت</Label>
              <Input id='name' value={name} onChange={(e) => setName(e.target.value)} placeholder='امداد مدیران' />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='domain'>دامنه</Label>
              <Input id='domain' value={domain} onChange={(e) => setDomain(e.target.value)} placeholder='example.com' dir='ltr' />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='site_id'>شناسه (slug)</Label>
              <Input
                id='site_id'
                value={effectiveId}
                onChange={(e) => {
                  setSiteIdTouched(true);
                  setSiteId(e.target.value.toLowerCase());
                }}
                dir='ltr'
                placeholder='example'
              />
              <p className='text-muted-foreground text-xs'>حروف کوچک انگلیسی، عدد و خط تیره؛ نام پوشه فضای کاری هم همین است.</p>
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='category'>حوزه کسب‌وکار</Label>
              <NativeSelect id='category' value={category} onChange={(e) => setCategory(e.target.value)}>
                {BUSINESS_CATEGORIES.map((c) => (
                  <NativeSelectOption key={c.value} value={c.value}>
                    {c.label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='language'>زبان محتوا</Label>
              <NativeSelect id='language' value={language} onChange={(e) => setLanguage(e.target.value)}>
                {LANGUAGES.map((l) => (
                  <NativeSelectOption key={l.value} value={l.value}>
                    {l.label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='country'>مکان / کشور هدف</Label>
              <NativeSelect id='country' value={country} onChange={(e) => setCountry(e.target.value)}>
                {COUNTRIES.map((c) => (
                  <NativeSelectOption key={c.value} value={c.value}>
                    {c.label} ({c.value})
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
            <div className='md:col-span-2 flex justify-end gap-2'>
              <Button onClick={createSite} disabled={!step1Valid || busy}>
                {busy ? 'در حال ایجاد…' : 'ایجاد سایت و ادامه'}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 2 && site && (
        <Card>
          <CardHeader>
            <CardTitle>مرحله ۲ — اتصال‌ها و تست مجوز</CardTitle>
            <CardDescription>
              همه تست‌ها فقط‌خواندنی هستند. اگر تست موفق باشد مقدار روی سایت ذخیره می‌شود؛ می‌توانید بعداً از صفحه سایت هم دوباره تست کنید.
            </CardDescription>
          </CardHeader>
          <CardContent className='grid gap-3'>
            <ConnectionTester siteId={site.site_id} kind='gsc' label='Google Search Console' hint='sc-domain:example.com یا https://example.com/'
              initialValue={site.gsc_property} onResult={(r) => setResults((s) => ({ ...s, gsc: r }))} />
            <ConnectionTester siteId={site.site_id} kind='ga4' label='Google Analytics 4 (Property ID)' hint='123456789'
              initialValue={site.ga4_property} onResult={(r) => setResults((s) => ({ ...s, ga4: r }))} />
            <ConnectionTester siteId={site.site_id} kind='wordpress' label='WordPress REST API' hint='https://example.com'
              initialValue={site.wp_url} onResult={(r) => setResults((s) => ({ ...s, wordpress: r }))} />
            <div className='flex justify-between gap-2'>
              <Button variant='ghost' onClick={() => setStep(1)}>بازگشت</Button>
              <Button onClick={() => setStep(3)}>ادامه {Object.values(results).some((r) => r?.ok) ? '' : '(بدون اتصال هم می‌توانید ادامه دهید)'}</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 3 && site && (
        <Card>
          <CardHeader>
            <CardTitle>مرحله ۳ — ایجاد فضای کاری</CardTitle>
            <CardDescription>
              پوشه <code dir='ltr'>data/sites/{site.site_id}</code>، رکورد حافظه سایت و گره ریشه گراف <code dir='ltr'>site:{site.site_id}</code> ساخته می‌شوند. این عمل قابل تکرار و بی‌خطر است.
            </CardDescription>
          </CardHeader>
          <CardContent className='grid gap-3'>
            {!init ? (
              <Button onClick={initialize} disabled={busy}>{busy ? 'در حال ایجاد…' : 'ایجاد فضای کاری'}</Button>
            ) : (
              <ul className='space-y-1 text-sm'>
                <li>✅ فضای کاری: <code dir='ltr'>{init.workspace.path}</code> {init.workspace.existed ? '(از قبل وجود داشت)' : `— ایجاد شد: ${init.workspace.created.join(', ')}`}</li>
                <li>✅ حافظه سایت: {init.memory.initialized ? 'ایجاد شد' : 'از قبل وجود داشت'}</li>
                <li>✅ فضای نام گراف: <code dir='ltr'>{init.graph.site_node}</code> — {init.graph.nodes} گره / {init.graph.edges} یال</li>
              </ul>
            )}
            <div className='flex justify-between gap-2'>
              <Button variant='ghost' onClick={() => setStep(2)}>بازگشت</Button>
              {init && (
                <div className='flex gap-2'>
                  <Button variant='secondary' render={<Link href={`/dashboard/sites/${site.site_id}?tab=brain`} />}>پیکربندی مغز سایت</Button>
                  <Button render={<Link href={`/dashboard/sites/${site.site_id}`} />}>رفتن به صفحه سایت</Button>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
