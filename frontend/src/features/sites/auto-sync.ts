import type { AutoSyncPlan } from '@/lib/api/client';

/** Pure helpers for the auto-sync line (unit-tested) — friendly text only, no scheduler internals. */
export function intervalFa(hours: number): string {
  if (hours % 24 === 0) {
    const d = hours / 24;
    return d === 1 ? 'روزانه' : `هر ${d.toLocaleString('fa-IR')} روز`;
  }
  return `هر ${hours.toLocaleString('fa-IR')} ساعت`;
}

export function nextSyncFa(plan: Partial<AutoSyncPlan> | null | undefined): string | null {
  if (!plan?.enabled || !plan.sources) return null;
  const nexts = Object.values(plan.sources).map((s) => s.next_at).filter((n): n is string => Boolean(n));
  if (!nexts.length) return null;
  const soonest = nexts.sort()[0];
  const dt = new Date(soonest);
  if (Number.isNaN(dt.getTime())) return null;
  return dt.getTime() <= Date.now()
    ? 'در نوبت اجرا'
    : dt.toLocaleString('fa-IR', { timeZone: 'Asia/Tehran', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function autoSyncLine(plan: Partial<AutoSyncPlan> | null | undefined): string {
  if (!plan) return '';
  if (!plan.enabled) return 'به‌روزرسانی خودکار: خاموش';
  const nxt = nextSyncFa(plan);
  return `به‌روزرسانی خودکار: ${intervalFa(plan.interval_hours ?? 24)}${nxt ? ` · بعدی: ${nxt}` : ''}`;
}
