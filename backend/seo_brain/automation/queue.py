"""JobQueue contract + in-process implementation.

Local (now): `InProcessJobQueue` runs handlers on a background thread inside the API process and keeps run
state in memory (phase 8 persists it in `jobs`/`job_runs` and adds cron scheduling).
Server (later): a Redis/RQ-backed queue implements the same Protocol; API and services do not change.
"""
from __future__ import annotations

import logging
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, runtime_checkable

log = logging.getLogger("automation.queue")
Handler = Callable[[dict[str, Any]], Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class Job:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    site_id: str | None = None


@dataclass
class JobRun:
    run_id: str
    job: Job
    status: str = "queued"          # queued | running | succeeded | failed
    queued_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "type": self.job.type, "site_id": self.job.site_id, "status": self.status,
                "queued_at": self.queued_at, "started_at": self.started_at, "finished_at": self.finished_at,
                "result": self.result, "error": self.error}


@runtime_checkable
class JobQueue(Protocol):
    def register(self, job_type: str, handler: Handler) -> None: ...
    def enqueue(self, job: Job) -> JobRun: ...
    def get(self, run_id: str) -> JobRun | None: ...
    def list(self, limit: int = 50) -> list[JobRun]: ...


class InProcessJobQueue:
    def __init__(self, sync: bool = False):
        self._handlers: dict[str, Handler] = {}
        self._runs: dict[str, JobRun] = {}
        self._lock = threading.Lock()
        self._sync = sync            # tests: run inline

    def register(self, job_type: str, handler: Handler) -> None:
        self._handlers[job_type] = handler

    def enqueue(self, job: Job) -> JobRun:
        if job.type not in self._handlers:
            raise KeyError(f"no handler registered for job type '{job.type}'")
        run = JobRun(run_id=f"job-{uuid.uuid4().hex[:12]}", job=job)
        if isinstance(job.payload, dict):
            job.payload.setdefault("job_id", run.run_id)     # known before the worker thread starts — no attach race
        with self._lock:
            self._runs[run.run_id] = run
        if self._sync:
            self._execute(run)
        else:
            threading.Thread(target=self._execute, args=(run,), daemon=True, name=f"job:{job.type}").start()
        return run

    def _execute(self, run: JobRun) -> None:
        run.status, run.started_at = "running", _now()
        try:
            run.result = self._handlers[run.job.type](run.job.payload)
            run.status = "succeeded"
        except Exception as e:  # noqa: BLE001
            run.status, run.error = "failed", f"{e.__class__.__name__}: {e}"
            log.error(f"job {run.run_id} ({run.job.type}) failed: {e}\n{traceback.format_exc()}")
        finally:
            run.finished_at = _now()

    def get(self, run_id: str) -> JobRun | None:
        return self._runs.get(run_id)

    def list(self, limit: int = 50) -> list[JobRun]:
        return sorted(self._runs.values(), key=lambda r: r.queued_at, reverse=True)[:limit]


_default: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """Factory: JOB_QUEUE=inprocess (default). Future: redis."""
    global _default
    if _default is None:
        _default = InProcessJobQueue()
    return _default
