# پژوهش مخزن‌های متن‌باز برای معماری SEO Brain — ۱۸ مهر ۱۴۰۵

## هدف و دامنه

این سند فهرست قبلی را نگه می‌دارد و مخزن‌های **محصولی و معماری** نزدیک به SEO Brain را به آن اضافه می‌کند. بررسی در ۱۰ اکتبر ۲۰۲۶ بر پایهٔ README، اسناد معماری، ساختار مخزن و فرادادهٔ GitHub انجام شده است. ادعاهای قابلیت و مقیاس، جز در مواردی که سند فنی یا کد مشخص بررسی شده، ادعای سازندهٔ مخزن هستند؛ نصب، آزمون بار و آزمون دادهٔ واقعی انجام نشده است. تعداد ستاره، تضمین کیفیت یا آماده‌بودن برای تولید نیست.

پژوهش [مدیریت پروژهٔ قبلی](./project-management-research-2026-10-05.md) برای Plane، OpenProject، Leantime و Vikunja همچنان معتبر است. این سند به جای تکرار آن، بر اتصال دادهٔ سئو به کار تیم تمرکز دارد. جست‌وجو با موضوع‌های SEO، audit، rank tracking، GSC، AI visibility و multi-site انجام شد؛ «همهٔ مخزن‌های GitHub» به معنای لفظی قابل احصا نیست، بنابراین این یک فهرست ارزیابی‌شده و قابل گسترش است.

## تصویر فعلی SEO Brain

طبق [README پروژه](../../README.md)، هستهٔ موجود Python/FastAPI، Next.js، SQLite، شناسهٔ `site_id`، خزندهٔ آگاه از robots، همگام‌سازی WordPress/GSC/GA4، گراف لینک و موجودیت، تحلیل سئو، برنامهٔ محتوا، MCP و `work_items` دارد. `gsc_daily` مشاهدهٔ عملکرد با بُعدهای تاریخ/صفحه/کوئری/کشور/دستگاه است؛ `ga4_daily` مسیر صفحه و منبع را نگه می‌دارد؛ [صف گزارش](../../backend/seo_brain/api/routers/reports.py) ماهانه، صفحه و کوئری را از دادهٔ موجود می‌سازد. [صف اجرای کار](../../backend/seo_brain/automation/queue.py) یک صف ماندگار مبتنی بر فایل دارد که برای یک پردازه مناسب است. [انتساب تماس](../../backend/seo_brain/call_center/attribution.py) نیز شواهد کلیک تماس را با برچسب «احتمالی» ثبت می‌کند و در ابهام منبع را `unknown` می‌گذارد. این‌ها سرمایهٔ موجودند و نباید با ورود یک محصول خارجی کنار گذاشته شوند.

در مرور کد، ماژول مشخصی برای **رتبه‌سنجی مستقل SERP**، پایش سراسری **Core Web Vitals** و **پروفایل بک‌لینک رقبا** دیده نشد. این گزاره نتیجهٔ مرور ایستا است، نه آزمون تمام مسیرهای اجرا. مهم‌تر از افزودن سه نمودار، اکنون دادهٔ مشاهده‌شده، منشأ، پوشش، مسئله، تصمیم تیم و نتیجهٔ پس از اجرا در یک مدل یکنواخت به هم وصل نیستند. این شکاف با یافتهٔ پژوهش مدیریت پروژه دربارهٔ baseline و اتصال تسک به KPI هم‌راستاست.

## مخزن‌های محصولی که بیشترین شباهت را دارند

«اولویت» یعنی ارزش مطالعه یا نمونه‌سازی برای معماری ما، نه دستور کپی کد. وضعیت مجوز از GitHub در روز بررسی خوانده شده؛ برای برداشت مستقیم کد باید فایل LICENSE همان نسخه و وابستگی‌ها جدا بازبینی شوند.

