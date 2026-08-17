"""Read-only query API over SQLite (graph + SEO data). Used by the MCP server and the dashboard.

Every function returns plain JSON-serialisable dicts/lists. No writes. No secrets.
"""
from __future__ import annotations

import json
import sqlite3
from collections import deque
from urllib.parse import unquote

import networkx as nx

from ..database.db import rows, one

MAX_LIMIT = 500


def _lim(n: int | None, default: int = 50) -> int:
    return max(1, min(int(n or default), MAX_LIMIT))


def _node(r: dict) -> dict:
    p = json.loads(r.get("props") or "{}")
    return {"node_id": r["node_id"], "type": r["node_type"], "label": r["label"], "url": unquote(r["url"]) if r.get("url") else None,
            "pagerank": r.get("pagerank"), "community": r.get("community"), "vault_path": r.get("vault_path"), "props": p}


def _edge(r: dict) -> dict:
    return {"source": r["source_id"], "target": r["target_id"], "type": r["edge_type"], "weight": r["weight"], "props": json.loads(r.get("props") or "{}")}


def resolve_node_id(conn, sid: str, ref: str) -> str | None:
    """Accept a node_id, a URL (any encoding), or a label."""
    if one(conn, "SELECT 1 FROM graph_nodes WHERE site_id=? AND node_id=?", (sid, ref)):
        return ref
    r = one(conn, "SELECT node_id FROM graph_nodes WHERE site_id=? AND (url=? OR url=?) LIMIT 1", (sid, ref, ref.rstrip("/") + "/"))
    if r:
        return r["node_id"]
    from ..normalizer import normalize_url
    from urllib.parse import urlsplit
    if ref.startswith("http"):
        host = urlsplit(ref).hostname
        n = normalize_url(ref, site_host=host)
        r = one(conn, "SELECT node_id FROM graph_nodes WHERE site_id=? AND url=? LIMIT 1", (sid, n))
        if r:
            return r["node_id"]
    r = one(conn, "SELECT node_id FROM graph_nodes WHERE site_id=? AND label=? LIMIT 1", (sid, ref))
    if r:
        return r["node_id"]
    r = one(conn, "SELECT node_id FROM graph_fts WHERE site_id=? AND graph_fts MATCH ? ORDER BY rank LIMIT 1", (sid, _fts_query(ref)))
    return r["node_id"] if r else None


def _fts_query(q: str) -> str:
    toks = [t.replace('"', "") for t in q.replace("‌", " ").split() if t.strip()]
    return " ".join(f'"{t}"' for t in toks) or '""'


# ---------------------------------------------------------------------------------
def search_graph(conn, sid, query: str, node_type: str | None = None, limit: int = 20) -> list[dict]:
    q = _fts_query(query)
    sql = "SELECT n.*, bm25(graph_fts) score FROM graph_fts f JOIN graph_nodes n ON n.site_id=f.site_id AND n.node_id=f.node_id WHERE f.site_id=? AND graph_fts MATCH ?"
    params: list = [sid, q]
    if node_type:
        sql += " AND n.node_type=?"
        params.append(node_type.upper())
    sql += " ORDER BY score LIMIT ?"
    params.append(_lim(limit))
    out = []
    try:
        for r in rows(conn, sql, params):
            d = _node(r)
            d["score"] = round(-r["score"], 3)
            out.append(d)
    except sqlite3.OperationalError:
        pass
    if not out:  # fallback: substring on label/url
        like = f"%{query}%"
        sql = "SELECT * FROM graph_nodes WHERE site_id=? AND (label LIKE ? OR url LIKE ?)" + (" AND node_type=?" if node_type else "") + " LIMIT ?"
        params = [sid, like, like] + ([node_type.upper()] if node_type else []) + [_lim(limit)]
        out = [_node(r) for r in rows(conn, sql, params)]
    return out


def get_node(conn, sid, ref: str) -> dict | None:
    nid = resolve_node_id(conn, sid, ref)
    if not nid:
        return None
    r = one(conn, "SELECT * FROM graph_nodes WHERE site_id=? AND node_id=?", (sid, nid))
    d = _node(r)
    d["out_edges"] = [_edge(e) | {"target_label": _label(conn, sid, e["target_id"])} for e in rows(conn, "SELECT * FROM graph_edges WHERE site_id=? AND source_id=?", (sid, nid))]
    d["in_edges"] = [_edge(e) | {"source_label": _label(conn, sid, e["source_id"])} for e in rows(conn, "SELECT * FROM graph_edges WHERE site_id=? AND target_id=?", (sid, nid))]
    return d


