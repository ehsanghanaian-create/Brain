"""Ingestion-triggered, persistent Ads guard. Detection-only release: no Ads mutations.

Client-supplied identifiers are evidence, not authenticated Google click receipts.
This module never interprets an IP, VPN, second click, or missing call as fraud.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

LOG = logging.getLogger(__name__)
VERSION = "20260910-detection-v1"
LAST_ERROR = None
CONFIG = "/app/config/ads-guard.json"
DATABASE = "/app/runtime-db/ads-guard.db"
SCOPES = {
    ("modirankhodro-emdad.com", "/emdad-modiran-khodro/", "{modirankhodro}"): "modirankhodro",
    ("modirankhodro-emdad.com", "/emdad-kerman-motor/", "emda_general"): "keramn_general",
}
# Renault is intentionally unmapped until its actual paid landing/UTM/ID is verified.
DEFAULT = dict(enabled=False, mode="detect_only", customer_id="4151368554",
               window_seconds=120, min_clicks=6, min_sessions=3,
               rapid_gap_seconds=10, min_rapid_gaps=3, cooldown_seconds=900)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def config(path=CONFIG):
    try:
        c = {**DEFAULT, **json.loads(Path(path).read_text())}
        assert c["mode"] == "detect_only" and c["customer_id"] == "4151368554"
        assert type(c["enabled"]) is bool
        for k, low, high in (("window_seconds",30,300),("min_clicks",6,100),
                              ("min_sessions",3,30),("rapid_gap_seconds",1,10),
                              ("min_rapid_gaps",3,50),("cooldown_seconds",300,86400)):
            assert type(c[k]) is int and low <= c[k] <= high
        return c
    except (OSError, ValueError, TypeError, AssertionError):
        return {**DEFAULT, "configuration_error": True}


def connect(path):
    c = sqlite3.connect(path, timeout=0.5)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS signals(
          site TEXT NOT NULL, click TEXT NOT NULL, campaign TEXT NOT NULL,
          identity TEXT NOT NULL, session TEXT NOT NULL, at REAL NOT NULL,
          trusted INTEGER NOT NULL, engaged INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(site,click));
        CREATE INDEX IF NOT EXISTS guard_window ON signals(site,campaign,identity,at);
        CREATE TABLE IF NOT EXISTS incidents(
          id INTEGER PRIMARY KEY, at REAL NOT NULL, site TEXT NOT NULL,
          campaign TEXT NOT NULL, identity TEXT NOT NULL, reason TEXT NOT NULL,
          evidence TEXT NOT NULL, action TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS guard_incident_identity ON incidents(site,campaign,identity,at);
        CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS engagement(
          site TEXT NOT NULL,identity TEXT NOT NULL,session TEXT NOT NULL,
          at REAL NOT NULL,PRIMARY KEY(site,identity,session));
    """)
    return c


