import KBar from '@/components/kbar';
import { SalimoreShell } from '@/features/navigation-menu/salimore-shell';
import { sessionDisplayName } from '@/features/navigation-menu/session-display';
import { InfobarProvider } from '@/components/ui/infobar';
import { SidebarProvider } from '@/components/ui/sidebar';
import type { Metadata } from 'next';
import { cookies } from 'next/headers';

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
  const defaultOpen = cookieStore.get('sidebar_state')?.value !== 'false';
  return (
    <KBar>
      <SidebarProvider defaultOpen={defaultOpen}>
        <a
          href='#main-content'
          className='bg-background ring-ring sr-only rounded-md px-3 py-2 text-sm font-medium shadow focus:not-sr-only focus:absolute focus:top-2 focus:start-2 focus:z-50 focus:ring-2'
        >
          پرش به محتوا
        </a>
        <InfobarProvider defaultOpen={false}>
          <SalimoreShell accountName={sessionDisplayName(cookieStore.get('seo_session')?.value)}>
            {children}
          </SalimoreShell>
        </InfobarProvider>
      </SidebarProvider>
    </KBar>
  );
}
