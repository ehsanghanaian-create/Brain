"""Tracking service: beacon ingestion, and the reports that join first-party visits to Search Console.

The split that everything else depends on:
  * a SESSION is the unit of truth for behaviour (what someone did on the site) — exact, first-party;
  * a PAGE-DAY is the unit of truth for keywords — Search Console never reports a query per visitor;
so anything that puts a keyword next to a session is an ESTIMATE and is returned with `estimated: true`
and a confidence grade. Paid traffic is the single exception: gclid identifies the ad keyword exactly.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlparse

from sqlalchemy import Engine, text

from ..db.repositories.base import utcnow
from .channels import classify, device_of, is_bot
from .repository import CONVERSION_TYPES, EVENT_TYPES, TrackingRepository

MAX_EVENTS_PER_BEACON = 40

# how much of a page's conversions a query may absorb, relative to its raw click share (see docs/tracker-setup.md)
INTENT_WEIGHTS = {"branded": 3.0, "transactional": 2.0, "commercial": 1.5, "navigational": 1.0, "informational": 0.5}
TRANSACTIONAL_FA = ("قیمت", "هزینه", "تعرفه", "سفارش", "رزرو", "تماس", "شماره", "فوری", "شبانه", "نزدیک", "اورژانس")
INFORMATIONAL_FA = ("چیست", "چگونه", "چطور", "آموزش", "علت", "دلیل", "تفاوت", "راهنما", "چرا", "معرفی")


def path_of(url: str) -> str:
    """Path part of a Search Console page URL, percent-decoded so Persian slugs compare equal to the tracker's."""
    if not url:
        return "/"
    try:
        p = urlparse(url if "//" in url else f"//{url}").path or "/"
    except ValueError:
        return "/"
    p = unquote(p)
    return p if p.startswith("/") else f"/{p}"


def normalize_path(raw: str | None) -> str:
    """Tracker-side path: decoded, query and fragment dropped, trailing slash kept (WordPress canonical form)."""
    if not raw:
        return "/"
    raw = raw.split("#", 1)[0].split("?", 1)[0]
    if "//" in raw:
        raw = path_of(raw)
    raw = unquote(raw)
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return raw[:500]


def intent_of(query: str, brand_terms: tuple[str, ...]) -> str:
    q = query.strip().lower()
    if any(b and b.lower() in q for b in brand_terms):
        return "branded"
    if any(w in q for w in TRANSACTIONAL_FA):
        return "transactional"
    if any(w in q for w in INFORMATIONAL_FA):
        return "informational"
    return "commercial"


