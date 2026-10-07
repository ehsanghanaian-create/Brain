"""Work items stay within their project and keep an event trail."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import sites as sites_router
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.api.panel_auth import hash_password


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
    assert client.patch(f"{base}/{item['id']}", json={"status": "in_progress"}).status_code == 200
    assert client.patch(f"{base}/{item['id']}", json={"title": None}).status_code == 422
    assert client.patch(f"{base}/{item['id']}", json={"status": "rejected"}).status_code == 422
    assert client.patch(f"{base}/{item['id']}", json={"owner_id": 1,
        "due_at": "2026-10-20T12:00:00", "status": "in_progress"}).status_code == 422
    changed = client.patch(f"{base}/{item['id']}", json={"status": "in_progress", "owner_id": 1,
        "due_at": "2026-10-20T12:00:00Z", "note": "در حال بررسی"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["owner_id"] == 1
    done = client.patch(f"{base}/{item['id']}", json={"status": "verified"})
    assert done.status_code == 200
    events = client.get(f"{base}/{item['id']}/events").json()
    assert [event["event_type"] for event in events] == ["created", "updated", "updated", "updated"]
    assert events[2]["note"] == "در حال بررسی"
    assert client.get(base).json()["summary"]["unassigned"] == 0


def test_work_site_isolation_and_source_validation(client):
    base = "/api/v1/sites/demo/work"
    assert client.post("/api/v1/sites/other/work", json={"title": "مسئلهٔ سایت دیگر",
        "kind": "issue", "source_id": 1}).status_code == 422
    item = client.post(base, json={"title": "کار دستی"}).json()
    assert client.get("/api/v1/sites/other/work").json()["total"] == 0
    assert client.patch(f"/api/v1/sites/other/work/{item['id']}", json={"status": "triaged"}).status_code == 404
    assert client.get(f"/api/v1/sites/other/work/{item['id']}/events").status_code == 404


def test_board_order_and_checklist_persist_with_site_boundary(client):
    base = "/api/v1/sites/demo/work"
    first = client.post(base, json={"title": "Audit landing pages"}).json()
    second = client.post(base, json={"title": "Prepare content brief"}).json()
    assert second["board_order"] > first["board_order"]
    moved = client.patch(f"{base}/{second['id']}", json={"board_order": first["board_order"] - 100})
    assert moved.status_code == 200
    assert moved.json()["board_order"] < first["board_order"]
    assigned = client.patch(f"{base}/{second['id']}", json={"status": "assigned", "owner_id": 1,
        "due_at": "2026-12-01T00:00:00Z", "board_order": 512})
    assert assigned.status_code == 200 and assigned.json()["status"] == "assigned"
    assert next(row for row in client.get(base).json()["items"] if row["id"] == second["id"])["board_order"] == 512
    assert client.patch(f"{base}/{second['id']}", json={"board_order": None}).status_code == 422
    check = client.post(f"{base}/{first['id']}/checklist", json={"title": "Inspect indexability"})
    assert check.status_code == 201 and check.json()["done"] is False
    checked = client.patch(f"{base}/{first['id']}/checklist/{check.json()['id']}", json={"done": True})
    assert checked.status_code == 200 and checked.json()["done"] is True
    events = client.get(f"{base}/{first['id']}/events").json()
    assert [event["event_type"] for event in events][-2:] == ["checklist_added", "checklist_updated"]
    overview = client.get("/api/v1/work/overview?site_id=demo").json()
    card = next(row for row in overview["items"] if row["id"] == first["id"])
    assert card["checklist_total"] == 1 and card["checklist_done"] == 1
    assert client.get(f"/api/v1/sites/other/work/{first['id']}/checklist").status_code == 404
    assert client.patch(f"/api/v1/sites/other/work/{first['id']}/checklist/{check.json()['id']}", json={"done": False}).status_code == 404


def test_project_labels_and_atomic_bulk_work_updates(client):
    base = "/api/v1/sites/demo/work"
    first = client.post(base, json={"title": "Audit crawl paths"}).json()
    second = client.post(base, json={"title": "Review content map"}).json()
    foreign = client.post("/api/v1/sites/other/work", json={"title": "Other project work"}).json()
    label = client.post(base + "/labels", json={"name": "Technical SEO", "color": "#2563eb"})
    assert label.status_code == 201
    label_id = label.json()["id"]
    assert client.post(base + "/labels", json={"name": "Technical SEO"}).status_code == 409
    assert client.put(f"{base}/{first['id']}/labels/{label_id}").status_code == 200
    assert client.put(f"{base}/{first['id']}/labels/{label_id}").status_code == 200
    assert [row["id"] for row in client.get(f"{base}/{first['id']}/labels").json()] == [label_id]
    assert client.put(f"/api/v1/sites/other/work/{foreign['id']}/labels/{label_id}").status_code == 404
    overview = client.get("/api/v1/work/overview?site_id=demo").json()
    assert next(row for row in overview["items"] if row["id"] == first["id"])["labels"][0]["name"] == "Technical SEO"
    first_page = client.get('/api/v1/work/board/demo?limit=1').json()
    assert len(first_page['items']) == 1 and first_page['next_after_id'] == first['id']
    second_page = client.get(f'/api/v1/work/board/demo?limit=1&after_id={first_page["next_after_id"]}').json()
    assert second_page['items'][0]['id'] == second['id'] and second_page['next_after_id'] is None
    invalid = client.post(base + "/bulk", json={"item_ids": [first["id"], foreign["id"]],
        "patch": {"priority": "critical"}})
    assert invalid.status_code == 404
    assert all(row["priority"] == "normal" for row in client.get(base).json()["items"])
    applied = client.post(base + "/bulk", json={"item_ids": [first["id"], second["id"]],
        "patch": {"priority": "high", "owner_id": 1}})
    assert applied.status_code == 200 and applied.json()["updated"] == 2
    assert all(row["priority"] == "high" and row["owner_id"] == 1 for row in client.get(base).json()["items"])
    assert client.delete(f"{base}/{first['id']}/labels/{label_id}").status_code == 204
    assert client.get(f"{base}/{first['id']}/labels").json() == []


def test_typed_project_fields_validate_and_persist(client):
    base = '/api/v1/sites/demo/work'
    item = client.post(base, json={'title': 'Measure SEO impact'}).json()
    other = client.post('/api/v1/sites/other/work', json={'title': 'Unrelated task'}).json()
    choice = client.post(base + '/fields', json={'name': 'Action type', 'field_type': 'select',
        'options': ['Technical', 'Content']})
    assert choice.status_code == 201
    field_id = choice.json()['id']
    assert client.post(base + '/fields', json={'name': 'Action type', 'field_type': 'text'}).status_code == 409
    value_url = f"{base}/{item['id']}/fields/{field_id}"
    assert client.put(value_url, json={'value': 'Unknown'}).status_code == 422
    assert client.put(f"/api/v1/sites/other/work/{other['id']}/fields/{field_id}",
        json={'value': 'Technical'}).status_code == 404
    assert client.put(value_url, json={'value': 'Technical'}).status_code == 200
    assert client.get(f"{base}/{item['id']}/fields").json()[0]['value'] == 'Technical'
    numeric = client.post(base + '/fields', json={'name': 'Budget', 'field_type': 'number'}).json()
    number_url = f"{base}/{item['id']}/fields/{numeric['id']}"
    assert client.put(number_url, json={'value': 'not a number'}).status_code == 422
    assert client.put(number_url, json={'value': 12.5}).json()['value'] == 12.5
    board_item = next(row for row in client.get('/api/v1/work/board/demo').json()['items'] if row['id'] == item['id'])
    assert any(field['name'] == 'Budget' and field['value'] == 12.5 for field in board_item['custom_fields'])
    calendar = client.post(base + '/fields', json={'name': 'Review date', 'field_type': 'date'}).json()
    date_url = f"{base}/{item['id']}/fields/{calendar['id']}"
    assert client.put(date_url, json={'value': '2026-02-31'}).status_code == 422
    assert client.put(date_url, json={'value': '2026-12-31'}).status_code == 200
    assert client.put(value_url, json={'value': None}).status_code == 200
    assert client.get(f"{base}/{item['id']}/fields").json()[0]['value'] is None
    events = client.get(f"{base}/{item['id']}/events").json()
    assert 'field_updated' in [event['event_type'] for event in events]
    assert client.delete(f"{base}/fields/{numeric['id']}").status_code == 204
    assert all(field['id'] != numeric['id'] for field in client.get(f"{base}/{item['id']}/fields").json())


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


def test_manual_project_assignment_priority_archive_and_profile(client):
    with client.eng.begin() as cx:
        cx.execute(text("UPDATE panel_users SET username='analyst',password_hash=:hash WHERE id=1"),
                   {"hash": hash_password("analyst-password")})
        cx.execute(text("""INSERT INTO panel_users(username,full_name,email,role,active,is_superadmin,password_hash,created_at,updated_at)
            VALUES ('manager','Manager','manager@example.com','admin',1,1,:hash,'2026-01-01','2026-01-01')"""),
            {"hash": hash_password("manager-password")})
    admin_login = client.post("/api/v1/auth/login", json={"username": "manager", "password": "manager-password"})
    assert admin_login.status_code == 200, admin_login.text
    admin = {"Authorization": "Bearer " + admin_login.json()["token"]}
    analyst_login = client.post("/api/v1/auth/login", json={"username": "analyst", "password": "analyst-password"})
    assert analyst_login.status_code == 200, analyst_login.text
    analyst = {"Authorization": "Bearer " + analyst_login.json()["token"]}

    created = client.post("/api/v1/work/projects", json={"name": "SEO Brain"}, headers=admin)
    assert created.status_code == 201, created.text
    project = created.json()["site_id"]
    assert project not in {site["site_id"] for site in client.get("/api/v1/sites", headers=admin).json()}
    assert next(row for row in client.get("/api/v1/work/projects", headers=admin).json()
                if row["site_id"] == project)["kind"] == "manual"
    assert client.patch(f"/api/v1/work/projects/{project}", headers=analyst,
                        json={"name": "Changed by outsider"}).status_code == 403
    assert client.patch(f"/api/v1/work/projects/{project}", headers=admin,
                        json={"name": "  "}).status_code == 422
    assert client.patch("/api/v1/work/projects/missing", headers=admin,
                        json={"name": "Missing project"}).status_code == 404
    assert client.put("/api/v1/work/projects/demo/members/1", headers=admin,
                      json={"user_id": 1, "responsibility": "lead"}).status_code == 200
    renamed_site = client.patch("/api/v1/work/projects/demo", headers=analyst,
                                json={"name": "  Demo workflow  "})
    assert renamed_site.status_code == 200 and renamed_site.json()["name"] == "Demo workflow"
    assert renamed_site.json()["kind"] == "site" and renamed_site.json()["site_id"] == "demo"
    assert client.put("/api/v1/work/projects/demo/members/2", headers=admin,
                      json={"user_id": 2, "responsibility": "lead"}).status_code == 200
    demo_project = next(row for row in client.get("/api/v1/work/projects", headers=admin).json()
                        if row["site_id"] == "demo")
    assert demo_project["lead_id"] == 2
    demo_members = client.get("/api/v1/work/projects/demo/members", headers=admin).json()
    assert next(row for row in demo_members if row["user_id"] == 1)["responsibility"] == "contributor"
    base = f"/api/v1/sites/{project}/work"
    urgent = client.post(base, headers=admin, json={"title": "Urgent task", "priority": "critical", "owner_id": 1})
    assert urgent.status_code == 201, urgent.text
    task_id = urgent.json()["id"]
    assert urgent.json()["created_by_id"] == 2
    assert next(row for row in client.get(f"/api/v1/work/projects/{project}/members", headers=admin).json()
                if row["user_id"] == 1)["responsibility"] == "contributor"
    ordinary = client.post(base, headers=admin, json={"title": "Next task", "priority": "normal", "owner_id": 1})
    assert ordinary.status_code == 201, ordinary.text
    renamed_manual = client.patch(f"/api/v1/work/projects/{project}", headers=admin,
                                  json={"name": "  SEO Brain Operations  "})
    assert renamed_manual.status_code == 200 and renamed_manual.json()["name"] == "SEO Brain Operations"
    assert renamed_manual.json()["kind"] == "manual" and renamed_manual.json()["site_id"] == project
    assert client.get(f"/api/v1/sites/{project}", headers=admin).json()["name"] == "SEO Brain Operations"
    assert next(row for row in client.get("/api/v1/work/projects", headers=analyst).json()
                if row["site_id"] == project)["name"] == "SEO Brain Operations"
    assert {task["id"] for task in client.get(base, headers=admin).json()["items"]} == {task_id, ordinary.json()["id"]}
    board = client.get("/api/v1/work/board/all", headers=analyst)
    assert board.status_code == 200, board.text
    assert {row["priority"] for row in board.json()["items"]} == {"critical", "normal"}
    assert next(row for row in board.json()["items"] if row["id"] == task_id)["created_by_name"] == "Manager"
    notifications = client.get("/api/v1/auth/notifications", headers=analyst).json()
    assert notifications["unread"] == 2
    assert client.post(f"/api/v1/auth/notifications/{notifications['items'][0]['id']}/read", headers=analyst).status_code == 200
    assert client.get("/api/v1/auth/notifications", headers=analyst).json()["unread"] == 1
    step = client.post(f"{base}/{task_id}/checklist", headers=analyst, json={"title": "Check page indexability"})
    assert step.status_code == 201, step.text
    preview = next(row for row in client.get("/api/v1/work/board/all", headers=analyst).json()["items"] if row["id"] == task_id)
    assert preview["checklist_total"] == 1 and preview["checklist"][0]["title"] == "Check page indexability"
    assert client.patch(f"{base}/{task_id}/checklist/{step.json()['id']}", headers=admin,
                        json={"done": True}).status_code == 200
    assert client.patch(f"{base}/{task_id}/checklist/{step.json()['id']}", headers=analyst,
                        json={"done": True}).status_code == 200
    preview = next(row for row in client.get("/api/v1/work/board/all", headers=analyst).json()["items"] if row["id"] == task_id)
    assert preview["checklist_done"] == 1 and preview["checklist"][0]["done"] is True
    project_preview = next(row for row in client.get(f"/api/v1/work/board/{project}", headers=admin).json()["items"] if row["id"] == task_id)
    assert project_preview["checklist"][0]["done"] is True
    overview_preview = next(row for row in client.get("/api/v1/work/overview", headers=admin).json()["items"] if row["id"] == task_id)
    assert overview_preview["checklist"][0]["title"] == "Check page indexability"

    assert client.patch(f"{base}/{task_id}", headers=analyst, json={"status": "verified"}).status_code == 200
    assert any(row["id"] == task_id for row in client.get("/api/v1/work/archive?kind=completed", headers=admin).json())
    assert client.delete(f"{base}/{task_id}", headers=analyst).status_code == 403
    assert client.delete(f"{base}/{task_id}", headers=admin).status_code == 200
    assert all(row["id"] != task_id for row in client.get("/api/v1/work/archive?kind=completed", headers=admin).json())
    assert any(row["id"] == task_id for row in client.get("/api/v1/work/archive?kind=deleted", headers=admin).json())
    assert client.delete(f"{base}/{ordinary.json()['id']}", headers=analyst).status_code == 403
    assert client.delete(f"{base}/{ordinary.json()['id']}", headers=admin).status_code == 200
    assert any(row["id"] == ordinary.json()["id"] for row in client.get("/api/v1/work/archive?kind=deleted", headers=admin).json())
    assert all(row["id"] != ordinary.json()["id"] for row in client.get(f"/api/v1/work/board/{project}", headers=admin).json()["items"])
    assert client.post(f"{base}/{ordinary.json()['id']}/restore", headers=analyst).status_code == 403
    assert client.post(f"{base}/{ordinary.json()['id']}/restore", headers=admin).status_code == 200

    assert client.patch("/api/v1/auth/me", headers=analyst,
                        json={"username": "analyst2", "current_password": "wrong"}).status_code == 403
    updated = client.patch("/api/v1/auth/me", headers=analyst,
                           json={"username": "analyst2", "full_name": "New Analyst",
                                 "current_password": "analyst-password", "new_password": "new-password-123"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["username"] == "analyst2"
    assert client.post("/api/v1/auth/login", json={"username": "analyst2", "password": "new-password-123"}).status_code == 200


def test_task_owner_isolation_subtasks_comments_and_calendar(client):
    with client.eng.begin() as cx:
        cx.execute(text("UPDATE panel_users SET username='worker',password_hash=:hash WHERE id=1"),
                   {"hash": hash_password("worker-password")})
        for username, role in (("lead", "analyst"), ("observer", "analyst")):
            cx.execute(text("""INSERT INTO panel_users(username,full_name,email,role,active,password_hash,created_at,updated_at)
                VALUES (:name,:name,:email,:role,1,:hash,'2026-01-01','2026-01-01')"""),
                {"name": username, "email": username + "@example.com", "role": role,
                 "hash": hash_password(username + "-password")})
    def auth(name):
        response = client.post("/api/v1/auth/login", json={"username": name, "password": name + "-password"})
        assert response.status_code == 200, response.text
        return {"Authorization": "Bearer " + response.json()["token"]}
    lead, worker, observer = auth("lead"), auth("worker"), auth("observer")
    with client.eng.begin() as cx:
        cx.execute(text("INSERT INTO site_assignments(site_id,user_id,responsibility,created_at) VALUES ('demo',2,'lead','2026-01-01')"))
        cx.execute(text("INSERT INTO site_assignments(site_id,user_id,responsibility,created_at) VALUES ('demo',3,'viewer','2026-01-01')"))
    root = "/api/v1/sites/demo/work"
    draft = client.post(root, headers=lead, json={"title": "Personal draft"}).json()
    assert client.patch(f"{root}/{draft['id']}", headers=worker, json={"title": "Hijacked draft"}).status_code == 403
    assert client.patch(f"{root}/{draft['id']}", headers=lead, json={"owner_id": 1}).status_code == 200
    assert client.patch(f"{root}/{draft['id']}", headers=lead, json={"title": "Changed by lead"}).status_code == 403
    assert client.patch(f"{root}/{draft['id']}", headers=worker, json={"title": "Planned by worker"}).status_code == 200
    assert client.patch(f"{root}/{draft['id']}", headers=worker, json={"owner_id": 3}).status_code == 403
    assert client.patch(f"{root}/{draft['id']}", headers=observer, json={"status": "in_progress"}).status_code == 403
    assert client.post(f"{root}/{draft['id']}/checklist", headers=observer, json={"title": "Unwanted step"}).status_code == 403
    assert client.post(f"{root}/{draft['id']}/comments", headers=observer,
                       json={"text": "Review note"}).status_code == 201
    assert any(row["note"] == "Review note" for row in client.get(f"{root}/{draft['id']}/events", headers=worker).json())
    assert client.post(f"{root}/{draft['id']}/subtasks", headers=observer,
                       json={"title": "Unwanted child"}).status_code == 403
    child = client.post(f"{root}/{draft['id']}/subtasks", headers=worker,
                        json={"title": "Worker child"})
    assert child.status_code == 201, child.text
    child_id = child.json()["id"]
    assert client.get(f"{root}/{draft['id']}/subtasks", headers=observer).json()[0]["id"] == child_id
    assert client.delete(f"{root}/{draft['id']}", headers=worker).status_code == 403
    assert client.delete(f"{root}/{draft['id']}", headers=lead).status_code == 409
    assert client.delete(f"{root}/{child_id}", headers=lead).status_code == 403
    assert client.delete(f"{root}/{child_id}", headers=worker).status_code == 200
    assert client.delete(f"{root}/{draft['id']}", headers=lead).status_code == 200
    assert all(row["id"] not in {draft["id"], child_id}
               for row in client.get("/api/v1/work/board/demo", headers=lead).json()["items"])
    assert client.post(f"{root}/{draft['id']}/restore", headers=worker).status_code == 403
    assert client.post(f"{root}/{draft['id']}/restore", headers=lead).status_code == 200
    assert client.post(f"{root}/{child_id}/restore", headers=worker).status_code == 200
    restored_board = client.get("/api/v1/work/board/demo", headers=lead).json()["items"]
    assert draft["id"] in {row["id"] for row in restored_board}
    assert child_id not in {row["id"] for row in restored_board}
    assert {"id": -child_id, "title": "Worker child", "done": False, "legacy": True} in next(
        row["checklist"] for row in restored_board if row["id"] == draft["id"])
    step_url = f"{root}/{draft['id']}/checklist/{-child_id}"
    assert client.patch(step_url, headers=observer, json={"done": True}).status_code == 403
    toggled = client.patch(step_url, headers=worker, json={"done": True})
    assert toggled.status_code == 200, toggled.text
    assert any(step["id"] == -child_id and step["done"] for step in client.get(
        f"{root}/{draft['id']}/checklist", headers=worker).json())
    assert client.get("/api/v1/work/board/all", headers=worker).json()["items"][0]["checklist_done"] == 1
    assert client.get("/api/v1/auth/me", headers=worker).json()["date_calendar"] == "jalali"
    assert client.patch("/api/v1/auth/me/preferences", headers=worker,
                        json={"date_calendar": "gregorian"}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=worker).json()["date_calendar"] == "gregorian"
    assert client.get("/api/v1/auth/me", headers=lead).json()["date_calendar"] == "jalali"


def test_shared_discussion_and_project_mentions(client):
    with client.eng.begin() as cx:
        cx.execute(text("UPDATE panel_users SET username='worker',password_hash=:hash WHERE id=1"),
                   {"hash": hash_password("worker-password")})
        for username, role in (("manager", "admin"), ("colleague", "analyst"), ("outsider", "analyst")):
            cx.execute(text("""INSERT INTO panel_users(username,full_name,email,role,active,password_hash,created_at,updated_at)
                VALUES (:name,:name,:email,:role,1,:hash,'2026-01-01','2026-01-01')"""),
                {"name": username, "email": username + "@example.com", "role": role,
                 "hash": hash_password(username + "-password")})

    def auth(name):
        response = client.post("/api/v1/auth/login", json={"username": name, "password": name + "-password"})
        assert response.status_code == 200, response.text
        return {"Authorization": "Bearer " + response.json()["token"]}

    manager, worker, colleague, outsider = (auth(name) for name in ("manager", "worker", "colleague", "outsider"))
    assert client.put("/api/v1/work/projects/demo/members/3", headers=manager,
                      json={"user_id": 3, "responsibility": "viewer"}).status_code == 200
    base = "/api/v1/sites/demo/work"
    root = client.post(base, headers=manager, json={"title": "Main task", "owner_id": 1,
        "note": "Initial explanation\nwith details"}).json()
    assert client.get(f"{base}/{root['id']}/subtasks", headers=manager).json() == []
    child = client.post(f"{base}/{root['id']}/subtasks", headers=worker,
                        json={"title": "Optional child"}).json()
    grandchild = client.post(f"{base}/{child['id']}/subtasks", headers=worker,
                             json={"title": "Nested child"}).json()
    assert client.post(f"{base}/{grandchild['id']}/comments", headers=colleague,
                       json={"text": "Please review @worker and @manager; not @outsider"}).status_code == 201
    assert client.patch(f"{base}/{child['id']}", headers=worker,
                        json={"note": "Progress\n@colleague please check"}).status_code == 200
    thread_urls = [f"{base}/{task_id}/discussion" for task_id in (root["id"], child["id"], grandchild["id"])]
    threads = [client.get(url, headers=worker) for url in thread_urls]
    assert all(response.status_code == 200 for response in threads)
    assert all(response.json()["root_id"] == root["id"] for response in threads)
    assert all(response.json()["messages"] == threads[0].json()["messages"] for response in threads)
    messages = threads[0].json()["messages"]
    assert [row["note"] for row in messages] == ["Initial explanation\nwith details",
        "Please review @worker and @manager; not @outsider", "Progress\n@colleague please check"]
    assert messages[1]["work_item_id"] == grandchild["id"]
    assert any(row["event_type"] == "subtask_added" for row in threads[0].json()["activity"])
    participants = {row["username"] for row in threads[0].json()["participants"]}
    assert {"worker", "manager", "colleague"} <= participants and "outsider" not in participants
    worker_notices = client.get("/api/v1/auth/notifications?audience=discussion", headers=worker).json()["items"]
    manager_notices = client.get("/api/v1/auth/notifications?audience=discussion", headers=manager).json()["items"]
    outsider_notices = client.get("/api/v1/auth/notifications?audience=discussion", headers=outsider).json()["items"]
    colleague_notices = client.get("/api/v1/auth/notifications?audience=discussion", headers=colleague).json()["items"]
    assert any(row["kind"] == "mention" and row["work_item_id"] == root["id"] for row in worker_notices)
    assert any(row["kind"] == "mention" and row["work_item_id"] == root["id"] for row in manager_notices)
    assert any(row["kind"] == "mention" and row["work_item_id"] == root["id"] for row in colleague_notices)
    assert not outsider_notices
    assert client.post(f"{base}/{root['id']}/comments", headers=outsider,
                       json={"text": "Unauthorized"}).status_code == 403


def test_task_handoff_notification_archive_and_period_report(client):
    from datetime import datetime, timedelta, timezone

    with client.eng.begin() as cx:
        cx.execute(text("UPDATE panel_users SET username='worker',password_hash=:hash WHERE id=1"),
                   {"hash": hash_password("worker-password")})
        for username, role in (("lead", "analyst"), ("next", "analyst")):
            cx.execute(text("""INSERT INTO panel_users(username,full_name,email,role,active,password_hash,created_at,updated_at)
                VALUES (:name,:name,:email,:role,1,:hash,'2026-01-01','2026-01-01')"""),
                {"name": username, "email": username + "@example.com", "role": role,
                 "hash": hash_password(username + "-password")})

    def auth(name):
        response = client.post("/api/v1/auth/login", json={"username": name, "password": name + "-password"})
        assert response.status_code == 200, response.text
        return {"Authorization": "Bearer " + response.json()["token"]}

    lead, worker, next_user = auth("lead"), auth("worker"), auth("next")
    with client.eng.begin() as cx:
        cx.execute(text("INSERT INTO site_assignments(site_id,user_id,responsibility,created_at) VALUES ('demo',2,'lead','2026-01-01')"))
    base = "/api/v1/sites/demo/work"
    bad = client.post(base, headers=lead, json={"title": "Invalid task", "subtasks": ["x"]})
    assert bad.status_code == 422
    assert not any(row["title"] == "Invalid task" for row in client.get(base, headers=lead).json()["items"])
    created = client.post(base, headers=lead, json={"title": "Parent work", "owner_id": 1,
        "priority": "critical", "subtasks": ["First step", "Second step"]})
    assert created.status_code == 201, created.text
    parent = created.json()
    children = client.get(f"{base}/{parent['id']}/subtasks", headers=worker).json()
    assert len(children) == 2 and all(row["owner_id"] == 1 for row in children)
    notification = client.get("/api/v1/auth/notifications?audience=assigned", headers=worker).json()
    assert notification["unread"] == 1 and notification["items"][0]["title"] == "Parent work"
    notification_id = notification["items"][0]["id"]
    assert client.post(f"/api/v1/auth/notifications/{notification_id}/archive", headers=lead).status_code == 404
    assert client.post(f"/api/v1/auth/notifications/{notification_id}/archive", headers=worker).status_code == 200
    assert client.get("/api/v1/auth/notifications", headers=worker).json()["unread"] == 0
    assert client.get("/api/v1/auth/notifications?view=archived&audience=assigned", headers=worker).json()["items"][0]["id"] == notification_id
    assert client.post(f"/api/v1/auth/notifications/{notification_id}/restore", headers=worker).status_code == 200

    handoff_url = f"{base}/{parent['id']}/handoff"
    assert client.post(handoff_url, headers=lead, json={"owner_id": 3, "reason": "capacity"}).status_code == 403
    assert client.post(handoff_url, headers=worker, json={"owner_id": 3, "reason": " "}).status_code == 422
    moved = client.post(handoff_url, headers=worker, json={"owner_id": 3, "reason": "Unable to finish"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["moved_tasks"] == 3
    assert all(row["owner_id"] == 3 for row in client.get(f"{base}/{parent['id']}/subtasks", headers=next_user).json())
    assert client.patch(f"{base}/{parent['id']}", headers=worker, json={"title": "Old owner edit"}).status_code == 403
    assert client.patch(f"{base}/{parent['id']}", headers=next_user, json={"title": "New owner edit"}).status_code == 200
    assert any(row["event_type"] == "handoff" and row["note"] == "Unable to finish"
               for row in client.get(f"{base}/{parent['id']}/events", headers=lead).json())
    assert any(row["kind"] == "handoff" for row in client.get("/api/v1/auth/notifications?audience=assigned", headers=next_user).json()["items"])
    assert any(row["kind"] == "handoff" for row in client.get("/api/v1/auth/notifications?audience=delegated", headers=lead).json()["items"])
    assert client.post(f"{base}/{parent['id']}/comments", headers=next_user,
                       json={"text": "I will continue this"}).status_code == 201
    assert any(row["kind"] == "comment" for row in client.get("/api/v1/auth/notifications?audience=discussion", headers=lead).json()["items"])

    for child in children:
        assert client.patch(f"{base}/{child['id']}", headers=next_user, json={"status": "verified"}).status_code == 200
    assert client.patch(f"{base}/{parent['id']}", headers=next_user, json={"status": "verified"}).status_code == 200
    anchor = datetime.now(timezone(timedelta(hours=3, minutes=30))).date().isoformat()
    report = client.get(f"/api/v1/work/reports?period=week&anchor={anchor}&site_id=demo", headers=lead)
    assert report.status_code == 200, report.text
    assert report.json()["totals"]["created"] >= 3
    assert report.json()["totals"]["completed"] == 3
    assert report.json()["totals"]["handoffs"] == 3
    assert client.get(f"/api/v1/work/reports?period=month&anchor={anchor}&user_id=3", headers=lead).json()["totals"]["completed"] == 3


def test_personal_and_delegated_boards_keep_task_ownership_separate(client):
    with client.eng.begin() as cx:
        cx.execute(text("UPDATE panel_users SET username='worker',password_hash=:hash WHERE id=1"),
                   {"hash": hash_password("worker-password")})
        cx.execute(text("""INSERT INTO panel_users(username,full_name,email,role,active,password_hash,created_at,updated_at)
            VALUES ('manager','Manager','manager@example.com','admin',1,:hash,'2026-01-01','2026-01-01')"""),
            {"hash": hash_password("manager-password")})

    def auth(name):
        response = client.post("/api/v1/auth/login", json={"username": name, "password": name + "-password"})
        assert response.status_code == 200, response.text
        return {"Authorization": "Bearer " + response.json()["token"]}

    manager, worker = auth("manager"), auth("worker")
    assert client.put("/api/v1/work/projects/demo/members/1", headers=manager,
                      json={"user_id": 1, "responsibility": "lead"}).status_code == 200
    base = "/api/v1/sites/demo/work"
    to_worker = client.post(base, headers=manager, json={"title": "Manager delegated to worker", "owner_id": 1}).json()
    second_to_worker = client.post(base, headers=manager,
                                   json={"title": "Second delegation", "owner_id": 1}).json()
    self_assigned = client.post(base, headers=manager,
                                json={"title": "Manager self-assigned", "owner_id": 2}).json()
    unassigned = client.post(base, headers=manager, json={"title": "Manager draft"}).json()
    to_manager = client.post(base, headers=worker, json={"title": "Worker delegated to manager", "owner_id": 2}).json()

    manager_delegated = client.get("/api/v1/work/board/delegated", headers=manager)
    assert manager_delegated.status_code == 200, manager_delegated.text
    assert {row["id"] for row in manager_delegated.json()["items"]} == {to_worker["id"], second_to_worker["id"]}
    assert {row["id"] for row in client.get("/api/v1/work/board/all", headers=manager).json()["items"]} == {
        self_assigned["id"], to_manager["id"]}
    assert {row["id"] for row in client.get("/api/v1/work/board/created", headers=manager).json()["items"]} == {
        to_worker["id"], second_to_worker["id"], self_assigned["id"], unassigned["id"]}
    assert {row["id"] for row in client.get("/api/v1/work/board/delegated", headers=worker).json()["items"]} == {
        to_manager["id"]}
    assert {row["id"] for row in client.get("/api/v1/work/board/all", headers=worker).json()["items"]} == {
        to_worker["id"], second_to_worker["id"]}
    added_step = client.post(f"{base}/{to_worker['id']}/checklist", headers=worker,
                             json={"title": "Review page content"})
    assert added_step.status_code == 201, added_step.text
    worker_board = client.get("/api/v1/work/board/all", headers=worker).json()["items"]
    assert {row["id"] for row in worker_board} == {to_worker["id"], second_to_worker["id"]}
    assert any(step["id"] == added_step.json()["id"] for row in worker_board
               if row["id"] == to_worker["id"] for step in row["checklist"])

    first_page = client.get("/api/v1/work/board/delegated?limit=1", headers=manager).json()
    assert [row["id"] for row in first_page["items"]] == [to_worker["id"]]
    assert first_page["next_after_id"] == to_worker["id"]
    second_page = client.get(f"/api/v1/work/board/delegated?limit=1&after_id={to_worker['id']}",
                             headers=manager).json()
    assert [row["id"] for row in second_page["items"]] == [second_to_worker["id"]]
    assert second_page["next_after_id"] is None

    handed_off = client.post(f"{base}/{to_manager['id']}/handoff", headers=manager,
                             json={"owner_id": 1, "reason": "Worker can finish this"})
    assert handed_off.status_code == 200, handed_off.text
    assert to_manager["id"] not in {row["id"] for row in client.get(
        "/api/v1/work/board/all", headers=manager).json()["items"]}
    assert to_manager["id"] in {row["id"] for row in client.get(
        "/api/v1/work/board/delegated", headers=manager).json()["items"]}
    assert to_manager["id"] in {row["id"] for row in client.get(
        "/api/v1/work/board/all", headers=worker).json()["items"]}
    assert to_manager["id"] not in {row["id"] for row in client.get(
        "/api/v1/work/board/delegated", headers=worker).json()["items"]}

    assert client.delete(f"{base}/{to_worker['id']}", headers=manager).status_code == 200
    assert [row["id"] for row in client.get("/api/v1/work/board/delegated", headers=manager).json()["items"]] == [
        second_to_worker["id"], to_manager["id"]]
    assert client.post(f"{base}/{to_worker['id']}/restore", headers=manager).status_code == 200
    assert {row["id"] for row in client.get("/api/v1/work/board/delegated", headers=manager).json()["items"]} == {
        to_worker["id"], second_to_worker["id"], to_manager["id"]}


def test_manager_dashboard_and_admin_task_override(client):
    with client.eng.begin() as cx:
        cx.execute(text("UPDATE panel_users SET username='worker',password_hash=:hash WHERE id=1"),
                   {"hash": hash_password("worker-password")})
        for username, role, owner in (("manager", "admin", 1), ("other-admin", "admin", 0),
                                      ("next", "analyst", 0)):
            cx.execute(text("""INSERT INTO panel_users(username,full_name,email,role,active,is_superadmin,
                password_hash,created_at,updated_at)
                VALUES (:name,:name,:email,:role,1,:owner,:hash,'2026-01-01','2026-01-01')"""),
                {"name": username, "email": username + "@example.com", "role": role,
                 "owner": owner, "hash": hash_password(username + "-password")})

    def auth(name):
        result = client.post("/api/v1/auth/login", json={"username": name, "password": name + "-password"})
        assert result.status_code == 200, result.text
        return {"Authorization": "Bearer " + result.json()["token"]}

    manager, worker, other_admin, next_user = (auth(name) for name in ("manager", "worker", "other-admin", "next"))
    assert client.get("/api/v1/auth/me", headers=manager).json()["is_superadmin"] is True
    assert client.get("/api/v1/auth/me", headers=other_admin).json()["is_superadmin"] is False
    assert client.get("/api/v1/work/team-management", headers=other_admin).status_code == 403
    assert client.get("/api/v1/work/team-management", headers=worker).status_code == 403
    assert client.patch("/api/v1/call-center/users/2", headers=other_admin,
                        json={"full_name": "Taken over"}).status_code == 403
    assert client.patch("/api/v1/call-center/users/2", headers=manager,
                        json={"active": False}).status_code == 422
    assert client.put("/api/v1/work/projects/demo/members/1", headers=manager,
                      json={"user_id": 1, "responsibility": "lead"}).status_code == 200
    base = "/api/v1/sites/demo/work"
    created = client.post(base, headers=worker, json={"title": "Worker task", "owner_id": 1,
                                                     "subtasks": ["Worker child"]})
    assert created.status_code == 201, created.text
    task = created.json()
    child = client.get(f"{base}/{task['id']}/subtasks", headers=manager).json()[0]
    dashboard = client.get("/api/v1/work/team-management?user_id=1", headers=manager)
    assert dashboard.status_code == 200, dashboard.text
    person = next(row for row in dashboard.json()["people"] if row["id"] == 1)
    assert person["open_tasks"] == 1
    assert dashboard.json()["summary"]["open_tasks"] >= 1
    assert any(row["work_item_id"] == task["id"] for row in dashboard.json()["recent"])
    ledger_url = "/api/v1/work/team-management/tasks"
    assert client.get(ledger_url, headers=other_admin).status_code == 403
    assert client.get(ledger_url, headers=worker).status_code == 403
    ledger = client.get(ledger_url + "?site_id=demo&owner_id=1&focus=unscheduled&limit=1",
                        headers=manager)
    assert ledger.status_code == 200, ledger.text
    assert ledger.json()["total"] == 1
    assert ledger.json()["schedule"]["unscheduled"] == 1
    assert ledger.json()["workload"][0]["open"] == 1
    assert sum(row["count"] for row in ledger.json()["timeline"] if row["week_index"] == -2) == 1
    assert len(ledger.json()["items"]) == 1
    assert ledger.json()["items"][0]["id"] == task["id"]
    assert ledger.json()["items"][0]["checklist_total"] == 1
    assert client.get(ledger_url + "?site_id=demo&owner_id=1&focus=unscheduled&limit=1&offset=1",
                      headers=manager).json()["items"] == []
    assert client.get(ledger_url + "?status=made_up", headers=manager).status_code == 422
    assert client.get(ledger_url + "?q=Worker%20task", headers=manager).json()["total"] == 1
    assert client.patch(f"{base}/{task['id']}", headers=other_admin,
                        json={"title": "Unauthorized edit"}).status_code == 403
    assert client.delete(f"{base}/{task['id']}", headers=other_admin).status_code == 403
    assert client.patch(f"{base}/{task['id']}", headers=manager,
                        json={"title": "Manager reviewed", "priority": "critical", "owner_id": 4}).status_code == 200
    assert client.patch(f"{base}/{task['id']}", headers=worker, json={"title": "Old owner edit"}).status_code == 403
    assert client.post(f"/api/v1/work/projects/demo/tasks/{task['id']}/time", headers=manager,
                       json={"user_id": 1, "minutes": 30, "work_date": "2026-01-01", "note": "review"}).status_code == 201
    assert client.delete(f"{base}/{task['id']}", headers=next_user).status_code == 403
    assert client.delete(f"{base}/{task['id']}", headers=manager).status_code == 200
    deleted = {row["id"] for row in client.get("/api/v1/work/archive?kind=deleted", headers=manager).json()}
    assert task["id"] in deleted and child["id"] not in deleted
    assert client.post(f"{base}/{task['id']}/restore", headers=manager).status_code == 200
    assert client.get(f"{base}/{task['id']}/subtasks", headers=next_user).status_code == 200
    due = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    scheduled = client.post(base, headers=manager,
                            json={"title": "Scheduled team task", "owner_id": 1, "due_at": due})
    assert scheduled.status_code == 201, scheduled.text
    portfolio = client.get(ledger_url + "?site_id=demo&owner_id=1&limit=1", headers=manager)
    assert portfolio.status_code == 200, portfolio.text
    assert portfolio.json()["schedule"]["due_week"] == 1
    assert {row["site_id"] for row in portfolio.json()["timeline"]} == {"demo"}
    assert sum(row["count"] for row in portfolio.json()["timeline"]
               if row["user_id"] == 1 and row["week_index"] >= 0) == 1
