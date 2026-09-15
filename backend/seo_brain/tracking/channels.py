"""Channel classification for a first-party visit.

Google strips the search term from the referrer (100% since 2013, and since Chrome 85 the browser's own
default `strict-origin-when-cross-origin` policy truncates it to the origin anyway), so a referrer tells us
WHICH engine sent the visit and nothing more. The keyword itself is only recoverable for paid traffic, via
gclid -> Google Ads API click_view. Everything organic is page-level at best.

The one thing an in-house tracker buys us here: the Iranian engines (Zarebin, Gerdoo, Yooz) are in no
off-the-shelf analytics tool's search-engine list, so every packaged product files their traffic as
"referral". Here they are classified as organic.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

CHANNELS = ("organic", "paid", "referral", "social", "direct")

# host suffix -> engine name. Matched on the registrable tail so google.com / google.de / www.google.co.uk all hit.
SEARCH_ENGINES: dict[str, str] = {
    "google.": "google",
    "bing.com": "bing",
    "duckduckgo.com": "duckduckgo",
    "search.brave.com": "brave",
    "yandex.": "yandex",
    "search.yahoo.": "yahoo",
    "ecosia.org": "ecosia",
    "qwant.com": "qwant",
    "startpage.com": "startpage",
    "mojeek.com": "mojeek",
    "baidu.com": "baidu",
    "search.naver.com": "naver",
    "seznam.cz": "seznam",
    # Iranian engines — absent from Matomo's SearchEngines.yml and from every packaged analytics tool
    "zarebin.ir": "zarebin",
    "gerdoo.me": "gerdoo",
    "gerdoo.ir": "gerdoo",
    "yooz.ir": "yooz",
    "parsijoo.ir": "parsijoo",
}

SOCIAL_HOSTS: dict[str, str] = {
    "instagram.com": "instagram",
    "t.me": "telegram",
    "telegram.me": "telegram",
    "web.telegram.org": "telegram",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "facebook.com": "facebook",
    "linkedin.com": "linkedin",
    "aparat.com": "aparat",
    "youtube.com": "youtube",
    "pinterest.com": "pinterest",
    "whatsapp.com": "whatsapp",
    "wa.me": "whatsapp",
}

PAID_MEDIUMS = {"cpc", "ppc", "paidsearch", "paid", "cpm", "cpv", "cpa", "display", "banner"}
ORGANIC_MEDIUMS = {"organic", "seo"}
SOCIAL_MEDIUMS = {"social", "social-network", "social-media", "sm", "social_network"}


def host_of(url: str | None) -> str:
    """Bare hostname of a referrer URL, lowercased, without a leading www."""
    if not url:
        return ""
    try:
        h = (urlparse(url if "//" in url else f"//{url}").hostname or "").lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def search_engine_of(host: str) -> str:
    """Engine name for a referrer host, or '' when the host is not a known search engine."""
    if not host:
        return ""
    for needle, name in SEARCH_ENGINES.items():
        if needle.endswith("."):          # 'google.' -> match google.com, google.de, www.google.co.uk
            if host == needle[:-1] or host.startswith(needle) or f".{needle}" in f".{host}":
                return name
        elif host == needle or host.endswith(f".{needle}"):
            return name
    return ""


def social_of(host: str) -> str:
    if not host:
        return ""
    for needle, name in SOCIAL_HOSTS.items():
        if host == needle or host.endswith(f".{needle}"):
            return name
    return ""


def params_of(url: str | None) -> dict[str, str]:
    """utm_* / gclid from the landing URL's query string. First value wins; everything is trimmed and capped."""
    if not url or "?" not in url:
        return {}
    try:
        q = parse_qs(urlparse(url).query, keep_blank_values=False)
    except ValueError:
        return {}
    wanted = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "gbraid", "wbraid")
    return {k: str(q[k][0])[:200] for k in wanted if q.get(k)}


def classify(referrer: str | None, landing_url: str | None, site_host: str = "") -> dict[str, str]:
    """Resolve {channel, search_engine, referrer_host, utm_*, gclid} for one visit.

    Order matters: an explicit paid marker beats a referrer, because an ad click still arrives with
    google.com as its referrer and would otherwise be counted as organic.
    """
    p = params_of(landing_url)
    ref_host = host_of(referrer)
    if site_host and (ref_host == site_host or ref_host.endswith(f".{site_host}")):
        ref_host = ""                     # same-site navigation is not a referrer

    medium = p.get("utm_medium", "").lower()
    engine = search_engine_of(ref_host)
    out = {
        "referrer_host": ref_host,
        "search_engine": engine,
        "utm_source": p.get("utm_source", ""),
        "utm_medium": p.get("utm_medium", ""),
        "utm_campaign": p.get("utm_campaign", ""),
        "utm_term": p.get("utm_term", ""),
        "gclid": p.get("gclid") or p.get("gbraid") or p.get("wbraid") or "",
    }

    if out["gclid"] or medium in PAID_MEDIUMS:
        out["channel"] = "paid"
    elif medium in ORGANIC_MEDIUMS or engine:
        out["channel"] = "organic"
    elif medium in SOCIAL_MEDIUMS or social_of(ref_host):
        out["channel"] = "social"
    elif ref_host:
        out["channel"] = "referral"
    else:
        out["channel"] = "direct"
    return out


def device_of(user_agent: str | None) -> str:
    """Coarse device class from the UA string. Coarse on purpose — we store no fingerprint."""
    ua = (user_agent or "").lower()
    if not ua:
        return "desktop"
    if "ipad" in ua or ("tablet" in ua and "mobile" not in ua) or ("android" in ua and "mobile" not in ua):
        return "tablet"
    if "mobi" in ua or "iphone" in ua or "ipod" in ua or "windows phone" in ua:
        return "mobile"
    return "desktop"


BOT_MARKERS = ("bot", "spider", "crawl", "slurp", "curl/", "wget", "python-requests", "httpx", "headlesschrome",
               "lighthouse", "pingdom", "uptimerobot", "facebookexternalhit", "preview", "monitoring")


def is_bot(user_agent: str | None) -> bool:
    ua = (user_agent or "").lower()
    return not ua or any(m in ua for m in BOT_MARKERS)
