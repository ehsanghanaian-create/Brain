"""Automatically block repeated paid-ad visitors through the WordPress security API.

Only website-origin entries can establish the client IP. Legacy behavioral events
may contribute phone clicks only when their GCLID maps to exactly one origin IP.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime
from pathlib import Path

SITE = "modirankhodro-emdad.com"
GCLID = re.compile(r"[A-Za-z0-9_-]{20,256}\Z")
TEST_GCLID = re.compile(r"(?:test|fake|synthetic|qa|health|diagnostic)", re.I)
QA = re.compile(r"(?:^|[^a-z])(qa|test|synthetic|diagnostic|healthcheck)(?:$|[^a-z])", re.I)


def parse_time(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.timestamp()


def allowed_ip(raw: str, protected_ips=(), protected_ranges=()) -> str | None:
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return None
    if not ip.is_global or str(ip) in protected_ips:
        return None
    if any(ip in ipaddress.ip_network(net, strict=False) for net in protected_ranges):
        return None
    return str(ip)


def collect_candidates(config: dict, now: float) -> list[dict]:
    cutoff = now - int(config.get("window_seconds", 86400))
    click_ips: dict[str, set[str]] = {}
    origin_entries: dict[str, list[tuple[str, float]]] = {}
    with closing(sqlite3.connect(f"file:{config['entry_source_db']}?mode=ro", uri=True)) as db:
        for gclid, ip, received, campaign in db.execute(
            "SELECT gclid,ip_address,received_at,COALESCE(utm_campaign,'') "
            "FROM ads_click_events WHERE site_id=? AND received_at<=?", (SITE, now)
        ):
            if (not isinstance(gclid, str) or not GCLID.fullmatch(gclid)
                    or TEST_GCLID.match(gclid) or QA.search(campaign or "")):
                continue
            normalized = allowed_ip(ip, set(config.get("protected_ips", ())), config.get("protected_ranges", ()))
            if normalized:
                click_ips.setdefault(gclid, set()).add(normalized)
                origin_entries.setdefault(gclid, []).append((normalized, float(received)))

    unique = {click: next(iter(ips)) for click, ips in click_ips.items() if len(ips) == 1}
    recent_unique = {click: ip for click, ip in unique.items()
                     if any(cutoff <= received <= now for _, received in origin_entries[click])}
    entries: dict[str, set[str]] = {}
    for click, ip in recent_unique.items():
        entries.setdefault(ip, set()).add(click)

    phones: dict[str, set[str]] = {}
    visitor_entries: dict[str, dict[str, tuple[str, float]]] = {}
    with closing(sqlite3.connect(f"file:{config['ads_source_db']}?mode=ro", uri=True)) as db:
        for visitor_id, gclid, received, metadata in db.execute(
            "SELECT visitor_id,gclid,received_at,metadata_json FROM ads_click_events "
            "WHERE site_id=? AND event_type='landing' AND visitor_id IS NOT NULL "
            "AND gclid IS NOT NULL", (SITE,)
        ):
            if not visitor_id or gclid not in unique:
                continue
            try:
                meta = json.loads(metadata or "{}")
                event_time = parse_time(received)
            except (ValueError, TypeError):
                continue
            if not isinstance(meta, dict) or meta.get("signal") != "fresh_ads_entry" or meta.get("navigation_type") != "navigate":
                continue
            if not any(ip == unique[gclid] and abs(event_time - origin_time) <= 120
                       for ip, origin_time in origin_entries[gclid]):
                continue
            previous = visitor_entries.setdefault(visitor_id, {}).get(gclid)
            if previous is None or event_time > previous[1]:
                visitor_entries[visitor_id][gclid] = (unique[gclid], event_time)
        fresh_sessions = {
            (session_id, gclid)
            for session_id, gclid, received, metadata in db.execute(
                "SELECT session_id,gclid,received_at,metadata_json FROM ads_click_events "
                "WHERE site_id=? AND event_type='landing' AND gclid IS NOT NULL", (SITE,)
            )
            if session_id and gclid in recent_unique and cutoff <= parse_time(received) <= now
            and json.loads(metadata or "{}").get("signal") == "fresh_ads_entry"
        }
        for event_uuid, gclid, session_id, received, source, medium, campaign in db.execute(
            "SELECT event_uuid,gclid,session_id,received_at,COALESCE(utm_source,''),"
            "COALESCE(utm_medium,''),COALESCE(utm_campaign,'') FROM ads_click_events "
            "WHERE site_id=? AND event_type='tel_click' AND gclid IS NOT NULL", (SITE,)
        ):
            ip = recent_unique.get(gclid)
            event_time = parse_time(received)
            if (not ip or (session_id, gclid) not in fresh_sessions
                    or not cutoff <= event_time <= now
                    or source.lower() != "google" or medium.lower() != "cpc"
                    or QA.search(campaign or "")):
                continue
            phones.setdefault(ip, set()).add(event_uuid)

    minimum = int(config.get("minimum_count", 3))
    repeat_ips: dict[str, set[str]] = {}
    rule_start = config.get("visitor_rule_start")
    if rule_start is not None:
        for clicks in visitor_entries.values():
            if len(clicks) < 2:
                continue
            ordered = sorted(clicks.items(), key=lambda item: item[1][1])
            _, (latest_ip, latest_time) = ordered[-1]
            if latest_time >= float(rule_start):
                repeat_ips.setdefault(latest_ip, set()).update(click for click, _ in ordered)
    candidates = []
    for ip in sorted(set(entries) | set(phones) | set(repeat_ips)):
        clicks, calls = entries.get(ip, set()), phones.get(ip, set())
        if len(clicks) < minimum and len(calls) < minimum and ip not in repeat_ips:
            continue
        evidence = json.dumps({"gclids": sorted(clicks), "tel_events": sorted(calls),
                               "repeat_visitor_gclids": sorted(repeat_ips.get(ip, ()))}, separators=(",", ":"))
        candidates.append({
            "ip": ip, "ads_entries": len(clicks), "ads_tel_clicks": len(calls),
            "repeat_visitor": ip in repeat_ips,
            "evidence_hash": hashlib.sha256(evidence.encode()).hexdigest(),
        })
    return candidates


def setup(path: str) -> None:
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
          CREATE TABLE IF NOT EXISTS automatic_blocks(
            ip TEXT PRIMARY KEY, evidence_hash TEXT NOT NULL, ads_entries INTEGER NOT NULL,
            ads_tel_clicks INTEGER NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL,
            created REAL NOT NULL, updated REAL NOT NULL, last_error TEXT);
          CREATE TABLE IF NOT EXISTS audit(
            id INTEGER PRIMARY KEY, at REAL NOT NULL, ip TEXT NOT NULL,
            action TEXT NOT NULL, detail TEXT NOT NULL);
        """)


