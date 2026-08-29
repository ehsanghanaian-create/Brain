"""Durable scheduled content generation and optional guarded WordPress delivery."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Engine, text

from .queue import Job
from ..db.repositories.base import loads, utcnow


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_time(value: str | None, timezone_name: str = "Asia/Tehran", default_now: bool = False) -> str | None:
    if not value:
        return utc_iso(datetime.now(timezone.utc)) if default_now else None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("تاریخ و ساعت معتبر نیست") from exc
    try:
        zone = ZoneInfo(timezone_name or "Asia/Tehran")
    except ZoneInfoNotFoundError:
        if (timezone_name or "Asia/Tehran") != "Asia/Tehran":
            raise ValueError("منطقه زمانی سایت معتبر نیست")
        zone = timezone(timedelta(hours=3, minutes=30), name="Asia/Tehran")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return utc_iso(parsed)


def _job(engine: Engine, jid: int) -> dict[str, Any] | None:
    with engine.connect() as cx:
        row = cx.execute(text("SELECT * FROM content_plan_generation_jobs WHERE id=:i"), {"i": jid}).mappings().first()
    if not row:
        return None
    value = dict(row)
    value["params"] = loads(value.get("params"), {})
    value["category_ids"] = loads(value.get("category_ids"), [])
    return value


def enqueue_due(engine: Engine, queue, limit: int = 3, now: datetime | None = None) -> list[dict[str, Any]]:
    """Atomically claim due DB rows and hand them to the process-wide persistent queue."""
    due_at = utc_iso(now or datetime.now(timezone.utc))
    with engine.connect() as cx:
        ids = [int(r[0]) for r in cx.execute(text(
            "SELECT id FROM content_plan_generation_jobs "
            "WHERE status IN ('prepared','retry') AND scheduled_at IS NOT NULL AND scheduled_at<=:n "
            "ORDER BY scheduled_at,id LIMIT :l"), {"n": due_at, "l": max(1, min(limit, 20))}).all()]
    queued: list[dict[str, Any]] = []
    for jid in ids:
        with engine.begin() as cx:
            claimed = cx.execute(text(
                "UPDATE content_plan_generation_jobs SET status='queued',updated_at=:n "
                "WHERE id=:i AND status IN ('prepared','retry') AND scheduled_at<=:n"), {"i": jid, "n": due_at}).rowcount
        if not claimed:
            continue
        job = _job(engine, jid)
        try:
            run = queue.enqueue(Job(type="content_automation", payload={"generation_job_id": jid}, site_id=job["site_id"] if job else None))
            with engine.begin() as cx:
                cx.execute(text("UPDATE content_plan_generation_jobs SET queue_run_id=:r,updated_at=:u WHERE id=:i"),
                           {"r": run.run_id, "u": utcnow(), "i": jid})
            queued.append({"id": jid, "run_id": run.run_id, "site_id": job["site_id"] if job else None})
        except Exception:
            with engine.begin() as cx:
                cx.execute(text("UPDATE content_plan_generation_jobs SET status='retry',last_error='queue enqueue failed',updated_at=:u WHERE id=:i"),
                           {"u": utcnow(), "i": jid})
            raise
    return queued


def enqueue_one(engine: Engine, queue, jid: int, force: bool = False) -> dict[str, Any]:
    now = utc_iso(datetime.now(timezone.utc))
    allowed = "('prepared','retry','failed','needs_changes')" if force else "('prepared','retry')"
    with engine.begin() as cx:
        claimed = cx.execute(text(
            f"UPDATE content_plan_generation_jobs SET status='queued',scheduled_at=:n,last_error=NULL,updated_at=:n "
            f"WHERE id=:i AND status IN {allowed}"), {"i": jid, "n": now}).rowcount
    if not claimed:
        current = _job(engine, jid)
        if not current:
            raise KeyError(jid)
        raise ValueError(f"job cannot run from status {current['status']}")
    current = _job(engine, jid)
    try:
        run = queue.enqueue(Job(type="content_automation", payload={"generation_job_id": jid}, site_id=current["site_id"]))
        with engine.begin() as cx:
            cx.execute(text("UPDATE content_plan_generation_jobs SET queue_run_id=:r,updated_at=:u WHERE id=:i"),
                       {"r": run.run_id, "u": utcnow(), "i": jid})
        return {"id": jid, "run_id": run.run_id, "status": run.status, "site_id": current["site_id"]}
    except Exception:
        with engine.begin() as cx:
            cx.execute(text("UPDATE content_plan_generation_jobs SET status='retry',last_error='queue enqueue failed',updated_at=:u WHERE id=:i"),
                       {"u": utcnow(), "i": jid})
        raise


class ContentAutomationService:
    def __init__(self, engine: Engine, gateway=None, pipeline_factory: Callable[..., Any] | None = None,
                 publisher_factory: Callable[..., Any] | None = None):
        self.engine = engine
        self.gateway = gateway
        self.pipeline_factory = pipeline_factory
        self.publisher_factory = publisher_factory

    def _update(self, jid: int, **fields: Any) -> None:
        allowed = {"status", "generation_run_id", "draft_id", "attempts", "queue_run_id", "last_error", "started_at", "finished_at", "scheduled_at"}
        values = {k: v for k, v in fields.items() if k in allowed}
        values["updated_at"] = utcnow()
        sets = ",".join(f"{k}=:{k}" for k in values)
        with self.engine.begin() as cx:
            cx.execute(text(f"UPDATE content_plan_generation_jobs SET {sets} WHERE id=:jid"), {**values, "jid": jid})

    def _failed(self, job: dict[str, Any], message: str) -> None:
        attempts = int(job.get("attempts") or 0) + 1
        retry = attempts < int(job.get("max_attempts") or 3)
        next_at = utc_iso(datetime.now(timezone.utc) + timedelta(minutes=60)) if retry else job.get("scheduled_at")
        self._update(job["id"], status="retry" if retry else "failed", attempts=attempts, last_error=message[:1000],
                     scheduled_at=next_at, finished_at=utcnow())

    def run(self, jid: int) -> dict[str, Any]:
        job = _job(self.engine, jid)
        if not job:
            raise KeyError(jid)
        if job["status"] in {"cancelled", "done", "scheduled", "wordpress_draft"}:
            return {"id": jid, "status": job["status"], "already_finished": True}
        self._update(jid, status="running", started_at=utcnow(), last_error=None)
        try:
            from ..brain.content import ContentIntelligenceService, ContentService
            from ..brain.generation import GenerationPipeline
            from ..brain.planner import PlannerService
            from ..wordpress.publisher import ContentPublisher

            planner = PlannerService(self.engine, ContentService(self.engine))
            cid = int(job.get("content_item_id") or planner.ensure_item(job["site_id"], int(job["plan_id"]), actor="scheduler")["content_id"])
            item = planner.content.repo.get(job["site_id"], cid)
            if not item or not item.brief_id:
                planner.brief(job["site_id"], int(job["plan_id"]), use_ai=False, mark_ready=True, actor="scheduler")
            if job["kind"] == "brief":
                self._update(jid, status="awaiting_approval", finished_at=utcnow())
                return {"id": jid, "status": "awaiting_approval", "content_id": cid, "kind": "brief"}

            if self.pipeline_factory:
                pipeline = self.pipeline_factory(self.engine, self.gateway)
            else:
                pipeline = GenerationPipeline(self.engine, self.gateway)
            params = job.get("params") or {}
            run = pipeline.create_run(job["site_id"], cid, "assisted", params.get("models"), params.get("prompt_versions"), "scheduler")
            self._update(jid, generation_run_id=run["run_id"])
            result = pipeline.execute(run["run_id"])
            if result.get("status") != "succeeded" or not result.get("draft_id"):
                raise RuntimeError(str(result.get("error") or "تولید مقاله کامل نشد"))
            draft_id = int(result["draft_id"])
            score = float(result.get("score") or 0)
            self._update(jid, draft_id=draft_id)
            if job.get("approval_mode") != "score_gate":
                planner.attach_generation_run(job["site_id"], jid, run["run_id"], draft_id)
                self._update(jid, status="awaiting_approval", attempts=int(job.get("attempts") or 0) + 1, finished_at=utcnow())
                return {"id": jid, "status": "awaiting_approval", "content_id": cid, "draft_id": draft_id, "score": score,
                        "review_status": result.get("review_status")}
            if result.get("review_status") != "ready" or score < float(job.get("min_score") or 85):
                self._update(jid, status="needs_changes", attempts=int(job.get("attempts") or 0) + 1,
                             last_error=f"quality gate: {result.get('review_status')} / {score}", finished_at=utcnow())
                return {"id": jid, "status": "needs_changes", "draft_id": draft_id, "score": score,
                        "required_score": float(job.get("min_score") or 85), "review_status": result.get("review_status")}

            item = planner.content.repo.get(job["site_id"], cid)
            for target in ("writing", "review"):
                if item and item.status in {"planned", "brief_ready", "writing"} and item.status != target:
                    item = planner.content.repo.transition(job["site_id"], cid, target, actor="scheduler", note=f"quality gate job #{jid}", force=(item.status == "planned"))
            ContentIntelligenceService(self.engine, None).check_gate(job["site_id"], cid, "approved")
            item = planner.content.repo.get(job["site_id"], cid)
            if item and item.status != "approved":
                planner.content.repo.transition(job["site_id"], cid, "approved", actor="scheduler", note=f"score gate {score}")
            planner.sync_from_item(job["site_id"], cid)

            action = job.get("publish_action") or "none"
            publication = None
            final_status = "approved"
            if action in {"draft", "future"}:
                publisher = self.publisher_factory(self.engine) if self.publisher_factory else ContentPublisher(self.engine)
                publication = publisher.publish(job["site_id"], cid, action, job.get("category_ids") or [], job.get("publish_at"), draft_id)
                final_status = "wordpress_draft" if action == "draft" else "scheduled"
            self._update(jid, status=final_status, attempts=int(job.get("attempts") or 0) + 1, finished_at=utcnow())
            return {"id": jid, "status": final_status, "content_id": cid, "draft_id": draft_id, "score": score, "publication": publication}
        except Exception as exc:
            fresh = _job(self.engine, jid) or job
            self._failed(fresh, f"{exc.__class__.__name__}: {exc}")
            raise

    def approve(self, jid: int, actor: str = "user") -> dict[str, Any]:
        """Human approval checkpoint: advance the content workflow and perform the job's configured delivery."""
        job = _job(self.engine, jid)
        if not job:
            raise KeyError(jid)
        if job["status"] != "awaiting_approval":
            raise ValueError(f"job cannot be approved from status {job['status']}")
        if not job.get("content_item_id") or not job.get("draft_id"):
            raise ValueError("job has no generated draft")
        from ..brain.content import ContentIntelligenceService, ContentService
        from ..brain.planner import PlannerService
        from ..wordpress.publisher import ContentPublisher

        planner = PlannerService(self.engine, ContentService(self.engine))
        cid = int(job["content_item_id"])
        item = planner.content.repo.get(job["site_id"], cid)
        if not item:
            raise KeyError(cid)
        for target in ("writing", "review"):
            if item.status in {"planned", "brief_ready", "writing"} and item.status != target:
                item = planner.content.repo.transition(job["site_id"], cid, target, actor=actor, note=f"approval job #{jid}", force=(item.status == "planned"))
        ContentIntelligenceService(self.engine, None).check_gate(job["site_id"], cid, "approved")
        item = planner.content.repo.get(job["site_id"], cid)
        if item and item.status != "approved":
            planner.content.repo.transition(job["site_id"], cid, "approved", actor=actor, note=f"approved job #{jid}")
        planner.sync_from_item(job["site_id"], cid)
        action = job.get("publish_action") or "none"
        publication = None
        final_status = "approved"
        if action in {"draft", "future"}:
            publisher = self.publisher_factory(self.engine) if self.publisher_factory else ContentPublisher(self.engine)
            publication = publisher.publish(job["site_id"], cid, action, job.get("category_ids") or [], job.get("publish_at"), int(job["draft_id"]))
            final_status = "wordpress_draft" if action == "draft" else "scheduled"
        self._update(jid, status=final_status, finished_at=utcnow(), last_error=None)
        return {"id": jid, "status": final_status, "content_id": cid, "draft_id": int(job["draft_id"]), "publication": publication}
