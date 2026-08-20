"""GA4 production pipeline — wiring only, the GA4 twin of gsc/pipeline.py. Every step is an existing component:

    GA4 connect / manual button → [ga4_sync job]
        ├─ sync        ga4.sync.sync_ga4 (non-interactive; ga4_daily upserts, history in sync_runs source='ga4')
        ├─ snapshot    brain.content.analytics.ContentAnalytics.snapshot (content_metrics — now incl. ga4_* columns)
        └─ graph       wordpress.orchestrator graph_only stage (the one existing rebuild path: ga4_* props on
                       PAGE/POST nodes + run_analysis → GA4 opportunities in seo_opportunities)

State lives in the existing sync_runs table (source `ga4_pipeline`, notes = JSON). No OAuth in the worker:
a missing/expired token or missing analytics scope surfaces as status `not_authorized`.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import Engine, text

from ..common.config import get_site
from ..common.logging_setup import new_run_id
from ..db.repositories.base import utcnow

log = logging.getLogger("ga4.pipeline")

STEPS: list[tuple[str, str]] = [
    ("sync", "در حال دریافت داده از Google Analytics"),
    ("snapshot", "در حال ثبت اسنپ‌شات عملکرد محتوا"),
    ("graph", "در حال به‌روزرسانی گراف و فرصت‌ها"),
]
STEP_FA = dict(STEPS)
SOURCE = "ga4_pipeline"
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _site_lock(site_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(site_id, threading.Lock())


@dataclass
class Ga4RunState:
    run_id: str
    site_id: str
    status: str = "queued"          # queued | running | succeeded | completed_with_errors | failed | not_authorized
    step: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    items: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    job_id: str | None = None

    @property
    def progress(self) -> float:
        done = sum(1 for s in self.steps if s["status"] in ("done", "skipped", "failed"))
        return round(done / len(self.steps), 3) if self.steps else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "site_id": self.site_id, "status": self.status, "step": self.step,
                "step_fa": STEP_FA.get(self.step or "", self.step), "progress": self.progress, "steps": self.steps,
                "items": self.items, "errors": self.errors, "started_at": self.started_at, "finished_at": self.finished_at, "job_id": self.job_id}


class Ga4Pipeline:
    """`sync_fn` / `snapshot_fn` / `graph_fn` are injectable for tests (no network in CI)."""

    def __init__(self, engine: Engine, sync_fn: Callable[..., dict] | None = None,
                 snapshot_fn: Callable[[str], dict] | None = None, graph_fn: Callable[[str], dict] | None = None):
        self.engine = engine
        self._sync_fn = sync_fn
        self._snapshot_fn = snapshot_fn
        self._graph_fn = graph_fn

    # ------------------------------------------------------------------ state persistence (existing sync_runs table)
    def _persist(self, st: Ga4RunState) -> None:
        with self.engine.begin() as cx:
            row = cx.execute(text("SELECT run_id, notes FROM sync_runs WHERE run_id=:r"), {"r": st.run_id}).first()
            if row and row[1] and not st.job_id:
                try:  # the job thread may persist before the API attached the job id — never drop it
                    st.job_id = (json.loads(row[1]) or {}).get("job_id") or None
                except ValueError:
                    pass
            payload = json.dumps(st.to_dict(), ensure_ascii=False)
            if row:
                cx.execute(text("UPDATE sync_runs SET status=:s, finished_at=:f, notes=:n, rows_written=:w WHERE run_id=:r"),
                           {"s": st.status, "f": st.finished_at, "n": payload, "w": int(st.items.get("rows", 0) or 0), "r": st.run_id})
            else:
                cx.execute(text("INSERT INTO sync_runs(run_id, site_id, source, started_at, finished_at, status, rows_written, notes) VALUES(:r,:s,:src,:st,:f,:status,0,:n)"),
                           {"r": st.run_id, "s": st.site_id, "src": SOURCE, "st": st.started_at or utcnow(), "f": st.finished_at, "status": st.status, "n": payload})

    def latest(self, site_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as cx:
            r = cx.execute(text("SELECT notes FROM sync_runs WHERE site_id=:s AND source=:src ORDER BY started_at DESC, rowid DESC LIMIT 1"), {"s": site_id, "src": SOURCE}).first()
        if not r or not r[0]:
            return None
        try:
            return json.loads(r[0])
        except ValueError:
            return None

    def is_running(self, site_id: str) -> bool:
        st = self.latest(site_id)
        return bool(st and st.get("status") in ("queued", "running"))

    def create(self, site_id: str, job_id: str | None = None) -> Ga4RunState:
        st = Ga4RunState(run_id=new_run_id("ga4pipe"), site_id=site_id, status="queued", job_id=job_id, started_at=utcnow())
        st.steps = [{"key": k, "fa": STEP_FA[k], "status": "pending", "started_at": None, "finished_at": None, "items": {}, "error": None} for k, _ in STEPS]
        self._persist(st)
        return st

    def attach_job(self, run_id: str, job_id: str) -> None:
        with self.engine.begin() as cx:
            r = cx.execute(text("SELECT notes FROM sync_runs WHERE run_id=:r"), {"r": run_id}).first()
            if r and r[0]:
                d = json.loads(r[0]); d["job_id"] = job_id
                cx.execute(text("UPDATE sync_runs SET notes=:n WHERE run_id=:r"), {"n": json.dumps(d, ensure_ascii=False), "r": run_id})

    # ------------------------------------------------------------------ coverage counters (from ga4_daily — the UI card)
    def coverage(self, site_id: str) -> dict[str, Any]:
        with self.engine.connect() as cx:
            d = cx.execute(text("SELECT MIN(date), MAX(date), COUNT(*), COUNT(DISTINCT page_path), SUM(sessions), SUM(total_users), SUM(conversions) "
                                "FROM ga4_daily WHERE site_id=:s AND source='page'"), {"s": site_id}).first()
            snaps = cx.execute(text("SELECT COUNT(*) FROM content_metrics WHERE site_id=:s AND ga4_sessions IS NOT NULL"), {"s": site_id}).scalar() or 0
            last = cx.execute(text("SELECT finished_at FROM sync_runs WHERE site_id=:s AND source='ga4' AND status='completed' ORDER BY started_at DESC LIMIT 1"), {"s": site_id}).scalar()
            top = [{"path": r[0], "sessions": int(r[1] or 0), "conversions": round(float(r[2] or 0), 1)} for r in
                   cx.execute(text("SELECT page_path, SUM(sessions), SUM(conversions) FROM ga4_daily WHERE site_id=:s AND source='page' "
                                   "GROUP BY page_path ORDER BY SUM(sessions) DESC LIMIT 5"), {"s": site_id}).all()]
        return {"date_from": d[0], "date_to": d[1], "rows": int(d[2] or 0), "pages": int(d[3] or 0),
                "sessions": int(d[4] or 0), "users": int(d[5] or 0), "conversions": round(float(d[6] or 0), 1),
                "content_snapshots": int(snaps), "last_ga4_sync": last, "top_pages": top}

    def status(self, site_id: str, job_queue=None) -> dict[str, Any]:
        st = self.latest(site_id)
        live = None
        if st and job_queue is not None and st.get("job_id"):
            jr = job_queue.get(st["job_id"])
            live = jr.to_dict() if jr else None
        return {"status": (st or {}).get("status", "never"), "step": (st or {}).get("step"), "step_fa": (st or {}).get("step_fa"),
                "progress": (st or {}).get("progress", 0), "started_at": (st or {}).get("started_at"), "finished_at": (st or {}).get("finished_at"),
                "items": (st or {}).get("items", {}), "errors": (st or {}).get("errors", []), "steps": (st or {}).get("steps", []),
                "run_id": (st or {}).get("run_id"), "job_id": (st or {}).get("job_id"), "job": live,
                "coverage": self.coverage(site_id), "steps_fa": STEP_FA}

    # ------------------------------------------------------------------ run (inside the ga4_sync job)
    def run(self, site_id: str, run_id: str | None = None, days: int | None = None, job_id: str | None = None) -> dict[str, Any]:
        lock = _site_lock(site_id)
        if not lock.acquire(blocking=False):
            raise RuntimeError("همگام‌سازی GA4 دیگری برای این سایت در حال اجراست")
        try:
            st = self._load_or_create(site_id, run_id, job_id)
            st.status, st.started_at = "running", st.started_at or utcnow()
            self._persist(st)
            self._step(st, "sync", lambda: self._sync(site_id, days))
            if st.status == "not_authorized":
                for s in st.steps:
                    if s["status"] == "pending":
                        s["status"] = "skipped"; s["items"] = {"reason": "not_authorized"}
                st.finished_at = utcnow(); self._persist(st)
                return st.to_dict()
            self._step(st, "snapshot", lambda: self._snapshot(site_id))
            self._step(st, "graph", lambda: self._graph(site_id))
            st.status = "completed_with_errors" if st.errors else "succeeded"
            st.finished_at = utcnow()
            self._persist(st)
            return st.to_dict()
        except Exception as e:  # noqa: BLE001
            st2 = self.latest(site_id)
            if st2 and st2.get("run_id"):
                s2 = Ga4RunState(**{k: st2[k] for k in ("run_id", "site_id", "steps", "items", "errors", "started_at", "job_id")})
                s2.status = st2.get("status") if st2.get("status") == "not_authorized" else "failed"
                s2.errors = list(s2.errors) + [f"{e.__class__.__name__}: {str(e)[:200]}"]
                s2.finished_at = utcnow()
                self._persist(s2)
            raise
        finally:
            lock.release()

    def _load_or_create(self, site_id: str, run_id: str | None, job_id: str | None) -> Ga4RunState:
        if run_id:
            with self.engine.connect() as cx:
                r = cx.execute(text("SELECT notes FROM sync_runs WHERE run_id=:r"), {"r": run_id}).first()
            if r and r[0]:
                d = json.loads(r[0])
                st = Ga4RunState(run_id=run_id, site_id=site_id, status=d.get("status", "queued"), steps=d.get("steps", []),
                                 items=d.get("items", {}), errors=d.get("errors", []), started_at=d.get("started_at"), job_id=job_id or d.get("job_id"))
                if st.steps:
                    return st
        return self.create(site_id, job_id)

    def _step(self, st: Ga4RunState, key: str, fn: Callable[[], dict | None]) -> None:
        for s in st.steps:
            if s["key"] == key:
                s["status"], s["started_at"] = "running", utcnow()
        st.step = key
        self._persist(st)
        t0 = time.perf_counter()
        try:
            out = fn() or {}
            status = out.pop("_step_status", "done")
            for s in st.steps:
                if s["key"] == key:
                    s["status"], s["finished_at"], s["items"] = status, utcnow(), {**out, "ms": int((time.perf_counter() - t0) * 1000)}
            for k in ("rows", "pages", "sessions", "users", "conversions", "snapshots", "graph_nodes", "graph_edges"):
                if k in out:
                    st.items[k] = out[k]
            if out.get("_not_authorized"):
                st.status = "not_authorized"
        except Exception as e:  # noqa: BLE001
            msg = f"{e.__class__.__name__}: {str(e)[:200]}"
            st.errors.append(f"{key}: {msg}")
            for s in st.steps:
                if s["key"] == key:
                    s["status"], s["finished_at"], s["error"] = "failed", utcnow(), msg
            if key == "sync":
                st.status = "failed"; st.finished_at = utcnow(); self._persist(st)
                raise
        self._persist(st)

    # ------------------------------------------------------------------ steps — every one delegates to an existing component
    def _sync(self, site_id: str, days: int | None) -> dict:
        if self._sync_fn:
            return self._sync_fn(site_id, days)
        from ..database.db import db
        from ..gsc.client import GscAuthError, date_window
        from .sync import sync_ga4
        site = get_site(site_id)
        with self.engine.connect() as cx:
            pid = cx.execute(text("SELECT ga4_property FROM sites WHERE site_id=:s"), {"s": site_id}).scalar()
        start, end = date_window(days or 30, end_offset_days=1)     # GA4 lags ~1 day (GSC helper reused)
        try:
            with db() as conn:
                out = sync_ga4(conn, site, start, end, property_id=pid, interactive=False)
            return {k: out.get(k) for k in ("run_id", "property", "rows", "pages", "sessions", "users", "conversions", "date_from", "date_to")}
        except GscAuthError as e:
            log.warning(f"GA4 not authorized for {site_id}: {e.__class__.__name__}")
            return {"_step_status": "failed", "_not_authorized": True,
                    "error": "توکن Google یا دسترسی GA4 معتبر نیست؛ اتصال GA4 را دوباره تست کنید"}

    def _snapshot(self, site_id: str) -> dict:
        if self._snapshot_fn:
            return self._snapshot_fn(site_id)
        from ..brain.content.analytics import ContentAnalytics
        out = ContentAnalytics(self.engine).snapshot(site_id)
        if not out.get("items"):
            return {"_step_status": "skipped", "reason": "no_content_with_url"}
        return {"snapshots": out.get("snapshots"), "content_items": out.get("items"), "source": out.get("source")}

    def _graph(self, site_id: str) -> dict:
        """Graph + opportunity refresh through the one existing rebuild path (wordpress orchestrator, graph_only stage)."""
        if self._graph_fn:
            return self._graph_fn(site_id)
        from ..wordpress.orchestrator import WordPressSyncOrchestrator
        orch = WordPressSyncOrchestrator(self.engine)
        if orch.is_running(site_id):
            return {"_step_status": "skipped", "reason": "graph_rebuild_busy"}
        out = orch.run(site_id, stage="graph_only", crawl=False)
        counts = orch.counts(site_id)
        return {"graph_nodes": counts.get("graph_nodes"), "graph_edges": counts.get("graph_edges"), "graph_status": out.get("status")}
