"""JWT is required for user-facing /user/* knowledge endpoints (Phase 1E-b)."""

from __future__ import annotations

from datetime import datetime

from backend.app.core.security import create_access_token
from backend.app.models import User, UserFact, UserProfileKnowledge


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _create_user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _knowledge_body(**overrides) -> dict:
    body = {
        "display_name": "Javad",
        "language": "fa",
        "baseline_summary": "Prefers gentle reminders.",
    }
    body.update(overrides)
    return body


def _fact_body(**overrides) -> dict:
    body = {
        "key": "diet",
        "value_json": "low sodium",
        "source": "manual",
    }
    body.update(overrides)
    return body


def test_user_knowledge_get_requires_auth(client, db):
    _create_user(db, "UkGetNoAuth")
    response = client.get("/user/knowledge")
    assert response.status_code == 401


def test_user_knowledge_put_requires_auth(client, db):
    _create_user(db, "UkPutNoAuth")
    response = client.put("/user/knowledge", json=_knowledge_body())
    assert response.status_code == 401


def test_user_facts_get_requires_auth(client, db):
    _create_user(db, "UfGetNoAuth")
    response = client.get("/user/facts")
    assert response.status_code == 401


def test_user_facts_post_requires_auth(client, db):
    _create_user(db, "UfPostNoAuth")
    response = client.post("/user/facts", json=_fact_body())
    assert response.status_code == 401


def test_user_knowledge_put_works_without_user_id_in_body(client, db):
    u = _create_user(db, "UkPutOwner")
    response = client.put(
        "/user/knowledge",
        json=_knowledge_body(),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("user_id") == u.id
    assert data.get("baseline_summary") == _knowledge_body()["baseline_summary"]


def test_user_knowledge_put_rejects_legacy_user_id_in_body(client, db):
    u = _create_user(db, "UkPutLegacy")
    response = client.put(
        "/user/knowledge",
        json=_knowledge_body(user_id=u.id + 9999),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_user_knowledge_get_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "UkGetLegacy")
    db.add(
        UserProfileKnowledge(
            user_id=u.id,
            baseline_summary="owner only",
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()
    response = client.get(
        f"/user/knowledge?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_user_facts_post_works_without_user_id_in_body(client, db):
    u = _create_user(db, "UfPostOwner")
    response = client.post(
        "/user/facts",
        json=_fact_body(),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("user_id") == u.id
    assert data.get("key") == "diet"


def test_user_facts_post_rejects_legacy_user_id_in_body(client, db):
    u = _create_user(db, "UfPostLegacy")
    response = client.post(
        "/user/facts",
        json=_fact_body(user_id=u.id + 9999),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_user_facts_get_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "UfGetLegacy")
    response = client.get(
        f"/user/facts?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_user_knowledge_cross_user_isolation(client, db):
    user_a = _create_user(db, "UkUserA")
    user_b = _create_user(db, "UkUserB")
    db.add(
        UserProfileKnowledge(
            user_id=user_b.id,
            baseline_summary="User B secret baseline",
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()

    response = client.get("/user/knowledge", headers=_auth_header(user_a.id))
    assert response.status_code == 404


def test_user_facts_cross_user_isolation(client, db):
    user_a = _create_user(db, "UfUserA")
    user_b = _create_user(db, "UfUserB")
    db.add(
        UserFact(
            user_id=user_b.id,
            key="secret",
            value_json="hidden",
            source="manual",
            confidence=0.9,
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()

    response = client.get("/user/facts", headers=_auth_header(user_a.id))
    assert response.status_code == 200
    assert response.json() == []