class TrackingService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.repo = TrackingRepository(engine)

    # ------------------------------------------------------------------ ingest

    def ingest(self, write_key: str, payload: dict[str, Any], ip: str, user_agent: str, site_host: str = "") -> dict[str, Any]:
        """Accept one beacon. Returns a small dict; the endpoint answers 204 either way so the page never waits."""
        key = self.repo.resolve_key(write_key)
        if not key or not int(key.get("enabled", 1)):
            return {"accepted": 0, "reason": "unknown_key"}
        if is_bot(user_agent):
            return {"accepted": 0, "reason": "bot"}

        site_id = key["site_id"]
        raw = payload.get("e") or payload.get("events") or []
        if not isinstance(raw, list) or not raw:
            return {"accepted": 0, "reason": "empty"}

        now = utcnow()
        day = now[:10]
        visitor = self.repo.visitor_id(key["hash_secret"], site_id, day, ip, user_agent)
        session = self.repo.open_session(site_id, visitor, now)

        first = raw[0] if isinstance(raw[0], dict) else {}
        landing = normalize_path(first.get("p") or payload.get("p"))
        if session is None:
            attrs = classify(payload.get("r") or first.get("r"), payload.get("u") or first.get("u"), site_host)
            attrs["landing_path"] = landing
            attrs["device"] = payload.get("d") if payload.get("d") in ("mobile", "tablet", "desktop") else device_of(user_agent)
            session = self.repo.create_session(site_id, visitor, now, attrs)

        events, pages, max_scroll, conversion, exit_path = [], 0, 0, None, ""
        for item in raw[:MAX_EVENTS_PER_BEACON]:
            if not isinstance(item, dict):
                continue
            etype = str(item.get("t") or item.get("type") or "")
            if etype not in EVENT_TYPES:
                continue
            path = normalize_path(item.get("p") or item.get("path"))
            ev: dict[str, Any] = {"type": etype, "path": path, "ts": now,
                                  "label": str(item.get("l") or item.get("label") or "")}
            for src, dst in (("v", "value"), ("x", "pos_x"), ("y", "pos_y")):
                val = item.get(src)
                if isinstance(val, (int, float)):
                    ev[dst] = float(val)
            events.append(ev)
            if etype == "pageview":
                pages += 1
                exit_path = path
            elif etype == "scroll" and isinstance(ev.get("value"), float):
                max_scroll = max(max_scroll, min(100, int(ev["value"])))
            elif etype in CONVERSION_TYPES and conversion is None:
                conversion = etype

        written = self.repo.add_events(site_id, session["session_id"], events)
        self.repo.touch_session(session["session_id"], now, pages=pages, events=written,
                                max_scroll=max_scroll, exit_path=exit_path, conversion=conversion)
        return {"accepted": written, "session_id": session["session_id"], "site_id": site_id}

    # ------------------------------------------------------------------ reports

    def overview(self, site_id: str, days: int) -> dict[str, Any]:
        data = self.repo.overview(site_id, days)
        data["coverage"] = self.repo.has_data(site_id)
        return data

    def organic_entries(self, site_id: str, days: int, limit: int) -> dict[str, Any]:
        """Landing pages with BOTH sides: exact first-party sessions/conversions, and exact Search Console clicks.

        The two numbers will not match and are not meant to — different counting, different bot filtering,
        different moment of attribution. `gsc_to_session_ratio` is that gap, made visible instead of hidden.
        """
        sessions = self.repo.entries(site_id, days, limit)
        gsc_rows = self.repo.gsc_pages(site_id, days, max(limit * 2, 100))
        gsc_by_path: dict[str, dict[str, Any]] = {}
        for r in gsc_rows:
            p = path_of(str(r["page"]))
            cur = gsc_by_path.setdefault(p, {"page": r["page"], "clicks": 0, "impressions": 0, "_wpos": 0.0})
            cur["clicks"] += int(r["clicks"] or 0)
            cur["impressions"] += int(r["impressions"] or 0)
            cur["_wpos"] += float(r["position"] or 0) * int(r["impressions"] or 0)

        seen, items = set(), []
        for row in sessions:
            g = gsc_by_path.get(row["path"])
            seen.add(row["path"])
            items.append(self._entry_row(row, g))
        for p, g in gsc_by_path.items():          # pages Search Console knows about but the tracker has not seen yet
            if p in seen or not g["clicks"]:
                continue
            items.append(self._entry_row({"path": p, "sessions": 0, "organic_sessions": 0, "conversions": 0,
                                          "tel_clicks": 0, "avg_duration": 0.0, "avg_scroll": 0.0}, g))
        items.sort(key=lambda r: (r["gsc_clicks"], r["sessions"]), reverse=True)
        return {"days": days, "items": items[:limit],
                "tracker_pages": len(sessions), "gsc_pages": len(gsc_by_path)}

    @staticmethod
    def _entry_row(row: dict[str, Any], g: dict[str, Any] | None) -> dict[str, Any]:
        clicks = int(g["clicks"]) if g else 0
        impressions = int(g["impressions"]) if g else 0
        position = round(g["_wpos"] / impressions, 1) if g and impressions else None
        sessions = int(row["sessions"])
        return {
            **row,
            "gsc_page": g["page"] if g else None,
            "gsc_clicks": clicks, "gsc_impressions": impressions, "gsc_position": position,
            "gsc_ctr": round(clicks / impressions, 4) if impressions else 0.0,
            "conversion_rate": round(int(row["conversions"]) / sessions, 4) if sessions else 0.0,
            "gsc_to_session_ratio": round(clicks / sessions, 2) if sessions and clicks else None,
        }

    def keyword_estimate(self, site_id: str, days: int, limit: int, brand_terms: tuple[str, ...] = ()) -> dict[str, Any]:
        """Estimated keyword -> conversion attribution. Explicitly an estimate; see the module docstring.

        Method: for each landing page, take its Search Console queries, weight each query's click share by
        intent, then renormalize so the page's estimated conversions sum EXACTLY to the conversions the
        tracker actually recorded for that page. Confidence falls as the number of candidate queries rises.
        """
        entries = self.repo.entries(site_id, days, limit)
        gsc_rows = self.repo.gsc_pages(site_id, days, max(limit * 2, 100))
        url_by_path = {path_of(str(r["page"])): str(r["page"]) for r in gsc_rows}
        pages = [url_by_path[e["path"]] for e in entries if e["path"] in url_by_path]
        queries_by_page = self.repo.gsc_queries_for_pages(site_id, days, pages, per_page=25)

        items: list[dict[str, Any]] = []
        for e in entries:
            url = url_by_path.get(e["path"])
            qs = queries_by_page.get(url or "", [])
            conversions = int(e["conversions"])
            if not qs or not conversions:
                continue
            weighted = []
            for q in qs:
                intent = intent_of(str(q["query"]), brand_terms)
                base = int(q["clicks"] or 0) or (int(q["impressions"] or 0) / 100.0)
                weighted.append((q, intent, base * INTENT_WEIGHTS[intent]))
            total = sum(w for _, _, w in weighted)
            if total <= 0:
                continue
            confidence = "high" if len(qs) <= 5 else "medium" if len(qs) <= 15 else "low"
            for q, intent, w in weighted:
                share = w / total
                items.append({
                    "path": e["path"], "query": q["query"], "intent": intent,
                    "gsc_clicks": int(q["clicks"] or 0), "gsc_position": round(float(q["position"] or 0), 1),
                    "share": round(share, 4),
                    "est_sessions": round(int(e["sessions"]) * share, 1),
                    "est_conversions": round(conversions * share, 2),
                    "confidence": confidence,
                })
        items.sort(key=lambda r: r["est_conversions"], reverse=True)
        return {
            "days": days, "estimated": True,
            "method": "سهم کلیک سرچ‌کنسول در سطح صفحه، وزن‌دهی‌شده با نیت کوئری و نرمال‌شده روی تبدیل واقعی همان صفحه",
            "caveat": "کلمه کلیدی هر سشن قابل دانستن نیست — گوگل آن را در ریفرر نمی‌فرستد. این اعداد تخمین‌اند.",
            "items": items[:limit],
        }

    def paid_keywords(self, site_id: str, days: int, limit: int) -> dict[str, Any]:
        """Sessions that arrived with a gclid — the only traffic whose keyword is exactly recoverable.

        The gclid -> keyword lookup itself needs Google Ads API click_view, which must be queried one day at a
        time and only reaches 90 days back; until that job exists these rows carry the click id and nothing else.
        """
        a, b = self.repo.window(days)
        with self.engine.connect() as cx:
            rows = [dict(r) for r in cx.execute(text(
                "SELECT gclid, utm_campaign, utm_term, landing_path, device, started_at, conversion_type "
                "FROM track_sessions WHERE site_id=:s AND gclid<>'' AND day BETWEEN :a AND :b "
                "ORDER BY started_at DESC LIMIT :l"), {"s": site_id, "a": a, "b": b, "l": limit}).mappings()]
        return {"days": days, "items": rows, "resolved": False,
                "note": "برای تبدیل gclid به کلمه کلیدی، جاب روزانه Google Ads API (click_view) لازم است — پنجره ۹۰ روزه."}
