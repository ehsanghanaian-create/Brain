"""Plan → AI draft → (optional) WordPress publish — pure wiring over existing components.

The user only types a TITLE (+keywords/date/category) in the planner/calendar; generation runs through the SAME
engine as «آزمایش تولید محتوا» (ContentTestWorkspace) with the SAME parameters, all stored per-plan in
content_plans.metadata.ai: {provider, model, tone, word_count, audience, intent, content_type, prompt}.
`prompt` is the manual instruction box. The chosen planner category maps to the WordPress category at publish time.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text

log = logging.getLogger("planner.generation")


def _plan(engine: Engine, site_id: str, plan_id: int):
    with engine.connect() as cx:
        return cx.execute(text("SELECT id, title, seo_title, meta_description, primary_keyword, secondary_keywords, intent, "
                               "target_audience, category_id, content_item_id, status, metadata, notes FROM content_plans "
                               "WHERE site_id=:s AND id=:p"), {"s": site_id, "p": plan_id}).first()


def ai_settings(plan_row) -> dict[str, Any]:
    try:
        meta = json.loads(plan_row[11] or "{}")
    except ValueError:
        meta = {}
    return meta.get("ai") or {}


def generate_for_plan(engine: Engine, site_id: str, plan_id: int, then_publish: bool = False,
                      actor: str = "human", workspace=None, writer=None) -> dict[str, Any]:
    """Build the workspace spec from the plan (title + keywords + description + manual prompt + همان پارامترها)
    → generate → save as a versioned draft on the linked content item → optionally publish. Injectable for tests."""
    plan = _plan(engine, site_id, plan_id)
    if not plan:
        return {"status": "error", "message": "برنامه محتوا پیدا نشد"}
    ai = ai_settings(plan)
    try:
        secondary = json.loads(plan[5] or "[]")
    except ValueError:
        secondary = []
    category_name = None
    if plan[8]:
        with engine.connect() as cx:
            category_name = cx.execute(text("SELECT name FROM content_categories WHERE site_id=:s AND id=:c"),
                                       {"s": site_id, "c": plan[8]}).scalar()
    from ...brain.generation.workspace import ContentSpec, ContentTestWorkspace
    spec = ContentSpec(
        title=plan[1],
        keyword=(plan[4] or plan[1]).strip(),
        secondary_keywords=[s for s in secondary if isinstance(s, str) and s.strip()],
        intent=ai.get("intent") or plan[6] or "informational",
        content_type=ai.get("content_type") or "article",
        category=category_name,
        audience=ai.get("audience") or plan[7],
        tone=ai.get("tone") or "formal",
        word_count=int(ai.get("word_count") or 1200),
        instructions="\n".join(x for x in ((ai.get("prompt") or "").strip(), (plan[12] or "").strip()) if x) or None,
    )
    if workspace is None:
        from ...ai.gateway import Gateway
        workspace = ContentTestWorkspace(engine, Gateway(engine))
    ws = workspace
    out = ws.generate(site_id, spec, provider=ai.get("provider"), model=ai.get("model"))
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    if not out.get("ok"):
        _event(engine, site_id, plan_id, "generation_failed", actor, {"error": out.get("error")}, now)
        return {"status": "generation_failed", "message": out.get("error") or "تولید محتوا ناموفق بود", "run_id": out.get("run_id")}
    result = out["result"]
    # content item: reuse the linked one or create + link
    content_id = plan[9]
    if not content_id:
        from ...brain.content.service import ContentService
        item = ContentService(engine).create(site_id, plan[1], status="writing", target_keyword=plan[4],
                                             seo_title=plan[2], meta_description=plan[3])
        content_id = item.id
        with engine.begin() as cx:
            cx.execute(text("UPDATE content_plans SET content_item_id=:c, updated_at=:t WHERE site_id=:s AND id=:p"),
                       {"c": content_id, "t": now, "s": site_id, "p": plan_id})
    saved = ws.save_draft(site_id, content_id, result.get("markdown") or "", title=result.get("title") or plan[1],
                          meta_description=result.get("meta_description") or plan[3],
                          meta={**out.get("meta", {}), "plan_id": plan_id}, actor=f"ai:planner:{actor}")
    if plan[10] in ("planned", "researching", "brief_ready", "writing"):
        with engine.begin() as cx:
            cx.execute(text("UPDATE content_plans SET status='review', updated_at=:t WHERE site_id=:s AND id=:p"),
                       {"t": now, "s": site_id, "p": plan_id})
    _event(engine, site_id, plan_id, "draft_generated", actor,
           {"content_id": content_id, "draft": saved.get("draft_id") or saved.get("id"), "words": (out.get("seo") or {}).get("word_count"),
            "provider": (out.get("meta") or {}).get("provider"), "model": (out.get("meta") or {}).get("model"), "seo_score": ((out.get("seo") or {}).get("score") or {}).get("total")}, now)
    res: dict[str, Any] = {"status": "generated", "content_id": content_id, "run_id": out.get("run_id"),
                           "provider": (out.get("meta") or {}).get("provider"), "model": (out.get("meta") or {}).get("model"),
                           "word_count": (out.get("seo") or {}).get("word_count"),
                           "seo_score": ((out.get("seo") or {}).get("score") or {}).get("total"),
                           "placeholder": bool((out.get("meta") or {}).get("placeholder"))}
    if then_publish:
        from ...integrations.wordpress import WordPressWriter
        w = writer or WordPressWriter(engine)
        res["publish"] = w.publish_plan(site_id, plan_id, actor=actor)
    return res


def _event(engine: Engine, site_id: str, plan_id: int, event: str, actor: str, payload: dict, now: str) -> None:
    with engine.begin() as cx:
        cx.execute(text("INSERT INTO content_plan_events(site_id, content_plan_id, event, actor, payload, created_at) "
                        "VALUES(:s,:p,:e,:a,:pl,:t)"),
                   {"s": site_id, "p": plan_id, "e": event, "a": actor, "pl": json.dumps(payload, ensure_ascii=False), "t": now})


def due_autopilot_plans(engine: Engine, limit: int = 3) -> list[dict[str, Any]]:
    """Plans whose calendar date/time has arrived, on sites in «خودکار» mode, not yet published."""
    from datetime import timedelta, timezone
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Tehran")
    except Exception:  # noqa: BLE001 — Windows without tzdata: Iran is fixed UTC+03:30 (no DST since 2022)
        tz = timezone(timedelta(hours=3, minutes=30))
    now = datetime.now(tz)
    today, hhmm = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    with engine.connect() as cx:
        rows = cx.execute(text(
            "SELECT p.site_id, p.id FROM content_plans p JOIN sites s ON s.site_id=p.site_id "
            "WHERE s.mode='autopilot' AND s.wp_url IS NOT NULL AND s.wp_url != '' "
            "AND p.status != 'published' AND p.publish_date IS NOT NULL AND p.publish_date != '' "
            "AND (p.publish_date < :d OR (p.publish_date = :d AND (p.publish_time IS NULL OR p.publish_time <= :t))) "
            "AND (p.publishing IS NULL OR p.publishing NOT LIKE '%wp_post_id%') "
            "ORDER BY p.publish_date, p.publish_time LIMIT :n"), {"d": today, "t": hhmm, "n": limit}).all()
    return [{"site_id": r[0], "plan_id": r[1]} for r in rows]