def _label(conn, sid, nid) -> str | None:
    r = one(conn, "SELECT label FROM graph_nodes WHERE site_id=? AND node_id=?", (sid, nid))
    return r["label"] if r else None


def get_neighbors(conn, sid, ref: str, depth: int = 1, edge_types: list[str] | None = None, direction: str = "both", limit: int = 100) -> dict:
    nid = resolve_node_id(conn, sid, ref)
    if not nid:
        return {"error": f"node not found: {ref}"}
    depth = max(1, min(int(depth), 4))
    seen = {nid: 0}
    q = deque([nid])
    edges_out = []
    while q:
        cur = q.popleft()
        d = seen[cur]
        if d >= depth:
            continue
        sql_parts, params = [], []
        if direction in ("out", "both"):
            sql_parts.append("SELECT * FROM graph_edges WHERE site_id=? AND source_id=?")
            params += [sid, cur]
        if direction in ("in", "both"):
            sql_parts.append("SELECT * FROM graph_edges WHERE site_id=? AND target_id=?")
            params += [sid, cur]
        for e in rows(conn, " UNION ".join(sql_parts), params):
            if edge_types and e["edge_type"] not in edge_types:
                continue
            edges_out.append(_edge(e))
            for nxt in (e["source_id"], e["target_id"]):
                if nxt not in seen and len(seen) < _lim(limit, 100):
                    seen[nxt] = d + 1
                    q.append(nxt)
    nodes = [_node(r) | {"distance": seen[r["node_id"]]} for r in rows(conn, f"SELECT * FROM graph_nodes WHERE site_id=? AND node_id IN ({','.join('?' * len(seen))})", [sid, *seen])]
    return {"root": nid, "nodes": nodes, "edges": edges_out}


def get_subgraph(conn, sid, node_types: list[str] | None = None, edge_types: list[str] | None = None, limit: int = 300) -> dict:
    sql, params = "SELECT * FROM graph_nodes WHERE site_id=?", [sid]
    if node_types:
        sql += f" AND node_type IN ({','.join('?' * len(node_types))})"
        params += [t.upper() for t in node_types]
    sql += " ORDER BY pagerank DESC NULLS LAST LIMIT ?"
    params.append(_lim(limit, 300))
    nodes = [_node(r) for r in rows(conn, sql, params)]
    ids = {n["node_id"] for n in nodes}
    esql, ep = "SELECT * FROM graph_edges WHERE site_id=?", [sid]
    if edge_types:
        esql += f" AND edge_type IN ({','.join('?' * len(edge_types))})"
        ep += edge_types
    edges = [_edge(e) for e in rows(conn, esql, ep) if e["source_id"] in ids and e["target_id"] in ids]
    return {"nodes": nodes, "edges": edges}


def _nx_graph(conn, sid, edge_types: list[str] | None = None) -> nx.DiGraph:
    G = nx.DiGraph()
    for e in rows(conn, "SELECT source_id, target_id, edge_type, weight FROM graph_edges WHERE site_id=?", (sid,)):
        if edge_types and e["edge_type"] not in edge_types:
            continue
        G.add_edge(e["source_id"], e["target_id"], type=e["edge_type"], weight=e["weight"])
    return G


def find_path(conn, sid, src: str, dst: str, edge_types: list[str] | None = None, max_paths: int = 3, max_depth: int = 6) -> dict:
    a, b = resolve_node_id(conn, sid, src), resolve_node_id(conn, sid, dst)
    if not a or not b:
        return {"error": f"node not found: {src if not a else dst}"}
    G = _nx_graph(conn, sid, edge_types)
    out = {"source": a, "target": b, "paths": []}
    if a not in G or b not in G:
        return out | {"note": "one endpoint has no edges of the requested types"}
    try:
        sp = nx.shortest_path(G, a, b)
        out["shortest_path"] = [{"node_id": n, "label": _label(conn, sid, n)} for n in sp]
    except nx.NetworkXNoPath:
        out["shortest_path"] = None
    try:
        for i, p in enumerate(nx.all_simple_paths(G, a, b, cutoff=max_depth)):
            if i >= max_paths:
                break
            out["paths"].append([{"node_id": n, "label": _label(conn, sid, n)} for n in p])
    except nx.NetworkXNoPath:
        pass
    # undirected fallback (e.g. entity <-> page)
    if not out.get("shortest_path"):
        U = G.to_undirected()
        try:
            sp = nx.shortest_path(U, a, b)
            out["undirected_shortest_path"] = [{"node_id": n, "label": _label(conn, sid, n)} for n in sp]
        except nx.NetworkXNoPath:
            out["undirected_shortest_path"] = None
    return out


