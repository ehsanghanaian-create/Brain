"""Preserve issue identity and evidence across replaceable analysis snapshots."""
from __future__ import annotations

import sqlite3

from ..database.db import utcnow


def fingerprint(site_id: str, problem_type: str, url: str | None, related_url: str | None) -> str:
    return "\x1f".join((site_id, problem_type, url or "", related_url or ""))


def reconcile_issue_cases(conn: sqlite3.Connection, site_id: str, run_id: str, *, allow_resolve: bool) -> dict[str, int]:
    """Observe current findings. Only a complete successful crawl may close absent cases."""
    now = utcnow()
    stats = {"opened": 0, "reopened": 0, "resolved": 0, "observed": 0}
    current = conn.execute(
        "SELECT problem_type,severity,url,related_url,detail FROM seo_problems WHERE site_id=?", (site_id,)
    ).fetchall()
    for problem_type, severity, url, related_url, detail in current:
        key = fingerprint(site_id, problem_type, url, related_url)
        existing = conn.execute("SELECT id,status FROM issue_cases WHERE fingerprint=?", (key,)).fetchone()
        if existing:
            case_id, previous_status = existing
            already_seen = conn.execute("SELECT 1 FROM issue_case_observations WHERE case_id=? AND run_id=?", (case_id, run_id)).fetchone()
            if already_seen:
                continue
            conn.execute("UPDATE issue_cases SET severity=?,status='open',detail=?,last_seen=?,last_run_id=?,seen_count=seen_count+1,resolved_at=NULL WHERE id=?",
                         (severity, detail, now, run_id, case_id))
            if previous_status == "resolved":
                conn.execute("INSERT INTO issue_case_events(site_id,case_id,run_id,event_type,created_at) VALUES(?,?,?,'reopened',?)",
                             (site_id, case_id, run_id, now))
                stats["reopened"] += 1
        else:
            cursor = conn.execute(
                "INSERT INTO issue_cases(site_id,fingerprint,problem_type,url,related_url,severity,status,detail,first_seen,last_seen,last_run_id) "
                "VALUES(?,?,?,?,?,?,'open',?,?,?,?)",
                (site_id, key, problem_type, url or "", related_url or "", severity, detail, now, now, run_id),
            )
            case_id = cursor.lastrowid
            conn.execute("INSERT INTO issue_case_events(site_id,case_id,run_id,event_type,created_at) VALUES(?,?,?,'opened',?)",
                         (site_id, case_id, run_id, now))
            stats["opened"] += 1
        conn.execute("INSERT INTO issue_case_observations(site_id,case_id,run_id,severity,detail,observed_at) VALUES(?,?,?,?,?,?)",
                     (site_id, case_id, run_id, severity, detail, now))
        stats["observed"] += 1
    if allow_resolve:
        absent = conn.execute("SELECT id FROM issue_cases WHERE site_id=? AND status='open' AND COALESCE(last_run_id,'')<>?", (site_id, run_id)).fetchall()
        for (case_id,) in absent:
            conn.execute("UPDATE issue_cases SET status='resolved',resolved_at=? WHERE id=?", (now, case_id))
            conn.execute("INSERT INTO issue_case_events(site_id,case_id,run_id,event_type,created_at) VALUES(?,?,?,'resolved',?)",
                         (site_id, case_id, run_id, now))
        stats["resolved"] = len(absent)
    return stats
