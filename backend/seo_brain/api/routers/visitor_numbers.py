"""Persistent, site-scoped display numbers for anonymous Ads visitors.

The dashboard's old three-digit hash could collide and did not convey order.
Numbers here follow the first accepted event ID. Only a SHA-256 digest of the
existing visitor/session/IP fallback key is stored; inactive mappings expire
with the telemetry retention window, while the next number never goes back.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping

from sqlalchemy import Engine, text


def visitor_identity(row: Mapping[str, Any]) -> str:
    return (
        row.get("visitor_id") or row.get("session_id")
        or row.get("ip_address") or row.get("ip_prefix")
        or f"event-{row['id']}"
    )


def visitor_identity_hash(row: Mapping[str, Any]) -> str:
    return hashlib.sha256(visitor_identity(row).encode("utf-8")).hexdigest()


def visitor_numbers(engine: Engine, site_id: str, retention_cutoff: str) -> dict[str, int]:
    """Catch up imported and live events, then return digest -> stable number.

    SQLite's immediate transaction serializes allocations from simultaneous
    dashboard requests. The cursor avoids rescanning old events on every poll.
    """
    with engine.connect() as cx:
        cx.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            cx.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS ads_visitor_numbers (
                    site_id TEXT NOT NULL,
                    identity_hash TEXT NOT NULL,
                    visitor_number INTEGER NOT NULL,
                    first_event_id INTEGER NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY (site_id, identity_hash),
                    UNIQUE (site_id, visitor_number)
                )
            """)
            cx.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS ads_visitor_number_state (
                    site_id TEXT PRIMARY KEY,
                    next_number INTEGER NOT NULL,
                    last_event_id INTEGER NOT NULL
                )
            """)
            cx.execute(text("DELETE FROM ads_visitor_numbers WHERE site_id=:site_id AND last_seen_at<:cutoff"),
                       {"site_id": site_id, "cutoff": retention_cutoff})
            state = cx.execute(text("""
                SELECT next_number, last_event_id FROM ads_visitor_number_state WHERE site_id=:site_id
            """), {"site_id": site_id}).first()
            next_number, last_event_id = (int(state[0]), int(state[1])) if state else (1, 0)
            stored = {
                row["identity_hash"]: [int(row["visitor_number"]), row["last_seen_at"]]
                for row in cx.execute(text("""
                    SELECT identity_hash, visitor_number, last_seen_at
                    FROM ads_visitor_numbers WHERE site_id=:site_id
                """), {"site_id": site_id}).mappings()
            }
            new_rows = cx.execute(text("""
                SELECT id, visitor_id, session_id, ip_address, ip_prefix, received_at
                FROM ads_click_events
                WHERE site_id=:site_id AND id>:last_event_id
                ORDER BY id
            """), {"site_id": site_id, "last_event_id": last_event_id}).mappings().all()
            changed_last_seen: dict[str, str] = {}
            for row in new_rows:
                last_event_id = int(row["id"])
                seen_at = row["received_at"]
                if seen_at < retention_cutoff:
                    continue
                digest = visitor_identity_hash(row)
                current = stored.get(digest)
                if current is None:
                    cx.execute(text("""
                        INSERT INTO ads_visitor_numbers
                        (site_id, identity_hash, visitor_number, first_event_id, last_seen_at)
                        VALUES (:site_id, :digest, :number, :event_id, :seen_at)
                    """), {"site_id": site_id, "digest": digest, "number": next_number,
                           "event_id": last_event_id, "seen_at": seen_at})
                    stored[digest] = [next_number, seen_at]
                    next_number += 1
                elif seen_at > current[1]:
                    current[1] = seen_at
                    changed_last_seen[digest] = seen_at
            for digest, seen_at in changed_last_seen.items():
                cx.execute(text("""
                    UPDATE ads_visitor_numbers SET last_seen_at=:seen_at
                    WHERE site_id=:site_id AND identity_hash=:digest
                """), {"site_id": site_id, "digest": digest, "seen_at": seen_at})
            cx.execute(text("""
                INSERT INTO ads_visitor_number_state(site_id, next_number, last_event_id)
                VALUES (:site_id, :next_number, :last_event_id)
                ON CONFLICT(site_id) DO UPDATE SET
                    next_number=excluded.next_number, last_event_id=excluded.last_event_id
            """), {"site_id": site_id, "next_number": next_number, "last_event_id": last_event_id})
            cx.commit()
            return {digest: data[0] for digest, data in stored.items()}
        except Exception:
            cx.rollback()
            raise
