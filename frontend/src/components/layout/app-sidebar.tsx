'use client';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail
} from '@/components/ui/sidebar';
import { navGroups } from '@/config/nav-config';
import { useMediaQuery } from '@/hooks/use-media-query';
import { useFilteredNavGroups } from '@/hooks/use-nav';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import * as React from 'react';
import { Icons } from '@/components/icons';
import { allowedPage, homeFor, type PanelRole } from '@/lib/panel-access';
import { api } from '@/lib/api/client';

export default function AppSidebar({ user }: { user: { username: string; full_name: string; role: PanelRole } }) {
  const pathname = usePathname();
  const { isOpen } = useMediaQuery();
  const router = useRouter();
  const filteredGroups = useFilteredNavGroups(navGroups);
  const visibleGroups = filteredGroups.map((group) => ({ ...group,
    items: group.items.filter((item) => allowedPage(user.role, item.url))
  })).filter((group) => group.items.length > 0);

  React.useEffect(() => {
    // Side effects based on sidebar state changes
  }, [isOpen]);

  return (
    <Sidebar collapsible='icon' side='right'>
      <SidebarHeader className='border-b'>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size='lg' tooltip='SEO Brain' render={<Link href={homeFor(user?.role ?? 'admin')} aria-label='صفحه اصلی SEO Brain' />} className='data-[state=open]:bg-sidebar-accent'>
              <span className='bg-primary text-primary-foreground flex size-8 shrink-0 items-center justify-center rounded-lg text-xs font-bold'>SB</span>
              <span className='grid flex-1 text-start leading-tight'><span className='truncate text-sm font-semibold'>SEO Brain</span><span className='text-muted-foreground truncate text-[11px]'>سیستم‌عامل سئوی محلی</span></span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent className='overflow-x-hidden'>
        {visibleGroups.map((group) => (
          <SidebarGroup key={group.label || 'ungrouped'} className='py-0'>
            {group.label && <SidebarGroupLabel>{group.label}</SidebarGroupLabel>}
            <SidebarMenu>
              {group.items.map((item) => {
                const Icon = item.icon ? Icons[item.icon] : Icons.logo;
                return item?.items && item?.items?.length > 0 ? (
                  <Collapsible
                    key={item.title}
                    defaultOpen={item.isActive}
                    render={<SidebarMenuItem />}
                  >
                    <CollapsibleTrigger
                      render={
                        <SidebarMenuButton
                          tooltip={item.title}
                          isActive={pathname === item.url}
                          className='group/collapsible'
                        />
                      }
                    >
                      {item.icon && <Icon />}
                      <span>{item.title}</span>
                      <Icons.chevronRight className='ms-auto transition-transform duration-200 group-data-panel-open/collapsible:rotate-90 rtl:rotate-180' />
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <SidebarMenuSub>
                        {item.items?.map((subItem) => (
                          <SidebarMenuSubItem key={subItem.title}>
                            <SidebarMenuSubButton
                              render={<Link href={subItem.url} aria-label={subItem.title} />}
                              isActive={pathname === subItem.url}
                            >
                              <span>{subItem.title}</span>
                            </SidebarMenuSubButton>
                          </SidebarMenuSubItem>
                        ))}
                      </SidebarMenuSub>
                    </CollapsibleContent>
                  </Collapsible>
                ) : (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton
                      render={<Link href={item.url} aria-label={item.title} />}
                      tooltip={item.title}
                      isActive={pathname === item.url}
                    >
                      <Icon />
                      <span>{item.title}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroup>
        ))}
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <SidebarMenuButton
                    size='lg'
                    className='data-popup-open:bg-sidebar-accent data-popup-open:text-sidebar-accent-foreground'
                  />
                }
              >
                <span className='truncate'>{user.full_name} · @{user.username}</span>
                <Icons.chevronsDown className='ms-auto size-4' />
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className='w-(--anchor-width) min-w-56 rounded-lg'
                side='bottom'
                align='end'
                sideOffset={4}
              >
                <DropdownMenuGroup>
                  <DropdownMenuLabel className='p-0 font-normal'>
                    <div className='text-muted-foreground px-1 py-1.5 text-sm'>
                      {user ? `${user.full_name} · ${user.role === 'admin' ? 'مدیر' : user.role === 'analyst' ? 'تحلیل‌گر' : 'اپراتور کال‌سنتر'}` : 'در حال دریافت کاربر…'}
                    </div>
                  </DropdownMenuLabel>
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
                <DropdownMenuGroup>
                  <DropdownMenuItem onClick={() => router.push('/dashboard/profile')}>
                    <Icons.profile className='me-2 h-4 w-4' />
                    پروفایل و رمز عبور
                  </DropdownMenuItem>
                  {user?.role === 'admin' && <DropdownMenuItem onClick={() => router.push('/dashboard/settings')}>
                    <Icons.settings className='me-2 h-4 w-4' />
                    تنظیمات
                  </DropdownMenuItem>}
                  <DropdownMenuItem onClick={async () => { await api('/auth/logout', { method: 'POST' }); router.replace('/login'); router.refresh(); }}>
                    خروج از حساب
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
