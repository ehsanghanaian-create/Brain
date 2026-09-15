"""Tracking repository: the only layer that knows the track_* columns.

Visitor identity is cookieless and deliberately short-lived — sha256(site hash_secret + UTC day + ip + ua),
truncated. It rotates every midnight, so nothing here can follow a person across days, and the raw IP is
never stored. Sessions are stitched with a 30-minute inactivity window, the same rule GA4 and Plausible use.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine, text

from ..db.repositories.base import Repository, dumps, utcnow
from ..db.tables import track_events, track_keys, track_sessions

SESSION_GAP_MINUTES = 30

EVENT_TYPES = ("pageview", "scroll", "click", "tel_click", "form_submit", "engaged", "exit")
CONVERSION_TYPES = ("tel_click", "form_submit")


def _day(ts: str) -> str:
    return ts[:10]


def _parse(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


class TrackingRepository(Repository):
    """Ingest + read side for first-party visit data."""

    # ------------------------------------------------------------------ keys

    def ensure_key(self, site_id: str) -> dict[str, Any]:
        """Site write key, created on first use. `write_key` is public (it ships in the page); `hash_secret` never leaves the server."""
        with self.engine.begin() as cx:
            row = cx.execute(text("SELECT site_id, write_key, enabled, created_at, rotated_at FROM track_keys WHERE site_id=:s"), {"s": site_id}).mappings().first()
            if row:
                return dict(row)
            rec = {"site_id": site_id, "write_key": f"tk_{secrets.token_urlsafe(18)}", "hash_secret": secrets.token_urlsafe(32),
                   "enabled": 1, "created_at": utcnow(), "rotated_at": None}
            self.upsert(cx, track_keys, rec, conflict=["site_id"])
            return {k: v for k, v in rec.items() if k != "hash_secret"}

    def rotate_key(self, site_id: str) -> dict[str, Any]:
        """New write key + new hash secret. Old pages stop reporting until the snippet is updated — that is the point."""
        self.ensure_key(site_id)
        now = utcnow()
        with self.engine.begin() as cx:
            cx.execute(text("UPDATE track_keys SET write_key=:w, hash_secret=:h, rotated_at=:r WHERE site_id=:s"),
                       {"w": f"tk_{secrets.token_urlsafe(18)}", "h": secrets.token_urlsafe(32), "r": now, "s": site_id})
        return self.ensure_key(site_id)

    def resolve_key(self, write_key: str) -> dict[str, Any] | None:
        """site_id + hash_secret for a write key, or None. Used by the public beacon endpoint."""
        with self.engine.connect() as cx:
            row = cx.execute(text("SELECT site_id, write_key, hash_secret, enabled FROM track_keys WHERE write_key=:w"), {"w": write_key}).mappings().first()
        return dict(row) if row else None

    def set_enabled(self, site_id: str, enabled: bool) -> None:
        with self.engine.begin() as cx:
            cx.execute(text("UPDATE track_keys SET enabled=:e WHERE site_id=:s"), {"e": 1 if enabled else 0, "s": site_id})

    # ------------------------------------------------------------------ ingest

    @staticmethod
    def visitor_id(hash_secret: str, site_id: str, day: str, ip: str, ua: str) -> str:
        raw = f"{hash_secret}|{site_id}|{day}|{ip}|{ua}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32]

    def open_session(self, site_id: str, visitor_id: str, now: str) -> dict[str, Any] | None:
        """The visitor's session if their last hit was inside the inactivity window, else None."""
        cutoff = (_parse(now) - timedelta(minutes=SESSION_GAP_MINUTES)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self.engine.connect() as cx:
            row = cx.execute(text(
                "SELECT * FROM track_sessions WHERE site_id=:s AND visitor_id=:v AND last_seen_at >= :c "
                "ORDER BY last_seen_at DESC LIMIT 1"), {"s": site_id, "v": visitor_id, "c": cutoff}).mappings().first()
        return dict(row) if row else None

    def create_session(self, site_id: str, visitor_id: str, now: str, attrs: dict[str, Any]) -> dict[str, Any]:
        rec = {
            "session_id": uuid.uuid4().hex, "site_id": site_id, "visitor_id": visitor_id, "day": _day(now),
            "started_at": now, "last_seen_at": now,
            "landing_path": attrs.get("landing_path") or "/", "exit_path": attrs.get("landing_path") or "/",
            "referrer_host": attrs.get("referrer_host", ""), "channel": attrs.get("channel", "direct"),
            "search_engine": attrs.get("search_engine", ""), "utm_source": attrs.get("utm_source", ""),
            "utm_medium": attrs.get("utm_medium", ""), "utm_campaign": attrs.get("utm_campaign", ""),
            "utm_term": attrs.get("utm_term", ""), "gclid": attrs.get("gclid", ""),
            "device": attrs.get("device", "desktop"), "country": attrs.get("country", ""),
            "pages_count": 0, "events_count": 0, "max_scroll": 0, "duration_s": 0,
            "converted_at": None, "conversion_type": None, "created_at": now,
        }
        with self.engine.begin() as cx:
            self.upsert(cx, track_sessions, rec, conflict=["session_id"])
        return rec

    def add_events(self, site_id: str, session_id: str, events: list[dict[str, Any]]) -> int:
        """Append raw hits. Returns the number written."""
        if not events:
            return 0
        rows = []
        for e in events:
            ts = e.get("ts") or utcnow()
            rows.append({
                "site_id": site_id, "session_id": session_id, "day": _day(ts), "ts": ts,
                "type": e["type"], "path": e.get("path") or "/", "label": (e.get("label") or "")[:400],
                "value": e.get("value"), "pos_x": e.get("pos_x"), "pos_y": e.get("pos_y"),
                "meta": dumps(e.get("meta") or {}), "created_at": utcnow(),
            })
        with self.engine.begin() as cx:
            cx.execute(track_events.insert(), rows)
        return len(rows)

    def touch_session(self, session_id: str, now: str, *, pages: int, events: int, max_scroll: int,
                      exit_path: str, conversion: str | None) -> None:
        """Roll the session forward: counters, duration, last page, and the first conversion (never overwritten)."""
        with self.engine.begin() as cx:
            cur = cx.execute(text("SELECT started_at, pages_count, events_count, max_scroll, conversion_type FROM track_sessions WHERE session_id=:i"),
                             {"i": session_id}).mappings().first()
            if not cur:
                return
            duration = max(0, int((_parse(now) - _parse(cur["started_at"])).total_seconds()))
            params = {
                "i": session_id, "l": now, "d": duration,
                "p": int(cur["pages_count"]) + pages, "e": int(cur["events_count"]) + events,
                "m": max(int(cur["max_scroll"] or 0), max_scroll), "x": exit_path or "",
            }
            cx.execute(text(
                "UPDATE track_sessions SET last_seen_at=:l, duration_s=:d, pages_count=:p, events_count=:e, "
                "max_scroll=:m, exit_path=CASE WHEN :x='' THEN exit_path ELSE :x END WHERE session_id=:i"), params)
            if conversion and not cur["conversion_type"]:
                cx.execute(text("UPDATE track_sessions SET converted_at=:c, conversion_type=:t WHERE session_id=:i"),
                           {"c": now, "t": conversion, "i": session_id})

    # ------------------------------------------------------------------ reports

    def window(self, days: int) -> tuple[str, str]:
        """Inclusive [from, to] date strings for a lookback window, in UTC — the grouping key of every report."""
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=max(1, days) - 1)
        return start.isoformat(), end.isoformat()

    def overview(self, site_id: str, days: int) -> dict[str, Any]:
        a, b = self.window(days)
        p = {"s": site_id, "a": a, "b": b}
        with self.engine.connect() as cx:
            totals = cx.execute(text(
                "SELECT COUNT(*) AS sessions, COALESCE(SUM(pages_count),0) AS pageviews, "
                "COALESCE(SUM(CASE WHEN conversion_type IS NOT NULL THEN 1 ELSE 0 END),0) AS conversions, "
                "COALESCE(SUM(CASE WHEN conversion_type='tel_click' THEN 1 ELSE 0 END),0) AS tel_clicks, "
                "COALESCE(SUM(CASE WHEN conversion_type='form_submit' THEN 1 ELSE 0 END),0) AS forms, "
                "COALESCE(SUM(CASE WHEN pages_count<=1 AND duration_s<10 THEN 1 ELSE 0 END),0) AS bounces, "
                "COALESCE(AVG(duration_s),0) AS avg_duration "
                "FROM track_sessions WHERE site_id=:s AND day BETWEEN :a AND :b"), p).mappings().first()
            by_channel = [dict(r) for r in cx.execute(text(
                "SELECT channel, COUNT(*) AS sessions, "
                "SUM(CASE WHEN conversion_type IS NOT NULL THEN 1 ELSE 0 END) AS conversions "
                "FROM track_sessions WHERE site_id=:s AND day BETWEEN :a AND :b GROUP BY channel ORDER BY sessions DESC"), p).mappings()]
            by_engine = [dict(r) for r in cx.execute(text(
                "SELECT search_engine, COUNT(*) AS sessions FROM track_sessions "
                "WHERE site_id=:s AND day BETWEEN :a AND :b AND search_engine<>'' GROUP BY search_engine ORDER BY sessions DESC"), p).mappings()]
            by_device = [dict(r) for r in cx.execute(text(
                "SELECT device, COUNT(*) AS sessions, SUM(CASE WHEN conversion_type IS NOT NULL THEN 1 ELSE 0 END) AS conversions "
                "FROM track_sessions WHERE site_id=:s AND day BETWEEN :a AND :b GROUP BY device ORDER BY sessions DESC"), p).mappings()]
            series = [dict(r) for r in cx.execute(text(
                "SELECT day, COUNT(*) AS sessions, "
                "SUM(CASE WHEN channel='organic' THEN 1 ELSE 0 END) AS organic, "
                "SUM(CASE WHEN conversion_type IS NOT NULL THEN 1 ELSE 0 END) AS conversions "
                "FROM track_sessions WHERE site_id=:s AND day BETWEEN :a AND :b GROUP BY day ORDER BY day"), p).mappings()]
        t = dict(totals or {})
        sessions = int(t.get("sessions", 0) or 0)
        return {
            "date_from": a, "date_to": b, "days": days,
            "sessions": sessions,
            "pageviews": int(t.get("pageviews", 0) or 0),
            "conversions": int(t.get("conversions", 0) or 0),
            "tel_clicks": int(t.get("tel_clicks", 0) or 0),
            "form_submits": int(t.get("forms", 0) or 0),
            "conversion_rate": round(int(t.get("conversions", 0) or 0) / sessions, 4) if sessions else 0.0,
            "bounce_rate": round(int(t.get("bounces", 0) or 0) / sessions, 4) if sessions else 0.0,
            "avg_duration_s": round(float(t.get("avg_duration", 0) or 0), 1),
            "by_channel": by_channel, "by_search_engine": by_engine, "by_device": by_device, "series": series,
        }

    def entries(self, site_id: str, days: int, limit: int) -> list[dict[str, Any]]:
        """Landing pages by session count, with conversions. Joined to Search Console by the caller."""
        a, b = self.window(days)
        with self.engine.connect() as cx:
            rows = cx.execute(text(
                "SELECT landing_path AS path, COUNT(*) AS sessions, "
                "SUM(CASE WHEN channel='organic' THEN 1 ELSE 0 END) AS organic_sessions, "
                "SUM(CASE WHEN conversion_type IS NOT NULL THEN 1 ELSE 0 END) AS conversions, "
                "SUM(CASE WHEN conversion_type='tel_click' THEN 1 ELSE 0 END) AS tel_clicks, "
                "AVG(duration_s) AS avg_duration, AVG(max_scroll) AS avg_scroll "
                "FROM track_sessions WHERE site_id=:s AND day BETWEEN :a AND :b "
                "GROUP BY landing_path ORDER BY sessions DESC LIMIT :l"),
                {"s": site_id, "a": a, "b": b, "l": limit}).mappings()
            return [{**dict(r), "avg_duration": round(float(r["avg_duration"] or 0), 1),
                     "avg_scroll": round(float(r["avg_scroll"] or 0), 1)} for r in rows]

    def calls(self, site_id: str, days: int, limit: int) -> dict[str, Any]:
        """tel: clicks — the conversion that matters for a roadside-assistance site. Intent to call, not a completed call."""
        a, b = self.window(days)
        p = {"s": site_id, "a": a, "b": b, "l": limit}
        with self.engine.connect() as cx:
            by_page = [dict(r) for r in cx.execute(text(
                "SELECT path, COUNT(*) AS clicks FROM track_events "
                "WHERE site_id=:s AND type='tel_click' AND day BETWEEN :a AND :b GROUP BY path ORDER BY clicks DESC LIMIT :l"), p).mappings()]
            by_hour = [dict(r) for r in cx.execute(text(
                "SELECT substr(ts, 12, 2) AS hour, COUNT(*) AS clicks FROM track_events "
                "WHERE site_id=:s AND type='tel_click' AND day BETWEEN :a AND :b GROUP BY hour ORDER BY hour"), p).mappings()]
            by_day = [dict(r) for r in cx.execute(text(
                "SELECT day, COUNT(*) AS clicks FROM track_events "
                "WHERE site_id=:s AND type='tel_click' AND day BETWEEN :a AND :b GROUP BY day ORDER BY day"), p).mappings()]
            by_channel = [dict(r) for r in cx.execute(text(
                "SELECT ts.channel, ts.search_engine, COUNT(*) AS clicks FROM track_events te "
                "JOIN track_sessions ts ON ts.session_id = te.session_id "
                "WHERE te.site_id=:s AND te.type='tel_click' AND te.day BETWEEN :a AND :b "
                "GROUP BY ts.channel, ts.search_engine ORDER BY clicks DESC"), p).mappings()]
            recent = [dict(r) for r in cx.execute(text(
                "SELECT te.ts, te.path, te.label, ts.channel, ts.search_engine, ts.device, ts.landing_path, ts.gclid "
                "FROM track_events te JOIN track_sessions ts ON ts.session_id = te.session_id "
                "WHERE te.site_id=:s AND te.type='tel_click' AND te.day BETWEEN :a AND :b "
                "ORDER BY te.ts DESC LIMIT :l"), p).mappings()]
        total = sum(int(r["clicks"]) for r in by_day)
        return {"date_from": a, "date_to": b, "total": total, "by_page": by_page, "by_hour": by_hour,
                "by_day": by_day, "by_channel": by_channel, "recent": recent}

    def behavior(self, site_id: str, days: int, path: str | None, limit: int) -> dict[str, Any]:
        """Scroll depth, click map and page sequence. `path` narrows everything to one page."""
        a, b = self.window(days)
        p: dict[str, Any] = {"s": site_id, "a": a, "b": b, "l": limit}
        clause = " AND path=:p" if path else ""
        if path:
            p["p"] = path
        with self.engine.connect() as cx:
            scroll = [dict(r) for r in cx.execute(text(
                f"SELECT CAST(value AS INTEGER) AS depth, COUNT(*) AS hits FROM track_events "
                f"WHERE site_id=:s AND type='scroll' AND day BETWEEN :a AND :b{clause} "
                f"GROUP BY depth ORDER BY depth"), p).mappings()]
            clicks = [dict(r) for r in cx.execute(text(
                f"SELECT label, path, COUNT(*) AS clicks, AVG(pos_x) AS x, AVG(pos_y) AS y FROM track_events "
                f"WHERE site_id=:s AND type IN ('click','tel_click') AND day BETWEEN :a AND :b{clause} "
                f"GROUP BY label, path ORDER BY clicks DESC LIMIT :l"), p).mappings()]
            points = [dict(r) for r in cx.execute(text(
                f"SELECT pos_x AS x, pos_y AS y, type FROM track_events "
                f"WHERE site_id=:s AND type IN ('click','tel_click') AND pos_x IS NOT NULL AND day BETWEEN :a AND :b{clause} "
                f"ORDER BY id DESC LIMIT 2000"), p).mappings()]
            pages = [dict(r) for r in cx.execute(text(
                "SELECT path, COUNT(*) AS views, COUNT(DISTINCT session_id) AS sessions FROM track_events "
                "WHERE site_id=:s AND type='pageview' AND day BETWEEN :a AND :b GROUP BY path ORDER BY views DESC LIMIT :l"),
                {"s": site_id, "a": a, "b": b, "l": limit}).mappings()]
            exits = [dict(r) for r in cx.execute(text(
                "SELECT exit_path AS path, COUNT(*) AS sessions FROM track_sessions "
                "WHERE site_id=:s AND day BETWEEN :a AND :b AND exit_path<>'' GROUP BY exit_path ORDER BY sessions DESC LIMIT :l"),
                {"s": site_id, "a": a, "b": b, "l": limit}).mappings()]
        return {"date_from": a, "date_to": b, "path": path, "scroll": scroll, "clicks": clicks,
                "points": [{**r, "x": round(float(r["x"] or 0), 4), "y": round(float(r["y"] or 0), 4)} for r in points],
                "pages": pages, "exits": exits}

    # ---- Search Console side (existing gsc_daily — this feature reads it, never re-ingests it) ----

    def gsc_pages(self, site_id: str, days: int, limit: int) -> list[dict[str, Any]]:
        a, b = self.window(days)
        with self.engine.connect() as cx:
            rows = cx.execute(text(
                "SELECT page, SUM(clicks) AS clicks, SUM(impressions) AS impressions, "
                "CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) ELSE 0 END AS position "
                "FROM gsc_daily WHERE site_id=:s AND date BETWEEN :a AND :b "
                "GROUP BY page ORDER BY clicks DESC LIMIT :l"), {"s": site_id, "a": a, "b": b, "l": limit}).mappings()
            return [dict(r) for r in rows]

    def gsc_queries_for_pages(self, site_id: str, days: int, pages: list[str], per_page: int) -> dict[str, list[dict[str, Any]]]:
        """Top queries per landing page — the click-share basis for any keyword estimate."""
        if not pages:
            return {}
        a, b = self.window(days)
        out: dict[str, list[dict[str, Any]]] = {}
        with self.engine.connect() as cx:
            for page in pages:
                rows = cx.execute(text(
                    "SELECT query, SUM(clicks) AS clicks, SUM(impressions) AS impressions, "
                    "CASE WHEN SUM(impressions)>0 THEN SUM(position*impressions)/SUM(impressions) ELSE 0 END AS position "
                    "FROM gsc_daily WHERE site_id=:s AND page=:p AND date BETWEEN :a AND :b AND query<>'' "
                    "GROUP BY query ORDER BY clicks DESC, impressions DESC LIMIT :l"),
                    {"s": site_id, "p": page, "a": a, "b": b, "l": per_page}).mappings()
                out[page] = [dict(r) for r in rows]
        return out

    def has_data(self, site_id: str) -> dict[str, Any]:
        with self.engine.connect() as cx:
            s = cx.execute(text("SELECT COUNT(*) FROM track_sessions WHERE site_id=:s"), {"s": site_id}).scalar() or 0
            e = cx.execute(text("SELECT COUNT(*) FROM track_events WHERE site_id=:s"), {"s": site_id}).scalar() or 0
            first = cx.execute(text("SELECT MIN(day) FROM track_sessions WHERE site_id=:s"), {"s": site_id}).scalar()
            last = cx.execute(text("SELECT MAX(day) FROM track_sessions WHERE site_id=:s"), {"s": site_id}).scalar()
            gsc = cx.execute(text("SELECT COUNT(*) FROM gsc_daily WHERE site_id=:s"), {"s": site_id}).scalar() or 0
        return {"sessions": int(s), "events": int(e), "first_day": first, "last_day": last, "gsc_rows": int(gsc)}