| مخزن | ارزش مشخص برای SEO Brain | محدودیت/وضعیت | اولویت |
| --- | --- | --- | --- |
| [OpenSEO](https://github.com/every-app/open-seo) | مجموعهٔ نزدیک به Ahrefs/Semrush: تحقیق کلمه، رتبه، رقبا، بک‌لینک، audit، AI visibility، MCP؛ تصمیم‌های معماری ثبت‌شده دربارهٔ خزیدن، منبع داده و داشبورد | MIT؛ وابسته به DataForSEO برای بسیاری از داده‌ها؛ معماری Cloudflare/TypeScript عیناً مناسب FastAPI ما نیست | **۱: مرجع محصول و معماری** |
| [RankMeFast](https://github.com/SelmiAbderrahim/rankme.fast) | audit، rank، GSC/GA4، CrUX، بک‌لینک، محتوا، گزارش؛ رابط مستقل برای هر provider، نمونهٔ بدون کلید، «Next Actions» | AGPL-3.0؛ بتای عمومی؛ MongoDB/Postgres و چند سرویس | **۱: مرجع قرارداد داده و اقدام** |
| [Ansvisor](https://github.com/ansvisor/ansvisor) | اتصال سیگنال‌های سئو و AI search به Action Center، صف کاندیدا، وظیفه و نتیجه؛ مقایسهٔ prompt/پلتفرم | MIT؛ حوزهٔ AI visibility پرنوسان؛ برخی ادعاهای اثرگذاری در docs نیازمند شواهد مستقل‌اند | **۱: مرجع چرخهٔ سیگنال تا اقدام** |
| [CrawlSEO](https://github.com/crawlseo/crawlseo) | الگوی صفحهٔ سادهٔ GSC + crawl + CWV + MCP؛ مناسب مقایسهٔ تجربهٔ کاربری و صفحهٔ سلامت | MIT؛ سقف خزیدن ادعایی ۲۰۰۰ صفحه؛ محصول جوان‌تر از OpenSEO | **۱: مرجع UX و دادهٔ صفحه** |
| [Bisibility](https://github.com/CorgiCorner/bisibility) | rank history، keyword/backlink research، share of voice و context از GSC/GA4؛ worker/Temporal برای چک‌های دوره‌ای | AGPL-3.0؛ README می‌گوید قرارداد ۱.۰ پایدار نیست؛ Temporal برای مقیاس فعلی ما سنگین است | ۲ |
| [OpenGSC](https://github.com/fenjo26/OpenGSC) | داشبورد چند سایت/چند موتور، GSC، GA4، crawl، index inspection و MCP؛ اسناد معماری روشن برای SQLite و کارهای پس‌زمینه | MIT؛ مجموعهٔ بسیار بزرگ و در حال تغییر؛ ماژول «Private Indexer» و cloaking در معماری آن با مسیر محصول ما سازگار نیست؛ کارهای in-process با restart قطع می‌شوند | ۲، فقط الگوهای منتخب |
| [SEO Panel](https://github.com/seopanel/Seo-Panel) | نمونهٔ قدیمی و نسبتاً کامل برای inventory ابزارها و گزارش مشتری | GPL-2.0، PHP، الگوهای معماری قدیمی؛ برای پشتهٔ ما مرجع اجرایی نیست | ۳ |
| [seo-os](https://github.com/AgriciDaniel/seo-os) | ایدهٔ workspace آژانسی و گردش کار عامل‌های AI | AGPL-3.0 و آزمایشی؛ رابط و ادعاها باید مستقل سنجیده شوند | ۳ |
| [RosterSEO](https://github.com/open-saas-org/RosterSeo) | ایدهٔ اتصال SEO، انتشار، AI visibility و دادهٔ کسب‌وکار | MIT، مخزن بسیار جوان با شواهد پذیرش کم؛ بیشتر watchlist | ۳ |

## مخزن‌های تخصصی و نقش دقیق آن‌ها

| لایه | مخزن‌های منتخب | الگوی مورد استفاده / احتیاط |
| --- | --- | --- |
| خزنده و audit | [SiteOne Crawler](https://github.com/janreges/siteone-crawler) (MIT)، [GoCrawl](https://github.com/Patience-dot-devl/gocrawl) (MIT)، [CrawlObserver](https://github.com/SEObserver/crawlobserver) (AGPL-3.0) | خروجی ساخت‌یافتهٔ crawl، اجرای CLI/worker، ثبت علت indexability، مقایسهٔ crawlها؛ اول با خزندهٔ فعلی تطبیق دهیم. GoCrawl بسیار جوان است. |
| CWV و رگرسیون | [Unlighthouse](https://github.com/harlan-zw/unlighthouse) (MIT)، [Lighthouse CI](https://github.com/GoogleChrome/lighthouse-ci) (Apache-2.0)، [Lighthouse](https://github.com/GoogleChrome/lighthouse) (Apache-2.0) | نمونه‌گیری سایت و آزمون رگرسیون در انتشار؛ lab score را با CrUX field data یکی ننامیم. |
| رتبهٔ مستقل | [SerpBear](https://github.com/towfiqi/serpbear) (MIT) | تاریخچهٔ رتبه در geo/device/engine مشخص؛ GSC average position را با مشاهدهٔ مستقیم SERP ادغام عددی نکنیم. |
| تحلیل GSC و پورتفولیو | [Site Analytics](https://github.com/jafforgehq/site-analytics-tool) (MIT)، [OpenGSC](https://github.com/fenjo26/OpenGSC) | پوشش داده، تاریخ آخرین sync، هشدار stale، مقایسهٔ ماهانه؛ Site Analytics تک‌مدیر و بسیار جوان است. |
| audit مبتنی بر شواهد | [Houtini SEO Audit](https://github.com/houtini-ai/seo-audit) (Apache-2.0)، [SEO Audit Skill](https://github.com/seo-skills/seo-audit-skill) (MIT) | شروع crawl از URLهای GSC در کنار sitemap/لینک، اتصال یافته به کلیک صفحه، تفکیک چک قطعی از قضاوتی؛ مجموعهٔ قواعد برای طبقه‌بندی، نه واردکردن بی‌بررسی تمام ruleها. |
| AI search | [Ansvisor](https://github.com/ansvisor/ansvisor) (MIT)، [Aperture](https://github.com/anyin-ai/aperture) (MIT) | ثبت prompt، پاسخ، citation URL، مدل/پلتفرم، زمان و نمونهٔ خام؛ امتیاز visibility با مجموعهٔ prompt ثابت و برچسب عدم قطعیت. Aperture جوان است. |
| گزارش و BI | [Metabase](https://github.com/metabase/metabase) (مجوز ترکیبی)، [Client Reporter](https://github.com/coysh-digital/client-reporter) (MIT) | گزارش قابل فیلتر مدیر/مشتری و قالب خروجی؛ Metabase را سرویس جداگانه ببینیم و فقط پس از تعریف مدل دادهٔ قابل اتکا. Client Reporter در v0.1 است. |
| ارزیابی AI | [Langfuse](https://github.com/langfuse/langfuse) (هستهٔ MIT با پوشه‌های تجاری) | trace، هزینه، prompt version و ارزیابی خروجی AI؛ دادهٔ سایت و رمزها نباید بی‌قرارداد به سرویس ثالث بروند. |
| مدیریت کار | [Plane](https://github.com/makeplane/plane)، [OpenProject](https://github.com/opf/openproject)، [Leantime](https://github.com/Leantime/leantime)، [Vikunja](https://github.com/go-vikunja/vikunja) | جزئیات در [پژوهش مستقل](./project-management-research-2026-10-05.md)؛ «تسک» باید در هستهٔ خودمان به شواهد SEO متصل شود. |

## یافته‌های معماری که ارزش انتقال دارند

### ۱. دادهٔ خارجی پشت قرارداد توانایی، نه داخل صفحهٔ محصول

[قرارداد provider در RankMeFast](https://github.com/SelmiAbderrahim/rankme.fast/blob/master/server/src/shared/providers/README.md) خروجی منبع را پیش از رسیدن به feature نرمال می‌کند؛ آزمون قرارداد برای موفقیت، timeout، پاسخ خراب و quota دارد. [قاعدهٔ رابط‌ها](https://github.com/SelmiAbderrahim/rankme.fast/blob/master/.claude/rules/provider-interfaces.md) نیز از fallback ساکت به دادهٔ ساختگی جلوگیری می‌کند. برای SEO Brain، `SearchPerformanceSource`، `SerpRankSource`، `PageExperienceSource`، `BacklinkSource` و `AiAnswerSource` با shape داخلی، `source`, `observed_at`, `fetched_at`, `coverage`, `cost`, `error_code` پیشنهاد می‌شود. GSC و GA4 موجود اولین adapterها هستند. نمونهٔ fake فقط برای demo/test است و باید صریح علامت بخورد.

[تصمیم routing در OpenSEO](https://github.com/every-app/open-seo/blob/main/docs/maintainers/specs/0004-keyword-data-source-routing.md) نشان می‌دهد پوشش جغرافیا، مقدار null برای فیلد ناموجود و هزینهٔ هر درخواست باید بخشی از قرارداد باشد. قیمت‌های آن سند تاریخی و مخصوص provider همان پروژه‌اند؛ بودجهٔ SEO Brain باید با نرخ و قرارداد واقعی خودمان محاسبه شود.

### ۲. crawl به صورت run قابل بازیابی با پوشش معلوم

[معماری crawl در OpenSEO](https://github.com/every-app/open-seo/blob/main/docs/maintainers/specs/0009-site-audit-crawl-architecture.md) وضعیت frontier، صفحات و مشکل‌ها را از orchestrator جدا کرده، URL را با کلید پایدار dedupe می‌کند، کارها را chunk می‌زند، شکست را طبقه‌بندی می‌کند و نتیجهٔ جزئی را نمایش می‌دهد. برای SEO Brain، پیاده‌سازی فعلی Python می‌تواند همین ناورداها را در SQLite/worker محقق کند؛ انتقال Durable Object/Cloudflare لازم نیست. دادهٔ `crawl_run` باید تعداد URL کشف‌شده/بررسی‌شده/ناموفق، درصد پوشش، seed source، مدت، robots status و دلیل شکست را داشته باشد. مسئلهٔ «نبود صفحه» فقط پس از crawl کامل و موفق صادر شود.

[Houtini](https://github.com/houtini-ai/seo-audit) سه منبع discovery را به هم می‌رساند: لینک داخلی، sitemap و URLهای GSC. نتیجهٔ منطقی برای ما: صفحه‌ای که کلیک دارد ولی در لینک‌ها یا sitemap نیست باید در inventory دیده شود، همراه با شواهد منشأ؛ «orphan» بودن با پوشش ناقص crawl یک **کاندیدا** است، نه حکم قطعی. برچسب deterministic/heuristic برای ruleها از همین الگو می‌آید.

### ۳. مشاهده، مسئله، تصمیم و تسک چهار موجودیت متفاوت‌اند

[Next Actions در RankMeFast](https://github.com/SelmiAbderrahim/rankme.fast/blob/master/docs/next-actions.en.md) دادهٔ audit، رتبه، GSC و محتوا را در یک صف قرار می‌دهد؛ Plan/Dismiss/Complete/Reopen تاریخچه دارد و dismiss اصل audit را پاک نمی‌کند. [صف کاندیدا در Ansvisor](https://github.com/ansvisor/ansvisor/blob/main/server/src/lib/action-center/candidates.js) «چه یافتیم؟» را از «الان چه اقدامی ترویج شود؟» جدا می‌کند تا یافتهٔ تازه، زیر تسک باز قبلی ناپدید نشود. این تفکیک مستقیماً مشکل قاطی شدن کارهای افراد با داده‌های گزارش را حل می‌کند: مشاهده و مسئله مشترک پروژه‌اند؛ تسک مالک و مجری، سطح دسترسی و تاریخچهٔ خود را دارد.

مدل پیشنهادی:

```text
source_run + raw_reference
   → observation(site, entity, metric, period, dimensions, source, freshness, coverage)
   → finding(rule, entity, severity, confidence, evidence[], first_seen, last_seen, state)
   → action_candidate(finding_ids[], impact, effort, decision_history)
   → work_item(existing id, assignee, creator, site, due, status)
   → verification(before_snapshot, after_snapshot, window, result, uncertainty)
   → report(site/team/client; links to evidence and owner)
```

یک finding پایدار با کلید `(site_id, rule_id, canonical_url/query/market)` و رویدادهای first/last seen ساخته می‌شود؛ runهای بعدی آن را به‌روزرسانی می‌کنند، بی‌آنکه تاریخچهٔ اصل مشاهده پاک شود. تسک می‌تواند چند یافته را حل کند و یک یافته می‌تواند چند تسک داشته باشد، اما عضویت و مجوز هر site باید در API هم چک شود. «کار تمام شد» نتیجهٔ SEO نیست؛ verification ممکن است `improved`, `unchanged`, `worse`, `insufficient_data` یا `not_due_yet` باشد. نتیجهٔ کسب‌وکار، مانند تماس ثبت‌شده، فقط با منبع و درجهٔ اطمینان خودش کنار KPIهای سئو می‌آید؛ نسبت‌دادن یک تماس احتمالی به یک تسک مشخص، ادعای علّی قابل دفاع نیست.

### ۴. عددها باید معنای دقیق و زمان مشاهده داشته باشند

[داشبورد وب‌سایت OpenSEO](https://github.com/every-app/open-seo/blob/main/docs/maintainers/specs/0015-website-dashboard.md) متوسط جایگاه GSC را صریحاً از رتبهٔ زنده جدا می‌کند، نتیجهٔ خالی را cache می‌کند، refresh را با هزینهٔ provider کنترل می‌کند و در عوض stale بودن را نشان می‌دهد. [RankMeFast برای افت رتبه](https://github.com/SelmiAbderrahim/rankme.fast/blob/master/docs/confirmed-rank-alerts.en.md) هشدار را پس از مشاهدهٔ دوم در همان بازار تأیید می‌کند و volatile/unconfirmed را جدا نگه می‌دارد. نمودار SEO Brain باید `metric_definition`, `source`, `date_range`, `market`, `device`, `last_sync`, `data_coverage` و baseline یکسان داشته باشد. نام «لایو» فقط برای دادهٔ واقعاً لحظه‌ای مجاز است؛ GSC/GA4 sync شده snapshot تاریخی‌اند.

### ۵. گزارش مدیریتی از مدل واحد، با drill-down و حفظ امنیت

[گزارش‌های OpenSEO](https://github.com/every-app/open-seo/blob/main/docs/maintainers/specs/0012-dynamic-reports.md) مالک پروژه، انتساب نویسنده، فهرست سبک بدون بارگیری HTML و viewer محدودشده دارند. برای SEO Brain، ابتدا گزارش ساخت‌یافته از `observation/finding/work_item/verification` لازم است: مدیر با یک کلیک از روند سایت به مسئله، تسک، مسئول و گفتگو برسد؛ گزارش هفتگی/ماهانه با یک تعریف KPI و یک منبع داده ساخته شود. خروجی HTML/PDF مرحلهٔ بعد است؛ محتوای تولیدی AI باید sandbox شود.

## ترتیب پیشنهادی تصمیم و نمونه‌سازی

| گام | خروجی قابل سنجش | مخزن مرجع |
| --- | --- | --- |
| ۰. ممیزی و baseline | inventory جدول‌ها/APIها، دو سایت آزمایشی، تعریف URL canonical، شمارش دادهٔ واقعی و stale/coverage؛ تأیید اینکه کدام قابلیت واقعاً غایب است | SEO Brain + CrawlSEO |
| ۱. مدل مشاهده/یافته | migration افزایشی، adapter برای GSC/GA4/crawl موجود، کلید پایدار finding، provenance و دو rule نمونه؛ بدون ورود vendor پولی | RankMeFast + Houtini + OpenSEO |
| ۲. پیوند کار تیم | ساخت action candidate از یافته، اتصال به `work_items` و دسترسی سایت، تاریخچهٔ تصمیم، صف «نیازمند اقدام/در کار/نیازمند تأیید/رفع‌شده» | Ansvisor + RankMeFast + Plane |
| ۳. بازآزمایی و اثر | snapshot قبل/بعد و بازهٔ انتظار برای GSC/GA4، تفکیک تحویل از اثر، تأیید مدیر بر شواهد | OpenSEO + RankMeFast |
| ۴. قابلیت‌های بیرونی منتخب | پایش رتبهٔ مستقل با market/device، CWV دوره‌ای، بک‌لینک/رقبا تنها بعد از بودجه و قرارداد provider | SerpBear + Unlighthouse + OpenSEO |
| ۵. پورتفولیو و گزارش | نمای چند سایت با پوشش و ریسک، drill-down به مسئول و task، قالب گزارش مشتری، BI اختیاری | Site Analytics + Metabase + OpenSEO |
| ۶. AI visibility | prompt set ثابت، raw citations و پاسخ، نرخ نمونه‌گیری و عدم قطعیت، فقط پس از تثبیت مدل مشاهده | Ansvisor + Aperture |

برای هر گام، معیار عبور: خروجی با دادهٔ واقعی دو سایت بازتولید شود، دادهٔ ناقص/قدیمی با برچسب روشن دیده شود، دوبار اجرای job finding/تسک تکراری نسازد، و کاربر سایت A نتواند دادهٔ سایت B را از API بخواند یا تغییر دهد. پیش از بالا بردن شمار site/job، صف فایل‌محور یک‌پردازهٔ فعلی با بار و restart آزمایش و در صورت نیاز با worker/queue مناسب جایگزین شود.

## تصمیم دربارهٔ استفاده از کد دیگران

**الگوها و قراردادها** از OpenSEO، RankMeFast، Ansvisor و بقیه برای طراحی داخلی SEO Brain استفاده می‌شوند. کپی مستقیم کل مخزن یا واردکردن سرویس بزرگ، مسیر منتخب نیست؛ پشتهٔ فعلی، دادهٔ محلی، RTL فارسی و مدیریت تیم بومی مزیت‌های محصول ما هستند. کد MIT/Apache هم به بررسی notice و وابستگی نیاز دارد؛ AGPL/GPL و مجوزهای ترکیبی پیش از هر استفادهٔ کدی به بررسی حقوقی و معماری جدا نیاز دارند. هیچ دادهٔ ساختگی یا capability نوشته‌شده در README به عنوان قابلیت عملیاتی SEO Brain گزارش نخواهد شد.
