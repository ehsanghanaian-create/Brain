'use client';

import { navGroups } from '@/config/nav-config';
import { usePathname } from 'next/navigation';
import { useMemo } from 'react';

type BreadcrumbItem = { title: string; link: string };

// Persian titles come from the nav config so breadcrumbs, sidebar and ⌘K stay in sync.
const NAV_TITLES: Record<string, string> = Object.fromEntries(
  navGroups.flatMap((g) => g.items.map((i) => [i.url, i.title]))
);
NAV_TITLES['/dashboard'] = 'داشبورد';

export function useBreadcrumbs() {
  const pathname = usePathname();
  return useMemo<BreadcrumbItem[]>(() => {
    const segments = pathname.split('/').filter(Boolean);
    const crumbs = segments.map((segment, index) => {
      const path = `/${segments.slice(0, index + 1).join('/')}`;
      return { title: NAV_TITLES[path] ?? decodeURIComponent(segment), link: path };
    });
    // "/dashboard/overview" → single crumb "داشبورد"
    return crumbs.filter((c, i) => !(i > 0 && c.title === crumbs[i - 1].title));
  }, [pathname]);
}
