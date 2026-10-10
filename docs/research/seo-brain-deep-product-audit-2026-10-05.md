# پژوهش عمیق دوم SEO Brain: دادهٔ قابل ردیابی، گراف، داشبورد و دردهای حل‌نشده

تاریخ بررسی: ۱۳ مهر ۱۴۰۵ / ۵ اکتبر ۲۰۲۶
مبنای محصول: نسخهٔ محلی شاخهٔ `codex/gentelella-integration`
پیوست به: [پژوهش شکاف](seo-brain-product-gap-2026-10-04.md)، [پایش بازار و انجمن‌ها](seo-brain-superplatform-landscape-2026-10-04.md)، [طرح اجرایی](../plans/seo-brain-progress-dashboard-2026-10-05.md)

## روش و سطح اطمینان

این دور، مستندات رسمی Google و سازندگان ابزارها، GitHub issue/discussion، گفتگوهای عمومی Reddit و چند پست عمومی X را با مسیرهای واقعی کد مقایسه می‌کند. جست‌وجوی وب و خواندن مستندات **اثبات کیفیت ابزار رقیب یا فراوانی مشکل در کل بازار نیست**. صفحات محصول، قابلیت ادعایی را نشان می‌دهند؛ مسئله‌های انجمنی فقط فرضیه برای مصاحبه‌اند. هیچ جست‌وجوی کنترل‌شدهٔ رتبه برای سایت مشتری، ورود به GSC واقعی مشتری، آزمایش provider پولی یا مصاحبهٔ تیم در این مرحله انجام نشده است.

برچسب شواهد این سند: **رسمی** = تعریف/محدودیت API یا مستندات سازنده؛ **کد** = رفتار فعلی Brain؛ **نشانهٔ کاربر** = گفتگو/issue عمومی؛ **پیشنهاد** = استنتاج و طراحی که باید آزمایش شود. برای هر قابلیت، منبع، سطح داده، کیفیت، علت پیشنهاد و معیار آزمون نگه داریم.

### خط پایهٔ دیتابیس محلی در همین بررسی

از `data/seo.db` در حالت **read-only** فقط شمارش و وضعیت اجرا خوانده شد؛ دادهٔ تماس/شخصی یا توکن نمایش داده نشد. این snapshot شامل **۱ سایت** (`salimore`)، **۲۸۶ ردیف محتوای WordPress**، **۲۰ صفحهٔ خزیده‌شده**، **۵۵ مسئلهٔ SEO** و **۵۲۹ گرهٔ گراف** بود. جدول‌های `gsc_daily`، `ga4_daily`، `call_center_calls` و `seo_opportunities` همگی **صفر ردیف** داشتند. سه اجرای آخر crawl با وضعیت `completed_capped` و سقف ۲۰ URL ثبت شده‌اند. پس با دادهٔ محلی کنونی نه روند ماهانهٔ واقعی GSC/GA4، نه انتساب تماس و نه پوشش همهٔ صفحات یک سایت قابل آزمون است. این «صفر ردیف محلی» نشانهٔ صفر بودن ترافیک/تماس واقعی آن کسب‌وکار نیست و نمایندهٔ سایت‌های آیندهٔ محصول هم نیست.

## نتیجهٔ اصلی

فرصت SEO Brain در تعداد کارت یا زیبایی موشن نیست. ارزش قابل دفاع در یک «دفتر تصمیم و نتیجه» است که بتواند از **URL/عبارت/منشأ داده → فرضیه و اولویت → مسئول/تغییر/انتشار → اثر مشاهده‌شده → تماس/سفارش** را بدون گم‌شدن بین ابزارها ردیابی کند. ابزارهای بزرگی هر کدام بخشی از زنجیره را قوی انجام می‌دهند. Brain هم اکنون تکه‌های WordPress، GSC، GA4، خزش، گراف، محتوا، تماس و Ads را دارد؛ اما هویت مشترک صفحه، خط زمانیِ مسئله و اقدام، و سنجهٔ قابل بازتولیدِ کل سایت هنوز کامل نیستند. این نتیجه از [کد گزارش](../../backend/seo_brain/api/routers/reports.py)، [نمای گراف](../../backend/seo_brain/graph/views.py)، [مدل تماس](../../database/migrations/0021_call_center.sql) و پژوهش‌های قبلی به دست آمده است.

## بنچمارک قابلیت‌ها: از بازار چه می‌آموزیم؟

