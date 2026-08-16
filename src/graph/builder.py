"""Graph builder: SQLite tables -> graph_nodes / graph_edges (+ FTS, PageRank, communities).

Only relationships supported by real data become edges. Node IDs are stable and site-scoped:
  site:<site_id> | page:<url> | post:<url> | category:<slug> | tag:<slug> | brand:<slug> | model:<slug>
  service:<slug> | location:<slug> | query:<hash> | schema:<Type> | problem:<type> | opportunity:<type>
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections import Counter, defaultdict
from urllib.parse import unquote

import networkx as nx

from ..common.config import SiteConfig
from ..common.logging_setup import new_run_id
from ..database.db import j, rows, utcnow

log = logging.getLogger("graph.builder")

# structural helper types never worth a node
SCHEMA_SKIP = {"ListItem", "EntryPoint", "ReadAction", "SearchAction", "CommentAction", "PropertyValueSpecification", "ImageObject", "Unknown"}


def pagerank_simple(G: nx.DiGraph, alpha: float = 0.85, max_iter: int = 200, tol: float = 1e-8) -> dict[str, float]:
    """Weighted PageRank by power iteration (pure Python; no numpy/scipy). Dangling mass redistributed uniformly."""
    nodes = list(G.nodes())
    n = len(nodes)
    if n == 0:
        return {}
    out_w = {u: sum(d.get("weight", 1.0) for _, _, d in G.out_edges(u, data=True)) for u in nodes}
    pr = {u: 1.0 / n for u in nodes}
    for _ in range(max_iter):
        dangling = sum(pr[u] for u in nodes if out_w[u] == 0)
        new = {u: (1 - alpha) / n + alpha * dangling / n for u in nodes}
        for u in nodes:
            if out_w[u] == 0:
                continue
            share = alpha * pr[u] / out_w[u]
            for _, v, d in G.out_edges(u, data=True):
                new[v] += share * d.get("weight", 1.0)
        err = sum(abs(new[u] - pr[u]) for u in nodes)
        pr = new
        if err < n * tol:
            break
    return pr


def qid(query: str) -> str:
    return "query:" + hashlib.sha1(query.encode("utf-8")).hexdigest()[:12]


class GraphBuild:
    def __init__(self, conn: sqlite3.Connection, site: SiteConfig):
        self.conn, self.site, self.sid = conn, site, site.site_id
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}

    def node(self, node_id: str, node_type: str, label: str, url: str | None = None, **props) -> str:
        if node_id in self.nodes:
            self.nodes[node_id]["props"].update({k: v for k, v in props.items() if v is not None})
            return node_id
        self.nodes[node_id] = {"node_id": node_id, "node_type": node_type, "label": label, "url": url, "props": {k: v for k, v in props.items() if v is not None}}
        return node_id

    def edge(self, src: str, tgt: str, etype: str, weight: float = 1.0, **props) -> None:
        if src not in self.nodes or tgt not in self.nodes or src == tgt:
            return
        eid = f"{etype}|{src}|{tgt}"
        if eid in self.edges:
            self.edges[eid]["weight"] += weight
            return
        self.edges[eid] = {"edge_id": eid, "source_id": src, "target_id": tgt, "edge_type": etype, "weight": weight, "props": props}

    # ------------------------------------------------------------------------------
    def build(self, limit_pages: int | None = None) -> dict:
        c, sid, site = self.conn, self.sid, self.site
        run_id = new_run_id("graph")
        c.execute("INSERT INTO sync_runs(run_id, site_id, source, started_at, status) VALUES (?,?,?,?,?)", (run_id, sid, "graph", utcnow(), "running"))
        site_node = self.node(f"site:{sid}", "SITE", site.name, site.canonical_url, language=site.language)

        posts = {p["url"]: p for p in rows(c, "SELECT * FROM posts WHERE site_id=?", (sid,))}
        cats = rows(c, "SELECT * FROM categories WHERE site_id=?", (sid,))
        cat_by_url = {ct["url"]: ct for ct in cats}
        cat_by_id = {ct["wp_id"]: ct for ct in cats}
        tags = rows(c, "SELECT * FROM tags WHERE site_id=?", (sid,))
        pages = rows(c, "SELECT * FROM pages WHERE site_id=? AND crawl_status='ok' ORDER BY depth, url", (sid,))
        if limit_pages:
            pages = pages[:limit_pages]
        page_urls = {p["url"] for p in pages}
        gsc = {r["page"]: r for r in rows(c, "SELECT page, SUM(clicks) clicks, SUM(impressions) impressions, "
                                             "CASE WHEN SUM(impressions)>0 THEN 1.0*SUM(clicks)/SUM(impressions) END ctr, "
                                             "CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) END position, "
                                             "MAX(date_to) last FROM gsc_query_page WHERE site_id=? GROUP BY page", (sid,))}
        inbound = Counter()
        for l in rows(c, "SELECT DISTINCT source_url, target_url FROM links WHERE site_id=? AND is_internal=1 AND source_url!=target_url", (sid,)):
            inbound[l["target_url"]] += 1

        # taxonomy nodes
        for ct in cats:
            if ct["taxonomy"] == "category" and ct["count"] == 0 and not any(x["parent_wp_id"] == ct["wp_id"] for x in cats):
                continue  # empty leaf category (e.g. uncategorized) — not part of the real structure
            nid = self.node(f"category:{ct['taxonomy']}:{ct['slug']}", "CATEGORY", ct["name"], ct["url"], slug=unquote(ct["slug"]), taxonomy=ct["taxonomy"], count=ct["count"], wp_id=ct["wp_id"])
            self.edge(site_node, nid, "HAS_CATEGORY")
        for ct in cats:
            if ct["parent_wp_id"] and ct["parent_wp_id"] in cat_by_id:
                p = cat_by_id[ct["parent_wp_id"]]
                self.edge(f"category:{ct['taxonomy']}:{ct['slug']}", f"category:{p['taxonomy']}:{p['slug']}", "BELONGS_TO")
        for tg in tags:
            nid = self.node(f"tag:{tg['taxonomy']}:{tg['slug']}", "TAG", tg["name"], tg["url"], count=tg["count"])
            self.edge(site_node, nid, "HAS_TAG")

        # page/post nodes from crawled pages (URL identity); category archive URLs map onto CATEGORY nodes
        url_to_node: dict[str, str] = {}
        for ct in cats:
            if ct["url"]:
                url_to_node[ct["url"]] = f"category:{ct['taxonomy']}:{ct['slug']}"
        for p in pages:
            u = p["url"]
            if u in url_to_node and url_to_node[u] in self.nodes:
                self._merge_page_props(url_to_node[u], p, gsc.get(u), inbound[u])
                continue
            post = posts.get(u)
            ntype = "POST" if (post and post["type"] == "post") else "PAGE"
            nid = f"{'post' if ntype == 'POST' else 'page'}:{u}"
            label = (p["title"] or (post or {}).get("title") or unquote(u)).split(" - ")[0].strip()
            self.node(nid, ntype, label, u)
            self._merge_page_props(nid, p, gsc.get(u), inbound[u], post)
            url_to_node[u] = nid
            self.edge(site_node, nid, "HAS_POST" if ntype == "POST" else "HAS_PAGE")
        # WP items that were not crawled (still real content)
        for u, post in posts.items():
            if u not in url_to_node:
                ntype = "POST" if post["type"] == "post" else "PAGE"
                nid = f"{'post' if ntype == 'POST' else 'page'}:{u}"
                self.node(nid, ntype, post["title"] or unquote(u), u, wp_id=post["wp_id"], crawled=False, word_count=post["word_count"])
                url_to_node[u] = nid
                self.edge(site_node, nid, "HAS_POST" if ntype == "POST" else "HAS_PAGE")

        # BELONGS_TO (post -> category / tag) from real taxonomy relations
        wp_url = {(p["type"], p["wp_id"]): u for u, p in posts.items()}
        for r in rows(c, "SELECT * FROM post_terms WHERE site_id=?", (sid,)):
            u = wp_url.get((r["post_type"], r["post_wp_id"]))
            if not u or u not in url_to_node:
                continue
            term = c.execute("SELECT slug FROM categories WHERE site_id=? AND taxonomy=? AND wp_id=?", (sid, r["taxonomy"], r["term_wp_id"])).fetchone()
            if term:
                self.edge(url_to_node[u], f"category:{r['taxonomy']}:{term[0]}", "BELONGS_TO")
                continue
            term = c.execute("SELECT slug FROM tags WHERE site_id=? AND taxonomy=? AND wp_id=?", (sid, r["taxonomy"], r["term_wp_id"])).fetchone()
            if term:
                self.edge(url_to_node[u], f"tag:{r['taxonomy']}:{term[0]}", "HAS_TAG")

        # LINKS_TO from real crawled links (distinct source->target; nav links flagged, weight = count)
        for l in rows(c, "SELECT source_url, target_url, MIN(is_nav) is_nav, COUNT(*) n, GROUP_CONCAT(DISTINCT anchor_text) anchors FROM links "
                         "WHERE site_id=? AND is_internal=1 GROUP BY source_url, target_url", (sid,)):
            s, t = url_to_node.get(l["source_url"]), url_to_node.get(l["target_url"])
            if s and t and s != t:
                self.edge(s, t, "LINKS_TO", weight=float(l["n"]), nav_only=bool(l["is_nav"]), anchors=(l["anchors"] or "")[:200])

        # entities
        ents = rows(c, "SELECT * FROM entities WHERE site_id=?", (sid,))
        ent_node = {}
        for e in ents:
            nid = f"{e['entity_type'].lower()}:{e['slug']}"
            ent_node[(e["entity_type"], e["slug"])] = nid
            self.node(nid, e["entity_type"], e["name"], None, aliases=json.loads(e["aliases"] or "[]"), source=e["source"], evidence=json.loads(e["evidence"] or "[]"))
        for e in ents:
            if e["parent_slug"]:
                parent = next((x for x in ents if x["slug"] == e["parent_slug"] and x["entity_type"] in ("BRAND",)), None)
                if parent:
                    self.edge(ent_node[(e["entity_type"], e["slug"])], ent_node[(parent["entity_type"], parent["slug"])], "BELONGS_TO")
        for m in rows(c, "SELECT * FROM entity_mentions WHERE site_id=?", (sid,)):
            pn = url_to_node.get(m["url"])
            en = ent_node.get((m["entity_type"], m["entity_slug"]))
            if not pn or not en:
                continue
            strong = m["in_title"] or m["in_h1"] or m["in_url"] or m["in_taxonomy"] or m["mentions"] >= 5
            if not strong:
                continue
            et = {"SERVICE": "OFFERS", "LOCATION": "TARGETS"}.get(m["entity_type"], "ABOUT")
            self.edge(pn, en, et, weight=float(m["score"]), in_title=bool(m["in_title"]), in_h1=bool(m["in_h1"]), mentions=m["mentions"])

        # queries: only important ones become nodes; RANKS_FOR edges
        for q in rows(c, "SELECT * FROM queries WHERE site_id=? AND is_important=1 ORDER BY impressions DESC LIMIT ?", (sid, site.graph.max_query_nodes)):
            nid = self.node(qid(q["query"]), "QUERY", q["query"], None, clicks=q["clicks"], impressions=q["impressions"], ctr=round(q["ctr"], 4),
                            position=round(q["position"], 1), pages_count=q["pages_count"], importance_reason=q["importance_reason"])
            for r in rows(c, "SELECT page, clicks, impressions, position FROM gsc_query_page WHERE site_id=? AND query=? AND impressions>=5", (sid, q["query"])):
                pn = url_to_node.get(r["page"])
                if pn:
                    self.edge(pn, nid, "RANKS_FOR", weight=float(r["impressions"]), clicks=r["clicks"], impressions=r["impressions"], position=round(r["position"], 1))

        # schema types: site-wide types (present on every crawled page) attach to SITE; page-specific to pages
        st_by_url = defaultdict(set)
        for r in rows(c, "SELECT url, schema_type FROM schemas WHERE site_id=?", (sid,)):
            for t in r["schema_type"].split(","):
                if t not in SCHEMA_SKIP:
                    st_by_url[r["url"]].add(t)
        n_pages_with_schema = len([u for u in st_by_url if u in page_urls])
        type_count = Counter(t for u, ts in st_by_url.items() if u in page_urls for t in ts)
        sitewide = {t for t, n in type_count.items() if n_pages_with_schema and n >= n_pages_with_schema}
        for t, n in type_count.items():
            nid = self.node(f"schema:{t}", "SCHEMA", t, None, pages=n, sitewide=t in sitewide)
            if t in sitewide:
                self.edge(site_node, nid, "HAS_SCHEMA", weight=float(n))
        for u, ts in st_by_url.items():
            pn = url_to_node.get(u)
            if not pn:
                continue
            for t in ts:
                if t not in sitewide:
                    self.edge(pn, f"schema:{t}", "HAS_SCHEMA")

        # problems / opportunities: node per type; edges from pages
        for r in rows(c, "SELECT problem_type, severity, COUNT(*) n FROM seo_problems WHERE site_id=? GROUP BY 1,2", (sid,)):
            self.node(f"problem:{r['problem_type']}", "SEO_PROBLEM", r["problem_type"].replace("_", " "), None, severity=r["severity"], count=r["n"])
        for r in rows(c, "SELECT problem_type, url FROM seo_problems WHERE site_id=?", (sid,)):
            pn = url_to_node.get(r["url"])
            if pn:
                self.edge(pn, f"problem:{r['problem_type']}", "HAS_PROBLEM")
        for r in rows(c, "SELECT opp_type, COUNT(*) n, AVG(score) s FROM seo_opportunities WHERE site_id=? GROUP BY 1", (sid,)):
            self.node(f"opportunity:{r['opp_type']}", "SEO_OPPORTUNITY", r["opp_type"].replace("_", " "), None, count=r["n"], avg_score=round(r["s"] or 0, 3))
        for r in rows(c, "SELECT opp_type, url, related_url, score FROM seo_opportunities WHERE site_id=?", (sid,)):
            pn = url_to_node.get(r["url"])
            if pn:
                self.edge(pn, f"opportunity:{r['opp_type']}", "HAS_OPPORTUNITY", weight=float(r["score"] or 0))

        # metrics on the internal link graph
        self._metrics()
        self._persist(run_id)
        stats = {"run_id": run_id, "nodes": len(self.nodes), "edges": len(self.edges),
                 "by_type": dict(Counter(n["node_type"] for n in self.nodes.values())),
                 "by_edge": dict(Counter(e["edge_type"] for e in self.edges.values()))}
        c.execute("UPDATE sync_runs SET finished_at=?, status='completed', rows_written=?, notes=? WHERE run_id=?", (utcnow(), len(self.nodes) + len(self.edges), j(stats), run_id))
        c.commit()
        log.info(f"graph built: {json.dumps(stats, ensure_ascii=False)}")
        return stats

    def _merge_page_props(self, nid, p, g, inbound_n, post=None):
        n = self.nodes[nid]
        n["props"].update({
            "status_code": p["status_code"], "indexable": bool(p["indexable"]) if p["indexable"] is not None else None,
            "indexability_reason": p["indexability_reason"], "canonical": p["canonical"], "title": p["title"],
            "meta_description": p["meta_description"], "h1": json.loads(p["h1"] or "[]"), "h1_count": p["h1_count"],
            "word_count": p["word_count"], "language": p["language"], "internal_links_in": inbound_n,
            "internal_links_out": p["internal_links_out"], "external_links_out": p["external_links_out"],
            "schema_types": json.loads(p["schema_types"] or "[]"), "in_sitemap": bool(p["in_sitemap"]), "depth": p["depth"],
            "last_crawled": p["last_crawled"], "content_hash": p["content_hash"], "images_missing_alt": p["images_missing_alt"],
            "gsc_clicks": g["clicks"] if g else None, "gsc_impressions": g["impressions"] if g else None,
            "gsc_ctr": round(g["ctr"], 4) if g and g["ctr"] is not None else None,
            "gsc_position": round(g["position"], 1) if g and g["position"] is not None else None,
            "last_gsc_sync": g["last"] if g else None,
        })
        if post:
            n["props"].update({"wp_id": post["wp_id"], "wp_type": post["type"], "date_gmt": post["date_gmt"], "modified_gmt": post["modified_gmt"],
                               "excerpt": (post["excerpt"] or "")[:300], "yoast_title": post["yoast_title"], "yoast_description": post["yoast_description"]})

    def _metrics(self):
        G = nx.DiGraph()
        for nid, n in self.nodes.items():
            if n["node_type"] in ("PAGE", "POST", "CATEGORY"):
                G.add_node(nid)
        for e in self.edges.values():
            if e["edge_type"] == "LINKS_TO" and e["source_id"] in G and e["target_id"] in G:
                G.add_edge(e["source_id"], e["target_id"], weight=e["weight"])
        if G.number_of_nodes() == 0:
            return
        pr = pagerank_simple(G) if G.number_of_edges() else {n: 1 / G.number_of_nodes() for n in G}
        for nid, v in pr.items():
            self.nodes[nid]["pagerank"] = round(v, 6)
        try:
            comms = nx.community.louvain_communities(G.to_undirected(), seed=42) if G.number_of_edges() else []
            for i, com in enumerate(comms):
                for nid in com:
                    self.nodes[nid]["community"] = i
        except Exception as e:  # noqa: BLE001
            log.warning(f"community detection failed: {e}")

    def _persist(self, run_id: str):
        c, sid = self.conn, self.sid
        c.execute("DELETE FROM graph_edges WHERE site_id=?", (sid,))
        c.execute("DELETE FROM graph_nodes WHERE site_id=?", (sid,))
        c.execute("DELETE FROM graph_fts WHERE site_id=?", (sid,))
        for n in self.nodes.values():
            c.execute("INSERT INTO graph_nodes(site_id,node_id,node_type,label,url,props,pagerank,community,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                      (sid, n["node_id"], n["node_type"], n["label"], n["url"], j(n["props"]), n.get("pagerank"), n.get("community"), utcnow()))
            p = n["props"]
            body = " ".join(str(x) for x in [p.get("title"), " ".join(p.get("h1") or []), p.get("meta_description"), p.get("excerpt"),
                                                " ".join(p.get("aliases") or []), p.get("yoast_description")] if x)
            c.execute("INSERT INTO graph_fts(node_id, site_id, node_type, label, url, body) VALUES (?,?,?,?,?,?)",
                      (n["node_id"], sid, n["node_type"], n["label"], unquote(n["url"] or ""), body))
        for e in self.edges.values():
            c.execute("INSERT INTO graph_edges(site_id,edge_id,source_id,target_id,edge_type,weight,props) VALUES (?,?,?,?,?,?,?)",
                      (sid, e["edge_id"], e["source_id"], e["target_id"], e["edge_type"], e["weight"], j(e["props"])))
        c.commit()
