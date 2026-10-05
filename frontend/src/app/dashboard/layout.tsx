import KBar from '@/components/kbar';
import AppSidebar from '@/components/layout/app-sidebar';
import Header from '@/components/layout/header';
import { InfoSidebar } from '@/components/layout/info-sidebar';
import { InfobarProvider } from '@/components/ui/infobar';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import type { Metadata } from 'next';
import { cookies } from 'next/headers';
import { BackgroundJobs } from '@/components/layout/background-jobs';
import { redirect } from 'next/navigation';
import type { PanelRole } from '@/lib/panel-access';

export const metadata: Metadata = {
  description: 'داشبورد SEO Brain — سیستم‌عامل سئوی محلی',
  robots: {
    index: false,
    follow: false
  }
};

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  // Persisting the sidebar state in the cookie.
  const cookieStore = await cookies();
  const defaultOpen = cookieStore.get('sidebar_state')?.value === 'true';
  const token = cookieStore.get('sb_panel_session')?.value;
  if (!token) redirect('/login');
  const backend = (process.env.SEO_BRAIN_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
  const me = await fetch(`${backend}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' });
  if (!me.ok) redirect('/login');
  const user = await me.json() as { full_name: string; role: PanelRole };
  return (
    <KBar role={user.role}>
      <SidebarProvider defaultOpen={defaultOpen}>
        <a
          href='#main-content'
          className='bg-background ring-ring sr-only rounded-md px-3 py-2 text-sm font-medium shadow focus:not-sr-only focus:absolute focus:top-2 focus:start-2 focus:z-50 focus:ring-2'
        >
          پرش به محتوا
        </a>
        <AppSidebar user={user} />
        <SidebarInset id='main-content' tabIndex={-1} className='scroll-mt-16'>
          <InfobarProvider defaultOpen={false}>
            <div className='flex min-w-0 flex-1 flex-col'>
              <Header />
              {children}
              {user.role === 'admin' && <BackgroundJobs />}
            </div>
            <InfoSidebar side='right' />
          </InfobarProvider>
        </SidebarInset>
      </SidebarProvider>
    </KBar>
  );
}