| دسته و مرجع رسمی | چیزی که نشان می‌دهد | ترجمهٔ دقیق برای Brain | تصمیم |
|---|---|---|---|
| [Semrush Position Tracking](https://www.semrush.com/kb/32-position-tracking) و [Rankings Distribution](https://www.semrush.com/kb/550-position-tracking-rankings-distribution) | پایش روزانهٔ کلمات هدف، شهر/دستگاه، رقیب، گروه و توزیع Top 3/10/20/100 | GSC برای کلیک و رفتار واقعی؛ پایش مستقل SERP برای فهرست محدودِ هدف با مکان/دستگاه ثابت | اتصال provider پس از آزمون هزینه/پوشش فارسی؛ منطق هدف و گزارش را خودمان بسازیم |
| [Semrush Keyword Gap](https://www.semrush.com/kb/28-keyword-gap) و [Cannibalization](https://www.semrush.com/kb/1066-position-tracking-cannibalization-report) | اشتراک/شکاف رقیب و جابه‌جایی صفحهٔ رتبه‌گیر برای یک عبارت | ماتریس query↔URL، تغییر landing برنده، تشخیص «نامزد cannibalization» با بازبینی انسانی | منطق تحلیل در Brain؛ دادهٔ رقیب از provider |
| [Ahrefs Site Audit compare](https://help.ahrefs.com/en/articles/5192078-how-to-compare-changes-between-two-crawls-in-site-audit) و [Always-on](https://help.ahrefs.com/en/articles/10957674-how-always-on-audit-works) | مقایسهٔ دو خزش، مشکل تازه/رفع‌شده، بازخزش صفحهٔ مهم | snapshot نسخه‌دار crawl، تغییرات title/canonical/noindex/status، اولویت بازخزش بر اساس ارزش صفحه | ساخت تدریجی روی خزندهٔ موجود |
| [Conductor Monitoring](https://www.conductor.com/platform/monitoring/) و [alerting](https://www.conductor.com/platform/features/real-time-alerting/) | پایش پیوسته، changelog و هشدار متناسب با بخش/مسئول | هشدارهای مهمِ سایت و URL، با provenance و مسیریابی به مسئول؛ جلوگیری از هشدارهای تکراری | ساخت قواعد و workflow؛ برای مقیاس عظیم امکان اتصال |
| [Sitebulb Crawl Maps](https://sitebulb.com/product/crawl-maps/) و [تعریف شش نما](https://support.sitebulb.com/en/articles/9887437-site-visualisations) | جداکردن نقشهٔ لینکِ واقعی از ساختار پوشه‌ای و نمایش عمق/انزوا | گراف فعلی را با نماهای «مسیر خزش»، «دایرکتوری» و «موضوع/کار» تکمیل کنیم؛ هر edge معنی و منبع داشته باشد | ساخت روی گراف موجود |
| [Botify LogAnalyzer](https://www.botify.com/platform/visibility/loganalyzer-feature) | مشاهدهٔ درخواست واقعی bot در log | در سایت بزرگ، log واقعی را کنار خزش خودمان بگذاریم تا «گوگل واقعاً چه دیده» معلوم شود | واردکنندهٔ log اختیاری، نه الزام همهٔ سایت‌ها |
| [Clearscope Inventory](https://www.clearscope.io/support/getting-started-content-inventory) و [Content Views](https://www.clearscope.io/support/content-views) | موجودی متصل به GSC، فیلترهای ذخیره‌شده، بازبینی دوره‌ای، annotation | صف refresh محتوای منتشرشده، owner، تاریخ بعدی بازبینی، فیلترهای قابل اشتراک | ساخت داخلی با دادهٔ موجود |
| [MarketMuse Topic Authority](https://help.marketmuse.com/support/solutions/articles/80001167736-personalized-difficulty-and-topic-authority) | فرصت بر اساس قدرت موضوعی خود سایت، نه فقط حجم کلمه | اولویت محتوا را با پوشش خوشه، صفحات پشتیبان و ارزش کسب‌وکار تنظیم کنیم؛ فرمول شفاف و قابل اعتراض | مدل محلی آزمایشی، نه تقلید نمرهٔ proprietary |
| [SEOmonitor Objective Status](https://help.seomonitor.com/en/articles/6478757-objective-status-tracking) و [Forecast](https://help.seomonitor.com/en/articles/6615822-forecast-overview) | actual در برابر هدف و سناریوی فرضی تا سشن/تبدیل/درآمد | goal tree برای هر سایت، سناریوی خوش‌بینانه/میانه/بدبینانه با مفروضات و بازهٔ عدم قطعیت | بسازیم؛ forecast پس از دادهٔ معتبر |
| [AgencyAnalytics annotations](https://agencyanalytics.com/features/custom-comments) و [client portal](https://agencyanalytics.com/features/agency-client-portals) | گزارش چندکاناله با توضیح رویداد روی نمودار و نمای مشتری | روایت مدیریتی و ثبت تاریخ تغییر، Ads و call در کنار SEO؛ مجوز دید مشتری | UI و شرح انسانی بسازیم؛ white-label دیرتر |
| [Ahrefs Brand Radar](https://help.ahrefs.com/en/articles/11064852-what-is-brand-radar-and-how-to-use-it) | prompt/mention/citation و مقایسه با رقیب با نمونه‌گیری مشخص | پنل آزمایشی promptهای ثابت، پاسخ خام، مدل/تاریخ/مکان؛ گزارش جدا از دادهٔ رسمی Google | نمونه‌گیری محدود و شفاف؛ provider اختیاری |
| [Google Search Console Generative AI report](https://support.google.com/webmasters/answer/16984139?hl=en) | از ۳۱ اوت ۲۰۲۶ گزارش رسمی نمایش در AI Overviews/AI Mode؛ ابعاد صفحه/کشور/دستگاه/تاریخ، **فقط impression** | ورودی دستی CSV با provenance و تاریخ در کوتاه‌مدت؛ اتصال برنامه‌ای فقط پس از آزمون روی property واقعی | اولویت جدید؛ availability، دسترسی API و اختلاف با Web را تست کنیم |

این جدول «امکان تقلید همهٔ ویژگی‌ها» نیست. دادهٔ جهانی رقیب/بک‌لینک/SERP و خزش وب‌مقیاس شبکه و هزینهٔ خاص می‌خواهد. هستهٔ مالکیت Brain باید **هویت، شواهد، اقدام، سنجش و گزارش فارسیِ متناسب با نوع کسب‌وکار** باشد.

## دردهایی که از مقایسه و گفتگوهای واقعی بیرون آمدند

| درد کاربر / شاهد | چرا با داشبورد معمول حل نمی‌شود | فرصت قابل‌آزمون برای Brain |
|---|---|---|
| ابزارهای گزارش، کار و تقویم جدا می‌شوند؛ یک [بحث چندمشتری در r/SEO](https://www.reddit.com/r/SEO/comments/1sephya/how_are_you_guys_handling_seo_content_work/) ترکیب Looker، Notion و Sheet را شرح می‌دهد | ردیف گزارش به owner و نتیجهٔ وظیفه وصل نیست | هر افت/فرصت یک پروندهٔ دارای تصمیم، مالک، موعد، انتشار و بازبینی نتیجه داشته باشد |
| [درخواست گزارش مدیریتی](https://www.reddit.com/r/SEO/comments/1vbvl5b/how_do_you_report_seo_results_to_a_new_client/) به نتیجهٔ تجاری و توضیح «قبل، اقدام، بعد» اشاره دارد | انبوه نمودار رتبه برای مدیر به تصمیم منجر نمی‌شود | دو سطح گزارش: مدیر ۵ سؤال و اقدام بعدی؛ متخصص drill-down کامل |
| [بحث انتساب SEO به تماس/درآمد](https://www.reddit.com/r/SEO/comments/1g88wtv) دشواری جداکردن تبلیغ/برند/تماس را نشان می‌دهد | کلیک روی شماره تماسِ برقرارشده نیست؛ تاریخ‌ها و هویت‌ها گم می‌شوند | دفتر انتساب با SEO/Ads/unknown، دلیل، confidence، dedupe و نتیجهٔ تماس؛ آزمایش روی نمونهٔ واقعی |
| [مشکل اختلاف Looker و GSC](https://www.reddit.com/r/LookerStudio/comments/1lxg5aj) و [راهنمای رسمی تجمیع Google](https://support.google.com/webmasters/answer/17011364?hl=en) | گزارش property و page/query با قواعد شمارش یکسان نیست | metric contract، tooltip منشأ و سطح تجمیع؛ reconciliation با توضیح اختلاف |
| [محدودیت رسمی GSC API](https://developers.google.com/webmaster-tools/v1/searchanalytics/query) | صفحه‌بندی، همهٔ queryها را برنمی‌گرداند؛ «نبود ردیف» صفر واقعی نیست | coverage، top-row bias، status `partial/unknown` و BigQuery برای سایت حجیم |
| [پاسخ Ahrefs دربارهٔ پیشنهاد لینک](https://help.ahrefs.com/en/articles/4662024-why-can-t-i-see-any-all-link-opportunities) | پیشنهادهایش به ۱۰ query برتر هر صفحه و سقف ۱۰هزار و تطابق دقیق عبارت محدود است | پیشنهاد لینک Brain با entity/intent/هدف تجاری و شاهدِ جمله، همراه کنترلِ لینک موجود و دلیل ندادن پیشنهاد |
| [پاسخ Ahrefs دربارهٔ orphanهای کاذب](https://help.ahrefs.com/en/articles/4756073-why-are-my-pages-being-reported-as-orphan-pages-when-they-are-not) | URL یافت‌شده از sitemap می‌تواند بدون مسیر داخلی دیده شود؛ پوشش crawl روی نتیجه اثر دارد | «یتیم در خزش مشاهده‌شده» با منشأ/پوشش، نه حکم قطعی دربارهٔ کل سایت |
| [بحث رتبه و پایداری provider در GitHub SerpBear](https://github.com/towfiqi/serpbear/issues) و [نیاز multiuser](https://github.com/towfiqi/serpbear/discussions/318) | دادهٔ بیرونی هزینه/قطع‌شدن دارد و کار تیمی نیازمند مجوز است | provider قابل‌تعویض، بودجه/health و RBAC سمت سرور |
| [Google دربارهٔ افت ترافیک](https://developers.google.com/search/docs/monitor-debug/debugging-search-traffic-drops) عوامل الگوریتم، فصل، تقاضا، مهاجرت و مشکل فنی را جدا می‌کند | یک نمودار افت، علت را اثبات نمی‌کند | «تشخیص افت» با چک‌لیست شواهد، تغییرات سایت، GSC، Trends و عوامل بیرونی؛ نتیجه با اطمینان |
| [Google دربارهٔ سنجش اثر تغییر](https://support.google.com/webmasters/answer/17010961?hl=en) می‌گوید تعیین علتِ مستقیم دشوار است | قبل/بعد ساده با تغییر تقاضا و رقبا اشتباه می‌شود | ledger اقدام، baseline، گروه مقایسه در صورت امکان، پنجرهٔ تأخیر، رویدادهای مزاحم و توضیح عدم قطعیت |

این نشانه‌ها برای **مصاحبه و مشاهدهٔ کار تیم** هستند؛ تعداد رأی یا تکرار thread به‌عنوان اندازهٔ بازار استفاده نشود. برای هر درد، نمونهٔ آخرین پروژهٔ واقعیِ تیم باید ثبت شود.

## ممیزی دقیق‌ترِ داشبورد و گراف فعلی Brain

| بخش کد | آنچه واقعاً وجود دارد | شکاف تحلیلی/نمایشی | اقدام پیشنهادی |
|---|---|---|---|
| [پرتفو](../../frontend/src/features/overview/components/portfolio-dashboard.tsx) | وضعیت اتصال/پردازش، شمار محتوا/گره/فرصت و جدول سایت‌ها | هدف، رشد ۱۲ماهه، تماس واجدکیفیت، ریسک افت و کارهای عقب‌مانده در یک سطح نیستند | کارت portfolio health جدا از outcome؛ رتبه‌بندی بر اساس نیاز اقدام و ارزش |
| [نبض زنده](../../frontend/src/features/overview/components/live-portfolio-signals.tsx) | polling هر ۲۰ ثانیه و ۱۸ نمونهٔ همین نشست از شمار گره/محتوا/کلمه | تاریخچه پایدار نیست و تازه‌شدن شمارنده با رشد SEO تفاوت دارد | جریان عملیاتی زنده برای job/call/task؛ سری عملکرد تاریخی از snapshot روزانه؛ timestamp کنار هر کارت |
| [گزارش سایت](../../frontend/src/features/reports/components/site-report-center.tsx) | نمودارهای area برای کلیک، میانگین جایگاه و GA4، جدول کلمه/مشکل/فرصت | نمودار rank ترکیب queryهای متغیر است؛ نمودار GA4 جمع page rows است؛ `score` فقط از مشکل و اتصال ساخته می‌شود و با خزش ناقص نمایندهٔ سلامت کل سایت نیست؛ annotation، cohort، funnel و YoY ندارد | KPI سایت از property-level؛ جایگاه فقط با segment ثابت؛ امتیاز فنی با پوشش/فرمول؛ تقویم تغییر روی نمودار |
| [خروجی GSC](../../backend/seo_brain/gsc/sync.py) و [گزارش](../../backend/seo_brain/api/routers/reports.py) | `gsc_daily` در سطح `date×query×page×country×device` و headline از جمع همان ردیف‌ها | headline کل سایت **property-level نیست**؛ ردیف‌های برتر ممکن است ناقص باشند | ingest مستقل property/date/search-type totals؛ query/page فقط drill-down؛ reconciliation |
| [خروجی GA4](../../backend/seo_brain/ga4/client.py) | `pagePath` و `landingPage` روزانه، با raw response؛ بازهٔ نمایش در برش قبلی اصلاح شد | مجموع `totalUsers` یا `sessions` ردیف‌های `pagePath` KPI یکتای سایت نیست؛ کانال Organic در سنجهٔ کلی گزارش نیست | ingest `date×channel` و `date×landing×channel` با KPI مستقل کل سایت؛ هدف و key event |
| [گراف](../../backend/seo_brain/graph/views.py) | ۴ mode: SEO، محتوا، لینک، برنامه‌ریز؛ ReactFlow با فیلتر/چیدمان/hover/particle | snapshot لحظه‌ای رابطه‌هاست؛ issue/opportunity به‌ازای **نوع** node می‌شوند، نه هر مورد؛ task/owner/change/outcome ندارد | گراف چندلایهٔ نسخه‌دار با node مورد، اقدام، تغییر، سنجه و شاهد |
| [انتخاب گراف](../../backend/seo_brain/graph/views.py) و [UI](../../frontend/src/features/graph/components/command-center.tsx) | nodeها بر اساس PageRank؛ سرور پیش‌فرض ۴۰۰، UI پیش‌فرض ۱۶۰، `truncated` نشان داده می‌شود | کل سایت ممکن است در نقشه دیده نشود؛ search فقط subset بارگذاری‌شده را می‌گردد | search سمت سرور در کل graph، progressive expansion/cluster، شمار و علت حذف؛ عملیات روی URL دلخواه |
| [ساخت query graph](../../backend/seo_brain/graph/builder.py) | فقط query مهم، حداکثر پیش‌فرض ۲۰۰؛ edge با impressions به page وصل است | query کم‌حجمِ استراتژیک/نوظهور ممکن است ناپدید شود؛ بازه و منبع وزن edge مشخص نیست | query هدف را مستقل نگه داریم، edgeها window/source/observed_at داشته باشند؛ گزینهٔ «کم‌داده» |
| [مرکز تماس](../../frontend/src/features/call-center/components/call-center-page.tsx) | area روزانهٔ منبع، bar کانال/منطقه، pie سهم، brand/model و دفتر تماس | قیف تماس → واجدکیفیت → سفارش و ارزش مالی، confidence انتساب، مقایسهٔ دوره و cohort پیگیری کامل نیست | قیف/ماتریس SEO×منطقه×مدل، unknown trend، نتیجه و زمان پیگیری |

**اصل طراحی گراف:** گراف تزئینی نخواهد بود. هر node و edge باید `source`, `observed_at`, `valid_from/to`, `confidence`, `site_id`, و لینک به شواهد داشته باشد. «پیوند به صفحه»، «رابطهٔ موضوعیِ استنتاجی»، «کلمه‌ای که واقعاً impression گرفته» و «وظیفهٔ انسانی» با رنگ/سبک/legend مجزا نمایش داده شوند. hover بدون drill-down کافی نیست. حرکت یال‌ها فقط مسیر انتخابی یا رویداد تازه را نشان دهد؛ motion بر اساس `prefers-reduced-motion` کم شود.

### نمودارهای پیشنهادی و سؤال تصمیمیِ هر کدام

| نما | نمودار مناسب | سؤال عملی و شرط داده |
|---|---|---|
| روند سایت | خط کلیک/نمایش/lead با baseline و annotation تغییرات؛ YoY جدا | آیا رشد واقعی است یا فصلی؟ property-level GSC و GA4 channel-level لازم است. |
| توزیع جایگاه | stacked bar برای Top 3/10/20/100 کلماتِ **ردیابی‌شده** | چه سهمی از کلمات هدف پیش رفته؟ provider SERP با geo/device ثابت لازم است. |
| ماتریس صفحه × ماه | heatmap تغییر کلیک/تبدیل و ستون حجم پایه | کدام صفحات افت پایدار/جهش دارند؟ صفر/ناشناخته و حجم کم باید متفاوت دیده شوند. |
| چرخهٔ عمر محتوا | cohort بر اساس ماه انتشار/refresh با median و بازهٔ پراکندگی | پس از انتشار چه مدت تا اولین impression/lead و بازگشت افت؟ changelog و snapshot لازم است. |
| قیف کسب‌وکار | funnel یا Sankey با تعداد در هر مرحله: GSC click → organic landing session → tel intent → تماس واقعی → lead → سفارش | کدام گلوگاه است؟ پیوند فردی مراحل ممکن است نباشد؛ Sankey فقط برای جریان‌های واقعاً متصل، وگرنه مراحل مستقل. |
| کار تیم | cumulative flow، aging WIP، تقویم موعد، blocked duration | کجا کار زمین می‌ماند؟ تاریخچهٔ event و owner لازم است. |
| ساختار سایت | crawl tree، directory tree، graph لینک واقعی، overlay عمق/ترافیک/indexability | صفحهٔ مهم چقدر دور یا یتیم است؟ منبع کشف/پوشش crawl باید کنار نقشه باشد. |
| موضوع و intent | bipartite query↔URL، treemap خوشه، شکاف intent×مرحلهٔ قیف | چه موضوعی صفحه دارد ولی demand/تبدیل ندارد؟ entity و page mapping معتبر لازم است. |
| فنی و index | stacked areaِ discovered/crawled/indexable/Google-inspected و new/resolved issues | مسئله از چه روزی شروع شد و چند URL مهم را زد؟ snapshot crawl و URL Inspection سهمیه‌دار لازم است. |
| منطقه و مدل | heatmap منطقه×خدمت/مدل و dot plot نرخ تبدیل با interval | تمرکز SEO کجا ارزش دارد؟ تعداد نمونه و unknown source باید نمایش داده شود. |
| پیش‌بینی | fan chart سناریو با مفروضات و actual overlay | آیا به هدف می‌رسیم؟ uncertainty و مقایسهٔ فصل ضروری است. |
| داده و اعتماد | data coverage waterfall، freshness calendar، reconciliation chart | آیا گزارش این ماه قابل اتکاست؟ sync/QA/error budget باید دیده شود. |

خط/area عمومی برای هر سنجه کافی نیست. رنگ باید معنی ثابتِ کسب‌وکار داشته باشد؛ tooltip تعریف/منبع/بازه/سطح تجمیع را نشان دهد؛ همهٔ نمودارها به ردیف URL/query/task برسند. برای عددهای بدون داده، جای خالی/کیفیت داده مهم‌تر از animation است.

## قرارداد داده و شواهد: «هر عدد از کجا آمده؟»

**واحدهای جدا:** property click ≠ page click ≠ session ≠ pageview ≠ tel click ≠ تماس برقرارشده ≠ lead واجدکیفیت ≠ سفارش. [Google تفاوت aggregation در Search Console](https://support.google.com/webmasters/answer/17011364?hl=en) و [ابعاد/سنجه‌های GA4 Data API](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema) را جدا تعریف کرده است. میانگین جایگاه هم با مکان، سابقه و نوع نتیجه تغییر می‌کند؛ جست‌وجوی دستی Google فقط مشاهدهٔ همان زمان/مکان است، baseline رتبه نیست. [تعریف رسمی position](https://support.google.com/webmasters/answer/7042828?hl=en).

برای هر کارت/ردیف/export یک `metric_ref` قابل کلیک ذخیره شود:

```
metric_ref = {
  metric_id, definition_version, site_id, grain, dimensions, filters,
  period_start, period_end, period_timezone, source, source_property,
  sync_run_id, raw_payload_ref_or_hash, transform_version,
  calculated_at, finalized_at, coverage_status, coverage_ratio,
  quality_flags, comparison_basis
}
```

UI با کلیک روی `metric_ref`: فرمول، ردیف‌های ورودی مجاز، تاریخ دریافت، اختلاف با منبع اصلی، محدودیت و توضیح تغییر فرمول را نشان دهد. raw پاسخ Google اکنون در [GSC client](../../backend/seo_brain/gsc/client.py) و [GA4 client](../../backend/seo_brain/ga4/client.py) ذخیره می‌شود؛ این شروع خوبی است، ولی اتصال مستقیم `metric_ref` به فایل خام و نسخهٔ تبدیل در read model هنوز طراحی نشده است.

**کنترل‌های کیفیت قابل خودکارسازی:**

1. همگام‌سازی موفق و بازهٔ پوشش؛ missing day، دادهٔ preliminary و افت غیرعادی حجم نسبت به هفتهٔ قبل.
2. گزارش جداگانهٔ GSC در سطح property/date و page/query؛ اختلاف قابل توضیح، بدون forcing برابری. [حد ۵۰هزار ردیف در روز/نوع](https://support.google.com/webmasters/answer/12919192?hl=en) و [Bulk Export](https://support.google.com/webmasters/answer/12918484?hl=en) مبنای تصمیم مقیاس هستند.
3. GA4 site/channel total در برابر جمع ردیف‌های landing و page؛ هیچ SUM صفحه‌ای با برچسب «کاربران یکتای سایت» نمایش داده نشود.
4. اتحاد URL: scheme/host/path، Unicode فارسی، slash، query parameter، redirect و canonical با alias حفظ‌شده. هر ادغام قابل بازگشت و دارای دلیل باشد.
5. در call center: `source`, `source_basis`, confidence، اپراتور/زمان اصلاح، کیفیت lead، dedupe تماس و وضعیت `unknown` ثبت و audit شود. شماره/اطلاعات شخصی در خروجی تحلیل جمعی masked شوند.
6. هر import از CSV/Sheet/provider دارای mapping، checksum، تعداد ردیف وارد/رد و فهرست خطا باشد؛ دادهٔ دستی برچسب دستی بماند.
7. anomalyهای شناخته‌شدهٔ خود Google در گزارش annotate شوند؛ [فهرست رسمی data anomalies](https://support.google.com/webmasters/answer/6211453?hl=en) نشان می‌دهد خطای logging می‌تواند افت ظاهری ایجاد کند.

**وضعیت هر سنجه:** `ready`, `partial`, `stale`, `preliminary`, `missing`, `not_applicable`, `estimated`, `manual`. عدد صفر فقط وقتی نمایش داده شود که منبع معتبر، بازهٔ کامل و تعریف سنجه آن را پشتیبانی کنند. پیش‌بینی و «ارزش ترافیک» با واحد/روش/عدم‌قطعیت در بخش جدا باشند.

## تغییر مهم در AI Search در اکتبر ۲۰۲۶

[Google از ژوئن ۲۰۲۶ گزارش Generative AI را معرفی کرد](https://developers.google.com/search/blog/2026/06/gen-ai-performance-reports?hl=en) و [راهنمای رسمی می‌گوید تا ۳۱ اوت ۲۰۲۶ به‌صورت جهانی عرضه شده](https://support.google.com/webmasters/answer/16984139?hl=en). گزارش Search برای AI Overviews و AI Mode **impression** و ابعاد page/country/device/date دارد؛ query، click، CTR و «رتبهٔ AI» در این گزارش تعریف نشده‌اند. در مستندات رسمی [Search Analytics API](https://developers.google.com/webmaster-tools/v1/searchanalytics/query) نوع گزارش جداگانهٔ Generative AI دیده نشد؛ دربارهٔ امکان `searchAppearance` هم از سند رسمی نتیجهٔ قطعی نگرفتیم. پیش از وعدهٔ sync خودکار، باید روی property مجاز آزمون واقعی و نتیجهٔ درخواست ثبت شود. تا آن زمان import دستی export رسمی با برچسب provenance قابل پیاده‌سازی است. نمونه‌گیری پاسخ ChatGPT/Perplexity/Claude یک منبع **متفاوت** با نتایج رسمی Google است و نباید در یک KPI جمع شود.

## دفتر قابلیت‌های پیشنهادی با اولویت و معیار آزمون

`A` = وابستگی پایه/اثر مستقیم بر تیم داخلی؛ `B` = عمق محصول پس از دادهٔ معتبر؛ `C` = پژوهش/افزونه. «بساز» به معنی قابل کدنویسی در Brain است، نه تعهد زمان بدون نمونهٔ واقعی.

| ID | قابلیت / منبع داده | رده | اجرا و معیار پذیرش |
|---|---|---|---|
| F01 | فهرست مشترک URL از WP+sitemap+crawl+GSC+manual | A | بساز؛ هر URL منشأ و last_seen دارد؛ شمار discovered/crawled جداست. |
| F02 | property-level GSC روزانه + page/query drill-down | A | بساز؛ headline از query بدون بعد page، تفاوت با جمع جدول توضیح دارد. |
| F03 | GA4 site/channel و landing/channel جدا | A | بساز؛ کاربران یکتای کل سایت از جمع pagePath به دست نیاید. |
| F04 | Metric catalog و `metric_ref`/lineage | A | بساز؛ هر عدد به تعریف، دوره، sync و کیفیت داده باز شود. |
| F05 | snapshot ماهانه و baseline قابل بازتولید | A | بساز؛ ماه بسته‌شده/ناقص تفکیک؛ versioning و YoY. |
| F06 | صفحهٔ پروندهٔ URL با تغییرات و دادهٔ یکپارچه | A | بساز؛ WP/crawl/GSC/GA4/هدف/وظیفه با provenance. |
| F07 | دفتر issue/opportunity به‌ازای مورد، نه فقط نوع | A | بساز؛ created/resolved/reopened، severity، affected URLs و evidence. |
| F08 | action ledger با owner/approval/due/blocked/verify | A | بساز؛ هیچ مورد پذیرفته‌شده بی‌مالک/بی‌موعد پنهان نماند. |
| F09 | timeline تغییر title/content/canonical/redirect/deploy | A | بساز؛ diff، actor، تاریخ مشاهده/انتشار و لینک شاهد. |
| F10 | گزارش مدیر با نتیجه/اقدام/ریسک و گزارش متخصص با drill-down | A | بساز؛ ۵ سؤال تصمیمی بدون اسکرول سنگین پاسخ بگیرند. |
| F11 | کیفیت انتساب تماس SEO/Ads/unknown و funnel واقعی | A | بساز؛ unknown rate و نمونهٔ هر مرحله معلوم باشد. |
| F12 | هویت فردی و RBAC واقعی سمت API | A | بساز؛ تست دسترسی ممنوع به سایت/تماس غیرمجاز. |
| F13 | مانیتور sync و data quality alert | A | بساز؛ stale/failed/partial برای مسئول نمایش داده شود. |
| F14 | بودجهٔ crawl، queue و completeness | A | بساز؛ خزش ۲۰ URL فعلی به‌عنوان خزش کامل معرفی نشود. |
| F15 | صفحه/خوشهٔ برنده و بازنده با حجم پایه و فصل | B | بساز؛ تغییر demand/CTR/rank را جدا توضیح دهد. |
| F16 | query↔URL stability و cannibalization candidate | B | بساز؛ جابه‌جایی landing و چند URL با مرور انسانی. |
| F17 | content decay/refresh queue و cohort بعد انتشار | B | بساز؛ صفحهٔ منتشرشده دوباره موعد بازبینی بگیرد. |
| F18 | گراف crawl tree و directory tree و overlay عملکرد | B | بساز؛ معنی یال و پوشش node آشکار باشد. |
| F19 | گراف evidence/action/outcome نسخه‌دار | B | بساز؛ از فرصت به task و snapshot قبل/بعد قابل پیمایش باشد. |
| F20 | پیشنهاد لینک داخلی با passage/intent/evidence | B | بساز؛ لینک موجود، noindex و مناسبت معنا بررسی شود. |
| F21 | alert تغییر فنی مهم و diff دو crawl | B | بساز؛ تغییر تازه/رفع‌شده با کاهش false positive. |
| F22 | URL Inspection صف‌بندی‌شده برای صفحات مهم | B | API رسمی؛ سهمیه و تاریخ نتیجه؛ indexability با indexed اشتباه نشود. |
| F23 | CrUX/PSI mobile+desktop و Lighthouse CI | B | اتصال؛ field/lab جدا و regression با چند اجرای کنترل‌شده. |
| F24 | Google Trends/context و تقویم update/anomaly | B | اتصال/annotation؛ فقط توضیح زمینه، نه علت قطعی. |
| F25 | هدف و سناریوی رشد با فرض/uncertainty | B | بساز؛ actual/target/forecast جدا، مفروضات قابل ویرایش. |
| F26 | rank tracker geo/device و SERP snapshot | B | provider؛ هزینه/خطا/مکان/دستگاه ثبت شود؛ آزمایش فارسی/ایران. |
| F27 | keyword/backlink/competitor gap | B | provider؛ دادهٔ تخمینی با source و freshness. |
| F28 | pipeline گزارش ماهانه + export قابل چاپ/اشتراک | B | بساز؛ narrative انسانی و لینک شواهد؛ snapshot قابل بازتولید. |
| F29 | dashboard ظرفیت و SLA تیم | B | بساز؛ throughput/aging/blocked، نه فقط تعداد کارت. |
| F30 | segmentation ذخیره‌شده و نماهای شخصی | B | بساز؛ page type/موضوع/خدمت/شهر/owner در همهٔ نمودارها یکسان اعمال شود. |
| F31 | log analysis Googlebot و AI bots برای سایت بزرگ | C | واردکننده؛ bot verification و privacy؛ اثبات crawl واقعی. |
| F32 | BigQuery GSC bulk export برای سایت حجیم | C | اتصال شرطی؛ هزینه و تفاوت anonymized query روشن باشد. |
| F33 | گزارش رسمی AI impressions از export GSC | B | import شفاف؛ تاریخ/صفحه/کشور/دستگاه؛ API را جدا آزمون کن. |
| F34 | panel نمونه‌گیری AI mentions/citations | C | provider/آزمون؛ prompt/model/response خام/تکرارپذیری. |
| F35 | AI analyst با metric catalog و citation به ردیف | C | بساز؛ عدد بدون provenance یا اقدام بدون تأیید تولید نکند. |
| F36 | templateهای عمودی خدمات/فروشگاه/محتوا/B2B | B | بساز؛ KPI/فیلتر/قیف بر اساس هدف کسب‌وکار. |
| F37 | ingestion رویداد واقعی تماس/سفارش از CRM/تلفن | B | اتصال؛ dedupe و trace id؛ مجوز/حریم داده. |
| F38 | Jira/Asana/Linear/Sheet sync برای تیم موجود | C | اتصال دوطرفه فقط بعد از تعیین source of truth و حل تعارض. |
| F39 | cost ledger سئو/محتوا/رپورتاژ/provider | B | بساز؛ هزینهٔ واقعی کنار هدف و نتیجه، ROI با سطح انتساب. |
| F40 | alert digest هفتگی «چه چیز نیاز به تصمیم دارد» | B | بساز؛ false positive و زمان تا تصمیم سنجیده شود. |

## ترتیب توسعهٔ پیشنهادی و آزمایش‌های توقف

1. **داده و اعتماد:** F01–F05، F13–F14. روی دو سایت پایلوت property totals و URL inventory با منبع اصلی reconcile شود. اگر پوشش پایین است، نمودار «رشد» منتشر نشود.
2. **کار روزانه:** F06–F12. ۱۰ مسئلهٔ واقعی از کشف تا نشر/رد در Brain مدیریت شود؛ درصد بی‌مالک، زمان تصمیم و درصد سنجش پس از اجرا اندازه‌گیری شود.
3. **ارزش کسب‌وکار:** F11، F15–F17، F25، F36–F37، F39. ۲۰ تماس و lead نمونه، همراه Ads/unknown و کیفیت انتساب، بررسی شود. اگر پیوند تماس به سایت/کانال مبهم است، ROI به شکل بازه یا نامعلوم گزارش شود.
4. **عمق و تمایز:** F18–F24، F26–F35 و F40. آزمایش ۲–۳ provider روی کلمات و شهرهای واقعی، هزینه/دقت/پایداری. هر integration پرهزینه gate دارد.

در پایان هر مرحله سه سؤال توقف: آیا داده قابل بازتولید است؟ آیا کاربر با این نما تصمیم بهتری گرفت؟ آیا هزینهٔ ساخت/داده با ارزش آن می‌خواند؟ این ترتیب با دادهٔ پایلوت می‌تواند تغییر کند.

## آزمون‌های پژوهشی که هنوز باید با انسان و دادهٔ واقعی انجام شوند

- مشاهدهٔ یک هفته کار SEO lead، محتوا، توسعه و کال‌سنتر؛ نمونهٔ واقعی از «چه کار جا ماند؟» و «کدام عدد در جلسه محل اختلاف شد؟».
- ممیزی ۲–۳ سایت دارای GSC/GA4/WP: coverage query/page/property، حجم URL، فاصلهٔ sync، source تماس و تراکم دادهٔ شهر/مدل. اطلاعات شخصی در فایل پژوهش نیاید.
- مصاحبه با مدیر مشتری/داخلی: گزارش ۵دقیقه‌ای چه تصمیمی می‌سازد؟ آیا نمرهٔ سلامت فعلی او را گمراه می‌کند؟
- prototype با دادهٔ واقعی برای graph overlay و گزارش ماهانه؛ زمان رسیدن از هشدار تا task و تفسیر اشتباه کاربران ثبت شود.
- آزمون مستندِ API گزارش Generative AI روی property مجاز؛ پاسخ HTTP، request، quota و مسیر جایگزین export حفظ شود.
- provider bake-off رتبه/بک‌لینک/AI: نمونهٔ ثابت فارسی، موبایل/دسکتاپ، تهران/سایر مکان‌ها، هزینهٔ هر ۱۰۰۰ مشاهده و نرخ خطا.

## جمع‌بندی تصمیمی

بهترین مسیر برای «کامل‌ترین داشبورد» این است که Brain **کامل‌ترین جریان قابل پیگیری برای تصمیم و اجرای رشدِ سایت‌های خودش** را بسازد: موجودی URL با پوشش روشن، سنجهٔ قابل توضیح، گرافِ زمان‌دار، کارِ مسئول‌دار، سنجش بعد از تغییر و نتیجهٔ تماس/سفارش. ادعای «بهترین بازار» تا تست کاربردپذیری، دقت داده و هزینه در برابر رقبا قابل اثبات نیست. معیار رقابت ما تعداد نمودار نیست؛ سرعت و صحت پاسخ به سؤال‌های واقعی تیم و کسب‌وکار است.
