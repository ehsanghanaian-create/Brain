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


def test_cross_site_command_center_teams_and_ownership(client):
    team = client.post("/api/v1/work/teams", json={"name": "SEO", "color": "#1abb9c"})
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]
    with client.eng.begin() as cx:
        cx.execute(text("UPDATE panel_users SET team_id=:team WHERE id=1"), {"team": team_id})
    created = client.post("/api/v1/sites/demo/work", json={"title": "بررسی صفحه", "team_id": team_id,
        "priority": "critical", "estimated_hours": 4, "owner_id": 1,
        "due_at": "2026-01-01T00:00:00Z", "status": "in_progress"})
    assert created.status_code == 201, created.text
    assert client.post("/api/v1/sites/other/work", json={"title": "سنجش دوم", "team_id": 999}).status_code == 422
    overview = client.get("/api/v1/work/overview").json()
    assert overview["summary"]["total"] == 1
    assert overview["summary"]["overdue"] == 1
    assert overview["summary"]["hours_open"] == 4
    assert overview["items"][0]["team_name"] == "SEO"
    assert overview["by_owner"][0]["name"] == "Operator"
    assert client.get("/api/v1/work/overview?team_id=999").json()["summary"]["total"] == 0
    assert client.get("/api/v1/work/teams").json()[0]["open_work"] == 1


def test_site_project_members_hierarchy_dependencies_time_and_progress(client):
    root = "/api/v1/work/projects/demo"
    assigned = client.put(root + "/members/1", json={"user_id": 1, "responsibility": "lead"})
    assert assigned.status_code == 200 and assigned.json()["responsibility"] == "lead"
    assert client.get(root + "/members").json()[0]["full_name"] == "Operator"
    assert client.put("/api/v1/work/projects/other/members/1", json={"user_id": 2}).status_code == 422

    milestone = client.post(root + "/milestones", json={"title": "فاز فنی", "due_at": "2026-12-01T00:00:00Z"})
    assert milestone.status_code == 201, milestone.text
    milestone_id = milestone.json()["id"]
    updated_milestone = client.patch(root + f"/milestones/{milestone_id}", json={"title": "پایان فاز فنی"})
    assert updated_milestone.status_code == 200 and updated_milestone.json()["title"] == "پایان فاز فنی"
    assert client.post("/api/v1/sites/other/work", json={"title": "کار در پروژهٔ دیگر",
        "milestone_id": milestone_id}).status_code == 422
    base = "/api/v1/sites/demo/work"
    parent = client.post(base, json={"title": "بهبود فنی سایت"}).json()
    prerequisite = client.post(base, json={"title": "بررسی سرچ کنسول", "parent_id": parent["id"],
        "milestone_id": milestone_id, "estimated_hours": 2, "progress_percent": 50,
        "start_at": "2026-11-01T00:00:00Z", "due_at": "2026-11-15T00:00:00Z"})
    assert prerequisite.status_code == 201, prerequisite.text
    first = prerequisite.json()
    dependent = client.post(base, json={"title": "اصلاح صفحات", "parent_id": parent["id"],
        "estimated_hours": 2, "due_at": "2026-11-30T00:00:00Z"}).json()
    assert client.post(base, json={"title": "کار سایت دیگر", "parent_id": 999}).status_code == 422
    assert client.patch(f"{base}/{parent['id']}", json={"parent_id": dependent["id"]}).status_code == 422
    assert client.patch(f"{base}/{first['id']}", json={"start_at": "2026-12-01T00:00:00Z"}).status_code == 422

    dep_url = root + f"/tasks/{dependent['id']}/dependencies"
    assert client.post(dep_url, json={"depends_on_id": first["id"]}).status_code == 201
    other_task = client.post("/api/v1/sites/other/work", json={"title": "کار مستقل سایت دیگر"}).json()
    assert client.post(dep_url, json={"depends_on_id": other_task["id"]}).status_code == 404
    assert client.post(dep_url, json={"depends_on_id": first["id"]}).status_code == 409
    assert client.post(root + f"/tasks/{first['id']}/dependencies", json={"depends_on_id": dependent["id"]}).status_code == 422
    assert client.post(dep_url, json={"depends_on_id": parent["id"]}).status_code == 201
    assert {row["depends_on_id"] for row in client.get(dep_url).json()} == {first["id"], parent["id"]}
    parent_finish = client.patch(f"{base}/{parent['id']}", json={"status": "verified", "owner_id": 1,
        "due_at": "2026-12-01T00:00:00Z", "verification_note": "بررسی شد"})
    assert parent_finish.status_code == 422 and "child work" in parent_finish.text
    dependent_finish = client.patch(f"{base}/{dependent['id']}", json={"status": "verified", "owner_id": 1,
        "verification_note": "بررسی شد"})
    assert dependent_finish.status_code == 422 and "prerequisite work" in dependent_finish.text

    logged = client.post(root + f"/tasks/{first['id']}/time", json={"user_id": 1, "minutes": 90,
        "work_date": "2026-11-02", "note": "تحلیل داده"})
    assert logged.status_code == 201, logged.text
    assert client.get(root + f"/tasks/{first['id']}/time").json()[0]["minutes"] == 90
    projects = client.get("/api/v1/work/projects").json()
    demo = next(row for row in projects if row["site_id"] == "demo")
    assert demo["members"] == 1 and demo["milestones"] == 1
    assert demo["estimated_hours"] == 4 and demo["spent_hours"] == 1.5
    assert demo["progress_percent"] == 25
    assert client.get(root + "/milestones").json()[0]["tasks"] == 1
    assert client.delete(root + "/members/1").status_code == 204
