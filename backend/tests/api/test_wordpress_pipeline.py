"""WordPress → sync → graph pipeline (wiring of existing components): connection auto-queues the job, the job runs the
orchestrator through the existing JobQueue, steps/progress are persisted, WordPress pages/posts become graph nodes without a
crawl, URL is canonical across sync/crawl/graph, REST failures are reported (never silent), credentials never leak."""
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import sites as sites_router
from seo_brain.automation.queue import InProcessJobQueue
from seo_brain.connections import ConnectionsService
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.wordpress.orchestrator import STEPS, WordPressSyncOrchestrator

SID = "demo"


def _fake_wp_sync(eng, fail: bool = False):
    """Stands in for wordpress.sync.sync_wordpress: writes the same tables (posts/categories/taxonomies) + drives the progress hook."""
    calls = {"n": 0, "site": None, "progress": []}

    def run(site, progress):
        calls["n"] += 1; calls["site"] = site
        if fail:
            raise RuntimeError("REST unreachable: ConnectError")
        progress("taxonomies", {}); calls["progress"].append("taxonomies")
        progress("categories", {}); calls["progress"].append("categories")
        with eng.begin() as cx:
            cx.execute(text("INSERT OR REPLACE INTO taxonomies(site_id, slug, name, rest_base, hierarchical, object_types) VALUES(:s,'category','Categories','categories',1,'[\"post\"]')"), {"s": site.site_id})
            for wp, name, slug, parent in ((10, "امداد", "emdad", 0), (11, "رنو", "renault", 10)):
                cx.execute(text("INSERT OR REPLACE INTO categories(site_id, taxonomy, wp_id, name, slug, url, description, parent_wp_id, count, created_at, updated_at) VALUES(:s,'category',:w,:n,:sl,:u,'',:p,2,datetime('now'),datetime('now'))"),
                           {"s": site.site_id, "w": wp, "n": name, "sl": slug, "u": f"{site.wp_url}/category/{slug}/", "p": parent})
        progress("pages", {}); calls["progress"].append("pages")
        with eng.begin() as cx:
            cx.execute(text("INSERT OR REPLACE INTO posts(site_id, wp_id, type, url, slug, title, content_html, content_text, status, word_count, parent_wp_id) VALUES(:s,1,'page',:u,'emdad-renault','امداد رنو','<p>x</p>','x','publish',120,0)"), {"s": site.site_id, "u": f"{site.wp_url}/emdad-renault/"})
        progress("posts", {}); calls["progress"].append("posts")
        with eng.begin() as cx:
            cx.execute(text("INSERT OR REPLACE INTO posts(site_id, wp_id, type, url, slug, title, content_html, content_text, status, word_count, parent_wp_id) VALUES(:s,2,'post',:u,'renault-tips','نکات رنو','<p>y</p>','y','publish',300,0)"), {"s": site.site_id, "u": f"{site.wp_url}/blog/renault-tips/"})
            cx.execute(text("INSERT OR IGNORE INTO post_terms(site_id, post_type, post_wp_id, taxonomy, term_wp_id) VALUES(:s,'post',2,'category',11)"), {"s": site.site_id})
        progress("media", {}); calls["progress"].append("media")
        return {"run_id": "wp-fake", "posts": 2, "types": {"page": 1, "post": 1}, "taxonomies": {"category": 2}, "media": 0, "errors": []}
    return run, calls


def _real_graph_build(dbfile):
    """Use the real GraphBuild on the test DB (no crawl rows) — WordPress items must still become PAGE/POST nodes."""
    def build(site):
        from seo_brain.graph import GraphBuild
        conn = sqlite3.connect(str(dbfile)); conn.row_factory = sqlite3.Row
        try:
            out = GraphBuild(conn, site).build(); conn.commit()
        finally:
            conn.close()
        return {"graph": out}
    return build


