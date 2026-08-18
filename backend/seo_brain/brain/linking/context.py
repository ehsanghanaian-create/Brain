"""LinkContext — everything the engine needs about a site, loaded once per run (graph + crawl + keywords + content)."""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlparse

from sqlalchemy import Engine, text

from ...brain.keywords.normalize import normalize_keyword, tokenize
from ...normalizer.url import normalize_url
from .journey import classify_stage


@dataclass
class PageInfo:
    node_id: str
    node_type: str                      # PAGE | POST | CATEGORY | CONTENT (planned)
    url: str
    url_n: str
    title: str
    h1: str = ""
    h2: list[str] = field(default_factory=list)
    text_tokens: set[str] = field(default_factory=set)      # title+h1+h2+meta (+ draft body for CONTENT)
    body_tokens: set[str] = field(default_factory=set)      # crawl body sample tokens when available (for anchor availability)
    word_count: int = 0
    indexable: bool = True
    status_code: int | None = 200
    pagerank: float = 0.0
    community: int | None = None
    entities: dict[str, str] = field(default_factory=dict)  # node_id → type
    entity_labels: dict[str, str] = field(default_factory=dict)
    clusters: set[str] = field(default_factory=set)         # keyword cluster ids
    topics: set[str] = field(default_factory=set)
    keywords: list[str] = field(default_factory=list)       # target keywords (explicit) + top GSC queries
    primary_keyword: str | None = None
    intent: str | None = None
    stage: str = "unknown"
    category_ids: set[str] = field(default_factory=set)
    gsc: dict[str, Any] = field(default_factory=dict)       # {impressions, clicks, position, top_queries[]}
    value: float = 0.0                                      # 0–1 how much this page matters (keyword priority, GSC)
    striking: bool = False                                  # position 4–20 on some query
    opportunities: list[str] = field(default_factory=list)  # keyword/seo opportunity kinds
    is_content_item: bool = False
    content_id: int | None = None
    published: bool = True


@dataclass
class LinkContext:
    site_id: str
    host: str
    pages: dict[str, PageInfo]                              # node_id → page
    by_url: dict[str, str]                                  # url_n → node_id
    links: dict[tuple[str, str], list[dict]]                # (src_id, tgt_id) → [{anchor, nav}]
    inbound: dict[str, list[dict]]                          # tgt_id → [{source_id, anchor, nav}]
    outbound: dict[str, list[dict]]                         # src_id → [{target_id, anchor, nav}]
    idf: dict[str, float]
    entity_type: dict[str, str]
    cluster_topic: dict[str, str]
    memory: dict[str, Any]
    settings: dict[str, Any]
    generic_anchors: set[str]

    def page_count(self) -> int:
        return len(self.pages)


DEFAULT_LINKING = {
    "weights": {"topic": 0.30, "entities": 0.20, "intent": 0.20, "authority": 0.15, "anchor": 0.15},
    "min_score": 0.45,
    "max_per_target": 5,
    "max_per_source": 3,
    "low_inbound_threshold": 2,
    "supports_min_topic": 0.6,
    "generic_anchors": ["اینجا", "کلیک کنید", "این لینک", "ادامه مطلب", "بیشتر بخوانید", "here", "click here", "read more", "link", "لینک"],
    "exclude_url_patterns": ["/tag/", "/page/", "?", "/feed", "/wp-"],
    "sync_threshold_pages": 500,
}

_GENERIC_TITLE_TOKENS = {"صفحه", "بلاگ", "وبلاگ", "خانه", "home", "blog", "page"}


