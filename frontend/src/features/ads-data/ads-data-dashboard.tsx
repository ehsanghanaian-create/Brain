'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { api, endpoints } from '@/lib/api/client';
import {
  IconAlertTriangle,
  IconChartBar,
  IconCheck,
  IconChevronLeft,
  IconClock,
  IconCopy,
  IconDatabase,
  IconDownload,
  IconEye,
  IconInfoCircle,
  IconListDetails,
  IconRefresh,
  IconSearch,
  IconShieldCheck,
  IconShieldX,
  IconUsers,
  IconWorld,
  type Icon
} from '@tabler/icons-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { toast } from 'sonner';
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { createIpBlockController } from './ip-blocking';

type Summary = {
  generated_at: string;
  hours: number;
  mode: string;
  blocking_enabled: boolean;
  totals: { events: number; unique_ips: number; visitors: number; sessions: number; landings: number; tel_clicks: number; form_submits: number; product_view_sessions: number; add_to_cart_sessions: number; view_cart_sessions: number; auth_started_sessions: number; auth_success_sessions: number; account_created_sessions: number; checkout_sessions: number; gateway_redirect_sessions: number; purchase_sessions: number; auth_successes: number; account_creations: number; checkout_starts: number; gateway_redirects: number; purchases: number; payment_failures: number; google_ads_confirmed_events: number; google_ads_likely_events: number; google_ads_sessions: number; google_ads_click_ids: number; linked_customers: number };
  recent: { events_5m: number; events_60m: number; ips_5m: number; ips_60m: number };
  hourly: { hour: string; events: number; unique_ips: number; landings: number; tel_clicks: number }[];
  event_types: { event_type: string; count: number }[];
  campaigns: { campaign: string; events: number; sessions: number; landings: number; tel_clicks: number }[];
};

type IpRow = {
  ip_address: string;
  ip_hash: string;
  ip_prefix: string;
  ip_source: string | null;
  proxy_ip: string | null;
  ip_confidence: string;
  ip_resolution_version: string;
  risk_score: number;
  risk_reasons: string[];
  events: number;
  events_5m: number;
  sessions: number;
  visitors: number;
  gclids: number;
  google_ads_confirmed_events: number;
  google_ads_likely_events: number;
  ads_sessions: number;
  ads_landings: number;
  ads_tel_clicks: number;
  landings: number;
  tel_clicks: number;
  form_submits: number;
  first_seen: string;
  last_seen: string;
  latest_page_path: string | null;
  latest_referrer: string | null;
  latest_user_agent: string | null;
  geo_country: string | null;
  geo_country_code: string | null;
  geo_city: string | null;
  geo_isp: string | null;
  geo_asn: string | null;
  geo_asname: string | null;
  geo_mobile: boolean;
  geo_proxy: boolean;
  geo_hosting: boolean;
};

type EventRow = {
  id: number;
  event_uuid: string;
  event_type: string;
  occurred_at_client: string | null;
  received_at: string;
  ip_address: string;
  ip_prefix: string;
  ip_source: string | null;
  proxy_ip: string | null;
  ip_confidence: string;
  ip_resolution_version: string;
  ads_attribution: string;
  visitor_id: string | null;
  session_id: string | null;
  gclid: string | null;
  gbraid: string | null;
  wbraid: string | null;
  utm_campaign: string | null;
  campaign_id: string | null;
  ad_group_id: string | null;
  creative_id: string | null;
  keyword: string | null;
  match_type: string | null;
  device: string | null;
  network: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_term: string | null;
  utm_content: string | null;
  landing_path: string | null;
  page_path: string | null;
  referrer: string | null;
  user_agent: string | null;
  browser_language: string | null;
  browser_timezone: string | null;
  screen_size: string | null;
  metadata: Record<string, unknown>;
};

type Session = {
  person_key: string;
  session_id: string | null;
  visitor_id: string | null;
  ip_address: string;
  ip_hash: string;
  ip_confidence: string;
  proxy_ip: string | null;
  first_seen: string;
  last_seen: string;
  last_page: string | null;
  landing_path: string | null;
  referrer: string | null;
  device: string | null;
  user_agent: string | null;
  browser_language: string | null;
  browser_timezone: string | null;
  screen_size: string | null;
  utm_campaign: string | null;
  utm_term: string | null;
  utm_content: string | null;
  campaign_id: string | null;
  gclid: string | null;
  ads_attribution: string;
  events: number;
  landings: number;
  page_views: number;
  scrolls: number;
  heartbeats: number;
  tel_clicks: number;
  form_submits: number;
  whatsapp_clicks: number;
  clicks: number;
  section_views: number;
  article_cta_clicks: number;
  view_items: number;
  add_to_carts: number;
  remove_from_carts: number;
  view_carts: number;
  begin_checkouts: number;
  add_shipping_infos: number;
  add_payment_infos: number;
  purchases: number;
  auth_requests: number;
  auth_successes: number;
  auth_failures: number;
  account_creations: number;
  auth_logouts: number;
  checkout_auth_requireds: number;
  gateway_redirects: number;
  payment_paid: number;
  payment_pending: number;
  payment_failures: number;
  distinct_pages: number;
  risk_score: number;
  risk_reasons: string[];
  geo_country: string | null;
  geo_country_code: string | null;
  geo_city: string | null;
  geo_isp: string | null;
  geo_asn: string | null;
  geo_asname: string | null;
  geo_mobile: boolean;
  geo_proxy: boolean;
  geo_hosting: boolean;
  geo_tz_mismatch: boolean;
  visitor_events: number;
  visitor_ips: number;
  visitor_sessions: number;
  visitor_landings: number;
  visitor_click_ids: number;
};

type RiskFilter = 'all' | 'review' | 'high' | 'normal';
type Keyword = {
  keyword: string;
  sources?: ('valuetrack_keyword' | 'utm_term')[];
  events: number;
  landings: number;
  tel_clicks: number;
  sessions: number;
  unique_ips: number;
  suspicious_ips: number;
  high_risk_ips: number;
  unique_visitors: number;
  bot_visitors: number;
  fraud_events: number;
  fraud_rate: number;
  last_seen: string;
};

type PageInsight = {
  page_path: string;
  events: number;
  sessions: number;
  page_views: number;
  clicks: number;
  scroll_25_sessions: number;
  scroll_50_sessions: number;
  scroll_75_sessions: number;
  scroll_90_sessions: number;
  avg_dwell_ms: number | null;
  product_views: number;
  add_to_carts: number;
  auth_starts: number;
  auth_successes: number;
  account_creations: number;
  checkout_starts: number;
  gateway_redirects: number;
  purchases: number;
};

type PageReport = {
  pages: PageInsight[];
  entries: { page_path: string; sessions: number }[];
  actions: { page_path: string; action: string; count: number }[];
};

type LiveAlerts = {
  generated_at: string;
  window_minutes: number;
  status: 'safe' | 'review' | 'danger';
  phone_events: { id: number; received_at: string; attribution: 'google_ads_confirmed' | 'other' }[];
  ad_entries: { id: number; received_at: string; landing_path: string | null; ip_hash: string }[];
  suspects: { ip_address: string; ip_hash: string; click_ids: number; sessions: number; landings: number; last_seen: string; level: 'review' | 'danger' }[];
  traffic_anomaly: { level: 'safe' | 'review' | 'danger'; current_click_ids: number; current_calls: number; current_ips: number; current_sessions: number; baseline_call_rate: number; expected_calls: number; dynamic_click_threshold: number; history_windows: number; enough_history: boolean; reasons: string[] };
};

type DashboardTab = 'sessions' | 'pages' | 'keywords' | 'logs' | 'ips' | 'overview';
const EVENT_PAGE_SIZE = 100;

const fa = new Intl.NumberFormat('fa-IR');
const time = new Intl.DateTimeFormat('fa-IR', {
  timeZone: 'Asia/Tehran',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit'
});
const EVENT_FA: Record<string, string> = {
  landing: 'ورود به سایت',
  page_view: 'مشاهده صفحه',
  heartbeat: 'حضور در صفحه',
  scroll: 'اسکرول صفحه',
  tel_click: 'کلیک تماس',
  whatsapp_click: 'کلیک واتساپ',
  form_start: 'شروع فرم',
  form_submit: 'ارسال فرم',
  page_exit: 'خروج از صفحه',
  click: 'کلیک عمومی',
  section_view: 'مشاهده بخش صفحه',
  article_cta_click: 'کلیک محصول از مقاله',
  view_item_list: 'نمایش فهرست محصول',
  select_item: 'انتخاب محصول',
  view_item: 'مشاهده محصول',
  add_to_cart: 'افزودن به سبد',
  remove_from_cart: 'حذف از سبد',
  view_cart: 'مشاهده سبد',
  begin_checkout: 'شروع تسویه‌حساب',
  add_shipping_info: 'ثبت روش ارسال',
  add_payment_info: 'ثبت روش پرداخت',
  purchase: 'خرید تأییدشده',
  auth_otp_requested: 'درخواست رمز یک‌بارمصرف',
  auth_otp_request_failed: 'خطای ارسال رمز یک‌بارمصرف',
  auth_otp_verified: 'تأیید رمز یک‌بارمصرف',
  auth_otp_verify_failed: 'خطای تأیید رمز یک‌بارمصرف',
  auth_login_success: 'ورود موفق با رمز',
  auth_login_failed: 'ورود ناموفق با رمز',
  auth_registration_complete: 'ساخت حساب کاربری',
  auth_password_recovery_requested: 'درخواست بازیابی رمز',
  auth_password_recovery_failed: 'خطای بازیابی رمز',
  auth_logout: 'خروج از حساب',
  checkout_auth_required: 'نیاز به ورود در تسویه‌حساب',
  payment_gateway_redirect: 'انتقال به درگاه پرداخت',
  payment_gateway_error: 'خطای انتقال به درگاه',
  payment_return_invalid: 'بازگشت نامعتبر از درگاه',
  payment_status_paid: 'پرداخت موفق',
  payment_status_pending: 'پرداخت در انتظار تأیید',
  payment_status_failed: 'پرداخت ناموفق',
  style_builder_entry: 'ورود به استایل‌ساز',
  stylist_start: 'شروع ساخت استایل',
  stylist_results_view: 'نمایش پیشنهاد استایل',
  stylist_apply: 'اعمال استایل پیشنهادی',
  stylist_feedback: 'بازخورد استایل',
  stylist_add_to_cart: 'افزودن استایل به سبد'
};

function isServiceRelevantEvent(eventType: string) {
  if (/^(auth_|payment_|stylist_)/.test(eventType)) return false;
  return ![
    'article_cta_click', 'view_item_list', 'select_item', 'view_item',
    'add_to_cart', 'remove_from_cart', 'view_cart', 'begin_checkout',
    'add_shipping_info', 'add_payment_info', 'purchase', 'checkout_auth_required',
    'style_builder_entry'
  ].includes(eventType);
}
const RISK_FA: Record<string, string> = {
  landing_velocity: 'تعداد ورود غیرعادی',
  landing_velocity_watch: 'افزایش تعداد ورود',
  tel_click_burst: 'تکرار زیاد کلیک تماس',
  many_sessions: 'نشست‌های متعدد از یک IP',
  five_minute_burst: 'جهش فعالیت در ۵ دقیقه',
  datacenter_ip: 'IP متعلق به دیتاسنتر است (سرور/ربات، نه کاربر واقعی)',
  proxy_ip: 'IP پروکسی یا VPN است',
  session_flood: 'تعداد رویداد بسیار زیاد در یک نشست (الگوی ربات)',
  tz_country_mismatch: 'ناهماهنگی منطقهٔ زمانی مرورگر با کشور IP (نشانهٔ VPN/تقلب)',
  visitor_ip_rotation: 'یک کاربر از ۲ IP دیتاسنتر/پروکسی/خارجی یا بیشتر — چرخش IP مشکوک (موبایل عادی ایران حساب نمی‌شود)',
  visitor_multi_ip: 'یک کاربر با حداقل یک IP مشکوک (دیتاسنتر/خارجی) در کنار IPهای دیگر',
  visitor_repeat_clicks: 'چند شناسهٔ یکتای ورودی تبلیغ برای یک مرورگر ثبت شده',
  ip_not_reliable: 'این رکورد قبل از اصلاح مسیر CDN ثبت شده و IP آن قابل اتکا نیست'
};
const TEST_CAMPAIGNS = new Set(['collector_validation', 'collector_live_validation', 'production-collector-verification']);
const LOG_USER_COLORS = [
  { dot: 'bg-cyan-500', badge: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300' },
  { dot: 'bg-violet-500', badge: 'border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300' },
  { dot: 'bg-fuchsia-500', badge: 'border-fuchsia-500/30 bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-300' },
  { dot: 'bg-indigo-500', badge: 'border-indigo-500/30 bg-indigo-500/10 text-indigo-700 dark:text-indigo-300' },
  { dot: 'bg-teal-500', badge: 'border-teal-500/30 bg-teal-500/10 text-teal-700 dark:text-teal-300' },
  { dot: 'bg-lime-500', badge: 'border-lime-500/30 bg-lime-500/10 text-lime-700 dark:text-lime-300' }
] as const;

function logIdentity(row: EventRow) {
  // visitor_id survives page changes and new sessions in the same browser, so one
  // real visitor keeps the same label and pastel color throughout the raw log.
  return row.visitor_id || row.session_id || row.ip_address || row.ip_prefix || `event-${row.id}`;
}

function identityNumber(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0);
}

function rangeLabel(hours: number) {
  if (hours === 0) return 'همه داده‌ها';
  if (hours === 168) return '۷ روز';
  return `${fa.format(hours)} ساعت`;
}

