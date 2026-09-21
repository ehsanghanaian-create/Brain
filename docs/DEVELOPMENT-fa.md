# مستند توسعهٔ SEO Brain

راهنمای فنی برای توسعه‌دهنده‌ای که می‌خواهد روی این پروژه کار کند. آخرین به‌روزرسانی: ۲۰۲۶/۰۹/۱۲ (شهریور ۱۴۰۵).

---

## ۱) پروژه چیست؟

«مغز سئو» برای مجموعه‌ای از سایت‌های وردپرسی: داده‌ها را از **وردپرس** (محتوا + کراول)، **Google Search Console** و **GA4** می‌کشد، گراف دانش می‌سازد، مشکلات و فرصت‌های سئو را تحلیل می‌کند، تولید محتوا با AI و انتشار به وردپرس را مدیریت می‌کند، ترافیک زندهٔ تبلیغات (کلیک‌های Google Ads) را جمع و پایش می‌کند و امکان مسدودسازی IP از طریق پلاگین اختصاصی روی خود سایت‌ها را می‌دهد.

- ریپو: `github.com/ehsanghanaian-create/Brain` — برنچ کاری اصلی: `feat/server-improvements`
- برنچ `ads-data-production`: عکسِ لحظه‌ایِ قدیمی پروداکشن — **هرگز تغییرش ندهید**
- پروداکشن: سرور `185.110.190.125` (پارس‌پک، ‏Ubuntu، ‏Docker) — پنل: `seo.gearboxemdad.com`

## ۲) پشته و ساختار

```
backend/            FastAPI + SQLAlchemy + SQLite (Python 3.11–3.13)
  cli/              نقاط ورود: api.py (uvicorn)، setup.py (env/db/vault)، ads-live-sync.py
  seo_brain/
    api/            main.py (اپ + ثبت روترها + lifespan) و routers/ (هر حوزه یک فایل)
    wordpress/      کلاینت REST وردپرس + orchestrator همگام‌سازی
    crawler/        کراولر صفحات (pages، links، schemas)
    gsc/  ga4/      کلاینت + sync + pipeline (سه‌مرحله‌ای: sync → snapshot/analysis → graph)
    graph/          ساخت و کوئری گراف دانش (graph_nodes/edges + FTS)
    analysis/       تحلیل سئو (seo_problems / seo_opportunities) — impression-weighted
    brain/          keywords، content (تولید/امتیازدهی/تحلیل)، planner، linking
    ads/            guard.py — تشخیص ناهنجاری زندهٔ تبلیغات (detection-only)
    ai/             گیت‌وی چند-Provider ‏(OpenAI/Anthropic/Gemini/Groq/…)، مسیربندی وظیفه→مدل
    automation/     صف job (فایل‌محور) + scheduler (تیک ۱۰ دقیقه)
    integrations/wordpress/  تنها جای مجاز برای نوشتن به بیرون (writer, security)
    common/         config/env، ‏http (ReadOnlyClient + پراکسی)، logging
  mcp_server/       سرور MCP فقط‌خواندنی برای Claude
  tests/            pytest — api/ unit/ integration/ e2e/
frontend/           Next.js 16 (App Router) + TypeScript + Tailwind + shadcn — کاملاً RTL/فارسی
  src/app/          صفحات (dashboard/*، ‏ads-data، ‏api/backend پروکسی، ‏api/ads-data/collect)
  src/features/     ماژول‌های فیچر (sites، keywords، content*، reports، ads-data، ...)
  src/lib/api/client.ts   تنها راه تماس با backend (endpoints + ApiError + settle)
database/migrations/  0001…0017 — شماره‌دار، خودکار در استارت backend اعمال می‌شود
deploy/             Dockerfileهای پروداکشن، ‏Caddyfile.snippet، پلاگین وردپرس، windows-local/
data/               SQLite ها (seo.db اصلی، ads-events.db تله‌متری) + secrets/ (DPAPI)
```

## ۳) راه‌اندازی محیط توسعه (ویندوز)

پیش‌نیاز: Python ‏3.11–3.13 (⚠️ ‏3.14 پشتیبانی نمی‌شود)، ‏Node 18+.

```bash
python -m venv .venv
.venv/Scripts/pip install ./backend
.venv/Scripts/python backend/cli/setup.py --env --db --vault
cd frontend && npm install
```

اجرا (دو ترمینال):

```bash
.venv/Scripts/python backend/cli/api.py            # http://127.0.0.1:8000  (docs: /api/docs)
cd frontend && npm run dev                          # http://localhost:3000
```

- ‏`.env` ریشه: تنظیمات backend (از `.env.example` ساخته می‌شود). فرانت به‌صورت پیش‌فرض backend را روی `127.0.0.1:8000` پیدا می‌کند.
- **پراکسی ضدفیلترینگ:** اگر ISP دامنه‌های سایت‌ها/گوگل را SNI-فیلتر می‌کند، یک تونل SOCKS بزنید و در `.env` بگذارید:
  `ssh -D 127.0.0.1:1080 -N root@185.110.190.125` سپس `WP_PROXY=socks5://127.0.0.1:1080` (سایت‌ها) و `AI_PROXY=...` (سرویس‌های AI). تونل بعد از هر بوت باید دوباره باز شود.

