"""JWT is required for user-facing /conditions/* endpoints (Phase 1E-c)."""

from __future__ import annotations

from datetime import datetime

from backend.app.core.security import create_access_token
from backend.app.models import MedicalCondition, User, UserCondition


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _create_user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _create_condition(db, name: str) -> MedicalCondition:
    cond = MedicalCondition(
        name=name,
        description="Test condition",
        category="chronic",
        created_at=datetime.utcnow(),
    )
    db.add(cond)
    db.commit()
    db.refresh(cond)
    return cond


def _assign_body(condition_id: int, **overrides) -> dict:
    body = {
        "condition_id": condition_id,
        "severity": "moderate",
        "notes": "Test assignment",
    }
    body.update(overrides)
    return body


def test_conditions_catalog_public_without_auth(client, db):
    _create_condition(db, "CondCatalogPublic")
    response = client.get("/conditions")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    assert "conditions" in (payload.get("data") or {})


def test_conditions_user_get_requires_auth(client, db):
    _create_user(db, "CondUserNoAuth")
    response = client.get("/conditions/user")
    assert response.status_code == 401


def test_conditions_assign_requires_auth(client, db):
    cond = _create_condition(db, "CondAssignNoAuth")
    response = client.post("/conditions/assign", json=_assign_body(cond.id))
    assert response.status_code == 401


def test_conditions_delete_requires_auth(client, db):
    _create_condition(db, "CondDeleteNoAuth")
    response = client.delete("/conditions/user/condition/1")
    assert response.status_code == 401


def test_conditions_user_get_works_with_jwt(client, db):
    u = _create_user(db, "CondUserOwner")
    cond = _create_condition(db, "CondUserOwnerCond")
    db.add(
        UserCondition(
            user_id=u.id,
            condition_id=cond.id,
            severity="mild",
            created_at=datetime.utcnow(),
        )
    )
    db.commit()

    response = client.get("/conditions/user", headers=_auth_header(u.id))
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    items = (payload.get("data") or {}).get("user_conditions") or []
    assert len(items) == 1
    assert items[0].get("user_id") == u.id
    assert items[0].get("condition_id") == cond.id


def test_conditions_assign_works_without_user_id_in_body(client, db):
    u = _create_user(db, "CondAssignOwner")
    cond = _create_condition(db, "CondAssignOwnerCond")
    response = client.post(
        "/conditions/assign",
        json=_assign_body(cond.id),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    data = payload.get("data") or {}
    assert data.get("user_id") == u.id
    assert data.get("condition_id") == cond.id
    assert data.get("severity") == "moderate"


def test_conditions_delete_works_with_jwt(client, db):
    u = _create_user(db, "CondDeleteOwner")
    cond = _create_condition(db, "CondDeleteOwnerCond")
    db.add(
        UserCondition(
            user_id=u.id,
            condition_id=cond.id,
            created_at=datetime.utcnow(),
        )
    )
    db.commit()

    response = client.delete(
        f"/conditions/user/condition/{cond.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True

    remaining = (
        db.query(UserCondition)
        .filter(UserCondition.user_id == u.id, UserCondition.condition_id == cond.id)
        .count()
    )
    assert remaining == 0


def test_conditions_user_get_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "CondUserLegacyQuery")
    response = client.get(
        f"/conditions/user?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_conditions_delete_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "CondDeleteLegacyQuery")
    cond = _create_condition(db, "CondDeleteLegacyQueryCond")
    response = client.delete(
        f"/conditions/user/condition/{cond.id}?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_conditions_assign_rejects_legacy_user_id_in_body(client, db):
    u = _create_user(db, "CondAssignLegacyBody")
    cond = _create_condition(db, "CondAssignLegacyBodyCond")
    response = client.post(
        "/conditions/assign",
        json=_assign_body(cond.id, user_id=u.id + 9999),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_conditions_old_user_id_path_returns_404(client, db):
    u = _create_user(db, "CondOldPath")
    response = client.get(
        f"/conditions/user/{u.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 404


def test_conditions_cross_user_isolation(client, db):
    user_a = _create_user(db, "CondUserA")
    user_b = _create_user(db, "CondUserB")
    cond = _create_condition(db, "CondCrossUser")
    db.add(
        UserCondition(
            user_id=user_b.id,
            condition_id=cond.id,
            severity="severe",
            notes="User B only",
            created_at=datetime.utcnow(),
        )
    )
    db.commit()

    read = client.get("/conditions/user", headers=_auth_header(user_a.id))
    assert read.status_code == 200
    items = (read.json().get("data") or {}).get("user_conditions") or []
    assert items == []

    delete = client.delete(
        f"/conditions/user/condition/{cond.id}",
        headers=_auth_header(user_a.id),
    )
    assert delete.status_code == 200
    assert delete.json().get("ok") is False
    assert delete.json().get("error", {}).get("code") == "CONDITION_NOT_ASSIGNED"

    still_assigned = (
        db.query(UserCondition)
        .filter(UserCondition.user_id == user_b.id, UserCondition.condition_id == cond.id)
        .count()
    )
    assert still_assigned == 1
