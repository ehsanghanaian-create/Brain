"""Conservative GA4 acquisition-source classification for identifiable AI referrals.

This is referral evidence, not a count of every visitor influenced by AI. Google
AI Overviews/Mode traffic cannot be separated with these referrer domains.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date
from urllib.parse import unquote, urlsplit

AI_SOURCE_PLATFORMS = {
    "chatgpt.com": "chatgpt",
    "chat.openai.com": "chatgpt",
    "perplexity.ai": "perplexity",
    "claude.ai": "claude",
    "gemini.google.com": "gemini",
    "copilot.microsoft.com": "copilot",
    "poe.com": "poe",
    "you.com": "you",
    "phind.com": "phind",
    "grok.com": "grok",
    "chat.mistral.ai": "mistral",
}


def classify_source(value: str) -> str | None:
    source = value.strip().lower().rstrip(".")
    if source.startswith(("https://", "http://")):
        source = urlsplit(source).hostname or ""
    if source.startswith("www."):
        source = source[4:]
    return AI_SOURCE_PLATFORMS.get(source)


def landing_path(value: str) -> str:
    """Remove query parameters so campaign tags do not split one landing page."""
    path = unquote(urlsplit(value).path or "/")
    return path.rstrip("/") or "/"


def store_referrals(conn: sqlite3.Connection, site_id: str, start: date, end: date,
                    result: dict, run_id: str) -> int:
    """Replace one completed reporting window atomically; a failed fetch keeps old data."""
    grouped: dict[tuple[str, str, str, str], dict] = defaultdict(lambda: {
        "sessions": 0, "engaged_sessions": 0, "transactions": 0.0, "purchase_revenue": 0.0,
    })
    commerce = bool(result.get("commerce_available"))
    for row in result["rows"]:
        platform = classify_source(row["session_source"])
        if platform is None:
            continue
        key = (row["date"], landing_path(row["landing_page"]), row["session_source"].lower().strip(),
               row["session_medium"].lower().strip())
        item = grouped[key]
        item["sessions"] += int(row["sessions"])
        item["engaged_sessions"] += int(row["engaged_sessions"])
        if commerce:
            item["transactions"] += float(row["transactions"])
            item["purchase_revenue"] += float(row["purchase_revenue"])
    with conn:
        conn.execute("DELETE FROM ga4_ai_referrals_daily WHERE site_id=? AND date BETWEEN ? AND ?",
                     (site_id, start.isoformat(), end.isoformat()))
        for (day, path, source, medium), values in grouped.items():
            conn.execute("""INSERT INTO ga4_ai_referrals_daily
                (site_id,date,landing_page,session_source,session_medium,platform,sessions,engaged_sessions,
                 transactions,purchase_revenue,currency,sync_run_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (site_id, day, path, source, medium, classify_source(source), values["sessions"],
                 values["engaged_sessions"], values["transactions"] if commerce else None,
                 values["purchase_revenue"] if commerce else None, result.get("currency"), run_id))
    return len(grouped)
