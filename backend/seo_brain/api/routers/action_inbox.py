"""One read-only triage inbox for existing, site-scoped SEO evidence.

The sources retain their own scoring and decision workflows.  This projection
only joins open issue cases and new keyword/link opportunities; it does not
turn a heuristic into a task or imply that unlike scores are comparable.
"""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine, text

from ...db.repositories.base import utcnow
from ..deps import engine
from ..errors import ApiError

router = APIRouter(prefix="/portfolio/action-inbox", tags=["portfolio"])

_SOURCES = """
SELECT 'issue' AS kind, i.id AS source_id, i.site_id, s.name AS site_name,
       i.problem_type AS subtype, i.problem_type AS title, '' AS summary,
       i.url AS url, i.related_url AS related_url, i.severity AS priority,
       NULL AS score, i.detail AS evidence, i.last_run_id AS run_id,
       i.last_seen AS observed_at,
       CASE i.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END AS triage_rank
FROM issue_cases i JOIN sites s ON s.site_id=i.site_id
WHERE i.status='open' AND (:site_id IS NULL OR i.site_id=:site_id)
UNION ALL
SELECT 'keyword', o.id, o.site_id, s.name, o.kind, k.keyword, COALESCE(o.reason,''),
       COALESCE(o.target_url,''), '',
       CASE WHEN o.score>=0.8 THEN 'high' WHEN o.score>=0.6 THEN 'medium' ELSE 'low' END,
       o.score, o.evidence, o.run_id, o.updated_at,
       CASE WHEN o.score>=0.8 THEN 0 WHEN o.score>=0.6 THEN 1 ELSE 2 END
FROM keyword_opportunities o
JOIN keywords k ON k.id=o.keyword_id AND k.site_id=o.site_id
JOIN sites s ON s.site_id=o.site_id
WHERE o.status='new' AND (:site_id IS NULL OR o.site_id=:site_id)
UNION ALL
SELECT 'link', l.id, l.site_id, s.name, l.kind,
       COALESCE(NULLIF(l.source_title,''),l.source_url,'صفحهٔ مبدأ') || ' ← ' ||
       COALESCE(NULLIF(l.target_title,''),l.target_url,'صفحهٔ مقصد'),
       COALESCE(l.reason_fa,''), COALESCE(l.target_url,''), COALESCE(l.source_url,''),
       CASE WHEN l.confidence='high' THEN 'high' WHEN l.confidence='recommended' THEN 'medium' ELSE 'low' END,
       l.score, l.evidence, l.run_id, l.updated_at,
       CASE WHEN l.confidence='high' THEN 0 WHEN l.confidence='recommended' THEN 1 ELSE 2 END
FROM link_suggestions l JOIN sites s ON s.site_id=l.site_id
WHERE l.status='new' AND l.scope='internal' AND (:site_id IS NULL OR l.site_id=:site_id)
"""


def _evidence(value: str | None) -> dict:
    try:
        parsed = json.loads(value) if value else {}
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


@router.get("")
def action_inbox(
    site_id: str | None = None,
    kind: Literal["all", "issue", "keyword", "link"] = "all",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    eng: Engine = Depends(engine),
) -> dict:
    params = {"site_id": site_id, "kind": kind, "limit": limit, "offset": offset}
    source_sql = f"WITH evidence AS ({_SOURCES}) "
    with eng.connect() as cx:
        if site_id and not cx.execute(text("SELECT 1 FROM sites WHERE site_id=:site_id"), params).first():
            raise ApiError(404, "سایت پیدا نشد", code="not_found")
        count_rows = cx.execute(text(source_sql + "SELECT kind,COUNT(*) FROM evidence GROUP BY kind"), params).all()
        counts = {"issue": 0, "keyword": 0, "link": 0}
        counts.update({str(source): int(count) for source, count in count_rows})
        rows = cx.execute(text(source_sql + """
            SELECT kind,source_id,site_id,site_name,subtype,title,summary,url,related_url,
                   priority,score,evidence,run_id,observed_at
            FROM evidence WHERE (:kind='all' OR kind=:kind)
            ORDER BY triage_rank ASC, observed_at DESC, kind, source_id DESC
            LIMIT :limit OFFSET :offset
        """), params).mappings()
        items = [{**dict(row), "evidence": _evidence(row["evidence"])} for row in rows]
    return {
        "generated_at": utcnow(), "site_id": site_id, "kind": kind,
        "counts": counts, "total": sum(counts.values()) if kind == "all" else counts[kind],
        "limit": limit, "offset": offset, "items": items,
        "scope": "open_cases_and_new_keyword_or_internal_link_opportunities",
        "ranking_note": "ترتیب مرور در هر منبع پیشنهادی است؛ امتیاز منابع مختلف معادل یکدیگر نیست.",
    }
