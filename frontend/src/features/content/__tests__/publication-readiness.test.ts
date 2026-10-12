import { describe, expect, it } from 'vitest';
import type { ContentDetail, ContentDraft } from '@/lib/api/client';
import { publicationChecks } from '../components/publication-readiness';

const item = {
  id: 5, current_draft_id: 9, title: 'راهنمای خرید', target_keyword: 'خرید لباس',
  status: 'approved', url: null,
} as ContentDetail;
const draft = {
  id: 9, version: 2, title: 'راهنمای خرید', meta_description: 'راهنمای انتخاب لباس مناسب', review_status: 'ready',
  structure: { h1: [], h2: ['انتخاب'], h3: [], paragraphs: [], links: [{ href: 'https://salimore.com/shop/', anchor: 'فروشگاه' }], images: [{ src: '/a.webp', alt: 'پیراهن مردانه' }], questions: [], faq: false, word_count: 420 },
} as unknown as ContentDraft;

describe('article publishing checks', () => {
  it('recognizes links on the site canonical host before a post has a public URL', () => {
    const checks = publicationChecks(item, draft, '12', 'https://salimore.com');
    expect(checks.filter((check) => check.required && !check.passed)).toEqual([]);
    expect(checks.find((check) => check.label.includes('پرسش مخاطب'))?.required).toBe(false);
  });

  it('flags a stale draft, missing excerpt, external-only links and missing image alt', () => {
    const checks = publicationChecks({ ...item, current_draft_id: 10 }, {
      ...draft, meta_description: '', structure: { ...draft.structure, links: [{ href: 'https://example.com/', anchor: 'منبع' }], images: [{ src: '/a.webp', alt: '' }] },
    }, '', 'https://salimore.com');
    const missing = checks.filter((check) => check.required && !check.passed).map((check) => check.label);
    expect(missing).toContain('آخرین نسخهٔ مقاله ثبت شده است');
    expect(missing).toContain('عنوان و خلاصهٔ مقاله آماده است');
    expect(missing).toContain('دستهٔ واقعی وردپرس انتخاب شده است');
    expect(missing).toContain('در متن پیوند داخلی وجود دارد');
    expect(missing).toContain('تصاویر داخل متن، در صورت وجود، متن جایگزین دارند');
  });
});
