"""Job queue contract and the local durable implementation.

Jobs execute on background threads, but their state is written atomically to disk.  This means a browser
navigation never owns the lifetime of a task and queued/running work can be recovered after an API restart.
A Redis/RQ implementation can still replace this class later without changing callers.
"""
from __future__ import annotations

import logging
import json
import os
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, runtime_checkable

from ..common.config import env, resolve_path

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

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "JobRun":
        return cls(
            run_id=str(value["run_id"]),
            job=Job(type=str(value["type"]), payload=dict(value.get("payload") or {}), site_id=value.get("site_id")),
            status=str(value.get("status") or "queued"),
            queued_at=str(value.get("queued_at") or _now()),
            started_at=value.get("started_at"),
            finished_at=value.get("finished_at"),
            result=value.get("result"),
            error=value.get("error"),
        )

    def persisted_dict(self) -> dict[str, Any]:
        return {**self.to_dict(), "payload": self.job.payload}


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


class PersistentJobQueue(InProcessJobQueue):
    """A small, dependency-free durable queue suitable for the single API process.

    Each run has its own JSON file, so writes are cheap and one corrupt record cannot damage the queue.
    Jobs found in ``queued`` or ``running`` state are resumed once their handler is registered at startup.
    """

    def __init__(self, directory: str | os.PathLike[str] | None = None, sync: bool = False):
        super().__init__(sync=sync)
        configured = directory or env("JOB_QUEUE_DIR", "data/jobs") or "data/jobs"
        self._directory = resolve_path(configured)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._recovered_types: set[str] = set()
        self._load()

    def _load(self) -> None:
        for path in self._directory.glob("job-*.json"):
            try:
                run = JobRun.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self._runs[run.run_id] = run
            except Exception as exc:  # noqa: BLE001
                log.warning("ignored unreadable job record %s: %s", path, exc)

    def _persist(self, run: JobRun) -> None:
        path = self._directory / f"{run.run_id}.json"
        tmp = self._directory / f".{run.run_id}.{uuid.uuid4().hex}.tmp"
        try:
            payload = json.dumps(run.persisted_dict(), ensure_ascii=False, default=str, separators=(",", ":"))
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def register(self, job_type: str, handler: Handler) -> None:
        super().register(job_type, handler)
        if job_type in self._recovered_types:
            return
        self._recovered_types.add(job_type)
        recover = [r for r in self._runs.values() if r.job.type == job_type and r.status in {"queued", "running"}]
        for run in sorted(recover, key=lambda r: r.queued_at):
            run.status = "queued"
            run.started_at = None
            run.finished_at = None
            run.error = None
            self._persist(run)
            if self._sync:
                self._execute(run)
            else:
                threading.Thread(target=self._execute, args=(run,), daemon=True, name=f"job:{job_type}:recovered").start()

    def enqueue(self, job: Job) -> JobRun:
        if job.type not in self._handlers:
            raise KeyError(f"no handler registered for job type '{job.type}'")
        run = JobRun(run_id=f"job-{uuid.uuid4().hex[:12]}", job=job)
        if isinstance(job.payload, dict):
            job.payload.setdefault("job_id", run.run_id)
        with self._lock:
            self._runs[run.run_id] = run
            self._persist(run)
        if self._sync:
            self._execute(run)
        else:
            threading.Thread(target=self._execute, args=(run,), daemon=True, name=f"job:{job.type}").start()
        return run

    def _execute(self, run: JobRun) -> None:
        run.status, run.started_at, run.finished_at = "running", _now(), None
        self._persist(run)
        try:
            run.result = self._handlers[run.job.type](run.job.payload)
            run.status = "succeeded"
        except Exception as exc:  # noqa: BLE001
            run.status, run.error = "failed", f"{exc.__class__.__name__}: {exc}"
            log.error("job %s (%s) failed: %s\n%s", run.run_id, run.job.type, exc, traceback.format_exc())
        finally:
            run.finished_at = _now()
            self._persist(run)


_default: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """Return the process-wide durable queue (set JOB_QUEUE=inprocess only for ephemeral use)."""
    global _default
    if _default is None:
        _default = InProcessJobQueue() if env("JOB_QUEUE") == "inprocess" else PersistentJobQueue()
    return _default