def process(row, *, cfg_path=CONFIG, db_path=DATABASE, now=None):
    """Called only AFTER accepted source event commit. No external network calls."""
    cfg = config(cfg_path)
    if not cfg["enabled"]:
        return {"state": "disabled"}
    at = time.time() if now is None else now
    site = row.get("site_id", "")
    if site not in {s[0] for s in SCOPES}:
        return {"state": "out_of_scope"}
    vid = row.get("visitor_id") or ""
    sid = row.get("session_id") or ""
    if not re.fullmatch(r"[A-Za-z0-9._~-]{8,100}", vid) or not sid:
        return {"state": "missing_identity"}
    identity = digest(site + ":" + vid)
    session = digest(site + ":" + sid)
    with closing(connect(db_path)) as c, c:
        c.execute("BEGIN IMMEDIATE")
        c.execute("INSERT OR REPLACE INTO state VALUES('last_event',?)", (str(at),))
        # Engagement can arrive without attribution: tie only to the same site+session+UUID.
        meta = row.get("metadata_json") or "{}"
        try:
            depth = float(json.loads(meta).get("depth_pct", 0))
        except (ValueError, TypeError, AttributeError):
            depth = 0
        if row.get("event_type") in {"tel_click", "form_submit", "whatsapp_click"} or (row.get("event_type") == "scroll" and depth >= 25):
            c.execute("INSERT OR REPLACE INTO engagement VALUES(?,?,?,?)",(site,identity,session,at))
            c.execute("UPDATE signals SET engaged=1 WHERE site=? AND identity=? AND session=?",
                      (site, identity, session))
        if row.get("event_type") not in {"landing", "page_view"}:
            return {"state": "behavior_only"}
        gclid = row.get("gclid") or ""
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,200}", gclid):
            return {"state": "no_usable_gclid"}
        # GBRAID/WBRAID are not per-click keys and never add another signal.
        campaign = SCOPES.get((site, row.get("landing_path"), row.get("utm_campaign")))
        if not campaign:
            return {"state": "unmapped_campaign"}
        refhost = (urlparse(row.get("referrer") or "").hostname or "").lower()
        try:
            client_at = datetime.fromisoformat((row.get("occurred_at_client") or "").replace("Z","+00:00"))
            fresh = client_at.tzinfo is not None and abs(at-client_at.timestamp()) <= 30
        except (ValueError, TypeError):
            fresh = False
        trusted = (row.get("ip_confidence") in {"trusted_proxy", "direct_peer"}
                   and str(row.get("ip_resolution_version")) == "3"
                   and row.get("utm_source") == "google" and row.get("utm_medium") == "cpc"
                   and refhost in {"google.com", "www.google.com", "www.google.co.uk", "www.google.de"}
                   and row.get("page_path") == row.get("landing_path") and fresh)
        # Global per-site dedup: reusing a GCLID across sessions/brands cannot manufacture clicks.
        inserted = c.execute("INSERT OR IGNORE INTO signals(site,click,campaign,identity,session,at,trusted) VALUES(?,?,?,?,?,?,?)",
                    (site, digest(gclid), campaign, identity, session, at, int(trusted))).rowcount
        if not inserted:
            return {"state": "duplicate_click"}
        if c.execute("SELECT 1 FROM engagement WHERE site=? AND identity=? AND session=?",(site,identity,session)).fetchone():
            c.execute("UPDATE signals SET engaged=1 WHERE site=? AND click=?",(site,digest(gclid)))
        c.execute("INSERT OR REPLACE INTO state VALUES('last_signal',?)", (str(at),))
        recent = [dict(r) for r in c.execute(
            "SELECT * FROM signals WHERE site=? AND campaign=? AND identity=? AND at>=? ORDER BY at",
            (site, campaign, identity, at-cfg["window_seconds"]))]
        gaps = sum(b["at"]-a["at"] <= cfg["rapid_gap_seconds"] for a,b in zip(recent,recent[1:]))
        sessions = len({r["session"] for r in recent})
        qualifies = (len(recent) >= cfg["min_clicks"] and sessions >= cfg["min_sessions"]
                     and gaps >= cfg["min_rapid_gaps"] and all(r["trusted"] for r in recent)
                     and not any(r["engaged"] for r in recent))
        if not qualifies:
            return {"state": "observed", "new_click": True}
        if c.execute("SELECT 1 FROM incidents WHERE site=? AND campaign=? AND identity=? AND at>=?",
                     (site,campaign,identity,at-cfg["cooldown_seconds"])).fetchone():
            return {"state": "incident_cooldown"}
        evidence = dict(version=VERSION, unique_gclids=len(recent), sessions=sessions,
                        rapid_gaps=gaps, first_at=recent[0]["at"], last_at=at,
                        thresholds={k:cfg[k] for k in DEFAULT if k not in {"enabled","mode","customer_id"}},
                        click_hashes=[r["click"] for r in recent],
                        limitation="Client telemetry is not a Google-validated click receipt; campaign inferred from exact landing+UTM.")
        c.execute("INSERT INTO incidents(at,site,campaign,identity,reason,evidence,action) VALUES(?,?,?,?,?,?,?)",
                  (at,site,campaign,identity,"rapid_distinct_clicks_multiple_sessions_no_engagement",
                   json.dumps(evidence),"not_executed_detection_only"))
        result = dict(state="incident", campaign=campaign, action="not_executed_detection_only")
        LOG.warning("ads_guard_incident %s", json.dumps(result))
        return result


