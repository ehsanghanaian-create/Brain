#!/usr/bin/env python3
"""Copy Ads telemetry into its own SQLite database without deleting source rows."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


EXTRA_COLUMNS = {
    "proxy_ip": "TEXT",
    "ip_confidence": "TEXT NOT NULL DEFAULT 'legacy_unverified'",
    "ip_resolution_version": "TEXT NOT NULL DEFAULT '1'",
}


def columns(db: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in db.execute(f"PRAGMA table_info({table})")]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--schema", type=Path, required=True)
    args = parser.parse_args()

    source = sqlite3.connect(f"file:{args.source}?mode=ro", uri=True, timeout=30)
    source.execute("PRAGMA query_only=ON")
    target = sqlite3.connect(args.target, timeout=30)
    target.execute("PRAGMA journal_mode=WAL")
    target.execute("PRAGMA busy_timeout=30000")
    target.executescript(args.schema.read_text(encoding="utf-8"))
    existing = set(columns(target, "ads_click_events"))
    for name, definition in EXTRA_COLUMNS.items():
        if name not in existing:
            target.execute(f"ALTER TABLE ads_click_events ADD COLUMN {name} {definition}")

    source_columns = columns(source, "ads_click_events")
    if not source_columns:
        raise SystemExit("source database does not contain ads_click_events")
    shared = [name for name in source_columns if name in set(columns(target, "ads_click_events"))]
    placeholders = ",".join("?" for _ in shared)
    names = ",".join(shared)
    before = target.execute("SELECT COUNT(*) FROM ads_click_events").fetchone()[0]
    cursor = source.execute(f"SELECT {names} FROM ads_click_events ORDER BY id")
    while batch := cursor.fetchmany(1000):
        target.executemany(f"INSERT OR IGNORE INTO ads_click_events ({names}) VALUES ({placeholders})", batch)
    target.execute(
        "UPDATE ads_click_events SET ip_confidence='legacy_unverified', ip_resolution_version='1' "
        "WHERE ip_confidence IS NULL OR ip_confidence=''"
    )
    target.commit()
    after = target.execute("SELECT COUNT(*) FROM ads_click_events").fetchone()[0]
    quick = target.execute("PRAGMA quick_check").fetchone()[0]
    print({"source_rows": source.execute("SELECT COUNT(*) FROM ads_click_events").fetchone()[0],
           "target_before": before, "target_after": after, "quick_check": quick})


if __name__ == "__main__":
    main()
