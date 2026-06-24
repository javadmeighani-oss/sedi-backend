"""JWT is required for POST /interact/chat (pilot stabilization)."""

from __future__ import annotations

from backend.app.core.security import create_access_token
from backend.app.models import User


def test_chat_requires_bearer_token(client, db):
    u = User(name="NoAuth", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)

    response = client.post(
        "/interact/chat",
        json={"user_id": u.id, "message": "hello"},
    )
    assert response.status_code == 401


def test_chat_rejects_mismatched_user_id(client, db):
    u = User(name="AuthUser", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    token = create_access_token({"user_id": u.id})

    response = client.post(
        "/interact/chat",
        json={"user_id": u.id + 9999, "message": "timezone: Asia/Tehran"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
