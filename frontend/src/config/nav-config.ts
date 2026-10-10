import { NavGroup } from '@/types';

// Hidden from the sidebar and command palette for now; the pages stay reachable by URL.
export const hiddenNavUrls = new Set([
  '/dashboard/keywords',
  '/dashboard/content',
  '/dashboard/content-planner',
  '/dashboard/ai-content-test',
  '/dashboard/ai-studio',
  '/dashboard/ai-models',
  '/dashboard/internal-linking',
  '/dashboard/opportunities'
]);

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
      { title: 'میز عملیات و تیم', url: '/dashboard/work', icon: 'kanban', shortcut: ['w', 'w'], items: [],
        description: 'شیت کارها، کانبان، تایم‌لاین، تیم‌ها و گراف مسئولیت همهٔ سایت‌ها' },
      { title: 'داشبورد مدیریت', url: '/dashboard/team-management', icon: 'teams', items: [],
        description: 'تصویر کلی کار تیم، بار هر نفر، پروژه‌ها و روند پیشرفت' },
      { title: 'شروع راه‌اندازی', url: '/dashboard/onboarding', icon: 'sparkles', items: [],
        description: 'اتصال گوگل ← انتخاب سایت‌ها ← شروع تحلیل سئو (چهار قدم، بدون تنظیم فنی)' },
      { title: 'سایت‌ها', url: '/dashboard/sites', icon: 'sites', shortcut: ['s', 's'], items: [],
        description: 'مدیریت سایت‌ها، اتصال Search Console و GA4، حالت انتشار' }
    ]
  },
  {
    label: 'دانش',
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
      { title: 'تقویم محتوا', url: '/dashboard/calendar', icon: 'calendar', items: [],
        description: 'برنامه‌ریزی، نوشتن با هوش مصنوعی و انتشار زمان‌بندی‌شده در وردپرس — همه در یک تقویم' },
      { title: 'برنامه‌ریز پیشرفته', url: '/dashboard/content-planner', icon: 'planner', items: [],
        description: 'جدول برنامه‌ریزی، کانبان، دسته‌ها، نگاشت کلمات و پیشنهادهای مغز (فاز ۸.۵)' },
      { title: 'مغز محتوا', url: '/dashboard/content', icon: 'content', items: [],
        description: 'خط لوله تولید محتوا: ایده تا انتشار (فاز ۶)' }
    ]
  },
  {
    label: 'هوش مصنوعی و لینک‌سازی',
    items: [
      { title: 'آزمایش تولید محتوا', url: '/dashboard/ai-content-test', icon: 'flask', items: [],
        description: 'فضای موقت آزمایش تولید محتوا با Echo یا ارائه‌دهنده واقعی' },
      { title: 'استودیوی AI', url: '/dashboard/ai-studio', icon: 'sparkles', items: [],
        description: 'تولید چندعاملی محتوا با تأیید انسانی (فاز ۹)' },
      { title: 'مدل‌های AI', url: '/dashboard/ai-models', icon: 'ai', items: [],
        description: 'ارائه‌دهنده‌ها، مدل‌ها، مسیردهی، پرامپت‌ها، بودجه (فاز ۹)' },
      { title: 'لینک‌سازی داخلی', url: '/dashboard/internal-linking', icon: 'linking', items: [],
        description: 'پیشنهاد لینک داخلی و الگوهای یادگرفته‌شده (فاز ۱۳–۱۴)' },
      { title: 'فرصت‌های سئو', url: '/dashboard/opportunities', icon: 'opportunities', items: [],
        description: 'صفحات جایگاه ۵–۲۰، CTR پایین، شکاف محتوا (فاز ۱۵)' },
      { title: 'مشکلات سئو', url: '/dashboard/problems', icon: 'opportunities', items: [],
        description: 'بررسی و رفع مرحله‌ای مشکلات سایت آزمایشی' }
    ]
  },
  {
    label: 'سیستم',
    items: [
      { title: 'کال‌سنتر', url: '/dashboard/call-center', icon: 'phone', items: [],
        description: 'ثبت تماس، تعیین منبع سئو یا ادز و پایش برند، مدل و منطقه' },
      { title: 'مدیریت کاربران', url: '/dashboard/users', icon: 'teams', items: [],
        description: 'مدیریت فهرست اعضای تیم و نقش‌ها' },
      { title: 'تم داشبورد', url: '/dashboard/theme', icon: 'palette', items: [],
        description: 'قالب Gentelella، رنگ شاخص و حالت روشن یا تیره' },
      { title: 'گزارش سایت', url: '/dashboard/reports', icon: 'reports', items: [],
        description: 'موجودی URL، روند ماهانه، کارهای تیم، سنجه‌های GSC و GA4، مشکلات و فرصت‌ها' },
      { title: 'داده زنده تبلیغات', url: '/ads-data', icon: 'reports', items: [],
        description: 'IP، GCLID، session و رفتار زنده ورودی‌های تبلیغاتی' },
      { title: 'ترافیک و تماس‌ها', url: '/dashboard/traffic', icon: 'trendingUp', items: [],
        description: 'ورودی ارگانیک، رفتار کاربر و کلیک روی شماره تماس از ترکر فرست‌پارتی قالب' },
      { title: 'تنظیمات', url: '/dashboard/settings', icon: 'settings', items: [],
        description: 'اتصال به بک‌اند، توکن API، ترجیحات نمایش' }
    ]
  }
];
