"""
Acceptance tests for GET/PUT /notifications/prefs (V1 Notification Preferences).

- GET returns defaults when no row exists (fail-open).
- PUT creates/updates and returns current prefs.
- GET after PUT returns persisted values.
Uses controlled data; creates user in same transaction as client.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.security import create_access_token
from backend.app.models import User


def _auth_headers(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def prefs_user(db: Session) -> User:
    """Create a user for prefs tests (no reliance on existing data)."""
    user = User(
        name="Prefs Test User",
        secret_key="prefs-secret",
        preferred_language="en",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_get_prefs_defaults_when_no_row(client: TestClient, prefs_user: User) -> None:
    """GET /notifications/prefs returns ok and defaults when no row exists."""
    response = client.get(
        f"/notifications/prefs?user_id={prefs_user.id}",
        headers=_auth_headers(prefs_user.id),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("ok") is True
    assert data.get("error") is None
    prefs = data.get("data")
    assert prefs is not None
    assert prefs["user_id"] == prefs_user.id
    assert "channels" in prefs
    ch = prefs["channels"]
    assert ch["companion"] is True
    assert ch["health_alert"] is True
    assert ch["reminder_medication"] is True
    assert ch["reminder_appointment"] is True
    assert ch["reminder_system"] is True
    assert "quiet_hours" in prefs
    qh = prefs["quiet_hours"]
    assert qh["enabled"] is False
    assert prefs["engagement_level"] == 1


def test_put_prefs_creates_and_returns(client: TestClient, prefs_user: User) -> None:
    """PUT /notifications/prefs with channels, quiet_hours, engagement_level returns 200 and matching data."""
    body = {
        "channels": {
            "companion": False,
            "health_alert": True,
            "reminder_medication": False,
            "reminder_appointment": True,
            "reminder_system": False,
        },
        "quiet_hours": {
            "enabled": True,
            "start": "22:00",
            "end": "07:00",
        },
        "engagement_level": 2,
    }
    response = client.put(
        f"/notifications/prefs?user_id={prefs_user.id}",
        headers=_auth_headers(prefs_user.id),
        json=body,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("ok") is True
    assert data.get("error") is None
    prefs = data["data"]
    assert prefs["user_id"] == prefs_user.id
    assert prefs["channels"]["companion"] is False
    assert prefs["channels"]["health_alert"] is True
    assert prefs["channels"]["reminder_medication"] is False
    assert prefs["channels"]["reminder_appointment"] is True
    assert prefs["channels"]["reminder_system"] is False
    assert prefs["quiet_hours"]["enabled"] is True
    assert prefs["quiet_hours"]["start"] == "22:00"
    assert prefs["quiet_hours"]["end"] == "07:00"
    assert prefs["engagement_level"] == 2


def test_get_prefs_after_put_persists(client: TestClient, prefs_user: User) -> None:
    """PUT then GET returns persisted values."""
    body = {
        "channels": {"companion": False, "health_alert": True},
        "quiet_hours": {"enabled": True, "start": "23:00", "end": "06:00"},
        "engagement_level": 0,
    }
    put_resp = client.put(
        f"/notifications/prefs?user_id={prefs_user.id}",
        headers=_auth_headers(prefs_user.id),
        json=body,
    )
    assert put_resp.status_code == 200
    get_resp = client.get(
        f"/notifications/prefs?user_id={prefs_user.id}",
        headers=_auth_headers(prefs_user.id),
    )
    assert get_resp.status_code == 200
    get_data = get_resp.json()["data"]
    assert get_data["channels"]["companion"] is False
    assert get_data["channels"]["health_alert"] is True
    assert get_data["quiet_hours"]["enabled"] is True
    assert get_data["quiet_hours"]["start"] == "23:00"
    assert get_data["quiet_hours"]["end"] == "06:00"
    assert get_data["engagement_level"] == 0


def test_get_prefs_requires_auth(client: TestClient) -> None:
    """GET /notifications/prefs without JWT is rejected."""
    response = client.get("/notifications/prefs?user_id=1")
    assert response.status_code == 401
