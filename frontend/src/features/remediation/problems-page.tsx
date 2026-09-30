'use client';

import { useEffect, useState } from 'react';
import { IconChevronDown } from '@tabler/icons-react';
import { Button } from '@/components/ui/button';
import { api, endpoints, type AutoSyncPlan, type WpSyncStatus } from '@/lib/api/client';
import type { components } from '@/lib/api/schema';
import { RemediationAction } from './remediation-action';

type Coverage = {
  status: string; complete: boolean; started_at?: string | null; finished_at?: string | null;
  max_urls?: number | null; urls_crawled?: number | null; urls_failed?: number | null;
  sitemap_urls?: number | null; queue_remaining?: number | null; recommended_max_urls: number;
};
type Result = components['schemas']['RemediationIssuesOut'] & { coverage?: Coverage | null };

const labels: Record<string, string> = {
  orphan: 'صفحهٔ یتیم', no_body_inbound_links: 'لینک ورودی متنی ندارد', low_inbound_links: 'لینک ورودی کم',
  high_outbound_links: 'لینک خروجی زیاد', missing_h1: 'H1 ندارد', multiple_h1: 'چند H1', duplicate_h1: 'H1 تکراری',
  duplicate_title: 'عنوان تکراری', missing_meta_description: 'توضیح متا ندارد', images_missing_alt: 'تصویر بدون alt',
  missing_canonical: 'canonical ندارد', important_non_indexable: 'صفحهٔ مهم غیرقابل ایندکس',
  thin_content: 'محتوای کم', redirect_in_sitemap: 'ریدایرکت در سایت‌مپ'
};
const categoryLabels: Record<string, string> = {
  links: 'لینک‌ها', headings_metadata: 'تیترها و متادیتا', content_media: 'محتوا و تصاویر',
  indexing_sitemap: 'ایندکس و سایت‌مپ', other: 'سایر مشکلات'
};

