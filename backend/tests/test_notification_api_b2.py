# tests/test_notification_api_b2.py
"""
Pytest tests for Release B - Part B2: Notification API

Tests:
- GET /notifications/unread returns unread notifications
- POST /notifications/{id}/mark-read marks notification as read
- POST /notifications/{id}/feedback accepts standardized payload

Section 15-P1 (B4): protected endpoints require Bearer JWT matching owner.
Unauthenticated calls must receive 401 (auth is not weakened).
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime
from sqlalchemy.orm import Session

from backend.app.core.security import create_access_token
from backend.app.models import Notification, User


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_user(db: Session):
    """Create a test user"""
    user = User(
        name="Test User",
        secret_key="test123",
        preferred_language="en"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_notification(db: Session, test_user: User):
    """Create a test notification"""
    notification = Notification(
        user_id=test_user.id,
        type="morning_brief",
        title="Test Notification",
        body="Test body",
        priority="normal",
        is_read=False,
        is_sent=False,
        created_at=datetime.utcnow()
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def test_get_unread_notifications_requires_auth(
    client: TestClient, db: Session, test_user: User, test_notification: Notification
):
    """Unauthenticated unread list must remain rejected (401)."""
    response = client.get(
        "/notifications/unread",
        params={"user_id": test_user.id, "limit": 20},
    )
    assert response.status_code == 401


def test_get_unread_notifications(client: TestClient, db: Session, test_user: User, test_notification: Notification):
    """Test GET /notifications/unread returns unread notifications"""
    response = client.get(
        "/notifications/unread",
        params={"user_id": test_user.id, "limit": 20},
        headers=_auth_header(test_user.id),
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "notifications" in data["data"]
    assert "count" in data["data"]
    assert len(data["data"]["notifications"]) > 0
    
    # Verify notification is in the list
    notification_ids = [n["id"] for n in data["data"]["notifications"]]
    assert test_notification.id in notification_ids


def test_get_unread_notifications_with_type_filter(client: TestClient, db: Session, test_user: User, test_notification: Notification):
    """Test GET /notifications/unread with type filter"""
    response = client.get(
        "/notifications/unread",
        params={"user_id": test_user.id, "type": "morning_brief", "limit": 20},
        headers=_auth_header(test_user.id),
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    
    # All returned notifications should be of the specified type
    for notif in data["data"]["notifications"]:
        assert notif["type"] == "morning_brief"


def test_get_unread_notifications_limit(client: TestClient, db: Session, test_user: User):
    """Test GET /notifications/unread respects limit parameter"""
    # Create multiple notifications
    for i in range(5):
        notification = Notification(
            user_id=test_user.id,
            type="morning_brief",
            title=f"Test {i}",
            body=f"Body {i}",
            priority="normal",
            is_read=False,
            is_sent=False,
            created_at=datetime.utcnow()
        )
        db.add(notification)
    db.commit()
    
    response = client.get(
        "/notifications/unread",
        params={"user_id": test_user.id, "limit": 3},
        headers=_auth_header(test_user.id),
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["data"]["notifications"]) <= 3


def test_mark_notification_read(client: TestClient, db: Session, test_user: User, test_notification: Notification):
    """Test POST /notifications/{id}/mark-read marks notification as read"""
    # Verify notification is unread
    assert test_notification.is_read is False
    
    response = client.post(
        f"/notifications/{test_notification.id}/mark-read",
        params={"user_id": test_user.id},
        headers=_auth_header(test_user.id),
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["data"]["is_read"] is True
    
    # Verify in database
    db.refresh(test_notification)
    assert test_notification.is_read is True


def test_mark_notification_read_idempotent(client: TestClient, db: Session, test_user: User, test_notification: Notification):
    """Test POST /notifications/{id}/mark-read is idempotent"""
    # Mark as read first time
    response1 = client.post(
        f"/notifications/{test_notification.id}/mark-read",
        params={"user_id": test_user.id},
        headers=_auth_header(test_user.id),
    )
    assert response1.status_code == 200
    
    # Mark as read second time (should still succeed)
    response2 = client.post(
        f"/notifications/{test_notification.id}/mark-read",
        params={"user_id": test_user.id},
        headers=_auth_header(test_user.id),
    )
    assert response2.status_code == 200
    assert response2.json()["ok"] is True


def test_mark_notification_read_ownership_validation(client: TestClient, db: Session, test_user: User, test_notification: Notification):
    """Non-owner JWT must not mark another user's notification read (HTTP 403)."""
    other_user = User(
        name="Other User",
        secret_key="other123",
        preferred_language="en"
    )
    db.add(other_user)
    db.commit()
    db.refresh(other_user)
    
    response = client.post(
        f"/notifications/{test_notification.id}/mark-read",
        params={"user_id": other_user.id},
        headers=_auth_header(other_user.id),
    )
    
    assert response.status_code == 403
    db.refresh(test_notification)
    assert test_notification.is_read is False


