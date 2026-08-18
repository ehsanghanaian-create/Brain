import type { PlanStatus } from '@/lib/api/client';

export const PLAN_STATUS_ORDER: PlanStatus[] = ['planned', 'researching', 'brief_ready', 'writing', 'review', 'approved', 'published'];
export const PLAN_STATUS_FA: Record<PlanStatus, string> = { planned: 'برنامه‌ریزی‌شده', researching: 'در حال تحقیق', brief_ready: 'بریف آماده', writing: 'در حال نگارش', review: 'بازبینی', approved: 'تأییدشده', published: 'منتشرشده' };
export const PLAN_STATUS_COLOR: Record<PlanStatus, string> = { planned: '#64748b', researching: '#6366f1', brief_ready: '#0ea5e9', writing: '#f59e0b', review: '#a855f7', approved: '#22c55e', published: '#16a34a' };
export const PRIORITY_COLOR: Record<string, string> = { high: '#dc2626', medium: '#f59e0b', low: '#94a3b8' };
export const PRIORITY_FA: Record<string, string> = { high: 'بالا', medium: 'متوسط', low: 'پایین' };
export const INTENT_FA: Record<string, string> = { informational: 'اطلاعاتی', navigational: 'ناوبری', commercial: 'تجاری', transactional: 'تراکنشی', local: 'محلی' };
export const PAGE_TYPE_FA: Record<string, string> = { service_landing: 'لندینگ خدمت', location_landing: 'لندینگ مکان', pillar: 'صفحه ستون', article: 'مقاله', guide: 'راهنما', comparison: 'مقایسه', faq: 'پرسش‌های متداول', product: 'محصول', category_page: 'صفحه دسته', news: 'خبر' };
export const FUNNEL_FA: Record<string, string> = { awareness: 'آگاهی', consideration: 'بررسی', decision: 'تصمیم', retention: 'وفاداری' };
export const GAP_FA: Record<string, string> = { none: 'بدون شکاف', partial: 'جزئی', full: 'کامل' };
export const ROLE_FA: Record<string, string> = { primary: 'اصلی', secondary: 'ثانویه', supporting: 'پشتیبان', question: 'پرسش', gsc_query: 'کوئری GSC' };
export const SOURCE_FA: Record<string, string> = { wordpress: 'وردپرس', brain: 'مغز (موضوعی)', manual: 'دستی' };
export const ACTION_FA: Record<string, string> = { create_new: 'ساخت محتوای جدید', optimize_existing: 'بهینه‌سازی صفحه موجود', improve_page: 'بهبود صفحه موجود', add_to_cluster: 'افزودن به خوشه', merge: 'ادغام', category: 'پیشنهاد دسته', link_prep: 'لینک‌های داخلی', gap: 'شکاف محتوایی', schedule: 'زمان‌بندی' };
export const fa = new Intl.NumberFormat('fa-IR');
export const optionFa = (key: string, v: string): string => ({ intent: INTENT_FA, serp_intent: INTENT_FA, page_type: PAGE_TYPE_FA, priority: PRIORITY_FA, status: PLAN_STATUS_FA as Record<string, string>, funnel_stage: FUNNEL_FA, content_gap: GAP_FA } as Record<string, Record<string, string>>)[key]?.[v] ?? v;
