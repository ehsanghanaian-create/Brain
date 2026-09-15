"""Traffic Intel (migration 0018): beacon ingestion, session stitching, channel classification, reports.

Same shape as test_gsc_pipeline: a real SQLite file in tmp_path, real migrations, no mocks on the DB.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.tracking import TrackingService, channels

SID = "demo"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"


@pytest.fixture
def env(tmp_path, monkeypatch):
    dbfile = tmp_path / "track.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng
    c = TestClient(app)
    r = c.post("/api/v1/sites", json={"site_id": SID, "name": "امداد دمو", "canonical_url": "https://demo.example/"})
    assert r.status_code == 201, r.text
    key = c.get(f"/api/v1/sites/{SID}/traffic/setup").json()["write_key"]
    return {"client": c, "eng": eng, "key": key}


def beacon(c: TestClient, key: str, events: list[dict], *, referrer: str = "", url: str = "https://demo.example/", ua: str = UA):
    """Post a batch exactly the way the browser tracker does — text/plain, so the request stays CORS-simple."""
    body = json.dumps({"k": key, "v": 1, "r": referrer, "u": url, "d": "mobile", "e": events})
    return c.post("/api/v1/track", content=body, headers={"Content-Type": "text/plain", "User-Agent": ua})


# ----------------------------------------------------------------------------- ingestion

def test_beacon_creates_session_and_events_and_answers_204(env):
    c, key = env["client"], env["key"]
    r = beacon(c, key, [{"t": "pageview", "p": "/امداد-خودرو/"}, {"t": "scroll", "p": "/امداد-خودرو/", "v": 50}])
    assert r.status_code == 204
    with env["eng"].connect() as cx:
        s = cx.execute(text("SELECT site_id, landing_path, pages_count, max_scroll, device FROM track_sessions")).first()
        n = cx.execute(text("SELECT COUNT(*) FROM track_events")).scalar()
    assert s[0] == SID and s[1] == "/امداد-خودرو/" and s[2] == 1 and s[3] == 50 and s[4] == "mobile"
    assert n == 2


def test_second_beacon_reuses_the_open_session(env):
    c, key = env["client"], env["key"]
    beacon(c, key, [{"t": "pageview", "p": "/"}])
    beacon(c, key, [{"t": "pageview", "p": "/tehran/"}])
    with env["eng"].connect() as cx:
        assert cx.execute(text("SELECT COUNT(*) FROM track_sessions")).scalar() == 1
        row = cx.execute(text("SELECT pages_count, exit_path FROM track_sessions")).first()
    assert row[0] == 2 and row[1] == "/tehran/"


def test_unknown_write_key_writes_nothing_but_still_returns_204(env):
    c = env["client"]
    assert beacon(c, "tk_not_a_real_key", [{"t": "pageview", "p": "/"}]).status_code == 204
    with env["eng"].connect() as cx:
        assert cx.execute(text("SELECT COUNT(*) FROM track_sessions")).scalar() == 0


def test_bot_user_agent_is_dropped(env):
    c, key = env["client"], env["key"]
    beacon(c, key, [{"t": "pageview", "p": "/"}], ua="Mozilla/5.0 (compatible; Googlebot/2.1)")
    with env["eng"].connect() as cx:
        assert cx.execute(text("SELECT COUNT(*) FROM track_sessions")).scalar() == 0


def test_malformed_body_never_raises(env):
    c = env["client"]
    assert c.post("/api/v1/track", content="not json", headers={"Content-Type": "text/plain"}).status_code == 204
    assert c.post("/api/v1/track", content="[]", headers={"Content-Type": "text/plain"}).status_code == 204


# ----------------------------------------------------------------------------- conversions

def test_tel_click_marks_the_session_converted_and_shows_up_in_calls(env):
    c, key = env["client"], env["key"]
    beacon(c, key, [{"t": "pageview", "p": "/"}, {"t": "tel_click", "p": "/", "l": "02122477005", "x": 0.5, "y": 0.2}])
    ov = c.get(f"/api/v1/sites/{SID}/traffic/overview").json()
    assert ov["sessions"] == 1 and ov["tel_clicks"] == 1 and ov["conversions"] == 1 and ov["conversion_rate"] == 1.0
    calls = c.get(f"/api/v1/sites/{SID}/traffic/calls").json()
    assert calls["total"] == 1 and calls["by_page"][0]["path"] == "/" and calls["recent"][0]["label"] == "02122477005"


def test_first_conversion_wins_and_is_not_overwritten(env):
    c, key = env["client"], env["key"]
    beacon(c, key, [{"t": "pageview", "p": "/"}, {"t": "tel_click", "p": "/", "l": "021"}])
    beacon(c, key, [{"t": "form_submit", "p": "/contact/", "l": "contact"}])
    with env["eng"].connect() as cx:
        assert cx.execute(text("SELECT conversion_type FROM track_sessions")).scalar() == "tel_click"


# ----------------------------------------------------------------------------- channels

def test_google_referrer_is_organic_and_gclid_wins_as_paid(env):
    c, key = env["client"], env["key"]
    beacon(c, key, [{"t": "pageview", "p": "/"}], referrer="https://www.google.com/")
    ov = c.get(f"/api/v1/sites/{SID}/traffic/overview").json()
    assert {r["channel"] for r in ov["by_channel"]} == {"organic"}
    assert ov["by_search_engine"][0]["search_engine"] == "google"

    # an ad click also carries google.com as its referrer — the gclid must win, or paid is counted as organic
    r = channels.classify("https://www.google.com/", "https://demo.example/?gclid=ABC123")
    assert r["channel"] == "paid" and r["gclid"] == "ABC123"


@pytest.mark.parametrize("referrer,expected_engine", [
    ("https://zarebin.ir/search?q=x", "zarebin"),
    ("https://www.google.de/", "google"),
    ("https://duckduckgo.com/", "duckduckgo"),
    ("https://yooz.ir/", "yooz"),
])
def test_iranian_and_foreign_engines_are_classified_as_organic(referrer, expected_engine):
    """Zarebin/Yooz are in no packaged tool's engine list — every off-the-shelf product files them as referral."""
    r = channels.classify(referrer, "https://demo.example/")
    assert r["channel"] == "organic" and r["search_engine"] == expected_engine


