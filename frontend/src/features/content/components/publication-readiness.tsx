'use client';

import { Badge } from '@/components/ui/badge';
import { ApiError, endpoints, type ContentDetail, type ContentDraft } from '@/lib/api/client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';

const MANUAL = [
  ['facts', 'ادعاها، قیمت و موجودی محصولات با منبع اصلی بررسی شده‌اند'],
  ['links', 'لینک‌های داخلی و مسیر رسیدن به محصول یا خدمت مرتبط بررسی شده‌اند'],
  ['rights', 'نویسنده، منابع و حق استفاده از تصاویر مشخص و تأیید شده‌اند'],
  ['search', 'عنوان و توضیح SEO، canonical و نوع Schema در وردپرس بازبینی می‌شوند'],
] as const;
type ManualKey = (typeof MANUAL)[number][0];
type SavedReview = { draft_id?: number; checks?: Partial<Record<ManualKey, boolean>>; updated_at?: string };

export type ReadinessCheck = { label: string; passed: boolean; required: boolean; detail?: string };

export function publicationChecks(item: ContentDetail | null, draft: ContentDraft | null, categoryId: string, canonicalUrl = ''): ReadinessCheck[] {
  const structure = draft?.structure;
  const links = structure?.links ?? [];
  const images = structure?.images ?? [];
  const isInternal = (href: string) => {
    if (href.startsWith('/') && !href.startsWith('//')) return true;
    try { return new URL(href).hostname === new URL(canonicalUrl || item?.url || '').hostname; }
    catch { return false; }
  };
  return [
    { label: 'آخرین نسخهٔ مقاله ثبت شده است', passed: !!draft && draft.id === item?.current_draft_id, required: true },
    { label: 'بازبینی آخرین نسخه آماده است', passed: !!draft && draft.review_status === 'ready', required: true },
    { label: 'مقاله برای انتشار تأیید شده است', passed: item?.status === 'approved' || item?.status === 'published', required: true },
    { label: 'عبارت هدف مشخص است', passed: !!item?.target_keyword?.trim(), required: true },
    { label: 'عنوان و خلاصهٔ مقاله آماده است', passed: !!(draft?.title || item?.title)?.trim() && !!draft?.meta_description?.trim(), required: true, detail: 'خلاصه به excerpt وردپرس ارسال می‌شود؛ ثبت آن در افزونهٔ SEO باید جداگانه بررسی شود.' },
    { label: 'ساختار مقاله دست‌کم یک H2 دارد', passed: !!structure?.h2?.length, required: true },
    { label: 'دستهٔ واقعی وردپرس انتخاب شده است', passed: !!categoryId, required: true },
    { label: 'در متن پیوند داخلی وجود دارد', passed: links.some((link) => isInternal(link.href)), required: true },
    { label: 'تصاویر داخل متن، در صورت وجود، متن جایگزین دارند', passed: images.every((image) => !!image.alt?.trim()), required: true },
    { label: 'پرسش مخاطب در متن پاسخ گرفته است', passed: !!structure?.questions?.length, required: false, detail: 'برای جست‌وجوی AI مفید است، اما به‌تنهایی نمایش یا ارجاع را تضمین نمی‌کند.' },
  ];
}

export function PublicationReadiness({ siteId, cid, categoryId, onReadyChange }: { siteId: string; cid: number; categoryId: string; onReadyChange?: (ready: boolean) => void }) {
  const [item, setItem] = useState<ContentDetail | null>(null);
  const [draft, setDraft] = useState<ContentDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [canonicalUrl, setCanonicalUrl] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true); setItem(null); setDraft(null); setError(null);
    (async () => {
      try {
        const [detail, site] = await Promise.all([endpoints.content(siteId, cid), endpoints.site(siteId)]);
        const latest = detail.current_draft_id ? await endpoints.contentDraft(siteId, cid, detail.current_draft_id) : null;
        if (active) { setItem(detail); setDraft(latest); setCanonicalUrl(site.canonical_url ?? ''); }
      } catch (e) {
        if (active) setError(e instanceof ApiError ? e.message : String(e));
      } finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [siteId, cid]);

  const saved = (item?.metadata?.publication_review ?? {}) as SavedReview;
  const checks = publicationChecks(item, draft, categoryId, canonicalUrl);
  const manual = saved.draft_id === draft?.id ? saved.checks ?? {} : {};
  const ready = !loading && !error && checks.filter((x) => x.required).every((x) => x.passed) && MANUAL.every(([key]) => manual[key]);
  useEffect(() => { onReadyChange?.(!!ready); }, [ready, onReadyChange]);

  async function toggle(key: ManualKey) {
    if (!item || !draft || saving) return;
    const review: SavedReview = { draft_id: draft.id, checks: { ...manual, [key]: !manual[key] }, updated_at: new Date().toISOString() };
    setSaving(true);
    try {
      await endpoints.updateContent(siteId, cid, { metadata: { ...item.metadata, publication_review: review } });
      setItem({ ...item, metadata: { ...item.metadata, publication_review: review } });
    } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
    finally { setSaving(false); }
  }

  return <section className='rounded-xl border bg-card p-4' aria-label='آمادگی انتشار مقاله'>
    <div className='flex flex-wrap items-center justify-between gap-2'>
      <div><h3 className='font-semibold'>آمادگی انتشار و سئو</h3><p className='text-muted-foreground text-xs'>بررسی‌ها به آخرین نسخهٔ ذخیره‌شدهٔ مقاله وابسته‌اند. با تغییر متن، تأییدهای دستی دوباره لازم می‌شوند.</p></div>
      <Badge variant={ready ? 'default' : 'secondary'}>{loading ? 'در حال بررسی…' : ready ? 'آمادهٔ انتشار' : `${checks.filter((x) => x.required && x.passed).length}/${checks.filter((x) => x.required).length} بررسی خودکار`}</Badge>
    </div>
    {error ? <p className='text-destructive mt-3 text-xs'>بررسی انجام نشد: {error}</p> : <div className='mt-3 grid gap-4 md:grid-cols-2'>
      <div><p className='mb-2 text-xs font-medium'>بررسی خودکار</p><ul className='space-y-1.5'>{checks.map((check) => <li key={check.label} className='rounded-md border px-2 py-1.5 text-xs'><span className={check.passed ? 'text-emerald-600' : check.required ? 'text-amber-600' : 'text-muted-foreground'}>{check.passed ? '✓' : check.required ? '○' : '◇'} </span>{check.label}{!check.required && <span className='text-muted-foreground'> · پیشنهادی</span>}{check.detail && <p className='text-muted-foreground mt-0.5 ps-4'>{check.detail}</p>}</li>)}</ul></div>
      <div><p className='mb-2 text-xs font-medium'>تأیید سردبیر · نسخه {draft?.version ?? '—'}</p><ul className='space-y-1.5'>{MANUAL.map(([key, label]) => <li key={key}><label className='flex cursor-pointer items-start gap-2 rounded-md border px-2 py-2 text-xs'><input type='checkbox' className='mt-0.5' checked={!!manual[key]} disabled={!draft || saving} onChange={() => toggle(key)} /><span>{label}</span></label></li>)}</ul><p className='text-muted-foreground mt-2 text-[11px]'>پس از انتشار، URL عمومی، canonical، Schema و وضعیت ایندکس را روی خروجی واقعی دوباره بررسی کنید.</p>{item?.url && <Link className='mt-2 inline-block text-xs underline' href={`/dashboard/ai-visibility?site=${encodeURIComponent(siteId)}`}>پایش دیده‌شدن در جست‌وجوی AI ←</Link>}</div>
    </div>}
  </section>;
}
