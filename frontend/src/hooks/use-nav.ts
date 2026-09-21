'use client';

import type { NavItem, NavGroup } from '@/types';
import { hiddenNavUrls } from '@/config/nav-config';

function filterNavItems(items: NavItem[]) {
  return items.filter((item) => !hiddenNavUrls.has(item.url));
}

export function useFilteredNavItems(items: NavItem[]) {
  return filterNavItems(items);
}

export function useFilteredNavGroups(groups: NavGroup[]) {
  return groups
    .map((group) => ({ ...group, items: filterNavItems(group.items) }))
    .filter((group) => group.items.length > 0);
}
