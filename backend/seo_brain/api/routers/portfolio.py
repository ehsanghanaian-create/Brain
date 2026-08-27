"""Portfolio-level read model for the main dashboard.

The overview page needs one consistent snapshot across every site.  Keeping the
aggregation here avoids an N+1 fan-out from Next.js and gives other clients the
same operational view.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import Engine, text

from ...db.repositories.base import utcnow
from ..deps import engine

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _group_counts(cx, table: str, *, extra: str = "") -> dict[str, int]:
    rows = cx.execute(text(f"SELECT site_id, COUNT(*) AS n FROM {table} {extra} GROUP BY site_id")).all()
    return {str(site_id): int(count) for site_id, count in rows}


def _pipeline_state(notes: str | None, fallback_status: str) -> dict[str, Any]:
    if notes:
        try:
            parsed = json.loads(notes)
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, ValueError):
            pass
    return {"status": fallback_status, "progress": 0, "errors": []}


def _site_operational_state(*, sync_status: str, connections: dict[str, str], has_content: bool,
                            has_crawl: bool, has_graph: bool) -> tuple[str, str, str, list[dict[str, str]]]:
    """Return an explainable portfolio state instead of a count-only guess.

    WordPress is the source of truth for the content inventory, so an explicit
    WordPress error is blocking even when an older snapshot is still present.
    GSC/GA4 issues stay visible as warnings but do not make the local content
    graph unusable.
    """
    issues: list[dict[str, str]] = []
    wp_status = connections.get("wordpress")
    gsc_status = connections.get("gsc")
    ga4_status = connections.get("ga4")
    if wp_status == "error":
        issues.append({"kind": "wordpress", "severity": "blocking", "message": "اتصال وردپرس خطا دارد"})
    if gsc_status in {"error", "not_authorized", "not_found"}:
        issues.append({"kind": "gsc", "severity": "warning", "message": "داده Search Console کامل در دسترس نیست"})
    if ga4_status in {"error", "not_authorized", "not_found"}:
        issues.append({"kind": "ga4", "severity": "warning", "message": "داده GA4 کامل در دسترس نیست"})

    if sync_status in {"queued", "running"}:
        return "running", "پردازش داده‌های سایت در حال اجراست", "صبر تا پایان پردازش", issues
    if sync_status in {"failed", "completed_with_errors"}:
        return "attention", "آخرین اجرای پردازش ناموفق یا ناقص بوده است", "بررسی خطای آخرین اجرا", issues
    if wp_status == "error":
        return "attention", "اتصال وردپرس برقرار نیست؛ داده موجود ممکن است قدیمی باشد", "اصلاح اتصال وردپرس", issues
    if has_content and has_graph:
        reason = "محتوا و گراف دانش قابل استفاده‌اند"
        if issues:
            reason += "؛ یکپارچه‌سازی تحلیلی نیازمند بررسی است"
        return "ready", reason, "بررسی فرصت‌های سئو", issues
    if has_content and not has_graph:
        return "partial", "محتوا دریافت شده اما گراف دانش ساخته نشده است", "ساخت گراف دانش", issues
    if has_graph and not has_content:
        return "partial", "گراف داده دارد اما موجودی محتوای وردپرس خالی است", "همگام‌سازی محتوای وردپرس", issues
    if has_crawl:
        return "partial", "خزش انجام شده اما محتوا و گراف کامل نیست", "تکمیل همگام‌سازی و ساخت گراف", issues
    return "not_started", "هنوز داده قابل استفاده‌ای ثبت نشده است", "شروع راه‌اندازی سایت", issues


@router.get("/overview")
def overview(eng: Engine = Depends(engine)) -> dict[str, Any]:
    with eng.connect() as cx:
        site_rows = [dict(row._mapping) for row in cx.execute(text("SELECT * FROM sites ORDER BY name, site_id")).all()]
        node_rows = cx.execute(text("SELECT site_id, node_type, COUNT(*) AS n FROM graph_nodes GROUP BY site_id, node_type")).all()
        nodes: dict[str, int] = defaultdict(int)
        by_type: dict[str, int] = defaultdict(int)
        for site_id, node_type, count in node_rows:
            nodes[str(site_id)] += int(count)
            by_type[str(node_type)] += int(count)

        edges = _group_counts(cx, "graph_edges")
        content = _group_counts(cx, "posts")
        crawled = _group_counts(cx, "pages", extra="WHERE crawl_status = 'ok'")
        keywords = _group_counts(cx, "keywords")
        planned = _group_counts(cx, "content_items")
        new_links = _group_counts(cx, "link_suggestions", extra="WHERE status = 'new'")
        high_links = _group_counts(cx, "link_suggestions", extra="WHERE status = 'new' AND confidence = 'high'")

        connection_rows = cx.execute(text(
            "SELECT site_id, kind, status FROM site_connections ORDER BY tested_at DESC"
        )).all()
        connections: dict[str, dict[str, str]] = defaultdict(dict)
        for site_id, kind, status in connection_rows:
            connections[str(site_id)].setdefault(str(kind), str(status))

        sync_rows = cx.execute(text(
            "SELECT site_id, run_id, status, started_at, finished_at, notes "
            "FROM sync_runs WHERE source = 'wordpress_pipeline' ORDER BY started_at DESC, id DESC"
        )).all()
        latest_sync: dict[str, dict[str, Any]] = {}
        activity: list[dict[str, Any]] = []
        names = {str(row["site_id"]): str(row["name"]) for row in site_rows}
        for site_id, run_id, status, started_at, finished_at, notes in sync_rows:
            sid = str(site_id)
            state = _pipeline_state(notes, str(status))
            item = {
                "site_id": sid,
                "site_name": names.get(sid, sid),
                "run_id": run_id,
                "status": state.get("status") or status,
                "progress": float(state.get("progress") or 0),
                "step": state.get("step"),
                "step_fa": state.get("step_fa"),
                "started_at": state.get("started_at") or started_at,
                "finished_at": state.get("finished_at") or finished_at,
                "errors": list(state.get("errors") or []),
            }
            if sid not in latest_sync:
                latest_sync[sid] = item
            if len(activity) < 8:
                activity.append(item)

    sites: list[dict[str, Any]] = []
    state_counts = {"ready": 0, "running": 0, "attention": 0, "partial": 0, "not_started": 0}
    for raw in site_rows:
        sid = str(raw["site_id"])
        sync = latest_sync.get(sid)
        sync_status = str((sync or {}).get("status") or "never")
        has_content = content.get(sid, 0) > 0
        has_graph = nodes.get(sid, 0) > 0
        site_connections = connections.get(sid, {})
        state, state_reason, next_action, issues = _site_operational_state(
            sync_status=sync_status,
            connections=site_connections,
            has_content=has_content,
            has_crawl=crawled.get(sid, 0) > 0,
            has_graph=has_graph,
        )
        state_counts[state] += 1

        setup_steps = [bool(raw.get("wp_url")), has_content, crawled.get(sid, 0) > 0, has_graph]
        sites.append({
            "site_id": sid,
            "name": raw["name"],
            "canonical_url": raw["canonical_url"],
            "wp_url": raw.get("wp_url"),
            "mode": raw.get("mode") or "manual",
            "state": state,
            "state_reason": state_reason,
            "next_action": next_action,
            "issues": issues,
            "setup_progress": sum(setup_steps) * 25,
            "setup_steps": {
                "wordpress_configured": bool(raw.get("wp_url")),
                "content_synced": has_content,
                "crawl_ready": crawled.get(sid, 0) > 0,
                "graph_ready": has_graph,
            },
            "counts": {
                "content": content.get(sid, 0),
                "crawled": crawled.get(sid, 0),
                "graph_nodes": nodes.get(sid, 0),
                "graph_edges": edges.get(sid, 0),
                "keywords": keywords.get(sid, 0),
                "planned_content": planned.get(sid, 0),
                "new_link_suggestions": new_links.get(sid, 0),
                "high_link_suggestions": high_links.get(sid, 0),
            },
            "connections": site_connections,
            "latest_sync": sync,
        })

    return {
        "generated_at": utcnow(),
        "totals": {
            "sites": len(sites),
            "ready_sites": state_counts["ready"],
            "needs_attention": state_counts["attention"] + state_counts["partial"] + state_counts["not_started"],
            "content": sum(content.values()),
            "crawled": sum(crawled.values()),
            "graph_nodes": sum(nodes.values()),
            "graph_edges": sum(edges.values()),
            "keywords": sum(keywords.values()),
            "planned_content": sum(planned.values()),
            "new_link_suggestions": sum(new_links.values()),
            "high_link_suggestions": sum(high_links.values()),
        },
        "state_counts": state_counts,
        "by_node_type": dict(sorted(by_type.items(), key=lambda item: (-item[1], item[0]))),
        "sites": sites,
        "recent_activity": activity,
    }
