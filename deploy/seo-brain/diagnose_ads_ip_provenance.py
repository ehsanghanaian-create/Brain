#!/usr/bin/env python3
"""Read-only provenance audit for the live Ads collector SQLite database.

The report intentionally omits raw IP addresses and browser identifiers. It is
safe to archive with project diagnostics and never changes the database.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def token(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(("ads-ip-audit:" + value).encode()).hexdigest()[:16]


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def classify_ads(row: sqlite3.Row) -> str:
    if row["gclid"] or row["gbraid"] or row["wbraid"]:
        return "google_ads_click_id"
    medium = (row["utm_medium"] or "").lower()
    source = (row["utm_source"] or "").lower()
    if medium in {"cpc", "ppc", "paid", "paidsearch", "paid_search"}:
        return "paid_utm"
    if row["campaign_id"] or row["ad_group_id"] or row["creative_id"]:
        return "valuetrack_ids"
    if source in {"google", "googleads", "google_ads"} and medium:
        return "google_utm_unconfirmed"
    return "unattributed"


def scalar(db: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return db.execute(sql, params).fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--site", default="modirankhodro-emdad.com")
    parser.add_argument("--hours", type=int, default=72)
    parser.add_argument("--probe-campaign")
    args = parser.parse_args()

    db = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    cutoff = iso_utc(datetime.now(timezone.utc) - timedelta(hours=max(args.hours, 1)))
    rows = db.execute(
        """SELECT * FROM ads_click_events
           WHERE site_id=? AND received_at>=?
           ORDER BY received_at""",
        (args.site, cutoff),
    ).fetchall()

    source_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    attribution: Counter[str] = Counter()
    invalid_ip_rows = 0
    zero_ip_rows = 0
    hourly: dict[str, dict[str, Any]] = {}
    ip_activity: dict[str, dict[str, Any]] = {}
    identity_columns = {
        "visitor": "visitor_id",
        "session": "session_id",
        "gclid": "gclid",
        "gbraid": "gbraid",
        "wbraid": "wbraid",
    }
    identities: dict[str, dict[str, set[str]]] = {key: {} for key in identity_columns}

    for row in rows:
        source_counts[row["ip_source"] or "missing"] += 1
        attribution[classify_ads(row)] += 1
        try:
            parsed = ipaddress.ip_address(row["ip_address"])
            family_counts[f"ipv{parsed.version}"] += 1
            if parsed.is_unspecified:
                zero_ip_rows += 1
        except ValueError:
            family_counts["invalid"] += 1
            invalid_ip_rows += 1

        hour = row["received_at"][:13] + ":00:00Z"
        bucket = hourly.setdefault(hour, {"events": 0, "ips": set(), "sessions": set(), "landings": 0})
        bucket["events"] += 1
        bucket["ips"].add(row["ip_hash"])
        if row["session_id"]:
            bucket["sessions"].add(row["session_id"])
        bucket["landings"] += int(row["event_type"] == "landing")

        ip_key = row["ip_hash"][:16]
        ip_row = ip_activity.setdefault(ip_key, {"events": 0, "landings": 0, "sessions": set(), "visitors": set(), "sources": set()})
        ip_row["events"] += 1
        ip_row["landings"] += int(row["event_type"] == "landing")
        if row["session_id"]:
            ip_row["sessions"].add(row["session_id"])
        if row["visitor_id"]:
            ip_row["visitors"].add(row["visitor_id"])
        ip_row["sources"].add(row["ip_source"] or "missing")

        for field, column in identity_columns.items():
            value = row[column]
            if value:
                identities[field].setdefault(value, set()).add(row["ip_hash"])

    hourly_rows = [
        {"hour_utc": key, "events": value["events"], "unique_ips": len(value["ips"]),
         "sessions": len(value["sessions"]), "landings": value["landings"]}
        for key, value in sorted(hourly.items())
    ]
    top_ips = sorted(ip_activity.items(), key=lambda item: (-item[1]["events"], item[0]))[:25]
    rotation: dict[str, list[dict[str, Any]]] = {}
    for field, values in identities.items():
        candidates = [(value, ips) for value, ips in values.items() if len(ips) > 1]
        candidates.sort(key=lambda item: (-len(item[1]), token(item[0]) or ""))
        rotation[field] = [
            {"identifier_token": token(value), "distinct_ips": len(ips)}
            for value, ips in candidates[:25]
        ]

    probe: dict[str, Any] | None = None
    if args.probe_campaign:
        probe_rows = db.execute(
            """SELECT received_at, ip_hash, ip_source, ip_address, session_id, visitor_id, metadata_json,
                      proxy_ip, ip_confidence, ip_resolution_version
               FROM ads_click_events WHERE site_id=? AND utm_campaign=?
               ORDER BY received_at DESC""",
            (args.site, args.probe_campaign),
        ).fetchall()
        echo_hashes = set()
        for row in probe_rows:
            try:
                value = json.loads(row["metadata_json"] or "{}").get("client_echo_sha256")
                if value:
                    echo_hashes.add(value)
            except (ValueError, TypeError):
                pass
        stored_hashes = {hashlib.sha256(row["ip_address"].encode()).hexdigest() for row in probe_rows}
        probe = {
            "campaign": args.probe_campaign,
            "events": len(probe_rows),
            "distinct_ips": len({row["ip_hash"] for row in probe_rows}),
            "ip_tokens": sorted({row["ip_hash"][:16] for row in probe_rows}),
            "ip_families": sorted({f"ipv{ipaddress.ip_address(row['ip_address']).version}" for row in probe_rows}),
            "sources": sorted({row["ip_source"] or "missing" for row in probe_rows}),
            "confidence": sorted({row["ip_confidence"] or "missing" for row in probe_rows}),
            "resolution_versions": sorted({row["ip_resolution_version"] or "missing" for row in probe_rows}),
            "has_separate_proxy_ip": any(row["proxy_ip"] and row["proxy_ip"] != row["ip_address"] for row in probe_rows),
            "public_echo_matches_stored_ip": bool(echo_hashes and echo_hashes == stored_hashes),
            "first_seen": probe_rows[-1]["received_at"] if probe_rows else None,
            "last_seen": probe_rows[0]["received_at"] if probe_rows else None,
        }

    report = {
        "generated_at": iso_utc(datetime.now(timezone.utc)),
        "database": str(args.database),
        "site": args.site,
        "window_hours": args.hours,
        "cutoff_utc": cutoff,
        "database_quick_check": scalar(db, "PRAGMA quick_check"),
        "totals": {
            "events_in_window": len(rows),
            "all_time_events": scalar(db, "SELECT COUNT(*) FROM ads_click_events WHERE site_id=?", (args.site,)),
            "unique_ips_in_window": len({row["ip_hash"] for row in rows}),
            "invalid_ip_rows": invalid_ip_rows,
            "unspecified_ip_rows": zero_ip_rows,
        },
        "ip_source_counts": dict(source_counts),
        "ip_family_counts": dict(family_counts),
        "ads_attribution_evidence": dict(attribution),
        "hourly": hourly_rows,
        "top_ip_activity_masked": [
            {"ip_token": key, "events": value["events"], "landings": value["landings"],
             "sessions": len(value["sessions"]), "visitors": len(value["visitors"]),
             "sources": sorted(value["sources"])}
            for key, value in top_ips
        ],
        "identity_ip_rotation": rotation,
        "probe": probe,
        "limitations": [
            "Collector events are site requests/behaviour events, not Google Ads billed-click records.",
            "An IP identifies a network egress point, not a person or device.",
            "Raw IP addresses and raw browser identifiers are intentionally omitted from this report.",
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