# --- SEO ------------------------------------------------------------------------
def find_orphans(conn, sid, include_nav_only: bool = False, limit: int = 100) -> list[dict]:
    types = ["orphan"] + (["no_body_inbound_links"] if include_nav_only else [])
    out = []
    for r in rows(conn, f"SELECT p.problem_type, p.severity, p.url, p.detail, g.title, g.indexable, g.in_sitemap FROM seo_problems p JOIN pages g ON g.site_id=p.site_id AND g.url=p.url "
                        f"WHERE p.site_id=? AND p.problem_type IN ({','.join('?' * len(types))}) ORDER BY p.problem_type, p.url LIMIT ?", [sid, *types, _lim(limit, 100)]):
        out.append({"url": unquote(r["url"]), "title": r["title"], "problem_type": r["problem_type"], "severity": r["severity"],
                    "in_sitemap": bool(r["in_sitemap"]), "detail": json.loads(r["detail"] or "{}")})
    return out


def find_cannibalization(conn, sid, min_confidence: float = 0.0, limit: int = 50) -> list[dict]:
    out = []
    for r in rows(conn, "SELECT * FROM seo_opportunities WHERE site_id=? AND opp_type='cannibalization_candidate' AND confidence>=? ORDER BY confidence DESC LIMIT ?", (sid, min_confidence, _lim(limit))):
        d = json.loads(r["detail"] or "{}")
        d.update({"page_a": unquote(d.get("page_a", "")), "page_b": unquote(d.get("page_b", "")), "confidence": r["confidence"], "reason": r["reason"]})
        out.append(d)
    return out


def find_internal_link_opportunities(conn, sid, page: str | None = None, as_target: bool = False, limit: int = 30) -> list[dict]:
    sql, params = "SELECT * FROM seo_opportunities WHERE site_id=? AND opp_type='internal_link'", [sid]
    if page:
        nid = resolve_node_id(conn, sid, page)
        url = one(conn, "SELECT url FROM graph_nodes WHERE site_id=? AND node_id=?", (sid, nid))["url"] if nid else page
        sql += " AND related_url=?" if as_target else " AND url=?"
        params.append(url)
    sql += " ORDER BY score DESC LIMIT ?"
    params.append(_lim(limit))
    out = []
    for r in rows(conn, sql, params):
        d = json.loads(r["detail"] or "{}")
        out.append({"source_page": unquote(r["url"]), "target_page": unquote(r["related_url"]), "potential_anchor": d.get("potential_anchor"),
                    "reason": r["reason"], "confidence": r["confidence"], "score": r["score"], "score_breakdown": json.loads(r["score_breakdown"] or "{}")})
    return out


def get_gsc_page_data(conn, sid, page: str | None = None, min_position: float | None = None, max_position: float | None = None,
                      min_impressions: int = 0, order_by: str = "impressions", limit: int = 50) -> dict:
    if not one(conn, "SELECT 1 FROM gsc_query_page WHERE site_id=? LIMIT 1", (sid,)):
        return {"status": "NO_GSC_DATA", "note": "GSC has not been synced (run scripts/sync-gsc.py). Rows: 0", "rows": []}
    ob = {"impressions": "impressions DESC", "clicks": "clicks DESC", "position": "position ASC", "ctr": "ctr ASC"}.get(order_by, "impressions DESC")
    sql = ("SELECT page, SUM(clicks) clicks, SUM(impressions) impressions, CASE WHEN SUM(impressions)>0 THEN 1.0*SUM(clicks)/SUM(impressions) END ctr, "
           "CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) END position, COUNT(*) queries, MIN(date_from) date_from, MAX(date_to) date_to "
           "FROM gsc_query_page WHERE site_id=?")
    params: list = [sid]
    if page:
        nid = resolve_node_id(conn, sid, page)
        url = one(conn, "SELECT url FROM graph_nodes WHERE site_id=? AND node_id=?", (sid, nid))["url"] if nid else page
        sql += " AND page=?"
        params.append(url)
    # Filter on the aggregated subquery: inside HAVING, SQLite would resolve bare `position`/`impressions`
    # to the raw per-row column instead of the weighted aggregate alias (surfaced by acceptance test 4).
    sql = f"SELECT * FROM ({sql} GROUP BY page) agg WHERE impressions>=?"
    params.append(min_impressions)
    if min_position is not None:
        sql += " AND position>=?"
        params.append(min_position)
    if max_position is not None:
        sql += " AND position<=?"
        params.append(max_position)
    sql += f" ORDER BY {ob} LIMIT ?"
    params.append(_lim(limit))
    out = []
    for r in rows(conn, sql, params):
        out.append({"page": unquote(r["page"]), "clicks": r["clicks"], "impressions": r["impressions"], "ctr": round(r["ctr"] or 0, 4),
                    "position": round(r["position"] or 0, 1), "queries": r["queries"], "date_from": r["date_from"], "date_to": r["date_to"]})
    return {"status": "OK", "rows": out}


