# Web Google OAuth + GA4 Property Discovery (SaaS onboarding layer)

**Status:** browser flow available; production HTTPS callback added 2026-09-30. The CLI-only Google consent (`sync-gsc.py --auth-only`) has a browser replacement.
No duplicate OAuth architecture: the flow reuses the EXISTING auth core in `gsc/client.py` — same OAuth client
(`_client_config` → `.env` / SecretStore), same data scopes, same `Credentials.to_json()` format in the encrypted
SecretStore (legacy file migration is supported) — so the GSC client, GA4 client and pipelines keep working.

```
[اتصال حساب گوگل] → GET /connections/google/authorize (→ consent URL, state nonce)
   → Google consent (openid email + webmasters.readonly + analytics.readonly + adwords)
   → GET https://seo.gearboxemdad.com/api/v1/connections/google/callback
   → Caddy bypasses Basic auth only for this route and forwards to /api/backend/connections/google/callback
   → encrypted shared token → GSC property discovery + GA4 property discovery
```

## Production configuration

- Set `FRONTEND_ORIGIN=https://seo.gearboxemdad.com` on the backend (or explicitly set `GOOGLE_OAUTH_REDIRECT`). The authorize response must return `https://seo.gearboxemdad.com/api/v1/connections/google/callback`, never a loopback address. Local development without an origin still uses loopback.
- Create a Google OAuth **Web application** client and register that exact HTTPS callback under **Authorized redirect URIs**. A Desktop client accepts local loopback callbacks and cannot complete this server-side browser flow. Save the Web client ID and secret in SEO Brain's encrypted SecretStore; do not replace the working client until the Web client exists.
- The Caddy block in `deploy/seo-brain/Caddyfile.snippet` routes only the exact callback around Basic auth, suppresses request logging for its one-time authorization code, and sets no-store/no-referrer. Keep the protected panel and all other routes behind Basic auth.
- In Google Auth Platform → Audience, an external app in **Testing** loses its refresh grant after seven days. Complete Branding, publish **In production**, and perform one new consent. Sensitive scopes may require Google verification. This affects the entire Google Cloud OAuth project, so review other clients in that project before changing Branding or Audience.
- The account token is shared across SEO Brain sites. Each configured Search Console/GA4 property still needs a separate access test under the connected Google account. Revoked grants surface as `needs_reconnect`; transient refresh failures retain the token and surface as `temporary_error`.

## Backend
| Piece | File | Notes |
|---|---|---|
| Web flow | `connections/google_oauth.py` | `begin()` (consent URL + state, TTL ۱۰ دقیقه) · `finish()` (code exchange → token file + `tokens/google_account.json` با email از id_token) · `status()` · `disconnect()` (best-effort revoke در گوگل + حذف فایل‌های محلی). `run_local_server` استفاده نمی‌شود. |
| Endpoints | `api/routers/google.py` | `GET /connections/google/status` · `GET /connections/google/authorize` (409 `google_client_not_configured`) · `DELETE /connections/google` — پشت X-API-Token؛ `GET /connections/google/callback` روی router بدون token (صفحهٔ فارسی بستن پنجره؛ هرگز token را echo نمی‌کند). |
| GA4 discovery | `connections/service.py::list_ga4_properties` + `GET /connections/ga4/properties` | Analytics **Admin API** v1beta ‏`accountSummaries.list` (paginated) با همان token مشترک → `{property_id, display_name, account}`؛ statusهای ok/not_configured/not_authorized/error مثل listing ‏GSC. |

## Frontend
- **کارت «حساب گوگل»** (`google-account-card.tsx` + ‏`google-account.ts`) در بالای مرکز اتصال‌ها: قطع → دکمهٔ «اتصال حساب گوگل» (باز کردن consent در تب جدید + polling تا برگشت callback)؛ متصل → ایمیل (برای tokenهای قدیمی CLI: «ایمیل نامشخص»)، چیپ‌های دسترسی GSC/GA4، «اتصال دوباره»، «قطع اتصال». بعد از تغییر، کارت‌های GSC/GA4 refresh می‌شوند.
- **Selector ‏property ‏GA4** در `connection-tester.tsx`: جایگزین ورودی دستی — dropdown با `display_name — id (account)`؛ اگر listing در دسترس نباشد ورودی دستی با پیام راهنما می‌ماند.

## Security
- توکن در SecretStore رمزگذاری می‌شود (فایل قدیمی فقط در صورت نبود SecretStore) — **هیچ ذخیرهٔ plaintext در دیتابیس**؛ ‏client credentials مثل قبل `.env`/SecretStore.
- ‏callback با state یک‌بارمصرف محافظت می‌شود؛ پاسخ HTML هیچ token/کدی را بازتاب نمی‌دهد؛ لاگ‌ها فقط class خطا.
- ‏scopeهای داده تغییر نکردند؛ ‏`openid email` فقط برای نمایش حساب اضافه شد. ‏revoke هنگام قطع اتصال (تنها POST خروجی مجاز — در گارد read-only صریحاً استثنا و مستند شد).
- tokenهای موجود CLI بدون تغییر معتبر می‌مانند.

## Tests / validation
- `tests/api/test_google_oauth.py` (۴): ‏authorize ‏(URL با scopeها/state/redirect)، ‏callback با flow جعلی → فرمت token سازگار با `_token_info` + ‏email + رد state تکراری + ‏disconnect، **دسترسی عمومی callback در حالی که بقیهٔ routeها 401 می‌گیرند**، کشف property ‏GA4 با Admin جعلی.
- pytest **164** · vitest **32** (+`google-account.test.ts`) · tsc تمیز · validate-api **219/219**.
- زنده (2026-08-20): status ‏connected ‏(token قدیمی CLI، هر دو scope ✓) · ‏GA4 discovery → **۴ property واقعی** در dropdown — ورودی دستی Property ID دیگر لازم نیست.
