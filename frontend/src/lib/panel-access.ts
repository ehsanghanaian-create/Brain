export type PanelRole = 'admin' | 'analyst' | 'call_center';

export function allowedPage(role: PanelRole, pathname: string): boolean {
  if (role === 'admin') return true;
  if (role === 'call_center') return pathname === '/dashboard/call-center';
  return ['/dashboard/overview', '/dashboard/reports', '/dashboard/traffic', '/dashboard/sites',
    '/dashboard/graph', '/dashboard/work', '/dashboard/opportunities', '/ads-data'].some((path) => pathname === path || pathname.startsWith(path + '/'));
}

export function homeFor(role: PanelRole): string {
  return role === 'call_center' ? '/dashboard/call-center' : '/dashboard/overview';
}