def test_unknown_referrer_is_referral_and_no_referrer_is_direct():
    assert channels.classify("https://blog.example/post", "https://demo.example/")["channel"] == "referral"
    assert channels.classify("", "https://demo.example/")["channel"] == "direct"
    assert channels.classify("https://t.me/somechannel", "https://demo.example/")["channel"] == "social"


# ----------------------------------------------------------------------------- reports over gsc_daily

def test_entries_join_first_party_sessions_to_existing_gsc_rows(env):
    c, key, eng = env["client"], env["key"], env["eng"]
    with eng.begin() as cx:
        cx.execute(text(
            "INSERT INTO gsc_daily(site_id, date, page, query, country, device, clicks, impressions, ctr, position) "
            "VALUES(:s, date('now'), 'https://demo.example/tehran/', 'امداد خودرو تهران', 'irn', 'MOBILE', 40, 900, 0.044, 6.2)"),
            {"s": SID})
        cx.execute(text(
            "INSERT INTO gsc_daily(site_id, date, page, query, country, device, clicks, impressions, ctr, position) "
            "VALUES(:s, date('now'), 'https://demo.example/tehran/', 'امداد خودرو فوری', 'irn', 'MOBILE', 10, 300, 0.033, 8.1)"),
            {"s": SID})
    beacon(c, key, [{"t": "pageview", "p": "/tehran/"}, {"t": "tel_click", "p": "/tehran/", "l": "021"}])

    data = c.get(f"/api/v1/sites/{SID}/traffic/entries").json()
    row = next(r for r in data["items"] if r["path"] == "/tehran/")
    assert row["sessions"] == 1 and row["conversions"] == 1
    assert row["gsc_clicks"] == 50 and row["gsc_impressions"] == 1200
    assert row["gsc_to_session_ratio"] == 50.0        # the gap is surfaced, not hidden

    est = c.get(f"/api/v1/sites/{SID}/traffic/keywords").json()
    assert est["estimated"] is True and est["items"]
    assert abs(sum(i["est_conversions"] for i in est["items"] if i["path"] == "/tehran/") - 1.0) < 0.01
    assert {i["confidence"] for i in est["items"]} == {"high"}


