"""
Acceptance A3: Devices E2E V1 flow

Scenario:
/devices/register -> rotate-token -> revoke -> /device/ingest behavior checks
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.core.security import create_access_token
from backend.tests.test_db_config import get_test_database_url


_BLOCKED_DB_SUBSTRINGS = ("sedi_db", "prod", "production")


def _is_production_db_url(url: str) -> bool:
    u = (url or "").lower()
    return any(blocked in u for blocked in _BLOCKED_DB_SUBSTRINGS)


def _env_indicates_production() -> bool:
    env = (os.environ.get("ENV") or "").lower()
    app_env = (os.environ.get("APP_ENV") or "").lower()
    return env == "production" or app_env == "production"


_test_db_url = get_test_database_url()
if _env_indicates_production():
    raise RuntimeError("Refusing to run acceptance tests: ENV or APP_ENV indicates production.")
if _is_production_db_url(_test_db_url):
    raise RuntimeError(
        "Refusing to run acceptance tests against a production-like DB URL. "
        "Set TEST_DATABASE_URL to a safe test database (e.g. sedi_test)."
    )


@pytest.fixture
def devices_e2e_user(db: Session) -> models.User:
    user = db.query(models.User).filter(models.User.id == 1002).first()
    if user is None:
        user = models.User(
            id=1002,
            name="Devices E2E User",
            secret_key="devices-e2e-secret",
            preferred_language="en",
            created_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _extract_token(response_json: dict) -> str | None:
    data = response_json.get("data")
    if not isinstance(data, dict):
        return None
    token = data.get("token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


def _ingest_payload(user_id: int, device_id: str) -> dict:
    return {
        "user_id": user_id,
        "device_id": device_id,
        "event_type": "heart_rate",
        "payload": {"bpm": 82, "quality": "good"},
    }


def _assert_ingest_rejected(response) -> None:
    # Depending on endpoint implementation, rejection may be 401/403
    # or 200 with ok=false envelope.
    if response.status_code in (401, 403):
        return
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is False, body


def test_devices_e2e_register_rotate_revoke_ingest_behavior(
    client: TestClient,
    db: Session,
    devices_e2e_user: models.User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Match V1 production auth mode.
    monkeypatch.setenv("DEVICE_AUTH_MODE", "db_only")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)

    user_id = devices_e2e_user.id
    device_id = "AccV1Device001"

    # Keep test idempotent if the same logical device id already exists.
    db.query(models.Device).filter(models.Device.device_id == device_id).delete(synchronize_session=False)
    db.commit()

    list_res = client.get("/devices", headers=_auth_header(user_id))
    assert list_res.status_code == 200, list_res.text
    assert list_res.json().get("ok") is True

    register_res = client.post(
        "/devices/register",
        json={"device_id": device_id, "device_type": "heart_rate"},
        headers=_auth_header(user_id),
    )
    assert register_res.status_code == 200, register_res.text
    register_json = register_res.json()
    assert register_json.get("ok") is True, register_json

    token_1 = _extract_token(register_json)
    if token_1 is None:
        rotate_bootstrap = client.post(f"/devices/{device_id}/rotate-token", headers=_auth_header(user_id))
        assert rotate_bootstrap.status_code == 200, rotate_bootstrap.text
        token_1 = _extract_token(rotate_bootstrap.json())
    assert isinstance(token_1, str) and token_1

    ingest_1 = client.post(
        "/device/ingest",
        headers={"X-DEVICE-TOKEN": token_1},
        json=_ingest_payload(user_id, device_id),
    )
    assert ingest_1.status_code == 200, ingest_1.text
    assert ingest_1.json().get("ok") is True, ingest_1.json()

    rotate_res = client.post(f"/devices/{device_id}/rotate-token", headers=_auth_header(user_id))
    assert rotate_res.status_code == 200, rotate_res.text
    rotate_json = rotate_res.json()
    assert rotate_json.get("ok") is True, rotate_json
    token_2 = _extract_token(rotate_json)
    assert isinstance(token_2, str) and token_2
    assert token_2 != token_1

    ingest_2 = client.post(
        "/device/ingest",
        headers={"X-DEVICE-TOKEN": token_2},
        json=_ingest_payload(user_id, device_id),
    )
    assert ingest_2.status_code == 200, ingest_2.text
    assert ingest_2.json().get("ok") is True, ingest_2.json()

    ingest_old_token = client.post(
        "/device/ingest",
        headers={"X-DEVICE-TOKEN": token_1},
        json=_ingest_payload(user_id, device_id),
    )
    _assert_ingest_rejected(ingest_old_token)

    revoke_res = client.post(f"/devices/{device_id}/revoke", headers=_auth_header(user_id))
    assert revoke_res.status_code == 200, revoke_res.text
    assert revoke_res.json().get("ok") is True

    ingest_after_revoke = client.post(
        "/device/ingest",
        headers={"X-DEVICE-TOKEN": token_2},
        json=_ingest_payload(user_id, device_id),
    )
    _assert_ingest_rejected(ingest_after_revoke)
