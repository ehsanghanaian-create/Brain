'use client';

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { useKBar } from 'kbar';
import { PearlMenu } from './pearl-menu';
import { pearlNavigation } from './navigation-model';
import { navigationHref, siteFromLocation } from './routing';
import { endpoints } from '@/lib/api/client';
import { AddSiteDialog } from '@/features/sites/components/add-site-dialog';
import { useSidebar } from '@/components/ui/sidebar';
import { useInfobar } from '@/components/ui/infobar';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle
} from '@/components/ui/sheet';
import Header from '@/components/layout/header';
import { TYPE_FA as JOB_LABELS } from '@/components/layout/background-jobs';
import { InfoSidebar } from '@/components/layout/info-sidebar';
import styles from './salimore-shell.module.css';

export function SalimoreShell({
  children,
  accountName
}: {
  children: ReactNode;
  accountName: string | null;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { open, setOpen, isMobile, openMobile, setOpenMobile } = useSidebar();
  const help = useInfobar();
  const { query: search } = useKBar();
  const [jobsOpen, setJobsOpen] = useState(false);
  const [siteFormOpen, setSiteFormOpen] = useState(false);
  const [rememberedSite, setRememberedSite] = useState('');
  const initialized = useRef(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const sitesQuery = useQuery({ queryKey: ['sites'], queryFn: endpoints.sites, staleTime: 30_000 });
  const sites = sitesQuery.data ?? [];
  const routeSite = siteFromLocation(pathname, searchParams.get('site'));
  const siteId =
    sites.find((site) => site.site_id === routeSite)?.site_id ??
    sites.find((site) => site.site_id === rememberedSite)?.site_id ??
    sites[0]?.site_id ??
    '';
  const jobs = useQuery({
    queryKey: ['background-jobs'],
    queryFn: () => endpoints.jobs(40),
    staleTime: 1000,
    refetchInterval: 15_000
  });
  const inbox = useQuery({
    queryKey: ['navigation-inbox', siteId],
    queryFn: () => endpoints.actionInbox({ siteId, limit: 1 }),
    enabled: !!siteId,
    staleTime: 30_000,
    refetchInterval: 60_000
  });
  const siteJobs = useMemo(
    () => (jobs.data ?? []).filter((job) => !siteId || job.site_id === siteId),
    [jobs.data, siteId]
  );
  const latest = siteJobs.find((job) => job.finished_at)?.finished_at;
  const lastRun = latest
    ? `آخرین: ${new Intl.DateTimeFormat('fa-IR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Tehran' }).format(new Date(latest))}`
    : jobs.isError
      ? 'وضعیت در دسترس نیست'
      : 'اجرایی ثبت نشده';
  const selectedEntry = pearlNavigation
    .flatMap((group) => group.entries)
    .find((entry) => entry.href === pathname);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    try {
      setRememberedSite(localStorage.getItem('salimore-selected-site') ?? '');
    } catch {
      /* Storage can be disabled. */
    }
    if (window.innerWidth >= 768 && window.innerWidth < 1200) setOpen(false);
  }, [setOpen]);
  useEffect(
    () => () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    },
    []
  );
  const navigate = (href: string) => {
    setOpenMobile(false);
    router.push(navigationHref(href, siteId));
  };
  const openSearch = (text = '') => {
    const show = () => {
      search.setSearch(text);
      search.toggle();
    };
    if (isMobile && openMobile) {
      setOpenMobile(false);
      if (searchTimer.current) clearTimeout(searchTimer.current);
      // Let the existing sheet's exit/focus-return finish before opening KBar.
      searchTimer.current = setTimeout(show, 220);
    } else show();
  };
  const changeSite = (id: string) => {
    if (!sites.some((site) => site.site_id === id)) return;
    setRememberedSite(id);
    try {
      localStorage.setItem('salimore-selected-site', id);
    } catch {
      /* URL remains the source of scope. */
    }
    setOpenMobile(false);
    router.push(`/dashboard/sites/${encodeURIComponent(id)}`);
  };
  const renderMenu = (mobile: boolean) => (
    <PearlMenu
      sites={sites.map((site) => ({
        id: site.site_id,
        name: site.name,
        domain: site.canonical_url.replace(/^https?:\/\//, '').replace(/\/$/, '')
      }))}
      selectedSiteId={siteId}
      onSiteChange={changeSite}
      user={{
        name: accountName ?? 'حساب جاری',
        role: 'SEO Brain',
        initial: (accountName ?? 'ک').slice(0, 1).toUpperCase()
      }}
      activeId={
        selectedEntry?.id ??
        (pathname.startsWith('/dashboard/sites/') ? 'sites' : pathname.replace('/dashboard/', ''))
      }
      collapsed={mobile ? false : !open}
      onCollapsedChange={(value) => (mobile ? setOpenMobile(!value) : setOpen(!value))}
      manageSearchShortcut={false}
      onOpenSearch={openSearch}
      onNavigate={navigate}
      onAddSite={() => {
        const show = () => {
          setSiteFormOpen(true);
        };
        if (isMobile && openMobile) {
          setOpenMobile(false);
          if (searchTimer.current) clearTimeout(searchTimer.current);
          searchTimer.current = setTimeout(show, 220);
        } else show();
      }}
      onCreateTask={() => navigate('/dashboard/calendar')}
      primaryActionLabel='برنامه‌ریزی محتوا'
      onSettings={() => navigate('/dashboard/settings')}
      onNotifications={() => {
        setOpenMobile(false);
        setJobsOpen(true);
      }}
      notificationLabel='گزارش پردازش‌ها'
      onHelp={() => {
        setOpenMobile(false);
        help.toggleInfobar();
      }}
      onSignOut={() => window.location.assign('/auth/logout')}
      openActions={inbox.data?.total}
      statsMessage={
        inbox.isLoading ? 'دریافت آمار…' : inbox.isError ? 'دریافت آمار ناموفق' : undefined
      }
      lastSync={lastRun}
      activity={
        jobs.isError
          ? ['دریافت وضعیت پردازش‌ها ناموفق بود.']
          : siteJobs
              .slice(0, 6)
              .map(
                (job) =>
                  `${JOB_LABELS[job.type] ?? job.type} · ${{ queued: 'در صف', running: 'در حال اجرا', succeeded: 'انجام شد', failed: 'ناموفق' }[job.status] ?? job.status}`
              )
      }
      sitesStatus={sitesQuery.isLoading ? 'loading' : sitesQuery.isError ? 'error' : undefined}
      onRetrySites={() => void sitesQuery.refetch()}
    />
  );

  return (
    <>
      <div className={styles.shell} data-salimore-shell='true'>
        {!isMobile && <div className={styles.menuHost}>{renderMenu(false)}</div>}
        <main id='main-content' tabIndex={-1} className={styles.content}>
          <Header accountName={accountName} jobsOpen={jobsOpen} onJobsOpenChange={setJobsOpen} />
          <div className={styles.page}>{children}</div>
        </main>
        {isMobile && (
          <Sheet open={openMobile} onOpenChange={setOpenMobile}>
            <SheetContent
              side='right'
              showCloseButton={false}
              data-sidebar='sidebar'
              className={styles.mobileSheet}
              finalFocus={() =>
                document.querySelector<HTMLButtonElement>('[data-sidebar="trigger"]')
              }
            >
              <SheetHeader className='sr-only'>
                <SheetTitle>منوی سالیمور</SheetTitle>
                <SheetDescription>سایت‌ها و بخش‌های SEO Brain</SheetDescription>
              </SheetHeader>
              <div className={styles.mobileMenu}>{renderMenu(true)}</div>
            </SheetContent>
          </Sheet>
        )}
        <AddSiteDialog open={siteFormOpen} onOpenChange={setSiteFormOpen} />
      </div>
      <InfoSidebar side='left' />
    </>
  );
}
