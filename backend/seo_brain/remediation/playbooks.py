"""Versioned, allowlisted methods for every problem emitted by analysis.seo."""
from __future__ import annotations

VERSION = 1

ROADMAPS: dict[str, list[str]] = {
    "orphan": ["پوشش خزش و ایندکس‌پذیری صفحه را تأیید کن.", "صفحهٔ منبع مرتبطی که هنوز لینک نداده پیدا کن و عبارت موجود در متن را انتخاب کن.", "پس از تغییر، لینک بدنه و ورود صفحه به گراف را بسنج."],
    "no_body_inbound_links": ["منابع فعلی را از لینک ناوبری جدا کن.", "در متن صفحهٔ مرتبط لینک طبیعی بگذار.", "وجود لینک در بدنهٔ رندرشده را تأیید کن."],
    "low_inbound_links": ["تعداد منابع یکتای فعلی و آستانهٔ تحلیل را بخوان.", "منبع مرتبط بدون لینک تکراری انتخاب کن.", "پس از خزش دوباره، شمار منابع معتبر را با آستانه مقایسه کن."],
    "high_outbound_links": ["لینک‌های بدنه و قالب را تفکیک و ضرورت هر کدام را بررسی کن.", "فقط لینک زائد مشخص را حذف کن یا هاب را در قالب تقسیم کن؛ لینک ضروری را کورکورانه حذف نکن.", "تعداد خروجی‌ها و حفظ مسیرهای اصلی را بررسی کن."],
    "missing_h1": ["HTML نهایی و مالک تیتر را پیدا کن.", "در مالک واقعی خروجی یک H1 متناسب با هدف صفحه بساز.", "دقیقاً یک H1 رندرشده را تأیید کن."],
    "multiple_h1": ["H1 قالب را از H1 بدنه جدا کن.", "H1های اضافی بدنه را H2 کن یا تولید تکراری قالب را اصلاح کن.", "دقیقاً یک H1 و ترتیب منطقی تیترها را تأیید کن."],
    "duplicate_h1": ["صفحات مشترک و هدف جست‌وجوی هر کدام را مقایسه کن.", "برای همین صفحه H1 متمایز و دقیق یا الگوی قالب مناسب بساز.", "خروجی همهٔ صفحات درگیر را برای یکتایی بررسی کن."],
    "duplicate_title": ["عنوان رندرشده و صفحات هم‌عنوان را پیدا کن.", "عنوان SEO همین صفحه یا الگوی عنوان را متناسب با هدف آن اصلاح کن.", "یکتایی title در همهٔ صفحات درگیر را تأیید کن."],
    "missing_meta_description": ["مالک metadata را از HTML و کد سایت مشخص کن.", "توضیح متای مرتبط در فیلد SEO یا قالب ثبت کن؛ excerpt را جایگزین فرض نکن.", "تگ description در HTML نهایی را بررسی کن."],
    "images_missing_alt": ["تصاویر بدون alt را با src و متن پیرامونی مشخص کن.", "فقط با شواهد کافی alt توصیفی بده؛ برای تصویر تزئینی alt خالی را آگاهانه انتخاب کن.", "alt همهٔ تصاویر هدف را در HTML نهایی بررسی کن."],
    "missing_canonical": ["URL مرجع، redirect و ایندکس‌پذیری را بررسی کن.", "canonical درست را در مالک خروجی ثبت کن؛ self-canonical را بدون شاهد فرض نکن.", "تگ نهایی و پاسخ ۲۰۰ مقصد را تأیید کن."],
    "important_non_indexable": ["علت واقعی در robots، header، canonical، وضعیت پاسخ و sitemap را تشخیص بده.", "فقط مانعِ ناخواستهٔ تأییدشده را بردار.", "ایندکس‌پذیری طبق تصمیم انتخاب‌شده را دوباره بررسی کن."],
    "thin_content": ["هدف صفحه و اطلاعات تأییدشدهٔ سایت را جمع کن.", "پاسخ مفید و مستند اضافه کن؛ ادعای خدماتی یا عدد ساختگی نساز.", "کامل‌تر شدن واقعی محتوا و خروج هشدار را بررسی کن."],
    "redirect_in_sitemap": ["زنجیرهٔ redirect و مقصد نهایی را تأیید کن.", "URL قدیمی را در منبع سایت‌مپ جایگزین یا حذف کن.", "نبود URL قدیمی و پاسخ ۲۰۰ مقصد را بررسی کن."],
}

