"""
Unit tests: KC → Notification Bridge V1.2 (delivery limit=1, in_app skip).
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.security import create_access_token

_UID = 91021


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def test_user_id(db: Session) -> int:
    db.execute(
        text(
            "INSERT INTO users (id, name, secret_key, preferred_language, created_at) "
            "VALUES (:id, :name, :secret, :lang, NOW())"
        ),
        {"id": _UID, "name": "KC Notify V1.2 Test", "secret": "n2", "lang": "fa"},
    )
    db.commit()
    return _UID


def _seed_candidate(client: TestClient, user_id: int) -> None:
    r = client.post(
        "/knowledge/extract_from_message",
        json={
            "text": "دارم متفورمین می‌خورم",
            "language": "fa",
            "source_message_id": f"pytest-notify2-{uuid.uuid4().hex[:12]}",
        },
        headers=_auth_header(user_id),
    )
    assert r.status_code == 200, r.text
    assert r.json().get("data", {}).get("created_candidates_count", 0) >= 1


def test_notify_true_in_app_skips_delivery_call(client: TestClient, test_user_id: int, monkeypatch):
    monkeypatch.setenv("KC_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("KC_BURST_GUARD_MINUTES", "0")
    _seed_candidate(client, test_user_id)

    with patch("backend.app.services.notifications.delivery_service.DeliveryService.deliver_pending") as mock_deliver:
        r = client.get(
            "/knowledge/next_question?lang=en&notify=true&in_app=true",
            headers=_auth_header(test_user_id),
        )
    assert r.status_code == 200, r.text
    data = r.json().get("data")
    assert data is not None
    assert data.get("question_type") == "confirm_candidate"
    assert "notification" in data
    assert data["notification"].get("ok") is True
    assert data["notification"].get("reason") == "in_app_skip_delivery"
    assert data["notification"].get("notification_id") is not None
    mock_deliver.assert_not_called()


def test_notify_true_not_in_app_calls_delivery_limit_1(client: TestClient, test_user_id: int, monkeypatch):
    monkeypatch.setenv("KC_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("KC_BURST_GUARD_MINUTES", "0")
    _seed_candidate(client, test_user_id)

    with patch("backend.app.services.notifications.delivery_service.DeliveryService.deliver_pending") as mock_deliver:
        mock_deliver.return_value = 0
        r = client.get(
            "/knowledge/next_question?lang=en&notify=true&in_app=false",
            headers=_auth_header(test_user_id),
        )
    assert r.status_code == 200, r.text
    data = r.json().get("data")
    assert data is not None
    assert data.get("question_type") == "confirm_candidate"
    assert data.get("notification", {}).get("ok") is True
    mock_deliver.assert_called_once_with(limit=1)
