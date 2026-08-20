"""Automatic sync scheduler — a thin timer over the EXISTING jobs, queues and sync_runs. No new sync logic.

Every tick (default ۱۰ دقیقه):
  1. stale recovery — pipeline runs stuck in queued/running longer than the threshold (e.g. the API was restarted
     mid-run) are marked failed with an interruption note, in BOTH the sync_runs.status column and the state JSON
     in notes (which is what is_running() reads) — otherwise one crash blocks a site's syncs forever.
  2. planning — for every site and every configured integration, compare the last successful pipeline run
     (sync_runs) with the per-site interval (site_settings key `auto_sync`, default enabled/daily) and enqueue the
     SAME job the UI buttons use (_queue_wordpress_sync / _queue_gsc_sync / _queue_ga4_sync). The existing
     per-site locks + already_running guards make double-enqueue harmless.

Safety: max N sites started per tick (Google quota / SQLite contention), skipped entirely under pytest, daemon
thread stopped via lifespan; uvicorn reload kills the process (and the thread) before starting a new one.
Times are stored/compared in UTC; the UI renders them in the viewer's locale (Asia/Tehran by default).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine, text

from ..common.config import env

log = logging.getLogger("automation.scheduler")

PIPELINES = ("wordpress_pipeline", "gsc_pipeline", "ga4_pipeline")
OK_STATUSES = ("succeeded", "completed_with_errors")
DEFAULT_SETTINGS = {"enabled": True, "interval_hours": 24}
RETRY_AFTER_MINUTES = 60          # one gentle retry per hour for transient failures…
MAX_CONSECUTIVE_FAILURES = 3      # …then back off to the normal interval (not_authorized is never retried)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def auto_sync_settings(engine: Engine, site_id: str) -> dict[str, Any]:
    with engine.connect() as cx:
        r = cx.execute(text("SELECT value FROM site_settings WHERE site_id=:s AND key='auto_sync'"), {"s": site_id}).first()
    out = dict(DEFAULT_SETTINGS)
    if r and r[0]:
        try:
            out.update({k: v for k, v in json.loads(r[0]).items() if k in DEFAULT_SETTINGS})
        except ValueError:
            pass
    out["interval_hours"] = max(1, min(24 * 7, int(out.get("interval_hours") or 24)))
    return out


def save_auto_sync_settings(engine: Engine, site_id: str, enabled: bool | None = None, interval_hours: int | None = None) -> dict[str, Any]:
    cur = auto_sync_settings(engine, site_id)
    if enabled is not None:
        cur["enabled"] = bool(enabled)
    if interval_hours is not None:
        cur["interval_hours"] = max(1, min(24 * 7, int(interval_hours)))
    with engine.begin() as cx:
        cx.execute(text("INSERT INTO site_settings(site_id, key, value, updated_at) VALUES(:s,'auto_sync',:v,:u) "
                        "ON CONFLICT(site_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at"),
                   {"s": site_id, "v": json.dumps(cur), "u": _iso(_utcnow())})
    return cur


def recover_stale_runs(engine: Engine, stale_after_minutes: int = 120) -> int:
    """Mark pipeline runs stuck in queued/running as failed (column AND state JSON) so is_running() unblocks."""
    cutoff = _iso(_utcnow() - timedelta(minutes=stale_after_minutes))
    fixed = 0
    with engine.begin() as cx:
        rows = cx.execute(text("SELECT run_id, notes FROM sync_runs WHERE source IN ('wordpress_pipeline','gsc_pipeline','ga4_pipeline','wordpress','gsc','ga4') "
                               "AND status IN ('queued','running') AND started_at < :c"), {"c": cutoff}).all()
        for run_id, notes in rows:
            state = None
            if notes:
                try:
                    state = json.loads(notes)
                except ValueError:
                    state = None
            if isinstance(state, dict) and "status" in state:
                state["status"] = "failed"
                state["finished_at"] = _iso(_utcnow())
                state["errors"] = [*(state.get("errors") or []), "interrupted: process restarted before the run finished"]
                for s in state.get("steps") or []:
                    if s.get("status") in ("queued", "running", "pending"):
                        s["status"] = "failed" if s.get("status") == "running" else "skipped"
                notes = json.dumps(state, ensure_ascii=False)
            cx.execute(text("UPDATE sync_runs SET status='failed', finished_at=:f, notes=:n WHERE run_id=:r"),
                       {"f": _iso(_utcnow()), "n": notes, "r": run_id})
            fixed += 1
    if fixed:
        log.warning(f"scheduler: recovered {fixed} stale sync run(s) (marked failed after >{stale_after_minutes}min)")
    return fixed


def last_success(engine: Engine, site_id: str, source: str) -> datetime | None:
    with engine.connect() as cx:
        r = cx.execute(text("SELECT finished_at FROM sync_runs WHERE site_id=:s AND source=:src AND status IN ('succeeded','completed_with_errors') "
                            "ORDER BY started_at DESC LIMIT 1"), {"s": site_id, "src": source}).first()
    return _parse(r[0]) if r else None


def _failure_streak(engine: Engine, site_id: str, source: str) -> tuple[int, datetime | None, str | None]:
    """(consecutive failed runs since the last success, started_at of the newest run, its status)."""
    with engine.connect() as cx:
        rows = cx.execute(text("SELECT status, started_at FROM sync_runs WHERE site_id=:s AND source=:src "
                               "ORDER BY started_at DESC, id DESC LIMIT 10"), {"s": site_id, "src": source}).all()
    if not rows:
        return 0, None, None
    streak = 0
    for st, _ts in rows:
        if st == "failed":
            streak += 1
        else:
            break
    return streak, _parse(rows[0][1]), rows[0][0]


def plan_for_site(engine: Engine, site_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Per-integration plan used by both the scheduler and the auto-sync API: last success, next planned, due."""
    now = now or _utcnow()
    cfg = auto_sync_settings(engine, site_id)
    interval = timedelta(hours=cfg["interval_hours"])
    with engine.connect() as cx:
        site = cx.execute(text("SELECT wp_url, gsc_property, ga4_property FROM sites WHERE site_id=:s"), {"s": site_id}).first()
    if not site:
        return {"enabled": cfg["enabled"], "interval_hours": cfg["interval_hours"], "sources": {}}
    from ..connections.service import GA4_SCOPE, _google_client_configured, _token_info
    tok = _token_info()
    google_ok = _google_client_configured() and tok.get("present")
    configured = {
        "wordpress": bool(site[0]),
        "gsc": bool(site[1] and google_ok),
        "ga4": bool(site[2] and google_ok and GA4_SCOPE in (tok.get("scopes") or [])),
    }
    sources: dict[str, Any] = {}
    for kind, src in (("wordpress", "wordpress_pipeline"), ("gsc", "gsc_pipeline"), ("ga4", "ga4_pipeline")):
        last = last_success(engine, site_id, src)
        nxt = (last + interval) if last else now
        # transient-failure retry: newest run failed (never not_authorized) → one retry per hour, max 3 in a row
        streak, latest_started, latest_status = _failure_streak(engine, site_id, src)
        if (cfg["enabled"] and configured[kind] and latest_status == "failed"
                and 0 < streak < MAX_CONSECUTIVE_FAILURES and latest_started):
            retry_at = latest_started + timedelta(minutes=RETRY_AFTER_MINUTES)
            if retry_at < nxt:
                nxt = retry_at
        sources[kind] = {"configured": configured[kind], "last_success": _iso(last) if last else None,
                         "next_at": _iso(nxt) if (cfg["enabled"] and configured[kind]) else None,
                         "due": bool(cfg["enabled"] and configured[kind] and nxt <= now)}
    return {"enabled": cfg["enabled"], "interval_hours": cfg["interval_hours"], "sources": sources}


