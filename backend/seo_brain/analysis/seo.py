"""SEO analyses (spec §37-41). Every finding is stored with an explainable `detail`/`score_breakdown`.

Problems  -> seo_problems     (orphan, no_inbound_links, low_inbound_links, high_outbound_links, missing_h1, multiple_h1,
                               duplicate_title, duplicate_h1, missing_canonical, important_non_indexable, thin_content,
                               missing_meta_description, images_missing_alt, redirect_in_sitemap)
Opportunities -> seo_opportunities (striking_distance [pos 4-15], ctr_opportunity [high impressions/low CTR],
                               cannibalization_candidate, internal_link)
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit

from rapidfuzz import fuzz

from ..common.config import SiteConfig
from ..common.logging_setup import new_run_id
from ..database.db import j, rows, upsert, utcnow

log = logging.getLogger("analysis.seo")

THIN_WORDS = 300
LOW_INBOUND = 2
HIGH_OUTBOUND = 100
CTR_MIN_IMPRESSIONS = 100
CTR_EXPECTED_BY_POS = [(1, 0.28), (2, 0.15), (3, 0.11), (4, 0.08), (5, 0.07), (6, 0.05), (7, 0.04), (8, 0.03), (10, 0.025), (20, 0.015)]


def expected_ctr(pos: float) -> float:
    for p, c in CTR_EXPECTED_BY_POS:
        if pos <= p:
            return c
    return 0.01


def _h1_comparison_url(url: str) -> str:
    """Treat pages of one archive as one heading context, not competing documents."""
    parts = urlsplit(url)
    path = re.sub(r"/page/(?:[2-9]|[1-9]\d+)/?$", "/", unquote(parts.path))
    return f"{parts.scheme}://{parts.netloc}{path.rstrip('/')}/"


def _redirects_to_other_document(page: sqlite3.Row) -> bool:
    """A redirect's final HTML belongs to its destination, not its source URL."""
    if not page["redirect_chain"] or page["redirect_chain"] == "[]" or not page["final_url"]:
        return False
    source = unquote(urlsplit(page["url"]).path).rstrip("/").casefold()
    destination = unquote(urlsplit(page["final_url"]).path).rstrip("/").casefold()
    return source != destination


def _distinct_document_urls(urls: list[str], by_url: dict, *, collapse_pagination: bool = True) -> list[str]:
    """Collapse identical canonical aliases; pagination may share H1 but should have unique titles."""
    unique_pages = {}
    for url in sorted(urls, key=lambda value: (bool(re.search(r"/page/(?:[2-9]|[1-9]\d+)/?$", urlsplit(value).path)), value)):
        unique_pages.setdefault(_h1_comparison_url(url) if collapse_pagination else url, url)
    aliases = {}
    for url in sorted(unique_pages.values(), key=lambda value: (by_url[value]["canonical"] != value, value)):
        page = by_url[url]
        canonical = page["canonical"] or ""
        content_hash = page["content_hash"] or ""
        if canonical and content_hash and urlsplit(canonical).netloc == urlsplit(url).netloc:
            identity = (_h1_comparison_url(canonical) if collapse_pagination else canonical.rstrip("/") + "/",
                        content_hash)
        else:
            identity = (_h1_comparison_url(url) if collapse_pagination else url, url)
        aliases.setdefault(identity, url)
    return list(aliases.values())


def _clear(conn, sid, run_id):
    conn.execute("DELETE FROM seo_problems WHERE site_id=?", (sid,))
    conn.execute("DELETE FROM seo_opportunities WHERE site_id=?", (sid,))


def _problem(conn, sid, ptype, severity, url, detail: dict, related_url=None, run_id=None):
    upsert(conn, "seo_problems", {"site_id": sid, "problem_type": ptype, "severity": severity, "url": url,
                                  "related_url": related_url or "", "detail": j(detail), "run_id": run_id},
           ["site_id", "problem_type", "url", "related_url"])


def _opp(conn, sid, otype, url, score, breakdown: dict, reason: str, confidence: float, detail: dict,
         related_url=None, query=None, run_id=None):
    upsert(conn, "seo_opportunities", {"site_id": sid, "opp_type": otype, "url": url, "related_url": related_url or "",
                                       "query": query or "", "score": round(score, 3), "score_breakdown": j(breakdown),
                                       "reason": reason, "confidence": round(confidence, 2), "detail": j(detail), "run_id": run_id},
           ["site_id", "opp_type", "url", "related_url", "query"])