# kind determines the executor; the model may suggest a value, never a new operation.
# The second method is a source-controlled template option. It remains blocked until a
# site-specific release connector is configured and has passed its own preflight.
PLAYBOOKS: dict[str, tuple[dict, dict]] = {
    "orphan": ({"id": "context_link", "title": "لینک از متن صفحه مرتبط", "kind": "wp_insert_link", "uncertain": True,
                "verify": "لینک بدنه از صفحه منبع به صفحه هدف"},
               {"id": "template_link", "title": "افزودن به بخش مرتبط قالب", "kind": "frontend", "uncertain": True, "verify": "لینک داخلی در خروجی قالب"}),
    "no_body_inbound_links": ({"id": "context_link", "title": "لینک متنی مرتبط", "kind": "wp_insert_link", "uncertain": True,
                               "verify": "لینک ورودی در بدنه"},
                              {"id": "template_context_link", "title": "بخش محتوایی مشترک", "kind": "frontend", "uncertain": True, "verify": "لینک در بدنه صفحات متأثر"}),
    "low_inbound_links": ({"id": "context_link", "title": "لینک از صفحه مرتبط", "kind": "wp_insert_link", "uncertain": True,
                           "verify": "افزایش لینک‌های معتبر"},
                          {"id": "hub_link", "title": "پیوند در هاب موضوعی", "kind": "frontend", "uncertain": True, "verify": "افزایش لینک‌های ورودی"}),
    "high_outbound_links": ({"id": "remove_excess_link", "title": "حذف لینک زائد مشخص", "kind": "wp_remove_link", "uncertain": True,
                             "verify": "کاهش لینک خروجی بدون حذف لینک‌های ضروری"},
                            {"id": "split_hub", "title": "تقسیم فهرست قالب", "kind": "frontend", "uncertain": True, "verify": "کاهش لینک خروجی"}),
    "missing_h1": ({"id": "add_body_h1", "title": "افزودن H1 در محتوای صفحه", "kind": "wp_add_h1", "uncertain": True,
                    "verify": "دقیقاً یک H1 در صفحه"},
                   {"id": "template_h1", "title": "اصلاح تیتر قالب", "kind": "frontend", "uncertain": True, "verify": "دقیقاً یک H1 در صفحه"}),
    "multiple_h1": ({"id": "demote_body_h1", "title": "تبدیل H1های بدنه به H2", "kind": "wp_demote_h1", "uncertain": False,
                     "verify": "دقیقاً یک H1 در صفحه"},
                    {"id": "template_h1", "title": "اصلاح تیتر تکراری قالب", "kind": "frontend", "uncertain": True, "verify": "دقیقاً یک H1 در صفحه"}),
    "duplicate_h1": ({"id": "unique_h1", "title": "عنوان اختصاصی همین صفحه", "kind": "wp_title", "uncertain": True,
                      "verify": "H1 متمایز و مرتبط"},
                     {"id": "template_h1", "title": "اصلاح الگوی تیتر قالب", "kind": "frontend", "uncertain": True, "verify": "H1های متمایز صفحات درگیر"}),
    "duplicate_title": ({"id": "unique_meta_title", "title": "عنوان SEO اختصاصی", "kind": "wp_meta_title", "uncertain": True,
                        "verify": "عنوان رندرشده متمایز"},
                       {"id": "template_title", "title": "اصلاح الگوی عنوان قالب", "kind": "frontend", "uncertain": True, "verify": "عنوان‌های متمایز صفحات درگیر"}),
    "missing_meta_description": ({"id": "wp_meta_description", "title": "توضیح متای اختصاصی", "kind": "wp_meta_description", "uncertain": True,
                                  "verify": "توضیح متا در HTML نهایی"},
                                 {"id": "template_description", "title": "اصلاح metadata قالب", "kind": "frontend", "uncertain": True, "verify": "توضیح متا در HTML نهایی"}),
    "images_missing_alt": ({"id": "body_image_alt", "title": "توصیف تصاویر محتوایی", "kind": "wp_image_alt", "uncertain": True,
                            "verify": "alt مناسب تمام تصاویر هدف"},
                           {"id": "template_image_alt", "title": "اصلاح تصویر قالب", "kind": "frontend", "uncertain": True, "verify": "alt مناسب تصویر قالب"}),
    "missing_canonical": ({"id": "wp_canonical", "title": "ثبت URL مرجع صفحه", "kind": "wp_canonical", "uncertain": True,
                           "verify": "canonical معتبر و مقصد ۲۰۰"},
                          {"id": "template_canonical", "title": "اصلاح canonical قالب", "kind": "frontend", "uncertain": True, "verify": "canonical معتبر در خروجی"}),
    "important_non_indexable": ({"id": "remove_noindex", "title": "برداشتن noindex همین صفحه", "kind": "wp_noindex_off", "uncertain": True,
                                "verify": "صفحه طبق تصمیم قابل ایندکس"},
                               {"id": "template_indexability", "title": "اصلاح کنترل ایندکس قالب", "kind": "frontend", "uncertain": True, "verify": "رفع مانع ایندکس"}),
    "thin_content": ({"id": "expand_content", "title": "افزودن پاسخ مستند به صفحه", "kind": "wp_append_content", "uncertain": True,
                      "verify": "محتوای مفید و رفع هشدار خزش"},
                     {"id": "template_content", "title": "تکمیل بخش محتوایی قالب", "kind": "frontend", "uncertain": True, "verify": "محتوای کامل‌تر در خروجی"}),
    "redirect_in_sitemap": ({"id": "replace_sitemap_url", "title": "جایگزینی URL در سایت‌مپ", "kind": "frontend", "uncertain": True,
                             "verify": "URL قدیمی حذف و مقصد ۲۰۰"},
                            {"id": "remove_sitemap_url", "title": "حذف ورودی نامعتبر", "kind": "frontend", "uncertain": True, "verify": "URL ریدایرکت‌شونده حذف"}),
}


def methods_for(problem_type: str) -> list[dict]:
    return [dict(method) for method in PLAYBOOKS.get(problem_type, ())]