## ۴) قراردادهای مهم (نشکنید!)

1. **Write-guard:** تست `tests/e2e/test_acceptance.py::test_10_no_wordpress_write_paths` کل `seo_brain/` را اسکن می‌کند: هیچ POST/PUT/PATCH/DELETE بیرونی خارج از `integrations/` و `api/` و `dashboard/` مجاز نیست. برای fetch بیرونیِ فقط‌خواندنی از `common/http.py::ReadOnlyClient` استفاده کنید (پراکسی و retry دارد).
2. **Migrations:** فایل جدید = `00NN_name.sql` در `database/migrations/` — شماره‌ها یکتا و مرتب (تست unit دارد). در استارت backend خودکار اعمال می‌شود.
3. **پوزیشن GSC:** همیشه میانگین وزنی با impressions: ‏`SUM(position*impressions)/SUM(impressions)` — هرگز میانگین ساده.
4. **فرانت:** ‏endpoint جدید فقط در `lib/api/client.ts` تعریف شود؛ خطاها `ApiError`؛ صفحات سروری با الگوی `settle()` + `<BackendError/>`؛ اعداد `Intl.NumberFormat('fa-IR')`؛ تاریخ شمسی از `features/content/constants.ts`؛ ‏URL/کد/ID داخل `dir='ltr'`؛ کامپوننت‌های `components/seo-brain/` (KpiCard، ‏EmptyState/LoadingState/ErrorState).
5. **‏site_id در ads:** ‏endpointهای خواندنی ads پیش‌فرض `modirankhodro-emdad.com` دارند؛ کلاینت جدید همیشه صریح بفرستد.
6. **رمزها:** فقط از کارت‌های UI وارد می‌شوند → ‏SecretStore (‏DPAPI روی ویندوز، فایل روی سرور). هرگز در کد/چت/گیت.

## ۵) تست‌ها

```bash
cd backend && ../.venv/Scripts/python -m pytest tests -q     # ‏~215 تست، ~6 دقیقه
cd frontend && npm run test                                   # vitest (54)
cd frontend && npx tsc --noEmit                               # type-check
```

هر فیچر backend یک فایل تست API دارد (الگو: fixture با DB موقت فایل‌محور + `create_app()` + ‏dependency_overrides — نمونه: `tests/api/test_report_center.py`). ایزولاسیون بین سایت‌ها را همیشه تست کنید.

## ۶) زیرسیستم‌ها در یک نگاه

| زیرسیستم | ورودی | جدول‌های کلیدی | ‏API |
|---|---|---|---|
| WordPress sync | REST + کراول | posts، pages، links، schemas | `/sites/{id}/wordpress/sync/*` |
| GSC | ‏Search Analytics | gsc_daily، gsc_query_page، queries | `/sites/{id}/gsc/sync/*` |
| GA4 | ‏Data API | ga4_daily | `/sites/{id}/ga4/sync/*` |
| تحلیل سئو | جدول‌های بالا | seo_problems، seo_opportunities | `/sites/{id}/report/problems|opportunities` |
| گراف | همه | graph_nodes/edges | `/sites/{id}/graph/*` |
| کلمات کلیدی | GSC + دستی | keywords، keyword_opportunities | `/sites/{id}/keywords/*` |
| محتوا/پلنر | AI + GSC | content_items، content_plans، content_metrics | `/sites/{id}/content*`، ‏`/content-plans` |
| گزارش سایت | تجمیع همه | backlinks، reportages (0017) | `/sites/{id}/report` + زیرمسیرها |
| ‏Ads زنده | ‏GTM tag سایت‌ها | ads_click_events (DB جدا: ads-events.db) | `/ads-data/*` |
| امنیت/IP | پلاگین WP ‏v1.2.0 | security_audit | `/sites/{id}/security/*` |
| زمان‌بند | — | sync_runs، site_settings.auto_sync | `/sites/{id}/auto-sync`، ‏`POST /sites/{id}/refresh` |

جریان دادهٔ ads: مرورگر بازدیدکننده → تگ GTM (در `deploy/seo-brain/gtm-tag-*.html`) → `seo.gearboxemdad.com/api/ads-data/collect` (‏Caddy هدرهای IP معتبر می‌گذارد؛ این مسیر **بدون** Basic-Auth است — بلوک `@ads_collector`) → روت Next (‏Origin-check با env ‏`ADS_COLLECTOR_ORIGINS`) → ‏backend (‏allowlist ‏`ADS_COLLECTOR_SITES`) → ‏ads-events.db.

مسدودسازی IP: داشبورد ads → `security/resolve-site` (تقدم canonical_url) → `POST /sites/{id}/security/block` → پلاگین `seo-brain/v1` روی خود سایت (auth = ‏Application Password ادمین؛ ‏WAF بعضی هاست‌ها مسیر users را می‌بندد — تأیید هویت با probe جایگزین انجام می‌شود).

## ۷) استقرار روی سرور (پروداکشن)

