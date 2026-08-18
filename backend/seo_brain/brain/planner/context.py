"""PlannerContext — one read of everything the planner rules need (keywords, clusters, GSC, graph pages/entities/categories,
content items, plans). Built per request; cheap for the sizes this local system handles (thousands of rows)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote

from sqlalchemy import Engine, text

from ...brain.keywords.normalize import normalize_keyword, tokenize
from ...brain.keywords.repository import Keyword, KeywordsRepository
from ...normalizer.url import normalize_url
from .repository import ContentPlan, PlannerRepository

QUESTION_WORDS = ("چگونه", "چطور", "چرا", "چیست", "چیه", "علائم", "علت", "مشکل", "مشکلات", "راهنما", "آموزش", "how", "why", "what")
COMPARE_WORDS = ("مقایسه", "بهتر", "یا", "تفاوت", "vs", "فرق")
COMMERCIAL_WORDS = ("قیمت", "هزینه", "خرید", "تعرفه", "ارزان", "بهترین", "شماره", "تماس", "آنلاین", "فوری", "سفارش")
LOCAL_WORDS = ("تهران", "کرج", "اصفهان", "شیراز", "مشهد", "تبریز", "نزدیک", "غرب", "شرق", "شمال", "جنوب", "منطقه")


@dataclass
class PageRef:
    node_id: str
    url: str
    title: str
    node_type: str
    category_ids: set[int] = field(default_factory=set)
    entities: set[str] = field(default_factory=set)      # entity node ids
    tokens: set[str] = field(default_factory=set)
    gsc: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannerContext:
    site_id: str
    keywords: dict[int, Keyword]
    kw_by_norm: dict[str, Keyword]
    clusters: dict[str, dict[str, Any]]                    # cluster_id → {name, topic, keywords_count, members[]}
    gsc: dict[str, dict[str, Any]]                         # normalized query → aggregate (+ pages)
    pages: dict[str, PageRef]                              # node_id → page
    page_by_url: dict[str, str]                            # url_n → node_id
    entities: dict[str, dict[str, Any]]                    # node_id → {label, type, aliases, tokens}
    categories: list[dict[str, Any]]                       # content_categories rows
    cat_by_wp: dict[int, dict[str, Any]]
    cat_node: dict[int, str]                               # content_category id → graph node id
    content_items: list[dict[str, Any]]                    # id, title, target_keyword_id, cluster_id, status, url
    plans: list[ContentPlan]
    plan_keywords: dict[int, list[dict[str, Any]]]          # keyword_id → [{plan_id, role}]
    memory: dict[str, Any]

    # ---- helpers
    def keyword_of(self, text_or_id: str | int | None) -> Keyword | None:
        if text_or_id is None:
            return None
        if isinstance(text_or_id, int):
            return self.keywords.get(text_or_id)
        return self.kw_by_norm.get(normalize_keyword(str(text_or_id)))

    def entities_in(self, txt: str) -> list[dict[str, Any]]:
        toks = set(tokenize(txt or "", drop_stopwords=False))
        norm = normalize_keyword(txt or "")
        out = []
        for nid, e in self.entities.items():
            if e["tokens"] and (e["tokens"] <= toks or (len(e["label_n"]) > 2 and e["label_n"] in norm)):
                out.append({"node_id": nid, **{k: e[k] for k in ("label", "type")}})
        return out

    def ranking_pages(self, kw_norm: str) -> list[dict[str, Any]]:
        g = self.gsc.get(kw_norm)
        return list(g["pages"]) if g else []

    def cluster_members(self, cluster_id: str | None) -> list[Keyword]:
        return [self.keywords[k] for k in (self.clusters.get(cluster_id or "", {}).get("members") or []) if k in self.keywords]

    def pages_in_category(self, cid: int) -> list[PageRef]:
        return [p for p in self.pages.values() if cid in p.category_ids]

    def guess_intent(self, kw: str) -> str:
        n = normalize_keyword(kw)
        if any(w in n for w in LOCAL_WORDS) and any(w in n for w in ("امداد", "خدمات", "تعمیر", "یدک", "نزدیک")):
            return "local"
        if any(w in n.split() for w in ("خرید", "سفارش", "شماره", "تماس", "فوری", "آنلاین")) or n.startswith("امداد") or "امداد" in n:
            return "transactional"
        if any(w in n for w in COMMERCIAL_WORDS) or any(w in n for w in COMPARE_WORDS):
            return "commercial"
        return "informational"


def build_planner_context(engine: Engine, site_id: str) -> PlannerContext:
    kw_repo = KeywordsRepository(engine)
    repo = PlannerRepository(engine)
    kws = kw_repo.all(site_id)
    keywords = {k.id: k for k in kws if k.id}
    kw_by_norm = {k.normalized: k for k in kws}
    clusters: dict[str, dict[str, Any]] = {}
    for c in kw_repo.list_clusters(site_id):
        clusters[c.cluster_id] = {"cluster_id": c.cluster_id, "name": c.name, "topic": c.topic, "keywords_count": c.keywords_count, "members": []}
    for k in kws:
        if k.cluster_id:
            clusters.setdefault(k.cluster_id, {"cluster_id": k.cluster_id, "name": k.keyword, "topic": k.topic, "keywords_count": 0, "members": []})["members"].append(k.id)
    gsc = kw_repo.gsc_by_normalized(site_id)
    categories = repo.list_categories(site_id)
    cat_by_wp = {c["wordpress_category_id"]: c for c in categories if c["wordpress_category_id"] is not None}
    pages: dict[str, PageRef] = {}
    page_by_url: dict[str, str] = {}
    entities: dict[str, dict[str, Any]] = {}
    cat_node: dict[int, str] = {}
    cat_node_to_id: dict[str, int] = {}
    with engine.connect() as cx:
        rows = cx.execute(text("SELECT node_id, node_type, label, url, props FROM graph_nodes WHERE site_id=:s AND node_type IN ('PAGE','POST','CATEGORY','BRAND','MODEL','SERVICE','LOCATION')"), {"s": site_id}).all()
        for nid, nt, label, url, props in rows:
            p = json.loads(props or "{}")
            if nt in ("PAGE", "POST"):
                u = unquote(url or "")
                ref = PageRef(nid, u, label or u, nt, tokens=set(tokenize(f"{label or ''} {p.get('h1') or ''} {p.get('title') or ''}")))
                pages[nid] = ref
                if u:
                    page_by_url[normalize_url(u)] = nid
            elif nt == "CATEGORY":
                wp = p.get("wp_id")
                if wp is not None and int(wp) in cat_by_wp:
                    cid = int(cat_by_wp[int(wp)]["id"]); cat_node[cid] = nid; cat_node_to_id[nid] = cid
                else:   # manual/brain categories carry their node id in intelligence.graph_node_id
                    for c in categories:
                        if (c.get("intelligence") or {}).get("graph_node_id") == nid:
                            cat_node[c["id"]] = nid; cat_node_to_id[nid] = c["id"]
            else:
                ln = normalize_keyword(label or "")
                al = [normalize_keyword(a) for a in (p.get("aliases") or []) if a]
                entities[nid] = {"label": label, "label_n": ln, "type": nt, "aliases": al, "tokens": set(tokenize(label or "", drop_stopwords=False))}
        erows = cx.execute(text("SELECT source_id, target_id, edge_type FROM graph_edges WHERE site_id=:s AND edge_type IN ('BELONGS_TO','ABOUT','OFFERS')"), {"s": site_id}).all()
        for src, tgt, et in erows:
            if src in pages:
                if et == "BELONGS_TO" and tgt in cat_node_to_id:
                    pages[src].category_ids.add(cat_node_to_id[tgt])
                elif et in ("ABOUT", "OFFERS") and tgt in entities:
                    pages[src].entities.add(tgt)
        # entity match by label in title for pages without ABOUT edges
        for p in pages.values():
            if not p.entities:
                for nid, e in entities.items():
                    if e["tokens"] and e["tokens"] <= p.tokens:
                        p.entities.add(nid)
        items = [dict(r._mapping) for r in cx.execute(text("SELECT id, title, target_keyword_id, target_keyword, cluster_id, status, url, priority, publish_date FROM content_items WHERE site_id=:s"), {"s": site_id}).all()]
        mem = cx.execute(text("SELECT successful_patterns, audience, business_rules FROM site_memory WHERE site_id=:s"), {"s": site_id}).first()
    for g in gsc.values():
        for pg in g["pages"]:
            nid = page_by_url.get(normalize_url(unquote(pg["page"] or "")))
            pg["node_id"] = nid
            if nid:
                cur = pages[nid].gsc
                cur["impressions"] = cur.get("impressions", 0) + (pg["impressions"] or 0); cur["clicks"] = cur.get("clicks", 0) + (pg["clicks"] or 0)
    memory = {"successful_patterns": json.loads(mem[0] or "[]") if mem else [], "audience": json.loads(mem[1] or "{}") if mem else {}, "business_rules": json.loads(mem[2] or "[]") if mem else []}
    plans = repo.all_plans(site_id)
    return PlannerContext(site_id, keywords, kw_by_norm, clusters, gsc, pages, page_by_url, entities, categories, cat_by_wp, cat_node, items, plans, repo.keywords_map(site_id), memory)
