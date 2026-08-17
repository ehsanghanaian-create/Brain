"""Run the SEO Brain API (FastAPI) on loopback.
    python backend/cli/api.py                 # http://127.0.0.1:8000  (docs: /api/docs, legacy dashboard: /legacy)
    python backend/cli/api.py --port 8010 --reload
"""
import _bootstrap  # noqa: F401
import argparse

import uvicorn

from seo_brain.common.logging_setup import setup_logging


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true")
    a = ap.parse_args()
    setup_logging("api")
    uvicorn.run("seo_brain.api.main:app", host=a.host, port=a.port, reload=a.reload, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
