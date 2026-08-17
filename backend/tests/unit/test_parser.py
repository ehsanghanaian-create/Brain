from seo_brain.crawler.parser import parse_html

HTML = """<!doctype html><html lang="fa-IR"><head><title> امداد   خودرو </title>
<meta name="description" content="توضیح">
<meta name="robots" content="index, follow, max-snippet:-1">
<link rel="canonical" href="/mvm/">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"WebPage","@id":"https://x/#webpage"},{"@type":["Organization","LocalBusiness"],"@id":"https://x/#org"}]}</script>
</head><body>
<header><nav><a href="/">خانه</a><a href="/mvm/">MVM</a></nav></header>
<main><h1>امداد خودرو ام وی ام</h1><h2>خدمات</h2><p>متن متن متن <a href="https://emdadmodiran.com/blog/x/?utm_source=a">لینک</a>
<a href="https://google.com/">گوگل</a><a href="#top">top</a><a href="mailto:a@b.c">m</a></p>
<img src="/a.png" alt="alt"><img src="/b.png"></main>
<footer><a href="/mvm2/" rel="nofollow">چری</a></footer>
<script>var x=1;</script></body></html>"""


def test_parse_basics():
    p = parse_html(HTML, "https://emdadmodiran.com/")
    assert p.title == "امداد خودرو"
    assert p.meta_description == "توضیح"
    assert p.robots_meta.startswith("index")
    assert p.canonical == "https://emdadmodiran.com/mvm/"
    assert p.language == "fa-IR"
    assert p.h1 == ["امداد خودرو ام وی ام"]
    assert p.h2 == ["خدمات"]


def test_links_and_nav_flag():
    p = parse_html(HTML, "https://emdadmodiran.com/")
    hrefs = [l.href for l in p.links]
    assert "https://emdadmodiran.com/" in hrefs
    assert "https://google.com/" in hrefs
    assert not any(h.startswith(("mailto:", "#")) for h in hrefs)
    nav = [l for l in p.links if l.is_nav]
    assert len(nav) == 3  # 2 in nav + 1 in footer
    foot = [l for l in p.links if l.href.endswith("/mvm2/")][0]
    assert foot.rel == "nofollow" and foot.anchor == "چری"


def test_schema_and_images_and_hash():
    p = parse_html(HTML, "https://emdadmodiran.com/")
    assert p.schema_types == ["WebPage", "Organization", "LocalBusiness"]
    assert len(p.images) == 2 and p.images[1]["alt"] is None
    assert p.word_count > 0 and len(p.content_hash) == 64
    p2 = parse_html(HTML.replace("متن متن متن", "متن متن متن!"), "https://emdadmodiran.com/")
    assert p2.content_hash != p.content_hash
