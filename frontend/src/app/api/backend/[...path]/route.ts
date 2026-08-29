/**
 * Server-side proxy: /api/backend/<path> → ${SEO_BRAIN_API_URL}/api/v1/<path>
 * Adds X-API-Token from the server env so the browser never sees it (contract §2).
 * Passes X-Request-ID through (or generates one) and returns the backend body/status untouched.
 */
import { NextRequest, NextResponse } from 'next/server';

const BASE = (process.env.SEO_BRAIN_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
const TOKEN = process.env.SEO_BRAIN_API_TOKEN ?? '';

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const target = `${BASE}/api/v1/${path.map(encodeURIComponent).join('/')}${req.nextUrl.search}`;
  const requestId = req.headers.get('x-request-id') ?? crypto.randomUUID().replace(/-/g, '').slice(0, 16);
  const headers: Record<string, string> = { 'X-Request-ID': requestId, Accept: 'application/json' };
  if (TOKEN) headers['X-API-Token'] = TOKEN;
  const ct = req.headers.get('content-type');
  if (ct) headers['Content-Type'] = ct;
  const hasBody = !['GET', 'HEAD'].includes(req.method);
  try {
    const res = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,   // arrayBuffer keeps multipart/binary intact
      cache: 'no-store'
    });
    const body = await res.text();
    const responseHeaders: Record<string, string> = {
      'Content-Type': res.headers.get('content-type') ?? 'application/json',
      'X-Request-ID': res.headers.get('x-request-id') ?? requestId,
      'Cache-Control': res.headers.get('cache-control') ?? 'no-store'
    };
    const disposition = res.headers.get('content-disposition');
    if (disposition) responseHeaders['Content-Disposition'] = disposition;
    return new NextResponse(body, {
      status: res.status,
      headers: responseHeaders
    });
  } catch (e) {
    // backend unreachable → same envelope shape as the backend would send
    return NextResponse.json(
      { error: { code: 'backend_unreachable', message: `بک‌اند در ${BASE} در دسترس نیست`, details: { target, reason: String(e) }, request_id: requestId } },
      { status: 503, headers: { 'X-Request-ID': requestId } }
    );
  }
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
