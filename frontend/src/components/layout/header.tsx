'use client';
import React from 'react';
import { SidebarTrigger, useSidebar } from '../ui/sidebar';
import { useInfobar } from '../ui/infobar';
import { Breadcrumbs } from '../breadcrumbs';
import { ThemeModeToggle } from '../themes/theme-mode-toggle';
import { BackgroundJobs } from './background-jobs';

/** Dashboard header: sidebar trigger (Ctrl+B), breadcrumbs, search, focus mode (Ctrl+Shift+F collapses navigation), theme. */
export default function Header({
  accountName,
  jobsOpen,
  onJobsOpenChange
}: {
  accountName?: string | null;
  jobsOpen?: boolean;
  onJobsOpenChange?: (open: boolean) => void;
}) {
  const { setOpen, isMobile } = useSidebar();
  const { setOpen: setInfobarOpen } = useInfobar();
  React.useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        setOpen(false);
        setInfobarOpen(false);
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [setOpen, setInfobarOpen]);
  return (
    <header
      data-salimore-header
      className='sticky top-0 z-20 flex min-h-16 shrink-0 items-center justify-between gap-2 border-b'
    >
      <div className='flex min-w-0 items-center gap-2 px-3 md:px-4'>
        {isMobile && <SidebarTrigger className='-ms-1 size-11 shrink-0' />}
        <div className='min-w-0 truncate'>
          <Breadcrumbs />
        </div>
      </div>
      <div className='flex items-center gap-1 px-3 md:px-4'>
        {accountName && (
          <span
            className='text-muted-foreground hidden max-w-32 truncate text-xs lg:block'
            dir='auto'
          >
            {accountName}
          </span>
        )}
        <ThemeModeToggle />
        <BackgroundJobs open={jobsOpen} onOpenChange={onJobsOpenChange} />
      </div>
    </header>
  );
}