def get_gsc_query_data(conn, sid, query: str | None = None, page: str | None = None, min_impressions: int = 0,
                       min_position: float | None = None, max_position: float | None = None, important_only: bool = False,
                       order_by: str = "impressions", limit: int = 50) -> dict:
    if not one(conn, "SELECT 1 FROM gsc_query_page WHERE site_id=? LIMIT 1", (sid,)):
        return {"status": "NO_GSC_DATA", "note": "GSC has not been synced (run scripts/sync-gsc.py). Rows: 0", "rows": []}
    ob = {"impressions": "impressions DESC", "clicks": "clicks DESC", "position": "position ASC", "ctr": "ctr ASC"}.get(order_by, "impressions DESC")
    if page:
        nid = resolve_node_id(conn, sid, page)
        url = one(conn, "SELECT url FROM graph_nodes WHERE site_id=? AND node_id=?", (sid, nid))["url"] if nid else page
        sql, params = "SELECT query, page, clicks, impressions, ctr, position FROM gsc_query_page WHERE site_id=? AND page=? AND impressions>=?", [sid, url, min_impressions]
        if query:
            sql += " AND query LIKE ?"
            params.append(f"%{query}%")
    else:
        sql, params = "SELECT query, NULL page, clicks, impressions, ctr, position, pages_count, is_important, importance_reason FROM queries WHERE site_id=? AND impressions>=?", [sid, min_impressions]
        if query:
            sql += " AND query LIKE ?"
            params.append(f"%{query}%")
        if important_only:
            sql += " AND is_important=1"
    if min_position is not None:
        sql += " AND position>=?"
        params.append(min_position)
    if max_position is not None:
        sql += " AND position<=?"
        params.append(max_position)
    sql += f" ORDER BY {ob} LIMIT ?"
    params.append(_lim(limit))
    out = [dict(r) | {"page": unquote(r["page"]) if r.get("page") else None, "ctr": round(r["ctr"] or 0, 4), "position": round(r["position"] or 0, 1)} for r in rows(conn, sql, params)]
    return {"status": "OK", "rows": out}


