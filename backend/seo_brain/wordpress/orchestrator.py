"""WordPress → Sync → Graph pipeline orchestrator (wiring only — every step is an existing component).

    WordPress connect → initialize → [wordpress_sync job]
        ├── taxonomies / categories / pages / posts / media   (wordpress.sync.sync_wordpress — v0.1, read-only REST)
        ├── category intelligence                             (brain.planner.categories — content_categories from the fresh snapshot)
        ├── crawl (enrichment: links, headings, metrics)      (crawler.Crawler — optional, capped)
        └── build graph                                       (graph.GraphBuild: WordPress pages/posts are the source of truth for
                                                               PAGE/POST/CATEGORY nodes; crawl only enriches) + keyword / content /
                                                               planner graph syncs (KEYWORD→TARGETS→CONTENT, TOPIC→SUPPORTS→CONTENT …)

Runs inside the existing JobQueue (job type `wordpress_sync`). Status is persisted in the existing `sync_runs` table
(source `wordpress_pipeline`, `notes` = JSON progress) so `GET /sites/{id}/wordpress/sync/status` works after restarts.
Credentials come from the SecretStore/.env via WordPressClient and are never written to status/notes/logs.
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
from ..common.urls import resolve_wordpress_base
from ..db.repositories.base import utcnow

log = logging.getLogger("wordpress.orchestrator")

STEPS: list[tuple[str, str]] = [
    ("resolve", "بررسی آدرس وردپرس"),
    ("categories", "در حال دریافت دسته‌بندی‌ها"),
    ("pages", "در حال دریافت صفحات"),
    ("posts", "در حال دریافت نوشته‌ها"),
    ("taxonomies", "در حال دریافت تاکسونومی‌ها و رسانه‌ها"),
    ("category_intelligence", "در حال تحلیل دسته‌بندی‌ها"),
    ("crawl", "در حال استخراج لینک‌ها"),
    ("build_graph", "در حال ساخت گراف"),
]
STEP_FA = dict(STEPS)
SOURCE = "wordpress_pipeline"
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _site_lock(site_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(site_id, threading.Lock())


@dataclass
class PipelineState:
    run_id: str
    site_id: str
    stage: str = "full"                     # full | graph_only
    status: str = "queued"                  # queued | running | succeeded | completed_with_errors | failed
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
        return {"run_id": self.run_id, "site_id": self.site_id, "stage": self.stage, "status": self.status, "step": self.step, "step_fa": STEP_FA.get(self.step or "", self.step),
                "progress": self.progress, "steps": self.steps, "items": self.items, "errors": self.errors, "started_at": self.started_at, "finished_at": self.finished_at, "job_id": self.job_id}


class WordPressSyncOrchestrator:
    def __init__(self, engine: Engine, crawler_factory: Callable[..., Any] | None = None, wp_sync: Callable[..., dict] | None = None,
                 graph_build: Callable[..., dict] | None = None, probe: Callable[[str], int | None] | None = None):
        self.engine = engine
        self._crawler_factory = crawler_factory
        self._wp_sync = wp_sync
        self._graph_build = graph_build
        self._probe = probe

    # ------------------------------------------------------------------ status persistence (sync_runs.notes = JSON state)
    def _persist(self, st: PipelineState) -> None:
        with self.engine.begin() as cx:
            row = cx.execute(text("SELECT run_id, notes FROM sync_runs WHERE run_id=:r"), {"r": st.run_id}).first()
            if row and row[1] and not st.job_id:
                # the job thread may start before the API attached the job id — never overwrite a stored job_id with None
                try:
                    st.job_id = (json.loads(row[1]) or {}).get("job_id") or None
                except ValueError:
                    pass
            payload = json.dumps(st.to_dict(), ensure_ascii=False)
            if row:
                cx.execute(text("UPDATE sync_runs SET status=:s, finished_at=:f, notes=:n, rows_written=:w WHERE run_id=:r"),
                           {"s": st.status, "f": st.finished_at, "n": payload, "w": int(st.items.get("posts", 0) or 0) + int(st.items.get("pages", 0) or 0), "r": st.run_id})
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

    def counts(self, site_id: str) -> dict[str, Any]:
        """What the site currently has (from the real tables) — the UI counters."""
        with self.engine.connect() as cx:
            q = lambda sql: int(cx.execute(text(sql), {"s": site_id}).scalar() or 0)  # noqa: E731
            return {"categories": q("SELECT COUNT(*) FROM categories WHERE site_id=:s AND taxonomy='category'"),
                    "pages": q("SELECT COUNT(*) FROM posts WHERE site_id=:s AND type='page'"),
                    "posts": q("SELECT COUNT(*) FROM posts WHERE site_id=:s AND type='post'"),
                    "content_items": q("SELECT COUNT(*) FROM posts WHERE site_id=:s"),
                    "taxonomies": q("SELECT COUNT(*) FROM taxonomies WHERE site_id=:s"),
                    "crawled": q("SELECT COUNT(*) FROM pages WHERE site_id=:s AND crawl_status='ok'"),
                    "graph_nodes": q("SELECT COUNT(*) FROM graph_nodes WHERE site_id=:s"),
                    "graph_edges": q("SELECT COUNT(*) FROM graph_edges WHERE site_id=:s"),
                    "graph_by_type": {r[0]: r[1] for r in cx.execute(text("SELECT node_type, COUNT(*) FROM graph_nodes WHERE site_id=:s GROUP BY node_type"), {"s": site_id}).all()}}

    def status(self, site_id: str, job_queue=None) -> dict[str, Any]:
        st = self.latest(site_id)
        live = None
        if st and job_queue is not None and st.get("job_id"):
            jr = job_queue.get(st["job_id"])
            live = jr.to_dict() if jr else None
        return {"status": (st or {}).get("status", "never"), "step": (st or {}).get("step"), "step_fa": (st or {}).get("step_fa"), "progress": (st or {}).get("progress", 0),
                "stage": (st or {}).get("stage"), "started_at": (st or {}).get("started_at"), "finished_at": (st or {}).get("finished_at"), "items": (st or {}).get("items", {}),
                "errors": (st or {}).get("errors", []), "steps": (st or {}).get("steps", []), "run_id": (st or {}).get("run_id"), "job_id": (st or {}).get("job_id"), "job": live,
                "counts": self.counts(site_id), "steps_fa": STEP_FA}

    def is_running(self, site_id: str) -> bool:
        st = self.latest(site_id)
        return bool(st and st.get("status") in ("queued", "running"))

    # ------------------------------------------------------------------ public: create a queued state (called by the API before enqueueing)
    def create(self, site_id: str, stage: str = "full", job_id: str | None = None) -> PipelineState:
        st = PipelineState(run_id=new_run_id("wpsync"), site_id=site_id, stage=stage, status="queued", job_id=job_id, started_at=utcnow())
        keys = [k for k, _ in STEPS] if stage == "full" else ["build_graph"]
        st.steps = [{"key": k, "fa": STEP_FA[k], "status": "pending", "started_at": None, "finished_at": None, "items": {}, "error": None} for k in keys]
        self._persist(st)
        return st

    def attach_job(self, run_id: str, job_id: str) -> None:
        with self.engine.begin() as cx:
            r = cx.execute(text("SELECT notes FROM sync_runs WHERE run_id=:r"), {"r": run_id}).first()
            if r and r[0]:
                d = json.loads(r[0]); d["job_id"] = job_id
                cx.execute(text("UPDATE sync_runs SET notes=:n WHERE run_id=:r"), {"n": json.dumps(d, ensure_ascii=False), "r": run_id})

    # ------------------------------------------------------------------ run (inside the job)
    def run(self, site_id: str, run_id: str | None = None, stage: str = "full", crawl: bool = True, max_urls: int | None = None, job_id: str | None = None) -> dict[str, Any]:
        lock = _site_lock(site_id)
        if not lock.acquire(blocking=False):
            raise RuntimeError("همگام‌سازی دیگری برای این سایت در حال اجراست")
        try:
            st = self._load_or_create(site_id, run_id, stage, job_id)
            st.status, st.started_at = "running", st.started_at or utcnow()
            self._persist(st)
            if stage == "full":
                self._step(st, "resolve", lambda: self._resolve(site_id))
                self._wordpress_steps(st, site_id)
                self._step(st, "category_intelligence", lambda: self._category_intelligence(site_id))
                if crawl:
                    self._step(st, "crawl", lambda: self._crawl(site_id, max_urls))
                else:
                    self._mark(st, "crawl", "skipped", {"reason": "crawl disabled"})
            self._step(st, "build_graph", lambda: self._build_graph(site_id))
            st.items.update({k: v for k, v in self.counts(site_id).items() if k != "graph_by_type"})
            st.status = "completed_with_errors" if st.errors else "succeeded"
            st.step, st.finished_at = None, utcnow()
            self._persist(st)
            return st.to_dict()
        except Exception as e:  # noqa: BLE001
            log.error("wordpress pipeline failed for %s: %s", site_id, e)
            try:
                st.status, st.finished_at = "failed", utcnow()
                if str(e) not in st.errors:
                    st.errors.append(f"{e.__class__.__name__}: {str(e)[:200]}")
                self._persist(st)
            except Exception:  # noqa: BLE001
                pass
            raise
        finally:
            lock.release()

    # ------------------------------------------------------------------ steps
    def _load_or_create(self, site_id: str, run_id: str | None, stage: str, job_id: str | None) -> PipelineState:
        if run_id:
            with self.engine.connect() as cx:
                r = cx.execute(text("SELECT notes FROM sync_runs WHERE run_id=:r"), {"r": run_id}).first()
            if r and r[0]:
                d = json.loads(r[0])
                st = PipelineState(run_id=run_id, site_id=site_id, stage=d.get("stage", stage), status=d.get("status", "queued"), steps=d.get("steps", []), items=d.get("items", {}),
                                   errors=d.get("errors", []), started_at=d.get("started_at"), job_id=job_id or d.get("job_id"))
                if st.steps:
                    return st
        return self.create(site_id, stage, job_id)

    def _mark(self, st: PipelineState, key: str, status: str, items: dict | None = None, error: str | None = None) -> None:
        for s in st.steps:
            if s["key"] == key:
                s["status"] = status
                if status == "running":
                    s["started_at"] = utcnow(); st.step = key
                else:
                    s["finished_at"] = utcnow()
                if items: s["items"] = {**s.get("items", {}), **items}
                if error: s["error"] = error
        self._persist(st)

    def _step(self, st: PipelineState, key: str, fn: Callable[[], dict | None]) -> None:
        self._mark(st, key, "running")
        t0 = time.perf_counter()
        try:
            out = fn() or {}
            out = {**out, "ms": int((time.perf_counter() - t0) * 1000)}
            self._mark(st, key, "done", out)
            for k in ("categories", "pages", "posts", "taxonomies", "media", "crawled", "graph_nodes", "graph_edges", "content_categories"):
                if k in out: st.items[k] = out[k]
        except Exception as e:  # noqa: BLE001
            msg = f"{e.__class__.__name__}: {str(e)[:200]}"
            st.errors.append(f"{key}: {msg}")
            self._mark(st, key, "failed", {"ms": int((time.perf_counter() - t0) * 1000)}, msg)
            if key in ("resolve", "categories", "build_graph"):
                raise

    def _resolve(self, site_id: str) -> dict:
        """One canonical WordPress base for sync/crawl/graph; stores the normalized value back on the site row."""
        with self.engine.connect() as cx:
            row = cx.execute(text("SELECT wp_url, canonical_url FROM sites WHERE site_id=:s"), {"s": site_id}).first()
        if not row:
            raise ValueError(f"unknown site '{site_id}'")
        raw = row[0] or row[1]
        probe = self._probe if self._probe is not None else _default_probe
        base, info = resolve_wordpress_base(raw, probe)
        if base != row[0]:
            with self.engine.begin() as cx:
                cx.execute(text("UPDATE sites SET wp_url=:u, updated_at=:t WHERE site_id=:s"), {"u": base, "t": utcnow(), "s": site_id})
        return {"wp_url": base, **info}

    def _site_config(self, site_id: str):
        site = get_site(site_id)        # config/site.yaml first (tuned crawler settings), else DB row with defaults
        with self.engine.connect() as cx:
            row = cx.execute(text("SELECT wp_url FROM sites WHERE site_id=:s"), {"s": site_id}).first()
        if row and row[0]:
            site.wp_url = row[0]
        return site

    def _wordpress_steps(self, st: PipelineState, site_id: str) -> None:
        """taxonomies / categories / pages / posts / media come from ONE read-only REST pass (sync_wordpress); the progress hook
        moves the step markers as the sync advances."""
        site = self._site_config(site_id)
        current = {"key": None}

        def progress(step: str, info: dict) -> None:
            key = {"taxonomies": "taxonomies", "categories": "categories", "pages": "pages", "posts": "posts", "media": "taxonomies"}.get(step)
            if not key or key == current["key"]:
                return
            if current["key"]:
                self._mark(st, current["key"], "done")
            current["key"] = key
            self._mark(st, key, "running")

        t0 = time.perf_counter()
        try:
            if self._wp_sync is not None:
                stats = self._wp_sync(site, progress)
            else:
                from ..database.db import db
                from .sync import sync_wordpress
                with db() as conn:
                    stats = sync_wordpress(conn, site, use_auth=True, progress=progress)
        except Exception as e:  # noqa: BLE001
            msg = f"{e.__class__.__name__}: {str(e)[:200]}"
            for k in ("categories", "pages", "posts", "taxonomies"):
                self._mark(st, k, "failed", error=msg)
            st.errors.append(f"wordpress: {msg}")
            raise
        c = self.counts(site_id)
        ms = int((time.perf_counter() - t0) * 1000)
        types = stats.get("types") or {}
        self._mark(st, "categories", "done", {"categories": c["categories"]})
        self._mark(st, "pages", "done", {"pages": types.get("page", c["pages"])})
        self._mark(st, "posts", "done", {"posts": types.get("post", c["posts"])})
        self._mark(st, "taxonomies", "done", {"taxonomies": len(stats.get("taxonomies") or {}), "media": stats.get("media", 0), "ms": ms})
        st.items.update({"categories": c["categories"], "pages": c["pages"], "posts": c["posts"], "taxonomies": c["taxonomies"], "media": stats.get("media", 0), "wp_run_id": stats.get("run_id")})
        for err in stats.get("errors") or []:
            st.errors.append(f"wordpress: {str(err)[:200]}")

    def _category_intelligence(self, site_id: str) -> dict:
        from ..brain.planner.categories import CategoryIntelligence
        ci = CategoryIntelligence(self.engine)
        try:
            out = {**ci.sync_from_local(site_id), "source": "snapshot", "status": "ok", "via": "pipeline_snapshot", "note": "از snapshot تازهٔ همین همگام‌سازی (بدون فراخوانی دوبارهٔ REST)"}
        except ValueError:
            out = {"source": "snapshot", "status": "empty", "terms": 0, "reason": "no_local_snapshot"}
        try:
            out["analysis"] = ci.analyze(site_id)
        except Exception as e:  # noqa: BLE001
            out["analysis_error"] = f"{e.__class__.__name__}: {str(e)[:120]}"
        return {"content_categories": out.get("terms", 0), **{k: v for k, v in out.items() if k != "analysis"}}

    def _crawl(self, site_id: str, max_urls: int | None) -> dict:
        site = self._site_config(site_id)
        if self._crawler_factory is not None:
            return self._crawler_factory(site, max_urls) or {}
        from ..crawler import Crawler
        from ..database.db import db
        with db() as conn:
            stats = Crawler(site, max_urls=max_urls).run(conn)
        return {"crawled": int(stats.get("ok", stats.get("crawled", 0)) or 0), **{k: v for k, v in stats.items() if isinstance(v, (int, float, str)) and k != "run_id"}}

    def _build_graph(self, site_id: str) -> dict:
        site = self._site_config(site_id)
        if self._graph_build is not None:
            out = self._graph_build(site) or {}
        else:
            from ..analysis import extract_entities, run_analysis
            from ..database.db import db
            from ..graph import GraphBuild
            out = {}
            with db() as conn:
                try:
                    out["entities"] = extract_entities(conn, site)
                    out["analysis"] = run_analysis(conn, site)
                except Exception as e:  # noqa: BLE001 — enrichment must not block the graph
                    out["analysis_error"] = f"{e.__class__.__name__}: {str(e)[:120]}"
                out["graph"] = GraphBuild(conn, site).build()
        # layers added by later phases live in graph_nodes too and GraphBuild rebuilds the site namespace → re-sync them
        syncs: dict[str, Any] = {}
        for name, fn in (("keywords", self._sync_keywords), ("content", self._sync_content), ("planner", self._sync_planner)):
            try:
                syncs[name] = fn(site_id)
            except Exception as e:  # noqa: BLE001
                syncs[name] = {"error": f"{e.__class__.__name__}: {str(e)[:120]}"}
        c = self.counts(site_id)
        g = out.get("graph") if isinstance(out.get("graph"), dict) else {}
        return {"graph_nodes": c["graph_nodes"], "graph_edges": c["graph_edges"], "by_type": c["graph_by_type"], "build": {k: g.get(k) for k in ("nodes", "edges", "run_id") if isinstance(g, dict) and k in g}, "syncs": syncs,
                "analysis_error": out.get("analysis_error")}

    def _sync_keywords(self, site_id: str) -> dict:
        from ..brain.keywords import KeywordService
        return KeywordService(self.engine).sync_graph(site_id)

    def _sync_content(self, site_id: str) -> dict:
        from ..brain.content import ContentService
        return ContentService(self.engine).sync_graph(site_id)

    def _sync_planner(self, site_id: str) -> dict:
        from ..brain.planner.graph_sync import PlannerGraphSync
        return PlannerGraphSync(self.engine).sync(site_id)


def _default_probe(url: str) -> int | None:
    import httpx
    try:
        return httpx.get(url, timeout=10, follow_redirects=True, headers={"User-Agent": "SEO-Brain/0.2 (+local; read-only)"}).status_code
    except httpx.HTTPError:
        return None
