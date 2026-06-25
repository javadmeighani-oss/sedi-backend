"""JWT is required for user-specific notification endpoints (pilot hardening)."""

from __future__ import annotations

from datetime import datetime

from backend.app.core.security import create_access_token
from backend.app.models import Notification, User

# Valid-looking FCM token for register tests (>=80 chars, no placeholders)
_TEST_FCM_TOKEN = (
    "d" * 80
)


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _create_user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _create_notification(db, user_id: int) -> Notification:
    n = Notification(
        user_id=user_id,
        type="health_alert",
        title="Test",
        body="Body",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def test_notifications_list_requires_auth(client, db):
    u = _create_user(db, "NotifNoAuth")
    response = client.get(f"/notifications/?user_id={u.id}")
    assert response.status_code == 401


def test_notifications_unread_requires_auth(client, db):
    u = _create_user(db, "UnreadNoAuth")
    response = client.get(f"/notifications/unread?user_id={u.id}")
    assert response.status_code == 401


def test_notifications_unread_mismatch_user_id(client, db):
    u = _create_user(db, "UnreadAuth")
    token = _auth_header(u.id)
    response = client.get(
        f"/notifications/unread?user_id={u.id + 9999}",
        headers=token,
    )
    assert response.status_code == 403


def test_notifications_unread_returns_own(client, db):
    u = _create_user(db, "UnreadOwner")
    n = _create_notification(db, u.id)
    response = client.get(
        f"/notifications/unread?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    ids = [item["id"] for item in data["data"]["notifications"]]
    assert n.id in ids


def test_mark_read_rejects_other_users_notification(client, db):
    owner = _create_user(db, "Owner")
    other = _create_user(db, "Other")
    n = _create_notification(db, owner.id)
    response = client.post(
        f"/notifications/{n.id}/mark-read?user_id={other.id}",
        headers=_auth_header(other.id),
    )
    assert response.status_code == 403


def test_mark_read_own_notification(client, db):
    u = _create_user(db, "MarkRead")
    n = _create_notification(db, u.id)
    response = client.post(
        f"/notifications/{n.id}/mark-read?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_feedback_rejects_other_users_notification(client, db):
    owner = _create_user(db, "FbOwner")
    other = _create_user(db, "FbOther")
    n = _create_notification(db, owner.id)
    response = client.post(
        f"/notifications/{n.id}/feedback?user_id={other.id}",
        headers=_auth_header(other.id),
        json={"feedback": "positive"},
    )
    assert response.status_code == 403


def test_prefs_get_requires_auth(client, db):
    u = _create_user(db, "PrefsNoAuth")
    response = client.get(f"/notifications/prefs?user_id={u.id}")
    assert response.status_code == 401


def test_prefs_put_and_get_authenticated(client, db):
    u = _create_user(db, "PrefsAuth")
    headers = _auth_header(u.id)
    put_resp = client.put(
        f"/notifications/prefs?user_id={u.id}",
        headers=headers,
        json={"engagement_level": 2},
    )
    assert put_resp.status_code == 200
    get_resp = client.get(f"/notifications/prefs?user_id={u.id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["engagement_level"] == 2


def test_push_register_requires_auth(client, db):
    u = _create_user(db, "PushNoAuth")
    response = client.post(
        "/notifications/push/register",
        json={
            "user_id": u.id,
            "platform": "android",
            "fcm_token": _TEST_FCM_TOKEN,
        },
    )
    assert response.status_code == 401
