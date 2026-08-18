/** Visual vocabulary of the command center — same palette family as the Obsidian graph groups. */
export const NODE_STYLE: Record<string, { fa: string; color: string; short: string }> = {
  SITE: { fa: 'سایت', color: '#e11d48', short: 'S' },
  PAGE: { fa: 'صفحه', color: '#2563eb', short: 'P' },
  POST: { fa: 'نوشته', color: '#3b82f6', short: 'N' },
  CATEGORY: { fa: 'دسته', color: '#f59e0b', short: 'C' },
  TAG: { fa: 'برچسب', color: '#fbbf24', short: 'T' },
  QUERY: { fa: 'کوئری GSC', color: '#8b5cf6', short: 'Q' },
  KEYWORD: { fa: 'کلمه کلیدی', color: '#7c3aed', short: 'K' },
  BRAND: { fa: 'برند', color: '#a855f7', short: 'B' },
  MODEL: { fa: 'مدل', color: '#c084fc', short: 'M' },
  SERVICE: { fa: 'خدمت', color: '#14b8a6', short: 'X' },
  LOCATION: { fa: 'مکان', color: '#10b981', short: 'L' },
  SCHEMA: { fa: 'اسکیما', color: '#64748b', short: '{}' },
  SEO_PROBLEM: { fa: 'مشکل', color: '#dc2626', short: '!' },
  SEO_OPPORTUNITY: { fa: 'فرصت', color: '#16a34a', short: '↑' },
  CONTENT: { fa: 'محتوا', color: '#0ea5e9', short: 'D' },
  TOPIC: { fa: 'موضوع', color: '#f97316', short: 'O' },
  CONTENT_PLAN: { fa: 'برنامه محتوا', color: '#0891b2', short: 'PL' },
  CONTENT_CLUSTER: { fa: 'خوشه محتوایی', color: '#0d9488', short: 'CC' },
  SEARCH_INTENT: { fa: 'اینتنت جستجو', color: '#db2777', short: 'I' },
  FUNNEL_STAGE: { fa: 'مرحله قیف', color: '#9333ea', short: 'F' }
};

/** UI grouping of node types (the "node types" requirement: Keyword · Page · Entity · Schema · Content · Brand · Location · Problem). */
export const TYPE_FAMILIES: { key: string; fa: string; types: string[] }[] = [
  { key: 'keyword', fa: 'کلمه کلیدی', types: ['QUERY', 'KEYWORD'] },
  { key: 'page', fa: 'صفحه', types: ['PAGE', 'POST', 'CATEGORY', 'TAG', 'SITE'] },
  { key: 'entity', fa: 'موجودیت', types: ['MODEL', 'SERVICE'] },
  { key: 'brand', fa: 'برند', types: ['BRAND'] },
  { key: 'location', fa: 'مکان', types: ['LOCATION'] },
  { key: 'schema', fa: 'اسکیما', types: ['SCHEMA'] },
  { key: 'content', fa: 'محتوا', types: ['CONTENT', 'TOPIC'] },
  { key: 'planner', fa: 'برنامه محتوا', types: ['CONTENT_PLAN', 'CONTENT_CLUSTER', 'SEARCH_INTENT', 'FUNNEL_STAGE'] },
  { key: 'problem', fa: 'مشکل / فرصت', types: ['SEO_PROBLEM', 'SEO_OPPORTUNITY'] }
];

export const RELATION_FA: Record<string, string> = {
  HAS_PAGE: 'دارای صفحه',
  HAS_POST: 'دارای نوشته',
  HAS_CATEGORY: 'دارای دسته',
  HAS_TAG: 'دارای برچسب',
  BELONGS_TO: 'متعلق به',
  LINKS_TO: 'لینک به',
  ABOUT: 'درباره',
  OFFERS: 'ارائه می‌دهد',
  TARGETS: 'هدف',
  RANKS_FOR: 'رتبه برای',
  HAS_SCHEMA: 'دارای اسکیما',
  HAS_PROBLEM: 'دارای مشکل',
  HAS_OPPORTUNITY: 'دارای فرصت',
  KEYWORD_TARGETS: 'کلمه کلیدی هدف',
  CLUSTERED_IN: 'در خوشه',
  CONTENT_FOR: 'محتوا برای',
  SUGGESTED_LINK: 'لینک پیشنهادی',
  PUBLISHED_AS: 'منتشر شده به‌عنوان',
  LINK_OPPORTUNITY: 'فرصت لینک',
  SUPPORTS: 'پشتیبانی می‌کند',
  CONNECTED_TO: 'مرتبط با',
  CONTAINS: 'شامل',
  PLANNED_AS: 'برنامه‌ریزی‌شده به‌عنوان',
  HAS_INTENT: 'اینتنت',
  IN_STAGE: 'مرحله قیف'
};

export const RELATION_STYLE: Record<string, { color: string; dashed?: boolean }> = {
  LINKS_TO: { color: '#60a5fa' },
  RANKS_FOR: { color: '#a78bfa' },
  KEYWORD_TARGETS: { color: '#a78bfa', dashed: true },
  HAS_PROBLEM: { color: '#f87171', dashed: true },
  HAS_OPPORTUNITY: { color: '#4ade80', dashed: true },
  ABOUT: { color: '#c084fc' },
  OFFERS: { color: '#2dd4bf' },
  TARGETS: { color: '#34d399' },
  HAS_SCHEMA: { color: '#94a3b8', dashed: true },
  SUGGESTED_LINK: { color: '#fbbf24', dashed: true },
  LINK_OPPORTUNITY: { color: '#f97316', dashed: true },
  SUPPORTS: { color: '#22c55e', dashed: true },
  BELONGS_TO: { color: '#fbbf24' },
  CONNECTED_TO: { color: '#f97316', dashed: true },
  CONTAINS: { color: '#0891b2' },
  PLANNED_AS: { color: '#0ea5e9' },
  HAS_INTENT: { color: '#db2777', dashed: true },
  IN_STAGE: { color: '#9333ea', dashed: true }
};

export const CONTENT_STATUS_FA: Record<string, string> = {
  ok: 'سالم',
  thin: 'محتوای کم',
  non_indexable: 'غیرقابل ایندکس',
  needs_links: 'نیاز به لینک ورودی',
  unknown: 'خزیده نشده'
};

export const SEVERITY_FA: Record<string, string> = { high: 'بالا', medium: 'متوسط', low: 'کم' };
