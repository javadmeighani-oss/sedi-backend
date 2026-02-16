"""
Unit tests: KC → Notification Bridge V1.2 (delivery limit=1, in_app skip).
- notify=true & in_app=true: create notification, do NOT call deliver_pending; reason=in_app_skip_delivery.
- notify=true & in_app=false: call deliver_pending(limit=1).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.app.database import Base, SessionLocal, engine
from backend.app.main import app as sedi_app

_UID = 91021


def _collect_paths(routes, prefix=""):
    paths = set()
    for r in routes:
        path = getattr(r, "path", None) or ""
        if hasattr(r, "routes"):
            paths.update(_collect_paths(r.routes, prefix + path))
        elif path:
            paths.add(prefix + path)
    return paths


@pytest.fixture()
def client() -> TestClient:
    paths = _collect_paths(sedi_app.routes)
    assert "/knowledge/next_question" in paths
    return TestClient(sedi_app)


@pytest.fixture()
def db() -> Session:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


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
            "user_id": user_id,
            "text": "دارم متفورمین می‌خورم",
            "language": "fa",
            "source_message_id": f"pytest-notify2-{uuid.uuid4().hex[:12]}",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("data", {}).get("created_candidates_count", 0) >= 1


def test_notify_true_in_app_skips_delivery_call(client: TestClient, test_user_id: int, monkeypatch):
    """notify=true & in_app=true: deliver_pending NOT called; notification.ok=true, reason=in_app_skip_delivery."""
    monkeypatch.setenv("KC_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("KC_BURST_GUARD_MINUTES", "0")
    _seed_candidate(client, test_user_id)

    with patch("backend.app.services.notifications.delivery_service.DeliveryService.deliver_pending") as mock_deliver:
        r = client.get(f"/knowledge/next_question?user_id={test_user_id}&lang=en&notify=true&in_app=true")
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
    """notify=true & in_app=false: deliver_pending called with limit=1."""
    monkeypatch.setenv("KC_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("KC_BURST_GUARD_MINUTES", "0")
    _seed_candidate(client, test_user_id)

    with patch("backend.app.services.notifications.delivery_service.DeliveryService.deliver_pending") as mock_deliver:
        mock_deliver.return_value = 0
        r = client.get(f"/knowledge/next_question?user_id={test_user_id}&lang=en&notify=true&in_app=false")
    assert r.status_code == 200, r.text
    data = r.json().get("data")
    assert data is not None
    assert data.get("question_type") == "confirm_candidate"
    assert data.get("notification", {}).get("ok") is True
    mock_deliver.assert_called_once_with(limit=1)
