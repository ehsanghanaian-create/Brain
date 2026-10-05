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
