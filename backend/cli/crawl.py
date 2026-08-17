"""Run the read-only crawler.

    python scripts/crawl.py --site emdadmodiran --max-urls 20
    python scripts/crawl.py --site emdadmodiran --full          # uses no cap beyond a safety ceiling
"""
import _bootstrap  # noqa: F401
import argparse
import json

from seo_brain.common.config import get_site
from seo_brain.common.logging_setup import setup_logging
from seo_brain.crawler import Crawler
from seo_brain.database.db import db

SAFETY_CEILING = 5000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=None)
    ap.add_argument("--max-urls", type=int, default=None, help="override config cap")
    ap.add_argument("--full", action="store_true", help=f"crawl everything discoverable (safety ceiling {SAFETY_CEILING})")
    a = ap.parse_args()
    log = setup_logging("crawl")
    site = get_site(a.site)
    cap = SAFETY_CEILING if a.full else (a.max_urls or site.crawler.max_urls)
    log.info(f"site={site.site_id} cap={cap} concurrency={site.crawler.concurrency} delay={site.crawler.delay_seconds}s")
    with db() as conn:
        stats = Crawler(site, max_urls=cap).run(conn)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0 if stats["crawled"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
