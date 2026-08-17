"""Database migrations.
    python backend/cli/migrate.py            # apply pending
    python backend/cli/migrate.py --status   # show versions
"""
import _bootstrap  # noqa: F401
import argparse
import json

from seo_brain.common.logging_setup import setup_logging
from seo_brain.db.engine import get_engine
from seo_brain.db.migrate import migrate, status


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    setup_logging("migrate")
    eng = get_engine()
    if a.status:
        print(json.dumps(status(eng), indent=1))
        return 0
    applied = migrate(eng)
    print(json.dumps({"applied_now": applied, "status": status(eng)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
