"""Category intelligence (phase 8.5): WordPress categories (read-only REST sync) + Brain topic categories (from keyword clusters)
+ manual categories, with per-category intelligence (pages, keywords, coverage, gaps, intents) and category suggestions with reasons.
Nothing is ever written to WordPress."""
from __future__ import annotations

from collections import Counter
from typing import Any, Callable
from urllib.parse import unquote

import httpx
from sqlalchemy import Engine, text

from ...brain.keywords.normalize import normalize_keyword, tokenize
from ...db.repositories.base import utcnow
from ...normalizer.url import normalize_url
from .context import PlannerContext, build_planner_context
from .repository import PlannerRepository, slugify

Fetch = Callable[[str, dict], tuple[Any, dict]]


def _default_fetch(url: str, params: dict) -> tuple[Any, dict]:
    r = httpx.get(url, params=params, timeout=30, headers={"User-Agent": "SEO-Brain-Planner/0.1 (read-only)"})
    r.raise_for_status()
    return r.json(), dict(r.headers)


class CategoryIntelligence:
    def __init__(self, engine: Engine, fetch: Fetch | None = None):
        self.engine = engine
        self.repo = PlannerRepository(engine)
        self.fetch = fetch or _default_fetch

    # ------------------------------------------------------------------ WordPress sync (read-only)
    def sync_wordpress(self, site_id: str, wp_url: str | None) -> dict[str, Any]:
        if not wp_url:
            raise ValueError("wordpress_not_configured")
        base = wp_url.rstrip("/") + "/wp-json/wp/v2/categories"
        terms: list[dict] = []
        page = 1
        while True:
            data, headers = self.fetch(base, {"per_page": 100, "page": page, "_fields": "id,name,slug,parent,count,link,description"})
            if not isinstance(data, list):
                raise ValueError("unexpected WordPress payload")
            terms.extend(data)
            total_pages = int(headers.get("x-wp-totalpages") or headers.get("X-WP-TotalPages") or 1)
            if page >= total_pages or not data:
                break
            page += 1
        now = utcnow()
        # 1) mirror into the v0.1 `categories` table so the graph builder / link engine keep seeing them
        with self.engine.begin() as cx:
            for t in terms:
                cx.execute(text("INSERT INTO categories(site_id, taxonomy, wp_id, name, slug, url, description, parent_wp_id, count, created_at, updated_at) "
                                "VALUES(:s,'category',:w,:n,:sl,:u,:d,:p,:c,:t,:t) ON CONFLICT(site_id, taxonomy, wp_id) DO UPDATE SET name=excluded.name, slug=excluded.slug, url=excluded.url, "
                                "description=excluded.description, parent_wp_id=excluded.parent_wp_id, count=excluded.count, updated_at=excluded.updated_at"),
                           {"s": site_id, "w": int(t["id"]), "n": t.get("name"), "sl": unquote(t.get("slug") or ""), "u": t.get("link"), "d": t.get("description"), "p": int(t.get("parent") or 0), "c": int(t.get("count") or 0), "t": now})
        # 2) content_categories (two passes: rows, then parents)
        ids: dict[int, int] = {}
        created = updated = 0
        existing = {c["wordpress_category_id"] for c in self.repo.list_categories(site_id, "wordpress")}
        for t in terms:
            wp = int(t["id"])
            row = self.repo.upsert_category(site_id, "wordpress", t.get("name") or f"category-{wp}", wordpress_category_id=wp, slug=unquote(t.get("slug") or "") or None,
                                            url=t.get("link"), description=t.get("description") or None, post_count=int(t.get("count") or 0), synced_at=now)
            ids[wp] = row["id"]
            created += 0 if wp in existing else 1; updated += 1 if wp in existing else 0
        for t in terms:
            parent = int(t.get("parent") or 0)
            self.repo.update_category(site_id, ids[int(t["id"])], parent_id=ids.get(parent) if parent else None)
        removed = 0
        seen = set(ids)
        for c in self.repo.list_categories(site_id, "wordpress"):
            if c["wordpress_category_id"] not in seen:
                self.repo.update_category(site_id, c["id"], metadata={**c["metadata"], "missing_in_wordpress": True, "missing_since": now}); removed += 1
        return {"source": "wordpress", "terms": len(terms), "created": created, "updated": updated, "missing": removed, "synced_at": now, "note": "فقط‌خواندنی — هیچ تغییری در وردپرس اعمال نمی‌شود"}

    def sync_from_local(self, site_id: str) -> dict[str, Any]:
        """Fallback when WordPress REST is unreachable: seed content_categories from the local `categories` snapshot (v0.1 sync-wordpress)."""
        with self.engine.connect() as cx:
            rows = cx.execute(text("SELECT wp_id, name, slug, url, description, parent_wp_id, count FROM categories WHERE site_id=:s AND taxonomy='category' ORDER BY wp_id"), {"s": site_id}).all()
        if not rows:
            raise ValueError("no_local_snapshot")
        now = utcnow()
        ids: dict[int, int] = {}
        for wp, name, slug, url, desc, parent, count in rows:
            row = self.repo.upsert_category(site_id, "wordpress", name or f"category-{wp}", wordpress_category_id=int(wp), slug=unquote(slug or "") or None, url=url, description=desc or None, post_count=int(count or 0), synced_at=now,
                                            metadata={"source_detail": "local_snapshot"})
            ids[int(wp)] = row["id"]
        for r in rows:
            parent = int(r[5] or 0)
            self.repo.update_category(site_id, ids[int(r[0])], parent_id=ids.get(parent) if parent else None)
        return {"source": "wordpress", "via": "local_snapshot", "terms": len(rows), "synced_at": now, "note": "REST وردپرس در دسترس نبود — از آخرین همگام‌سازی محلی استفاده شد"}

    # ------------------------------------------------------------------ Brain topic categories from keyword clusters
    def sync_brain(self, site_id: str, min_keywords: int = 3) -> dict[str, Any]:
        ctx = build_planner_context(self.engine, site_id)
        made = 0
        for cid, c in ctx.clusters.items():
            n = len(c["members"])
            if n < min_keywords:
                continue
            name = c.get("topic") or c.get("name") or cid
            wp_match = self._best_wp_match(ctx, name, [ctx.keywords[k] for k in c["members"] if k in ctx.keywords])
            row = self.repo.upsert_category(site_id, "brain", name, slug=f"topic-{cid}", keyword_count=n,
                                            metadata={"keyword_cluster_id": cid, "related_wp_category_id": wp_match["id"] if wp_match else None, "related_wp_category": wp_match["name"] if wp_match else None},
                                            intelligence={"clusters": [cid], "graph_node_id": f"category:brain:topic-{cid}"})
            made += 1
        return {"source": "brain", "categories": made, "min_keywords": min_keywords}

    def _best_wp_match(self, ctx: PlannerContext, name: str, members: list) -> dict[str, Any] | None:
        best, best_s = None, 0.0
        for c in ctx.categories:
            if c["source"] != "wordpress":
                continue
            s = self._score_category(ctx, c, name, members)["score"]
            if s > best_s:
                best, best_s = c, s
        return best if best_s >= 0.3 else None

    # ------------------------------------------------------------------ analysis
    def analyze(self, site_id: str, ctx: PlannerContext | None = None) -> dict[str, Any]:
        ctx = ctx or build_planner_context(self.engine, site_id)
        out = []
        plan_counts = Counter(p.category_id for p in ctx.plans if p.category_id)
        gap_seen: set[int] = set()
        for c in sorted(ctx.categories, key=lambda c: (c["source"] != "wordpress", c["name"])):   # WP categories first so gaps attach to real categories
            related = self._related_keywords(ctx, c)
            pages = ctx.pages_in_category(c["id"]) if c["source"] == "wordpress" else self._brain_pages(ctx, c, related)
            page_ids = {p.node_id for p in pages}
            covered, gaps = [], []
            for k in related:
                pgs = ctx.ranking_pages(k.normalized)
                cov = any(pg.get("node_id") in page_ids and (pg.get("position") or 99) <= 30 for pg in pgs) or bool(k.target_url and ctx.page_by_url.get(normalize_url(k.target_url)) in page_ids)
                (covered if cov else gaps).append(k)
            intents = Counter(k.intent or ctx.guess_intent(k.keyword) for k in related)
            clusters = Counter(k.cluster_id for k in related if k.cluster_id)
            coverage = round(100 * len(covered) / len(related), 1) if related else None
            gaps.sort(key=lambda k: -(k.volume or 0))
            intel = {**(c.get("intelligence") or {}),
                     "clusters": [x for x, _ in clusters.most_common(10)], "intents": dict(intents), "top_keywords": [{"id": k.id, "keyword": k.keyword, "volume": k.volume, "intent": k.intent} for k in sorted(related, key=lambda k: -(k.volume or 0))[:15]],
                     "gaps": [{"id": k.id, "keyword": k.keyword, "volume": k.volume, "intent": k.intent or ctx.guess_intent(k.keyword)} for k in gaps[:15]],
                     "entities": sorted({e for p in pages for e in p.entities})[:20], "pages": [{"node_id": p.node_id, "url": p.url, "title": p.title} for p in pages[:50]],
                     "graph_node_id": ctx.cat_node.get(c["id"]) or (c.get("intelligence") or {}).get("graph_node_id"), "analyzed_at": utcnow()}
            self.repo.update_category(site_id, c["id"], page_count=len(pages), keyword_count=len(related), plan_count=int(plan_counts.get(c["id"], 0)), coverage_score=coverage, intelligence=intel)
            out.append({"id": c["id"], "name": c["name"], "source": c["source"], "pages": len(pages), "keywords": len(related), "coverage": coverage, "gaps": len(gaps)})
            # permanent gap recommendations (top 5 per category)
            for k in gaps[:5]:
                if k.id in ctx.plan_keywords or k.id in gap_seen:
                    continue
                gap_seen.add(k.id)
                self.repo.save_recommendation(site_id, "gap", {"action": "create_new", "title": k.keyword, "keyword_id": k.id, "keyword": k.keyword, "category_id": c["id"], "category": c["name"],
                                                               "intent": k.intent or ctx.guess_intent(k.keyword), "priority": k.priority or ("high" if (k.volume or 0) >= 500 else "medium"),
                                                               "priority_score": min(100.0, 40 + (k.volume or 0) / 20), "confidence": 0.6,
                                                               "reasons_fa": [f"شکاف محتوایی در دسته «{c['name']}»", f"کلمه «{k.keyword}» با هیچ صفحه‌ای از این دسته پوشش داده نشده", *( [f"حجم جستجو {k.volume}"] if k.volume else [])]},
                                              keyword_id=k.id, category_id=c["id"])
        return {"categories": out, "analyzed": len(out)}

    def _related_keywords(self, ctx: PlannerContext, c: dict[str, Any]) -> list:
        """Rules: name/slug tokens overlap · entity label match (brand/model/service/location) · cluster membership (brain) · GSC page in category."""
        toks = set(tokenize(c["name"] or "")) | set(t for t in (c.get("slug") or "").replace("-", " ").split() if len(t) > 1)
        name_n = normalize_keyword(c["name"] or "")
        ent_tokens: list[set[str]] = [e["tokens"] for e in ctx.entities.values() if e["label_n"] and (e["label_n"] == name_n or e["label_n"] in name_n or name_n in e["label_n"]) and e["tokens"]]
        cluster_ids = set((c.get("intelligence") or {}).get("clusters") or []) if c["source"] == "brain" else set()
        page_ids = {p.node_id for p in ctx.pages_in_category(c["id"])}
        out = []
        for k in ctx.keywords.values():
            kt = set(tokenize(k.keyword))
            hit = bool(toks and toks & kt) or any(et <= kt for et in ent_tokens) or (k.cluster_id in cluster_ids)
            if not hit and page_ids:
                hit = any(pg.get("node_id") in page_ids and (pg.get("position") or 99) <= 50 for pg in ctx.ranking_pages(k.normalized))
            if hit:
                out.append(k)
        return out

    def _brain_pages(self, ctx: PlannerContext, c: dict[str, Any], related: list) -> list:
        ids = set()
        for k in related:
            for pg in ctx.ranking_pages(k.normalized):
                if pg.get("node_id") and (pg.get("position") or 99) <= 30:
                    ids.add(pg["node_id"])
        return [ctx.pages[i] for i in ids if i in ctx.pages]

    # ------------------------------------------------------------------ suggestion (with reasons)
    def _score_category(self, ctx: PlannerContext, c: dict[str, Any], kw_text: str, members: list, intent: str | None = None) -> dict[str, Any]:
        intel = c.get("intelligence") or {}
        top_ids = {k["id"] for k in intel.get("top_keywords", [])} | {k["id"] for k in intel.get("gaps", [])}
        related_kw = self._related_keywords(ctx, c) if not top_ids else [ctx.keywords[i] for i in top_ids if i in ctx.keywords]
        member_ids = {k.id for k in members}
        kw_norm = normalize_keyword(kw_text)
        kt = set(tokenize(kw_text))
        # 1) keyword overlap: cluster members related to the category + direct token/entity match
        overlap = [k for k in related_kw if k.id in member_ids]
        name_n = normalize_keyword(c["name"] or "")
        direct = bool(set(tokenize(c["name"] or "")) & kt) or (len(name_n) > 2 and name_n in kw_norm)
        s_kw = min(1.0, len(overlap) / 8) * 0.8 + (0.2 if direct else 0)
        # 2) existing pages in category ranking for the keyword / cluster
        page_ids = {p["node_id"] for p in intel.get("pages", [])} or {p.node_id for p in ctx.pages_in_category(c["id"])}
        rank_pages = [pg for pg in ctx.ranking_pages(kw_norm) if pg.get("node_id") in page_ids]
        for k in members[:30]:
            rank_pages += [pg for pg in ctx.ranking_pages(k.normalized) if pg.get("node_id") in page_ids]
        n_pages = len({pg["node_id"] for pg in rank_pages})
        s_pages = min(1.0, n_pages / 5)
        # 3) intent match
        intents = intel.get("intents") or {}
        want = intent or ctx.guess_intent(kw_text)
        tot = sum(intents.values()) or 0
        s_intent = (intents.get(want, 0) / tot) if tot else (0.5 if direct else 0.0)
        # 4) graph proximity: shared entities between keyword and category pages/name
        ents = {e["node_id"] for e in ctx.entities_in(kw_text)}
        cat_ents = set(intel.get("entities") or []) | {nid for nid, e in ctx.entities.items() if e["label_n"] and (e["label_n"] == name_n or e["label_n"] in name_n)}
        s_graph = 1.0 if ents and ents & cat_ents else (0.5 if direct else 0.0)
        score = round(0.35 * s_kw + 0.25 * s_pages + 0.15 * s_intent + 0.25 * s_graph, 3)
        reasons = []
        if overlap or direct:
            reasons.append(f"{len(overlap) or 1} کلمه کلیدی مرتبط")
        if n_pages:
            reasons.append(f"{n_pages} صفحه موجود")
        if s_intent >= 0.5:
            reasons.append("اینتنت مشابه")
        if s_graph >= 1.0:
            reasons.append("رابطه گراف قوی")
        return {"id": c["id"], "name": c["name"], "source": c["source"], "score": score, "reasons_fa": reasons, "components": {"keywords": round(s_kw, 2), "pages": round(s_pages, 2), "intent": round(s_intent, 2), "graph": round(s_graph, 2)}}

    def suggest(self, site_id: str, keyword: str | None = None, keyword_id: int | None = None, plan_id: int | None = None, ctx: PlannerContext | None = None, top: int = 3) -> dict[str, Any]:
        ctx = ctx or build_planner_context(self.engine, site_id)
        intent = None
        if plan_id:
            p = next((x for x in ctx.plans if x.id == plan_id), None)
            keyword = keyword or (p.primary_keyword or p.title if p else None); intent = p.intent if p else None
        k = ctx.keyword_of(keyword_id) if keyword_id else ctx.keyword_of(keyword)
        kw_text = (k.keyword if k else keyword) or ""
        members = ctx.cluster_members(k.cluster_id) if k and k.cluster_id else ([k] if k else [])
        scored = [self._score_category(ctx, c, kw_text, members, intent or (k.intent if k else None)) for c in ctx.categories]
        scored = [s for s in scored if s["score"] > 0]
        scored.sort(key=lambda s: -s["score"])
        best = scored[0] if scored and scored[0]["score"] >= 0.2 else None
        return {"keyword": kw_text, "suggested": best, "candidates": scored[:top], "confidence": best["score"] if best else 0.0}
