"""Node details for the command-center side panel: the SEO facts that matter for each node type.

Combines the GraphStore (node + neighbours) with the v0.1 analytics (`graph.queries`, sqlite) so the panel
shows real crawl/GSC/problem data. Everything is read-only. Suggested actions are rule-based and explainable.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from ..db.repositories.graph import GraphRepository
from . import queries as Q

PROBLEM_ACTIONS: dict[str, dict[str, str]] = {
    "orphan": {"title_fa": "صفحه یتیم", "action_fa": "حداقل ۲ لینک داخلی از صفحات مرتبط با انکرتکست معنادار به این صفحه بدهید"},
    "low_inbound_links": {"title_fa": "لینک ورودی کم", "action_fa": "از صفحات هم‌موضوع (دسته/خدمت) لینک داخلی اضافه کنید"},
    "no_body_inbound_links": {"title_fa": "فقط لینک ناوبری", "action_fa": "در متن مقالات مرتبط لینک متنی به این صفحه بگذارید"},
    "missing_h1": {"title_fa": "بدون H1", "action_fa": "یک H1 یکتا شامل کلمه کلیدی اصلی اضافه کنید"},
    "multiple_h1": {"title_fa": "چند H1", "action_fa": "فقط یک H1 نگه دارید؛ بقیه را به H2 تبدیل کنید"},
    "duplicate_title": {"title_fa": "عنوان تکراری", "action_fa": "عنوان‌ها را یکتا و مطابق اینتنت هر صفحه بنویسید"},
    "duplicate_h1": {"title_fa": "H1 تکراری", "action_fa": "H1 هر صفحه را متمایز کنید (مدل/خدمت/مکان)"},
    "missing_meta_description": {"title_fa": "بدون توضیحات متا", "action_fa": "توضیحات متا ۱۲۰–۱۶۰ نویسه با CTA بنویسید"},
    "images_missing_alt": {"title_fa": "تصویر بدون alt", "action_fa": "برای تصاویر alt توصیفی شامل مدل/خدمت اضافه کنید"},
    "missing_canonical": {"title_fa": "بدون canonical", "action_fa": "تگ canonical به آدرس اصلی اضافه کنید"},
    "important_non_indexable": {"title_fa": "صفحه مهم غیرقابل ایندکس", "action_fa": "robots/noindex و canonical را بررسی و اصلاح کنید"},
    "thin_content": {"title_fa": "محتوای کم", "action_fa": "محتوا را با پاسخ به سؤالات کاربر و FAQ گسترش دهید"},
    "redirect_in_sitemap": {"title_fa": "ریدایرکت در سایت‌مپ", "action_fa": "آدرس نهایی را در سایت‌مپ قرار دهید"},
}
OPP_ACTIONS: dict[str, str] = {
    "internal_link": "لینک داخلی از صفحه مبدأ به مقصد با انکرتکست پیشنهادی اضافه کنید",
    "striking_distance": "صفحه را برای کوئری‌های جایگاه ۴–۱۵ تقویت کنید (عنوان، H2، لینک داخلی)",
    "cannibalization_candidate": "یکی از دو صفحه را هدف اصلی کوئری کنید و دیگری را به آن لینک/ادغام کنید",
    "ctr_opportunity": "عنوان و توضیحات متا را برای CTR بهتر بازنویسی کنید",
}


def _neighbors(repo: GraphRepository, site_id: str, node_id: str, rel: str | None = None, direction: str = "both", limit: int = 30) -> list[dict]:
    edges = repo.edges_of(site_id, [node_id], [rel] if rel else None, direction)
    other_ids = [e.target if e.source == node_id else e.source for e in edges]
    nodes = {n.id: n for n in repo.nodes_by_ids(site_id, set(other_ids))}
    out = []
    for e in edges[:limit]:
        oid = e.target if e.source == node_id else e.source
        n = nodes.get(oid)
        if n:
            out.append({"id": n.id, "type": n.type, "label": n.label, "url": n.metadata.get("url"), "relation": e.relation_type,
                        "direction": "out" if e.source == node_id else "in", "props": e.metadata.get("props", {})})
    return out


def node_details(repo: GraphRepository, conn, site_id: str, node_id: str) -> dict[str, Any] | None:
    n = repo.get_node(site_id, node_id)
    if not n:
        return None
    base: dict[str, Any] = {"id": n.id, "type": n.type, "label": n.label, "url": n.metadata.get("url"),
                            "pagerank": n.metadata.get("pagerank"), "community": n.metadata.get("community"), "props": n.metadata.get("props", {})}
    t = n.type
    if t in ("PAGE", "POST", "CATEGORY"):
        seo = Q.get_page_seo_data(conn, site_id, n.metadata.get("url") or n.id) or {}
        crawl = seo.get("crawl") or {}
        gsc = seo.get("gsc") if isinstance(seo.get("gsc"), dict) and "status" not in (seo.get("gsc") or {}) else None
        base["page"] = {
            "title": crawl.get("title"), "h1": crawl.get("h1"), "word_count": crawl.get("word_count"),
            "indexable": crawl.get("indexable"), "indexability_reason": crawl.get("indexability_reason"),
            "canonical": crawl.get("canonical"), "status_code": crawl.get("status_code"), "last_crawled": crawl.get("last_crawled"),
            "content_status": _content_status(crawl, seo),
            "links": {"inbound": (seo.get("internal_links_in") or {}).get("count", 0),
                      "inbound_body": (seo.get("internal_links_in") or {}).get("body_count", 0),
                      "outbound": len(seo.get("internal_links_out") or []),
                      "external": len(seo.get("external_links_out") or []),
                      "inbound_sources": ((seo.get("internal_links_in") or {}).get("sources") or [])[:15],
                      "outbound_targets": (seo.get("internal_links_out") or [])[:15]},
            "gsc": gsc, "top_queries": (seo.get("top_queries") or [])[:10],
            "problems": [{**p, **_action_for_problem(p.get("type"))} for p in seo.get("problems") or []],
            "opportunities": [{**o, "action_fa": OPP_ACTIONS.get(o.get("type"), "")} for o in seo.get("opportunities") or []],
            "entities": seo.get("entities") or [], "wordpress": seo.get("wordpress"),
        }
        base["related"] = {"queries": _neighbors(repo, site_id, node_id, "RANKS_FOR"), "entities": _neighbors(repo, site_id, node_id, "ABOUT")}
        try:
            row = conn.execute("SELECT health_score, health_breakdown, flags, inbound_body, inbound_nav_only, outbound_body, stage FROM link_page_stats WHERE site_id=? AND node_id=?", (site_id, node_id)).fetchone()
            if row:
                import json as _json
                base["link_health"] = {"score": row["health_score"], "breakdown": _json.loads(row["health_breakdown"] or "{}"), "flags": _json.loads(row["flags"] or "[]"), "inbound_body": row["inbound_body"],
                                       "inbound_nav_only": row["inbound_nav_only"], "outbound_body": row["outbound_body"], "stage": row["stage"]}
        except Exception:  # noqa: BLE001
            pass
        base["link_suggestions"] = {"to": _neighbors(repo, site_id, node_id, "LINK_OPPORTUNITY", "in"), "from": _neighbors(repo, site_id, node_id, "LINK_OPPORTUNITY", "out"),
                                    "supports": _neighbors(repo, site_id, node_id, "SUPPORTS")}
    elif t in ("QUERY", "KEYWORD"):
        label = n.label
        rows = []
        try:
            data = Q.get_gsc_query_data(conn, site_id, query=label, limit=20)
            rows = data.get("rows") or [] if isinstance(data, dict) else []
        except Exception:  # noqa: BLE001
            rows = []
        props = n.metadata.get("props", {})
        base["keyword"] = {
            "position": props.get("position"), "ctr": props.get("ctr"), "impressions": props.get("impressions"), "clicks": props.get("clicks"),
            "pages_count": props.get("pages_count"), "importance_reason": props.get("importance_reason"), "intent": props.get("intent"),
            "per_page": [{"page": unquote(r.get("page") or ""), "clicks": r.get("clicks"), "impressions": r.get("impressions"),
                          "ctr": r.get("ctr"), "position": r.get("position")} for r in rows],
            "related_pages": _neighbors(repo, site_id, node_id, "RANKS_FOR") + _neighbors(repo, site_id, node_id, "KEYWORD_TARGETS"),
        }
    elif t == "SEO_PROBLEM":
        ptype = n.id.split(":", 1)[1] if ":" in n.id else n.label
        items = Q.get_seo_problems(conn, site_id, problem_type=ptype, limit=100).get("items", [])
        base["problem"] = {"issue": ptype, "severity": n.metadata.get("props", {}).get("severity") or (items[0]["severity"] if items else None),
                           "count": len(items), **_action_for_problem(ptype),
                           "affected_pages": [{"url": i["url"], "related_url": i.get("related_url"), "detail": i.get("detail")} for i in items[:50]]}
    elif t == "SEO_OPPORTUNITY":
        otype = n.id.split(":", 1)[1] if ":" in n.id else n.label
        items = Q.get_seo_opportunities(conn, site_id, opp_type=otype, limit=50).get("items", [])
        base["opportunity"] = {"type": otype, "count": len(items), "action_fa": OPP_ACTIONS.get(otype, ""),
                               "items": [{"url": i["url"], "related_url": i.get("related_url"), "query": i.get("query"), "score": i.get("score"),
                                          "reason": i.get("reason"), "confidence": i.get("confidence")} for i in items[:30]]}
    elif t == "CONTENT_PLAN":
        pid = int(n.id.split(":", 1)[1]) if n.id.split(":", 1)[1].isdigit() else None
        row = conn.execute("SELECT * FROM content_plans WHERE site_id=? AND id=?", (site_id, pid)).fetchone() if pid else None
        if row:
            import json as _json
            r = dict(row)
            for f in ("secondary_keywords", "heading_structure", "existing_pages", "link_targets", "cannibalization", "recommendation", "publishing"):
                r[f] = _json.loads(r.get(f) or ("{}" if f in ("recommendation", "publishing") else "[]"))
            cat = conn.execute("SELECT id, name, source FROM content_categories WHERE id=?", (r.get("category_id"),)).fetchone() if r.get("category_id") else None
            kws = conn.execute("SELECT k.id, k.keyword, pk.role, k.volume, k.intent FROM content_plan_keywords pk JOIN keywords k ON k.id=pk.keyword_id WHERE pk.content_plan_id=?", (pid,)).fetchall()
            base["plan"] = {**{k: r.get(k) for k in ("id", "title", "url", "status", "intent", "serp_intent", "page_type", "funnel_stage", "priority", "priority_score", "ai_priority", "business_value", "publish_date", "primary_keyword",
                                                     "content_gap", "cannibalization_risk", "ranking_url", "ranking_position", "traffic_opportunity", "content_item_id", "content_score", "graph_connections", "category_reason")},
                            "category": dict(cat) if cat else None, "keywords": [dict(k) for k in kws], "secondary_keywords": r["secondary_keywords"], "heading_structure": r["heading_structure"],
                            "existing_pages": r["existing_pages"], "link_targets": r["link_targets"], "cannibalization": r["cannibalization"], "recommendation": r["recommendation"]}
        base["related"] = {"keywords": _neighbors(repo, site_id, node_id, "TARGETS"), "category": _neighbors(repo, site_id, node_id, "BELONGS_TO"), "content": _neighbors(repo, site_id, node_id, "PLANNED_AS"),
                           "supports": _neighbors(repo, site_id, node_id, "SUPPORTS"), "links": _neighbors(repo, site_id, node_id, "LINK_OPPORTUNITY"), "intent": _neighbors(repo, site_id, node_id, "HAS_INTENT"), "stage": _neighbors(repo, site_id, node_id, "IN_STAGE")}
    elif t == "CONTENT_CLUSTER":
        base["cluster"] = {"plans": _neighbors(repo, site_id, node_id, "CONTAINS", "out"), "category": _neighbors(repo, site_id, node_id, "BELONGS_TO", "out")}
    elif t in ("SEARCH_INTENT", "FUNNEL_STAGE"):
        base["plans"] = _neighbors(repo, site_id, node_id, "HAS_INTENT" if t == "SEARCH_INTENT" else "IN_STAGE", "in")
    if t == "CATEGORY":
        try:
            import json as _json
            props = n.metadata.get("props", {})
            crow = conn.execute("SELECT * FROM content_categories WHERE site_id=? AND (wordpress_category_id=? OR (intelligence LIKE ?))", (site_id, props.get("wp_id"), '%"graph_node_id": "' + node_id + '"%')).fetchone()
            if crow:
                cr = dict(crow); intel = _json.loads(cr.get("intelligence") or "{}")
                base["planner_category"] = {"id": cr["id"], "source": cr["source"], "post_count": cr["post_count"], "page_count": cr["page_count"], "keyword_count": cr["keyword_count"], "plan_count": cr["plan_count"],
                                            "coverage_score": cr["coverage_score"], "gaps": intel.get("gaps", [])[:10], "top_keywords": intel.get("top_keywords", [])[:10], "intents": intel.get("intents", {})}
                base["plans"] = _neighbors(repo, site_id, node_id, "CONTAINS", "out")
        except Exception:  # noqa: BLE001
            pass
    if t in ("BRAND", "MODEL", "SERVICE", "LOCATION"):
        base["entity"] = {"kind": t, "aliases": n.metadata.get("props", {}).get("aliases", []), "evidence": n.metadata.get("props", {}).get("evidence"),
                          "pages": _neighbors(repo, site_id, node_id, "ABOUT") + _neighbors(repo, site_id, node_id, "OFFERS"),
                          "children": _neighbors(repo, site_id, node_id, "BELONGS_TO", "in")}
    elif t == "SCHEMA":
        base["schema"] = {"type": n.label, "pages": _neighbors(repo, site_id, node_id, "HAS_SCHEMA", "in", limit=100)}
    elif t == "SITE":
        base["site"] = Q.get_site_summary(conn, site_id)
    elif t == "CONTENT":
        cid = n.id.split(":", 1)[1] if ":" in n.id else None
        try:
            row = conn.execute("SELECT id, title, status, priority, publish_date, target_keyword, topic, url, brief_id FROM content_items WHERE site_id=? AND id=?", (site_id, cid)).fetchone()
        except Exception:  # noqa: BLE001
            row = None
        base["content"] = {"status": (row["status"] if row else n.metadata.get("props", {}).get("stage")), "priority": row["priority"] if row else None,
                           "publish_date": row["publish_date"] if row else None, "target_keyword": row["target_keyword"] if row else None, "topic": row["topic"] if row else None,
                           "url": row["url"] if row else None, "has_brief": bool(row["brief_id"]) if row else False, "content_id": row["id"] if row else None,
                           "neighbors": _neighbors(repo, site_id, node_id)}
    elif t == "TOPIC":
        base["topic"] = {"cluster_id": n.metadata.get("props", {}).get("cluster_id"), "keywords_count": n.metadata.get("props", {}).get("keywords_count"),
                         "keywords": _neighbors(repo, site_id, node_id, "CLUSTERED_IN", "in", limit=100)}
    else:
        base["neighbors"] = _neighbors(repo, site_id, node_id)
    base["degree"] = len(repo.edges_of(site_id, [node_id]))
    return base


def _content_status(crawl: dict, seo: dict) -> str:
    """Rule-based content status shown in the panel: ok | thin | non_indexable | needs_links | unknown."""
    if not crawl:
        return "unknown"
    if crawl.get("indexable") is False:
        return "non_indexable"
    wc = crawl.get("word_count") or 0
    if wc and wc < 300:
        return "thin"
    if (seo.get("internal_links_in") or {}).get("count", 0) == 0:
        return "needs_links"
    return "ok"


def _action_for_problem(ptype: str | None) -> dict[str, str]:
    a = PROBLEM_ACTIONS.get(ptype or "", {})
    return {"title_fa": a.get("title_fa", (ptype or "").replace("_", " ")), "action_fa": a.get("action_fa", "بررسی دستی")}