function riskInfo(score: number) {
  if (score >= 70) return { label: 'ریسک بالا', dot: 'bg-rose-500', badge: 'border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300' };
  if (score >= 35) return { label: 'نیازمند بررسی', dot: 'bg-amber-500', badge: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300' };
  if (score >= 15) return { label: 'زیر نظر', dot: 'bg-sky-500', badge: 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300' };
  return { label: 'عادی', dot: 'bg-emerald-500', badge: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' };
}

function confidenceInfo(value: string) {
  if (value === 'trusted_proxy') return { label: 'IP بازدیدکننده · تأییدشده', className: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' };
  if (value === 'direct_peer') return { label: 'اتصال مستقیم', className: 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300' };
  if (value === 'legacy_unverified') return { label: 'قدیمی · IP لبه CDN', className: 'border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300' };
  return { label: 'IP تأییدنشده', className: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300' };
}

function adsInfo(value: string) {
  if (value === 'google_ads_confirmed') return { label: 'Google Ads قطعی', className: 'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300' };
  if (value === 'google_ads_likely') return { label: 'Google Ads محتمل', className: 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300' };
  if (value === 'paid_traffic_likely') return { label: 'تبلیغ پولی محتمل', className: 'border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300' };
  return { label: 'بدون مدرک Ads', className: 'text-muted-foreground' };
}

function rowHasConfirmedAds(row: EventRow) {
  return Boolean(row.gclid || row.gbraid || row.wbraid);
}

function flagEmoji(code: string | null) {
  if (!code || code.length !== 2 || !/^[a-zA-Z]{2}$/.test(code)) return '';
  const base = 0x1f1e6;
  const cc = code.toUpperCase();
  return String.fromCodePoint(base + cc.charCodeAt(0) - 65, base + cc.charCodeAt(1) - 65);
}

function sessionIsOnline(lastSeen: string) {
  return Date.now() - Date.parse(lastSeen) < 60_000;
}

function durationLabel(first: string, last: string) {
  const seconds = Math.max(0, Math.round((Date.parse(last) - Date.parse(first)) / 1000));
  if (seconds < 60) return `${fa.format(seconds)} ثانیه`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${fa.format(minutes)} دقیقه`;
  const hours = Math.floor(minutes / 60);
  return `${fa.format(hours)} ساعت و ${fa.format(minutes % 60)} دقیقه`;
}

function parseUserAgent(ua: string | null): { browser: string; os: string } {
  if (!ua) return { browser: '—', os: '—' };
  let os = 'نامشخص';
  if (/Windows NT 10/.test(ua)) os = 'Windows 10/11';
  else if (/Windows NT/.test(ua)) os = 'Windows';
  else if (/Android[ /]?([\d.]+)?/.test(ua)) os = `Android ${ua.match(/Android[ /]?([\d.]+)/)?.[1] ?? ''}`.trim();
  else if (/iPhone|iPad|iPod/.test(ua)) { const m = ua.match(/OS (\d+)[._]/); os = `iOS ${m?.[1] ?? ''}`.trim(); }
  else if (/Mac OS X/.test(ua)) os = 'macOS';
  else if (/CrOS/.test(ua)) os = 'ChromeOS';
  else if (/Linux/.test(ua)) os = 'Linux';
  let browser = 'نامشخص';
  if (/bot|spider|crawl|headless|python-|curl|wget|okhttp|Go-http/i.test(ua)) browser = 'ربات/اسکریپت';
  else if (/Edg\//.test(ua)) browser = 'Edge';
  else if (/OPR\/|Opera/.test(ua)) browser = 'Opera';
  else if (/SamsungBrowser/.test(ua)) browser = 'Samsung Internet';
  else if (/Firefox\//.test(ua)) browser = 'Firefox';
  else if (/Chrome\//.test(ua)) browser = 'Chrome';
  else if (/Safari\//.test(ua)) browser = 'Safari';
  const version = ua.match(/(?:Edg|OPR|Firefox|Chrome|Version)\/(\d+)/);
  if (version && browser !== 'نامشخص' && browser !== 'ربات/اسکریپت') browser += ` ${version[1]}`;
  return { browser, os };
}

// Campaign templates can contain brace-wrapped placeholders; strip the braces
// so the campaign reads cleanly without exposing template syntax.
function cleanCampaign(value: string | null): string | null {
  if (!value) return null;
  const cleaned = value.replace(/[{}]/g, '').trim();
  return cleaned || null;
}

function GeoInfo({ row, showIsp = true }: { row: IpRow | Session; showIsp?: boolean }) {
  const place = [row.geo_country, row.geo_city].filter(Boolean).join(' · ');
  if (!place && !row.geo_isp) return <p className='text-muted-foreground mt-1.5 text-[10px]'>موقعیت: —</p>;
  return (
    <div className='mt-1.5 space-y-1'>
      {place && <p className='text-[11px]'><span aria-hidden='true'>{flagEmoji(row.geo_country_code)} </span>{place}</p>}
      {showIsp && row.geo_isp && <p className='text-muted-foreground text-[10px]' dir='ltr'>{row.geo_isp}{row.geo_asname ? ` · ${row.geo_asname}` : ''}</p>}
      {(row.geo_hosting || row.geo_proxy || row.geo_mobile) && (
        <div className='flex flex-wrap gap-1'>
          {row.geo_hosting && <Badge variant='outline' className='border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300 text-[10px]'>دیتاسنتر</Badge>}
          {row.geo_proxy && <Badge variant='outline' className='border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300 text-[10px]'>پروکسی/VPN</Badge>}
          {row.geo_mobile && <Badge variant='outline' className='text-[10px]'>موبایل</Badge>}
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value, hint, icon: MetricIcon, tone = 'default' }: {
  label: string;
  value: number;
  hint: string;
  icon: Icon;
  tone?: 'default' | 'warning';
}) {
  return (
    <Card className={tone === 'warning' ? 'border-amber-500/30 bg-amber-500/[0.04]' : 'border-border/70'}>
      <CardContent className='flex items-start justify-between gap-3 p-4 sm:p-5'>
        <div className='min-w-0'>
          <p className='text-muted-foreground text-xs font-medium'>{label}</p>
          <p className='mt-1 text-2xl font-bold tracking-tight tabular-nums'>{fa.format(value)}</p>
          <p className='text-muted-foreground mt-1 truncate text-[11px]'>{hint}</p>
        </div>
        <div className={`rounded-xl p-2.5 ${tone === 'warning' ? 'bg-amber-500/10 text-amber-600' : 'bg-primary/8 text-primary'}`}>
          <MetricIcon className='size-5' aria-hidden='true' />
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className='flex min-h-52 flex-col items-center justify-center px-5 text-center'>
      <div className='bg-muted mb-3 rounded-full p-3'><IconDatabase className='text-muted-foreground size-5' /></div>
      <p className='font-medium'>{title}</p>
      <p className='text-muted-foreground mt-1 max-w-md text-xs leading-6'>{description}</p>
    </div>
  );
}

function IpBlockToggle({ ip, blocked, busy, ready, onToggle }: { ip: string; blocked: boolean; busy: boolean; ready: boolean; onToggle: () => void }) {
  return <Button type='button' size='sm' variant={blocked ? 'destructive' : 'outline'} role='switch'
    aria-checked={blocked} aria-label={`بلاک IP ${ip}`} aria-busy={busy}
    disabled={!ready || busy || !ip} onClick={onToggle}
    title={ready ? blocked ? 'رفع مسدودی این IP در سایت' : 'مسدود کردن این IP در سایت' : 'وضعیت مسدودسازی هنوز در دسترس نیست'}>
    <span aria-hidden='true' dir='ltr' className={`inline-flex h-4 w-7 items-center rounded-full px-0.5 ${blocked ? 'bg-destructive' : 'bg-muted-foreground/40'}`}>
      <span className={`size-3 rounded-full bg-white transition-transform ${blocked ? 'translate-x-3' : ''}`} />
    </span>
    {busy ? 'در حال ثبت…' : !ready ? 'وضعیت نامشخص' : blocked ? 'بلاک شده' : 'بلاک IP'}
  </Button>;
}

export function AdsDataDashboard({ siteId, siteLabel }: { siteId: string; siteLabel: string }) {
  const siteQuery = encodeURIComponent(siteId);
  const ipBlockController = useMemo(() => createIpBlockController(siteId, endpoints), [siteId]);
  const ipBlockState = useSyncExternalStore(ipBlockController.subscribe, ipBlockController.getSnapshot, ipBlockController.getSnapshot);
  const blockedIps = ipBlockState.blockedIps;
  useEffect(() => {
    void ipBlockController.load();
    return () => ipBlockController.dispose();
  }, [ipBlockController]);
  async function toggleIpBlock(ip: string) {
    const result = await ipBlockController.toggle(ip);
    if (result) {
      if (result.success) toast.success(result.message);
      else toast.error(result.message);
    }
  }
  function ipBlockControl(ip: string) {
    return <IpBlockToggle ip={ip} blocked={blockedIps.has(ip)} busy={ipBlockState.pendingIps.has(ip)}
      ready={ipBlockState.status === 'ready'} onToggle={() => void toggleIpBlock(ip)} />;
  }
  const [hours, setHours] = useState(24);
  const [tab, setTab] = useState<DashboardTab>('sessions');
  const [summary, setSummary] = useState<Summary | null>(null);
  const [liveAlerts, setLiveAlerts] = useState<LiveAlerts | null>(null);
  const [pageReport, setPageReport] = useState<PageReport>({ pages: [], entries: [], actions: [] });
  const [ips, setIps] = useState<IpRow[]>([]);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [query, setQuery] = useState('');
  const [riskFilter, setRiskFilter] = useState<RiskFilter>('all');
  const [eventFilter, setEventFilter] = useState('all');
  const [adsFilter, setAdsFilter] = useState<'all' | 'ads' | 'confirmed' | 'unattributed'>('all');
  const [logQueryInput, setLogQueryInput] = useState('');
  const [logQuery, setLogQuery] = useState('');
  const [eventPage, setEventPage] = useState(0);
  const [eventTotal, setEventTotal] = useState(0);
  const [selectedIp, setSelectedIp] = useState<IpRow | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<EventRow | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [keywords, setKeywords] = useState<Keyword[]>([]);
  const [selectedSession, setSelectedSession] = useState<Session | null>(null);
  const [sessionEvents, setSessionEvents] = useState<EventRow[]>([]);
  const [sessionEventsLoading, setSessionEventsLoading] = useState(false);
  const [copiedIp, setCopiedIp] = useState(false);
  const [soundOn, setSoundOn] = useState(() => {
    if (typeof window === 'undefined') return true;
    return window.localStorage.getItem('adsDataSound') !== 'off';
  });
  const [audioReady, setAudioReady] = useState(false);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const lastPhoneEventIdRef = useRef<number | null>(null);
  const lastAdEntryIdRef = useRef<number | null>(null);
  const knownLiveSuspectsRef = useRef<Set<string> | null>(null);

  const ensureAudio = useCallback(() => {
    if (typeof window === 'undefined') return null;
    if (!audioCtxRef.current) {
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (Ctx) audioCtxRef.current = new Ctx();
    }
    const ctx = audioCtxRef.current;
    if (ctx && ctx.state === 'suspended') void ctx.resume();
    return ctx;
  }, []);

  const unlockAudio = useCallback(async () => {
    const ctx = ensureAudio();
    if (!ctx) return false;
    try {
      if (ctx.state === 'suspended') await ctx.resume();
      const ready = ctx.state === 'running';
      setAudioReady(ready);
      return ready;
    } catch {
      setAudioReady(false);
      return false;
    }
  }, [ensureAudio]);

  // کوتاه و دلنشین: به‌ازای هر «کلیک تماس» جدید پخش می‌شود
  const playDing = useCallback(() => {
    const ctx = ensureAudio();
    if (!ctx) return;
    const now = ctx.currentTime;
    ([[880, 0], [1320, 0.09]] as [number, number][]).forEach(([freq, offset]) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = freq;
      osc.connect(gain);
      gain.connect(ctx.destination);
      const t = now + offset;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.55, t + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.55);
      osc.start(t);
      osc.stop(t + 0.6);
    });
  }, [ensureAudio]);

  // صدای بسیار کوتاه و کم‌حجم برای هر ورودی تبلیغاتی یکتای تازه.
  const playEntryTick = useCallback(() => {
    const ctx = ensureAudio();
    if (!ctx) return;
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 520;
    osc.connect(gain);
    gain.connect(ctx.destination);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.07, now + 0.006);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.12);
    osc.start(now);
    osc.stop(now + 0.14);
  }, [ensureAudio]);

  // آژیر بالا-پایین: وقتی یک IP جدید با ریسک بالا (کلیک مشکوک) دیده شود
  const playSiren = useCallback(() => {
    const ctx = ensureAudio();
    if (!ctx) return;
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sawtooth';
    osc.connect(gain);
    gain.connect(ctx.destination);
    gain.gain.setValueAtTime(0.3, now);
    let t = now;
    for (let i = 0; i < 4; i += 1) {
      osc.frequency.setValueAtTime(620, t);
      osc.frequency.linearRampToValueAtTime(1180, t + 0.32);
      osc.frequency.linearRampToValueAtTime(620, t + 0.64);
      t += 0.64;
    }
    gain.gain.setValueAtTime(0.3, t - 0.06);
    gain.gain.linearRampToValueAtTime(0.0001, t);
    osc.start(now);
    osc.stop(t + 0.05);
  }, [ensureAudio]);

  const toggleSound = useCallback(() => {
    if (soundOn && audioReady) {
      setSoundOn(false);
      window.localStorage.setItem('adsDataSound', 'off');
      return;
    }
    setSoundOn(true);
    window.localStorage.setItem('adsDataSound', 'on');
    void unlockAudio().then((ready) => { if (ready) playDing(); });
  }, [audioReady, playDing, soundOn, unlockAudio]);

  // پخش نمونهٔ هر دو صدا برای تست دستی (مستقل از رویدادهای زنده)
  const testSounds = useCallback(() => {
    void unlockAudio().then((ready) => {
      if (!ready) return;
      playDing();
      window.setTimeout(() => playSiren(), 900);
    });
  }, [playDing, playSiren, unlockAudio]);

  // مرورگرها تا اولین تعامل کاربر اجازه پخش صدا نمی‌دهند؛ با اولین کلیک آزاد می‌شود
  useEffect(() => {
    const unlock = () => { void unlockAudio(); };
    window.addEventListener('pointerdown', unlock, { once: true });
    return () => window.removeEventListener('pointerdown', unlock);
  }, [unlockAudio]);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const [nextSummary, nextIps, nextEvents, nextSessions, nextKeywords, nextPages] = await Promise.all([
        api<Summary>(`/ads-data/summary?site_id=${siteQuery}&hours=${hours}`),
        api<{ items: IpRow[] }>(`/ads-data/ips?site_id=${siteQuery}&hours=${hours}&limit=10000`),
        api<{ items: EventRow[]; total: number }>(
          `/ads-data/events?site_id=${siteQuery}&hours=${hours}&limit=${EVENT_PAGE_SIZE}&offset=${eventPage * EVENT_PAGE_SIZE}` +
          `${eventFilter !== 'all' ? `&event_type=${encodeURIComponent(eventFilter)}` : ''}` +
          `${adsFilter !== 'all' ? `&attribution=${adsFilter}` : ''}` +
          `${logQuery ? `&q=${encodeURIComponent(logQuery)}` : ''}`
        ),
        api<{ items: Session[] }>(`/ads-data/sessions?site_id=${siteQuery}&hours=${hours}&limit=1000`),
        api<{ items: Keyword[] }>(`/ads-data/keywords?site_id=${siteQuery}&hours=${hours}&limit=500`),
        api<PageReport>(`/ads-data/pages?site_id=${siteQuery}&hours=${hours}&limit=100`)
      ]);
      setSummary(nextSummary);
      setIps(nextIps.items);
      setEvents(nextEvents.items);
      setEventTotal(nextEvents.total);
      setSessions(nextSessions.items);
      setKeywords(nextKeywords.items);
      setPageReport(nextPages);
      setLastUpdated(new Date());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [adsFilter, eventFilter, eventPage, hours, logQuery, siteQuery]);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(true), 5_000);
    return () => window.clearInterval(id);
  }, [load]);

  const loadAlerts = useCallback(async () => {
    try {
      setLiveAlerts(await api<LiveAlerts>(`/ads-data/alerts?site_id=${siteQuery}`));
    } catch {
      // The main dashboard error already communicates connectivity failures.
    }
  }, [siteQuery]);

  useEffect(() => {
    lastPhoneEventIdRef.current = null;
    lastAdEntryIdRef.current = null;
    knownLiveSuspectsRef.current = null;
    void loadAlerts();
    const id = window.setInterval(() => void loadAlerts(), 3_000);
    return () => window.clearInterval(id);
  }, [loadAlerts]);

  // هشدار صوتی مستقل از بازه گزارش است: تماس از همه کانال‌ها دینگ می‌زند،
  // ولی آژیر حمله فقط از پنجره زنده پنج‌دقیقه‌ای Google Ads می‌آید.
  useEffect(() => {
    if (!liveAlerts) return;
    const newestPhoneId = liveAlerts.phone_events[0]?.id ?? null;
    const previousPhoneId = lastPhoneEventIdRef.current;
    if (soundOn && audioReady && previousPhoneId !== null) {
      const freshCount = liveAlerts.phone_events.filter((event) => event.id > previousPhoneId).length;
      for (let index = 0; index < Math.min(freshCount, 4); index += 1) {
        window.setTimeout(() => playDing(), index * 650);
      }
    }
    if (newestPhoneId !== null) lastPhoneEventIdRef.current = Math.max(previousPhoneId ?? 0, newestPhoneId);

    const newestAdId = liveAlerts.ad_entries[0]?.id ?? null;
    const previousAdId = lastAdEntryIdRef.current;
    if (soundOn && audioReady && previousAdId !== null && newestAdId !== null && newestAdId > previousAdId) playEntryTick();
    if (newestAdId !== null) lastAdEntryIdRef.current = Math.max(previousAdId ?? 0, newestAdId);

    const dangerHashes = liveAlerts.suspects.filter((row) => row.level === 'danger').map((row) => row.ip_hash);
    const known = knownLiveSuspectsRef.current;
    if (soundOn && audioReady && known !== null && dangerHashes.some((hash) => !known.has(hash))) playSiren();
    const nextKnown = known ?? new Set<string>();
    dangerHashes.forEach((hash) => nextKnown.add(hash));
    knownLiveSuspectsRef.current = nextKnown;
  }, [audioReady, liveAlerts, playDing, playEntryTick, playSiren, soundOn]);

  // When a session is opened, load its full chronological event timeline.
  useEffect(() => {
    if (!selectedSession) {
      setSessionEvents([]);
      return;
    }
    let cancelled = false;
    const key = selectedSession.session_id || selectedSession.visitor_id || selectedSession.ip_address;
    setSessionEventsLoading(true);
    api<{ items: EventRow[] }>(`/ads-data/events?site_id=${siteQuery}&hours=0&limit=500&q=${encodeURIComponent(key)}`)
      .then((res) => { if (!cancelled) setSessionEvents(res.items); })
      .catch(() => { if (!cancelled) setSessionEvents([]); })
      .finally(() => { if (!cancelled) setSessionEventsLoading(false); });
    return () => { cancelled = true; };
  }, [selectedSession, siteQuery]);

  const suspicious = useMemo(() => ips.filter((row) => row.risk_score >= 35), [ips]);
  const highRisk = useMemo(() => ips.filter((row) => row.risk_score >= 70), [ips]);
  const topRisk = useMemo(
    () => ips.filter((row) => row.risk_score >= 35).toSorted((a, b) => b.risk_score - a.risk_score).slice(0, 3),
    [ips],
  );
  const verifiedIps = useMemo(() => ips.filter((row) => row.ip_confidence === 'trusted_proxy' || row.ip_confidence === 'direct_peer'), [ips]);
  const chart = useMemo(() => (summary?.hourly ?? []).map((row) => ({ ...row, label: time.format(new Date(row.hour)) })), [summary]);
  const serviceEventTypes = (summary?.event_types ?? []).filter((row) => isServiceRelevantEvent(row.event_type));
  const maxEventCount = Math.max(1, ...serviceEventTypes.map((row) => row.count));

  const filteredIps = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return [...ips]
      .filter((row) => {
        if (riskFilter === 'high' && row.risk_score < 70) return false;
        if (riskFilter === 'review' && (row.risk_score < 35 || row.risk_score >= 70)) return false;
        if (riskFilter === 'normal' && row.risk_score >= 35) return false;
        if (!normalized) return true;
        return [row.ip_address, row.latest_page_path, row.latest_referrer, row.latest_user_agent,
                row.geo_country, row.geo_city, row.geo_isp, row.geo_asname, ...(row.risk_reasons ?? [])]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(normalized));
      })
      .sort((a, b) => b.risk_score - a.risk_score || Date.parse(b.last_seen) - Date.parse(a.last_seen));
  }, [ips, query, riskFilter]);

  const selectedEvents = useMemo(
    () => selectedIp ? events.filter((row) => row.ip_address === selectedIp.ip_address && isServiceRelevantEvent(row.event_type)).slice(0, 20) : [],
    [events, selectedIp]
  );

  const visibleEvents = useMemo(() => events.filter((row) => isServiceRelevantEvent(row.event_type)), [events]);

  const confirmedAdsSessions = useMemo(() => {
    const sessions = new Set<string>();
    for (const row of visibleEvents) {
      if (row.session_id && rowHasConfirmedAds(row)) sessions.add(row.session_id);
    }
    return sessions;
  }, [visibleEvents]);

  const eventAdsInfo = (row: EventRow) => {
    if (rowHasConfirmedAds(row) && row.event_type === 'landing') {
      return { label: 'ورود از Google Ads', className: 'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300' };
    }
    if (row.ads_attribution === 'google_ads_confirmed' || (row.session_id && confirmedAdsSessions.has(row.session_id))) {
      return { label: 'ادامهٔ نشست Ads', className: 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300' };
    }
    return adsInfo(row.ads_attribution);
  };

  const logUsers = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of visibleEvents) {
      const identity = logIdentity(row);
      counts.set(identity, (counts.get(identity) ?? 0) + 1);
    }
    const shortLabelCounts = new Map<number, number>();
    for (const identity of counts.keys()) {
      const shortNumber = 100 + (identityNumber(identity) % 900);
      shortLabelCounts.set(shortNumber, (shortLabelCounts.get(shortNumber) ?? 0) + 1);
    }
    const users = new Map<string, { label: string; count: number; color: (typeof LOG_USER_COLORS)[number] }>();
    for (const [identity, count] of counts) {
      const hash = identityNumber(identity);
      const shortNumber = 100 + (hash % 900);
      const collisionSuffix = (shortLabelCounts.get(shortNumber) ?? 0) > 1
        ? `-${hash.toString(36).slice(-2).toUpperCase()}`
        : '';
      users.set(identity, {
        // Keep the friendly short label. Only add a stable suffix when two
        // unrelated visitors would otherwise receive the same display number.
        label: `کاربر ${fa.format(shortNumber)}${collisionSuffix}`,
        count,
        color: LOG_USER_COLORS[hash % LOG_USER_COLORS.length]
      });
    }
    return users;
  }, [visibleEvents]);

  const riskByIp = useMemo(() => new Map(ips.map((row) => [row.ip_address, row.risk_score])), [ips]);

  const logRowTone = (row: EventRow) => {
    const risk = riskByIp.get(row.ip_address) ?? 0;
    if (risk >= 70 || row.ip_confidence === 'legacy_unverified') return 'border-r-2 border-r-rose-500 bg-rose-500/[0.035]';
    if (risk >= 35 || row.ip_confidence === 'unknown') return 'border-r-2 border-r-amber-500 bg-amber-500/[0.035]';
    return 'border-r-2 border-r-transparent';
  };

  const sessionSectionCoverage = useMemo(() => {
    const seen = new Set<string>();
    const unseen = new Set<string>();
    for (const row of sessionEvents) {
      const page = row.page_path ?? 'صفحه نامشخص';
      const seenSection = row.metadata.section;
      const unseenSections = row.metadata.unseen_sections;
      if (row.event_type === 'section_view' && typeof seenSection === 'string') {
        seen.add(`${page} · ${seenSection}`);
      }
      if (row.event_type === 'page_exit' && typeof unseenSections === 'string') {
        unseenSections.split('|').filter(Boolean).forEach((section) => unseen.add(`${page} · ${section}`));
      }
    }
    seen.forEach((section) => unseen.delete(section));
    return { seen: [...seen], unseen: [...unseen] };
  }, [sessionEvents]);

  const copyIp = async () => {
    if (!selectedIp) return;
    try {
      await navigator.clipboard.writeText(selectedIp.ip_address);
      setCopiedIp(true);
      window.setTimeout(() => setCopiedIp(false), 1500);
    } catch {
      setCopiedIp(false);
    }
  };

  const openIp = (row: IpRow) => {
    setSelectedIp(row);
    setCopiedIp(false);
  };

  const reviewMessage = liveAlerts?.status === 'danger'
    ? { tone: 'danger', title: 'الگوی حملهٔ احتمالی همین حالا دیده شده', body: `در ۱۵ دقیقهٔ اخیر ${fa.format(liveAlerts.traffic_anomaly.current_click_ids)} ورودی تبلیغاتی یکتا از ${fa.format(liveAlerts.traffic_anomaly.current_ips)} IP و ${fa.format(liveAlerts.traffic_anomaly.current_calls)} تماس ثبت شده است.` }
    : liveAlerts?.status === 'review'
      ? { tone: 'warning', title: 'الگوی زنده نیازمند بررسی است', body: `در ۱۵ دقیقهٔ اخیر ${fa.format(liveAlerts.traffic_anomaly.current_click_ids)} ورودی یکتا از ${fa.format(liveAlerts.traffic_anomaly.current_ips)} IP و ${fa.format(liveAlerts.traffic_anomaly.current_calls)} تماس دیده شده است.` }
      : highRisk.length
    ? { tone: 'danger', title: `${fa.format(highRisk.length)} IP با ریسک بالا دیده شده`, body: 'ابتدا جزئیات این IPها و توالی زمانی رویدادهایشان را بررسی کنید.' }
    : suspicious.length
      ? { tone: 'warning', title: `${fa.format(suspicious.length)} IP نیازمند بررسی است`, body: 'سیستم الگوی پرتکرار دیده؛ این علامت به‌تنهایی به معنی کلیک تقلبی قطعی نیست.' }
      : { tone: 'safe', title: 'در بازه انتخاب‌شده رفتار غیرعادی واضحی دیده نشد', body: 'سامانه همچنان فعال است و هر ۵ ثانیه داده‌های جدید را بررسی می‌کند.' };
  const eventPageCount = Math.max(1, Math.ceil(eventTotal / EVENT_PAGE_SIZE));
  const eventStart = eventTotal ? eventPage * EVENT_PAGE_SIZE + 1 : 0;
  const eventEnd = Math.min(eventTotal, (eventPage + 1) * EVENT_PAGE_SIZE);
  const engagedSessions = sessions.filter((session) =>
    session.distinct_pages >= 2 || session.scrolls >= 2 || session.clicks > 0 || session.view_items > 0,
  ).length;
  const logCsvUrl = `/api/backend/ads-data/events.csv?site_id=${siteQuery}&hours=${hours}` +
    `${eventFilter !== 'all' ? `&event_type=${encodeURIComponent(eventFilter)}` : ''}` +
    `${adsFilter !== 'all' ? `&attribution=${adsFilter}` : ''}` +
    `${logQuery ? `&q=${encodeURIComponent(logQuery)}` : ''}`;

  return (
    <main className='bg-muted/20 min-h-screen' dir='rtl'>
      <div className='mx-auto w-full max-w-[1480px] space-y-5 p-3 sm:p-6 lg:p-8'>
        <section className='border-border/70 bg-background overflow-hidden rounded-2xl border shadow-sm'>
          <div className='flex flex-col justify-between gap-5 p-5 sm:p-6 lg:flex-row lg:items-center'>
            <div className='min-w-0'>
              <div className='mb-3 flex flex-wrap items-center gap-2'>
                <Badge className='border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'>
                  <span className='me-1.5 size-2 animate-pulse rounded-full bg-emerald-500' />دریافت زنده فعال
                </Badge>
                <Badge variant='outline'>فقط پایش؛ مسدودسازی خاموش</Badge>
              </div>
              <h1 className='text-2xl font-bold tracking-tight sm:text-3xl'>پایش ورود، تماس و رفتار کاربران</h1>
              <div className='text-muted-foreground mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs sm:text-sm'>
                <span className='flex items-center gap-1.5' dir='ltr'><IconWorld className='size-4' />{siteLabel}</span>
                <span className='flex items-center gap-1.5'><IconClock className='size-4' />آخرین به‌روزرسانی: {lastUpdated ? time.format(lastUpdated) : loading ? 'در حال دریافت…' : '—'}</span>
              </div>
            </div>

            <div className='flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center'>
              <div className='bg-muted flex overflow-x-auto rounded-xl p-1' role='group' aria-label='بازه زمانی'>
                {[1, 6, 24, 168, 0].map((value) => (
                  <Button key={value} size='sm' variant={hours === value ? 'default' : 'ghost'} className='flex-1 px-3 sm:flex-none' onClick={() => { setHours(value); setEventPage(0); }}>
                    {rangeLabel(value)}
                  </Button>
                ))}
              </div>
              <div className='flex gap-2'>
                <Button className='flex-1' size='sm' variant={soundOn && audioReady ? 'default' : 'outline'} onClick={toggleSound} aria-pressed={soundOn && audioReady} title='دینگ برای همهٔ کلیک‌های تماس؛ آژیر فقط برای حملهٔ Google Ads'>
                  <span aria-hidden='true'>{soundOn && audioReady ? '🔔' : '🔕'}</span>{soundOn && audioReady ? 'هشدار فعال' : 'فعال‌کردن صدا'}
                </Button>
                <Button className='flex-1' size='sm' variant='outline' onClick={testSounds} title='پخش نمونهٔ دینگ و آژیر برای اطمینان از سالم بودن صدا'>
                  <span aria-hidden='true'>🔊</span>تست صدا
                </Button>
                <Button className='flex-1' size='sm' variant='outline' onClick={() => void load()} disabled={loading}>
                  <IconRefresh className={loading ? 'animate-spin' : ''} />تازه‌سازی
                </Button>
                <Button className='flex-1' size='sm' nativeButton={false} render={<a href={`/api/backend/ads-data/events.csv?site_id=${siteQuery}&hours=0`} />}>
                  <IconDownload />CSV تمام تاریخچه
                </Button>
              </div>
            </div>
          </div>
          <div className='border-border/70 bg-muted/35 flex items-start gap-2 border-t px-5 py-3 text-xs leading-5 sm:px-6'>
            <IconInfoCircle className='text-muted-foreground mt-0.5 size-4 shrink-0' />
            <p><span className='font-medium'>اعتبار IP:</span> فقط رکورد دارای برچسب سبز «تأییدشده» برای تحلیل IP استفاده می‌شود. رکوردهای قبل از اصلاح CDN با برچسب قرمز نگه داشته شده‌اند اما در امتیاز ریسک دخالت ندارند. سیستم فعلاً کسی را خودکار مسدود نمی‌کند.</p>
          </div>
        </section>

        {error && (
          <div className='flex items-start gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-700 dark:text-rose-300'>
            <IconAlertTriangle className='mt-0.5 size-5 shrink-0' />
            <div><p className='font-medium'>دریافت داده با مشکل روبه‌رو شد</p><p className='mt-1 text-xs opacity-80'>{error}</p></div>
          </div>
        )}

        <section className={`overflow-hidden rounded-2xl border ${reviewMessage.tone === 'danger' ? 'border-rose-500/35 bg-rose-500/[0.06]' : reviewMessage.tone === 'warning' ? 'border-amber-500/35 bg-amber-500/[0.06]' : 'border-emerald-500/30 bg-emerald-500/[0.05]'}`}>
          <div className='flex flex-col gap-4 p-4 sm:p-5 lg:flex-row lg:items-center lg:justify-between'>
            <div className='flex min-w-0 items-start gap-3'>
              <div className={`mt-0.5 rounded-full p-2.5 ${reviewMessage.tone === 'danger' ? 'bg-rose-500/15 text-rose-600' : reviewMessage.tone === 'warning' ? 'bg-amber-500/15 text-amber-600' : 'bg-emerald-500/15 text-emerald-600'}`}>
                {reviewMessage.tone === 'safe' ? <IconCheck className='size-5' /> : <IconAlertTriangle className='size-5' />}
              </div>
              <div className='min-w-0'>
                <p className='text-muted-foreground text-xs font-medium'>پایش زنده · تماس از همهٔ ورودی‌ها، تشخیص حمله فقط روی Ads</p>
                <h2 className='mt-1 text-base font-bold sm:text-lg'>{reviewMessage.title}</h2>
                <p className='text-muted-foreground mt-1 text-xs leading-6'>{reviewMessage.body}</p>
              </div>
            </div>
            <div className='grid grid-cols-3 gap-2 text-center lg:w-[390px] lg:shrink-0'>
              <div className='bg-background/80 rounded-xl border p-2.5'><p className='text-lg font-bold tabular-nums'>{fa.format(Math.max(liveAlerts?.suspects.filter((row) => row.level === 'danger').length ?? 0, liveAlerts?.traffic_anomaly.level === 'danger' ? 1 : 0))}</p><p className='text-muted-foreground text-[10px]'>خطر زنده</p></div>
              <div className='bg-background/80 rounded-xl border p-2.5'><p className='text-lg font-bold tabular-nums'>{fa.format(liveAlerts?.traffic_anomaly.current_click_ids ?? 0)}</p><p className='text-muted-foreground text-[10px]'>ورودی یکتا · ۱۵ دقیقه</p></div>
              <div className='bg-background/80 rounded-xl border p-2.5'><p className='text-lg font-bold tabular-nums'>{fa.format(liveAlerts?.traffic_anomaly.current_calls ?? 0)}</p><p className='text-muted-foreground text-[10px]'>تماس Ads · ۱۵ دقیقه</p></div>
            </div>
          </div>

          {topRisk.length > 0 && (
            <div className='border-border/60 grid gap-2 border-t p-3 sm:grid-cols-3 sm:p-4'>
              {topRisk.map((row) => (
                <button key={row.ip_hash} type='button' onClick={() => openIp(row)} className='bg-background/80 hover:border-primary/50 rounded-xl border p-3 text-start transition-colors'>
                  <div className='flex items-center justify-between gap-2'>
                    <span className='font-mono text-xs font-semibold' dir='ltr'>{row.ip_address}</span>
                    <Badge variant='outline' className={riskInfo(row.risk_score).badge}>{riskInfo(row.risk_score).label}</Badge>
                  </div>
                  <p className='text-muted-foreground mt-2 text-[11px] leading-5'>
                    {fa.format(row.gclids)} کلیک Ads یکتا · {fa.format(row.ads_sessions)} نشست Ads · {fa.format(row.ads_landings)} مراجعه Ads · {fa.format(row.ads_tel_clicks)} تماس
                  </p>
                  <span className='text-primary mt-2 inline-flex items-center gap-1 text-[11px]'>مشاهدهٔ شواهد <IconChevronLeft className='size-3.5' /></span>
                </button>
              ))}
            </div>
          )}

          <div className='border-border/60 flex flex-col gap-2 border-t px-4 py-3 sm:flex-row sm:items-center sm:justify-between'>
            <p className='text-muted-foreground text-[11px]'>عدد «کلیک Ads» فقط شناسهٔ یکتای تبلیغ است؛ بازدید صفحه و heartbeat در آن شمرده نمی‌شود.</p>
            <Button size='sm' variant={highRisk.length ? 'default' : 'outline'} onClick={() => { setRiskFilter(highRisk.length ? 'high' : suspicious.length ? 'review' : 'all'); setTab('ips'); }}>
              {highRisk.length ? 'بررسی موارد پرخطر' : suspicious.length ? 'بررسی موارد مشکوک' : 'مشاهدهٔ پایش IP'}<IconChevronLeft />
            </Button>
          </div>
        </section>

        <section className='grid gap-3 sm:grid-cols-2 xl:grid-cols-3'>
          <MetricCard label='سشن‌های واقعی' value={summary?.totals.sessions ?? sessions.length} hint={hours === 0 ? 'از شروع ثبت داده' : `در ${rangeLabel(hours)} اخیر`} icon={IconUsers} />
          <MetricCard label='سشن درگیرشده' value={engagedSessions} hint='حداقل دو صفحه، تعامل یا اسکرول' icon={IconEye} />
          <MetricCard label='کلیک تماس' value={summary?.totals.tel_clicks ?? 0} hint='از همهٔ مسیرهای ورودی سایت' icon={IconListDetails} />
          <MetricCard label='ارسال فرم' value={summary?.totals.form_submits ?? 0} hint='فرم‌های تکمیل‌شدهٔ ثبت‌شده' icon={IconCheck} />
          <MetricCard label='سشن ورودی Google Ads' value={summary?.totals.google_ads_sessions ?? 0} hint='هر سشن فقط یک‌بار؛ نه heartbeat و scroll' icon={IconWorld} />
          <MetricCard label='شناسه کلیک یکتای Ads' value={summary?.totals.google_ads_click_ids ?? 0} hint='GCLID / GBRAID / WBRAID یکتا' icon={IconChartBar} />
        </section>

        <Tabs value={tab} onValueChange={(value) => setTab(value as DashboardTab)} className='gap-4'>
          <div className='overflow-x-auto pb-1'>
            <TabsList className='h-11 min-w-max p-1'>
              <TabsTrigger value='sessions' className='px-4'><IconUsers />بازدیدکننده‌ها <Badge variant='secondary' className='ms-1'>{fa.format(sessions.length)}</Badge></TabsTrigger>
              <TabsTrigger value='pages' className='px-4'><IconEye />رفتار صفحات <Badge variant='secondary' className='ms-1'>{fa.format(pageReport.pages.length)}</Badge></TabsTrigger>
              <TabsTrigger value='keywords' className='px-4'><IconSearch />کلمات کلیدی <Badge variant='secondary' className='ms-1'>{fa.format(keywords.length)}</Badge></TabsTrigger>
              <TabsTrigger value='logs' className='px-4'><IconListDetails />لاگ خام <Badge variant='secondary' className='ms-1'>{fa.format(eventTotal)}</Badge></TabsTrigger>
              <TabsTrigger value='ips' className='px-4'><IconShieldCheck />بررسی IPها <Badge variant='secondary' className='ms-1'>{fa.format(ips.length)}</Badge></TabsTrigger>
              <TabsTrigger value='overview' className='px-4'><IconChartBar />نمای کلی</TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value='sessions' className='space-y-4'>
            <Card className='border-border/70'>
              <CardHeader className='gap-2'>
                <div className='flex flex-col justify-between gap-2 sm:flex-row sm:items-center'>
                  <div>
                    <CardTitle>بازدیدکننده‌ها به‌صورت زنده</CardTitle>
                    <CardDescription className='mt-1'>هر کارت یک نفر (نشست) است؛ همهٔ رفتارهای او در یک ردیف جمع شده و هر ۵ ثانیه به‌روز می‌شود. برای دیدن سفر کامل، روی کارت بزنید.</CardDescription>
                  </div>
                  <Badge className='w-fit border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'>
                    <span className='me-1.5 size-2 animate-pulse rounded-full bg-emerald-500' />
                    {fa.format(sessions.filter((s) => sessionIsOnline(s.last_seen)).length)} نفر همین حالا آنلاین
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                {sessions.length ? (
                  <div className='space-y-2.5'>
                    {sessions.map((s) => {
                      const online = sessionIsOnline(s.last_seen);
                      const risk = riskInfo(s.risk_score);
                      const ua = parseUserAgent(s.user_agent);
                      const place = [s.geo_country, s.geo_city].filter(Boolean).join(' · ');
                      return (
                        <button key={s.person_key} type='button' onClick={() => setSelectedSession(s)} className='hover:border-primary/50 hover:bg-muted/30 block w-full rounded-xl border p-3 text-start transition-colors sm:p-4'>
                          <div className='flex flex-col gap-3 lg:flex-row lg:items-center'>
                            <div className='flex min-w-0 flex-1 items-center gap-3'>
                              <span className='relative flex size-2.5 shrink-0'>
                                {online && <span className='absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75' />}
                                <span className={`relative inline-flex size-2.5 rounded-full ${online ? 'bg-emerald-500' : 'bg-muted-foreground/40'}`} />
                              </span>
                              <div className='min-w-0'>
                                <div className='flex flex-wrap items-center gap-2'>
                                  <span className='font-mono text-sm font-semibold' dir='ltr'>{s.ip_address}</span>
                                  <Badge variant='outline' className={`text-[10px] ${risk.badge}`}>{risk.label}</Badge>
                                  {online && <span className='text-[10px] text-emerald-600 dark:text-emerald-400'>آنلاین</span>}
                                </div>
                                <p className='mt-0.5 truncate text-[11px]'><span aria-hidden='true'>{flagEmoji(s.geo_country_code)} </span>{place || 'موقعیت نامشخص'}{s.geo_asname ? <span className='text-muted-foreground'> · {s.geo_asname}</span> : null}</p>
                                {s.utm_term && <p className='text-primary mt-0.5 truncate text-[11px]' title={s.utm_term}><span className='text-muted-foreground'>کلمهٔ کلیدی: </span>{s.utm_term}</p>}
                                {(s.visitor_ips > 1 || s.visitor_sessions > 1) && <p className={`mt-0.5 text-[10px] ${s.risk_reasons.includes('visitor_ip_rotation') ? 'text-rose-600 dark:text-rose-400' : 'text-muted-foreground'}`}>این کاربر: {fa.format(s.visitor_sessions)} نشست · {fa.format(s.visitor_ips)} آی‌پی · {fa.format(s.visitor_events)} رویداد</p>}
                              </div>
                            </div>

                            <div className='flex flex-wrap items-center gap-1.5 lg:w-60 lg:shrink-0'>
                              <Badge variant='secondary' className='text-[10px]'>{ua.browser}</Badge>
                              <Badge variant='secondary' className='text-[10px]'>{ua.os}</Badge>
                              {s.device && <Badge variant='outline' className='text-[10px]'>{s.device}</Badge>}
                              {s.geo_hosting && <Badge variant='outline' className='border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300 text-[10px]'>دیتاسنتر</Badge>}
                              {s.geo_tz_mismatch && <Badge variant='outline' className='border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300 text-[10px]'>ناهماهنگی زمان/کشور</Badge>}
                              {s.risk_reasons.includes('visitor_ip_rotation') && <Badge variant='outline' className='border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300 text-[10px]'>چرخش IP مشکوک ({fa.format(s.visitor_ips)})</Badge>}
                              {s.risk_reasons.includes('visitor_multi_ip') && <Badge variant='outline' className='border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300 text-[10px]'>چند IP مشکوک</Badge>}
                              {s.risk_reasons.includes('visitor_repeat_clicks') && <Badge variant='outline' className='border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300 text-[10px]' title='تعداد شناسه‌های یکتای GCLID/GBRAID/WBRAID؛ کلیک داخل سایت نیست'>ورودی تبلیغاتی یکتا: {fa.format(s.visitor_click_ids)} در {fa.format(s.visitor_sessions)} نشست</Badge>}
                              {s.geo_mobile && <Badge variant='outline' className='text-[10px]'>موبایل</Badge>}
                            </div>

                            <div className='grid grid-cols-4 gap-2 text-center lg:w-72 lg:shrink-0'>
                              <div><p className='text-sm font-bold tabular-nums'>{fa.format(s.events)}</p><p className='text-muted-foreground text-[10px]'>رویداد</p></div>
                              <div><p className='text-sm font-bold tabular-nums'>{fa.format(s.distinct_pages)}</p><p className='text-muted-foreground text-[10px]'>صفحه</p></div>
                              <div><p className='text-sm font-bold tabular-nums'>{fa.format(s.tel_clicks)}</p><p className='text-muted-foreground text-[10px]'>تماس</p></div>
                              <div><p className='text-[11px] font-bold leading-4'>{durationLabel(s.first_seen, s.last_seen)}</p><p className='text-muted-foreground text-[10px]'>مدت</p></div>
                            </div>

                            <div className='min-w-0 lg:w-52 lg:shrink-0'>
                              <p className='truncate font-mono text-[11px]' dir='ltr' title={s.last_page ?? ''}>{s.last_page ?? '—'}</p>
                              <p className='text-muted-foreground mt-0.5 text-[10px]'>{time.format(new Date(s.last_seen))}</p>
                              {s.risk_reasons.length > 0 && <p className='mt-0.5 truncate text-[10px] text-amber-600 dark:text-amber-400' title={s.risk_reasons.map((r) => RISK_FA[r] ?? r).join('، ')}>{RISK_FA[s.risk_reasons[0]] ?? s.risk_reasons[0]}</p>}
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : <EmptyState title='هنوز بازدیدکننده‌ای در این بازه نیست' description='به‌محض ورود اولین نفر، اینجا به‌صورت زنده نمایش داده می‌شود.' />}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value='pages' className='space-y-4'>
            <div className='grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(300px,1fr)]'>
              <Card className='border-border/70 min-w-0'>
                <CardHeader>
                  <CardTitle>رفتار تجمیعی در هر صفحه</CardTitle>
                  <CardDescription className='mt-1'>تعداد نشست‌ها، کلیک‌ها، عمق اسکرول و زمان حضور در هر مسیر؛ بدون نمایش شناسه یا اطلاعات فرم کاربر.</CardDescription>
                </CardHeader>
                <CardContent className='p-0'>
                  <div className='hidden overflow-x-auto md:block'>
                    <table className='w-full min-w-[720px] text-sm'>
                      <thead className='bg-muted/40 text-muted-foreground border-y text-xs'>
                        <tr>{['صفحه', 'نشست / بازدید', 'کلیک', 'عمق اسکرول', 'میانگین حضور'].map((heading) => <th key={heading} className='px-4 py-3 text-start font-medium'>{heading}</th>)}</tr>
                      </thead>
                      <tbody>
                        {pageReport.pages.map((row) => (
                          <tr key={row.page_path} className='hover:bg-muted/40 border-b align-top transition-colors last:border-0'>
                            <td className='max-w-72 px-4 py-3'><p className='truncate font-mono text-xs' dir='ltr' title={row.page_path}>{row.page_path}</p></td>
                            <td className='px-4 py-3 tabular-nums'>{fa.format(row.sessions)}<span className='text-muted-foreground text-[10px]'> / {fa.format(row.page_views)}</span></td>
                            <td className='px-4 py-3 tabular-nums'>{fa.format(row.clicks)}</td>
                            <td className='px-4 py-3 text-[11px] leading-5 tabular-nums'>۵۰٪: {fa.format(row.scroll_50_sessions)} · ۷۵٪: {fa.format(row.scroll_75_sessions)} · ۹۰٪: {fa.format(row.scroll_90_sessions)}</td>
                            <td className='px-4 py-3 whitespace-nowrap tabular-nums'>{row.avg_dwell_ms == null ? '—' : `${fa.format(Math.round(row.avg_dwell_ms / 1000))} ثانیه`}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className='space-y-2 p-4 md:hidden'>
                    {pageReport.pages.map((row) => (
                      <div key={row.page_path} className='rounded-xl border p-3'>
                        <p className='truncate font-mono text-xs font-semibold' dir='ltr' title={row.page_path}>{row.page_path}</p>
                        <div className='mt-3 grid grid-cols-2 gap-2 text-xs'>
                          <p><span className='text-muted-foreground'>نشست:</span> {fa.format(row.sessions)}</p>
                          <p><span className='text-muted-foreground'>بازدید:</span> {fa.format(row.page_views)}</p>
                          <p><span className='text-muted-foreground'>کلیک:</span> {fa.format(row.clicks)}</p>
                          <p><span className='text-muted-foreground'>حضور:</span> {row.avg_dwell_ms == null ? '—' : `${fa.format(Math.round(row.avg_dwell_ms / 1000))} ثانیه`}</p>
                          <p><span className='text-muted-foreground'>اسکرول ۷۵٪:</span> {fa.format(row.scroll_75_sessions)}</p>
                        </div>
                      </div>
                    ))}
                  </div>

                  {!pageReport.pages.length && <EmptyState title='هنوز دادهٔ صفحه‌ای ثبت نشده' description='پس از ورود کاربران، رفتار تجمیعی هر صفحه در این بخش ظاهر می‌شود.' />}
                </CardContent>
              </Card>

              <div className='space-y-4'>
                <Card className='border-border/70'>
                  <CardHeader>
                    <CardTitle>صفحات ورود</CardTitle>
                    <CardDescription className='mt-1'>اولین صفحه‌ای که هر نشست از آن شروع شده است.</CardDescription>
                  </CardHeader>
                  <CardContent className='space-y-2'>
                    {pageReport.entries.slice(0, 12).map((entry) => (
                      <div key={entry.page_path} className='flex items-center justify-between gap-3 rounded-lg border px-3 py-2'>
                        <span className='min-w-0 truncate font-mono text-[11px]' dir='ltr' title={entry.page_path}>{entry.page_path}</span>
                        <Badge variant='secondary' className='shrink-0'>{fa.format(entry.sessions)} نشست</Badge>
                      </div>
                    ))}
                    {!pageReport.entries.length && <p className='text-muted-foreground py-4 text-center text-xs'>داده‌ای موجود نیست.</p>}
                  </CardContent>
                </Card>

                <Card className='border-border/70'>
                  <CardHeader>
                    <CardTitle>اقدام‌های پرتکرار</CardTitle>
                    <CardDescription className='mt-1'>دکمه‌ها و انتخاب‌های معنی‌دار کاربران، بدون ذخیرهٔ متن ورودی.</CardDescription>
                  </CardHeader>
                  <CardContent className='space-y-2'>
                    {pageReport.actions.slice(0, 15).map((item) => (
                      <div key={`${item.page_path}:${item.action}`} className='rounded-lg border px-3 py-2'>
                        <div className='flex items-center justify-between gap-3'>
                          <span className='truncate text-xs font-medium' dir='ltr' title={item.action}>{item.action}</span>
                          <Badge variant='outline' className='shrink-0'>{fa.format(item.count)}</Badge>
                        </div>
                        <p className='text-muted-foreground mt-1 truncate font-mono text-[10px]' dir='ltr' title={item.page_path}>{item.page_path}</p>
                      </div>
                    ))}
                    {!pageReport.actions.length && <p className='text-muted-foreground py-4 text-center text-xs'>پس از انتشار برچسب‌های معنایی، این بخش پر می‌شود.</p>}
                  </CardContent>
                </Card>
              </div>
            </div>
          </TabsContent>

          <TabsContent value='keywords' className='space-y-4'>
            {(summary?.totals.google_ads_sessions ?? 0) > 0 && !keywords.length && (
              <div className='flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-800 dark:text-amber-200'>
                <IconAlertTriangle className='mt-0.5 size-5 shrink-0' />
                <p className='leading-6'>ورودی Google Ads با GCLID/GBRAID ثبت شده، اما «کلمهٔ تطبیق‌یافته» همراه URL نیامده است. برای پرشدن این جدول باید ValueTrack <code dir='ltr'>{'{keyword}'}</code> در Final URL suffix یا <code dir='ltr'>utm_term</code> ارسال شود. این فیلد، عبارت خام جست‌وجوی کاربر نیست.</p>
              </div>
            )}
            <Card className='border-border/70'>
              <CardHeader>
                <CardTitle>کلمهٔ تطبیق‌یافتهٔ تبلیغ و نرخ ریسک</CardTitle>
                <CardDescription className='mt-1'>فقط keyword واقعیِ ارسال‌شده با ValueTrack/UTM نمایش داده می‌شود؛ سیستم از روی GCLID کلمه جعل یا حدس نمی‌زند. «نرخ ریسک» سهم رویدادهای IP پرخطر است.</CardDescription>
              </CardHeader>
              <CardContent className='p-0'>
                <div className='overflow-x-auto'>
                  <table className='w-full min-w-[820px] text-sm'>
                    <thead className='bg-muted/40 text-muted-foreground border-y text-xs'>
                      <tr>{['کلمه کلیدی', 'رویداد / نشست', 'کلیک تماس', 'IP یکتا', 'IP مشکوک', 'کاربر مشکوک', 'نرخ تقلب', 'آخرین'].map((h) => <th key={h} className='px-4 py-3 text-start font-medium'>{h}</th>)}</tr>
                    </thead>
                    <tbody>
                      {keywords.map((k) => {
                        const tone = k.fraud_rate >= 40 ? 'text-rose-600 dark:text-rose-400' : k.fraud_rate >= 15 ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400';
                        const bar = k.fraud_rate >= 40 ? 'bg-rose-500' : k.fraud_rate >= 15 ? 'bg-amber-500' : 'bg-emerald-500';
                        return (
                          <tr key={k.keyword} className='hover:bg-muted/40 border-b transition-colors last:border-0'>
                            <td className='max-w-72 px-4 py-3'><p className='truncate font-medium' title={k.keyword}>{k.keyword}</p></td>
                            <td className='px-4 py-3 tabular-nums'>{fa.format(k.events)}<span className='text-muted-foreground text-[10px]'> / {fa.format(k.sessions)}</span></td>
                            <td className='px-4 py-3 tabular-nums'>{fa.format(k.tel_clicks)}</td>
                            <td className='px-4 py-3 tabular-nums'>{fa.format(k.unique_ips)}</td>
                            <td className='px-4 py-3 tabular-nums'>{fa.format(k.suspicious_ips)}{k.high_risk_ips ? <span className='text-rose-600 dark:text-rose-400'> ({fa.format(k.high_risk_ips)} پرخطر)</span> : null}</td>
                            <td className='px-4 py-3 tabular-nums'>{k.bot_visitors ? <span className='text-rose-600 dark:text-rose-400 font-semibold'>{fa.format(k.bot_visitors)}</span> : fa.format(0)}<span className='text-muted-foreground text-[10px]'> / {fa.format(k.unique_visitors)}</span></td>
                            <td className='px-4 py-3'>
                              <div className='flex items-center gap-2'>
                                <div className='bg-muted h-1.5 w-16 shrink-0 overflow-hidden rounded-full'><div className={`h-full rounded-full ${bar}`} style={{ width: `${Math.min(100, k.fraud_rate)}%` }} /></div>
                                <span className={`text-xs font-semibold tabular-nums ${tone}`}>{fa.format(k.fraud_rate)}٪</span>
                              </div>
                            </td>
                            <td className='text-muted-foreground px-4 py-3 whitespace-nowrap text-[10px]'>{time.format(new Date(k.last_seen))}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {!keywords.length && <EmptyState title='هنوز کلمهٔ قابل استنادی نرسیده' description='GCLID به‌تنهایی نام کلمه را در URL نمی‌آورد؛ ValueTrack {keyword} یا utm_term باید همراه کلیک ارسال شود.' />}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value='overview' className='space-y-5'>
            <div className='grid gap-5 xl:grid-cols-[1.7fr_1fr]'>
              <Card className='border-border/70 min-w-0'>
                <CardHeader className='pb-2'>
                  <div className='flex flex-col justify-between gap-2 sm:flex-row sm:items-start'>
                    <div><CardTitle>روند فعالیت</CardTitle><CardDescription className='mt-1'>مقایسه ورود، کل رویدادها و کلیک تماس به وقت تهران</CardDescription></div>
                    <div className='flex flex-wrap gap-3 text-[11px]'>
                      <span className='flex items-center gap-1.5'><span className='size-2 rounded-full bg-[var(--chart-1)]' />همه رویدادها</span>
                      <span className='flex items-center gap-1.5'><span className='size-2 rounded-full bg-[var(--chart-2)]' />ورود</span>
                      <span className='flex items-center gap-1.5'><span className='size-2 rounded-full bg-[var(--chart-5)]' />تماس</span>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className='h-72 px-2 pb-3 sm:h-80 sm:px-5'>
                  {chart.length ? (
                    <ResponsiveContainer width='100%' height='100%'>
                      <AreaChart data={chart} margin={{ top: 10, right: 4, bottom: 0, left: 0 }}>
                        <defs><linearGradient id='eventsFillV2' x1='0' y1='0' x2='0' y2='1'><stop offset='5%' stopColor='var(--chart-1)' stopOpacity={0.32}/><stop offset='95%' stopColor='var(--chart-1)' stopOpacity={0.01}/></linearGradient></defs>
                        <CartesianGrid strokeDasharray='3 3' vertical={false} opacity={0.45}/>
                        <XAxis dataKey='label' minTickGap={44} tick={{ fontSize: 10 }} axisLine={false} tickLine={false}/>
                        <YAxis width={30} allowDecimals={false} tick={{ fontSize: 10 }} axisLine={false} tickLine={false}/>
                        <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                        <Area type='monotone' dataKey='events' name='همه رویدادها' stroke='var(--chart-1)' fill='url(#eventsFillV2)' strokeWidth={2}/>
                        <Area type='monotone' dataKey='landings' name='ورود' stroke='var(--chart-2)' fill='transparent' strokeWidth={2}/>
                        <Area type='monotone' dataKey='tel_clicks' name='کلیک تماس' stroke='var(--chart-5)' fill='transparent' strokeWidth={2}/>
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : <EmptyState title='هنوز نموداری شکل نگرفته' description='به محض دریافت اولین ورودی، روند ساعتی در این قسمت نمایش داده می‌شود.' />}
                </CardContent>
              </Card>

              <Card className='border-border/70'>
                <CardHeader><CardTitle>کاربران چه کاری انجام دادند؟</CardTitle><CardDescription>سهم هر نوع رفتار از داده‌های ثبت‌شده</CardDescription></CardHeader>
                <CardContent className='space-y-4'>
                  {serviceEventTypes.slice(0, 8).map((row) => (
                    <div key={row.event_type}>
                      <div className='mb-1.5 flex items-center justify-between gap-3 text-xs'><span>{EVENT_FA[row.event_type] ?? row.event_type}</span><span className='font-medium tabular-nums'>{fa.format(row.count)}</span></div>
                      <div className='bg-muted h-1.5 overflow-hidden rounded-full'><div className='bg-primary h-full rounded-full' style={{ width: `${Math.max(4, (row.count / maxEventCount) * 100)}%` }} /></div>
                    </div>
                  ))}
                  {!serviceEventTypes.length && <EmptyState title='رفتاری ثبت نشده' description='پس از ورود کاربران، نوع رفتار آن‌ها اینجا خلاصه می‌شود.' />}
                </CardContent>
              </Card>
            </div>

            <div className='grid gap-5 xl:grid-cols-[1.15fr_1fr]'>
              <Card className='border-border/70'>
                <CardHeader><CardTitle>کمپین‌ها و شناسه‌های ورودی</CardTitle><CardDescription>برای مقایسه کیفیت ورودی هر کمپین</CardDescription></CardHeader>
                <CardContent className='space-y-2'>
                  {(summary?.campaigns ?? []).slice(0, 8).map((row) => (
                    <div key={row.campaign} className='hover:bg-muted/50 grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 rounded-xl border p-3 text-xs transition-colors'>
                      <div className='min-w-0'><p className='truncate font-mono' dir='ltr'>{row.campaign === '(unknown)' ? 'بدون شناسه کمپین' : (cleanCampaign(row.campaign) ?? row.campaign)}</p>{TEST_CAMPAIGNS.has(row.campaign) && <Badge variant='outline' className='mt-1'>داده تست</Badge>}</div>
                      <div className='text-center'><p className='font-semibold'>{fa.format(row.landings)}</p><p className='text-muted-foreground mt-0.5'>ورود</p></div>
                      <div className='text-center'><p className='font-semibold'>{fa.format(row.tel_clicks)}</p><p className='text-muted-foreground mt-0.5'>تماس</p></div>
                    </div>
                  ))}
                  {!summary?.campaigns.length && <EmptyState title='کمپینی شناسایی نشده' description='وقتی UTM یا campaign ID در آدرس ورودی باشد، نتیجه اینجا دیده می‌شود.' />}
                </CardContent>
              </Card>

              <Card className='border-border/70'>
                <CardHeader><CardTitle>این سیستم چطور کار می‌کند؟</CardTitle><CardDescription>مسیر داده از ورود کاربر تا نمایش در داشبورد</CardDescription></CardHeader>
                <CardContent className='space-y-4'>
                  {[
                    ['۱', 'کاربر وارد سایت می‌شود', 'تگ سایت ورود و شناسه تبلیغ را ثبت می‌کند.'],
                    ['۲', 'IP در سرور تشخیص داده می‌شود', 'IP از هدر شبکه گرفته می‌شود، نه از ورودی قابل‌تغییر مرورگر.'],
                    ['۳', 'رفتار کاربر ثبت می‌شود', 'تماس، واتساپ، فرم، اسکرول و مدت حضور به‌صورت رویداد ذخیره می‌شوند.'],
                    ['۴', 'الگوهای مشکوک امتیاز می‌گیرند', 'تکرار زیاد یا جهش فعالیت برای بررسی انسانی علامت‌گذاری می‌شود.']
                  ].map(([step, title, body]) => (
                    <div key={step} className='flex gap-3'>
                      <div className='bg-primary/10 text-primary flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-bold'>{step}</div>
                      <div><p className='text-sm font-medium'>{title}</p><p className='text-muted-foreground mt-1 text-xs leading-5'>{body}</p></div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value='ips' className='space-y-4'>
            <Card className='border-border/70'>
              <CardHeader className='gap-4'>
                <div className='flex flex-col justify-between gap-3 lg:flex-row lg:items-start'>
                  <div><CardTitle>بررسی IPها</CardTitle><CardDescription className='mt-1'>موارد پرریسک بالاتر نمایش داده می‌شوند؛ برای جزئیات روی هر ردیف بزنید.</CardDescription></div>
                  <div className='flex w-full gap-2 lg:w-auto'>
                    <div className='relative min-w-0 flex-1 lg:w-80'>
                      <IconSearch className='text-muted-foreground pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2' />
                      <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder='جست‌وجوی IP، صفحه یا مرورگر…' className='h-10 pr-9' aria-label='جست‌وجوی IPها' />
                    </div>
                    <Button size='sm' className='h-10 shrink-0' nativeButton={false} render={<a href={`/api/backend/ads-data/ips.csv?site_id=${siteQuery}&hours=${hours}`} />}><IconDownload />CSV همه IPها</Button>
                  </div>
                </div>
                <div className='flex gap-2 overflow-x-auto pb-1' role='group' aria-label='فیلتر ریسک'>
                  {([
                    ['all', `همه (${fa.format(ips.length)})`],
                    ['high', `ریسک بالا (${fa.format(highRisk.length)})`],
                    ['review', `نیاز بررسی (${fa.format(suspicious.length - highRisk.length)})`],
                    ['normal', 'عادی']
                  ] as [RiskFilter, string][]).map(([value, label]) => (
                    <Button key={value} size='sm' variant={riskFilter === value ? 'default' : 'outline'} className='shrink-0' onClick={() => setRiskFilter(value)}>{label}</Button>
                  ))}
                </div>
              </CardHeader>
              <CardContent className='p-0'>
                <div className='hidden overflow-x-auto md:block'>
                  <table className='w-full min-w-[900px] text-sm'>
                    <thead className='bg-muted/40 text-muted-foreground border-y text-xs'>
                      <tr>{['وضعیت', 'IP', 'فعالیت', 'ورود', 'کلیک تماس', 'آخرین مشاهده', 'آخرین صفحه', ''].map((heading) => <th key={heading} className='px-4 py-3 text-start font-medium'>{heading}</th>)}</tr>
                    </thead>
                    <tbody>
                      {filteredIps.map((row) => {
                        const risk = riskInfo(row.risk_score);
                        return (
                          <tr key={row.ip_hash} className='hover:bg-muted/40 cursor-pointer border-b transition-colors last:border-0' onClick={() => openIp(row)}>
                            <td className='px-4 py-3'><Badge variant='outline' className={risk.badge}><span className={`me-1.5 size-1.5 rounded-full ${risk.dot}`} />{risk.label}</Badge><p className='text-muted-foreground mt-1 text-[10px]'>امتیاز {fa.format(row.risk_score)}</p></td>
                            <td className='px-4 py-3 text-xs'><p className='font-mono' dir='ltr'>{row.ip_address}</p><Badge variant='outline' className={`mt-2 text-[10px] ${confidenceInfo(row.ip_confidence).className}`}>{confidenceInfo(row.ip_confidence).label}</Badge><GeoInfo row={row} /></td>
                            <td className='px-4 py-3'><p className='font-medium'>{fa.format(row.events)} رویداد</p><p className='text-muted-foreground mt-1 text-[10px]'>{fa.format(row.events_5m)} در ۵ دقیقه</p></td>
                            <td className='px-4 py-3 tabular-nums'>{fa.format(row.landings)}</td>
                            <td className='px-4 py-3 tabular-nums'>{fa.format(row.tel_clicks)}</td>
                            <td className='px-4 py-3 whitespace-nowrap text-xs'>{time.format(new Date(row.last_seen))}</td>
                            <td className='max-w-56 truncate px-4 py-3 font-mono text-xs' dir='ltr' title={row.latest_page_path ?? ''}>{row.latest_page_path ?? '—'}</td>
                            <td className='px-4 py-3'><Button size='icon-sm' variant='ghost' aria-label={`مشاهده جزئیات ${row.ip_address}`}><IconEye /></Button></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className='divide-y md:hidden'>
                  {filteredIps.map((row) => {
                    const risk = riskInfo(row.risk_score);
                    return (
                      <button key={row.ip_hash} type='button' className='hover:bg-muted/40 w-full p-4 text-start transition-colors' onClick={() => openIp(row)}>
                        <div className='flex items-start justify-between gap-3'><div><p className='font-mono text-sm' dir='ltr'>{row.ip_address}</p><Badge variant='outline' className={`mt-2 text-[10px] ${confidenceInfo(row.ip_confidence).className}`}>{confidenceInfo(row.ip_confidence).label}</Badge><GeoInfo row={row} /><p className='text-muted-foreground mt-1 text-[11px]'>{time.format(new Date(row.last_seen))}</p></div><Badge variant='outline' className={risk.badge}>{risk.label}</Badge></div>
                        <div className='mt-4 grid grid-cols-3 gap-2 text-center text-xs'><div className='bg-muted/50 rounded-lg p-2'><p className='font-semibold'>{fa.format(row.events)}</p><p className='text-muted-foreground mt-1'>رویداد</p></div><div className='bg-muted/50 rounded-lg p-2'><p className='font-semibold'>{fa.format(row.landings)}</p><p className='text-muted-foreground mt-1'>ورود</p></div><div className='bg-muted/50 rounded-lg p-2'><p className='font-semibold'>{fa.format(row.tel_clicks)}</p><p className='text-muted-foreground mt-1'>تماس</p></div></div>
                        <p className='text-muted-foreground mt-3 truncate font-mono text-[11px]' dir='ltr'>{row.latest_page_path ?? 'بدون مسیر صفحه'}</p>
                      </button>
                    );
                  })}
                </div>
                {!filteredIps.length && <EmptyState title='IP مطابق این فیلتر پیدا نشد' description='فیلتر ریسک یا عبارت جست‌وجو را تغییر دهید؛ ممکن است در بازه زمانی انتخاب‌شده داده‌ای وجود نداشته باشد.' />}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value='logs' className='space-y-4'>
            {ipBlockState.status !== 'ready' && <div role='status' className='flex flex-wrap items-center gap-2 rounded-lg border p-3 text-sm'>
              <span>{ipBlockState.status === 'loading' ? 'در حال دریافت وضعیت بلاک IPها…' : ipBlockState.message}</span>
              {ipBlockState.status !== 'loading' && <Button size='sm' variant='outline' onClick={() => void ipBlockController.load()}>تلاش دوباره</Button>}
            </div>}
            <Card className='border-border/70'>
              <CardHeader className='gap-4'>
                <div className='flex flex-col justify-between gap-3 lg:flex-row lg:items-start'>
                  <div><CardTitle>لاگ کامل همه ورودها و رفتارها</CardTitle><CardDescription className='mt-1'>هر رکورد ذخیره‌شده با IP، شناسه‌ها، کمپین، صفحه، دستگاه و جزئیات فنی؛ جدیدترین رکورد بالا است.</CardDescription></div>
                  <div className='flex w-full flex-col gap-2 xl:w-auto'>
                    <form className='flex min-w-0 gap-2' onSubmit={(event) => { event.preventDefault(); setEventPage(0); setLogQuery(logQueryInput.trim()); }}>
                      <div className='relative min-w-0 flex-1 xl:w-80'>
                      <IconSearch className='text-muted-foreground pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2' />
                        <Input value={logQueryInput} onChange={(event) => setLogQueryInput(event.target.value)} placeholder='IP، GCLID، session، صفحه، کمپین…' className='h-10 pr-9' aria-label='جست‌وجوی کل لاگ‌ها' />
                      </div>
                      <Button type='submit' size='sm' className='h-10'>جست‌وجو</Button>
                    </form>
                    <div className='flex gap-2'>
                    <select value={eventFilter} onChange={(event) => { setEventFilter(event.target.value); setEventPage(0); }} className='border-input bg-background h-10 min-w-0 flex-1 rounded-lg border px-3 text-sm outline-none' aria-label='نوع رویداد'>
                      <option value='all'>همه رفتارها</option>
                      {Object.entries(EVENT_FA).filter(([value]) => isServiceRelevantEvent(value)).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                    <select value={adsFilter} onChange={(event) => { setAdsFilter(event.target.value as typeof adsFilter); setEventPage(0); }} className='border-input bg-background h-10 min-w-0 flex-1 rounded-lg border px-3 text-sm outline-none' aria-label='منبع ورودی (تبلیغات)'>
                      <option value='all'>همه منابع</option>
                      <option value='ads'>فقط تبلیغات</option>
                      <option value='confirmed'>فقط Google Ads قطعی</option>
                      <option value='unattributed'>بدون تبلیغ (عادی)</option>
                    </select>
                      <Button size='sm' className='h-10 shrink-0' nativeButton={false} render={<a href={logCsvUrl} />}><IconDownload />CSV کامل</Button>
                    </div>
                  </div>
                </div>
                <div className='flex flex-wrap items-center justify-between gap-2 rounded-xl border border-sky-500/25 bg-sky-500/[0.06] p-3 text-xs'>
                  <p><span className='font-semibold'>{fa.format(eventTotal)} رویداد خام</span> در بازه «{rangeLabel(hours)}» پیدا شد. heartbeat، scroll و click هرکدام یک رویدادند و به معنی کاربر یا کلیک تبلیغاتی تازه نیستند؛ دکمه «جزئیات کامل» تمام فیلدهای همان رویداد را نشان می‌دهد.</p>
                  {logQuery && <Button size='xs' variant='ghost' onClick={() => { setLogQuery(''); setLogQueryInput(''); setEventPage(0); }}>پاک‌کردن جست‌وجو</Button>}
                </div>
              </CardHeader>
              <CardContent className='p-0'>
                <div className='hidden overflow-x-auto md:block'>
                  <table className='w-full min-w-[1100px] text-sm'>
                    <thead className='bg-muted/60 text-muted-foreground sticky top-0 z-10 border-y text-xs'><tr>{['زمان و رفتار', 'کاربر', 'IP و وضعیت', 'منبع ورود', 'صفحه', 'نشانه مهم', ''].map((heading) => <th key={heading} className='px-4 py-3 text-start font-medium'>{heading}</th>)}</tr></thead>
                    <tbody>{visibleEvents.map((row) => {
                      const user = logUsers.get(logIdentity(row))!;
                      return <tr key={row.id} className={`hover:bg-muted/40 align-top border-b transition-colors last:border-0 ${blockedIps.has(row.ip_address) ? 'bg-destructive/10 hover:bg-destructive/15' : logRowTone(row)}`}>
                      <td className='sticky right-0 z-[1] bg-background/95 px-4 py-3 backdrop-blur'><Badge variant='outline'>{EVENT_FA[row.event_type] ?? row.event_type}</Badge><p className='mt-2 whitespace-nowrap text-xs'>{time.format(new Date(row.received_at))}</p><p className='text-muted-foreground mt-1 font-mono text-[10px]' dir='ltr'>ID: {row.id}</p></td>
                      <td className='max-w-56 px-4 py-3 text-[11px]'><Badge variant='outline' className={blockedIps.has(row.ip_address) ? 'border-destructive/40 bg-destructive/15 text-destructive' : user.color.badge}><span className={`me-1.5 size-2 rounded-full ${blockedIps.has(row.ip_address) ? 'bg-destructive' : user.color.dot}`} />{user.label}</Badge><p className='text-muted-foreground mt-1'>{fa.format(user.count)} رویداد در این صفحه</p><p className='text-muted-foreground mt-2 truncate font-mono' dir='ltr'>session: {row.session_id ?? '—'}</p></td>
                      <td className='px-4 py-3 text-xs'><p className='font-mono font-semibold' dir='ltr'>{row.ip_address}</p><Badge variant='outline' className={`mt-2 text-[10px] ${confidenceInfo(row.ip_confidence).className}`}>{confidenceInfo(row.ip_confidence).label}</Badge></td>
                      <td className='max-w-56 px-4 py-3 text-xs'><Badge variant='outline' className={eventAdsInfo(row).className}>{eventAdsInfo(row).label}</Badge><p className='text-muted-foreground mt-2 truncate font-mono' dir='ltr'>{row.utm_source || row.referrer || 'ورود مستقیم'}</p></td>
                      <td className='max-w-72 px-4 py-3 font-mono text-[11px]' dir='ltr'><p className='break-all'>{row.page_path || row.landing_path || '—'}</p></td>
                      <td className='max-w-64 px-4 py-3 text-[11px]'>{row.gclid || row.gbraid || row.wbraid ? <><p className='font-medium'>شناسه تبلیغ ثبت شده</p><p className='text-muted-foreground mt-1 truncate font-mono' dir='ltr'>{row.gclid || row.gbraid || row.wbraid}</p></> : row.utm_campaign || row.campaign_id ? <><p className='font-medium'>کمپین ثبت شده</p><p className='text-muted-foreground mt-1 truncate font-mono' dir='ltr'>{row.utm_campaign || row.campaign_id}</p></> : <span className='text-muted-foreground'>بدون دادهٔ تبلیغاتی</span>}</td>
                      <td className='px-4 py-3'><div className='flex flex-wrap items-center gap-2'>{ipBlockControl(row.ip_address)}<Button size='sm' variant='outline' onClick={() => setSelectedEvent(row)}><IconEye />جزئیات کامل</Button></div></td>
                    </tr>})}</tbody>
                  </table>
                </div>
                <div className='divide-y md:hidden'>
                  {visibleEvents.map((row) => {
                    const user = logUsers.get(logIdentity(row))!;
                    return <div key={row.id} className={`hover:bg-muted/40 w-full p-4 text-start ${blockedIps.has(row.ip_address) ? 'bg-destructive/10' : logRowTone(row)}`}><div className='flex items-center justify-between gap-3'><div className='flex flex-wrap gap-1'><Badge variant='outline' className={blockedIps.has(row.ip_address) ? 'border-destructive/40 bg-destructive/15 text-destructive' : user.color.badge}><span className={`me-1.5 size-2 rounded-full ${blockedIps.has(row.ip_address) ? 'bg-destructive' : user.color.dot}`} />{user.label}</Badge><Badge variant='outline'>{EVENT_FA[row.event_type] ?? row.event_type}</Badge><Badge variant='outline' className={eventAdsInfo(row).className}>{eventAdsInfo(row).label}</Badge></div><span className='text-muted-foreground text-[11px]'>{time.format(new Date(row.received_at))}</span></div><p className='mt-3 font-mono text-sm font-semibold' dir='ltr'>{row.ip_address}</p><p className='text-muted-foreground mt-1 text-[11px]'>{fa.format(user.count)} رویداد از همین کاربر در این صفحه</p><Badge variant='outline' className={`mt-2 text-[10px] ${confidenceInfo(row.ip_confidence).className}`}>{confidenceInfo(row.ip_confidence).label}</Badge><div className='text-muted-foreground mt-2 space-y-1 font-mono text-[11px]' dir='ltr'><p className='truncate'>page: {row.page_path ?? '—'}</p><p className='truncate'>campaign: {row.utm_campaign ?? row.campaign_id ?? '—'}</p><p className='truncate'>gclid: {row.gclid ?? '—'}</p><p className='truncate'>session: {row.session_id ?? '—'}</p></div><div className='mt-3 flex flex-wrap items-center gap-2'>{ipBlockControl(row.ip_address)}<Button size='sm' variant='outline' onClick={() => setSelectedEvent(row)}>جزئیات کامل <IconChevronLeft className='size-4' /></Button></div></div>})}
                </div>
                {!visibleEvents.length && <EmptyState title='لاگی مطابق این فیلتر نیست' description='بازه زمانی را روی «همه داده‌ها» بگذارید یا جست‌وجو و نوع رفتار را تغییر دهید.' />}
                <div className='flex flex-col items-center justify-between gap-3 border-t p-4 sm:flex-row'>
                  <p className='text-muted-foreground text-xs'>نمایش {fa.format(eventStart)} تا {fa.format(eventEnd)} از {fa.format(eventTotal)} رکورد · صفحه {fa.format(eventPage + 1)} از {fa.format(eventPageCount)}</p>
                  <div className='flex gap-2'><Button size='sm' variant='outline' disabled={eventPage === 0} onClick={() => setEventPage((page) => Math.max(0, page - 1))}>صفحه قبل</Button><Button size='sm' variant='outline' disabled={eventPage + 1 >= eventPageCount} onClick={() => setEventPage((page) => page + 1)}>صفحه بعد</Button></div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>

      <Sheet open={Boolean(selectedIp)} onOpenChange={(open) => { if (!open) setSelectedIp(null); }}>
        <SheetContent side='left' className='w-full overflow-y-auto p-0 sm:max-w-xl' dir='rtl'>
          {selectedIp && (
            <>
              <SheetHeader className='border-b p-5 pe-14'>
                <div className='mb-2 flex flex-wrap items-center gap-2'><Badge variant='outline' className={confidenceInfo(selectedIp.ip_confidence).className}>{confidenceInfo(selectedIp.ip_confidence).label}</Badge><Badge variant='outline' className={riskInfo(selectedIp.risk_score).badge}>{riskInfo(selectedIp.risk_score).label}</Badge><Badge variant='secondary'>امتیاز {fa.format(selectedIp.risk_score)} از ۱۰۰</Badge></div>
                <SheetTitle className='font-mono text-lg' dir='ltr'>{selectedIp.ip_address}</SheetTitle>
                <SheetDescription>جزئیات رفتار ثبت‌شده برای این IP در بازه انتخاب‌شده</SheetDescription>
              </SheetHeader>

              <div className='space-y-5 p-5'>
                <Button size='sm' variant='outline' onClick={() => void copyIp()}>{copiedIp ? <IconCheck /> : <IconCopy />}{copiedIp ? 'کپی شد' : 'کپی IP'}</Button>
                  {ipBlockControl(selectedIp.ip_address)}

                <section>
                  <h3 className='mb-3 text-sm font-semibold'>خلاصه فعالیت</h3>
                  <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
                    {[
                      ['رویداد', selectedIp.events],
                      ['ورود', selectedIp.landings],
                      ['تماس', selectedIp.tel_clicks],
                      ['نشست', selectedIp.sessions]
                    ].map(([label, value]) => <div key={String(label)} className='bg-muted/50 rounded-xl p-3 text-center'><p className='text-lg font-bold'>{fa.format(Number(value))}</p><p className='text-muted-foreground mt-1 text-[11px]'>{label}</p></div>)}
                  </div>
                </section>

                <section className='rounded-xl border p-4'>
                  <h3 className='text-sm font-semibold'>چرا این امتیاز را گرفته؟</h3>
                  {selectedIp.risk_reasons.length ? <ul className='mt-3 space-y-2'>{selectedIp.risk_reasons.map((reason) => <li key={reason} className='flex items-start gap-2 text-xs leading-5'><span className='mt-1.5 size-1.5 shrink-0 rounded-full bg-amber-500' />{RISK_FA[reason] ?? reason}</li>)}</ul> : <p className='text-muted-foreground mt-2 text-xs leading-5'>الگوی غیرعادی مشخصی برای این IP دیده نشده است.</p>}
                  <p className='text-muted-foreground mt-3 border-t pt-3 text-[11px] leading-5'>این تشخیص احتمالی است. برای تصمیم‌گیری، زمان رویدادها، کمپین و کلیک‌های تماس را کنار هم بررسی کنید.</p>
                </section>

                <section className='rounded-xl border p-4'>
                  <h3 className='text-sm font-semibold'>موقعیت جغرافیایی و شبکه</h3>
                  <GeoInfo row={selectedIp} />
                  {selectedIp.geo_asn && <p className='text-muted-foreground mt-2 font-mono text-[11px]' dir='ltr'>{selectedIp.geo_asn}</p>}
                  <p className='text-muted-foreground mt-3 border-t pt-3 text-[11px] leading-5'>منبع: پایگاه‌دادهٔ آفلاین DB-IP (تخمینی). برچسب «دیتاسنتر» یا «پروکسی/VPN» نشانهٔ احتمالی ترافیک غیرواقعی است؛ ترافیک واقعیِ کاربر معمولاً از اپراتور خانگی یا موبایل می‌آید.</p>
                </section>

                <section className='space-y-3'>
                  <h3 className='text-sm font-semibold'>اطلاعات فنی قابل استفاده</h3>
                  {[
                    ['اولین مشاهده', time.format(new Date(selectedIp.first_seen))],
                    ['آخرین مشاهده', time.format(new Date(selectedIp.last_seen))],
                    ['فعالیت ۵ دقیقه اخیر', `${fa.format(selectedIp.events_5m)} رویداد`],
                    ['GCLID یکتا', fa.format(selectedIp.gclids)],
                    ['آخرین صفحه', selectedIp.latest_page_path ?? '—'],
                    ['منبع IP', selectedIp.ip_source ?? '—'],
                    ['اعتبار IP', confidenceInfo(selectedIp.ip_confidence).label],
                    ['IP لبه CDN', selectedIp.proxy_ip ?? '—'],
                    ['نسخه تشخیص IP', selectedIp.ip_resolution_version]
                  ].map(([label, value]) => <div key={label} className='grid grid-cols-[130px_minmax(0,1fr)] gap-3 border-b pb-2 text-xs last:border-0'><span className='text-muted-foreground'>{label}</span><span className='min-w-0 break-words' dir={label === 'آخرین صفحه' ? 'ltr' : undefined}>{value}</span></div>)}
                </section>

                <section>
                  <h3 className='mb-3 text-sm font-semibold'>آخرین رفتارهای همین IP</h3>
                  <div className='space-y-2'>
                    {selectedEvents.map((row) => <div key={row.id} className='flex items-start gap-3 rounded-xl border p-3'><span className='mt-1.5 size-2 shrink-0 rounded-full bg-primary' /><div className='min-w-0 flex-1'><div className='flex justify-between gap-3'><p className='text-xs font-medium'>{EVENT_FA[row.event_type] ?? row.event_type}</p><span className='text-muted-foreground shrink-0 text-[10px]'>{time.format(new Date(row.received_at))}</span></div><p className='text-muted-foreground mt-1 truncate font-mono text-[10px]' dir='ltr'>{row.page_path ?? '—'}</p></div></div>)}
                    {!selectedEvents.length && <p className='text-muted-foreground rounded-xl border border-dashed p-5 text-center text-xs'>در فهرست رویدادهای اخیر، جزئیاتی برای این IP نیست.</p>}
                  </div>
                </section>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>

      <Sheet open={Boolean(selectedEvent)} onOpenChange={(open) => { if (!open) setSelectedEvent(null); }}>
        <SheetContent side='left' className='w-full overflow-y-auto p-0 sm:max-w-2xl' dir='rtl'>
          {selectedEvent && (
            <>
              <SheetHeader className='border-b p-5 pe-14'>
                <div className='mb-2 flex flex-wrap items-center gap-2'><Badge>{EVENT_FA[selectedEvent.event_type] ?? selectedEvent.event_type}</Badge><Badge variant='outline'>رکورد #{fa.format(selectedEvent.id)}</Badge></div>
                <SheetTitle>تمام فیلدهای این لاگ</SheetTitle>
                <SheetDescription>{time.format(new Date(selectedEvent.received_at))} · <span className='font-mono' dir='ltr'>{selectedEvent.ip_address}</span></SheetDescription>
              </SheetHeader>
              <div className='space-y-5 p-5'>
                {[
                  ['شناسه رکورد', selectedEvent.id],
                  ['Event UUID', selectedEvent.event_uuid],
                  ['نوع رویداد', `${EVENT_FA[selectedEvent.event_type] ?? selectedEvent.event_type} (${selectedEvent.event_type})`],
                  ['زمان دریافت سرور', selectedEvent.received_at],
                  ['زمان مرورگر', selectedEvent.occurred_at_client],
                  ['IP', selectedEvent.ip_address],
                  ['IP Prefix', selectedEvent.ip_prefix],
                  ['منبع IP', selectedEvent.ip_source],
                  ['اعتبار IP', confidenceInfo(selectedEvent.ip_confidence).label],
                  ['IP لبه CDN', selectedEvent.proxy_ip],
                  ['نسخه تشخیص IP', selectedEvent.ip_resolution_version],
                  ['انتساب تبلیغ', adsInfo(selectedEvent.ads_attribution).label],
                  ['Visitor ID', selectedEvent.visitor_id],
                  ['Session ID', selectedEvent.session_id],
                  ['GCLID', selectedEvent.gclid],
                  ['GBRAID', selectedEvent.gbraid],
                  ['WBRAID', selectedEvent.wbraid],
                  ['Campaign ID', selectedEvent.campaign_id],
                  ['Ad Group ID', selectedEvent.ad_group_id],
                  ['Creative ID', selectedEvent.creative_id],
                  ['Keyword', selectedEvent.keyword],
                  ['Match Type', selectedEvent.match_type],
                  ['Device', selectedEvent.device],
                  ['Network', selectedEvent.network],
                  ['UTM Source', selectedEvent.utm_source],
                  ['UTM Medium', selectedEvent.utm_medium],
                  ['UTM Campaign', selectedEvent.utm_campaign],
                  ['UTM Term', selectedEvent.utm_term],
                  ['UTM Content', selectedEvent.utm_content],
                  ['Landing Path', selectedEvent.landing_path],
                  ['Page Path', selectedEvent.page_path],
                  ['Referrer', selectedEvent.referrer],
                  ['Browser Language', selectedEvent.browser_language],
                  ['Browser Timezone', selectedEvent.browser_timezone],
                  ['Screen Size', selectedEvent.screen_size],
                  ['User Agent', selectedEvent.user_agent]
                ].map(([label, value]) => (
                  <div key={String(label)} className='grid gap-1 border-b pb-3 text-xs sm:grid-cols-[150px_minmax(0,1fr)] sm:gap-4'>
                    <span className='text-muted-foreground'>{label}</span>
                    <span className='min-w-0 break-all font-mono text-[11px]' dir='ltr'>{value === null || value === '' ? '—' : String(value)}</span>
                  </div>
                ))}
                <section>
                  <h3 className='mb-2 text-sm font-semibold'>Metadata کامل</h3>
                  <pre className='bg-muted/60 max-h-80 overflow-auto rounded-xl p-4 text-[11px] leading-5' dir='ltr'>{JSON.stringify(selectedEvent.metadata ?? {}, null, 2)}</pre>
                </section>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>

      <Sheet open={Boolean(selectedSession)} onOpenChange={(open) => { if (!open) setSelectedSession(null); }}>
        <SheetContent side='left' className='w-full overflow-y-auto p-0 sm:max-w-xl' dir='rtl'>
          {selectedSession && (
            <>
              <SheetHeader className='border-b p-5 pe-14'>
                <div className='mb-2 flex flex-wrap items-center gap-2'>
                  <Badge variant='outline' className={riskInfo(selectedSession.risk_score).badge}>{riskInfo(selectedSession.risk_score).label}</Badge>
                  {sessionIsOnline(selectedSession.last_seen) && <Badge className='border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'><span className='me-1 size-1.5 animate-pulse rounded-full bg-emerald-500' />آنلاین</Badge>}
                  <Badge variant='outline' className={adsInfo(selectedSession.ads_attribution).className}>{adsInfo(selectedSession.ads_attribution).label}</Badge>
                </div>
                <SheetTitle className='font-mono text-lg' dir='ltr'>{selectedSession.ip_address}</SheetTitle>
                <SheetDescription>سفر کامل این بازدیدکننده در سایت</SheetDescription>
              </SheetHeader>

              <div className='space-y-5 p-5'>
                <GeoInfo row={selectedSession} />

                <section className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
                  {([['رویداد', fa.format(selectedSession.events)], ['صفحه', fa.format(selectedSession.distinct_pages)], ['کلیک تماس', fa.format(selectedSession.tel_clicks)], ['مدت حضور', durationLabel(selectedSession.first_seen, selectedSession.last_seen)]] as [string, string][]).map(([label, value]) => (
                    <div key={label} className='bg-muted/50 rounded-xl p-3 text-center'><p className='text-base font-bold'>{value}</p><p className='text-muted-foreground mt-1 text-[11px]'>{label}</p></div>
                  ))}
                </section>

                {selectedSession.risk_reasons.length > 0 && (
                  <section className='rounded-xl border border-amber-500/30 bg-amber-500/[0.05] p-4'>
                    <h3 className='text-sm font-semibold'>چرا این بازدیدکننده مشکوک است؟</h3>
                    <ul className='mt-2 space-y-1.5'>{selectedSession.risk_reasons.map((reason) => <li key={reason} className='flex items-start gap-2 text-xs leading-5'><span className='mt-1.5 size-1.5 shrink-0 rounded-full bg-amber-500' />{RISK_FA[reason] ?? reason}</li>)}</ul>
                  </section>
                )}

                <section className='space-y-2 text-xs'>
                  {([['نوع رفتار', `${fa.format(selectedSession.page_views)} صفحه · ${fa.format(selectedSession.scrolls)} اسکرول · ${fa.format(selectedSession.clicks)} کلیک · ${fa.format(selectedSession.section_views)} بخش دیده‌شده · ${fa.format(selectedSession.tel_clicks)} کلیک تماس`], ['مرورگر', `${parseUserAgent(selectedSession.user_agent).browser} · ${parseUserAgent(selectedSession.user_agent).os}`], ['دستگاه', selectedSession.device], ['زبان مرورگر', selectedSession.browser_language], ['منطقهٔ زمانی', selectedSession.browser_timezone ? `${selectedSession.browser_timezone}${selectedSession.geo_tz_mismatch ? '  ⚠ ناهماهنگ با کشور IP' : ''}` : null], ['اندازهٔ نمایشگر', selectedSession.screen_size], ['ردپای این کاربر (visitor_id)', `${fa.format(selectedSession.visitor_sessions)} نشست · ${fa.format(selectedSession.visitor_ips)} شبکه · ${fa.format(selectedSession.visitor_landings)} ورود · ${fa.format(selectedSession.visitor_events)} رویداد`], ['آگهی (creative)', selectedSession.utm_content], ['کمپین', cleanCampaign(selectedSession.utm_campaign) ?? selectedSession.campaign_id], ['شناسه نشست', selectedSession.session_id], ['شناسه بازدیدکننده', selectedSession.visitor_id], ['GCLID', selectedSession.gclid], ['صفحهٔ ورود', selectedSession.landing_path], ['ارجاع‌دهنده', selectedSession.referrer], ['مرورگر و سیستم‌عامل', selectedSession.user_agent]] as [string, string | null][]).map(([label, value]) => (
                    <div key={label} className='grid grid-cols-[110px_minmax(0,1fr)] gap-2 border-b pb-2 last:border-0'><span className='text-muted-foreground'>{label}</span><span className='min-w-0 break-all font-mono text-[11px]' dir='ltr'>{value || '—'}</span></div>
                  ))}
                </section>

                <section className='rounded-xl border p-4'>
                  <h3 className='text-sm font-semibold'>پوشش بخش‌های صفحه</h3>
                  <p className='text-muted-foreground mt-1 text-[11px] leading-5'>بر اساس دیده‌شدن حداقل ۵۰٪ هر بخش؛ بدون ثبت متن صفحه یا ورودی فرم.</p>
                  <p className='mt-4 text-xs font-medium text-emerald-700 dark:text-emerald-300'>دیده‌شده</p>
                  <div className='mt-2 flex flex-wrap gap-1.5'>
                    {sessionSectionCoverage.seen.map((section) => <Badge key={section} variant='outline' className='max-w-full truncate text-[10px]'>{section}</Badge>)}
                    {!sessionSectionCoverage.seen.length && <span className='text-muted-foreground text-[11px]'>هنوز بخشی ثبت نشده است.</span>}
                  </div>
                  <p className='mt-4 text-xs font-medium text-amber-700 dark:text-amber-300'>دیده‌نشده هنگام خروج</p>
                  <div className='mt-2 flex flex-wrap gap-1.5'>
                    {sessionSectionCoverage.unseen.map((section) => <Badge key={section} variant='outline' className='max-w-full truncate border-amber-500/30 text-[10px]'>{section}</Badge>)}
                    {!sessionSectionCoverage.unseen.length && <span className='text-muted-foreground text-[11px]'>بخش جامانده‌ای در دادهٔ فعلی ثبت نشده است.</span>}
                  </div>
                </section>

                <section>
                  <h3 className='mb-3 text-sm font-semibold'>سفر کاربر (به‌ترتیب زمان)</h3>
                  {sessionEventsLoading ? (
                    <p className='text-muted-foreground text-xs'>در حال بارگذاری…</p>
                  ) : sessionEvents.length ? (
                    <div className='relative space-y-3 pe-2 before:absolute before:top-2 before:bottom-2 before:right-[5px] before:w-px before:bg-border'>
                      {[...sessionEvents].filter((row) => isServiceRelevantEvent(row.event_type)).reverse().map((row) => (
                        <div key={row.id} className='relative flex gap-3'>
                          <span className='relative z-[1] mt-1 size-2.5 shrink-0 rounded-full bg-primary' />
                          <div className='min-w-0 flex-1'>
                            <div className='flex items-center justify-between gap-2'>
                              <span className='text-xs font-medium'>{EVENT_FA[row.event_type] ?? row.event_type}</span>
                              <span className='text-muted-foreground shrink-0 text-[10px]'>{time.format(new Date(row.received_at))}</span>
                            </div>
                            <p className='text-muted-foreground mt-0.5 truncate font-mono text-[10px]' dir='ltr' title={row.page_path ?? ''}>{row.page_path ?? '—'}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className='text-muted-foreground text-xs'>رویدادی برای این نشست پیدا نشد.</p>
                  )}
                </section>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </main>
  );
}
