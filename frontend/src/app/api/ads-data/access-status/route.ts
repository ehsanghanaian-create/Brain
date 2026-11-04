import { NextRequest, NextResponse } from 'next/server';
import { accessStatusResponse } from '@/features/ads-data/access-status-response';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  const result = await accessStatusResponse(req.nextUrl.searchParams.get('site_id'), {
    enabled: process.env.AD_ACCESS_STATUS_ENABLED,
    site: process.env.AD_ACCESS_SITE_ID
  });
  return NextResponse.json(result.data, { status: result.status, headers: { 'Cache-Control': 'private, no-store' } });
}
