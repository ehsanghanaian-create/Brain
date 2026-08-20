# Web Google OAuth + GA4 Property Discovery (SaaS onboarding layer)

**Status:** done (2026-08-20). The CLI-only Google consent (`sync-gsc.py --auth-only`) now has a browser replacement.
No duplicate OAuth architecture: the flow reuses the EXISTING auth core in `gsc/client.py` — same OAuth client
(`_client_config` → `.env` / SecretStore), same data scopes, same token file format (`Credentials.to_json()` at
`GSC_TOKEN_PATH`) — so the GSC client, GA4 client, every pipeline and the CLI keep working unchanged.

```
[اتصال حساب گوگل] → GET /connections/google/authorize (→ consent URL, state nonce)
   → Google consent (openid email + webmasters.readonly + analytics.readonly)
   → GET /connections/google/callback  (public route — Google's redirect can't send X-API-Token; state is the guard)
   → token stored in the SAME tokens/gsc_token.json → GSC property discovery + GA4 property discovery work immediately
```

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
- توکن فقط در فایل git-ignored (فرمت قبلی) — **هیچ ذخیرهٔ plaintext در دیتابیس**؛ ‏client credentials مثل قبل `.env`/SecretStore.
- ‏callback با state یک‌بارمصرف محافظت می‌شود؛ پاسخ HTML هیچ token/کدی را بازتاب نمی‌دهد؛ لاگ‌ها فقط class خطا.
- ‏scopeهای داده تغییر نکردند؛ ‏`openid email` فقط برای نمایش حساب اضافه شد. ‏revoke هنگام قطع اتصال (تنها POST خروجی مجاز — در گارد read-only صریحاً استثنا و مستند شد).
- tokenهای موجود CLI بدون تغییر معتبر می‌مانند.

## Tests / validation
- `tests/api/test_google_oauth.py` (۴): ‏authorize ‏(URL با scopeها/state/redirect)، ‏callback با flow جعلی → فرمت token سازگار با `_token_info` + ‏email + رد state تکراری + ‏disconnect، **دسترسی عمومی callback در حالی که بقیهٔ routeها 401 می‌گیرند**، کشف property ‏GA4 با Admin جعلی.
- pytest **164** · vitest **32** (+`google-account.test.ts`) · tsc تمیز · validate-api **219/219**.
- زنده (2026-08-20): status ‏connected ‏(token قدیمی CLI، هر دو scope ✓) · ‏GA4 discovery → **۴ property واقعی** در dropdown — ورودی دستی Property ID دیگر لازم نیست.