def test_percent_encoded_gsc_url_matches_the_decoded_tracker_path(env):
    """Search Console reports Persian slugs percent-encoded; the tracker reports them decoded."""
    c, key, eng = env["client"], env["key"], env["eng"]
    with eng.begin() as cx:
        cx.execute(text(
            "INSERT INTO gsc_daily(site_id, date, page, query, country, device, clicks, impressions, ctr, position) "
            "VALUES(:s, date('now'), 'https://demo.example/%D8%A7%D9%85%D8%AF%D8%A7%D8%AF/', 'q', '', '', 5, 10, 0.5, 3)"),
            {"s": SID})
    beacon(c, key, [{"t": "pageview", "p": "/امداد/"}])
    data = c.get(f"/api/v1/sites/{SID}/traffic/entries").json()
    row = next(r for r in data["items"] if r["path"] == "/امداد/")
    assert row["gsc_clicks"] == 5


# ----------------------------------------------------------------------------- setup

def test_script_is_served_with_the_key_injected_and_rotation_replaces_it(env):
    c, key = env["client"], env["key"]
    r = c.get(f"/api/v1/track/{SID}/t.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert key in r.text and "__WRITE_KEY__" not in r.text and "__ENDPOINT__" not in r.text

    rotated = c.post(f"/api/v1/sites/{SID}/traffic/setup/rotate").json()
    assert rotated["write_key"] != key
    assert beacon(c, key, [{"t": "pageview", "p": "/"}]).status_code == 204
    with env["eng"].connect() as cx:
        assert cx.execute(text("SELECT COUNT(*) FROM track_sessions")).scalar() == 0   # the old key is dead


def test_disabling_the_tracker_stops_ingestion(env):
    c, key = env["client"], env["key"]
    c.patch(f"/api/v1/sites/{SID}/traffic/setup", json={"enabled": False})
    beacon(c, key, [{"t": "pageview", "p": "/"}])
    with env["eng"].connect() as cx:
        assert cx.execute(text("SELECT COUNT(*) FROM track_sessions")).scalar() == 0


def test_visitor_id_is_a_daily_hash_that_hides_the_ip(env):
    svc = TrackingService(env["eng"])
    a = svc.repo.visitor_id("secret", SID, "2026-09-14", "1.2.3.4", UA)
    b = svc.repo.visitor_id("secret", SID, "2026-09-15", "1.2.3.4", UA)
    assert a != b and len(a) == 32 and "1.2.3.4" not in a


def test_behavior_returns_scroll_and_click_positions(env):
    c, key = env["client"], env["key"]
    beacon(c, key, [{"t": "pageview", "p": "/"}, {"t": "scroll", "p": "/", "v": 75},
                    {"t": "click", "p": "/", "l": "a.btn|تماس", "x": 0.4, "y": 0.65}])
    b = c.get(f"/api/v1/sites/{SID}/traffic/behavior", params={"path": "/"}).json()
    assert b["scroll"] and b["scroll"][0]["depth"] == 75
    assert b["clicks"][0]["label"].startswith("a.btn")
    assert b["points"][0]["x"] == 0.4 and b["points"][0]["y"] == 0.65
