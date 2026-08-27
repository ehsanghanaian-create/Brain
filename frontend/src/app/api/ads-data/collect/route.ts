import { BlockList, isIP } from 'node:net';
import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const BASE = (process.env.SEO_BRAIN_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
const TOKEN = process.env.SEO_BRAIN_API_TOKEN ?? '';
const ALLOWED_ORIGINS = new Set(
  (process.env.ADS_COLLECTOR_ORIGINS ??
    'https://modirankhodro-emdad.com,https://www.modirankhodro-emdad.com,http://localhost:3000')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
);
const MAX_BYTES = 24_000;
const RATE_LIMIT = 180;
const rate = new Map<string, { minute: number; count: number }>();
const RESOLUTION_VERSION = '2';
const trustedProxies = new BlockList();

for (const item of (process.env.ADS_TRUSTED_PROXY_CIDRS ?? '').split(',').map((value) => value.trim()).filter(Boolean)) {
  const [address, prefixRaw] = item.split('/');
  const family = isIP(address);
  const prefix = Number(prefixRaw);
  if (family && Number.isInteger(prefix) && prefix >= 0 && prefix <= (family === 4 ? 32 : 128)) {
    trustedProxies.addSubnet(address, prefix, family === 4 ? 'ipv4' : 'ipv6');
  }
}

function cors(origin: string | null): Record<string, string> {
  return {
    'Access-Control-Allow-Origin': origin && ALLOWED_ORIGINS.has(origin) ? origin : 'null',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    Vary: 'Origin',
    'Cache-Control': 'no-store, private, max-age=0',
    'X-Robots-Tag': 'noindex, nofollow, noarchive'
  };
}

function normalizedIp(value: string | null): string | null {
  if (!value) return null;
  const candidate = value.trim().replace(/^\[|\]$/g, '').replace(/^::ffff:/, '');
  return isIP(candidate) ? candidate : null;
}

function proxyIsTrusted(ip: string | null): boolean {
  if (!ip) return false;
  const family = isIP(ip);
  return Boolean(family && trustedProxies.check(ip, family === 4 ? 'ipv4' : 'ipv6'));
}

function firstForwarded(value: string | null): string | null {
  for (const raw of (value ?? '').split(',')) {
    const ip = normalizedIp(raw);
    if (ip) return ip;
  }
  return null;
}

function requestIp(req: NextRequest): { ip: string; source: string; proxyIp: string | null; confidence: string; headersAgree: boolean } {
  // Caddy overwrites these internal headers. Standard X-Forwarded-For is not
  // used because Caddy replaces it with the CDN edge address by default.
  const claimed = normalizedIp(req.headers.get('x-collector-client-ip'));
  const forwarded = firstForwarded(req.headers.get('x-collector-xff'));
  const proxyIp = normalizedIp(req.headers.get('x-collector-proxy-ip'));
  const headersAgree = Boolean(claimed && forwarded && claimed === forwarded);
  if (claimed && headersAgree && proxyIsTrusted(proxyIp)) {
    return { ip: claimed, source: 'wcdn-x-real-ip', proxyIp, confidence: 'trusted_proxy', headersAgree };
  }
  if (claimed && headersAgree) {
    return { ip: claimed, source: 'wcdn-x-real-ip', proxyIp, confidence: 'unverified_proxy', headersAgree };
  }
  if (proxyIp) {
    return { ip: proxyIp, source: 'direct-peer', proxyIp, confidence: 'direct_peer', headersAgree };
  }
  const fallback = firstForwarded(req.headers.get('x-forwarded-for')) ?? normalizedIp(req.headers.get('x-real-ip'));
  if (fallback) return { ip: fallback, source: 'legacy-forwarded', proxyIp: null, confidence: 'unverified', headersAgree };
  return { ip: '0.0.0.0', source: 'unavailable', proxyIp: null, confidence: 'unavailable', headersAgree };
}

function allowed(origin: string | null): boolean {
  return Boolean(origin && ALLOWED_ORIGINS.has(origin));
}

function withinRate(ip: string): boolean {
  const minute = Math.floor(Date.now() / 60_000);
  const current = rate.get(ip);
  if (!current || current.minute !== minute) {
    rate.set(ip, { minute, count: 1 });
    return true;
  }
  current.count += 1;
  return current.count <= RATE_LIMIT;
}

export async function OPTIONS(req: NextRequest) {
  const origin = req.headers.get('origin');
  return new NextResponse(null, { status: allowed(origin) ? 204 : 403, headers: cors(origin) });
}

export async function POST(req: NextRequest) {
  const origin = req.headers.get('origin');
  const headers = cors(origin);
  if (!allowed(origin)) return NextResponse.json({ accepted: false }, { status: 403, headers });

  const declared = Number(req.headers.get('content-length') ?? 0);
  if (declared > MAX_BYTES) return NextResponse.json({ accepted: false }, { status: 413, headers });

  const { ip, source, proxyIp, confidence, headersAgree } = requestIp(req);
  if (!withinRate(ip)) return NextResponse.json({ accepted: false }, { status: 202, headers });

  try {
    const raw = await req.text();
    if (new TextEncoder().encode(raw).byteLength > MAX_BYTES) {
      return NextResponse.json({ accepted: false }, { status: 413, headers });
    }
    const input = JSON.parse(raw) as Record<string, unknown>;
    const inputMetadata =
      input.metadata && typeof input.metadata === 'object' && !Array.isArray(input.metadata)
        ? (input.metadata as Record<string, unknown>)
        : {};
    const edgeCountry = req.headers.get('wcdn-country') ?? req.headers.get('cf-ipcountry');
    const payload = {
      ...input,
      server_ip: ip,
      server_ip_source: source,
      server_proxy_ip: proxyIp,
      server_ip_confidence: confidence,
      server_ip_resolution_version: RESOLUTION_VERSION,
      server_user_agent: req.headers.get('user-agent')?.slice(0, 1000) ?? null,
      metadata: {
        ...inputMetadata,
        ip_headers_agree: headersAgree,
        ...(edgeCountry ? { edge_country: edgeCountry.slice(0, 8) } : {})
      }
    };
    const internalHeaders: Record<string, string> = {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-Request-ID': crypto.randomUUID().replace(/-/g, '').slice(0, 16)
    };
    if (TOKEN) internalHeaders['X-API-Token'] = TOKEN;
    const res = await fetch(`${BASE}/api/v1/ads-data/events`, {
      method: 'POST',
      headers: internalHeaders,
      body: JSON.stringify(payload),
      cache: 'no-store',
      signal: AbortSignal.timeout(5000)
    });
    return NextResponse.json({ accepted: res.ok }, { status: 202, headers });
  } catch {
    // Collection must never interfere with the WordPress visitor experience.
    return NextResponse.json({ accepted: false }, { status: 202, headers });
  }
}
