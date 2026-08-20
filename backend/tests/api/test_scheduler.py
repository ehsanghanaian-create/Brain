"""Sync scheduler (thin timer over the existing jobs + sync_runs): stale-run recovery unlocks is_running,
due-planning per site/integration, existing jobs enqueued with a per-tick cap, settings in site_settings,
auto-sync API — no new tables, no new sync logic."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import sites as sites_router
from seo_brain.automation.queue import InProcessJobQueue
from seo_brain.automation.scheduler import (auto_sync_settings, plan_for_site, recover_stale_runs, run_tick,
                                            save_auto_sync_settings)
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.gsc.pipeline import GscPipeline
from seo_brain.wordpress.orchestrator import WordPressSyncOrchestrator


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@pytest.fixture
def env(tmp_path, monkeypatch):
    eng = make_engine("sqlite:///" + (tmp_path / "s.db").as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("seo_brain.connections.service._google_client_configured", lambda: True)
    monkeypatch.setattr("seo_brain.connections.service._token_info",
                        lambda: {"present": True, "scopes": ["https://www.googleapis.com/auth/webmasters.readonly",
                                                             "https://www.googleapis.com/auth/analytics.readonly"]})
    q = InProcessJobQueue(sync=True)
    ran: list[tuple[str, str]] = []
    for jt in ("wordpress_sync", "gsc_sync", "ga4_sync"):
        q.register(jt, lambda payload, jt=jt: ran.append((jt, payload["site_id"])) or {"ok": True})
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng; app.dependency_overrides[deps.job_queue] = lambda: q
    c = TestClient(app)
    return {"client": c, "eng": eng, "q": q, "ran": ran}


def _mk_site(c, sid, **extra):
    r = c.post("/api/v1/sites", json={"site_id": sid, "name": sid, "canonical_url": f"https://{sid}.example/", **extra})
    assert r.status_code == 201, r.text


def _seed_success(eng, sid, source, hours_ago):
    ts = _iso(datetime.now(timezone.utc) - timedelta(hours=hours_ago))
    with eng.begin() as cx:
        cx.execute(text("INSERT INTO sync_runs(run_id, site_id, source, started_at, finished_at, status, notes) "
                        "VALUES(:r,:s,:src,:t,:t,'succeeded','{}')"),
                   {"r": f"seed-{sid}-{source}-{hours_ago}", "s": sid, "src": source, "t": ts})


def test_stale_recovery_unblocks_is_running(env):
    eng = env["eng"]
    env["client"].post("/api/v1/sites", json={"site_id": "demo", "name": "D", "canonical_url": "https://d.example/", "wp_url": "https://d.example/"})
    orch = WordPressSyncOrchestrator(eng)
    st = orch.create("demo", stage="full")
    # simulate a crash 3 hours ago: state stuck in queued
    old = _iso(datetime.now(timezone.utc) - timedelta(hours=3))
    with eng.begin() as cx:
        cx.execute(text("UPDATE sync_runs SET started_at=:t WHERE run_id=:r"), {"t": old, "r": st.run_id})
    assert orch.is_running("demo") is True
    fixed = recover_stale_runs(eng, stale_after_minutes=120)
    assert fixed == 1
    assert orch.is_running("demo") is False                     # future syncs unlocked
    latest = orch.latest("demo")
    assert latest["status"] == "failed" and any("interrupted" in e for e in latest["errors"])
    with eng.connect() as cx:
        assert cx.execute(text("SELECT status FROM sync_runs WHERE run_id=:r"), {"r": st.run_id}).scalar() == "failed"
    # a fresh run (started now) is NOT recovered
    st2 = GscPipeline(eng).create("demo")
    assert recover_stale_runs(eng, stale_after_minutes=120) == 0
    assert GscPipeline(eng).latest("demo")["run_id"] == st2.run_id


def test_plan_due_logic_and_settings(env):
    c, eng = env["client"], env["eng"]
    _mk_site(c, "s1", wp_url="https://s1.example/", gsc_property="sc-domain:s1.example", ga4_property="471988572")
    # never synced → everything configured is due now
    p = plan_for_site(eng, "s1")
    assert p["enabled"] is True and p["interval_hours"] == 24
    assert all(p["sources"][k]["due"] for k in ("wordpress", "gsc", "ga4"))
    # recent success → not due; old success → due again
    _seed_success(eng, "s1", "wordpress_pipeline", hours_ago=1)
    _seed_success(eng, "s1", "gsc_pipeline", hours_ago=30)
    p = plan_for_site(eng, "s1")
    assert p["sources"]["wordpress"]["due"] is False and p["sources"]["wordpress"]["next_at"]
    assert p["sources"]["gsc"]["due"] is True
    # disabled via settings (existing site_settings table) → nothing due, next_at hidden
    save_auto_sync_settings(eng, "s1", enabled=False)
    p = plan_for_site(eng, "s1")
    assert not any(v["due"] for v in p["sources"].values()) and p["sources"]["gsc"]["next_at"] is None
    assert auto_sync_settings(eng, "s1")["enabled"] is False
    # unconfigured integrations are never due
    _mk_site(c, "s2")                                            # no wp/gsc/ga4
    assert not any(v["due"] for v in plan_for_site(eng, "s2")["sources"].values())


def test_tick_enqueues_existing_jobs_with_cap_and_no_duplicates(env):
    c, eng, q, ran = env["client"], env["eng"], env["q"], env["ran"]
    for sid in ("a1", "a2", "a3"):
        _mk_site(c, sid, wp_url=f"https://{sid}.example/")
    out = run_tick(eng, q, max_sites=2)
    assert out["sites_started"] == 2                             # per-tick cap respected
    assert [x for x in ran if x[0] == "wordpress_sync"] == [("wordpress_sync", "a1"), ("wordpress_sync", "a2")]
    # sync queue ran inline; the runs did not persist success (handlers are fakes) → a queued/running guard test:
    st = WordPressSyncOrchestrator(eng).create("a3", stage="full")   # a3 now "running" → tick must skip it
    ran.clear()
    out = run_tick(eng, q, max_sites=5)
    assert ("wordpress_sync", "a3") not in ran                   # already_running guard prevented a duplicate
    with eng.begin() as cx:                                       # cleanup for clarity
        cx.execute(text("UPDATE sync_runs SET status='failed' WHERE run_id=:r"), {"r": st.run_id})


def test_auto_sync_api(env):
    c = env["client"]
    _mk_site(c, "api1", gsc_property="sc-domain:api1.example")
    d = c.get("/api/v1/sites/api1/auto-sync").json()
    assert d["enabled"] is True and d["sources"]["gsc"]["configured"] is True and d["sources"]["wordpress"]["configured"] is False
    d = c.put("/api/v1/sites/api1/auto-sync", json={"enabled": False, "interval_hours": 48}).json()
    assert d["enabled"] is False and d["interval_hours"] == 48
    assert c.get("/api/v1/sites/api1/auto-sync").json()["interval_hours"] == 48
    # bounds
    assert c.put("/api/v1/sites/api1/auto-sync", json={"interval_hours": 999}).status_code == 422


def test_scheduler_disabled_under_pytest():
    """create_app's lifespan must not start the background thread inside tests (PYTEST_CURRENT_TEST guard)."""
    from seo_brain.automation.scheduler import SyncScheduler
    assert SyncScheduler.enabled() is False
    import threading
    with TestClient(create_app()):                                # lifespan runs here
        assert not any(t.name == "sync-scheduler" for t in threading.enumerate())
