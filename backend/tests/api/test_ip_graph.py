"""Entry-flow graph (`/ip-graph`): source → visitor/IP → landing page → goal, for the cookieless tracker (scope=seo, anonymous
daily visitors — the tracker stores no IP) and for the ads collector (scope=ads, real IPs + the dashboard's risk score)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import sites as sites_router
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate


@pytest.fixture
def c(tmp_path, monkeypatch):
    eng = make_engine("sqlite:///" + (tmp_path / "ipg.db").as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("ADS_DATABASE_PATH", raising=False)          # ads tables live in the same (temp) database
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app); client.eng = eng  # type: ignore[attr-defined]
    assert client.post("/api/v1/sites", json={"site_id": "demo-site", "name": "Demo", "canonical_url": "https://demo.example/"}).status_code == 201
    return client


def test_seo_scope_uses_anonymous_daily_visitors(c):
    from datetime import datetime, timezone
    day = datetime.now(timezone.utc).date().isoformat()
    rows = [("s1", "v-aaaaaa111", "organic", "google", "", "/blog/%D8%B1%D9%88%D8%BA%D9%86", "tel_click"), ("s2", "v-aaaaaa111", "organic", "google", "", "/blog/%D8%B1%D9%88%D8%BA%D9%86", ""),
            ("s3", "v-bbbbbb222", "referral", "", "divar.ir", "/", ""), ("s4", "v-cccccc333", "direct", "", "", "/contact", "form_submit")]
    with c.eng.begin() as cx:
        for sid, vid, channel, se, ref, landing, conv in rows:
            cx.execute(text("INSERT INTO track_sessions(session_id, site_id, visitor_id, day, started_at, last_seen_at, landing_path, referrer_host, channel, search_engine, device, country, pages_count, conversion_type) "
                            "VALUES(:sid,'demo-site',:vid,:day,:ts,:ts,:landing,:ref,:channel,:se,'mobile','IR',2,:conv)"),
                       {"sid": sid, "vid": vid, "day": day, "ts": day + "T10:00:00.000Z", "landing": landing, "ref": ref, "channel": channel, "se": se, "conv": conv or None})
    d = c.get("/api/v1/ip-graph", params={"scope": "seo", "site_id": "demo-site", "hours": 48}).json()
    by = {n["id"]: n for n in d["nodes"]}
    assert d["stats"]["sessions"] == 4 and d["stats"]["actors_total"] == 3 and d["stats"]["conversions"] == 2 and "IP" in d["stats"]["note"]
    top = by["ip:v-aaaaaa111"]
    assert top["kind"] == "actor" and top["status"] == "hot" and top["weight"] == 2 and top["label"].endswith("v-aaaa") and top["meta"]["conversions"] == 1
    assert by["src:ارگانیک · google"]["weight"] == 2 and by["src:ارجاعی · divar.ir"]["kind"] == "source" and by["page:/blog/روغن"]["weight"] == 2      # percent-decoded path
    assert {"goal:tel_click", "goal:form_submit"} <= set(by) and by["goal:tel_click"]["label"] == "تماس"
    edges = {(e["source"], e["target"]): e for e in d["edges"]}
    assert edges[("src:ارگانیک · google", "ip:v-aaaaaa111")]["weight"] == 2 and edges[("ip:v-aaaaaa111", "goal:tel_click")]["kind"] == "goal"
    assert nodes_order(d, "actor")[0] == "ip:v-aaaaaa111"                       # converters first


def nodes_order(d, kind):
    return [n["id"] for n in d["nodes"] if n["kind"] == kind]


def test_ads_scope_real_ips_risk_and_empty_window(c):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    ts = lambda m: (now - timedelta(minutes=m)).isoformat(timespec="milliseconds").replace("+00:00", "Z")  # noqa: E731
    events = []
    for i in range(12):                                                          # one IP hammering an ad: 12 ad landings + 3 tel clicks
        events.append((f"e-bad-{i}", "landing", "9.9.9.9", "h-bad", f"sess-{i}", "gclid-x", "امداد خودرو", "/landing-a", ts(30 + i)))
    for i in range(3):
        events.append((f"e-bad-t{i}", "tel_click", "9.9.9.9", "h-bad", "sess-0", "gclid-x", "امداد خودرو", "/landing-a", ts(10 + i)))
    events.append(("e-ok-1", "landing", "8.8.8.8", "h-ok", "sess-ok", "", "", "/", ts(50)))
    events.append(("e-hb", "heartbeat", "7.7.7.7", "h-idle", "sess-idle", "", "", "/", ts(5)))                   # no landing → not an actor
    with c.eng.begin() as cx:
        for uuid, etype, ip, h, sess, gclid, kw, path, at in events:
            cx.execute(text("INSERT INTO ads_click_events(event_uuid, site_id, event_type, received_at, ip_address, ip_hash, ip_confidence, session_id, visitor_id, gclid, keyword, landing_path, page_path) "
                            "VALUES(:u,'demo.example',:t,:at,:ip,:h,'direct_peer',:s,:s,:g,:k,:p,:p)"), {"u": uuid, "t": etype, "at": at, "ip": ip, "h": h, "s": sess, "g": gclid, "k": kw, "p": path})
    d = c.get("/api/v1/ip-graph", params={"scope": "ads", "site_id": "demo.example", "hours": 24}).json()
    actors = [n for n in d["nodes"] if n["kind"] == "actor"]
    assert [a["label"] for a in actors] == ["9.9.9.9", "8.8.8.8"]                 # riskiest first, idle heartbeat IP left out
    bad = actors[0]
    assert bad["status"] == "risk" and bad["meta"]["risk_score"] >= 50 and bad["meta"]["tel_clicks"] == 3 and "کلیک تماس پشت‌سرهم" in bad["meta"]["risk_reasons"]
    assert actors[1]["status"] == "ok" and d["stats"] == {"actors_total": 2, "shown": 2, "risky": 1, "calls": 3, "landings": 13}
    by = {n["id"]: n for n in d["nodes"]}
    assert by["src:امداد خودرو"]["weight"] == 12 and by["src:بدون نشان تبلیغ"]["weight"] == 1 and by["goal:tel_click"]["weight"] == 3
    risky_edges = [e for e in d["edges"] if e["status"] == "risk"]
    assert {e["kind"] for e in risky_edges} == {"entry", "landing"}
    empty = c.get("/api/v1/ip-graph", params={"scope": "ads", "site_id": "nobody.example", "hours": 24}).json()
    assert empty["nodes"] == [] and empty["edges"] == [] and empty["stats"]["shown"] == 0
    assert c.get("/api/v1/ip-graph", params={"scope": "weird", "site_id": "demo-site"}).status_code == 422