def request_block(config: dict, candidate: dict, opener=urllib.request.urlopen) -> dict:
    token = os.environ.get(config.get("api_token_env", "SEO_BRAIN_API_TOKEN"), "")
    if not token:
        raise RuntimeError("api token unavailable")
    base = config["api_url"].rstrip("/")
    site_id = config["wordpress_site_id"]
    reason = (
        f"Auto Ads rule: repeat visitor after second distinct paid entry; "
        f"{candidate['ads_entries']} IP entries / {candidate['ads_tel_clicks']} phone clicks in 24h"
        if candidate.get("repeat_visitor") else
        f"Auto Ads rule: {candidate['ads_entries']} fresh entries / "
        f"{candidate['ads_tel_clicks']} phone clicks in 24h"
    )
    body = json.dumps({"ip": candidate["ip"], "reason": reason}).encode()
    req = urllib.request.Request(
        f"{base}/sites/{site_id}/security/block", data=body, method="POST",
        headers={"Content-Type": "application/json", "X-API-Token": token},
    )
    with opener(req, timeout=15) as response:
        result = json.loads(response.read(65536))
    if result.get("success") is not True or result.get("ip") != candidate["ip"]:
        raise RuntimeError("WordPress security API rejected block")
    return result


def iteration(config: dict, now: float | None = None, block=request_block) -> list[tuple[str, str]]:
    now = time.time() if now is None else now
    state = config["state_db"]
    setup(state)
    errors = []
    for candidate in collect_candidates(config, now):
        with closing(sqlite3.connect(state)) as db:
            row = db.execute("SELECT status,evidence_hash,attempts,updated FROM automatic_blocks WHERE ip=?",
                             (candidate["ip"],)).fetchone()
        if row and row[0] == "blocked":
            continue
        if row and now - row[3] < min(300, 2 ** min(row[2], 8)):
            continue
        try:
            result = block(config, candidate)
            status, error = "blocked", None
            detail = json.dumps({**candidate, "wordpress_status": result.get("status")}, separators=(",", ":"))
        except Exception as exc:  # retry is durable; do not leak response bodies/secrets
            status, error = "retry", type(exc).__name__
            detail = json.dumps({**candidate, "error": error}, separators=(",", ":"))
            errors.append((candidate["ip"], error))
            logging.error("automatic Ads block failed ip=%s error=%s", candidate["ip"], error)
        with closing(sqlite3.connect(state)) as db:
            db.execute("BEGIN IMMEDIATE")
            attempts = (row[2] if row else 0) + 1
            db.execute(
                "INSERT INTO automatic_blocks VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(ip) DO UPDATE SET evidence_hash=excluded.evidence_hash,"
                "ads_entries=excluded.ads_entries,ads_tel_clicks=excluded.ads_tel_clicks,"
                "status=excluded.status,attempts=excluded.attempts,updated=excluded.updated,last_error=excluded.last_error",
                (candidate["ip"], candidate["evidence_hash"], candidate["ads_entries"],
                 candidate["ads_tel_clicks"], status, attempts, now, now, error),
            )
            db.execute("INSERT INTO audit(at,ip,action,detail) VALUES(?,?,?,?)",
                       (now, candidate["ip"], status, detail))
            db.commit()
    return errors


def run(config_path: str) -> None:
    while True:
        try:
            iteration(json.loads(Path(config_path).read_text()))
        except Exception:
            logging.exception("automatic Ads threshold iteration failed")
        time.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(os.environ.get("ADS_THRESHOLD_CONFIG", "/etc/ead-access/threshold.json"))
