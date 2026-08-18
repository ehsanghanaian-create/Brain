"""BriefGenerator — structured content brief from what the Brain already knows.

Sources (all real, all listed in `brief.sources`):
  keyword        the target keyword row (+ intent/priority/volume)
  cluster        sibling keywords of its cluster → H2 candidates
  gsc            GSC queries related to the keyword (position/impressions) → H2/H3 + questions
  existing_pages pages already ranking (GSC top pages, KEYWORD_TARGETS) → improve-vs-create hint, avoid cannibalization
  entities       BRAND/MODEL/SERVICE/LOCATION nodes whose label/aliases occur in the keyword or its cluster
  internal_links pages ABOUT those entities, keyword-opportunity `add_internal_links` rows, top-PageRank service pages
  competitors    not collected by the platform yet → reported as unavailable (never invented)
Deterministic first; when `use_ai=True` the orchestrator may refine H1/outline/questions (JSON-validated) and the
result carries provenance. Nothing here calls the network by itself.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote

from sqlalchemy import Engine, text

from ...ai import AIMessage, AIOrchestrator, AITask, TaskKind
from ...brain.keywords import KeywordsRepository, normalize_keyword, tokenize
from ...brain.keywords.repository import Keyword
from ...db.repositories.graph import GraphRepository
from ...normalizer.url import normalize_url
from .repository import ContentBrief, ContentItem

_QUESTION_MARKERS = ("چگونه", "چطور", "چرا", "چیست", "چیه", "کجا", "کدام", "آیا", "چند", "قیمت", "هزینه", "شماره", "بهترین", "how", "why", "what", "where", "which", "cost", "price", "best")
_INTENT_FA = {"informational": "اطلاعاتی", "navigational": "ناوبری", "commercial": "تجاری", "transactional": "تراکنشی", "local": "محلی"}


class BriefGenerator:
    def __init__(self, engine: Engine, orchestrator: AIOrchestrator | None = None):
        self.engine = engine
        self.kw = KeywordsRepository(engine)
        self.graph = GraphRepository(engine)
        self.orch = orchestrator

    # ------------------------------------------------------------------ public
    def generate(self, item: ContentItem, use_ai: bool = False) -> ContentBrief:
        site_id = item.site_id
        keyword = self._keyword(item)
        kw_text = item.target_keyword or (keyword.keyword if keyword else item.title)
        norm = normalize_keyword(kw_text)
        toks = set(tokenize(kw_text))
        cluster_members = self._cluster_members(site_id, keyword) if keyword else []
        gsc_all = self.kw.gsc_by_normalized(site_id)
        gsc_kw = gsc_all.get(norm)
        related_q = self._related_queries(gsc_all, toks, norm)
        existing = self._existing_pages(site_id, keyword, gsc_kw)
        entities = self._entities(site_id, toks | {t for m in cluster_members for t in tokenize(m.keyword)})
        links = self._internal_links(site_id, keyword, entities, existing)
        intent = item.intent or (keyword.intent if keyword else None) or self._guess_intent(kw_text)

        h1 = self._h1(kw_text, intent, entities)
        outline = self._outline(kw_text, intent, cluster_members, related_q, entities)
        questions = self._questions(related_q, kw_text, entities)
        seo_title = f"{h1} | {self._brand(site_id)}".strip(" |")[:70]
        meta = self._meta(kw_text, intent, entities)
        sources = {
            "keyword": {"id": keyword.id, "keyword": keyword.keyword, "intent": keyword.intent, "priority": keyword.priority, "volume": keyword.volume} if keyword else {"keyword": kw_text, "note": "not in keyword table"},
            "cluster": [{"id": m.id, "keyword": m.keyword} for m in cluster_members],
            "gsc": {"keyword": gsc_kw and {k: gsc_kw[k] for k in ("clicks", "impressions", "ctr", "position", "top_page")}, "related_queries": related_q[:20]},
            "existing_pages": existing,
            "competitors": {"available": False, "note": "داده رقبا هنوز جمع‌آوری نمی‌شود (فاز بعدی) — چیزی حدس زده نشد"},
            "opportunities": self._opps(site_id, keyword),
        }
        brief = ContentBrief(site_id=site_id, content_id=item.id, h1=h1, seo_title=seo_title, meta_description=meta, intent=intent, outline=outline,  # type: ignore[arg-type]
                             entities=entities, questions=questions, internal_links=links, sources=sources,
                             provenance={"generator": "rules-v1", "ai_used": False})
        if use_ai and self.orch is not None:
            brief = self._refine_with_ai(brief, item)
        brief.markdown = self.render_markdown(brief, item)
        return brief

    # ------------------------------------------------------------------ pieces
    def _keyword(self, item: ContentItem) -> Keyword | None:
        if item.target_keyword_id:
            k = self.kw.get(item.site_id, item.target_keyword_id)
            if k:
                return k
        if item.target_keyword:
            return self.kw.get_by_normalized(item.site_id, normalize_keyword(item.target_keyword))
        return None

    def _cluster_members(self, site_id: str, k: Keyword) -> list[Keyword]:
        if not k.cluster_id:
            return []
        rows, _ = self.kw.list(site_id, cluster_id=k.cluster_id, limit=50)
        return [r for r in rows if r.id != k.id]

    @staticmethod
    def _related_queries(gsc_all: dict, toks: set[str], norm: str) -> list[dict[str, Any]]:
        out = []
        for q, g in gsc_all.items():
            if q == norm or not toks:
                continue
            qt = set(tokenize(q))
            overlap = len(qt & toks) / max(1, len(toks))
            if overlap >= 0.5:
                out.append({"query": q, "impressions": g["impressions"], "clicks": g["clicks"], "position": g["position"], "top_page": unquote(g["top_page"]) if g["top_page"] else None, "overlap": round(overlap, 2)})
        out.sort(key=lambda r: (-(r["impressions"] or 0), r["position"] or 99))
        return out[:40]

    def _existing_pages(self, site_id: str, k: Keyword | None, gsc_kw: dict | None) -> list[dict[str, Any]]:
        pages: dict[str, dict[str, Any]] = {}
        if gsc_kw:
            for p in gsc_kw["pages"][:5]:
                url = unquote(p["page"])
                pages[normalize_url(url)] = {"url": url, "position": p["position"], "impressions": p["impressions"], "clicks": p["clicks"], "source": "gsc"}
        if k and k.target_url:
            key = normalize_url(k.target_url)
            pages.setdefault(key, {"url": k.target_url, "source": "target_url"})["target"] = True
        for v in pages.values():
            n = self._page_node_by_url(site_id, v["url"])
            if n:
                v.update(node_id=n["node_id"], title=n["title"], word_count=n["word_count"], internal_links_in=n["internal_links_in"])
        out = list(pages.values())
        for p in out:
            p["recommendation"] = ("بهبود همین صفحه" if (p.get("position") or 99) <= 20 else "صفحه جدید؛ به این صفحه لینک بدهید") if p.get("position") is not None else ("صفحه هدف انتخاب‌شده" if p.get("target") else "—")
        return out

    def _page_node_by_url(self, site_id: str, url: str) -> dict | None:
        with self.engine.connect() as cx:
            for nid, u, props in cx.execute(text("SELECT node_id, url, props FROM graph_nodes WHERE site_id=:s AND node_type IN ('PAGE','POST','CATEGORY') AND url IS NOT NULL"), {"s": site_id}).all():
                if normalize_url(unquote(u)) == normalize_url(url):
                    import json
                    p = json.loads(props or "{}")
                    return {"node_id": nid, "title": p.get("title"), "word_count": p.get("word_count"), "internal_links_in": p.get("internal_links_in")}
        return None

    def _entities(self, site_id: str, toks: set[str]) -> list[dict[str, Any]]:
        out = []
        for n in self.graph.list_nodes(site_id, ["BRAND", "MODEL", "SERVICE", "LOCATION"], limit=500):
            names = {n.label} | set((n.metadata.get("props") or {}).get("aliases") or [])
            ntoks = {t for name in names for t in tokenize(str(name))}
            hit = ntoks & toks
            if hit or any(normalize_keyword(str(name)) in " ".join(toks) for name in names):
                out.append({"type": n.type, "label": n.label, "node_id": n.id, "matched": sorted(hit)})
        # always offer the site's services/locations as context (max 3 each) if nothing matched
        if not out:
            for t in ("SERVICE", "LOCATION"):
                for n in self.graph.list_nodes(site_id, [t], limit=3):
                    out.append({"type": n.type, "label": n.label, "node_id": n.id, "matched": []})
        return out[:12]

    def _internal_links(self, site_id: str, k: Keyword | None, entities: list[dict], existing: list[dict]) -> list[dict[str, Any]]:
        links: dict[str, dict[str, Any]] = {}
        existing_urls = {normalize_url(p["url"]) for p in existing}
        # 1) pages ABOUT / OFFERS matched entities
        for e in entities:
            for edge in self.graph.edges_of(site_id, [e["node_id"]], ["ABOUT", "OFFERS"], "in")[:6]:
                n = self.graph.get_node(site_id, edge.source)
                if n and n.metadata.get("url") and normalize_url(n.metadata["url"]) not in existing_urls:
                    links.setdefault(n.id, {"url": n.metadata["url"], "anchor": e["label"], "reason": f"صفحه درباره «{e['label']}»", "node_id": n.id, "pagerank": n.metadata.get("pagerank") or 0})
        # 2) keyword opportunities of kind add_internal_links / internal_link suggestions in seo_opportunities
        with self.engine.connect() as cx:
            try:
                for url, related, query, reason in cx.execute(text("SELECT url, related_url, query, reason FROM seo_opportunities WHERE site_id=:s AND opp_type='internal_link' ORDER BY score DESC LIMIT 30"), {"s": site_id}).all():
                    src = unquote(url or ""); tgt = unquote(related or "")
                    if tgt and normalize_url(tgt) in existing_urls and src:
                        links.setdefault(f"opp:{src}", {"url": src, "anchor": query or (k.keyword if k else ""), "reason": f"فرصت لینک داخلی: {reason}", "node_id": None, "pagerank": 0})
            except Exception:  # noqa: BLE001
                pass
        # 3) top PageRank pages of the site (hubs) as fallback
        if len(links) < 3:
            for n in self.graph.list_nodes(site_id, ["PAGE", "CATEGORY"], limit=6):
                if n.metadata.get("url") and normalize_url(n.metadata["url"]) not in existing_urls and n.id not in links:
                    links[n.id] = {"url": n.metadata["url"], "anchor": n.label, "reason": "صفحه هاب با PageRank بالا", "node_id": n.id, "pagerank": n.metadata.get("pagerank") or 0}
        out = sorted(links.values(), key=lambda l: -(l.get("pagerank") or 0))[:8]
        for l in out:
            l.pop("pagerank", None)
        return out

    def _opps(self, site_id: str, k: Keyword | None) -> list[dict[str, Any]]:
        if not k:
            return []
        rows, _ = self.kw.list_opportunities(site_id, keyword_id=k.id, limit=10)
        return [{"kind": o.kind, "score": o.score, "reason": o.reason, "target_url": o.target_url} for o in rows]

    def _brand(self, site_id: str) -> str:
        with self.engine.connect() as cx:
            r = cx.execute(text("SELECT name FROM sites WHERE site_id=:s"), {"s": site_id}).first()
        return r[0] if r else ""

    @staticmethod
    def _guess_intent(kw: str) -> str:
        n = normalize_keyword(kw)
        if any(w in n for w in ("شماره", "تماس", "خرید", "قیمت", "سفارش", "buy", "price", "call")):
            return "transactional"
        if any(w in n for w in ("چگونه", "چطور", "چرا", "چیست", "راهنما", "how", "why", "what")):
            return "informational"
        if any(w in n for w in ("تهران", "کرج", "اصفهان", "شیراز", "مشهد", "near", "در")):
            return "local"
        return "commercial"

    @staticmethod
    def _h1(kw: str, intent: str | None, entities: list[dict]) -> str:
        loc = next((e["label"] for e in entities if e["type"] == "LOCATION"), None)
        base = kw.strip()
        if intent == "transactional":
            return f"{base} — تماس فوری و اعزام سریع" if "شماره" not in base and "تماس" not in base else base
        if intent == "informational":
            return f"راهنمای کامل {base}"
        if intent == "local" and loc and loc not in base:
            return f"{base} در {loc}"
        return base

    def _outline(self, kw: str, intent: str | None, members: list[Keyword], related: list[dict], entities: list[dict]) -> list[dict[str, Any]]:
        outline: list[dict[str, Any]] = []
        outline.append({"h2": f"{kw} چیست و چه زمانی به آن نیاز دارید؟" if intent == "informational" else f"خدمات {kw}", "h3": [], "why": "پاسخ مستقیم به اینتنت اصلی در ابتدای صفحه"})
        # cluster siblings → H2s (top by volume)
        for m in sorted(members, key=lambda x: -(x.volume or 0))[:4]:
            outline.append({"h2": m.keyword, "h3": [], "why": f"کلمه کلیدی هم‌خوشه (حجم {m.volume or '—'})"})
        # related GSC queries → H2/H3
        for r in related[:6]:
            if any(o["h2"] == r["query"] for o in outline):
                continue
            outline.append({"h2": r["query"], "h3": [], "why": f"کوئری واقعی GSC — {r['impressions']} ایمپرشن، جایگاه {r['position']}"})
        # entities → H3 under a models/services section
        models = [e["label"] for e in entities if e["type"] in ("MODEL", "BRAND")]
        if models:
            outline.append({"h2": "مدل‌ها و برندهای تحت پوشش", "h3": models[:8], "why": "موجودیت‌های گراف مرتبط با کلمه کلیدی"})
        outline.append({"h2": "مراحل درخواست و زمان رسیدن", "h3": ["تماس", "اعلام موقعیت", "اعزام"], "why": "CTA و کاهش اصطکاک (قواعد CTA سایت)"} if intent in ("transactional", "local", "commercial") else {"h2": "جمع‌بندی و اقدام بعدی", "h3": [], "why": "CTA"})
        outline.append({"h2": "سؤالات متداول", "h3": [], "why": "FAQ + اسکیما FAQPage"})
        return outline[:12]

    @staticmethod
    def _questions(related: list[dict], kw: str, entities: list[dict]) -> list[dict[str, Any]]:
        qs: list[dict[str, Any]] = []
        for r in related:
            if any(m in r["query"] for m in _QUESTION_MARKERS):
                qs.append({"question": r["query"] + ("؟" if not r["query"].endswith("؟") else ""), "source": f"gsc ({r['impressions']} imp)"})
        defaults = [f"هزینه {kw} چقدر است؟", f"زمان رسیدن {kw} چقدر طول می‌کشد؟", f"{kw} چه مدل‌هایی را پوشش می‌دهد؟", f"شرایط استفاده از {kw} چیست؟"]
        for d in defaults:
            if len(qs) >= 8:
                break
            qs.append({"question": d, "source": "template"})
        return qs[:8]

    @staticmethod
    def _meta(kw: str, intent: str | None, entities: list[dict]) -> str:
        loc = next((e["label"] for e in entities if e["type"] == "LOCATION"), None)
        s = f"{kw}{' در ' + loc if loc and loc not in kw else ''} — خدمات تخصصی، اعزام سریع و پشتیبانی شبانه‌روزی. همین حالا تماس بگیرید."
        return s[:160]

    # ------------------------------------------------------------------ AI refinement (optional)
    def _refine_with_ai(self, brief: ContentBrief, item: ContentItem) -> ContentBrief:
        schema = {"type": "object", "required": ["h1", "outline", "questions"], "properties": {"h1": {}, "outline": {}, "questions": {}}}
        prompt = ("Refine this SEO content brief. Keep it factual to the sources; return JSON with keys h1 (string), outline (array of {h2, h3[]}), questions (array of strings).\n"
                  f"Keyword: {brief.sources.get('keyword')}\nIntent: {brief.intent}\nCurrent H1: {brief.h1}\nOutline: {brief.outline}\nQuestions: {brief.questions}\nEntities: {brief.entities}")
        task = AITask(kind=TaskKind.BRIEF, site_id=item.site_id, messages=[AIMessage("user", prompt)], json_schema=schema)
        res = self.orch.run(task)  # type: ignore[union-attr]
        prov = {"generator": "rules-v1", "ai_used": False, "attempts": [a.__dict__ for a in res.attempts]}
        if res.ok and res.response and isinstance(res.response.parsed, dict) and res.response.provider != "echo":
            p = res.response.parsed
            if isinstance(p.get("h1"), str) and p["h1"].strip():
                brief.h1 = p["h1"].strip()
            if isinstance(p.get("outline"), list) and p["outline"]:
                brief.outline = [{"h2": o.get("h2", ""), "h3": o.get("h3", []) or [], "why": "AI"} for o in p["outline"] if isinstance(o, dict) and o.get("h2")][:12] or brief.outline
            if isinstance(p.get("questions"), list) and p["questions"]:
                brief.questions = [{"question": q, "source": "ai"} for q in p["questions"] if isinstance(q, str)][:8] or brief.questions
            prov.update(ai_used=True, provider=res.response.provider, model=res.response.model)
        elif res.ok and res.response and res.response.provider == "echo":
            prov["note"] = "فقط EchoProvider در دسترس است؛ بریف قاعده‌محور بدون تغییر ماند"
        brief.provenance = prov
        return brief

    # ------------------------------------------------------------------ markdown
    @staticmethod
    def render_markdown(b: ContentBrief, item: ContentItem) -> str:
        L = [f"# بریف محتوا: {item.title}", "", f"- **کلمه کلیدی هدف:** {b.sources.get('keyword', {}).get('keyword', item.target_keyword or '')}",
             f"- **اینتنت:** {_INTENT_FA.get(b.intent or '', b.intent or '—')}", f"- **عنوان سئو:** {b.seo_title}", f"- **توضیحات متا:** {b.meta_description}", "",
             f"## H1 پیشنهادی", f"{b.h1}", "", "## ساختار سرفصل‌ها"]
        for o in b.outline:
            L.append(f"- **H2:** {o['h2']}  _({o.get('why', '')})_")
            for h3 in o.get("h3") or []:
                L.append(f"  - H3: {h3}")
        L += ["", "## موجودیت‌ها"] + [f"- {e['type']}: {e['label']}" for e in b.entities] + ["", "## سؤالات (FAQ)"] + [f"- {q['question']}  _({q['source']})_" for q in b.questions]
        L += ["", "## لینک‌های داخلی پیشنهادی"] + [f"- [{l['anchor']}]({l['url']}) — {l['reason']}" for l in b.internal_links]
        ex = b.sources.get("existing_pages") or []
        if ex:
            L += ["", "## صفحات موجود"] + [f"- {p['url']} — {p.get('recommendation', '')}" + (f" (جایگاه {p['position']}, {p['impressions']} ایمپرشن)" if p.get('position') is not None else "") for p in ex]
        L += ["", f"_منبع: {b.provenance.get('generator')}{' + AI ' + str(b.provenance.get('model')) if b.provenance.get('ai_used') else ''}_"]
        return "\n".join(L)
