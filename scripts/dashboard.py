"""Run the local dashboard on http://127.0.0.1:3000/ (localhost only).

    python scripts/dashboard.py [--port 3000]
"""
import _bootstrap  # noqa: F401
import argparse

import uvicorn


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=3000)
    ap.add_argument("--host", default="127.0.0.1", help="keep 127.0.0.1 (local-first)")
    a = ap.parse_args()
    uvicorn.run("src.dashboard.app:app", host=a.host, port=a.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