@pytest.fixture
def env(tmp_path, monkeypatch):
    dbfile = tmp_path / "wp.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    # the orchestrator's SiteConfig / DB paths must point at the test DB
    monkeypatch.setattr("seo_brain.common.config.database_path", lambda: dbfile)
    from seo_brain.common import config as cfg
    monkeypatch.setattr(cfg, "load_sites", lambda path=None, include_db=True: cfg._sites_from_db())
    q = InProcessJobQueue(sync=True)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng; app.dependency_overrides[deps.job_queue] = lambda: q
    wp_ok = httpx.Response(200, json={"name": "Demo", "namespaces": ["wp/v2"]}, request=httpx.Request("GET", "https://demo.example/wp-json/"))
    app.dependency_overrides[sites_router.connections_service] = lambda: ConnectionsService(eng, wp_fetch=lambda url: wp_ok)
    state = {"fail": False, "crawl_calls": 0}
    wp_sync, calls = _fake_wp_sync(eng)
    wp_sync_fail, _ = _fake_wp_sync(eng, fail=True)

    def crawler(site, max_urls):
        state["crawl_calls"] += 1
        with eng.begin() as cx:   # enrichment row for one WP page (what the real crawler would add)
            cx.execute(text("INSERT OR REPLACE INTO pages(site_id, url, crawl_status, status_code, title, depth, discovered_from, last_crawled, created_at, updated_at) VALUES(:s,:u,'ok',200,'امداد رنو',1,'sitemap',datetime('now'),datetime('now'),datetime('now'))"), {"s": site.site_id, "u": f"{site.wp_url}/emdad-renault/"})
        return {"ok": 1, "crawled": 1}

    def make_orch():
        return WordPressSyncOrchestrator(eng, crawler_factory=crawler, wp_sync=(wp_sync_fail if state["fail"] else wp_sync), graph_build=_real_graph_build(dbfile), probe=lambda url: 200 if url.startswith("https://") else None)
    q.register("wordpress_sync", lambda payload: make_orch().run(payload["site_id"], run_id=payload.get("run_id"), stage=payload.get("stage", "full"), crawl=payload.get("crawl", True), max_urls=payload.get("max_urls"), job_id=payload.get("job_id")))
    c = TestClient(app)
    r = c.post("/api/v1/sites", json={"site_id": SID, "name": "Demo", "canonical_url": "https://demo.example/", "wp_url": "http://demo.example/"}); assert r.status_code == 201, r.text
    return {"client": c, "eng": eng, "q": q, "calls": calls, "state": state, "dbfile": dbfile, "root": tmp_path, "monkeypatch": monkeypatch}


def test_successful_wordpress_connection_queues_sync_job_and_pipeline_runs(env):
    c = env["client"]
    r = c.post(f"/api/v1/sites/{SID}/connections/wordpress/test", json={"property": "https://demo.example"}).json()
    assert r["ok"] and r["detail"]["sync_job"]["status"] == "queued" and r["detail"]["sync_job"]["job_id"].startswith("job-") and r["detail"]["sync_job"]["stage"] == "full"
    # queue is synchronous in tests → the pipeline already ran through the job system
    st = c.get(f"/api/v1/sites/{SID}/wordpress/sync/status").json()
    assert st["status"] == "succeeded" and st["progress"] == 1.0 and st["finished_at"] and st["job"]["status"] == "succeeded" and st["errors"] == []
    assert [s["key"] for s in st["steps"]] == [k for k, _ in STEPS] and all(s["status"] in ("done", "skipped") for s in st["steps"])
    assert env["calls"]["n"] == 1 and env["calls"]["progress"] == ["taxonomies", "categories", "pages", "posts", "media"] and env["state"]["crawl_calls"] == 1
    # items + counters: categories, pages, posts imported; graph nodes created
    assert st["items"]["categories"] == 2 and st["items"]["pages"] == 1 and st["items"]["posts"] == 1 and st["counts"]["graph_nodes"] >= 5
    by = st["counts"]["graph_by_type"]
    assert by.get("SITE") == 1 and by.get("PAGE") == 1 and by.get("POST") == 1 and by.get("CATEGORY") == 2
    # relations: CONTENT BELONGS_TO CATEGORY, site HAS_PAGE/HAS_POST, category tree
    with env["eng"].connect() as cx:
        et = {r_[0]: r_[1] for r_ in cx.execute(text("SELECT edge_type, COUNT(*) FROM graph_edges WHERE site_id=:s GROUP BY edge_type"), {"s": SID}).all()}
    assert et.get("BELONGS_TO", 0) >= 2 and et.get("HAS_PAGE") == 1 and et.get("HAS_POST") == 1 and et.get("HAS_CATEGORY") == 2
    # graph API sees it (same tables) — PAGE node exists although only the enrichment crawl touched one page
    nodes = c.get(f"/api/v1/sites/{SID}/graph/nodes?types=PAGE,POST&limit=10").json()
    assert {n["type"] for n in nodes} == {"PAGE", "POST"}


def test_canonical_url_one_resolver_for_sync_crawl_graph(env):
    c = env["client"]
    c.post(f"/api/v1/sites/{SID}/wordpress/sync", json={"crawl": True})
    site = c.get(f"/api/v1/sites/{SID}").json()
    assert site["wp_url"] == "https://demo.example"                         # http://demo.example/ → https, no trailing slash (probe said https works)
    assert env["calls"]["site"].wp_url == "https://demo.example"             # the SAME value reached the sync (and crawler/graph use the same SiteConfig)
    st = c.get(f"/api/v1/sites/{SID}/wordpress/sync/status").json()
    resolve = next(s for s in st["steps"] if s["key"] == "resolve")
    assert resolve["items"]["wp_url"] == "https://demo.example" and resolve["items"]["scheme_switched"] is True
    with env["eng"].connect() as cx:
        urls = [r_[0] for r_ in cx.execute(text("SELECT url FROM graph_nodes WHERE site_id=:s AND node_type IN ('PAGE','POST')"), {"s": SID}).all()]
    assert all(u.startswith("https://demo.example/") for u in urls)


