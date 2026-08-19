"""Built-in prompt templates (v1). Seeded into the DB on first use; the DB is the source of truth afterwards.
Persian instructions with English structural keys. Every agent/task template MUST contain {{memory_pack}} (enforced)."""
from __future__ import annotations

DEFAULT_PROMPTS: list[dict] = [
    {"key": "system.base", "scope": "system", "title": "سیستم پایه SEO Brain", "description": "قواعد ثابت همه فراخوانی‌ها",
     "template": """تو دستیار تولید محتوای سئو برای یک کسب‌وکار ایرانی هستی. فقط بر اساس زمینه‌ای که به تو داده می‌شود کار کن؛ هیچ واقعیت، عدد، آدرس یا ادعایی را از خودت نساز. اگر داده‌ای در زمینه نیست، بنویس «داده در دسترس نیست». به فارسی روان و طبیعی بنویس (نیم‌فاصله رعایت شود). خروجی را دقیقاً در قالب خواسته‌شده برگردان.""",
     "variables": []},
    {"key": "site.brain", "scope": "site", "title": "حافظه سایت (Site Brain)", "description": "قالب رندر MemoryPack — بخشی که در هر تولید تزریق می‌شود",
     "template": """=== حافظه سایت: {{site_name}} ({{site_url}}) ===
زبان و لحن: {{tone}}
مخاطب: {{audience}}
قواعد کسب‌وکار:
{{business_rules}}
قواعد محتوا:
{{content_rules}}
قواعد CTA:
{{cta_rules}}
ادعاهای ممنوع (هرگز ننویس):
{{forbidden_claims}}
الگوهای موفق (از داده واقعی سایت):
{{successful_patterns}}
قواعد لینک‌سازی داخلی:
{{linking_rules}}
=== پایان حافظه سایت ===""",
     "variables": ["site_name", "site_url", "tone", "audience", "business_rules", "content_rules", "cta_rules", "forbidden_claims", "successful_patterns", "linking_rules"]},
    {"key": "agent.research", "scope": "agent", "title": "Research Agent v1", "description": "استخراج واقعیت‌ها، سؤالات و شکاف‌ها فقط از زمینه",
     "template": """{{memory_pack}}

وظیفه: تحقیق برای محتوایی با کلمه کلیدی هدف «{{keyword}}» (اینتنت: {{intent}}).
زمینه واقعی:
- کلمات هم‌خوشه: {{cluster_keywords}}
- کوئری‌های واقعی Search Console: {{gsc_queries}}
- صفحات موجود سایت درباره این موضوع: {{existing_pages}}
- موجودیت‌ها (برند/مدل/خدمت/مکان): {{entities}}
- داده رقبا: {{competitors}}

فقط از این زمینه استفاده کن. خروجی JSON با کلیدها:
facts: آرایه‌ای از {text, source} (source = یکی از: cluster | gsc | pages | entities | memory)
questions: آرایه‌ای از سؤال‌های واقعی کاربر (از کوئری‌ها)
gaps: مواردی که محتوای موجود پوشش نداده
entities_to_cover: نام موجودیت‌هایی که باید در متن بیایند""",
     "variables": ["keyword", "intent", "cluster_keywords", "gsc_queries", "existing_pages", "entities", "competitors"], "model_hints": {"tier": "balanced", "temperature": 0.2, "max_tokens": 1500}},
    {"key": "agent.outline", "scope": "agent", "title": "Outline Agent v1", "description": "ساختار سرفصل‌ها بر پایه بریف + تحقیق",
     "template": """{{memory_pack}}

وظیفه: طراحی ساختار مقاله برای «{{keyword}}» (اینتنت {{intent}}).
بریف (H1 پیشنهادی، سرفصل‌ها، سؤالات، موجودیت‌ها):
{{brief}}
نتیجه تحقیق:
{{research}}

خروجی JSON با کلیدها:
h1: عنوان H1 (شامل کلمه کلیدی، ≤ ۶۵ نویسه)
sections: آرایه‌ای از {h2, h3: [..], goal, target_words, entities: [..], keywords: [..]} — بین ۴ تا ۹ بخش؛ بخش سؤالات متداول در انتها؛ هر بخش هدف مشخص
faq: آرایه‌ای از {question, answer_hint}
schema_types: آرایه‌ای از نوع اسکیما پیشنهادی (مثل FAQPage, Service, Article)""",
     "variables": ["keyword", "intent", "brief", "research"], "model_hints": {"tier": "fast", "temperature": 0.3, "max_tokens": 1500}},
    {"key": "agent.writer_section", "scope": "agent", "title": "Writer Agent (per section) v1", "description": "نگارش یک بخش از مقاله",
     "template": """{{memory_pack}}

مقاله: «{{h1}}» — کلمه کلیدی هدف: «{{keyword}}» (اینتنت {{intent}}).
ساختار کلی مقاله (برای پیوستگی، فقط این بخش را بنویس): {{outline_summary}}
بخش موردنظر: H2 = «{{h2}}»
هدف بخش: {{goal}}
H3های این بخش: {{h3}}
موجودیت‌هایی که باید در این بخش بیایند: {{entities}}
کلمات کلیدی مرتبط برای پوشش طبیعی: {{keywords}}
واقعیت‌های مجاز (فقط این‌ها): {{facts}}
لینک‌های داخلی که می‌توانی با انکر مشخص در متن بگذاری: {{internal_links}}
حداقل کلمات: {{target_words}}

قواعد: فارسی روان؛ پاراگراف‌های ۴۰ تا ۹۰ کلمه‌ای؛ بدون کلیشه («در این مقاله…»)؛ بدون ادعای ممنوع؛ CTA طبق قواعد سایت فقط اگر برای این بخش مناسب است؛ لینک‌ها به شکل [انکر](URL).
خروجی JSON با کلیدها:
markdown: متن بخش با «## {{h2}}» در ابتدا و «### …» برای H3ها
word_count: عدد
entities_used: آرایه
links_used: آرایه‌ای از {anchor, url}""",
     "variables": ["h1", "keyword", "intent", "outline_summary", "h2", "goal", "h3", "entities", "keywords", "facts", "internal_links", "target_words"], "model_hints": {"tier": "quality", "temperature": 0.5, "max_tokens": 2200}},
    {"key": "agent.fact_check", "scope": "agent", "title": "Fact Check Agent v1", "description": "ادعاهای بی‌پشتوانه، دقت فنی، مشخصات خودرو، ادعاهای ممنوع",
     "template": """{{memory_pack}}

متن بخش زیر را راستی‌آزمایی کن. واقعیت‌های مجاز (تنها منبع معتبر): {{facts}}
مشخصات/موجودیت‌های شناخته‌شده سایت: {{entities}}
متن:
{{markdown}}

بررسی کن:
1) ادعاهای بی‌پشتوانه (عدد، آمار، قول، مقایسه) که در واقعیت‌های مجاز نیست
2) دقت فنی و مشخصات خودرو/خدمت (مدل، سال، قطعه، زمان، هزینه) — هر مورد نامطمئن را علامت بزن
3) ادعاهای ممنوع سایت
خروجی JSON با کلیدها:
verdict: "pass" | "revise"
issues: آرایه‌ای از {type: unsupported|technical|spec|forbidden, quote, why, fix}
safe_rewrite: نسخه اصلاح‌شده متن اگر revise (فقط جمله‌های مشکل‌دار عوض شود)، وگرنه رشته خالی""",
     "variables": ["facts", "entities", "markdown"], "model_hints": {"tier": "reasoning", "temperature": 0.1, "max_tokens": 1800}},
    {"key": "agent.seo", "scope": "agent", "title": "SEO Agent v1", "description": "عنوان/متا/پوشش کلمه کلیدی/اسکیما",
     "template": """{{memory_pack}}

مقاله زیر برای «{{keyword}}» (اینتنت {{intent}}) نوشته شده. کلمات هم‌خوشه: {{cluster_keywords}}
متن (خلاصه ساختاری): {{outline_summary}}
مقدمه: {{intro}}

خروجی JSON با کلیدها:
title_options: ۳ عنوان سئو (≤ ۶۰ نویسه، شامل کلمه کلیدی، متمایز)
meta_options: ۲ توضیحات متا (۱۲۰–۱۶۰ نویسه، با CTA طبق قواعد سایت)
keyword_coverage_fixes: آرایه‌ای از پیشنهاد کوتاه برای پوشش بهتر کلمات هم‌خوشه (بدون تکرار مصنوعی)
schema_jsonld: شیء JSON-LD مناسب (فقط با داده‌های واقعی؛ فیلد ناشناخته را حذف کن)""",
     "variables": ["keyword", "intent", "cluster_keywords", "outline_summary", "intro"], "model_hints": {"tier": "reasoning", "temperature": 0.2, "max_tokens": 1500}},
    {"key": "agent.linking", "scope": "agent", "title": "Linking Agent v1", "description": "جایگذاری لینک‌های داخلی پیشنهادی در متن",
     "template": """{{memory_pack}}

متن مقاله (Markdown): {{markdown}}
لینک‌های داخلی پیشنهادی موتور لینک‌سازی (انکر، URL، دلیل): {{link_candidates}}

برای هر لینک، اگر جای طبیعی دارد، جمله‌ای از متن را نشان بده که می‌توان انکر را در آن گذاشت (یا یک جمله کوتاه پیشنهاد بده). حداکثر {{max_links}} لینک؛ انکرها متنوع و توصیفی؛ هیچ لینکی به بیرون از فهرست اضافه نکن.
خروجی JSON با کلیدها:
links: آرایه‌ای از {anchor, url, section_h2, sentence, action: "replace"|"insert"}""",
     "variables": ["markdown", "link_candidates", "max_links"], "model_hints": {"tier": "fast", "temperature": 0.2, "max_tokens": 1200}},
    {"key": "agent.reviewer", "scope": "agent", "title": "Reviewer Agent v1", "description": "بازبینی نهایی نسبت به بریف و قواعد؛ فقط پیشنهاد",
     "template": """{{memory_pack}}

بریف: {{brief}}
یافته‌های موتور قواعد (قبلاً بررسی شده، تکرار نکن): {{rule_findings}}
متن مقاله: {{markdown}}

بازبینی کن و فقط پیشنهاد بده (متن را بازنویسی نکن مگر در rewrite_proposals و فقط برای پاراگراف‌های مشکل‌دار).
خروجی JSON با کلیدها:
findings: آرایه‌ای از {code, severity: high|medium|low, area: structure|entities|quality|seo|intent|cta, message_fa, evidence, suggestion_fa}
rewrite_proposals: آرایه‌ای از {section_h2, paragraph_index, text}
summary_fa: یک جمله""",
     "variables": ["brief", "rule_findings", "markdown"], "model_hints": {"tier": "reasoning", "temperature": 0.2, "max_tokens": 1800}},
    {"key": "task.rewrite", "scope": "task", "title": "بازنویسی پاراگراف v1", "description": "بازنویسی یک پاراگراف طبق یافته",
     "template": """{{memory_pack}}

پاراگراف: {{paragraph}}
مشکل: {{issue}}
پاراگراف را با حفظ واقعیت‌ها بازنویسی کن. خروجی JSON با کلید text.""",
     "variables": ["paragraph", "issue"], "model_hints": {"tier": "fast", "temperature": 0.4, "max_tokens": 600}},
    {"key": "task.title_meta", "scope": "task", "title": "عنوان و متا v1", "description": "تولید گزینه‌های عنوان/متا",
     "template": """{{memory_pack}}

برای صفحه‌ای درباره «{{keyword}}» (اینتنت {{intent}}) ۳ عنوان (≤۶۰ نویسه) و ۲ توضیحات متا (۱۲۰–۱۶۰) بده. خروجی JSON با کلیدهای titles و metas.""",
     "variables": ["keyword", "intent"], "model_hints": {"tier": "fast", "temperature": 0.5, "max_tokens": 500}},
    {"key": "task.article_test", "scope": "task", "title": "تولید مقاله کامل (فضای آزمایش) v1", "description": "تولید یک مقاله کامل در یک فراخوانی برای فضای آزمایش تولید محتوا — پایه عامل نگارش آینده",
     "template": """{{memory_pack}}

یک محتوای کامل و ساخت‌یافته بنویس.
- عنوان کاری: «{{title}}»
- کلمه کلیدی اصلی: «{{keyword}}» (اینتنت: {{intent}})
- کلمات کلیدی ثانویه: {{secondary_keywords}}
- نوع محتوا: {{content_type}} · دسته: {{category}} · مخاطب هدف: {{audience}} · لحن: {{tone}}
- طول هدف: حدود {{word_count}} کلمه
- دستورالعمل‌های اضافی: {{instructions}}

الزامات: کلمه کلیدی اصلی در عنوان، H1، پاراگراف اول و حداقل یک H2؛ کلمات ثانویه به‌صورت طبیعی؛ ۴ تا ۸ بخش H2 (در صورت نیاز H3)؛ پاراگراف‌های کوتاه؛ بخش سؤالات متداول (۳ تا ۶ پرسش)؛ پیشنهاد ۳ تا ۶ لینک داخلی (انکر + موضوع صفحه مقصد)؛ هیچ ادعای ممنوع یا بی‌پشتوانه؛ فقط از اطلاعات همین پرامپت و حافظه سایت استفاده کن و اعداد/مشخصات را حدس نزن.
خروجی را فقط به‌صورت JSON با فیلدهای زیر بده: title, meta_description, h1, sections (آرایه‌ای از {h2, h3: [], paragraphs: []}), faq (آرایه‌ای از {question, answer}), internal_links (آرایه‌ای از {anchor, target_topic}), keywords_used (آرایه رشته), notes.""",
     "variables": ["title", "keyword", "intent", "secondary_keywords", "content_type", "category", "audience", "tone", "word_count", "instructions"], "model_hints": {"tier": "quality", "temperature": 0.4, "max_tokens": 4000}},
]