def run_analysis(conn: sqlite3.Connection, site: SiteConfig) -> dict:
    sid = site.site_id
    run_id = new_run_id("analysis")
    conn.execute("INSERT INTO sync_runs(run_id, site_id, source, started_at, status) VALUES (?,?,?,?,?)",
                 (run_id, sid, "analysis", utcnow(), "running"))
    _clear(conn, sid, run_id)
    # Pages are retained across crawls for history and targeted verification.
    # An uncapped full crawl replaces the previous snapshot. A capped daily
    # crawl covers only a rotating slice, so combine pages seen within the
    # last 30 days instead of analysing just its most recent 20 URLs.
    full_crawl = None
    sitemap_urls = 0
    for crawl in rows(conn, "SELECT started_at,status,notes FROM crawl_runs WHERE site_id=? AND status IN ('completed','completed_capped') ORDER BY started_at DESC LIMIT 100", (sid,)):
        try:
            notes = json.loads(crawl["notes"] or "{}")
        except (ValueError, TypeError):
            notes = {}
        if not isinstance(notes, dict) or notes.get("scope") != "targeted":
            sitemap_urls = max(0, int(notes.get("sitemap_urls") or 0)) if isinstance(notes, dict) else 0
            full_crawl = ((datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
                          if crawl["status"] == "completed_capped" else crawl["started_at"])
            break
    # Missing inbound links cannot be inferred from a graph built from only a
    # rotating slice of the sitemap. Positive per-page observations remain valid.
    link_graph_complete = True
    fresh_sitemap_pages = 0
    if sitemap_urls:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
        fresh_sitemap_pages = conn.execute(
            "SELECT COUNT(*) FROM pages WHERE site_id=? AND in_sitemap=1 AND crawl_status='ok' "
            "AND h1_count IS NOT NULL AND last_crawled>=?", (sid, cutoff)
        ).fetchone()[0]
        link_graph_complete = fresh_sitemap_pages >= sitemap_urls
    page_sql = "SELECT * FROM pages WHERE site_id=? AND crawl_status='ok' AND h1_count IS NOT NULL"
    crawled_pages = rows(conn, page_sql + (" AND last_crawled>=?" if full_crawl else ""),
                         (sid, full_crawl) if full_crawl else (sid,))
    pages = [page for page in crawled_pages if not _redirects_to_other_document(page)]
    by_url = {p["url"]: p for p in pages}
    home = site.canonical_url
    # inbound/outbound from real crawled links (distinct source pages, self-links excluded)
    inbound_all = defaultdict(set)
    inbound_body = defaultdict(set)
    outbound = defaultdict(set)
    for l in rows(conn, "SELECT source_url, target_url, is_nav, anchor_text FROM links WHERE site_id=? AND is_internal=1", (sid,)):
        if l["source_url"] not in by_url or l["source_url"] == l["target_url"]:
            continue
        outbound[l["source_url"]].add(l["target_url"])
        inbound_all[l["target_url"]].add(l["source_url"])
        if not l["is_nav"]:
            inbound_body[l["target_url"]].add(l["source_url"])
    gsc_impressions = {r["page"]: r["impressions"] for r in rows(
        conn, "SELECT page, SUM(impressions) AS impressions FROM gsc_query_page WHERE site_id=? GROUP BY page", (sid,))}
    counts = {"problems": 0, "opportunities": 0}

    # Report a stale sitemap entry at its source URL, but never attribute the
    # destination's headings, images or links to that redirected URL.
    for p in crawled_pages:
        if p["redirect_chain"] and json.loads(p["redirect_chain"]) and p["in_sitemap"] and p["final_url"] and p["final_url"] != p["url"]:
            _problem(conn, sid, "redirect_in_sitemap", "medium", p["url"],
                     {"chain": json.loads(p["redirect_chain"]), "final_url": p["final_url"]}, run_id=run_id)
            counts["problems"] += 1

    # --- link structure ---------------------------------------------------------
    for p in pages:
        u = p["url"]
        if p["status_code"] != 200:
            continue
        n_all, n_body = len(inbound_all[u]), len(inbound_body[u])
        is_home = u == home
        if link_graph_complete and p["indexable"] == 1 and not is_home:
            if n_all == 0:
                _problem(conn, sid, "orphan", "high", u, {"definition": "indexable page with zero internal inbound links in crawled link graph",
                                                          "in_sitemap": p["in_sitemap"], "inbound_links": 0}, run_id=run_id)
                counts["problems"] += 1
            elif n_body == 0:
                _problem(conn, sid, "no_body_inbound_links", "medium", u, {"definition": "only navigation/footer links point here (no contextual inbound links)",
                                                                           "inbound_nav_sources": sorted(inbound_all[u])[:20]}, run_id=run_id)
                counts["problems"] += 1
            elif n_all < LOW_INBOUND:
                _problem(conn, sid, "low_inbound_links", "low", u, {"inbound_sources": sorted(inbound_all[u]), "threshold": LOW_INBOUND}, run_id=run_id)
                counts["problems"] += 1
        if len(outbound[u]) > HIGH_OUTBOUND:
            _problem(conn, sid, "high_outbound_links", "low", u, {"outbound_unique_targets": len(outbound[u]), "threshold": HIGH_OUTBOUND}, run_id=run_id)
            counts["problems"] += 1

    # --- on-page ------------------------------------------------------------------
    titles = defaultdict(list)
    h1s = defaultdict(list)
    for p in pages:
        if p["status_code"] != 200:
            continue
        u = p["url"]
        h1 = json.loads(p["h1"] or "[]")
        if p["h1_count"] == 0:
            _problem(conn, sid, "missing_h1", "high" if p["indexable"] else "low", u, {"title": p["title"]}, run_id=run_id); counts["problems"] += 1
        elif p["h1_count"] > 1:
            _problem(conn, sid, "multiple_h1", "medium", u, {"h1_count": p["h1_count"], "h1": h1[:10]}, run_id=run_id); counts["problems"] += 1
        if p["indexable"] == 1 and not p["canonical"]:
            _problem(conn, sid, "missing_canonical", "medium", u, {}, run_id=run_id); counts["problems"] += 1
        if p["indexable"] == 1 and not p["meta_description"]:
            _problem(conn, sid, "missing_meta_description", "low", u, {"title": p["title"]}, run_id=run_id); counts["problems"] += 1
        # A noindex archive linked from every global menu is often intentional.
        # Contextual links, sitemap inclusion or search impressions are stronger
        # signals that a non-indexable page merits an explicit review.
        if p["indexable"] == 0 and (p["in_sitemap"] or len(inbound_body[u]) >= 3 or gsc_impressions.get(u, 0) > 0):
            _problem(conn, sid, "important_non_indexable", "high", u, {"reason": p["indexability_reason"], "in_sitemap": p["in_sitemap"],
                                                                        "inbound_links": len(inbound_all[u]),
                                                                        "body_inbound_links": len(inbound_body[u]),
                                                                        "gsc_impressions": gsc_impressions.get(u, 0)}, run_id=run_id); counts["problems"] += 1
        if p["indexable"] == 1 and (p["word_count"] or 0) < THIN_WORDS and "/category/" not in u and "/page/" not in u:
            _problem(conn, sid, "thin_content", "medium", u, {"word_count": p["word_count"], "threshold": THIN_WORDS}, run_id=run_id); counts["problems"] += 1
        if (p["images_missing_alt"] or 0) > 0:
            _problem(conn, sid, "images_missing_alt", "low", u, {"images_missing_alt": p["images_missing_alt"]}, run_id=run_id); counts["problems"] += 1
        if p["title"]:
            titles[p["title"].strip()].append(u)
        if h1:
            h1s[h1[0].strip()].append(u)
    for t, urls in titles.items():
        distinct_urls = _distinct_document_urls(urls, by_url, collapse_pagination=False)
        if len(distinct_urls) > 1:
            for u in distinct_urls:
                _problem(conn, sid, "duplicate_title", "medium", u,
                         {"title": t, "shared_with": [x for x in distinct_urls if x != u]}, run_id=run_id)
                counts["problems"] += 1
    for h, urls in h1s.items():
        distinct_urls = _distinct_document_urls(urls, by_url)
        if len(distinct_urls) > 1:
            for u in distinct_urls:
                _problem(conn, sid, "duplicate_h1", "medium", u,
                         {"h1": h, "shared_with": [x for x in distinct_urls if x != u]}, run_id=run_id)
                counts["problems"] += 1

    # --- GSC-driven ---------------------------------------------------------------
    qp = rows(conn, "SELECT * FROM gsc_query_page WHERE site_id=?", (sid,))
    if qp:
        # positions 4-15 (striking distance)
        by_page = defaultdict(list)
        for r in qp:
            by_page[r["page"]].append(r)
        for page, rs in by_page.items():
            imp = sum(r["impressions"] for r in rs)
            clicks = sum(r["clicks"] for r in rs)
            pos = sum(r["position"] * r["impressions"] for r in rs) / imp if imp else 0
            sd = [r for r in rs if 4 <= r["position"] <= 15 and r["impressions"] >= 10]
            if sd:
                sd.sort(key=lambda r: -r["impressions"])
                imp_sd = sum(r["impressions"] for r in sd)
                breakdown = {"impression_potential": min(1.0, imp_sd / 1000), "ranking_potential": 1 - (min(pos, 15) - 4) / 11 if pos >= 4 else 1.0,
                             "internal_link_potential": 1 - min(len(inbound_all[page]), 10) / 10, "queries_in_range": len(sd)}
                score = 0.4 * breakdown["impression_potential"] + 0.35 * breakdown["ranking_potential"] + 0.25 * breakdown["internal_link_potential"]
                _opp(conn, sid, "striking_distance", page, score, breakdown,
                     f"{len(sd)} queries ranking 4-15 with {imp_sd} impressions; avg position {pos:.1f}", 0.8,
                     {"top_queries": [{"query": r["query"], "position": round(r["position"], 1), "impressions": r["impressions"], "clicks": r["clicks"]} for r in sd[:10]],
                      "inbound_links": len(inbound_all[page])}, run_id=run_id); counts["opportunities"] += 1
            # CTR opportunity
            ctr = clicks / imp if imp else 0
            exp = expected_ctr(pos) if pos else 0
            if imp >= CTR_MIN_IMPRESSIONS and pos and pos <= 20 and ctr < 0.6 * exp:
                gain = (exp - ctr) * imp
                breakdown = {"impressions": imp, "ctr": round(ctr, 4), "expected_ctr": exp, "estimated_extra_clicks": round(gain, 1), "position": round(pos, 1)}
                _opp(conn, sid, "ctr_opportunity", page, min(1.0, gain / 100), breakdown,
                     f"CTR {ctr:.1%} vs expected ~{exp:.1%} at position {pos:.1f} on {imp} impressions", 0.7,
                     {"title": (by_url.get(page) or {}).get("title"), "meta_description": (by_url.get(page) or {}).get("meta_description")}, run_id=run_id); counts["opportunities"] += 1
        # cannibalization candidates
        by_query = defaultdict(list)
        for r in qp:
            by_query[r["query"]].append(r)
        for q, rs in by_query.items():
            rs = [r for r in rs if r["impressions"] >= 10]
            if len(rs) < 2:
                continue
            rs.sort(key=lambda r: -r["impressions"])
            a = rs[0]
            for b in rs[1:4]:
                if b["impressions"] < 0.2 * a["impressions"]:
                    continue
                if abs(a["position"] - b["position"]) > 20:
                    continue
                ta = (by_url.get(a["page"]) or {}).get("title") or unquote(a["page"])
                tb = (by_url.get(b["page"]) or {}).get("title") or unquote(b["page"])
                sim = fuzz.token_set_ratio(ta, tb) / 100
                if sim < 0.4:
                    continue
                conf = 0.3 + 0.4 * sim + 0.3 * (1 - min(abs(a["position"] - b["position"]), 20) / 20)
                _opp(conn, sid, "cannibalization_candidate", a["page"], conf, {"title_similarity": round(sim, 2), "position_gap": round(abs(a["position"] - b["position"]), 1),
                                                                                "impressions_a": a["impressions"], "impressions_b": b["impressions"]},
                     f"query '{q}' shows both pages (pos {a['position']:.1f} vs {b['position']:.1f}); title similarity {sim:.0%}", conf,
                     {"query": q, "page_a": a["page"], "page_b": b["page"], "clicks_a": a["clicks"], "clicks_b": b["clicks"],
                      "impressions_a": a["impressions"], "impressions_b": b["impressions"], "position_a": round(a["position"], 1),
                      "position_b": round(b["position"], 1), "similarity": round(sim, 2), "label": "Cannibalization Candidate (not confirmed)"},
                     related_url=b["page"], query=q, run_id=run_id); counts["opportunities"] += 1

    # --- internal linking opportunities (entity/topic based; works without GSC) ------------
    ments = defaultdict(dict)   # url -> {(type,slug): score}
    for m in rows(conn, "SELECT url, entity_type, entity_slug, score, in_title, in_h1 FROM entity_mentions WHERE site_id=?", (sid,)):
        ments[m["url"]][(m["entity_type"], m["entity_slug"])] = m
    gsc_page = {r["page"]: r for r in rows(conn, "SELECT page, SUM(clicks) clicks, SUM(impressions) impressions FROM gsc_query_page WHERE site_id=? GROUP BY page", (sid,))}
    ent_names = {(e["entity_type"], e["slug"]): e["name"] for e in rows(conn, "SELECT entity_type, slug, name FROM entities WHERE site_id=?", (sid,))}
    indexable = [p for p in pages if p["indexable"] == 1 and p["status_code"] == 200]
    for tgt in indexable:
        tu = tgt["url"]
        if tu == home:
            continue
        # target's primary topics: entities in title/h1 (BRAND/MODEL/LOCATION only)
        topics = {k: m for k, m in ments[tu].items() if k[0] in ("BRAND", "MODEL") and (m["in_title"] or m["in_h1"])}
        if not topics:
            continue
        importance = 0.5 * min(len(inbound_all[tu]), 10) / 10 + 0.5 * min((gsc_page.get(tu) or {}).get("impressions", 0) or 0, 1000) / 1000
        for src in indexable:
            su = src["url"]
            if su == tu or tu in outbound[su] or "/category/" in su or "/page/" in su:
                continue
            shared = [k for k in topics if k in ments[su] and ments[su][k]["score"] >= 1.0]
            if not shared:
                continue
            rel = min(1.0, sum(ments[su][k]["score"] for k in shared) / 8)
            # source is more relevant if the shared topic is NOT its own primary topic (avoid two brand hubs cross-linking randomly)? keep simple: relevance by mention score
            breakdown = {"semantic_relevance": round(rel, 2), "link_absent": 1, "target_importance": round(importance, 2),
                         "target_inbound_deficit": round(1 - min(len(inbound_all[tu]), 5) / 5, 2), "shared_entities": [ent_names.get(k, k[1]) for k in shared]}
            score = 0.45 * rel + 0.25 * breakdown["target_inbound_deficit"] + 0.2 * (1 - importance) + 0.1
            anchor = (tgt["title"] or "").split(" - ")[0]
            _opp(conn, sid, "internal_link", su, score, breakdown,
                 f"source mentions {', '.join(breakdown['shared_entities'])} but does not link to the target page about it", min(0.9, 0.4 + rel / 2),
                 {"source": su, "target": tu, "potential_anchor": anchor, "shared_entities": breakdown["shared_entities"]},
                 related_url=tu, run_id=run_id); counts["opportunities"] += 1

    # --- GA4 behaviour opportunities (existing ga4_daily; skipped silently when GA4 was never synced) ---------------
    try:
        ga4 = rows(conn, "SELECT page_path, SUM(sessions) s, SUM(conversions) c, "
                         "CASE WHEN SUM(sessions)>0 THEN SUM(engagement_rate*sessions)/SUM(sessions) END e "
                         "FROM ga4_daily WHERE site_id=? AND source='page' GROUP BY page_path", (sid,))
    except sqlite3.OperationalError:
        ga4 = []
    if ga4:
        from urllib.parse import unquote as _uq, urlsplit as _us
        by_path = {}
        for p_ in pages:
            by_path[_uq(_us(p_["url"]).path or "/").rstrip("/") or "/"] = p_["url"]
        for r_ in rows(conn, "SELECT url FROM posts WHERE site_id=?", (sid,)):     # uncrawled WP content too
            by_path.setdefault(_uq(_us(r_["url"]).path or "/").rstrip("/") or "/", r_["url"])
        mid = conn.execute("SELECT date(MAX(date), '-14 day') FROM ga4_daily WHERE site_id=? AND source='page'", (sid,)).fetchone()[0]
        recent = {r["page_path"]: r for r in rows(conn, "SELECT page_path, SUM(sessions) s FROM ga4_daily WHERE site_id=? AND source='page' AND date>? GROUP BY page_path", (sid, mid or ""))}
        prior = {r["page_path"]: r for r in rows(conn, "SELECT page_path, SUM(sessions) s FROM ga4_daily WHERE site_id=? AND source='page' AND date<=? GROUP BY page_path", (sid, mid or ""))}
        for g in ga4:
            path = _uq(g["page_path"] or "/").rstrip("/") or "/"
            url = by_path.get(path)
            if not url or path == "/":
                continue
            sess, conv, eng = int(g["s"] or 0), float(g["c"] or 0), g["e"]
            # 1) high traffic, no/low conversion
            if sess >= 100 and conv <= max(1.0, sess * 0.002):
                score = min(1.0, 0.4 + sess / 2000)
                _opp(conn, sid, "ga4_traffic_no_conversion", url, score, {"sessions": sess, "conversions": conv},
                     f"این صفحه ورودی زیادی دارد ({sess} session) ولی تبدیل پایین است ({conv:.0f}) — CTA و مسیر تبدیل را بازبینی کنید",
                     0.7, {"sessions": sess, "conversions": conv, "engagement_rate": eng}, run_id=run_id); counts["opportunities"] += 1
            # 2) meaningful traffic, weak engagement
            if sess >= 50 and eng is not None and eng < 0.35:
                score = min(1.0, 0.35 + (0.35 - eng) + sess / 4000)
                _opp(conn, sid, "ga4_low_engagement", url, score, {"sessions": sess, "engagement_rate": round(eng, 3)},
                     f"نرخ تعامل فقط {eng*100:.0f}٪ با {sess} session — صفحه نیاز به بهبود عنوان، محتوا یا UX دارد",
                     0.65, {"sessions": sess, "engagement_rate": round(eng, 3)}, run_id=run_id); counts["opportunities"] += 1
            # 3) traffic drop: last 14 days vs the 14 days before
            pr, rc = int((prior.get(g["page_path"]) or {"s": 0})["s"] or 0), int((recent.get(g["page_path"]) or {"s": 0})["s"] or 0)
            if pr >= 50 and rc < pr * 0.6:
                drop = 1 - rc / pr
                _opp(conn, sid, "ga4_traffic_drop", url, min(1.0, 0.4 + drop / 2), {"prev_sessions": pr, "recent_sessions": rc, "drop": round(drop, 2)},
                     f"کاهش ترافیک GA4 نسبت به دوره قبل: {pr} → {rc} session ({drop*100:.0f}٪ افت) — محتوا و رتبه‌ها را بررسی کنید",
                     0.7, {"prev_sessions": pr, "recent_sessions": rc}, run_id=run_id); counts["opportunities"] += 1

    analysis_notes = {**counts, "link_graph_complete": link_graph_complete,
                      "sitemap_urls": sitemap_urls, "fresh_sitemap_pages": fresh_sitemap_pages}
    conn.execute("UPDATE sync_runs SET finished_at=?, status='completed', rows_written=?, notes=? WHERE run_id=?",
                 (utcnow(), counts["problems"] + counts["opportunities"], j(analysis_notes), run_id))
    conn.commit()
    summary = {"run_id": run_id, **counts,
               "by_problem": {r["problem_type"]: r["n"] for r in rows(conn, "SELECT problem_type, count(*) n FROM seo_problems WHERE site_id=? GROUP BY 1", (sid,))},
               "by_opportunity": {r["opp_type"]: r["n"] for r in rows(conn, "SELECT opp_type, count(*) n FROM seo_opportunities WHERE site_id=? GROUP BY 1", (sid,))}}
    log.info(f"analysis: {json.dumps(summary, ensure_ascii=False)}")
    return summary
