import { pearlNavigation } from './navigation-model';

export const MAX_QUICK_ACCESS = 5;
export const DEFAULT_QUICK_ACCESS = ['graph', 'keywords', 'research', 'rank-tracking', 'calendar'];
const allowed = new Set(pearlNavigation.flatMap((group) => group.entries.map((entry) => entry.id)));

export function normalizeQuickAccess(value: unknown): string[] {
  if (!Array.isArray(value)) return [...DEFAULT_QUICK_ACCESS];
  return [
    ...new Set(value.filter((id): id is string => typeof id === 'string' && allowed.has(id)))
  ].slice(0, MAX_QUICK_ACCESS);
}
export function quickAccessKey(account: string | null): string {
  return `salimore:quick-access:v1:${encodeURIComponent(account ?? 'anonymous')}`;
}
