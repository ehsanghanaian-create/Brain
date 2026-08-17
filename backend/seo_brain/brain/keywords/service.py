"""KeywordService — enrich with GSC, run clustering, derive opportunities, sync KEYWORD/TOPIC into the graph."""
from __future__ import annotations

import logging
import uuid
from typing import Any
from urllib.parse import unquote

from sqlalchemy import Engine, text

from ...graph.model import GraphEdge, GraphNode
from ...graph.store import get_graph_store
from ...normalizer.url import normalize_url
from .clustering import cluster_keywords
from .repository import Keyword, KeywordOpportunity, KeywordsRepository

log = logging.getLogger("brain.keywords")

# Expected CTR by position (rough industry curve) — used only to detect "title/CTR" opportunities.
_EXPECTED_CTR = {1: 0.28, 2: 0.15, 3: 0.11, 4: 0.08, 5: 0.07, 6: 0.05, 7: 0.04, 8: 0.035, 9: 0.03, 10: 0.025}
OPP_FA = {"improve_page": "بهبود صفحه", "create_content": "تولید محتوای جدید", "update_title": "به‌روزرسانی عنوان/متا", "add_internal_links": "افزودن لینک داخلی"}


def _expected_ctr(pos: float | None) -> float:
    if pos is None:
        return 0.0
    p = int(round(pos))
    return _EXPECTED_CTR.get(max(1, min(p, 10)), 0.02 if p <= 20 else 0.01)


