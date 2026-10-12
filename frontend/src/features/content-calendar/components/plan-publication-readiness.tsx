'use client';

import { Badge } from '@/components/ui/badge';
import { ApiError, endpoints, type ContentPlan } from '@/lib/api/client';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';

const EDITORIAL = [
  ['facts', 'ادعاها و جزئیات محصولات از منبع اصلی بررسی شده‌اند'],
  ['intent', 'هدف جست‌وجو و تفاوت این مقاله با صفحات مشابه روشن است'],
  ['conversion', 'لینک‌های داخلی و مسیر رسیدن به محصول/خدمت مرتبط مشخص است'],
  ['assets', 'منابع، نویسنده و مجوز تصاویر مشخص‌اند'],
  ['technical', 'اسلاگ، canonical، متادیتای افزونهٔ SEO و Schema قبل/بعد انتشار بررسی می‌شوند'],
] as const;
type EditorialKey = (typeof EDITORIAL)[number][0];
type SavedReview = { signature?: string; checks?: Partial<Record<EditorialKey, boolean>>; updated_at?: string };

export function planSignature(plan: ContentPlan): string {
  return JSON.stringify({
    title: plan.title, keyword: plan.primary_keyword, intent: plan.serp_intent || plan.intent,
    seoTitle: plan.seo_title, description: plan.meta_description, category: plan.category_id,
    slug: plan.slug, headings: plan.heading_structure, links: plan.link_targets.map((link) => link.url).sort(),
    contentId: plan.content_item_id,
  });
}

export function planPublicationChecks(plan: ContentPlan) {
  return [
    { label: 'عنوان مقاله مشخص است', passed: !!plan.title?.trim(), required: true },
    { label: 'عبارت کلیدی اصلی تعیین شده است', passed: !!plan.primary_keyword?.trim(), required: true },
    { label: 'هدف جست‌وجو مشخص است', passed: !!(plan.serp_intent || plan.intent), required: true },
    { label: 'عنوان سئو و توضیح متا ثبت شده‌اند', passed: !!plan.seo_title?.trim() && !!plan.meta_description?.trim(), required: true },
    { label: 'دستهٔ واقعی وردپرس انتخاب شده است', passed: plan.category?.source === 'wordpress', required: true },
    { label: 'متن نسخه‌دار برای بازبینی وجود دارد', passed: !!plan.content_item_id, required: true },
    { label: 'اسلاگ پیشنهادی ثبت شده است', passed: !!plan.slug?.trim(), required: false },
    { label: 'ساختار H2 برای مقاله آماده است', passed: plan.heading_structure.some((heading) => heading.level === 2), required: false },
    { label: 'مقصد لینک داخلی پیشنهاد شده است', passed: plan.link_targets.length > 0, required: false },
    { label: 'مخاطب مقاله مشخص است', passed: !!plan.target_audience?.trim(), required: false },
  ];
}

export function PlanPublicationReadiness({ siteId, plan }: { siteId: string; plan: ContentPlan }) {
  const [current, setCurrent] = useState(plan);
  const [saving, setSaving] = useState(false);
  useEffect(() => { setCurrent(plan); }, [plan]);
  const checks = planPublicationChecks(current);
  const signature = planSignature(current);
  const saved = (current.metadata?.plan_publication_review ?? {}) as SavedReview;
  const editorial = saved.signature === signature ? saved.checks ?? {} : {};
  const passed = checks.filter((check) => check.required && check.passed).length;
  const required = checks.filter((check) => check.required).length;

  async function toggle(key: EditorialKey) {
    if (saving) return;
    setSaving(true);
    const review: SavedReview = { signature, checks: { ...editorial, [key]: !editorial[key] }, updated_at: new Date().toISOString() };
    try {
      const updated = await endpoints.planPatch(siteId, current.id, { metadata: { ...current.metadata, plan_publication_review: review } });
      setCurrent(updated);
    } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
    finally { setSaving(false); }
  }

  return <details open className='rounded-xl border bg-card p-3'>
    <summary className='flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 font-medium'>
      <span>کارهای سئو و انتشار همین مقاله</span><Badge variant={passed === required ? 'default' : 'secondary'}>{passed}/{required} بررسی اصلی</Badge>
    </summary>
    <p className='text-muted-foreground mt-1 text-xs'>بر اساس اطلاعات ذخیره‌شدهٔ این برنامه است. پس از ویرایش فیلدها، «ذخیره» را بزنید تا بررسی به‌روز شود.</p>
    {current.status === 'published' && !current.content_item_id && <p className='mt-2 rounded-md border border-amber-500/30 px-2 py-1.5 text-xs text-amber-700'>این مقاله «منتشرشده» ثبت شده اما متن نسخه‌دار در Brain ندارد؛ کنترل متن و متادیتای واقعی آن باید روی پست وردپرس انجام شود.</p>}
    <div className='mt-3 grid gap-3 text-xs md:grid-cols-2'>
      <div><p className='mb-2 font-medium'>از داده‌های برنامه</p><ul className='space-y-1.5'>{checks.map((check) => <li key={check.label} className='rounded-md border px-2 py-1.5'><span className={check.passed ? 'text-emerald-600' : check.required ? 'text-amber-600' : 'text-muted-foreground'}>{check.passed ? '✓' : check.required ? '○' : '◇'} </span>{check.label}{!check.required && <span className='text-muted-foreground'> · پیشنهادی</span>}</li>)}</ul></div>
      <div><p className='mb-2 font-medium'>تأیید سردبیر</p><ul className='space-y-1.5'>{EDITORIAL.map(([key, label]) => <li key={key}><label className='flex cursor-pointer items-start gap-2 rounded-md border px-2 py-2'><input type='checkbox' className='mt-0.5' checked={!!editorial[key]} disabled={saving} onChange={() => toggle(key)} /><span>{label}</span></label></li>)}</ul><p className='text-muted-foreground mt-2'>تأییدها با تغییر اطلاعات اصلی این برنامه نیازمند بازبینی دوباره‌اند. بررسی متن نهایی در بخش پیش‌نویس انجام می‌شود.</p></div>
    </div>
  </details>;
}
