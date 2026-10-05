'use client';
import { navGroups } from '@/config/nav-config';
import { KBarAnimator, KBarPortal, KBarPositioner, KBarProvider, KBarSearch } from 'kbar';
import { Kbd } from '@/components/ui/kbd';
import { useRouter } from 'next/navigation';
import { useMemo } from 'react';
import RenderResults from './render-result';
import useThemeSwitching from './use-theme-switching';
import { useFilteredNavGroups } from '@/hooks/use-nav';
import { allowedPage, type PanelRole } from '@/lib/panel-access';

export default function KBar({ children, role }: { children: React.ReactNode; role: PanelRole }) {
  const router = useRouter();
  const filteredGroups = useFilteredNavGroups(navGroups);

  // These action are for the navigation
  const actions = useMemo(() => {
    // Define navigateTo inside the useMemo callback to avoid dependency array issues
    const navigateTo = (url: string) => {
      router.push(url);
    };

    const allItems = filteredGroups.flatMap((group) => group.items).filter((item) => allowedPage(role, item.url));

    return allItems.flatMap((navItem) => {
      // Only include base action if the navItem has a real URL and is not just a container
      const baseAction =
        navItem.url !== '#'
          ? {
              id: `${navItem.title.toLowerCase()}Action`,
              name: navItem.title,
              shortcut: navItem.shortcut,
              keywords: navItem.title.toLowerCase(),
              section: 'Navigation',
              subtitle: `Go to ${navItem.title}`,
              perform: () => navigateTo(navItem.url)
            }
          : null;

      // Map child items into actions
      const childActions =
        navItem.items?.map((childItem) => ({
          id: `${childItem.title.toLowerCase()}Action`,
          name: childItem.title,
          shortcut: childItem.shortcut,
          keywords: childItem.title.toLowerCase(),
          section: navItem.title,
          subtitle: `Go to ${childItem.title}`,
          perform: () => navigateTo(childItem.url)
        })) ?? [];

      // Return only valid actions (ignoring null base actions for containers)
      return baseAction ? [baseAction, ...childActions] : childActions;
    });
  }, [router, filteredGroups, role]);

  return (
    <KBarProvider actions={actions}>
      <KBarComponent>{children}</KBarComponent>
    </KBarProvider>
  );
}
const KBarComponent = ({ children }: { children: React.ReactNode }) => {
  useThemeSwitching();

  return (
    <>
      <KBarPortal>
        <KBarPositioner className='bg-black/10 supports-backdrop-filter:backdrop-blur-xs fixed inset-0 z-99999 flex items-start! justify-center p-4! pt-[14vh]!'>
          <KBarAnimator className='bg-popover text-popover-foreground ring-foreground/10 relative mx-auto w-full max-w-[600px] overflow-hidden rounded-xl shadow-lg ring-1'>
            <div className='bg-popover sticky top-0 z-10 border-b'>
              <KBarSearch className='placeholder:text-muted-foreground w-full border-none bg-transparent px-4 py-3.5 text-sm outline-hidden focus:ring-0 focus:outline-hidden' />
            </div>
            <div className='h-[400px]'>
              <RenderResults />
            </div>
            <div className='text-muted-foreground flex items-center gap-3 border-t px-3 py-2 text-xs'>
              <span className='flex items-center gap-1'>
                <Kbd>↑</Kbd>
                <Kbd>↓</Kbd> navigate
              </span>
              <span className='flex items-center gap-1'>
                <Kbd>↵</Kbd> open
              </span>
              <span className='flex items-center gap-1'>
                <Kbd>esc</Kbd> close
              </span>
            </div>
          </KBarAnimator>
        </KBarPositioner>
      </KBarPortal>
      {children}
    </>
  );
};
