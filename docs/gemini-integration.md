# Google Gemini Integration (Gemini 3.6 Flash)

Status: **implemented** · Date: 2026-08-27 · Scope: existing AI Gateway → `GeminiAdapter` (kind `google`) → همه بخش‌هایی که مدل AI استفاده می‌کنند (آزمایش تولید محتوا، استودیوی AI، تقویم محتوایی/مغز محتوا، مسیردهی وظایف).

Gemini از فاز ۹ یک adapter کامل داشت (`ai/gateway/adapters.py::GeminiAdapter` — ‏generateContent، ‏systemInstruction، ‏JSON mode، ‏list models). این فاز آن را به یک Provider درجه‌یک تبدیل می‌کند: مدل `gemini-3.6-flash` پیش‌فرض، کارت اختصاصی UI، مسیرهای پیشنهادی، و ‏fallback اختیاری env.

## 1. دریافت کلید و فعال‌سازی (اقدام انسانی)

1. کلید API را از **Google AI Studio** بسازید: <https://aistudio.google.com/apikey> (با `AIza` شروع می‌شود).
2. **AI Models → کارت Google Gemini → «اتصال Gemini»** → کلید را وارد کنید → ذخیره.
   کلید یک‌بار از پروکسی محلی عبور می‌کند، در **SecretStore** (DPAPI، ref ‏`ai-provider-{id}`) ذخیره می‌شود و فقط ۴ رقم آخر آن دوباره نمایش داده می‌شود. هرگز در `.env`ِ ریپو، سورس یا DB قرار نگیرد.
3. **«تست اتصال»** — پروب فقط‌خواندنی `GET /v1beta/models`؛ هیچ پرامپتی ارسال نمی‌شود → ‏Connected ✅ / خطا ❌ با پیام فارسی.
4. اختیاری: **«همگام‌سازی مدل‌ها»** (ادغام فهرست زنده مدل‌ها در کاتالوگ) و **«اعمال مسیرهای پیشنهادی»**.

### Env fallback (اختیاری، برای دیپلوی headless)

`GEMINI_API_KEY` و `GEMINI_MODEL` در `.env` — مسیر اصلی همچنان UI/SecretStore است؛ env فقط هنگام نبود کلید ذخیره‌شده خوانده می‌شود (`ai/config.py::env_api_key`)، هرگز ذخیره یا لاگ نمی‌شود و در UI با برچسب `key_source: env` دیده می‌شود.

## 2. مدل و کاتالوگ

| مدل | tier | برچسب‌ها | context | قیمت پیش‌فرض (in/out per 1M) |
|---|---|---|---|---|
| `gemini-3.6-flash` (پیش‌فرض) | balanced | persian, long_form, json, translation | 1M | 0.5 / 3.0 (تقریبی — در AI Models قابل اصلاح) |
| `gemini-2.5-pro` | reasoning | … | 1M | 1.25 / 10 |
| `gemini-2.5-flash` | fast | … | 1M | 0.3 / 2.5 |

قابلیت‌های اعلام‌شده kind ‏(`/ai/provider-kinds`): ‏content_generation، ‏seo_analysis، ‏content_rewrite، ‏structured_output، ‏long_context.

## 3. مسیردهی وظایف (Task Mapping — بدون hardcode)

`RECOMMENDED_ROUTES["google"]` در `ai/config.py`: همه ۱۷ task kind → ‏primary ‏`gemini-3.6-flash`؛ ‏fallback برای وظایف سنگین (article_long، content_writing، seo_analysis، fact_check، …) ‏`gemini-2.5-pro` و برای وظایف سبک (faq، rewrite، title_meta، schema، …) ‏`gemini-2.5-flash`. اعمال آن فقط با کلیک «اعمال مسیرهای پیشنهادی» انجام می‌شود — مسیردهی هرگز خودکار تغییر نمی‌کند. بدون مسیر صریح، سیاست خودکار ‏TaskRouter بر اساس tier/tags/قیمت انتخاب می‌کند و در خطاهای retryable (کلید نامعتبر نه؛ rate limit/timeout/5xx بله) به Provider بعدی زنجیره ‏fallback می‌رود؛ همه تلاش‌ها در `ai_calls` (provider، model، توکن‌ها، هزینه، تأخیر، وضعیت، خطا، site) ثبت می‌شوند.

## 4. مثال تولید محتوا

- **آزمایش تولید محتوا:** provider ‏`gemini` + model ‏`gemini-3.6-flash` را انتخاب کنید — همان فرم، همان خروجی (markdown + امتیاز سئو + ledger).
- **تقویم/مغز محتوا:** در شیت برنامه، بخش «تولید با هوش مصنوعی» → ارائه‌دهنده gemini → «تولید پیش‌نویس» یا «انتشار در وردپرس».
- **API:** ‏`POST /api/v1/sites/{site}/ai-workspace/generate {"title":"…","keyword":"…","provider":"gemini","model":"gemini-3.6-flash"}`.

## 5. تست‌ها

`tests/api/test_ai_phase9.py::test_gemini_provider_setup_routes_env_fallback_and_workspace` — ‏kind/setup/catalog/مسیرهای پیشنهادی/تولید workspace با ‏transport جعلی/‏env fallback؛ ‏adapter (فرمت درخواست/پاسخ/خطاها) از قبل در `test_adapters_complete_and_list_models_via_fake_transports` پوشش دارد.
