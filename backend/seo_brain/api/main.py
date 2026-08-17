"""SEO Brain API (FastAPI).

    uvicorn seo_brain.api.main:app --host 127.0.0.1 --port 8000      (or: python backend/cli/api.py)

* versioned under /api/v1, OpenAPI at /api/docs (the frontend TS client is generated from /api/openapi.json)
* the v0.1 Jinja dashboard stays available at /legacy until the Next.js UI reaches parity
* CORS is restricted to the local frontend origin; both servers bind 127.0.0.1 in local mode
"""
from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..automation import get_job_queue
from ..common.config import env
from .deps import require_token
from .errors import install_error_handlers
from .routers import ai, graph, health, jobs, memory, sites

API_PREFIX = "/api/v1"


def _register_builtin_jobs() -> None:
    """Phase 1 job handlers: the existing sync/build entry points, callable from the UI/API."""
    q = get_job_queue()

    def _run_sync_wordpress(payload: dict):
        from ..common.config import get_site
        from ..database.db import db
        from ..wordpress import sync_wordpress
        with db() as conn:
            return sync_wordpress(conn, get_site(payload["site_id"]), use_auth=payload.get("use_auth", True))

    def _run_build_graph(payload: dict):
        from ..analysis import extract_entities, run_analysis
        from ..common.config import get_site, vault_path
        from ..database.db import db
        from ..graph import GraphBuild, ObsidianWriter
        site = get_site(payload["site_id"])
        out: dict = {}
        with db() as conn:
            if not payload.get("skip_analysis"):
                out["entities"] = extract_entities(conn, site)
                out["analysis"] = run_analysis(conn, site)
            out["graph"] = GraphBuild(conn, site).build(limit_pages=payload.get("limit_pages"))
            if not payload.get("no_obsidian"):
                out["obsidian"] = ObsidianWriter(conn, site, vault_path()).write()
        return out

    def _noop(payload: dict):
        return {"echo": payload}

    for name, fn in (("sync_wordpress", _run_sync_wordpress), ("build_graph", _run_build_graph), ("noop", _noop)):
        try:
            q.register(name, fn)
        except Exception:  # noqa: BLE001
            pass


def create_app() -> FastAPI:
    app = FastAPI(title="SEO Brain API", version="0.2.0", docs_url="/api/docs", redoc_url=None,
                  openapi_url="/api/openapi.json")
    origins = [o.strip() for o in (env("FRONTEND_ORIGIN", "http://localhost:3000,http://127.0.0.1:3000") or "").split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"])
    install_error_handlers(app)

    deps = [Depends(require_token)]
    app.include_router(health.router, prefix=API_PREFIX)
    for r in (sites.router, sites.gsc_router, graph.router, memory.router, ai.router, jobs.router):
        app.include_router(r, prefix=API_PREFIX, dependencies=deps)

    # legacy dashboard (v0.1) mounted read-only until UI parity
    try:
        from ..dashboard.app import app as legacy_app
        app.mount("/legacy", legacy_app)
    except Exception:  # noqa: BLE001  (dashboard is optional)
        pass

    _register_builtin_jobs()

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"name": "SEO Brain API", "docs": "/api/docs", "api": API_PREFIX, "legacy_dashboard": "/legacy"}

    return app


app = create_app()
