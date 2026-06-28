"""JWT is required for user-facing POST /ai_core/analyze (Phase 1E-d)."""

from __future__ import annotations

from datetime import datetime

from backend.app.core.security import create_access_token
from backend.app.models import HealthData, Memory, Notification, User


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _create_user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _insert_health(db, user_id: int, *, heart_rate: str = "82") -> HealthData:
    row = HealthData(
        user_id=user_id,
        heart_rate=heart_rate,
        temperature="36.8",
        spo2="97",
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _mock_generate_notification_text(**kwargs) -> str:
    return "Mock health insight for analyze smoke test."


def test_ai_core_analyze_requires_auth(client, db):
    _create_user(db, "AiCoreNoAuth")
    response = client.post("/ai_core/analyze")
    assert response.status_code == 401


def test_ai_core_analyze_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "AiCoreLegacyQuery")
    response = client.post(
        "/ai_core/analyze?user_id=999999",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_ai_core_analyze_no_data_for_authenticated_user_without_health(client, db):
    u = _create_user(db, "AiCoreNoData")
    response = client.post("/ai_core/analyze", headers=_auth_header(u.id))
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is False
    assert payload.get("error", {}).get("code") == "NO_DATA"


def test_ai_core_analyze_success_with_jwt_and_mocked_ai(client, db, monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.ai_core.generate_notification_text",
        _mock_generate_notification_text,
    )
    u = _create_user(db, "AiCoreOwner")
    _insert_health(db, u.id)

    response = client.post("/ai_core/analyze", headers=_auth_header(u.id))
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    data = payload.get("data") or {}
    assert data.get("user_id") == u.id
    notification = data.get("notification") or {}
    assert notification.get("id") is not None
    assert notification.get("body")

    notif = db.query(Notification).filter(Notification.id == notification["id"]).first()
    assert notif is not None
    assert notif.user_id == u.id

    memory_rows = (
        db.query(Memory)
        .filter(Memory.user_id == u.id, Memory.sedi_response == _mock_generate_notification_text())
        .count()
    )
    assert memory_rows >= 1


def test_ai_core_analyze_cross_user_isolation(client, db, monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.ai_core.generate_notification_text",
        _mock_generate_notification_text,
    )
    user_a = _create_user(db, "AiCoreUserA")
    user_b = _create_user(db, "AiCoreUserB")
    _insert_health(db, user_b.id, heart_rate="110")

    notif_b_before = db.query(Notification).filter(Notification.user_id == user_b.id).count()
    memory_b_before = db.query(Memory).filter(Memory.user_id == user_b.id).count()

    response = client.post("/ai_core/analyze", headers=_auth_header(user_a.id))
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is False
    assert payload.get("error", {}).get("code") == "NO_DATA"

    notif_b_after = db.query(Notification).filter(Notification.user_id == user_b.id).count()
    memory_b_after = db.query(Memory).filter(Memory.user_id == user_b.id).count()
    assert notif_b_after == notif_b_before
    assert memory_b_after == memory_b_before

    notif_a = db.query(Notification).filter(Notification.user_id == user_a.id).count()
    memory_a = db.query(Memory).filter(Memory.user_id == user_a.id).count()
    assert notif_a == 0
    assert memory_a == 0


def test_ai_core_analyze_uses_only_authenticated_user_health(client, db, monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.ai_core.generate_notification_text",
        _mock_generate_notification_text,
    )
    user_a = _create_user(db, "AiCoreScopedA")
    user_b = _create_user(db, "AiCoreScopedB")
    _insert_health(db, user_a.id, heart_rate="75")
    _insert_health(db, user_b.id, heart_rate="120")

    response = client.post("/ai_core/analyze", headers=_auth_header(user_a.id))
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    assert payload.get("data", {}).get("user_id") == user_a.id

    notif_b = db.query(Notification).filter(Notification.user_id == user_b.id).count()
    assert notif_b == 0
