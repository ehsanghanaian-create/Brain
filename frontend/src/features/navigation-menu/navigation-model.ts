import { navGroups } from '@/config/nav-config';
import type { NavItem } from '@/types';

function flatten(items: NavItem[]): NavItem[] {
  return items.flatMap((item) => [item, ...flatten(item.items ?? [])]);
}

// Read the existing product inventory directly. Do not maintain a smaller copy
// of its destinations in the menu. Route authentication stays in the existing
// gateway; no authorization decisions are made by the navigation.
export const pearlNavigation = navGroups.map((group, index) => ({
  id: ['start', 'seo', 'content', 'opportunities', 'measurement'][index] ?? `group-${index}`,
  label: group.label,
  entries: flatten(group.items).map((item) => ({
    id: item.url.replace('/dashboard/', '').replace(/^\//, ''),
    label: item.title,
    href: item.url,
    iconName: item.icon ?? 'dashboard',
    description: item.description?.replace(/\s*\([^)]*فاز[^)]*\)/g, '')
  }))
}));
