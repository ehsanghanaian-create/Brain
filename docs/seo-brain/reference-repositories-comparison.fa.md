# مقایسهٔ محلی ۴۸ مخزن برای SEO Brain

تاریخ به‌روزرسانی: ۱۹ مهر ۱۴۰۵. فهرست دقیق ۴۸ نسخه در [manifest مخزن](./reference-repositories-manifest.md) و مسیرهای محلی در `C:\Users\saleh\Claude\Projects\seo-brain-reference-repos\manifest.json` ثبت شده است. هر موردِ manifest یک checkout از شاخهٔ اصلی در کامیت مشخص با تاریخچهٔ کم‌عمق است. مخزن‌ها اجرا یا نصب نشده‌اند و یافته‌ها از کد، README و اسناد موجود در همان نسخه‌اند؛ عملکرد، کیفیت دادهٔ vendor و مقیاس تولید هنوز آزموده نشده است. دو پوشهٔ حاصل از دانلود ناقص خارج از manifest هستند و جزو ۴۸ مخزن محسوب نمی‌شوند.

## سؤال اصلی معماری

در شاخهٔ فعلی SEO Brain دادهٔ GSC/GA4/crawl، گراف و محتوا وجود دارد؛ اما مدل عمومی تسک تیمی (`work_items`) در این شاخه وجود ندارد. مزیت رقابتی بعدی در **اتصال قابل‌اثبات داده به تصمیم و اجرای تیم** است. اگر فقط صفحات OpenSEO یا RankMeFast را تکرار کنیم، هزینهٔ provider و انبوه گزارش خواهیم داشت، ولی همچنان مدیر نمی‌فهمد «چه یافته‌ای با کدام تسک حل شد و چه اثری گذاشت». پیشنهاد این است که هستهٔ فعلی حفظ شود و بهترین قراردادهای داده و گردش کار از منابع زیر بازطراحی شوند. [کالبدشکافی و برنامهٔ دقیق ۴۸ مخزن](./reference-architecture-48.fa.md) وضعیت فعلی و مسیر اجرا را توضیح می‌دهد.

## مقایسهٔ مخزن‌های اصلی

