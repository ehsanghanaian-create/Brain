# Salimore navigation refinement — 2026-11-05

## Product behavior

All 22 canonical destinations remain available. Expanded navigation has up to five ordered, account-scoped quick links in the rail; collapsed navigation has the five product groups. Profile → «تنظیمات دسترسی سریع» opens the same editor as the rail adjustment button. Preferences store route IDs only, per account in this browser, and do not synchronize across devices. Invalid or blocked storage fails visibly.

The selected item uses an inset accent and fading glass surface. Decorative tree dots/lines and the floating selection bridge have been removed. The footer boundary fades, the edge collapse control is a compact glass tab, and the redundant footer gear becomes the existing gateway logout action.

«تازه‌سازی وضعیت» refetches jobs and the selected site's action inbox, disables repeat clicks and rotates during the request. Failure retains previous data with a visible message; it does not start a crawl or synchronization.

## Support runtime

The rail support action opens an in-app ticket list and thread without leaving the current page. Create, reply, close/reopen, status filtering and pagination use persisted SQLite records and server references, not simulated success. Failed submissions retain text. There is no email delivery, push notification, external chat agent or response-time promise.

`backend/Dockerfile.support` runs only `support.app:app`, using the existing backend Python image as a dependency base. It does not import the SEO application or scheduler. Deploy as a private `support` Compose service on `seo_net`, port 8010 inside the network, no host port:

- Dedicated `SEO_BRAIN_SUPPORT_API_TOKEN` in the root-owned production env file; pass it to this service as `SUPPORT_API_TOKEN`.
- `SUPPORT_DB_PATH=/data/support.db`, mounted from `./support-data` owned by UID/GID 10001, mode 0700.
- Explicit `SUPPORT_STAFF_ACCOUNTS=salimore-seo` for the existing business administrator. No default staff role. The existing shared login is still a shared identity; individual team identities require separate gateway accounts.
- Frontend `SEO_BRAIN_SUPPORT_API_URL=http://support:8010` and the dedicated token, server-side only.
- No core `.env.production` env_file on the support service: Google/WordPress/core API credentials are not supplied to it.
- Read-only root filesystem, tmpfs `/tmp`, cap_drop ALL, no-new-privileges, 192 MB memory, 0.2 CPU; GET `/health` healthcheck.

Every public support request must pass the existing Nginx auth_request gateway. The proxy projects the already gateway-validated signed session's account and ignores caller actor/role headers; it never forwards the raw cookie. Its actor projection is not an independent signature verifier, so the Next port must remain loopback-only and support must remain private. The support service independently requires its dedicated token, scopes reads/writes by owner, and permits team-wide access/staff replies only for explicitly configured staff. SQL is parameterized; bodies/roles/owners are not accepted from a caller. No production test tickets should be created.

## Verification / release

Unit coverage includes allowlisted preference choices/order/isolation, proxy forwarding/token separation and fail-closed behavior, and temporary-database support authentication, persistence, ownership, staff replies, status transitions and validation. Synthetic browser tests exercise preference reload/order, collapsed rail, live-refetch loading/error/retry, failed ticket draft retention and successful ticket/reply/status flow, plus dialog accessibility. Existing site setup tests remain in the regression suite.

Before release: back up Compose/env and SQLite databases; build a private frontend candidate; verify actual read-only SEO endpoints; start only the isolated support service; release only frontend with --no-deps. Record the source commit, image IDs, backup and unchanged core backend/storefront IDs. Rollback restores previous frontend/Compose/env; retain support data rather than deleting tickets. Production browser checks are read-only except explicitly requested appearance/quick-link preferences.
