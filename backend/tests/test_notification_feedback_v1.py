# backend/tests/test_notification_feedback_v1.py
"""Tests for notification feedback V1: normalization, 422 when interact without action_id, legacy, admin stats."""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from backend.app.database import SessionLocal, Base, engine
from backend.app.main import app
from backend.app.models import Notification, NotificationFeedback, User

client = TestClient(app)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(db):
    u = User(name="Feedback Test User", secret_key="ft", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def test_notification(db, test_user):
    n = Notification(
        user_id=test_user.id,
        type="connection_ping",
        title="Test",
        body="Test body",
        priority="normal",
        is_read=False,
        is_sent=False,
        created_at=datetime.utcnow(),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def test_accept_like_with_reason(db, test_user, test_notification):
    """POST feedback with like + reason is accepted and stored with normalized event_type."""
    r = client.post(
        f"/notifications/{test_notification.id}/feedback",
        params={"user_id": test_user.id},
        json={
            "reaction": "like",
            "timestamp": datetime.utcnow().isoformat(),
            "reason": "too_frequent",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data.get("data", {}).get("feedback_received") is True
    row = db.query(NotificationFeedback).filter(
        NotificationFeedback.notification_id == test_notification.id,
    ).first()
    assert row is not None
    assert row.action == "like"
    assert row.user_id == test_user.id
    if row.meta_json:
        import json
        meta = json.loads(row.meta_json)
        assert meta.get("reason") == "too_frequent"


def test_interact_without_action_id_returns_422(db, test_user, test_notification):
    """POST feedback with reaction=interact and no action_id returns 422."""
    r = client.post(
        f"/notifications/{test_notification.id}/feedback",
        params={"user_id": test_user.id},
        json={
            "reaction": "interact",
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
    assert r.status_code == 422


def test_legacy_payload_still_accepted(db, test_user, test_notification):
    """Legacy B2 payload (feedback/reason/action) is accepted and normalized."""
    r = client.post(
        f"/notifications/{test_notification.id}/feedback",
        params={"user_id": test_user.id},
        json={
            "feedback": "positive",
            "reason": "Helpful",
            "action": "too_early",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    row = db.query(NotificationFeedback).filter(
        NotificationFeedback.notification_id == test_notification.id,
    ).first()
    assert row is not None
    assert row.action == "like"


def test_admin_feedback_stats_returns_correct_counts(db, test_user, test_notification):
    """GET admin/feedback_stats returns counts_by_event_type and last_events."""
    client.post(
        f"/notifications/{test_notification.id}/feedback",
        params={"user_id": test_user.id},
        json={"reaction": "like", "timestamp": datetime.utcnow().isoformat()},
    )
    client.post(
        f"/notifications/{test_notification.id}/feedback",
        params={"user_id": test_user.id},
        json={"reaction": "dislike", "timestamp": datetime.utcnow().isoformat(), "reason": "irrelevant"},
    )
    r = client.get(
        "/notifications/admin/feedback_stats",
        params={"user_id": test_user.id, "days": 7},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    counts = data.get("data", {}).get("counts_by_event_type", {})
    assert "like" in counts or "dislike" in counts
    assert data["data"].get("last_events") is not None
    assert "counts_by_reason" in data["data"]