def get_page_seo_data(conn, sid, page: str) -> dict | None:
    nid = resolve_node_id(conn, sid, page)
    if not nid:
        return None
    n = one(conn, "SELECT * FROM graph_nodes WHERE site_id=? AND node_id=?", (sid, nid))
    url = n["url"]
    p = one(conn, "SELECT * FROM pages WHERE site_id=? AND url=?", (sid, url)) or {}
    post = one(conn, "SELECT wp_id, type, slug, title, excerpt, status, date_gmt, modified_gmt, word_count, yoast_title, yoast_description, yoast_canonical, yoast_robots FROM posts WHERE site_id=? AND url=?", (sid, url)) or {}
    inbound = rows(conn, "SELECT source_url, anchor_text, is_nav FROM links WHERE site_id=? AND target_url=? AND is_internal=1 AND source_url!=target_url", (sid, url))
    outbound = rows(conn, "SELECT target_url, anchor_text, is_nav, is_internal FROM links WHERE site_id=? AND source_url=? AND source_url!=target_url", (sid, url))
    problems = [{"type": r["problem_type"], "severity": r["severity"], "detail": json.loads(r["detail"] or "{}")} for r in rows(conn, "SELECT problem_type, severity, detail FROM seo_problems WHERE site_id=? AND url=?", (sid, url))]
    opps = [{"type": r["opp_type"], "score": r["score"], "reason": r["reason"], "related": unquote(r["related_url"] or ""), "query": r["query"]} for r in rows(conn, "SELECT opp_type, score, reason, related_url, query FROM seo_opportunities WHERE site_id=? AND url=? ORDER BY score DESC LIMIT 20", (sid, url))]
    ents = [{"type": r["entity_type"], "entity": r["name"], "score": r["score"], "in_title": bool(r["in_title"]), "in_h1": bool(r["in_h1"]), "mentions": r["mentions"]}
            for r in rows(conn, "SELECT m.*, e.name FROM entity_mentions m JOIN entities e ON e.site_id=m.site_id AND e.entity_type=m.entity_type AND e.slug=m.entity_slug WHERE m.site_id=? AND m.url=? ORDER BY m.score DESC", (sid, url))]
    gsc = get_gsc_page_data(conn, sid, page=url)
    top_q = get_gsc_query_data(conn, sid, page=url, limit=15) if gsc.get("status") == "OK" else None
    return {
        "node_id": nid, "type": n["node_type"], "url": unquote(url), "label": n["label"],
        "crawl": {k: (json.loads(p[k]) if k in ("h1", "h2", "schema_types", "redirect_chain", "images") and p.get(k) else p.get(k)) for k in
                  ("status_code", "final_url", "redirect_chain", "title", "meta_description", "h1", "h1_count", "h2", "canonical", "robots_meta", "x_robots_tag",
                   "indexable", "indexability_reason", "word_count", "language", "images_missing_alt", "internal_links_out", "external_links_out",
                   "schema_types", "content_hash", "in_sitemap", "depth", "response_time_ms", "last_crawled")} if p else None,
        "wordpress": post or None,
        "internal_links_in": {"count": len({l["source_url"] for l in inbound}), "body_count": len({l["source_url"] for l in inbound if not l["is_nav"]}),
                              "sources": [{"url": unquote(l["source_url"]), "anchor": l["anchor_text"], "nav": bool(l["is_nav"])} for l in inbound[:50]]},
        "internal_links_out": [{"url": unquote(l["target_url"]), "anchor": l["anchor_text"], "nav": bool(l["is_nav"])} for l in outbound if l["is_internal"]][:50],
        "external_links_out": [{"url": l["target_url"], "anchor": l["anchor_text"]} for l in outbound if not l["is_internal"]][:50],
        "entities": ents, "gsc": (gsc["rows"][0] if gsc.get("rows") else gsc), "top_queries": (top_q or {}).get("rows"),
        "problems": problems, "opportunities": opps, "pagerank": n["pagerank"], "community": n["community"], "vault_path": n["vault_path"],
    }


def get_site_structure(conn, sid) -> dict:
    site = one(conn, "SELECT * FROM sites WHERE site_id=?", (sid,))
    cats = rows(conn, "SELECT wp_id, name, slug, url, parent_wp_id, count FROM categories WHERE site_id=? ORDER BY parent_wp_id, name", (sid,))
    by_parent: dict[int, list] = {}
    for c in cats:
        by_parent.setdefault(c["parent_wp_id"] or 0, []).append(c)
    posts = rows(conn, "SELECT p.wp_id, p.type, p.url, p.title, p.word_count FROM posts p WHERE site_id=? ORDER BY type, title", (sid,))
    post_cats = {}
    for r in rows(conn, "SELECT post_wp_id, term_wp_id FROM post_terms WHERE site_id=? AND taxonomy='category'", (sid,)):
        post_cats.setdefault(r["term_wp_id"], []).append(r["post_wp_id"])
    post_by_id = {p["wp_id"]: p for p in posts if p["type"] == "post"}

    def tree(parent=0):
        out = []
        for c in by_parent.get(parent, []):
            out.append({"category": c["name"], "slug": unquote(c["slug"]), "url": unquote(c["url"] or ""), "post_count": c["count"],
                        "posts": [{"title": post_by_id[pid]["title"], "url": unquote(post_by_id[pid]["url"])} for pid in post_cats.get(c["wp_id"], []) if pid in post_by_id],
                        "children": tree(c["wp_id"])})
        return out

    ents = rows(conn, "SELECT entity_type, name, slug, parent_slug, aliases FROM entities WHERE site_id=? ORDER BY entity_type, name", (sid,))
    return {
        "site": {"site_id": sid, "name": site["name"], "url": site["canonical_url"], "language": site["language"]} if site else None,
        "pages": [{"title": p["title"], "url": unquote(p["url"]), "word_count": p["word_count"]} for p in posts if p["type"] == "page"],
        "category_tree": tree(0),
        "custom_post_types": sorted({p["type"] for p in posts if p["type"] not in ("post", "page")}),
        "entities": {t: [{"name": e["name"], "aliases": json.loads(e["aliases"] or "[]"), "parent": e["parent_slug"]} for e in ents if e["entity_type"] == t] for t in ("SERVICE", "BRAND", "MODEL", "LOCATION")},
        "counts": get_site_summary(conn, sid)["counts"],
    }


