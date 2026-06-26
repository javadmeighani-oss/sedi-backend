"""JWT is required for user-facing lifestyle endpoints; admin routes are fail-closed (Phase 1B)."""

from __future__ import annotations

import json

from backend.app.core.security import create_access_token
from backend.app.models import User, UserFactCandidate, UserMemoryFact
from backend.app.services.memory import MemoryRepository

_TEST_ADMIN_TOKEN = "test-lifestyle-admin-token"


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _admin_header(token: str = _TEST_ADMIN_TOKEN) -> dict[str, str]:
    return {"X-Admin-Token": token}


def _create_user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _update_body(**overrides) -> dict:
    body = {
        "entries": [
            {
                "domain": "lifestyle",
                "key": "sleep_duration_hours",
                "value": 7.5,
                "confidence": 0.8,
                "source": "manual",
            }
        ]
    }
    body.update(overrides)
    return body


def test_lifestyle_update_requires_auth(client, db):
    u = _create_user(db, "LifeUpNoAuth")
    response = client.post("/lifestyle/update", json=_update_body())
    assert response.status_code == 401


def test_lifestyle_context_requires_auth(client, db):
    _create_user(db, "LifeCtxNoAuth")
    response = client.get("/lifestyle/context")
    assert response.status_code == 401


def test_lifestyle_summary_requires_auth(client, db):
    _create_user(db, "LifeSumNoAuth")
    response = client.get("/lifestyle/summary")
    assert response.status_code == 401


def test_lifestyle_update_works_without_user_id_in_body(client, db):
    u = _create_user(db, "LifeUpOwner")
    response = client.post(
        "/lifestyle/update",
        json=_update_body(),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    assert data.get("data", {}).get("updated_count") == 1


def test_lifestyle_context_works_without_user_id_query(client, db):
    u = _create_user(db, "LifeCtxOwner")
    repo = MemoryRepository(db)
    repo.upsert_fact(
        user_id=u.id,
        domain="lifestyle",
        key="sleep_duration_hours",
        value=6.0,
        confidence=0.9,
        source="manual",
    )
    response = client.get("/lifestyle/context", headers=_auth_header(u.id))
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    ctx = payload.get("data") or {}
    assert ctx.get("sleep_duration_hours") == 6.0


def test_lifestyle_summary_works_without_user_id_query(client, db):
    u = _create_user(db, "LifeSumOwner")
    response = client.get("/lifestyle/summary", headers=_auth_header(u.id))
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    assert "sections" in (payload.get("data") or {})


def test_lifestyle_update_rejects_legacy_user_id_in_body(client, db):
    u = _create_user(db, "LifeLegacyReject")
    body = _update_body(user_id=u.id + 9999)
    response = client.post(
        "/lifestyle/update",
        json=body,
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_lifestyle_cross_user_isolation(client, db):
    user_a = _create_user(db, "LifeUserA")
    user_b = _create_user(db, "LifeUserB")

    repo = MemoryRepository(db)
    repo.upsert_fact(
        user_id=user_b.id,
        domain="lifestyle",
        key="sleep_duration_hours",
        value=99.0,
        confidence=0.9,
        source="manual",
    )

    response = client.get("/lifestyle/context", headers=_auth_header(user_a.id))
    assert response.status_code == 200
    ctx = (response.json().get("data") or {})
    assert ctx.get("sleep_duration_hours") != 99.0

    write = client.post(
        "/lifestyle/update",
        json=_update_body(),
        headers=_auth_header(user_a.id),
    )
    assert write.status_code == 200 and write.json().get("ok") is True

    fact_b = (
        db.query(UserMemoryFact)
        .filter(
            UserMemoryFact.user_id == user_b.id,
            UserMemoryFact.key == "sleep_duration_hours",
        )
        .first()
    )
    assert fact_b is not None
    assert json.loads(fact_b.value_json) == 99.0


def test_admin_candidates_fails_when_admin_token_not_configured(client, db, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    u = _create_user(db, "AdminNoCfg")
    response = client.get(f"/lifestyle/admin/candidates?user_id={u.id}")
    assert response.status_code == 403
    assert response.json().get("detail") == "admin_disabled"


def test_admin_candidates_returns_403_when_header_missing(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    u = _create_user(db, "AdminNoHdr")
    response = client.get(f"/lifestyle/admin/candidates?user_id={u.id}")
    assert response.status_code == 403
    assert response.json().get("detail") == "forbidden"


def test_admin_candidates_returns_403_when_header_wrong(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    u = _create_user(db, "AdminBadHdr")
    response = client.get(
        f"/lifestyle/admin/candidates?user_id={u.id}",
        headers=_admin_header("wrong-admin-token"),
    )
    assert response.status_code == 403
    assert response.json().get("detail") == "forbidden"


def test_admin_candidates_works_with_correct_admin_token(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    u = _create_user(db, "AdminOk")
    db.add(
        UserFactCandidate(
            user_id=u.id,
            domain="lifestyle",
            key="sleep_duration_hours",
            value_json="7.0",
            confidence=0.9,
            is_explicit=True,
            status="pending",
        )
    )
    db.commit()
    response = client.get(
        f"/lifestyle/admin/candidates?user_id={u.id}",
        headers=_admin_header(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    assert payload.get("data", {}).get("count") == 1


def test_admin_candidate_decision_requires_admin_token(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    response = client.post(
        "/lifestyle/admin/candidates/1/decision",
        json={"status": "rejected"},
    )
    assert response.status_code == 403
    assert response.json().get("detail") == "forbidden"


def test_admin_candidate_decision_works_with_correct_admin_token(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    u = _create_user(db, "AdminDecision")
    cand = UserFactCandidate(
        user_id=u.id,
        domain="lifestyle",
        key="sleep_duration_hours",
        value_json="8.0",
        confidence=0.9,
        is_explicit=True,
        status="pending",
    )
    db.add(cand)
    db.commit()
    db.refresh(cand)
    response = client.post(
        f"/lifestyle/admin/candidates/{cand.id}/decision",
        json={"status": "rejected"},
        headers=_admin_header(),
    )
    assert response.status_code == 200
    assert response.json().get("ok") is True
    assert response.json().get("data", {}).get("status") == "rejected"


def test_admin_source_preview_requires_admin_token(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    response = client.get("/lifestyle/admin/source_preview?type=user_memory_fact&id=1")
    assert response.status_code == 403
    assert response.json().get("detail") == "forbidden"


def test_admin_source_preview_works_with_correct_admin_token(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    u = _create_user(db, "AdminPreview")
    repo = MemoryRepository(db)
    fact = repo.upsert_fact(
        user_id=u.id,
        domain="lifestyle",
        key="sleep_duration_hours",
        value=6.5,
        confidence=0.8,
        source="manual",
    )
    response = client.get(
        f"/lifestyle/admin/source_preview?type=user_memory_fact&id={fact.id}",
        headers=_admin_header(),
    )
    assert response.status_code == 200
    assert response.json().get("ok") is True
    preview = response.json().get("data", {}).get("preview", {})
    assert preview.get("key") == "sleep_duration_hours"