| مخزن | مزیت قابل انتقال | هزینه/ضعف برای ما | تصمیم پیشنهادی |
| --- | --- | --- | --- |
| [OpenSEO](https://github.com/every-app/open-seo) | معماری crawl با frontier جدا، chunk/retry و نمایش نتیجهٔ جزئی؛ تفکیک رتبهٔ زنده از GSC؛ داشبورد پروژه و گزارش‌های مستند | بیشتر داده‌های research به DataForSEO و هزینهٔ درخواست وابسته‌اند؛ پیاده‌سازی Cloudflare/TypeScript با FastAPI ما هم‌شکل نیست | **الگوی اصلی audit، provenance و UX**؛ منطق را به Python/SQLite خودمان ترجمه کنیم |
| [RankMeFast](https://github.com/SelmiAbderrahim/rankme.fast) | رابط provider مستقل، نرمال‌سازی داده، error taxonomy و fixture؛ صف Next Actions با تاریخچهٔ تصمیم و بازآزمایی | AGPL؛ بتای عمومی؛ MongoDB + Postgres + Redis + API/worker/web برای امروز سنگین است | **الگوی اصلی adapter و action queue**؛ کد محصول را مستقیم وارد نکنیم |
| [Ansvisor](https://github.com/ansvisor/ansvisor) | زنجیرهٔ سیگنال→کاندیدا→اقدام→تسک؛ صفی که یافته را وقتی ظرفیت اقدام نیست نگه می‌دارد؛ پایش پاسخ/citation | تمرکز بر AI Search؛ امتیاز visibility مدل‌محور و حساس به نمونهٔ prompt است؛ سرویس AI هزینه و نوسان دارد | **الگوی action lifecycle**؛ AI visibility فاز بعد از مدل شواهد |
| [CrawlSEO](https://github.com/crawlseo/crawlseo) | صفحهٔ کم‌تراکم برای GSC + crawl + CWV؛ Next.js نزدیک به frontend فعلی؛ راه سریع دیدن مشکل صفحه | خزیدن README تا ۲۰۰۰ صفحه؛ عمق برنامه‌ریزی تیم و تحلیل اثر کمتر از هدف SEO Brain است | **مرجع UX و page health**، نه هستهٔ مدیریت تیم |
| [Bisibility](https://github.com/CorgiCorner/bisibility) | rank history، share of voice و اتصال context؛ Temporal/worker برای کار دوره‌ای و retry | AGPL؛ API پایدار ۱.۰ اعلام نشده؛ Temporal + Redis/Valkey + Postgres سربار دارد | **مرجع rank scheduling** فقط پس از سنجش بار صف فعلی |
| [OpenGSC](https://github.com/fenjo26/OpenGSC) | چند سایت/موتور، cache، مقایسهٔ GSC با SERP، بکاپ پیش از migration و ثبت وضعیت job | تک‌اپ Next.js بسیار گسترده؛ بعضی jobها در همان پردازه‌اند و با restart قطع می‌شوند؛ indexer/cloaking مناسب SEO Brain نیست | **مرجع inventory قابلیت و محافظت از داده**؛ زیرسیستم‌های منتخب را بررسی کنیم |
| [Plane](https://github.com/makeplane/plane) | کارت، نما، cycle، ماژول، گفتگو و دسترسی تیمی | AGPL و چندسرویسی؛ هیچ مدل بومی GSC/SEO ندارد | **مرجع تجربهٔ کار تیم**؛ تسک بومی SEO Brain بماند |
| [OpenProject](https://github.com/opf/openproject) | گانت، وابستگی، زمان واقعی، برنامهٔ تیم و کنترل تحویل | GPL، استقرار سنگین و پشتهٔ متفاوت؛ اتصال تسک به اثر سئو خودکار نیست | **مرجع زمان‌بندی و تأیید مدیر** |
| [Metabase](https://github.com/metabase/metabase) | فیلتر، drill-down، داشبوردهای مدیریتی و گزارش قابل اشتراک | محصول BI مستقل و مجوز ترکیبی؛ روی مدل دادهٔ مبهم فقط نمودار مبهم می‌سازد | **بعد از تثبیت مدل KPI**، سرویس جدا یا الگوی UX |

## مخزن‌های پشتیبان؛ چه چیزی را از هرکدام بگیریم؟

| مخزن | مزیت | احتیاط |
| --- | --- | --- |
| [SerpBear](https://github.com/towfiqi/serpbear) | snapshot مستقل جایگاه کلمه و هشدار | provider/proxy برای SERP هزینه یا محدودیت عملی دارد؛ جایگاه GSC معیار دیگری است |
| [SiteOne Crawler](https://github.com/janreges/siteone-crawler) | crawler مستقل و خروجی ساخت‌یافته برای مقایسه | نصب/اجرای باینری جدا و تکرار بخشی از crawler موجود |
| [Unlighthouse](https://github.com/harlan-zw/unlighthouse) | نمونه‌گیری Lighthouse در سطح سایت | اجرای مرورگر سنگین؛ lab data معادل تجربهٔ میدانی همهٔ کاربران نیست |
| [Lighthouse CI](https://github.com/GoogleChrome/lighthouse-ci) | جلوگیری از افت کیفیت در هر انتشار | بیشتر gate توسعه است تا داشبورد عملیات روزانه |
| [Lighthouse](https://github.com/GoogleChrome/lighthouse) | موتور سنجش performance/accessibility/best practice | یک اجرای آزمایشگاهی به‌تنهایی نشان‌دهندهٔ وضعیت همهٔ صفحات نیست |
| [Houtini SEO Audit](https://github.com/houtini-ai/seo-audit) | seed خزیدن از لینک+sitemap+URLهای GSC؛ شواهد کنار هر یافته | ابزار MCP/audit است، نه سیستم کامل مدیریت پروژه؛ ruleهای heuristic باید جدا برچسب بخورند |
| [SEO Audit Skill](https://github.com/seo-skills/seo-audit-skill) | دسته‌بندی گستردهٔ ruleها | منبع ایده و taxonomy است؛ rule بدون داده و آزمون، هشدار کاذب می‌سازد |
| [Site Analytics](https://github.com/jafforgehq/site-analytics-tool) | نمای پورتفولیو، سلامت sync، دادهٔ قدیمی و coverage | طراحی تک‌مدیر؛ جامعه و سابقهٔ محدود |
| [Aperture](https://github.com/anyin-ai/aperture) | نمونهٔ زیرساخت AI visibility | پروژهٔ جوان؛ سنجش تکرارپذیری پاسخ‌ها لازم است |
| [Client Reporter](https://github.com/coysh-digital/client-reporter) | ایدهٔ قالب و ساخت گزارش مشتری | v0.1 و شواهد تولید کم |
| [Langfuse](https://github.com/langfuse/langfuse) | trace، نسخهٔ prompt، هزینه و کیفیت خروجی AI | سرویس اضافه و دادهٔ حساس؛ بخش‌هایی از مخزن مجوز متفاوت دارند |
| [Vikunja](https://github.com/go-vikunja/vikunja) | نماهای سادهٔ لیست/کانبان/گانت | AGPL؛ SEO و گزارش اثر بومی ندارد |
| [Leantime](https://github.com/Leantime/leantime) | هدف→مایلستون→زیرکار و ساعت | AGPL/PHP؛ برای الگو مناسب‌تر از کد مستقیم |
| [PLANKA](https://github.com/plankanban/planka) | روانی برد و کارت | مجوز جامعه محدودیت تجاری دارد؛ کد را بدون بررسی حقوقی ادغام نکنیم |
| [SEO Panel](https://github.com/seopanel/Seo-Panel) | فهرست قابلیت‌های کلاسیک ابزار سئو | GPL/PHP و معماری قدیمی برای هستهٔ فعلی |
| [seo-os](https://github.com/AgriciDaniel/seo-os) | ایدهٔ عامل‌های AI برای آژانس | AGPL و معماری/UX آزمایشی |
| [RosterSEO](https://github.com/open-saas-org/RosterSeo) | ترکیب SEO، انتشار و AI visibility | بسیار جوان؛ قابلیت‌های README باید با سناریوی واقعی آزموده شوند |
| [GoCrawl](https://github.com/Patience-dot-devl/gocrawl) | analyzer افزونه‌ای و خروجی JSON/CSV | سابقه و پذیرش بسیار کم؛ مرجع آزمایشی |
| [CrawlObserver](https://github.com/SEObserver/crawlobserver) | crawler سریع با سیگنال‌های SEO | AGPL و جامعهٔ محدود؛ اول ارزشش در برابر crawler موجود سنجیده شود |

## معماری منتخب برای بحث و تصمیم

1. **لایهٔ منبع داده:** GSC، GA4، crawl، tracking تماس و providerهای آینده در adapterهای محدود با schema یکسان، منشأ، زمان، پوشش، هزینه و خطای صریح. این از RankMeFast و OpenSEO الهام می‌گیرد.
2. **فهرست موجودیت‌های واقعی سایت:** URL canonical، کوئری، کلمهٔ تحت پایش، سِرپ در بازار مشخص، محتوای منتشرشده و کمپین. هر مشاهده به موجودیت/بازه/منبع وصل شود. URLهای GSC، sitemap و crawler اختلاف پوشش را آشکار کنند.
3. **موتور یافته:** rule قطعی و heuristic جدا، کلید پایدار، شواهد خام و تاریخ first/last seen؛ اجرای دوباره finding تکراری نسازد. از Houtini و OpenSEO الهام می‌گیرد.
4. **صف تصمیم:** یافته ممکن است «کاندیدا» باشد اما هنوز تسک نباشد. مدیر/کارشناس آن را برنامه‌ریزی، رد یا بازآزمایی کند؛ تاریخچهٔ تصمیم حذف نشود. از Ansvisor و RankMeFast الهام می‌گیرد.
5. **تسک بومی:** `work_items` و مجوز سایت/فرد، مسئول، گفتگو، چک‌لیست و تأیید مدیر باید به این شاخه اضافه شوند. از Plane/OpenProject برای UX و زمان‌بندی استفاده شود؛ دادهٔ SEO داخل محصول دیگر مهاجرت نکند.
6. **بازآزمایی اثر:** تکمیل تسک و رشد کلیک/رتبه/تماس جدا نمایش داده شوند. snapshot پیش/پس و بازهٔ انتظار ثبت شود؛ نتیجهٔ نامطمئن با برچسب نامطمئن بماند.
7. **نمای مدیر:** سایت→یافته→اقدام→مسئول→وضعیت→اثر در یک مسیر drill-down؛ خلاصهٔ پورتفولیو، backlog و پروژه‌های بی‌مسئول. نمودارهای زیبا بر همین دادهٔ قابل ردیابی سوار شوند.

## ریسک‌هایی که باید پیش از ادغام حل شوند

- **مجوز کد:** MIT/Apache معمولاً ساده‌ترند، اما notice و وابستگی‌ها باید بررسی شوند؛ AGPL/GPL و مجوزهای ترکیبی/جامعه برای SaaS یا کپی مستقیم نیازمند تصمیم حقوقی‌اند. الهام از الگو با کپی کد یکی نیست.
- **هزینه و پوشش داده:** keyword volume، بک‌لینک، SERP و AI visibility غالباً به API پولی وابسته‌اند. cache، بودجه، geo/device و برچسب «داده موجود نیست» باید در قرارداد باشند.
- **اعتماد به رتبه:** GSC average position، rank check لحظه‌ای و visibility AI سه سنجهٔ متفاوت‌اند؛ یک نمودار واحد بدون برچسب منبع گمراه‌کننده می‌شود.
- **بار عملیاتی:** صف فایل‌محور فعلی برای یک API process طراحی شده است. سایت‌های زیاد و crawl/PSI/AI هم‌زمان، آزمون restart/lease/retry و احتمالاً worker جدا می‌خواهند؛ مهاجرت به Postgres/Redis باید از اندازه‌گیری بیاید.
- **دسترسی و حریم داده:** هر site و report باید در API نیز scope شود؛ دکمهٔ پنهان‌شده در UI مجوز نیست. اتصال مشتریان مختلف به provider و گزارش اشتراکی بدون جداسازی داده خطرناک است.
- **قابلیت ردیابی اثر:** همبستگی بعد از انجام تسک، اثبات علت نیست. برای تماس‌های احتمالی و پاسخ‌های AI عدم قطعیت باید همیشه قابل دیدن باشد.

## تصمیم اول پیشنهادی

برای تیم داخلی، از **مدل مشاهده و یافته** شروع کنیم و سپس مدل کار تیمی جدید را به آن پیوند دهیم. گام نخست با دادهٔ GSC/GA4/crawl موجود و بدون API پولی جدید آزمودنی است. بعد از اینکه مدیر بتواند از یک افت کلیک به URL، مسئله، مسئول و نتیجهٔ بازآزمایی برسد، رتبه‌سنجی مستقل، CWV دوره‌ای و AI visibility ارزش بیشتری خواهند داشت.

## ۲۰ مخزن تکمیلی انتخاب‌شده در ۱۹ مهر ۱۴۰۵

این انتخاب شکاف‌های معماری و تجربهٔ کار را پوشش می‌دهد؛ «دانلود» به معنی «اتصال به SEO Brain» نیست. اولویت **۱** یعنی مطالعه و طراحی بومی در گام بعدی، **۲** یعنی نیازمند قرارداد داده/هزینه/آزمون، و **۳** یعنی مرجع محدود یا دارای مانع مجوز. اطلاعات مجوز از GitHub و فایل ریشه گرفته شده؛ نبود فایل مجوز را با ادعای README جایگزین نکردیم.

| مخزن | نقش مشخص برای SEO Brain | اولویت و شرط استفاده |
| --- | --- | --- |
| [SEOnaut](https://github.com/StJudeWasHere/seonaut) | severity و گزارش audit ساده برای هر سایت | ۱؛ ruleهای هم‌پوشان با crawler فعلی را دوباره نسازیم |
| [LibreCrawl](https://github.com/PhialsBasement/LibreCrawl) | session جدا برای crawl هم‌زمان و خروجی صفحه/لینک | ۲؛ سنجش throughput و ایزوله‌سازی سایت پیش از الگوبرداری |
| [seo-ops](https://github.com/tigerless-labs/seo-ops) | چک‌های ساختاری قطعی، مستقل از LLM | ۳؛ فایل مجوز ریشه ندارد، صرفاً ایدهٔ rule |
| [advertools](https://github.com/eliasdabbas/advertools) | تحلیل sitemap، robots، log و دادهٔ جست‌وجو در Python | ۱؛ ابتدا یک adapter کوچک روی دادهٔ موجود، نه نصب کل ابزار در runtime |
| [google-searchconsole](https://github.com/joshcarty/google-searchconsole) | ergonomics دریافت GSC و DataFrame | ۲؛ SEO Brain کلاینت GSC دارد؛ فقط API/تست‌های بهتر ارزش دارد |
| [seo-keyword-clusters](https://github.com/jfaccioli/seo-keyword-clusters) | ایدهٔ خوشه‌بندی query | ۳؛ README آن نسخه را legacy می‌نامد و مجوز ریشه روشن نیست |
| [OpenSERP](https://github.com/karust/openserp) | قرارداد یکسان SERP چند موتور و geo/language | ۲؛ رتبه‌گیری خودمیزبان به پایداری منبع و محدودیت درخواست وابسته است |
| [SerpTrail](https://github.com/serpapi/serptrail) | ذخیرهٔ snapshot واقعی SERP جدا از سایت/کلمه، تاریخچه و بودجهٔ درخواست | ۱ برای مدل داده؛ فراخوانی زنده هزینهٔ SerpApi دارد |
| [OpenCited](https://github.com/opencited/opencited) | worker جدا و فرمول شفاف ذکر/استناد در پاسخ AI | ۲؛ مجوز MIT در README آمده ولی فایل LICENSE ریشه موجود نیست؛ صحت روش نمونه‌گیری باید آزموده شود |
| [Spider-Lens](https://github.com/GDM-Pixel/spider-lens) | لاگ‌کاوی خزنده‌های واقعی، status و TTFB در سطح URL | ۱؛ نیازمند دسترسی لاگ و حذف دادهٔ شخصی؛ ادعای MIT در README است، فایل LICENSE ریشه نیست |
| [Elmo](https://github.com/elmohq/elmo) | ذخیرهٔ پاسخ خام، citation و رقیب برای AI visibility | ۲؛ دادهٔ AI وابسته به prompt/مدل/بازار و هزینهٔ اجراست |
| [web-vitals](https://github.com/GoogleChrome/web-vitals) | سنجش میدانی CWV در مرورگر و پیوند به URL/نسخه | ۱؛ فقط با رضایت و نمونهٔ کافی، و جدا از Lighthouse آزمایشگاهی |
| [Mapping Website Internal Links](https://github.com/devbret/mapping-website-internal-links) | گراف لینک و امتیاز صفحه برای یافتن orphan/depth | ۱؛ نمایش گراف را با شبکهٔ فعلی URLهای SEO Brain یکی کنیم |
| [Link Graph Explorer](https://github.com/ruslan2027/link-graph-explorer-oss) | نمای تعاملی سبک گراف لینک با خروجی مستقل | ۲؛ مرجع UX؛ دادهٔ گراف مستقل نسازیم |
| [SEOCORE](https://github.com/codepurse/SEOCORE) | rule engine اعلامی، عمق خزیدن، redirect و link graph | ۱؛ rule قطعی با کلید/شاهد پایدار به موتور یافتهٔ بومی وصل شود |
| [Rank Math plugin](https://github.com/rankmath/seo-by-rank-math) | شناخت دقیق متای افزونهٔ فعال وردپرس سالیمور | ۱ برای قرارداد خواندن metadata؛ کد GPL را مستقیم به SEO Brain وارد نکنیم |
| [Rank Math API Manager](https://github.com/Devora-AS/rank-math-api-manager) | الگوی endpoint وردپرس برای فیلدهای Rank Math | ۲؛ نصب plugin/نوشتن SEO در فروشگاه تصمیم مستقل و نیازمند مجوز است |
| [QueryLoom](https://github.com/publicusdijital-ai/queryloom) | تبدیل GSC به low CTR، striking distance، decay و page/query mismatch | ۱؛ با دادهٔ GSC فعلی و تعریف آستانهٔ قابل توضیح قابل آزمون است |
| [AiCMO](https://github.com/AICMO/ai-cmo) | نمونهٔ نمای مدیریتی prompt و رقیب در AI SEO | ۳؛ زمان به‌روزرسانی قدیمی‌تر و سیگنال‌ها نیازمند راستی‌آزمایی‌اند |
| [SearchMirror](https://github.com/databluedev/searchmirror) | تاریخچهٔ رتبه، هزینهٔ provider و کنترل دسترسی تیمی | ۲؛ AGPL، وابسته به DataBlue و پشتهٔ قدیمی Django/Mongo؛ مرجع مدل، نه کد قابل کپی |

### اولویت اجرایی پس از پایدار شدن وردپرس

1. **نمایش metadata واقعی Rank Math:** REST عمومی سالیمور برای یک نوشته فقط `id/link/meta` برگرداند و `rank_math_head(_json)` و `yoast_head_json` را برنگرداند. crawler فعلی title/description/canonical/schema را از HTML نهایی می‌گیرد؛ این داده را در گزارش با منشأ `rendered_page` نشان دهیم و فیلدهای Yoast خالی را متای Rank Math تلقی نکنیم. اگر دادهٔ معتبر بیشتری لازم شد، endpoint خواندنیِ دارای احراز هویت را جدا طراحی کنیم. کد افزونهٔ ثالث را به backend کپی نکنیم.
2. **یافتهٔ قابل اقدام از GSC + crawl:** QueryLoom، SEOCORE و SEOnaut را برای taxonomy، شواهد و threshold مقایسه کنیم؛ خروجی به URL و بازهٔ زمانی وصل شود و بعد به تسک.
3. **پایش واقعی اجرا:** Spider-Lens برای لاگ Googlebot و web-vitals برای تجربهٔ میدانی؛ هر دو منبع و پوشش نمونه را صریح نشان دهند.
4. **رتبه و AI visibility:** مدل snapshot از SerpTrail و شفافیت پاسخ خام از Elmo/OpenCited؛ فقط پس از تعیین بازار، هزینه، نرخ پایش و معیار صحت.
