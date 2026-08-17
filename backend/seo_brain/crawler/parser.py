"""HTML parsing for SEO signals. Pure functions; no I/O."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

_WS = re.compile(r"\s+")


def _clean(s: str | None) -> str:
    return _WS.sub(" ", (s or "")).strip()


@dataclass
class LinkOut:
    href: str          # absolute, un-normalized
    anchor: str
    rel: str
    is_nav: bool
    position: int


@dataclass
class ParsedPage:
    title: str | None = None
    meta_description: str | None = None
    h1: list[str] = field(default_factory=list)
    h2: list[str] = field(default_factory=list)
    canonical: str | None = None
    robots_meta: str | None = None
    language: str | None = None
    word_count: int = 0
    text: str = ""
    images: list[dict] = field(default_factory=list)
    links: list[LinkOut] = field(default_factory=list)
    ld_json: list[dict] = field(default_factory=list)
    schema_types: list[str] = field(default_factory=list)
    has_microdata: bool = False
    content_hash: str = ""


def _schema_types(blocks: list[dict]) -> list[str]:
    out: list[str] = []

    def walk(o):
        if isinstance(o, dict):
            t = o.get("@type")
            if isinstance(t, str):
                out.append(t)
            elif isinstance(t, list):
                out.extend([x for x in t if isinstance(x, str)])
            for k, v in o.items():
                if k == "@graph" or isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(blocks)
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def parse_html(html: str, base_url: str) -> ParsedPage:
    soup = BeautifulSoup(html, "lxml")
    p = ParsedPage()
    if soup.title and soup.title.string:
        p.title = _clean(soup.title.string)
    md = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if md and md.get("content"):
        p.meta_description = _clean(md["content"])
    rb = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
    if rb and rb.get("content"):
        p.robots_meta = _clean(rb["content"])
    can = soup.find("link", rel=lambda v: v and "canonical" in [x.lower() for x in (v if isinstance(v, list) else [v])])
    if can and can.get("href"):
        p.canonical = urljoin(base_url, can["href"].strip())
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        p.language = html_tag["lang"]
    p.h1 = [_clean(h.get_text(" ")) for h in soup.find_all("h1")]
    p.h2 = [_clean(h.get_text(" ")) for h in soup.find_all("h2")]

    # structured data
    for s in soup.find_all("script", type=re.compile(r"application/ld\+json", re.I)):
        raw = s.string or s.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
            p.ld_json.append(obj)
        except json.JSONDecodeError:
            try:
                obj = json.loads(re.sub(r"[\x00-\x1f]", " ", raw))
                p.ld_json.append(obj)
            except json.JSONDecodeError:
                pass
    p.schema_types = _schema_types(p.ld_json)
    p.has_microdata = bool(soup.find(attrs={"itemscope": True}))

    # links (record nav vs body)
    pos = 0
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            continue
        absu = urljoin(base_url, href)
        if not absu.startswith(("http://", "https://")):
            continue
        is_nav = a.find_parent(["nav", "header", "footer"]) is not None
        rel = " ".join(a.get("rel", [])) if a.get("rel") else ""
        anchor = _clean(a.get_text(" ")) or _clean(a.get("title") or "")
        if not anchor:
            img = a.find("img")
            if img is not None:
                anchor = _clean(img.get("alt") or "")
        pos += 1
        p.links.append(LinkOut(href=absu, anchor=anchor[:300], rel=rel, is_nav=is_nav, position=pos))

    # images
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src:
            continue
        p.images.append({"src": urljoin(base_url, src.strip()), "alt": _clean(img.get("alt")) if img.has_attr("alt") else None})

    # visible text + hash (strip boilerplate tags)
    for t in soup(["script", "style", "noscript", "template", "svg"]):
        t.decompose()
    body = soup.body or soup
    main = body.find("main") or body.find("article") or body
    text = _clean(main.get_text(" "))
    p.text = text
    p.word_count = len(text.split())
    p.content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return p
