'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api/client';
import type { components } from '@/lib/api/schema';
import { RemediationAction } from './remediation-action';

type Result = components['schemas']['RemediationIssuesOut'];

const labels: Record<string, string> = {
  orphan: 'صفحهٔ یتیم', no_body_inbound_links: 'لینک ورودی متنی ندارد', low_inbound_links: 'لینک ورودی کم',
  high_outbound_links: 'لینک خروجی زیاد', missing_h1: 'H1 ندارد', multiple_h1: 'چند H1', duplicate_h1: 'H1 تکراری',
  duplicate_title: 'عنوان تکراری', missing_meta_description: 'توضیح متا ندارد', images_missing_alt: 'تصویر بدون alt',
  missing_canonical: 'canonical ندارد', important_non_indexable: 'صفحهٔ مهم غیرقابل ایندکس',
  thin_content: 'محتوای کم', redirect_in_sitemap: 'ریدایرکت در سایت‌مپ'
};

export function ProblemsPage({ sites, initialSiteId }: { sites: { site_id: string; name: string }[]; initialSiteId: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(null);
    api<Result>(`/sites/${encodeURIComponent(siteId)}/remediation/problems?limit=30&offset=${offset}`)
      .then((data) => { if (active) setResult(data); })
      .catch((e) => { if (active) { setResult(null); setError(String(e?.message ?? e)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [siteId, offset]);
  return <div className='space-y-4'>
    <label className='flex items-center gap-2 text-sm'>سایت
      <select className='rounded border bg-background p-2' value={siteId} onChange={(e) => { setSiteId(e.target.value); setOffset(0); }}>
        {sites.map((s) => <option key={s.site_id} value={s.site_id}>{s.name}</option>)}
      </select>
    </label>
    {loading && <p>در حال دریافت مشکلات…</p>}
    {error && <p className='text-destructive'>{error}</p>}
    {result && <>
      <p className='text-muted-foreground text-sm'>{result.total} مشکل ثبت‌شده</p>
      <div className='space-y-2'>{result.items.map((issue) => <article key={issue.issue_key} className='rounded-lg border bg-card p-4'>
        <div className='flex items-center justify-between gap-2'><h2 className='font-semibold'>{labels[issue.problem_type] ?? issue.problem_type}</h2><span className='text-xs'>{issue.severity}</span></div>
        <a href={issue.url} target='_blank' rel='noreferrer' dir='ltr' className='text-muted-foreground block break-all text-xs hover:underline'>{issue.url}</a>
        <RemediationAction siteId={siteId} issueKey={issue.issue_key} />
      </article>)}</div>
      <div className='flex gap-2'>
        <Button variant='outline' disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}>قبلی</Button>
        <Button variant='outline' disabled={offset + 30 >= result.total} onClick={() => setOffset(offset + 30)}>بعدی</Button>
      </div>
    </>}
  </div>;
}
