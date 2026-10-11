"""An issue stays identifiable across runs; a partial crawl cannot resolve it."""
import sqlite3
import shutil

from fastapi.testclient import TestClient

from seo_brain.analysis.issue_cases import reconcile_issue_cases
from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import MIGRATIONS_DIR, migrate, migrate_sqlite


def test_issue_case_lifecycle_and_site_scoping(tmp_path, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    path = tmp_path / "cases.db"
    eng = make_engine("sqlite:///" + path.as_posix())
    migrate(eng)
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app)
    for site in ("one", "two"):
        assert client.post("/api/v1/sites", json={"site_id": site, "name": site, "canonical_url": f"https://{site}.example/"}).status_code == 201
    conn = sqlite3.connect(path)
    try:
        conn.execute("INSERT INTO seo_problems(site_id,problem_type,severity,url,related_url,detail,run_id) VALUES('one','missing_h1','medium','https://one.example/a/','','{\"count\":0}','analysis-1')")
        assert reconcile_issue_cases(conn, "one", "analysis-1", allow_resolve=False) == {"opened": 1, "reopened": 0, "resolved": 0, "observed": 1}
        assert reconcile_issue_cases(conn, "one", "analysis-1", allow_resolve=False)["observed"] == 0
        conn.commit()
        base = "/api/v1/sites/one/issues"
        first = client.get(base).json()
        assert first["counts"] == {"open": 1, "resolved": 0}
        case_id = first["items"][0]["id"]
        assert first["items"][0]["detail"] == {"count": 0}
        assert client.get("/api/v1/sites/two/issues").json()["total"] == 0
        assert client.get(f"/api/v1/sites/two/issues/{case_id}").status_code == 404
        conn.execute("DELETE FROM seo_problems WHERE site_id='one'")
        assert reconcile_issue_cases(conn, "one", "analysis-2", allow_resolve=False)["resolved"] == 0
        conn.commit()
        assert client.get(base).json()["counts"]["open"] == 1
        assert reconcile_issue_cases(conn, "one", "analysis-3", allow_resolve=True)["resolved"] == 1
        conn.commit()
        assert client.get(base).json()["total"] == 0
        assert client.get(base, params={"status": "resolved"}).json()["total"] == 1
        conn.execute("INSERT INTO seo_problems(site_id,problem_type,severity,url,related_url,detail,run_id) VALUES('one','missing_h1','high','https://one.example/a/','','{}','analysis-4')")
        assert reconcile_issue_cases(conn, "one", "analysis-4", allow_resolve=False)["reopened"] == 1
        conn.commit()
        current = client.get(base).json()["items"][0]
        assert current["id"] == case_id and current["seen_count"] == 2 and current["severity"] == "high"
        detail = client.get(f"{base}/{case_id}").json()
        assert [event["event_type"] for event in detail["events"]] == ["reopened", "resolved", "opened"]
        assert len(detail["observations"]) == 2
    finally:
        conn.close()


def test_existing_problem_snapshot_is_backfilled_on_migration(tmp_path):
    old_migrations = tmp_path / "old_migrations"
    old_migrations.mkdir()
    for source in MIGRATIONS_DIR.glob("*.sql"):
        if source.name < "0021_issue_cases.sql":
            shutil.copy2(source, old_migrations / source.name)
    conn = sqlite3.connect(tmp_path / "old.db")
    try:
        migrate_sqlite(conn, directory=old_migrations)
        conn.execute("INSERT INTO sites(site_id,name,canonical_url) VALUES('one','One','https://one.example/')")
        conn.execute("INSERT INTO seo_problems(site_id,problem_type,severity,url,related_url,detail,run_id) VALUES('one','missing_h1','medium','https://one.example/a/','','{}','old-run')")
        conn.commit()
        assert "0021" in migrate_sqlite(conn)
        case = conn.execute("SELECT status,seen_count,last_run_id FROM issue_cases WHERE site_id='one'").fetchone()
        assert case == ("open", 1, "old-run")
        assert conn.execute("SELECT COUNT(*) FROM issue_case_observations").fetchone()[0] == 1
        assert migrate_sqlite(conn) == []
    finally:
        conn.close()