def safe_process(row):
    global LAST_ERROR
    try:
        return process(row)
    except Exception as exc:
        # Collector remains available; an error must never be interpreted as protection.
        LOG.error("ads_guard_error type=%s", type(exc).__name__)
        LAST_ERROR = {"at": time.time(), "type": type(exc).__name__}
        return {"state": "error", "error_type": type(exc).__name__}


def status(*, cfg_path=CONFIG, db_path=DATABASE, site_id=None):
    cfg = config(cfg_path)
    result = dict(version=VERSION, enabled=cfg["enabled"], mode="detect_only",
                  ads_pause_enforced=False, configuration_error=cfg.get("configuration_error",False),
                  last_process_error=LAST_ERROR, customer_mapping_verified=False,
                  blockers=["google_oauth_refresh_failed_at_release", "production_api_access_unverified", "legacy_client_developer_token_missing", "numeric_campaign_mapping_not_verified", "pause_executor_not_enabled_in_this_release"],
                  thresholds={k:cfg[k] for k in DEFAULT},
                  mapped_campaigns=sorted(set(SCOPES.values())),
                  unmapped_campaigns=["Renu Emdad"], incidents=[])
    if not Path(db_path).exists():
        result["runtime"] = "awaiting_first_event"
        return result
    try:
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=0.5)) as c:
            c.row_factory = sqlite3.Row
            result["runtime"] = "ready"
            result["state"] = dict(c.execute("SELECT key,value FROM state"))
            result["signal_count"] = c.execute("SELECT count(*) FROM signals").fetchone()[0]
            result["incidents"] = [dict(r) for r in c.execute(
                "SELECT id,at,site,campaign,reason,evidence,action FROM incidents WHERE (? IS NULL OR site=?) ORDER BY id DESC LIMIT 20",
                (site_id,site_id))]
    except sqlite3.Error:
        result["runtime"] = "database_error"
    return result


def view_html():
    return """<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>وضعیت Guard</title>
<style>body{font:18px/1.8 Tahoma,sans-serif;max-width:900px;margin:40px auto;padding:20px;background:#101827;color:#edf2f7}section{padding:18px;border:1px solid #718096;border-radius:12px;margin:18px 0}.warn{background:#713f12}pre{white-space:pre-wrap;font-size:13px}a{color:#93c5fd}</style>
<h1>Guard دریافت کلیک</h1><section class="warn"><strong>تشخیص بدون توقف Ads</strong><p>توقف خودکار کمپین فعال نیست. Refresh مجوز OAuth موجود شکست خورده؛ دسترسی Production API و شناسه‌های حساب/کمپین تأیید نشده‌اند. کلاینت قدیمی Developer Token ندارد؛ مسیر جدید Cloud access هم هنوز تأیید نشده است. رنو هنوز نگاشت تأییدشده ندارد. این صفحه تضمین جلوگیری از هزینه نیست.</p></section>
<p>تشخیص با رسیدن Event به سرور اجرا می‌شود؛ بازبودن این صفحه لازم نیست. نمایش وضعیت هر۳ثانیه به‌روز می‌شود.</p>
<section id="status">درحال دریافت وضعیت…</section><h2>Incidentهای ثبت‌شده</h2><div id="incidents"></div>
<script>const box=document.getElementById('status'),inc=document.getElementById('incidents');async function refresh(){try{const r=await fetch('status',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);const d=await r.json();box.textContent='تشخیص: '+(d.enabled?'فعال':'خاموش')+' | Runtime: '+d.runtime+' | GCLID ذخیره‌شده: '+(d.signal_count||0)+' | توقف Ads: غیرفعال'+(d.last_process_error?' | خطای پردازش ثبت شده':'');inc.replaceChildren();for(const x of d.incidents){const el=document.createElement('section');el.textContent=new Date(x.at*1000).toLocaleString('fa-IR',{timeZone:'Asia/Tehran'})+' — '+x.campaign+' — الگوی پرتکرار نیازمند بررسی؛ هیچ توقفی اجرا نشده. '+x.evidence;inc.append(el)}if(!d.incidents.length)inc.textContent='Incident ثبت‌شده‌ای وجود ندارد؛ این به معنی اثبات نبود تقلب نیست.'}catch(e){box.textContent='دریافت وضعیت ناموفق؛ حفاظت را فعال فرض نکنید. '+e.message}}refresh();setInterval(refresh,3000)</script></html>"""
