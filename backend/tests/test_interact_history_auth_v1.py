"""JWT is required for user-specific history endpoints (pilot stabilization)."""

from __future__ import annotations

from backend.app.core.security import create_access_token
from backend.app.models import Memory, User


def test_interact_history_requires_bearer_token(client, db):
    u = User(name="HistNoAuth", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)

    response = client.get(f"/interact/history?user_id={u.id}&limit=5")
    assert response.status_code == 401


def test_interact_history_rejects_mismatched_user_id(client, db):
    u = User(name="HistAuth", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    token = create_access_token({"user_id": u.id})

    response = client.get(
        f"/interact/history?user_id={u.id + 9999}&limit=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_interact_history_returns_own_messages(client, db):
    u = User(name="HistOwner", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(
        Memory(
            user_id=u.id,
            user_message="hello",
            sedi_response="hi",
            language="en",
        )
    )
    db.commit()
    token = create_access_token({"user_id": u.id})

    response = client.get(
        f"/interact/history?user_id={u.id}&limit=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == u.id
    assert len(body["messages"]) == 1
    assert body["messages"][0]["user_message"] == "hello"


def test_memory_history_requires_bearer_token(client, db):
    u = User(name="MemNoAuth", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)

    response = client.get(f"/memory/history?user_id={u.id}&group=daily&limit=10")
    assert response.status_code == 401


def test_memory_history_rejects_mismatched_user_id(client, db):
    u = User(name="MemAuth", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    token = create_access_token({"user_id": u.id})

    response = client.get(
        f"/memory/history?user_id={u.id + 9999}&group=daily&limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_memory_history_returns_own_groups(client, db):
    u = User(name="MemOwner", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(
        Memory(
            user_id=u.id,
            user_message="ping",
            sedi_response="pong",
            language="en",
        )
    )
    db.commit()
    token = create_access_token({"user_id": u.id})

    response = client.get(
        f"/memory/history?user_id={u.id}&group=daily&limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["group"] == "daily"
    assert len(body["items"]) >= 1
    assert body["items"][0]["turns"][0]["user_message"] == "ping"
