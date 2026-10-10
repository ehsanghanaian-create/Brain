/**
 * Backend routes that must be reachable without the SEO Brain panel session.
 *
 * Keep this allow-list exact. The Google callback is protected by the
 * short-lived, one-time OAuth state nonce in the backend; Google's redirect
 * cannot carry our private panel cookie.
 */
const PUBLIC_BACKEND_ROUTES = new Set([
  'auth/login',
  'auth/status',
  'connections/google/callback'
]);

export function isPublicBackendRoute(path: readonly string[]): boolean {
  return PUBLIC_BACKEND_ROUTES.has(path.join('/'));
}
