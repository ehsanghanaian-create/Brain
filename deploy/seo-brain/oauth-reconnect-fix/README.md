# Google authorization repair — 2026-09-21

Reconnecting previously revoked the old refresh token after exchanging the new
authorization code. Google revocation affects the project grant, potentially
invalidating the newly issued credentials too. Revocation now happens only on
explicit disconnect. A callback without offline refresh credentials preserves
the previously stored token and reports an error.

Expired access tokens still refresh automatically and persist in the encrypted
SecretStore. Transient transport/retryable provider failures retry twice, then
report a temporary failure without starting consent or deleting credentials.
Nonretryable refresh errors require reconnecting. This cannot resurrect an
already revoked grant or override Google's token expiration rules.

Build from repository root on the production Docker host:

```sh
docker build -f deploy/seo-brain/oauth-reconnect-fix/Dockerfile -t seo-brain-backend:20260921-oauth-reconnect-v2 .
```

The base image is the verified production 20260920-phonetab-v1 release. Update
only the backend image in compose, retaining the existing data/secrets volume
and encryption key. Keep a copy of the previous compose file for rollback.

Validation: OAuth API, service-account and refresh persistence suites: 22 tests
passed. Refresh tests use real Google credential parsing/refresh with mocked
HTTP and a real encrypted temporary store, including reopening that store.

Operational follow-up: verify OAuth consent is Production (Testing can impose
seven-day refresh grants), complete Google's account-owner verification for an
already invalid grant, and test live GSC/GA4 requests. Token presence alone in
the current status endpoint is not evidence of a healthy provider connection.
