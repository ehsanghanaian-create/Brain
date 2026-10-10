import { NextResponse, type NextRequest } from 'next/server';
import { allowedPage, homeFor, type PanelRole } from '@/lib/panel-access';

const BASE = (process.env.SEO_BRAIN_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');

export async function proxy(req: NextRequest) {
  const path = req.nextUrl.pathname;
  if (!path.startsWith('/dashboard') && path !== '/ads-data' && path !== '/api/ads-data/access-status') return NextResponse.next();
  const token = req.cookies.get('sb_panel_session')?.value;
  if (!token) return NextResponse.redirect(new URL('/login', req.url));
  try {
    const res = await fetch(`${BASE}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` }, cache: 'no-store'
    });
    if (!res.ok) return NextResponse.redirect(new URL('/login', req.url));
    const user = await res.json() as { role: PanelRole; is_superadmin: boolean };
    if (!allowedPage(user.role, path === '/api/ads-data/access-status' ? '/ads-data' : path, user.is_superadmin)) {
      if (path.startsWith('/api/')) return NextResponse.json({ error: 'forbidden' }, { status: 403 });
      return NextResponse.redirect(new URL(homeFor(user.role), req.url));
    }
  } catch {
    return NextResponse.redirect(new URL('/login', req.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ['/dashboard/:path*', '/ads-data', '/api/ads-data/access-status']
};
