from fastapi.testclient import TestClient
import pytest

from seo_brain.support.app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPPORT_DB_PATH", str(tmp_path / "support.db"))
    monkeypatch.setenv("SUPPORT_API_TOKEN", "test-support-token")
    monkeypatch.setenv("SUPPORT_STAFF_ACCOUNTS", "manager")
    with TestClient(app) as c:
        yield c


def headers(actor="amir"):
    return {"X-API-Token": "test-support-token", "X-SEO-Actor": actor}


def create(client, actor="amir"):
    return client.post("/api/v1/support/tickets", headers=headers(actor), json={
        "subject": "Cannot open a report", "message": "The report does not load.",
        "site_id": "salimore", "context_path": "/dashboard/reports?discard=secret#fragment"})


def test_authentication_and_actor_are_required(client, monkeypatch):
    assert client.get("/api/v1/support/tickets").status_code == 401
    assert client.get("/api/v1/support/tickets", headers={"X-API-Token": "test-support-token"}).status_code == 401
    monkeypatch.delenv("SUPPORT_API_TOKEN")
    assert client.get("/api/v1/support/tickets", headers=headers()).status_code == 503


def test_create_is_durable_and_discards_query_secrets(client):
    result = create(client)
    assert result.status_code == 201
    item = result.json()
    assert item["reference"] == "SB-000001"
    assert item["context_path"] == "/dashboard/reports"
    assert item["owner"] == "amir"
    assert len(item["messages"]) == 1
    assert client.get("/api/v1/support/tickets/1", headers=headers()).json()["messages"][0]["body"] == "The report does not load."


def test_other_accounts_cannot_read_reply_or_close_a_ticket(client):
    create(client)
    assert client.get("/api/v1/support/tickets", headers=headers("another")).json()["total"] == 0
    assert client.get("/api/v1/support/tickets/1", headers=headers("another")).status_code == 404
    assert client.post("/api/v1/support/tickets/1/messages", headers=headers("another"), json={"message": "unauthorized"}).status_code == 404
    assert client.patch("/api/v1/support/tickets/1", headers=headers("another"), json={"status": "closed"}).status_code == 404
    assert client.post("/api/v1/support/tickets/1/messages", headers=headers(), json={"message": "fake staff reply", "as_support": True}).status_code == 403


def test_staff_inbox_reply_close_and_owner_followup(client):
    create(client)
    inbox = client.get("/api/v1/support/tickets", headers=headers("manager")).json()
    assert inbox["is_staff"] and inbox["total"] == 1
    result = client.post("/api/v1/support/tickets/1/messages", headers=headers("manager"), json={"message": "Please retry now", "as_support": True}).json()
    assert result["status"] == "waiting" and result["messages"][-1]["is_staff"] == 1
    closed = client.patch("/api/v1/support/tickets/1", headers=headers(), json={"status": "closed"}).json()
    assert closed["status"] == "closed" and len(closed["messages"]) == 2
    reopened = client.post("/api/v1/support/tickets/1/messages", headers=headers(), json={"message": "Still fails"}).json()
    assert reopened["status"] == "open" and len(reopened["messages"]) == 3


def test_validation_rejects_spoofed_owners_and_external_context(client):
    payload = {"subject": "Valid subject", "message": "Valid message", "owner": "manager"}
    assert client.post("/api/v1/support/tickets", headers=headers(), json=payload).status_code == 422
    payload.pop("owner")
    payload["context_path"] = "https://external.example"
    assert client.post("/api/v1/support/tickets", headers=headers(), json=payload).status_code == 422
    assert client.get("/api/v1/support/tickets", headers=headers()).json()["total"] == 0
