"""Completed calls are distinct from web click events; source changes update aggregates."""
from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from seo_brain.api.routers import call_center


def test_call_center_source_and_operator_flow():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sql = (Path(__file__).parents[3] / "database" / "migrations" / "0020_call_center.sql").read_text(encoding="utf-8")
    outcomes_sql = (Path(__file__).parents[3] / "database" / "migrations" / "0023_call_outcomes.sql").read_text(encoding="utf-8")
    with eng.begin() as cx:
        cx.connection.driver_connection.executescript(sql)
        cx.connection.driver_connection.executescript(outcomes_sql)
    app = FastAPI()
    app.include_router(call_center.router, prefix="/api/v1")
    app.dependency_overrides[call_center.engine] = lambda: eng
    client = TestClient(app)

    user = client.post("/api/v1/call-center/users", json={"full_name": "Operator Test", "email": "Operator@Example.com", "role": "call_center"})
    assert user.status_code == 201
    assert user.json()["email"] == "operator@example.com"
    duplicate = client.post("/api/v1/call-center/users", json={"full_name": "Another", "email": "operator@example.com"})
    assert duplicate.status_code == 409
    assert client.patch(f"/api/v1/call-center/users/{user.json()['id']}", json={"active": None}).status_code == 422
    record = client.post("/api/v1/call-center/calls", json={
        "phone": "۰۹۱۲۳۴۵۶۷۸۹", "customer_name": "Test", "brand": "مدیران", "model": "X22",
        "region": "تهران", "source": "seo", "source_basis": "customer", "operator_id": user.json()["id"]
    })
    assert record.status_code == 201, record.text
    assert record.json()["phone"] == "09123456789"
    assert client.patch(f"/api/v1/call-center/calls/{record.json()['id']}", json={"order_value": 100}).status_code == 422
    assert client.patch(f"/api/v1/call-center/calls/{record.json()['id']}", json={"operator_id": 999}).status_code == 422
    summary = client.get("/api/v1/call-center/analytics").json()
    assert summary["total"] == 1 and summary["by_source"]["seo"] == 1
    assert summary["by_outcome"]["pending"] == 1

    won = client.patch(f"/api/v1/call-center/calls/{record.json()['id']}", json={
        "outcome": "order", "order_value": 2500000, "source_confidence": "confirmed"})
    assert won.status_code == 200, won.text
    funnel = client.get("/api/v1/call-center/analytics").json()["by_source_outcome"]["seo"]
    assert funnel == {"total": 1, "qualified": 1, "orders": 1,
                      "order_value": 2500000, "unknown_confidence": 0}
    assert client.patch(f"/api/v1/call-center/calls/{record.json()['id']}", json={"outcome": "qualified"}).status_code == 422

    changed = client.patch(f"/api/v1/call-center/calls/{record.json()['id']}", json={"source": "ads", "source_basis": "manual"})
    assert changed.status_code == 200
    summary = client.get("/api/v1/call-center/analytics").json()
    assert summary["by_source"].get("seo", 0) == 0
    assert summary["by_source"]["ads"] == 1
    focused = client.get("/api/v1/call-center/analytics?source=ads").json()
    assert focused["total"] == 1 and focused["by_region"] == [["تهران", 1]]
    assert client.get("/api/v1/call-center/analytics?source=seo").json()["total"] == 0
    listing = client.get("/api/v1/call-center/calls?source=ads&limit=1").json()
    assert listing["total"] == 1 and listing["items"][0]["operator_name"] == "Operator Test"
    assert client.get("/api/v1/call-center/calls?source=ads&limit=1&offset=1").json()["items"] == []
    future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    assert client.post("/api/v1/call-center/calls", json={"occurred_at": future, "source": "unknown"}).status_code == 201
    summary = client.get("/api/v1/call-center/analytics").json()
    assert summary["total"] == 1 and summary["future"] == 1
