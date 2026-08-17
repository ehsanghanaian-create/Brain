export const INTENT_FA: Record<string, string> = {
  informational: 'اطلاعاتی',
  navigational: 'ناوبری',
  commercial: 'تجاری',
  transactional: 'تراکنشی',
  local: 'محلی'
};
export const PRIORITY_FA: Record<string, string> = { high: 'بالا', medium: 'متوسط', low: 'کم' };
export const KW_STATUS_FA: Record<string, string> = { new: 'جدید', planned: 'برنامه‌ریزی‌شده', in_progress: 'در حال انجام', published: 'منتشرشده', ignored: 'نادیده' };
export const OPP_KIND_FA: Record<string, string> = { improve_page: 'بهبود صفحه', create_content: 'تولید محتوای جدید', update_title: 'به‌روزرسانی عنوان/متا', add_internal_links: 'افزودن لینک داخلی' };
export const OPP_STATUS_FA: Record<string, string> = { new: 'جدید', accepted: 'پذیرفته', dismissed: 'رد شده', done: 'انجام‌شده' };
export const FIELD_FA: Record<string, string> = {
  keyword: 'کلمه کلیدی', intent: 'اینتنت', cluster: 'خوشه', topic: 'موضوع', volume: 'حجم', difficulty: 'سختی', priority: 'اولویت',
  target_url: 'صفحه هدف', status: 'وضعیت', notes: 'یادداشت'
};
export const fa = new Intl.NumberFormat('fa-IR');
export const num = (v: unknown, d = 0) => (typeof v === 'number' ? fa.format(Number(v.toFixed(d))) : '—');
export const pct = (v: unknown) => (typeof v === 'number' ? `${(v * 100).toFixed(1)}٪` : '—');
