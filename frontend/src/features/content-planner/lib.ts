import type { ContentPlan } from '@/lib/api/client';

/** Pure helpers for the planner UI (unit-tested): text ↔ structured field parsers, client-side filter/sort, calendar grouping. */
export function parseHeadings(text: string): { level: number; text: string }[] {
  return text.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => { const m = l.match(/^h?([23])[:.\-)\s]+(.*)$/i); return m ? { level: Number(m[1]), text: m[2].trim() } : { level: 2, text: l.replace(/^#+\s*/, '') }; });
}
export function headingsToText(h: { level: number; text: string }[]): string { return h.map((x) => `H${x.level}: ${x.text}`).join('\n'); }
export function parseTags(s: string): string[] { return s.split(/[,،;|\n]/).map((x) => x.trim()).filter(Boolean); }
export function filterPlans(items: ContentPlan[], f: { q?: string; status?: string; category_id?: string | number; priority?: string }): ContentPlan[] {
  const q = (f.q ?? '').trim();
  return items.filter((p) => (!f.status || p.status === f.status) && (!f.category_id || String(p.category_id ?? '') === String(f.category_id)) && (!f.priority || p.priority === f.priority) && (!q || [p.title, p.primary_keyword, p.url, p.seo_title, ...(p.secondary_keywords ?? [])].some((v) => (v ?? '').includes(q))));
}
export function sortPlans(items: ContentPlan[], key: keyof ContentPlan, desc = true): ContentPlan[] {
  return [...items].sort((a, b) => { const x = a[key] as any, y = b[key] as any; if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1; const c = typeof x === 'number' ? x - y : String(x).localeCompare(String(y), 'fa'); return desc ? -c : c; });
}
export function groupByDay<T extends { publish_date: string | null }>(items: T[]): Record<string, T[]> {
  const out: Record<string, T[]> = {};
  for (const it of items) if (it.publish_date) (out[it.publish_date] ??= []).push(it);
  return out;
}
export function weekDays(anchor: Date): string[] {
  const start = new Date(anchor); start.setUTCDate(start.getUTCDate() - ((start.getUTCDay() + 1) % 7));   // Saturday-first
  return Array.from({ length: 7 }, (_, i) => { const d = new Date(start); d.setUTCDate(start.getUTCDate() + i); return d.toISOString().slice(0, 10); });
}
