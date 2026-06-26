"""JWT is required for user-facing health endpoints (Phase 1C)."""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.app.core.security import create_access_token
from backend.app.models import HealthData, User


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _create_user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _add_body(**overrides) -> dict:
    body = {
        "heart_rate": 82.0,
        "temperature": 36.8,
        "spo2": 97.0,
    }
    body.update(overrides)
    return body


def _insert_health(db, user_id: int, heart_rate: str, *, minutes_ago: int = 0) -> HealthData:
    created_at = datetime.utcnow() - timedelta(minutes=minutes_ago)
    row = HealthData(
        user_id=user_id,
        heart_rate=heart_rate,
        temperature="36.5",
        spo2="98",
        created_at=created_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_health_add_requires_auth(client, db):
    _create_user(db, "HealthAddNoAuth")
    response = client.post("/health/add", json=_add_body())
    assert response.status_code == 401


def test_health_add_works_without_user_id_in_body(client, db):
    u = _create_user(db, "HealthAddOwner")
    response = client.post(
        "/health/add",
        json=_add_body(),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    assert data.get("data", {}).get("user_id") == u.id
    assert data.get("data", {}).get("health_id") is not None


def test_health_add_rejects_legacy_user_id_in_body(client, db):
    u = _create_user(db, "HealthLegacyReject")
    body = _add_body(user_id=u.id + 9999)
    response = client.post(
        "/health/add",
        json=body,
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_health_latest_requires_auth(client, db):
    _create_user(db, "HealthLatestNoAuth")
    response = client.get("/health/latest")
    assert response.status_code == 401


def test_health_context_requires_auth(client, db):
    _create_user(db, "HealthCtxNoAuth")
    response = client.get("/health/context")
    assert response.status_code == 401


def test_health_latest_returns_authenticated_user_data(client, db):
    u = _create_user(db, "HealthLatestOwner")
    _insert_health(db, u.id, "75", minutes_ago=5)
    _insert_health(db, u.id, "88", minutes_ago=0)

    response = client.get("/health/latest", headers=_auth_header(u.id))
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    latest = payload.get("data")
    assert latest is not None
    assert latest.get("user_id") == u.id
    assert latest.get("heart_rate") == 88.0


def test_health_context_returns_authenticated_user_context(client, db):
    u = _create_user(db, "HealthCtxOwner")
    _insert_health(db, u.id, "70", minutes_ago=10)
    _insert_health(db, u.id, "72", minutes_ago=0)

    response = client.get("/health/context", headers=_auth_header(u.id))
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    ctx = payload.get("data") or {}
    assert ctx.get("total_records") == 2
    assert ctx.get("latest", {}).get("heart_rate") == 72.0
    assert ctx.get("last_update_minutes_ago") is not None


def test_health_cross_user_isolation(client, db):
    user_a = _create_user(db, "HealthUserA")
    user_b = _create_user(db, "HealthUserB")
    _insert_health(db, user_b.id, "120", minutes_ago=0)

    response = client.get("/health/latest", headers=_auth_header(user_a.id))
    assert response.status_code == 200
    assert response.json().get("data") is None

    ctx_resp = client.get("/health/context", headers=_auth_header(user_a.id))
    assert ctx_resp.status_code == 200
    ctx = ctx_resp.json().get("data") or {}
    assert ctx.get("total_records") == 0
    assert ctx.get("latest") is None

    write = client.post(
        "/health/add",
        json=_add_body(heart_rate=80.0),
        headers=_auth_header(user_a.id),
    )
    assert write.status_code == 200 and write.json().get("ok") is True

    b_latest = (
        db.query(HealthData)
        .filter(HealthData.user_id == user_b.id)
        .order_by(HealthData.id.desc())
        .first()
    )
    assert b_latest is not None
    assert float(b_latest.heart_rate) == 120.0


def test_system_health_monitoring_unchanged(client):
    """GET /health remains public system monitoring (not user vitals)."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    assert "version" in data
    assert data.get("env") in ("prod", "dev")
    assert data.get("db") in ("ok", "error")
    assert "timestamp" in data


def test_device_ingest_still_requires_device_token(client):
    """Smoke: device ingest auth path unchanged (no JWT on ingest)."""
    response = client.post(
        "/device/ingest",
        json={
            "user_id": 1,
            "event_type": "heart_rate",
            "payload": {"bpm": 82},
        },
    )
    assert response.status_code == 422
