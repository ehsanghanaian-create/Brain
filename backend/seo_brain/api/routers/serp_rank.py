"""Independent daily organic SERP rank tracking."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text

from ...analysis import serp_rank
from ...automation import get_job_queue
from ...automation.queue import Job
from ..deps import engine, require_site
from ..errors import ApiError

router = APIRouter(prefix="/sites/{site_id}/rank-tracking", tags=["rank-tracking"],
                   dependencies=[Depends(require_site)])


class SettingsUpdate(BaseModel):
    enabled: bool
    provider: Literal["serpkite", "serpapi", "dataforseo"]
    device: Literal["mobile", "desktop"] = "mobile"
    depth: Literal[10, 20, 30, 50] = 10
    max_keywords_per_run: int = Field(default=30, ge=1, le=5000)


@router.get("/overview")
def rank_overview(site_id: str, days: int = Query(30, ge=7, le=90), eng: Engine = Depends(engine)) -> dict:
    return serp_rank.overview(eng, site_id, days)


@router.put("/settings")
def update_settings(site_id: str, body: SettingsUpdate, eng: Engine = Depends(engine)) -> dict:
    return serp_rank.save_settings(eng, site_id, **body.model_dump())


@router.post("/run", status_code=202)
def start_run(site_id: str, eng: Engine = Depends(engine)) -> dict:
    result = serp_rank.create_run(eng, site_id)
    if result["status"] == "needs_provider":
        raise ApiError(409, "کلید ارائه‌دهندهٔ نتایج جست‌وجو روی سرور تنظیم نشده است", code="serp_provider_required")
    if result["status"] == "disabled":
        raise ApiError(409, "پایش رتبه برای این سایت خاموش است", code="rank_tracking_disabled")
    if result["status"] != "queued":
        return result
    try:
        job = get_job_queue().enqueue(Job(type="serp_rank_daily",
                                          payload={"site_id": site_id, "run_id": result["run_id"]},
                                          site_id=site_id))
    except Exception:
        with eng.begin() as cx:
            cx.execute(text("UPDATE serp_rank_runs SET status='blocked',error_code='queue_unavailable' WHERE id=:i"),
                       {"i": result["run_id"]})
        raise ApiError(503, "صف پایش رتبه در دسترس نیست", code="queue_unavailable") from None
    return {**result, "job_id": job.run_id}
