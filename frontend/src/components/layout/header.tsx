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
import { TaskNotifications } from '@/features/workspace/components/task-notifications';
import { api } from '@/lib/api/client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';

/** Dashboard header: sidebar trigger (Ctrl+B), breadcrumbs, search, focus mode (Ctrl+Shift+F collapses navigation), theme. */
export default function Header({ user }: { user: { username: string; full_name: string } }) {
  const { open, setOpen, isMobile } = useSidebar();
  const router = useRouter();
  const infobar = useInfobar();
  React.useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'f') { e.preventDefault(); setOpen(false); infobar.setOpen(false); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [setOpen]);
  async function logout() {
    try { await api('/auth/logout', { method: 'POST' }); router.replace('/login'); router.refresh(); }
    catch { toast.error('خروج انجام نشد؛ دوباره تلاش کنید'); }
  }
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
        <TaskNotifications />
        <Link href='/dashboard/profile' title='پروفایل من' className='hidden max-w-48 truncate rounded-md border px-2 py-1 text-xs hover:bg-muted sm:block'>
          {user.full_name} <span dir='ltr' className='text-muted-foreground'>@{user.username}</span>
        </Link>
        <Button variant='ghost' size='sm' onClick={() => void logout()} aria-label={`خروج از حساب ${user.username}`} title={`خروج از حساب ${user.username}`}>
          <Icons.logout className='size-4' /><span className='hidden lg:inline'>خروج</span>
        </Button>
      </div>
    </header>
  );
}
