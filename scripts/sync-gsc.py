"""Sync Google Search Console data into SQLite (cached; Claude never hits GSC directly).

    python scripts/sync-gsc.py --auth-only              # one-time browser consent, stores refresh token
    python scripts/sync-gsc.py --list-sites             # show properties visible to the account
    python scripts/sync-gsc.py --days 1                 # first validation sync
    python scripts/sync-gsc.py --days 30                # after validation (lookback configurable)
    python scripts/sync-gsc.py --start 2026-07-01 --end 2026-07-31
"""
import _bootstrap  # noqa: F401
import argparse
import json
from datetime import date

from src.common.config import get_site
from src.common.logging_setup import setup_logging
from src.database.db import db
from src.gsc import GscAuthError, GscClient, date_window, sync_gsc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=None)
    ap.add_argument("--days", type=int, default=None, help="lookback days (default: config gsc.lookback_days)")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--auth-only", action="store_true")
    ap.add_argument("--list-sites", action="store_true")
    ap.add_argument("--non-interactive", action="store_true", help="fail instead of opening a browser")
    a = ap.parse_args()
    log = setup_logging("sync-gsc")
    site = get_site(a.site)
    try:
        if a.auth_only or a.list_sites:
            client = GscClient(site.site_id, interactive=not a.non_interactive)
            if a.list_sites:
                for s in client.list_sites():
                    print(f"{s.get('siteUrl'):45s} {s.get('permissionLevel')}")
            else:
                print("GSC authorization OK; token cached.")
            return 0
        if a.start and a.end:
            start, end = date.fromisoformat(a.start), date.fromisoformat(a.end)
        else:
            start, end = date_window(a.days or site.gsc.lookback_days)
        log.info(f"GSC sync {site.site_id} {start}..{end} dims={site.gsc.dimensions}")
        with db() as conn:
            stats = sync_gsc(conn, site, start, end, interactive=not a.non_interactive)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0
    except GscAuthError as e:
        log.error(f"BLOCKED: {e}")
        print(f"BLOCKED: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
