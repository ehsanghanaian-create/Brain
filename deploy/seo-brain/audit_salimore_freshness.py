"""Read-only SEO data freshness inventory for the Salimore instance."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    args = parser.parse_args()
    database = args.db.resolve(strict=True)
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")

    def scalar(sql: str):
        return connection.execute(sql).fetchone()[0]

    result = {
        "integrity": scalar("PRAGMA quick_check"),
        "sites": [dict(row) for row in connection.execute("SELECT site_id,name FROM sites ORDER BY site_id")],
        "sources": {},
        "inventory": {},
        "problem_types": {},
        "sync_runs": {},
    }
    for source, table in (("gsc", "gsc_daily"), ("ga4", "ga4_daily")):
        row = connection.execute(
            f"SELECT COUNT(*) rows,COUNT(DISTINCT date) days,MIN(date) first_date,MAX(date) last_date "
            f"FROM {table} WHERE site_id='salimore'"
        ).fetchone()
        item = dict(row)
        item["days_behind_today"] = (date.today() - date.fromisoformat(item["last_date"])).days if item["last_date"] else None
        result["sources"][source] = item
    for table in ("pages", "posts", "content_plans", "gsc_query_page", "seo_problems", "seo_opportunities"):
        result["inventory"][table] = scalar(f"SELECT COUNT(*) FROM {table} WHERE site_id='salimore'")
    result["problem_types"] = {
        row["problem_type"]: row["count"] for row in connection.execute(
            "SELECT problem_type,COUNT(*) count FROM seo_problems WHERE site_id='salimore' GROUP BY problem_type"
        )
    }
    result["crawl"] = dict(connection.execute(
        "SELECT COUNT(*) rows,MIN(last_crawled) first_crawl,MAX(last_crawled) last_crawl,"
        "SUM(CASE WHEN in_sitemap=1 THEN 1 ELSE 0 END) sitemap_rows,"
        "SUM(CASE WHEN redirect_chain IS NOT NULL AND redirect_chain!='[]' THEN 1 ELSE 0 END) redirect_rows "
        "FROM pages WHERE site_id='salimore'"
    ).fetchone())
    result["redirect_examples"] = [
        dict(row) for row in connection.execute(
            "SELECT p.url,p.final_url,p.status_code,p.redirect_chain,p.last_crawled FROM pages p "
            "JOIN seo_problems i ON i.site_id=p.site_id AND i.url=p.url "
            "WHERE i.site_id='salimore' AND i.problem_type='redirect_in_sitemap' ORDER BY p.url LIMIT 5"
        )
    ]
    result["url_examples"] = {
        table: [row[0] for row in connection.execute(
            f"SELECT {column} FROM {table} WHERE site_id='salimore' AND {column} LIKE 'https://salimore.com/blog/%' LIMIT 3"
        )] for table, column in (("posts", "url"), ("pages", "url"), ("gsc_daily", "page"))
    }
    result["post_url_examples"] = [row[0] for row in connection.execute(
        "SELECT url FROM posts WHERE site_id='salimore' LIMIT 5"
    )]
    for source in ("crawl", "wordpress", "gsc", "ga4", "analysis", "graph"):
        result["sync_runs"][source] = [
            dict(row) for row in connection.execute(
                "SELECT run_id,status,started_at,finished_at,rows_written FROM sync_runs "
                "WHERE site_id='salimore' AND source=? ORDER BY started_at DESC LIMIT 3", (source,)
            )
        ]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