def test_mark_notification_read_user_id_mismatch_rejected(
    client: TestClient, db: Session, test_user: User, test_notification: Notification
):
    """JWT owner cannot spoof a different user_id query (HTTP 403)."""
    other_user = User(
        name="Mismatch User",
        secret_key="mismatch123",
        preferred_language="en",
    )
    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    response = client.post(
        f"/notifications/{test_notification.id}/mark-read",
        params={"user_id": other_user.id},
        headers=_auth_header(test_user.id),
    )
    assert response.status_code == 403


def test_submit_feedback_standardized(client: TestClient, db: Session, test_user: User, test_notification: Notification):
    """Test POST /notifications/{id}/feedback accepts standardized payload"""
    feedback_payload = {
        "feedback": "positive",
        "reason": "Helpful notification",
        "action": None
    }
    
    response = client.post(
        f"/notifications/{test_notification.id}/feedback",
        json=feedback_payload,
        params={"user_id": test_user.id},
        headers=_auth_header(test_user.id),
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["data"]["feedback"] == "positive"


def test_submit_feedback_all_types(client: TestClient, db: Session, test_user: User, test_notification: Notification):
    """Test POST /notifications/{id}/feedback accepts all feedback types"""
    for feedback_type in ["positive", "negative", "neutral"]:
        feedback_payload = {
            "feedback": feedback_type,
            "reason": f"Test {feedback_type}",
            "action": "test_action"
        }
        
        response = client.post(
            f"/notifications/{test_notification.id}/feedback",
            json=feedback_payload,
            params={"user_id": test_user.id},
            headers=_auth_header(test_user.id),
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["data"]["feedback"] == feedback_type


def test_submit_feedback_ownership_validation(client: TestClient, db: Session, test_user: User, test_notification: Notification):
    """Non-owner JWT must not submit feedback on another user's notification (HTTP 403)."""
    other_user = User(
        name="Other User",
        secret_key="other123",
        preferred_language="en"
    )
    db.add(other_user)
    db.commit()
    db.refresh(other_user)
    
    feedback_payload = {
        "feedback": "positive",
        "reason": "Test"
    }
    
    response = client.post(
        f"/notifications/{test_notification.id}/feedback",
        json=feedback_payload,
        params={"user_id": other_user.id},
        headers=_auth_header(other_user.id),
    )
    
    assert response.status_code == 403


def test_get_unread_excludes_read_notifications(client: TestClient, db: Session, test_user: User, test_notification: Notification):
    """Test GET /notifications/unread excludes read notifications"""
    # Mark notification as read
    test_notification.is_read = True
    db.commit()
    
    response = client.get(
        "/notifications/unread",
        params={"user_id": test_user.id, "limit": 20},
        headers=_auth_header(test_user.id),
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    
    # Verify read notification is not in the list
    notification_ids = [n["id"] for n in data["data"]["notifications"]]
    assert test_notification.id not in notification_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
