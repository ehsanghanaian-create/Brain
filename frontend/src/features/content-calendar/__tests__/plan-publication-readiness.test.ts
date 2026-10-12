import { describe, expect, it } from 'vitest';
import type { ContentPlan } from '@/lib/api/client';
import { planPublicationChecks, planSignature } from '../components/plan-publication-readiness';

const plan = {
  id: 7, title: 'راهنمای انتخاب شلوار', primary_keyword: 'شلوار مردانه', intent: 'commercial',
  seo_title: 'راهنمای خرید شلوار مردانه', meta_description: 'مقایسهٔ مدل‌ها و انتخاب سایز',
  category_id: 3, category: { id: 3, name: 'راهنما', source: 'wordpress', parent_id: null },
  content_item_id: 10, slug: 'mens-pants-guide', heading_structure: [{ level: 2, text: 'انتخاب سایز' }],
  link_targets: [{ direction: 'to', node_id: 'x', url: 'https://salimore.com/shop/', title: 'فروشگاه', anchor: 'فروشگاه', reason_fa: '', score: 1 }],
  target_audience: 'خریداران پوشاک مردانه', metadata: {},
} as unknown as ContentPlan;

describe('publication work on existing article plans', () => {
  it('evaluates a saved plan even without opening a versioned draft', () => {
    expect(planPublicationChecks(plan).filter((check) => check.required && !check.passed)).toEqual([]);
  });

  it('shows missing work and invalidates editorial review when important fields change', () => {
    const changed = { ...plan, primary_keyword: '', content_item_id: null, meta_description: '' };
    const missing = planPublicationChecks(changed).filter((check) => check.required && !check.passed).map((check) => check.label);
    expect(missing).toContain('عبارت کلیدی اصلی تعیین شده است');
    expect(missing).toContain('عنوان سئو و توضیح متا ثبت شده‌اند');
    expect(missing).toContain('متن نسخه‌دار برای بازبینی وجود دارد');
    expect(planSignature(changed)).not.toBe(planSignature(plan));
  });
});
