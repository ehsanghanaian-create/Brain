"""Sync WordPress content (read-only) into SQLite.

    python scripts/sync-wordpress.py --site emdadmodiran [--no-auth]
"""
import _bootstrap  # noqa: F401
import argparse
import json

from seo_brain.common.config import get_site
from seo_brain.common.logging_setup import setup_logging
from seo_brain.database.db import db
from seo_brain.wordpress import sync_wordpress


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=None)
    ap.add_argument("--no-auth", action="store_true", help="ignore WP_USERNAME/WP_APP_PASSWORD even if set")
    a = ap.parse_args()
    setup_logging("sync-wordpress")
    site = get_site(a.site)
    with db() as conn:
        stats = sync_wordpress(conn, site, use_auth=not a.no_auth)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0 if stats["posts"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
