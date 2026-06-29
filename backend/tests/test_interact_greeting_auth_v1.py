"""JWT is required for GET /interact/greeting (pilot hardening)."""

from __future__ import annotations

from unittest.mock import patch

from backend.app.core.security import create_access_token
from backend.app.models import User


def test_greeting_requires_bearer_token(client, db):
    u = User(name="GreetNoAuth", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)

    response = client.get(f"/interact/greeting?user_id={u.id}&lang=en")
    assert response.status_code == 401


def test_greeting_rejects_mismatched_user_id(client, db):
    u = User(name="GreetAuth", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    token = create_access_token({"user_id": u.id})

    response = client.get(
        f"/interact/greeting?user_id={u.id + 9999}&lang=en",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_greeting_returns_for_authenticated_user(client, db):
    u = User(name="GreetOwner", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    token = create_access_token({"user_id": u.id})

    with patch(
        "backend.app.core.conversation.brain.ConversationBrain.get_greeting",
        return_value={"message": "Hello there"},
    ):
        response = client.get(
            f"/interact/greeting?user_id={u.id}&lang=en",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == u.id
    assert body["message"] == "Hello there"


def test_greeting_works_without_user_id_query(client, db):
    u = User(name="GreetJwtOnly", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    token = create_access_token({"user_id": u.id})

    with patch(
        "backend.app.core.conversation.brain.ConversationBrain.get_greeting",
        return_value={"message": "Hi JWT only"},
    ):
        response = client.get(
            "/interact/greeting?lang=en",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Hi JWT only"
