"""Work items stay within their site, require ownership for active work, and keep an event trail."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import sites as sites_router
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate


@pytest.fixture
def client(tmp_path, monkeypatch):
    eng = make_engine("sqlite:///" + (tmp_path / "work.db").as_posix())
    migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    c = TestClient(app)
    for sid in ("demo", "other"):
        assert c.post("/api/v1/sites", json={"site_id": sid, "name": sid,
            "canonical_url": f"https://{sid}.example/"}).status_code == 201
    with eng.begin() as cx:
        cx.execute(text("""INSERT INTO panel_users(full_name,email,role,active,created_at,updated_at)
            VALUES ('Operator','operator@example.com','analyst',1,'2026-01-01','2026-01-01')"""))
        cx.execute(text("""INSERT INTO seo_problems(site_id,problem_type,severity,url)
            VALUES ('demo','orphan','high','https://demo.example/a/')"""))
    c.eng = eng
    return c


def test_work_lifecycle_and_events(client):
    base = "/api/v1/sites/demo/work"
    created = client.post(base, json={"title": "اصلاح صفحه یتیم", "kind": "issue", "source_id": 1,
        "url": "https://demo.example/a/"})
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["status"] == "new" and item["owner_id"] is None
    assert client.post(base, json={"title": "اصلاح صفحه یتیم", "kind": "issue", "source_id": 1}).status_code == 409
    assert client.patch(f"{base}/{item['id']}", json={"status": "in_progress"}).status_code == 422
    assert client.patch(f"{base}/{item['id']}", json={"title": None}).status_code == 422
    assert client.patch(f"{base}/{item['id']}", json={"status": "rejected"}).status_code == 422
    assert client.patch(f"{base}/{item['id']}", json={"owner_id": 1,
        "due_at": "2026-10-20T12:00:00", "status": "in_progress"}).status_code == 422
    changed = client.patch(f"{base}/{item['id']}", json={"status": "in_progress", "owner_id": 1,
        "due_at": "2026-10-20T12:00:00Z", "note": "در حال بررسی"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["owner_id"] == 1
    assert client.patch(f"{base}/{item['id']}", json={"status": "verified"}).status_code == 422
    done = client.patch(f"{base}/{item['id']}", json={"status": "verified", "verification_note": "خزش دوباره تأیید شد"})
    assert done.status_code == 200
    events = client.get(f"{base}/{item['id']}/events").json()
    assert [event["event_type"] for event in events] == ["created", "updated", "updated"]
    assert events[1]["note"] == "در حال بررسی"
    assert client.get(base).json()["summary"]["unassigned"] == 0


def test_work_site_isolation_and_source_validation(client):
    base = "/api/v1/sites/demo/work"
    assert client.post("/api/v1/sites/other/work", json={"title": "مسئلهٔ سایت دیگر",
        "kind": "issue", "source_id": 1}).status_code == 422
    item = client.post(base, json={"title": "کار دستی"}).json()
    assert client.get("/api/v1/sites/other/work").json()["total"] == 0
    assert client.patch(f"/api/v1/sites/other/work/{item['id']}", json={"status": "triaged"}).status_code == 404
    assert client.get(f"/api/v1/sites/other/work/{item['id']}/events").status_code == 404