def test_manual_sync_status_rebuild_and_guards(env):
    c = env["client"]
    # no wp_url → 409
    c.post("/api/v1/sites", json={"site_id": "nowp", "name": "N", "canonical_url": "https://n.example/"})
    assert c.post("/api/v1/sites/nowp/wordpress/sync", json={}).status_code == 409
    # never synced → status 'never' with zero counts
    assert c.get("/api/v1/sites/nowp/wordpress/sync/status").json()["status"] == "never"
    # manual start → 202 queued; then graph rebuild (graph_only) → 202, steps only build_graph
    r = c.post(f"/api/v1/sites/{SID}/wordpress/sync", json={"crawl": False}); assert r.status_code == 202 and r.json()["status"] == "queued"
    st = c.get(f"/api/v1/sites/{SID}/wordpress/sync/status").json()
    assert st["status"] == "succeeded" and next(s for s in st["steps"] if s["key"] == "crawl")["status"] == "skipped" and env["state"]["crawl_calls"] == 0
    r2 = c.post(f"/api/v1/sites/{SID}/graph/rebuild"); assert r2.status_code == 202 and r2.json()["stage"] == "graph_only"
    st2 = c.get(f"/api/v1/sites/{SID}/wordpress/sync/status").json()
    assert st2["stage"] == "graph_only" and [s["key"] for s in st2["steps"]] == ["build_graph", "knowledge_pack"] and st2["status"] == "succeeded" and st2["counts"]["graph_by_type"].get("PAGE") == 1
    # already-running guard (simulate a running state)
    orch = WordPressSyncOrchestrator(env["eng"]); stq = orch.create(SID); stq.status = "running"; orch._persist(stq)
    r3 = c.post(f"/api/v1/sites/{SID}/wordpress/sync", json={}).json(); assert r3["status"] == "already_running" and r3["run_id"] == stq.run_id
    # connection test with auto_sync=false does not queue
    r4 = c.post(f"/api/v1/sites/{SID}/connections/wordpress/test", json={"property": "https://demo.example", "auto_sync": False}).json()
    assert "sync_job" not in r4["detail"]


def test_failed_rest_is_reported_never_silent_and_credentials_never_leak(env):
    c = env["client"]
    # per-site Application Password in SecretStore must never appear in status / sync_runs
    from seo_brain.core.secrets import SecretStore
    from seo_brain.wordpress import auth as wp_auth
    store = SecretStore(env["root"] / "secrets"); env["monkeypatch"].setattr(wp_auth, "get_secret_store", lambda: store)
    wp_auth.save_site_auth(SID, "editor", "aaaa bbbb cccc dddd eeee ffff")
    env["state"]["fail"] = True
    r = c.post(f"/api/v1/sites/{SID}/wordpress/sync", json={}); assert r.status_code == 202
    st = c.get(f"/api/v1/sites/{SID}/wordpress/sync/status").json()
    assert st["status"] == "failed" and st["job"]["status"] == "failed" and any("REST unreachable" in e for e in st["errors"])
    assert {s["key"]: s["status"] for s in st["steps"]}["categories"] == "failed" and next(s for s in st["steps"] if s["key"] == "build_graph")["status"] == "pending"
    blob = json.dumps(st, ensure_ascii=False)
    with env["eng"].connect() as cx:
        notes = " ".join(r_[0] or "" for r_ in cx.execute(text("SELECT notes FROM sync_runs WHERE site_id=:s"), {"s": SID}).all())
    assert "aaaa bbbb" not in blob and "aaaa bbbb" not in notes and "editor:" not in notes
    # planner category sync: REST failure explicit + snapshot clearly labelled (no silent empty)
    from seo_brain.api.routers import content_plans as cp_router
    from seo_brain.brain.planner import PlannerService
    def boom(url, params): raise RuntimeError("ConnectError: boom")
    c.app.dependency_overrides[cp_router.svc] = lambda: PlannerService(env["eng"], category_fetch=boom)
    rr = c.post(f"/api/v1/sites/{SID}/content-plans/categories/sync?brain=false")
    body = rr.json()
    assert rr.status_code == 409 and body["error"]["code"] == "wordpress_not_configured"
    rr2 = c.post(f"/api/v1/sites/{SID}/content-plans/categories/sync?brain=true").json()
    assert rr2["wordpress"] == {"source": "wordpress_rest", "status": "failed", "reason": rr2["wordpress"]["reason"]} and "ConnectError" in rr2["wordpress"]["reason"]
    assert rr2["wordpress_snapshot"]["source"] == "snapshot" and rr2["wordpress_snapshot"]["status"] in ("ok", "empty")


def test_persist_never_drops_attached_job_id(env):
    """The job thread may start (and persist) before the API attaches the job id — a later persist with job_id=None must keep it."""
    from seo_brain.wordpress.orchestrator import PipelineState
    orch = WordPressSyncOrchestrator(env["eng"])
    st = orch.create(SID, stage="graph_only")
    orch.attach_job(st.run_id, "job-abc123")
    stale = PipelineState(run_id=st.run_id, site_id=SID, stage="graph_only", status="running", steps=st.steps, job_id=None)
    orch._persist(stale)
    assert orch.latest(SID)["job_id"] == "job-abc123" and orch.latest(SID)["status"] == "running"
