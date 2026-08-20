'use client';

import { Button } from '@/components/ui/button';
import { ApiError, endpoints } from '@/lib/api/client';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';

const TABLE_FA: Record<string, string> = {
  graph_nodes: 'گره‌های گراف', graph_edges: 'یال‌های گراف', gsc_daily: 'داده Search Console', ga4_daily: 'داده Analytics',
  keywords: 'کلمات کلیدی', content_items: 'محتواها', content_plans: 'برنامه‌های محتوا', posts: 'نوشته‌های وردپرس',
  pages: 'صفحات خزش‌شده', site_memory: 'مغز سایت', site_connections: 'اتصال‌ها', sync_runs: 'تاریخچه همگام‌سازی'
};

/**
 * حذف سایت + کل داده‌هایش — تأیید دومرحله‌ای:
 * ۱) DELETE بدون force → اگر 409 (site_has_data)، فهرست داده‌هایی که پاک می‌شوند نشان داده می‌شود
 * ۲) تأیید صریح کاربر → DELETE?force=true (برگشت‌ناپذیر — backend همه ردیف‌های مرتبط را پاک می‌کند)
 */
export function DeleteSiteButton({ siteId, siteName, redirectAfter = false, size = 'sm' }: {
  siteId: string;
  siteName: string;
  redirectAfter?: boolean;
  size?: 'sm' | 'default';
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function remove() {
    if (!window.confirm(`سایت «${siteName}» حذف شود؟`)) return;
    setBusy(true);
    try {
      // مرحله ۱ — بدون force: اگر داده دارد، backend با 409 جزئیات را برمی‌گرداند
      await endpoints.deleteSite(siteId, false);
      toast.success(`سایت «${siteName}» حذف شد`);
      redirectAfter ? router.push('/dashboard/sites') : router.refresh();
      return;
    } catch (e) {
      if (!(e instanceof ApiError) || e.code !== 'site_has_data') {
        toast.error(e instanceof ApiError ? e.message : String(e));
        setBusy(false);
        return;
      }
      // مرحله ۲ — تأیید صریح حذف داده‌ها (details = {جدول: تعداد ردیف})
      const detail = e.details as Record<string, number> | string[] | null;
      const entries: [string, number | null][] = Array.isArray(detail)
        ? detail.map((t) => [t, null])
        : Object.entries(detail ?? {}).sort((a, b) => b[1] - a[1]);
      const fa = entries.slice(0, 8).map(([t, n]) => `${TABLE_FA[t] ?? t}${n != null ? ` (${n.toLocaleString('fa-IR')})` : ''}`).join('، ');
      const ok = window.confirm(
        `⚠️ این سایت داده دارد و همه چیز برای همیشه پاک می‌شود:\n${fa}${entries.length > 8 ? ' و…' : ''}\n\nحذف کامل «${siteName}» و تمام داده‌هایش؟ (برگشت‌ناپذیر)`
      );
      if (!ok) {
        setBusy(false);
        return;
      }
    }
    try {
      const r = await endpoints.deleteSite(siteId, true);
      const n = Object.values((r as { related_rows_deleted?: Record<string, number> }).related_rows_deleted ?? {}).reduce((a, b) => a + b, 0);
      toast.success(`سایت «${siteName}» و ${n.toLocaleString('fa-IR')} ردیف داده حذف شد`);
      redirectAfter ? router.push('/dashboard/sites') : router.refresh();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button type='button' size={size} variant='destructive' disabled={busy} onClick={() => void remove()} data-testid={`delete-site-${siteId}`}>
      {busy ? 'در حال حذف…' : 'حذف سایت'}
    </Button>
  );
}