منبع حقیقت پروداکشن = **کانتینرهای در حال اجرا**؛ همکار گاهی از ‏working tree ‏`/opt/seo-brain/app` (برنچ قدیمی + تغییرات کامیت‌نشده) ‏build می‌زند — **قبل از هر deploy، پکیج کانتینر را با برنچ diff بگیرید** و تغییرات جامانده را وارد ریپو کنید:

```bash
docker cp seo-brain-backend-1:/usr/local/lib/python3.12/site-packages/seo_brain /tmp/pkg
diff -rq /tmp/pkg <clone>/backend/seo_brain -x __pycache__
```

مراحل deploy (الگوی تست‌شده):
1. کلون تازه در `/opt/seo-brain/builds/<name>` از برنچ.
2. ‏Backup: ‏`compose.production.yaml` + دو DB (با `sqlite backup` روی `runtime-db/seo.db` و `ads-events.db`) در `backups/<name>/`.
3. ‏Build backend: ‏`docker build -f deploy/seo-brain/backend.online.Dockerfile -t seo-brain-backend:<tag> .`
4. ‏Build frontend — **سرور فقط 2GB RAM دارد؛ بدون سقف، کل سرور فریز می‌شود:**
   `DOCKER_BUILDKIT=0 docker build --memory=1500m --memory-swap=3500m ...` + در Dockerfile ‏`ENV NODE_OPTIONS=--max-old-space-size=1200`.
5. سوییچ تگ‌ها در `compose.production.yaml` → ‏`docker compose up -d backend frontend`.
6. ‏Verify: ‏migrations (استارت backend خودکار اعمال می‌کند)، ‏`/ads-data/sites`، ‏summary بدون site_id، ‏`/ads-data/alerts`، صفحهٔ فرانت، ‏**کالکتور باید 202 بدهد** (لاگ caddy)، ‏security resolve.
7. ‏Rollback: تگ قبلی در compose + ‏up -d؛ ‏DBها از backup.

نکات عملیاتی سرور: ‏`/tmp` ‏tmpfs ~1GB است (snapshot بزرگ آنجا نگذارید)؛ فایل‌های کانتینر ممکن است CRLF باشند (قبل از diff نرمال کنید)؛ ‏Caddyfile فعال در `/opt/gearboxemdad/current/ops/Caddyfile` است (نه نسخهٔ repo) و بلوک `@ads_collector` حیاتی است.

## ۸) دردسرهای شناخته‌شده

- **کپی DBِ در حال استفاده خراب می‌شود:** قبل از جایگزینی فایل SQLite، پروسهٔ خواننده را ببندید و **هر سه فایل** ‏`.db` ‏`.db-wal` ‏`.db-shm` را پاک/جایگزین کنید. برای snapshot سازگار: ‏`VACUUM INTO` یا ‏backup API.
- ‏**GSC توکن:** اگر «token refresh failed» دیدید، از UI دوباره Authorize کنید (per-machine است).
- **دیسک C پر می‌شود:** ‏cache های pytest/pip/npm و سطل بازیافت را خالی کنید.
- **پایتون 3.14** نصب است ولی پروژه پشتیبانی نمی‌کند — همیشه `py -3.13` یا venv موجود.

## ۹) نسخهٔ نصبی ویندوز

بستهٔ آفلاین با یک دستور از روی کامیت جاری ساخته می‌شود:

```
powershell -ExecutionPolicy Bypass -File deploy\windows-local\packaging\build-package.ps1            # با دادهٔ اولیه (seed)
powershell -ExecutionPolicy Bypass -File deploy\windows-local\packaging\build-package.ps1 -NoSeed    # بستهٔ تمیز برای دیگران
```

خروجی در `D:\seo-brain-dist`: ‏`SEO-Brain-Setup-<date>.exe` (ویزارد تک‌فایلی: stub سی‌شارپِ `packaging/Setup.cs` + ‏ZIP چسبیده به انتهای EXE) و ‏`SEO-Brain-Portable-<date>.zip` (همان فایل‌ها + ‏`INSTALL.bat`). داخل بسته: ‏Node پرتابل، نصب‌کنندهٔ رسمی Python 3.12، ‏wheelهای بک‌اند برای cp312 و cp313 (`runtime\wheels` ← ‏`pip --no-index`)، رابط وبِ ازپیش‌ساخته (`frontend-standalone` = ‏Next standalone، بدون `npm install`/build روی مقصد) و در صورت نیاز `seed\*.db`.
اسکریپت‌های زمان نصب/اجرا: ‏`installer\install.ps1` (venv + نصب آفلاین + seed + migrate + میان‌برها)، ‏`start.ps1` (بک‌اند + ‏`node frontend-standalone\server.js` روی 127.0.0.1)، ‏`stop.ps1`، ‏`uninstall.ps1`. نصب بی‌صدا برای تست: ‏`Setup.exe /silent /dir=D:\some-folder /noshortcut /nolaunch /noregistry` (لاگ در `run\setup.log`).
فایل‌های Node/Python باید در `D:\seo-brain-dist\runtime` باشند (`node-v*-win-x64.zip` و `python-3.*-amd64.exe`).
