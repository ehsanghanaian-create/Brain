"""Conservative time-based attribution for completed calls.

The tracked tel: number is the business destination, not the caller. A unique
nearby click is therefore probable only; ambiguous/missing evidence stays unknown.
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy import text


def suggest(cx, site_id: str | None, occurred_at: str | None, call_id: int | None = None) -> dict:
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    empty = {"source": "unknown", "source_confidence": "unknown", "source_basis": "manual",
             "attribution_event": None, "attribution_checked_at": checked_at, "auto_attributed": 0}
    if not site_id or not occurred_at:
        return empty
    try:
        at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        if at.tzinfo is None:
            return empty
    except ValueError:
        return empty
    start = (at - timedelta(minutes=5)).isoformat(timespec="seconds")
    end = (at + timedelta(minutes=2)).isoformat(timespec="seconds")
    args = {"site": site_id, "start": start, "end": end}
    tracked = cx.execute(text("""SELECT 'track:' || e.id AS event_id, s.channel AS channel,
        s.gclid AS gclid, s.utm_medium AS utm_medium
        FROM track_events e JOIN track_sessions s ON s.session_id=e.session_id
        WHERE e.site_id=:site AND e.type='tel_click' AND datetime(e.ts) BETWEEN datetime(:start) AND datetime(:end)
        ORDER BY e.ts DESC LIMIT 3"""), args).mappings().all()
    ads = cx.execute(text("""SELECT 'ads:' || id AS event_id,
        CASE WHEN COALESCE(gclid,'')<>'' OR COALESCE(gbraid,'')<>'' OR COALESCE(wbraid,'')<>''
          OR lower(COALESCE(utm_medium,'')) IN ('cpc','ppc','paid','paid_search') THEN 'paid'
          ELSE 'unknown' END AS channel, gclid, utm_medium
        FROM ads_click_events WHERE site_id=:site AND event_type='tel_click'
          AND datetime(received_at) BETWEEN datetime(:start) AND datetime(:end) ORDER BY received_at DESC LIMIT 3"""), args).mappings().all()
    candidates = [*tracked, *ads]
    if len(candidates) != 1:
        return empty
    candidate = candidates[0]
    if cx.execute(text("""SELECT 1 FROM call_center_calls
        WHERE attribution_event=:event_id AND auto_attributed=1 AND id<>:call_id LIMIT 1"""),
        {"event_id": candidate["event_id"], "call_id": call_id or -1}).first():
        return empty
    channel = candidate["channel"]
    source = {"organic": "seo", "paid": "ads", "direct": "direct", "referral": "referral"}.get(channel)
    if source is None:
        return empty
    return {"source": source, "source_confidence": "probable", "source_basis": "gclid" if candidate["gclid"] else "manual",
            "attribution_event": candidate["event_id"], "attribution_checked_at": checked_at, "auto_attributed": 1}