class KeywordService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.repo = KeywordsRepository(engine)

    # ------------------------------------------------------------ enrichment
    def enrich(self, site_id: str, kws: list[Keyword]) -> list[dict[str, Any]]:
        """Attach GSC metrics (matched on normalized text) + resolved target page + cluster/topic labels."""
        gsc = self.repo.gsc_by_normalized(site_id)
        clusters = {c.cluster_id: c for c in self.repo.list_clusters(site_id)}
        out = []
        for k in kws:
            g = gsc.get(k.normalized)
            d = k.to_dict()
            d["gsc"] = None if not g else {"clicks": g["clicks"], "impressions": g["impressions"], "ctr": g["ctr"], "position": g["position"],
                                           "top_page": unquote(g["top_page"]) if g["top_page"] else None, "pages_count": g["pages_count"]}
            c = clusters.get(k.cluster_id) if k.cluster_id else None
            d["cluster"] = {"cluster_id": c.cluster_id, "name": c.name, "topic": c.topic} if c else None
            if not d.get("topic") and c and c.topic:
                d["topic"] = c.topic
            out.append(d)
        return out

    def detail(self, site_id: str, kid: int) -> dict[str, Any] | None:
        k = self.repo.get(site_id, kid)
        if not k:
            return None
        d = self.enrich(site_id, [k])[0]
        g = self.repo.gsc_by_normalized(site_id).get(k.normalized)
        d["gsc_pages"] = [{**p, "page": unquote(p["page"])} for p in (g["pages"] if g else [])][:20]
        opps, _ = self.repo.list_opportunities(site_id, keyword_id=kid, limit=20)
        d["opportunities"] = [{**o.to_dict(), "kind_fa": OPP_FA.get(o.kind, o.kind)} for o in opps]
        return d

    # ------------------------------------------------------------ clustering
    def run_clustering(self, site_id: str, threshold: float = 0.42) -> dict[str, Any]:
        kws = self.repo.all(site_id)
        clusters, assignment = cluster_keywords(kws, threshold)
        self.repo.replace_clusters(site_id, clusters)
        self.repo.set_clusters(site_id, assignment)
        return {"clusters": len(clusters), "keywords": len(kws), "threshold": threshold,
                "top": [c.to_dict() for c in sorted(clusters, key=lambda c: -c.keywords_count)[:10]]}

    def topic_map(self, site_id: str) -> dict[str, Any]:
        kws = self.enrich(site_id, self.repo.all(site_id))
        clusters = self.repo.list_clusters(site_id)
        by_cluster: dict[str | None, list[dict]] = {}
        for k in kws:
            by_cluster.setdefault(k["cluster_id"], []).append(k)
        items = []
        for c in clusters:
            members = by_cluster.get(c.cluster_id, [])
            imp = sum((m["gsc"] or {}).get("impressions", 0) for m in members)
            clk = sum((m["gsc"] or {}).get("clicks", 0) for m in members)
            pos = [m["gsc"]["position"] for m in members if m["gsc"] and m["gsc"]["position"] is not None]
            targets = sorted({m["target_url"] for m in members if m["target_url"]})
            items.append({**c.to_dict(), "members": members, "gsc": {"impressions": imp, "clicks": clk, "avg_position": round(sum(pos) / len(pos), 1) if pos else None,
                                                                    "with_data": sum(1 for m in members if m["gsc"])}, "targets": targets,
                          "volume": sum(m["volume"] or 0 for m in members)})
        unclustered = by_cluster.get(None, [])
        return {"clusters": items, "unclustered": unclustered, "counts": self.repo.counts(site_id)}

    # ------------------------------------------------------------ opportunities
    def analyze(self, site_id: str, min_impressions: int = 5) -> dict[str, Any]:
        """Rule-based opportunities from keywords × GSC × graph (inbound links). Every row is explainable."""
        run_id = f"kwopp-{uuid.uuid4().hex[:8]}"
        kws = self.repo.all(site_id)
        gsc = self.repo.gsc_by_normalized(site_id)
        store = get_graph_store(self.engine)
        pages_in = self._inbound_links_by_url(site_id)
        opps: list[KeywordOpportunity] = []
        for k in kws:
            if k.status == "ignored":
                continue
            g = gsc.get(k.normalized)
            pos = g["position"] if g else None
            imp = g["impressions"] if g else 0
            clicks = g["clicks"] if g else 0
            ctr = g["ctr"] if g else 0.0
            top = unquote(g["top_page"]) if g and g["top_page"] else None
            target = k.target_url or top
            prio_w = {"high": 1.0, "medium": 0.7, "low": 0.4}.get(k.priority or "", 0.6)
            vol_w = min(1.0, (k.volume or 0) / 1000) if k.volume else 0.3
            ev = {"position": pos, "impressions": imp, "clicks": clicks, "ctr": ctr, "top_page": top, "target_url": k.target_url, "volume": k.volume, "priority": k.priority}
            # 1) create new content: no ranking page (no GSC data or position > 20) and nothing targeted
            if (g is None or (pos is not None and pos > 20)) and not k.target_url:
                score = round(0.35 + 0.35 * prio_w + 0.3 * vol_w, 3)
                reason = ("این کلمه کلیدی هیچ صفحه‌ای در نتایج ندارد" if g is None else f"بهترین جایگاه {pos:.1f} است (فراتر از ۲۰)") + " و صفحه هدفی تعیین نشده؛ محتوای جدید بسازید"
                opps.append(KeywordOpportunity(site_id, k.id, "create_content", score, reason, None, ev, run_id=run_id))  # type: ignore[arg-type]
                continue
            if g is None:
                continue
            # 2) improve page: striking distance 4–20 with impressions
            if pos is not None and 4 <= pos <= 20 and imp >= min_impressions and target:
                score = round(min(1.0, 0.4 + 0.3 * min(1.0, imp / 200) + 0.3 * (1 - (pos - 4) / 16)), 3)
                reason = f"جایگاه {pos:.1f} با {imp} ایمپرشن — با تقویت محتوا/عنوان/H2 می‌تواند به صفحه اول برسد"
                opps.append(KeywordOpportunity(site_id, k.id, "improve_page", score, reason, target, ev, run_id=run_id))  # type: ignore[arg-type]
            # 3) update title/meta: CTR far below expected for the position
            exp = _expected_ctr(pos)
            if pos is not None and pos <= 12 and imp >= max(min_impressions, 20) and exp and ctr < exp * 0.5:
                score = round(min(1.0, 0.4 + 0.4 * (1 - ctr / exp) + 0.2 * min(1.0, imp / 300)), 3)
                reason = f"CTR {ctr*100:.1f}٪ در جایگاه {pos:.1f} (انتظار ≈ {exp*100:.0f}٪) — عنوان و توضیحات متا را بازنویسی کنید"
                opps.append(KeywordOpportunity(site_id, k.id, "update_title", score, reason, target, {**ev, "expected_ctr": exp}, run_id=run_id))  # type: ignore[arg-type]
            # 4) add internal links: ranking page has few inbound links
            if pos is not None and 4 <= pos <= 25 and target:
                inbound = pages_in.get(normalize_url(target)) if target else None
                if inbound is not None and inbound <= 3:
                    score = round(min(1.0, 0.45 + 0.25 * (1 - inbound / 4) + 0.3 * min(1.0, imp / 200)), 3)
                    reason = f"صفحه هدف فقط {inbound} لینک داخلی ورودی دارد و در جایگاه {pos:.1f} است — لینک داخلی با انکر «{k.keyword}» اضافه کنید"
                    opps.append(KeywordOpportunity(site_id, k.id, "add_internal_links", score, reason, target, {**ev, "inbound_links": inbound}, run_id=run_id))  # type: ignore[arg-type]
        stats = self.repo.replace_opportunities(site_id, opps, run_id)
        by_kind: dict[str, int] = {}
        for o in opps:
            by_kind[o.kind] = by_kind.get(o.kind, 0) + 1
        return {"run_id": run_id, "keywords": len(kws), "with_gsc": sum(1 for k in kws if k.normalized in gsc), "opportunities": len(opps), "by_kind": by_kind, **stats}

    def _inbound_links_by_url(self, site_id: str) -> dict[str, int]:
        out: dict[str, int] = {}
        with self.engine.connect() as cx:
            try:
                rows = cx.execute(text("SELECT target_url, COUNT(DISTINCT source_url) FROM links WHERE site_id=:s AND is_internal=1 GROUP BY target_url"), {"s": site_id}).all()
            except Exception:  # noqa: BLE001
                rows = []
        for url, n in rows:
            out[normalize_url(unquote(url))] = int(n)
        # pages known to the crawler with zero inbound links
        with self.engine.connect() as cx:
            try:
                for (url,) in cx.execute(text("SELECT url FROM pages WHERE site_id=:s"), {"s": site_id}).all():
                    out.setdefault(normalize_url(unquote(url)), 0)
            except Exception:  # noqa: BLE001
                pass
        return out

    # ------------------------------------------------------------ graph sync
    def sync_graph(self, site_id: str) -> dict[str, Any]:
        """Upsert KEYWORD + TOPIC nodes and CLUSTERED_IN / KEYWORD_TARGETS edges. Removes stale keyword/topic nodes."""
        store = get_graph_store(self.engine)
        kws = self.enrich(site_id, self.repo.all(site_id))
        clusters = self.repo.list_clusters(site_id)
        page_ids = self._page_node_ids(site_id)
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        for c in clusters:
            nodes.append(GraphNode(f"topic:{c.cluster_id}", site_id, "TOPIC", {"label": c.topic or c.name, "props": {"cluster_id": c.cluster_id, "name": c.name, "keywords_count": c.keywords_count, "method": c.method}}))
        for k in kws:
            nid = f"keyword:{k['id']}"
            g = k["gsc"] or {}
            nodes.append(GraphNode(nid, site_id, "KEYWORD", {"label": k["keyword"], "props": {"intent": k["intent"], "volume": k["volume"], "difficulty": k["difficulty"], "priority": k["priority"],
                                                                                        "status": k["status"], "topic": k["topic"], "position": g.get("position"), "impressions": g.get("impressions"),
                                                                                        "clicks": g.get("clicks"), "ctr": g.get("ctr"), "target_url": k["target_url"]}}))
            if k["cluster_id"]:
                edges.append(GraphEdge(nid, f"topic:{k['cluster_id']}", "CLUSTERED_IN", 1.0, {}, site_id))
            tgt = k["target_url"] or g.get("top_page")
            if tgt:
                pid = page_ids.get(normalize_url(tgt))
                if pid:
                    edges.append(GraphEdge(nid, pid, "KEYWORD_TARGETS", 1.0 if k["target_url"] else 0.6, {"props": {"source": "target_url" if k["target_url"] else "gsc_top_page", "position": g.get("position")}}, site_id))
        # remove stale keyword/topic nodes + their edges
        keep = {n.id for n in nodes}
        with self.engine.begin() as cx:
            cx.execute(text("DELETE FROM graph_edges WHERE site_id=:s AND (source_id LIKE 'keyword:%' OR source_id LIKE 'topic:%' OR target_id LIKE 'topic:%')"), {"s": site_id})
            for (nid,) in cx.execute(text("SELECT node_id FROM graph_nodes WHERE site_id=:s AND (node_type='KEYWORD' OR node_type='TOPIC')"), {"s": site_id}).all():
                if nid not in keep:
                    cx.execute(text("DELETE FROM graph_nodes WHERE site_id=:s AND node_id=:n"), {"s": site_id, "n": nid})
        n_nodes = store.upsert_nodes(nodes)
        n_edges = store.upsert_edges(edges)
        return {"nodes": n_nodes, "edges": n_edges, "keywords": len(kws), "topics": len(clusters), "targets_linked": sum(1 for e in edges if e.relation_type == "KEYWORD_TARGETS")}

    def _page_node_ids(self, site_id: str) -> dict[str, str]:
        out: dict[str, str] = {}
        with self.engine.connect() as cx:
            for nid, url in cx.execute(text("SELECT node_id, url FROM graph_nodes WHERE site_id=:s AND node_type IN ('PAGE','POST','CATEGORY') AND url IS NOT NULL"), {"s": site_id}).all():
                out[normalize_url(unquote(url))] = nid
        return out