def run_tick(engine: Engine, queue, max_sites: int = 2, stale_after_minutes: int = 120) -> dict[str, Any]:
    """One scheduler pass: recover stale runs, then enqueue the existing jobs for due integrations (staggered)."""
    recovered = recover_stale_runs(engine, stale_after_minutes)
    with engine.connect() as cx:
        site_ids = [r[0] for r in cx.execute(text("SELECT site_id FROM sites ORDER BY site_id")).all()]
    queued: list[dict[str, str]] = []
    started_sites = 0
    from ..api.routers.sites import _queue_ga4_sync, _queue_gsc_sync, _queue_wordpress_sync
    for sid in site_ids:
        if started_sites >= max_sites:
            break
        plan = plan_for_site(engine, sid)
        due = [k for k, v in plan["sources"].items() if v["due"]]
        if not due:
            continue
        started_sites += 1
        for kind in due:
            try:
                if kind == "wordpress":
                    r = _queue_wordpress_sync(sid, engine, queue, stage="full", crawl=True, max_urls=None, reason="scheduler")
                elif kind == "gsc":
                    r = _queue_gsc_sync(sid, engine, queue, days=None, reason="scheduler")
                else:
                    r = _queue_ga4_sync(sid, engine, queue, days=None, reason="scheduler")
                queued.append({"site_id": sid, "kind": kind, "status": r.get("status", "?")})
            except Exception as e:  # noqa: BLE001 — one failure must not stop the tick
                log.error(f"scheduler: enqueue {kind} for {sid} failed: {e.__class__.__name__}: {e}")
    if queued:
        log.info(f"scheduler tick: recovered={recovered}, queued={queued}")
    return {"recovered": recovered, "queued": queued, "sites_started": started_sites}


class SyncScheduler:
    """Daemon-thread ticker; started from the FastAPI lifespan (skipped under pytest and when the flag is off)."""

    def __init__(self, engine: Engine, queue, tick_seconds: int | None = None, max_sites: int | None = None, stale_after_minutes: int | None = None):
        self.engine = engine
        self.queue = queue
        self.tick_seconds = tick_seconds or int(env("SCHEDULER_TICK_SECONDS", "600"))
        self.max_sites = max_sites or int(env("SCHEDULER_MAX_SITES_PER_TICK", "2"))
        self.stale_after_minutes = stale_after_minutes or int(env("SCHEDULER_STALE_MINUTES", "120"))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def enabled() -> bool:
        return env("SCHEDULER_ENABLED", "1") == "1" and "PYTEST_CURRENT_TEST" not in os.environ

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="sync-scheduler")
        self._thread.start()
        log.info(f"sync scheduler started (tick={self.tick_seconds}s, max_sites/tick={self.max_sites}, stale>{self.stale_after_minutes}min)")

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        # first tick shortly after startup (recovers stale runs from the previous process quickly)
        wait = min(30, self.tick_seconds)
        while not self._stop.wait(wait):
            wait = self.tick_seconds
            try:
                run_tick(self.engine, self.queue, self.max_sites, self.stale_after_minutes)
            except Exception as e:  # noqa: BLE001 — the loop must survive anything
                log.error(f"scheduler tick failed: {e.__class__.__name__}: {e}")