export function ProblemsPage({ sites, initialSiteId }: { sites: { site_id: string; name: string }[]; initialSiteId: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [summary, setSummary] = useState<Result | null>(null);
  const [categoryResult, setCategoryResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<WpSyncStatus | null>(null);
  const [plan, setPlan] = useState<AutoSyncPlan | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [overview, setOverview] = useState<Record<string, { issues: number; coverage: Coverage | null } | null>>({});
  useEffect(() => {
    let active = true;
    void Promise.allSettled(sites.map((site) =>
      api<Result>(`/sites/${encodeURIComponent(site.site_id)}/remediation/problems?limit=1`)
    )).then((rows) => {
      if (!active) return;
      setOverview(Object.fromEntries(sites.map((site, index) => [site.site_id,
        rows[index].status === 'fulfilled'
          ? { issues: rows[index].value.total, coverage: rows[index].value.coverage ?? null }
          : null])));
    });
    return () => { active = false; };
  }, [sites, revision]);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(null);
    api<Result>(`/sites/${encodeURIComponent(siteId)}/remediation/problems?limit=1`)
      .then((data) => { if (active) setSummary(data); })
      .catch((e) => { if (active) { setSummary(null); setError(String(e?.message ?? e)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [siteId, revision]);
  useEffect(() => {
    if (!activeCategory) { setCategoryResult(null); setListError(null); return; }
    let active = true;
    setCategoryResult(null); setListLoading(true); setListError(null);
    api<Result>(`/sites/${encodeURIComponent(siteId)}/remediation/problems?category=${encodeURIComponent(activeCategory)}&limit=30&offset=${offset}`)
      .then((data) => { if (active) setCategoryResult(data); })
      .catch((e) => { if (active) setListError(String(e?.message ?? e)); })
      .finally(() => { if (active) setListLoading(false); });
    return () => { active = false; };
  }, [siteId, activeCategory, offset, revision]);
  useEffect(() => {
    let active = true;
    let previousRunId: string | null = null;
    let previousStatus: string | null = null;
    const refresh = async () => {
      try {
        const [status, nextPlan] = await Promise.all([endpoints.wpSyncStatus(siteId), endpoints.autoSyncGet(siteId)]);
        if (!active) return;
        setSyncStatus(status);
        setPlan(nextPlan);
        setSyncError(null);
        if (status.run_id && status.status !== 'queued' && status.status !== 'running' && previousRunId &&
            (previousRunId !== status.run_id || previousStatus === 'queued' || previousStatus === 'running')) {
          setOffset(0);
          setRevision((n) => n + 1);
        }
        previousRunId = status.run_id;
        previousStatus = status.status;
      } catch (e) {
        if (active) setSyncError(String(e));
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    return () => { active = false; clearInterval(timer); };
  }, [siteId]);

  async function startRefresh() {
    setSyncing(true); setSyncError(null);
    try {
      const queued = await endpoints.wpSyncStart(siteId, { crawl: true, max_urls: summary?.coverage?.recommended_max_urls ?? 500 });
      if (queued.status !== 'queued' && queued.status !== 'already_running') {
        throw new Error(queued.error ?? 'خزش شروع نشد');
      }
      setSyncStatus(await endpoints.wpSyncStatus(siteId));
    } catch (e) {
      setSyncError(String(e));
    } finally {
      setSyncing(false);
    }
  }

  const running = syncStatus?.status === 'queued' || syncStatus?.status === 'running';
  const nextAt = plan?.sources.wordpress.next_at;
  return <div className='space-y-4'>
    <div className='grid gap-2 sm:grid-cols-2 lg:grid-cols-4'>
      {sites.map((site) => {
        const item = overview[site.site_id];
        return <button key={site.site_id} type='button' onClick={() => { setSiteId(site.site_id); setOffset(0); setActiveCategory(null); setSummary(null); setCategoryResult(null); }}
          className={`rounded border p-3 text-right text-sm ${siteId === site.site_id ? 'border-primary' : ''}`}>
          <span className='block font-medium'>{site.name}</span>
          <span dir='ltr' className='block text-xs text-muted-foreground'>{site.site_id}</span>
          <span className='block'>{item === undefined ? 'در حال دریافت…' : item === null ? 'داده در دسترس نیست' : `${item.issues} مشکل · ${item.coverage?.complete ? 'خزش کامل' : 'پوشش ناقص یا نامشخص'}`}</span>
        </button>;
      })}
    </div>
    <label className='flex items-center gap-2 text-sm'>سایت
      <select className='rounded border bg-background p-2' value={siteId} onChange={(e) => { setSiteId(e.target.value); setOffset(0); setActiveCategory(null); setSummary(null); setCategoryResult(null); setSyncStatus(null); setPlan(null); }}>
        {sites.map((s) => <option key={s.site_id} value={s.site_id}>{s.name}</option>)}
      </select>
    </label>
    <div className='flex flex-wrap items-center gap-3 rounded-lg border bg-card p-3 text-sm'>
      <Button type='button' disabled={syncing || running} onClick={() => void startRefresh()}>بررسی دوبارهٔ سایت</Button>
      <Button type='button' variant='outline' disabled={loading} onClick={() => setRevision((n) => n + 1)}>تازه‌سازی فهرست</Button>
      <span className='text-muted-foreground'>
        {running ? `خزش در جریان است · ${syncStatus?.progress ?? 0}٪` : plan?.enabled && nextAt
          ? `بررسی خودکار بعدی: ${new Date(nextAt).getTime() <= Date.now() ? 'در نوبت اجرا' : new Date(nextAt).toLocaleString('fa-IR', { timeZone: 'Asia/Tehran' })}`
          : 'بررسی خودکار خاموش است'}
      </span>
      {syncStatus?.finished_at && !running && <span className='text-muted-foreground'>آخرین بررسی: {new Date(syncStatus.finished_at).toLocaleString('fa-IR', { timeZone: 'Asia/Tehran' })}</span>}
      {syncStatus?.status === 'failed' && <span className='text-destructive'>همگام‌سازی ناموفق: {syncStatus.errors?.[0] ?? 'گزارش اتصال را بررسی کنید'}</span>}
      {syncError && <span className='text-destructive'>{syncError}</span>}
    </div>
    {loading && <p>در حال دریافت مشکلات…</p>}
    {error && <p className='text-destructive'>{error}</p>}
    {summary && <>
      <p className='text-muted-foreground text-sm'>{summary.total} مشکل ثبت‌شده</p>
      {summary.coverage && <div className={summary.coverage.complete ? 'rounded border border-emerald-300 p-3 text-sm' : 'rounded border border-amber-400 p-3 text-sm'}>
        <p>{summary.coverage.status === 'never' ? 'برای این سایت هنوز خزش معتبری ثبت نشده است؛ صفر مشکل به معنی سالم بودن سایت نیست.' :
          `آخرین خزش: ${summary.coverage.urls_crawled ?? 0} صفحه، ${summary.coverage.urls_failed ?? 0} خطا، ${summary.coverage.sitemap_urls ?? 'نامشخص'} URL در سایت‌مپ.`}</p>
        {!summary.coverage.complete && summary.coverage.status !== 'never' && <p>پوشش خزش کامل تأیید نشده است؛ فهرست مشکلات ممکن است ناقص باشد.{summary.coverage.queue_remaining ? ` ${summary.coverage.queue_remaining} URL در صف خزش باقی مانده بود.` : ''}</p>}
        {summary.coverage.finished_at && Date.now() - new Date(summary.coverage.finished_at).getTime() > 7 * 86400000 && <p>دادهٔ این خزش بیش از هفت روز قدمت دارد.</p>}
      </div>}
      {summary.groups.length === 0 && <p className='rounded-lg border bg-card p-4 text-sm'>مشکلی ثبت نشده است.</p>}
      <div className='space-y-2'>{summary.groups.map((group) => {
        const open = activeCategory === group.category;
        return <section key={group.category} className='rounded-lg border bg-card'>
          <button type='button' aria-expanded={open} onClick={() => { setActiveCategory(open ? null : group.category); setCategoryResult(null); setOffset(0); }}
            className='flex w-full items-center justify-between gap-3 p-4 text-right'>
            <span className='min-w-0 space-y-1'>
              <span className='block font-semibold'>{categoryLabels[group.category] ?? group.category}</span>
              <span className='block text-xs text-muted-foreground'>{group.types.map((item) => `${labels[item.problem_type] ?? item.problem_type}: ${item.count}`).join(' · ')}</span>
            </span>
            <span className='flex shrink-0 items-center gap-2 text-sm'><span>{group.count} مشکل</span><IconChevronDown className={`size-4 transition-transform ${open ? 'rotate-180' : ''}`} /></span>
          </button>
          {open && <div className='space-y-2 border-t p-3'>
            {listLoading && <p className='text-sm'>در حال دریافت فهرست…</p>}
            {listError && <p className='text-sm text-destructive'>{listError}</p>}
            {categoryResult && <>
              <p className='text-xs text-muted-foreground'>نمایش {categoryResult.total ? offset + 1 : 0} تا {Math.min(offset + categoryResult.items.length, categoryResult.total)} از {categoryResult.total}</p>
              {categoryResult.items.map((issue) => <article key={issue.issue_key} className='rounded-lg border p-4'>
                <div className='flex items-center justify-between gap-2'><h3 className='font-semibold'>{labels[issue.problem_type] ?? issue.problem_type}</h3><span className='text-xs'>{issue.severity}</span></div>
                <a href={issue.url} target='_blank' rel='noreferrer' dir='ltr' className='text-muted-foreground block break-all text-xs hover:underline'>{issue.url}</a>
                <RemediationAction siteId={siteId} issueKey={issue.issue_key} />
              </article>)}
              {categoryResult.total > 30 && <div className='flex gap-2'>
                <Button variant='outline' disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}>قبلی</Button>
                <Button variant='outline' disabled={offset + 30 >= categoryResult.total} onClick={() => setOffset(offset + 30)}>بعدی</Button>
              </div>}
            </>}
          </div>}
        </section>;
      })}</div>
    </>}
  </div>;
}
