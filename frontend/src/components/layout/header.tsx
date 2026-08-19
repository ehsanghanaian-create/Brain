'use client';
import React from 'react';
import { SidebarTrigger, useSidebar } from '../ui/sidebar';
import { useInfobar } from '../ui/infobar';
import { Separator } from '../ui/separator';
import { Breadcrumbs } from '../breadcrumbs';
import SearchInput from '../search-input';
import { ThemeModeToggle } from '../themes/theme-mode-toggle';
import { Button } from '../ui/button';
import { Icons } from '../icons';

/** Dashboard header: sidebar trigger (Ctrl+B), breadcrumbs, search, focus mode (Ctrl+Shift+F collapses navigation), theme. */
export default function Header() {
  const { open, setOpen, isMobile } = useSidebar();
  const infobar = useInfobar();
  React.useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'f') { e.preventDefault(); setOpen(false); infobar.setOpen(false); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [setOpen]);
  return (
    <header className='bg-background/70 sticky top-0 z-20 flex h-14 shrink-0 items-center justify-between gap-2 border-b backdrop-blur-md'>
      <div className='flex min-w-0 items-center gap-2 px-3 md:px-4'>
        <SidebarTrigger className='-ms-1' />
        <Separator orientation='vertical' className='me-2 h-4 data-vertical:self-center' />
        <div className='min-w-0 truncate'><Breadcrumbs /></div>
      </div>
      <div className='flex items-center gap-1 px-3 md:px-4'>
        <div className='hidden lg:flex'><SearchInput /></div>
        {!isMobile && (
          <Button variant='ghost' size='icon-sm' title={open ? 'حالت تمرکز: بستن منو و پنل راهنما (Ctrl+Shift+F)' : 'باز کردن منو (Ctrl+B)'} onClick={() => { if (open) { setOpen(false); infobar.setOpen(false); } else setOpen(true); }} aria-label='حالت تمرکز'>
            {open ? <Icons.focus className='size-4' /> : <Icons.menu className='size-4' />}
          </Button>
        )}
        <ThemeModeToggle />
      </div>
    </header>
  );
}
