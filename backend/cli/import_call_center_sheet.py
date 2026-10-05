"""Preview or import a private Google Sheets XLSX export into the local DB.

The workbook must remain outside Git. Default mode is read-only dry-run.
"""
import _bootstrap  # noqa: F401
import argparse
import json
import sys
from pathlib import Path

from seo_brain.call_center.sheet_import import import_workbook
from seo_brain.db.engine import get_engine
from seo_brain.db.migrate import migrate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--site-id")
    args = parser.parse_args()
    eng = get_engine()
    migrate(eng)
    result = import_workbook(args.workbook.read_bytes(), eng, apply=args.apply, site_id=args.site_id)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