def list_entities(conn, sid, entity_type: str) -> list[dict]:
    out = []
    for e in rows(conn, "SELECT * FROM entities WHERE site_id=? AND entity_type=? ORDER BY name", (sid, entity_type)):
        pages = rows(conn, "SELECT url, score, in_title FROM entity_mentions WHERE site_id=? AND entity_type=? AND entity_slug=? ORDER BY score DESC LIMIT 20", (sid, entity_type, e["slug"]))
        out.append({"name": e["name"], "slug": e["slug"], "aliases": json.loads(e["aliases"] or "[]"), "parent": e["parent_slug"], "source": e["source"],
                    "evidence": json.loads(e["evidence"] or "[]"), "pages": [{"url": unquote(p["url"]), "score": p["score"], "in_title": bool(p["in_title"])} for p in pages]})
    return out


def get_categories(conn, sid) -> list[dict]:
    return [{"name": c["name"], "slug": unquote(c["slug"]), "url": unquote(c["url"] or ""), "parent_wp_id": c["parent_wp_id"], "post_count": c["count"], "taxonomy": c["taxonomy"],
             "crawl": (lambda p: {"indexable": p["indexable"], "inbound_links": None, "word_count": p["word_count"]} if p else None)(one(conn, "SELECT indexable, word_count FROM pages WHERE site_id=? AND url=?", (sid, c["url"])))}
            for c in rows(conn, "SELECT * FROM categories WHERE site_id=? ORDER BY parent_wp_id, name", (sid,))]


def get_seo_problems(conn, sid, problem_type: str | None = None, severity: str | None = None, page: str | None = None, limit: int = 100) -> dict:
    sql, params = "SELECT * FROM seo_problems WHERE site_id=?", [sid]
    if problem_type:
        sql += " AND problem_type=?"; params.append(problem_type)
    if severity:
        sql += " AND severity=?"; params.append(severity)
    if page:
        nid = resolve_node_id(conn, sid, page)
        url = one(conn, "SELECT url FROM graph_nodes WHERE site_id=? AND node_id=?", (sid, nid))["url"] if nid else page
        sql += " AND url=?"; params.append(url)
    sql += " ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, problem_type, url LIMIT ?"
    params.append(_lim(limit, 100))
    items = [{"type": r["problem_type"], "severity": r["severity"], "url": unquote(r["url"] or ""), "related_url": unquote(r["related_url"] or ""), "detail": json.loads(r["detail"] or "{}")} for r in rows(conn, sql, params)]
    summary = {r["problem_type"]: {"count": r["n"], "severity": r["severity"]} for r in rows(conn, "SELECT problem_type, severity, count(*) n FROM seo_problems WHERE site_id=? GROUP BY 1,2", (sid,))}
    return {"summary": summary, "items": items}


def get_seo_opportunities(conn, sid, opp_type: str | None = None, page: str | None = None, min_score: float = 0.0, limit: int = 50) -> dict:
    sql, params = "SELECT * FROM seo_opportunities WHERE site_id=? AND score>=?", [sid, min_score]
    if opp_type:
        sql += " AND opp_type=?"; params.append(opp_type)
    if page:
        nid = resolve_node_id(conn, sid, page)
        url = one(conn, "SELECT url FROM graph_nodes WHERE site_id=? AND node_id=?", (sid, nid))["url"] if nid else page
        sql += " AND (url=? OR related_url=?)"; params += [url, url]
    sql += " ORDER BY score DESC LIMIT ?"
    params.append(_lim(limit))
    items = [{"type": r["opp_type"], "url": unquote(r["url"] or ""), "related_url": unquote(r["related_url"] or ""), "query": r["query"], "score": r["score"],
              "score_breakdown": json.loads(r["score_breakdown"] or "{}"), "reason": r["reason"], "confidence": r["confidence"], "detail": json.loads(r["detail"] or "{}")}
             for r in rows(conn, sql, params)]
    summary = {r["opp_type"]: {"count": r["n"], "avg_score": round(r["s"] or 0, 3)} for r in rows(conn, "SELECT opp_type, count(*) n, avg(score) s FROM seo_opportunities WHERE site_id=? GROUP BY 1", (sid,))}
    return {"summary": summary, "items": items}


