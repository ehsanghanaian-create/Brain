import { afterEach, expect, test, vi } from 'vitest';
import { NextRequest } from 'next/server';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});
async function setup() {
  vi.stubEnv('SEO_BRAIN_API_URL', 'http://core:8000');
  vi.stubEnv('SEO_BRAIN_API_TOKEN', 'core-test-token');
  vi.stubEnv('SEO_BRAIN_SUPPORT_API_URL', 'http://support:8010');
  vi.stubEnv('SEO_BRAIN_SUPPORT_API_TOKEN', 'support-test-token');
  vi.stubEnv('SEO_BRAIN_SESSION_COOKIE_NAME', 'salimore_seo_session');
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);
  const route = await import('@/app/api/backend/[...path]/route');
  return { route, fetchMock };
}
test('support uses the gateway-validated session actor and a dedicated token, ignoring caller role headers', async () => {
  const { route, fetchMock } = await setup();
  const payload = Buffer.from(`operator\n${Math.floor(Date.now() / 1000) + 3600}\nnonce`).toString(
    'base64url'
  );
  // Signature verification is performed by the upstream gateway. This test
  // verifies only the post-gateway projection and forwarding boundary.
  const request = new NextRequest('http://ui/api/backend/support/tickets', {
    headers: {
      cookie: `salimore_seo_session=${payload}.gateway-signature`,
      'X-SEO-Actor': 'manager',
      'X-SEO-Role': 'admin'
    }
  });
  await route.GET(request, { params: Promise.resolve({ path: ['support', 'tickets'] }) });
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe('http://support:8010/api/v1/support/tickets');
  expect(init.headers['X-SEO-Actor']).toBe('operator');
  expect(init.headers['X-API-Token']).toBe('support-test-token');
  expect(init.headers['X-SEO-Role']).toBeUndefined();
  expect(init.headers.Cookie).toBeUndefined();
});
test('support fails closed without a session or configured service', async () => {
  const { route, fetchMock } = await setup();
  const response = await route.GET(new NextRequest('http://ui/api/backend/support/tickets'), {
    params: Promise.resolve({ path: ['support', 'tickets'] })
  });
  expect(response.status).toBe(401);
  expect(fetchMock).not.toHaveBeenCalled();
});
test('normal SEO requests retain the core token and never receive a support actor', async () => {
  const { route, fetchMock } = await setup();
  await route.GET(
    new NextRequest('http://ui/api/backend/sites', { headers: { 'X-SEO-Actor': 'manager' } }),
    { params: Promise.resolve({ path: ['sites'] }) }
  );
  expect(fetchMock.mock.calls[0][0]).toBe('http://core:8000/api/v1/sites');
  expect(fetchMock.mock.calls[0][1].headers['X-API-Token']).toBe('core-test-token');
  expect(fetchMock.mock.calls[0][1].headers['X-SEO-Actor']).toBeUndefined();
});
