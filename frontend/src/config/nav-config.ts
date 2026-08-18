import { NavGroup } from '@/types';

/**
 * SEO Brain navigation — one entry per product area (docs/seo-brain/01-architecture.md §5).
 * Titles are Persian (RTL UI). `description` feeds tooltips / help (Phase 18).
 * Items are enabled as their phase lands; not-yet-built areas render a roadmap placeholder page.
 */
export const navGroups: NavGroup[] = [
  {
    label: 'نمای کلی',
    items: [
      { title: 'داشبورد', url: '/dashboard/overview', icon: 'dashboard', shortcut: ['d', 'd'], items: [],
        description: 'وضعیت کلی سایت‌ها، گراف دانش و سلامت سیستم' },
      { title: 'سایت‌ها', url: '/dashboard/sites', icon: 'sites', shortcut: ['s', 's'], items: [],
        description: 'مدیریت سایت‌ها، اتصال Search Console و GA4، حالت انتشار' }
    ]
  },
  {
    label: 'دانش و کلمات کلیدی',
    items: [
      { title: 'گراف دانش', url: '/dashboard/graph', icon: 'graph', shortcut: ['g', 'g'], items: [],
        description: 'گراف صفحات، کوئری‌ها، موجودیت‌ها و اسکیما (فاز ۴)' },
      { title: 'کلمات کلیدی', url: '/dashboard/keywords', icon: 'keywords', items: [],
        description: 'ورود، خوشه‌بندی و نقشه موضوعی کلمات کلیدی (فاز ۵)' }
    ]
  },
  {
    label: 'محتوا',
    items: [
      { title: 'برنامه‌ریز محتوا', url: '/dashboard/content-planner', icon: 'planner', items: [],
        description: 'جدول برنامه‌ریزی، کانبان، تقویم، دسته‌ها، نگاشت کلمات و پیشنهادهای مغز (فاز ۸.۵)' },
      { title: 'مغز محتوا', url: '/dashboard/content', icon: 'content', items: [],
        description: 'خط لوله تولید محتوا: ایده تا انتشار (فاز ۶)' },
      { title: 'تقویم محتوایی', url: '/dashboard/calendar', icon: 'calendar', items: [],
        description: 'زمان‌بندی محتوا با نمای ماهانه و هفتگی (فاز ۷)' }
    ]
  },
  {
    label: 'هوش مصنوعی و لینک‌سازی',
    items: [
      { title: 'استودیوی AI', url: '/dashboard/ai-studio', icon: 'sparkles', items: [],
        description: 'تولید چندعاملی محتوا با تأیید انسانی (فاز ۹)' },
      { title: 'مدل‌های AI', url: '/dashboard/ai-models', icon: 'ai', items: [],
        description: 'ارائه‌دهنده‌ها، مدل‌ها، مسیردهی، پرامپت‌ها، بودجه (فاز ۹)' },
      { title: 'لینک‌سازی داخلی', url: '/dashboard/internal-linking', icon: 'linking', items: [],
        description: 'پیشنهاد لینک داخلی و الگوهای یادگرفته‌شده (فاز ۱۳–۱۴)' },
      { title: 'فرصت‌های سئو', url: '/dashboard/opportunities', icon: 'opportunities', items: [],
        description: 'صفحات جایگاه ۵–۲۰، CTR پایین، شکاف محتوا (فاز ۱۵)' }
    ]
  },
  {
    label: 'سیستم',
    items: [
      { title: 'گزارش‌ها', url: '/dashboard/reports', icon: 'reports', items: [],
        description: 'گزارش رشد کلمات کلیدی، عملکرد محتوا و مشکلات سئو (فاز ۱۷)' },
      { title: 'تنظیمات', url: '/dashboard/settings', icon: 'settings', items: [],
        description: 'اتصال به بک‌اند، توکن API، ترجیحات نمایش' }
    ]
  }
];