def get_site_summary(conn, sid) -> dict:
    site = one(conn, "SELECT * FROM sites WHERE site_id=?", (sid,))
    c = lambda sql, p=(): (conn.execute(sql, (sid, *p)).fetchone() or [0])[0]  # noqa: E731
    counts = {
        "crawled_urls": c("SELECT count(*) FROM pages WHERE site_id=? AND crawl_status='ok'"),
        "indexable_urls": c("SELECT count(*) FROM pages WHERE site_id=? AND indexable=1"),
        "non_indexable_urls": c("SELECT count(*) FROM pages WHERE site_id=? AND indexable=0"),
        "wp_pages": c("SELECT count(*) FROM posts WHERE site_id=? AND type='page'"),
        "wp_posts": c("SELECT count(*) FROM posts WHERE site_id=? AND type='post'"),
        "wp_custom_post_type_items": c("SELECT count(*) FROM posts WHERE site_id=? AND type NOT IN ('post','page')"),
        "categories": c("SELECT count(*) FROM categories WHERE site_id=?"),
        "tags": c("SELECT count(*) FROM tags WHERE site_id=?"),
        "media": c("SELECT count(*) FROM media WHERE site_id=?"),
        "internal_links": c("SELECT count(*) FROM links WHERE site_id=? AND is_internal=1"),
        "external_links": c("SELECT count(*) FROM links WHERE site_id=? AND is_internal=0"),
        "entities": c("SELECT count(*) FROM entities WHERE site_id=?"),
        "gsc_daily_rows": c("SELECT count(*) FROM gsc_daily WHERE site_id=?"),
        "gsc_queries": c("SELECT count(*) FROM queries WHERE site_id=?"),
        "seo_problems": c("SELECT count(*) FROM seo_problems WHERE site_id=?"),
        "seo_opportunities": c("SELECT count(*) FROM seo_opportunities WHERE site_id=?"),
        "graph_nodes": c("SELECT count(*) FROM graph_nodes WHERE site_id=?"),
        "graph_edges": c("SELECT count(*) FROM graph_edges WHERE site_id=?"),
    }
    last = {}
    for r in rows(conn, "SELECT source, MAX(finished_at) t, status FROM sync_runs WHERE site_id=? GROUP BY source", (sid,)):
        last[r["source"]] = {"finished_at": r["t"], "status": r["status"]}
    cr = one(conn, "SELECT run_id, finished_at, urls_crawled, status FROM crawl_runs WHERE site_id=? ORDER BY id DESC LIMIT 1", (sid,))
    if cr:
        last["crawl"] = dict(cr)
    gsc_range = one(conn, "SELECT MIN(date) d0, MAX(date) d1 FROM gsc_daily WHERE site_id=?", (sid,))
    return {
        "site": {"site_id": sid, "name": site["name"], "url": site["canonical_url"], "language": site["language"], "gsc_property": site["gsc_property"]} if site else {"site_id": sid},
        "counts": counts,
        "gsc_status": "OK" if counts["gsc_daily_rows"] else "NO_GSC_DATA (not synced yet)",
        "gsc_date_range": dict(gsc_range) if gsc_range and gsc_range["d0"] else None,
        "problems_by_type": {r["problem_type"]: r["n"] for r in rows(conn, "SELECT problem_type, count(*) n FROM seo_problems WHERE site_id=? GROUP BY 1", (sid,))},
        "opportunities_by_type": {r["opp_type"]: r["n"] for r in rows(conn, "SELECT opp_type, count(*) n FROM seo_opportunities WHERE site_id=? GROUP BY 1", (sid,))},
        "nodes_by_type": {r["node_type"]: r["n"] for r in rows(conn, "SELECT node_type, count(*) n FROM graph_nodes WHERE site_id=? GROUP BY 1", (sid,))},
        "last_runs": last,
        "read_only": True,
    }