def build_context(engine: Engine, site_id: str, settings: dict[str, Any] | None = None, memory: dict[str, Any] | None = None) -> LinkContext:
    st = {**DEFAULT_LINKING, **(settings or {})}
    with engine.connect() as cx:
        row = cx.execute(text("SELECT canonical_url FROM sites WHERE site_id=:s"), {"s": site_id}).first()
        host = (urlparse(row[0]).hostname or "").replace("www.", "") if row else ""
        nodes = cx.execute(text("SELECT node_id, node_type, label, url, props, pagerank, community FROM graph_nodes WHERE site_id=:s AND node_type IN ('PAGE','POST','CATEGORY') AND url IS NOT NULL"), {"s": site_id}).all()
        ents = {r[0]: (r[1], r[2]) for r in cx.execute(text("SELECT node_id, node_type, label FROM graph_nodes WHERE site_id=:s AND node_type IN ('BRAND','MODEL','SERVICE','LOCATION')"), {"s": site_id}).all()}
        edges = cx.execute(text("SELECT source_id, target_id, edge_type, props FROM graph_edges WHERE site_id=:s AND edge_type IN ('ABOUT','OFFERS','RANKS_FOR','KEYWORD_TARGETS','BELONGS_TO','HAS_CATEGORY')"), {"s": site_id}).all()
        queries = {r[0]: (r[1], json.loads(r[2] or "{}")) for r in cx.execute(text("SELECT node_id, label, props FROM graph_nodes WHERE site_id=:s AND node_type='QUERY'"), {"s": site_id}).all()}
        kws = {r[0]: {"keyword": r[1], "normalized": r[2], "cluster_id": r[3], "topic": r[4], "intent": r[5], "priority": r[6], "target_url": r[7]}
               for r in cx.execute(text("SELECT id, keyword, normalized, cluster_id, topic, intent, priority, target_url FROM keywords WHERE site_id=:s"), {"s": site_id}).all()}
        cluster_topic = {r[0]: (r[1] or r[2]) for r in cx.execute(text("SELECT cluster_id, topic, name FROM keyword_clusters WHERE site_id=:s"), {"s": site_id}).all()}
        crawl = {}
        try:
            for r in cx.execute(text("SELECT url, title, h1, h2, meta_description, word_count, indexable, status_code FROM pages WHERE site_id=:s"), {"s": site_id}).all():
                crawl[normalize_url(unquote(r[0]))] = {"title": r[1], "h1": r[2], "h2": r[3], "meta": r[4], "word_count": r[5], "indexable": r[6], "status_code": r[7]}
        except Exception:  # noqa: BLE001
            crawl = {}
        links_rows = []
        try:
            links_rows = cx.execute(text("SELECT source_url, target_url, anchor_text, is_nav FROM links WHERE site_id=:s AND is_internal=1"), {"s": site_id}).all()
        except Exception:  # noqa: BLE001
            pass
        gsc_pages: dict[str, dict] = defaultdict(lambda: {"impressions": 0, "clicks": 0, "_pw": 0.0, "queries": []})
        try:
            for page, query, clicks, imp, pos in cx.execute(text("SELECT page, query, clicks, impressions, position FROM gsc_query_page WHERE site_id=:s"), {"s": site_id}).all():
                g = gsc_pages[normalize_url(unquote(page))]
                g["impressions"] += imp or 0; g["clicks"] += clicks or 0; g["_pw"] += (pos or 0) * (imp or 0); g["queries"].append((query, imp or 0, pos))
        except Exception:  # noqa: BLE001
            pass
        kw_opps: dict[str, list[str]] = defaultdict(list)
        try:
            for url, kind in cx.execute(text("SELECT target_url, kind FROM keyword_opportunities WHERE site_id=:s AND status IN ('new','accepted') AND target_url IS NOT NULL"), {"s": site_id}).all():
                kw_opps[normalize_url(url)].append(kind)
        except Exception:  # noqa: BLE001
            pass
        content_rows = []
        try:
            content_rows = cx.execute(text("SELECT ci.id, ci.title, ci.status, ci.url, ci.target_keyword_id, ci.intent, ci.cluster_id, ci.topic, d.structure, d.body_text FROM content_items ci LEFT JOIN content_drafts d ON d.id = ci.current_draft_id WHERE ci.site_id=:s"), {"s": site_id}).all()
        except Exception:  # noqa: BLE001
            pass

    pages: dict[str, PageInfo] = {}
    by_url: dict[str, str] = {}
    excl = st.get("exclude_url_patterns", [])
    for nid, ntype, label, url, props, pr, comm in nodes:
        u = unquote(url); un = normalize_url(u)
        if any(x in un for x in excl):
            continue
        p = json.loads(props or "{}"); c = crawl.get(un, {})
        h2 = c.get("h2"); h2l = json.loads(h2) if isinstance(h2, str) and h2.startswith("[") else ([h2] if isinstance(h2, str) and h2 else (h2 or []))
        h1 = c.get("h1"); h1s = json.loads(h1) if isinstance(h1, str) and h1.startswith("[") else ([h1] if isinstance(h1, str) and h1 else (h1 or []))
        title = c.get("title") or p.get("title") or label or ""
        pi = PageInfo(node_id=nid, node_type=ntype, url=u, url_n=un, title=title, h1=(h1s[0] if h1s else ""), h2=[x for x in h2l if x],
                      word_count=int(c.get("word_count") or p.get("word_count") or 0), indexable=(c.get("indexable") if c.get("indexable") is not None else p.get("indexable", True)) not in (0, False),
                      status_code=c.get("status_code") or p.get("status_code") or 200, pagerank=float(pr or 0), community=comm)
        g = gsc_pages.get(un)
        if g:
            top = sorted(g["queries"], key=lambda q: -q[1])[:8]
            pi.gsc = {"impressions": g["impressions"], "clicks": g["clicks"], "position": round(g["_pw"] / g["impressions"], 1) if g["impressions"] else None, "top_queries": [q[0] for q in top]}
            pi.keywords.extend(q[0] for q in top[:3])
            pi.striking = any(q[2] is not None and 4 <= q[2] <= 20 and q[1] >= 5 for q in g["queries"])
        pi.opportunities = kw_opps.get(un, [])
        pages[nid] = pi; by_url[un] = nid
    # entities / clusters / categories via edges
    kw_by_url: dict[str, list[dict]] = defaultdict(list)
    for k in kws.values():
        if k["target_url"]:
            kw_by_url[normalize_url(k["target_url"])].append(k)
    for src, tgt, et, props in edges:
        if et in ("ABOUT", "OFFERS") and src in pages and tgt in ents:
            pages[src].entities[tgt] = ents[tgt][0]; pages[src].entity_labels[tgt] = ents[tgt][1]
        elif et == "RANKS_FOR" and src in pages and tgt in queries:
            qlabel = queries[tgt][0]
            nq = normalize_keyword(qlabel)
            for k in kws.values():
                if k["normalized"] == nq and k["cluster_id"]:
                    pages[src].clusters.add(k["cluster_id"])
                    if k["topic"] or cluster_topic.get(k["cluster_id"]): pages[src].topics.add(k["topic"] or cluster_topic[k["cluster_id"]])
                    if k["intent"] and not pages[src].intent: pages[src].intent = k["intent"]
        elif et == "KEYWORD_TARGETS" and tgt in pages and src.startswith("keyword:"):
            try:
                k = kws.get(int(src.split(":", 1)[1]))
            except ValueError:
                k = None
            if k:
                pages[tgt].keywords.insert(0, k["keyword"]); pages[tgt].primary_keyword = pages[tgt].primary_keyword or k["keyword"]
                if k["cluster_id"]: pages[tgt].clusters.add(k["cluster_id"])
                if k["topic"] or (k["cluster_id"] and cluster_topic.get(k["cluster_id"])): pages[tgt].topics.add(k["topic"] or cluster_topic[k["cluster_id"]])
                if k["intent"]: pages[tgt].intent = k["intent"]
                pages[tgt].value = max(pages[tgt].value, {"high": 1.0, "medium": 0.7, "low": 0.4}.get(k["priority"] or "", 0.5))
        elif et in ("BELONGS_TO", "HAS_CATEGORY"):
            a, b = (src, tgt) if et == "BELONGS_TO" else (tgt, src)
            if a in pages and b in pages and pages[b].node_type == "CATEGORY":
                pages[a].category_ids.add(b)
    for un, klist in kw_by_url.items():
        nid = by_url.get(un)
        if nid:
            for k in klist:
                if k["keyword"] not in pages[nid].keywords: pages[nid].keywords.insert(0, k["keyword"])
                pages[nid].primary_keyword = pages[nid].primary_keyword or k["keyword"]
                if k["cluster_id"]: pages[nid].clusters.add(k["cluster_id"])
                if k["intent"]: pages[nid].intent = pages[nid].intent or k["intent"]
    # planned content items (Content Brain) as future pages
    for cid, ctitle, cstatus, curl, kwid, cintent, ccl, ctopic, structure, body_text in content_rows:
        un = normalize_url(curl) if curl else None
        if un and un in by_url:
            pages[by_url[un]].content_id = cid; pages[by_url[un]].is_content_item = True
            continue
        nid = f"content:{cid}"
        st_json = json.loads(structure or "{}") if structure else {}
        pi = PageInfo(node_id=nid, node_type="CONTENT", url=curl or f"content://{cid}", url_n=un or f"content:{cid}", title=ctitle, h1=(st_json.get("h1") or [ctitle])[0], h2=st_json.get("h2", []),
                      indexable=True, pagerank=0.0, is_content_item=True, content_id=cid, published=cstatus == "published", intent=cintent)
        pi.body_tokens = set(tokenize(body_text or ""))
        k = kws.get(kwid) if kwid else None
        if k:
            pi.keywords.append(k["keyword"]); pi.primary_keyword = k["keyword"]; pi.value = 0.8
            if k["cluster_id"]: pi.clusters.add(k["cluster_id"])
        if ccl: pi.clusters.add(ccl)
        if ctopic: pi.topics.add(ctopic)
        pages[nid] = pi
    # tokens + IDF
    df: Counter = Counter()
    for p in pages.values():
        toks = set(tokenize(" ".join([p.title, p.h1] + p.h2 + p.keywords))) - _GENERIC_TITLE_TOKENS
        p.text_tokens = toks
        df.update(toks)
    n = max(1, len(pages))
    idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}
    # stage
    for p in pages.values():
        p.stage = classify_stage(p)
        if not p.value:
            p.value = min(1.0, 0.3 + (0.3 if p.striking else 0) + min(0.4, (p.gsc.get("impressions", 0) if p.gsc else 0) / 2000))
    # links
    links: dict[tuple[str, str], list[dict]] = defaultdict(list); inbound = defaultdict(list); outbound = defaultdict(list)
    for s_url, t_url, anchor, nav in links_rows:
        s = by_url.get(normalize_url(unquote(s_url or ""))); t = by_url.get(normalize_url(unquote(t_url or "")))
        if not s or not t or s == t:
            continue
        rec = {"anchor": (anchor or "").strip(), "nav": bool(nav)}
        links[(s, t)].append(rec); inbound[t].append({"source_id": s, **rec}); outbound[s].append({"target_id": t, **rec})
    return LinkContext(site_id=site_id, host=host, pages=pages, by_url=by_url, links=links, inbound=inbound, outbound=outbound, idf=idf,
                       entity_type={k: v[0] for k, v in ents.items()}, cluster_topic=cluster_topic, memory=memory or {}, settings=st,
                       generic_anchors={normalize_keyword(a) for a in st.get("generic_anchors", [])})
