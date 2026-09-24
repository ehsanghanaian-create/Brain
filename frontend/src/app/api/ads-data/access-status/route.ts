import { readFile } from 'node:fs/promises';
import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const data = JSON.parse(await readFile('/app/access-status/status.json', 'utf8'));
    if (data.site !== req.nextUrl.searchParams.get('site_id') || !Array.isArray(data.items) || typeof data.generated_at !== 'number') {
      throw new Error('unavailable');
    }
    return NextResponse.json(data, { headers: { 'Cache-Control': 'private, no-store' } });
  } catch {
    return NextResponse.json({ error: 'access_status_unavailable' }, { status: 503, headers: { 'Cache-Control': 'private, no-store' } });
  }
}
