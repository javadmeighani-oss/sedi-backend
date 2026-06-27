"""JWT is required for user-facing /devices/* endpoints (Phase 1D-a)."""

from __future__ import annotations

from datetime import datetime

from backend.app.core.device_auth import hash_device_token
from backend.app.core.security import create_access_token
from backend.app.models import Device, User


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _create_user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _register_body(device_id: str) -> dict:
    return {"device_id": device_id, "device_type": "heart_rate"}


def test_devices_register_requires_auth(client, db):
    _create_user(db, "DevRegNoAuth")
    response = client.post("/devices/register", json=_register_body("DevNoAuth001"))
    assert response.status_code == 401


def test_devices_list_requires_auth(client, db):
    _create_user(db, "DevListNoAuth")
    response = client.get("/devices")
    assert response.status_code == 401


def test_devices_revoke_requires_auth(client, db):
    _create_user(db, "DevRevNoAuth")
    response = client.post("/devices/SomeDevice/revoke")
    assert response.status_code == 401


def test_devices_rotate_requires_auth(client, db):
    _create_user(db, "DevRotNoAuth")
    response = client.post("/devices/SomeDevice/rotate-token")
    assert response.status_code == 401


def test_devices_register_works_without_user_id_query(client, db):
    u = _create_user(db, "DevRegOwner")
    response = client.post(
        "/devices/register",
        json=_register_body("DevOwner001"),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    token = data.get("data", {}).get("token")
    assert isinstance(token, str) and len(token) >= 32
    dev = db.query(Device).filter(Device.device_id == "DevOwner001").first()
    assert dev is not None
    assert dev.user_id == u.id
    assert dev.token_hash == hash_device_token(token)


def test_devices_register_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "DevRegLegacy")
    response = client.post(
        f"/devices/register?user_id={u.id + 9999}",
        json=_register_body("DevLegacy001"),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_devices_list_works_and_returns_only_owner_devices(client, db):
    owner = _create_user(db, "DevListOwner")
    other = _create_user(db, "DevListOther")
    db.add(
        Device(
            user_id=other.id,
            device_id="OtherDevList001",
            device_type="heart_rate",
            status="active",
            token_hash=hash_device_token("other-token-placeholder"),
            created_at=datetime.utcnow(),
        )
    )
    db.commit()

    reg = client.post(
        "/devices/register",
        json=_register_body("OwnerDevList001"),
        headers=_auth_header(owner.id),
    )
    assert reg.status_code == 200 and reg.json().get("ok") is True

    response = client.get("/devices", headers=_auth_header(owner.id))
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    devices = (payload.get("data") or {}).get("devices") or []
    device_ids = {d.get("device_id") for d in devices}
    assert "OwnerDevList001" in device_ids
    assert "OtherDevList001" not in device_ids


def test_devices_list_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "DevListLegacy")
    response = client.get(f"/devices?user_id={u.id}", headers=_auth_header(u.id))
    assert response.status_code == 422


def test_devices_revoke_works_only_for_owner(client, db):
    u = _create_user(db, "DevRevOwner")
    reg = client.post(
        "/devices/register",
        json=_register_body("DevRevOwner001"),
        headers=_auth_header(u.id),
    )
    assert reg.status_code == 200

    response = client.post(
        "/devices/DevRevOwner001/revoke",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    assert response.json().get("ok") is True
    dev = db.query(Device).filter(Device.device_id == "DevRevOwner001").first()
    assert dev is not None
    assert dev.status == "revoked"


def test_devices_revoke_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "DevRevLegacy")
    response = client.post(
        f"/devices/FakeDev/revoke?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_devices_rotate_works_only_for_owner(client, db):
    u = _create_user(db, "DevRotOwner")
    reg = client.post(
        "/devices/register",
        json=_register_body("DevRotOwner001"),
        headers=_auth_header(u.id),
    )
    token1 = reg.json().get("data", {}).get("token")
    assert token1

    response = client.post(
        "/devices/DevRotOwner001/rotate-token",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    token2 = data.get("data", {}).get("token")
    assert isinstance(token2, str) and token2 != token1


def test_devices_rotate_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "DevRotLegacy")
    response = client.post(
        f"/devices/FakeDev/rotate-token?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_devices_cross_user_revoke_isolation(client, db):
    user_a = _create_user(db, "DevUserA")
    user_b = _create_user(db, "DevUserB")
    reg = client.post(
        "/devices/register",
        json=_register_body("DevCrossB001"),
        headers=_auth_header(user_b.id),
    )
    assert reg.status_code == 200

    response = client.post(
        "/devices/DevCrossB001/revoke",
        headers=_auth_header(user_a.id),
    )
    assert response.status_code == 200
    assert response.json().get("ok") is False
    assert response.json().get("error", {}).get("code") == "DEVICE_NOT_FOUND"

    dev = db.query(Device).filter(Device.device_id == "DevCrossB001").first()
    assert dev is not None
    assert dev.status == "active"


def test_devices_cross_user_rotate_isolation(client, db):
    user_a = _create_user(db, "DevUserARot")
    user_b = _create_user(db, "DevUserBRot")
    reg = client.post(
        "/devices/register",
        json=_register_body("DevCrossRotB001"),
        headers=_auth_header(user_b.id),
    )
    old_hash = db.query(Device).filter(Device.device_id == "DevCrossRotB001").first().token_hash

    response = client.post(
        "/devices/DevCrossRotB001/rotate-token",
        headers=_auth_header(user_a.id),
    )
    assert response.status_code == 200
    assert response.json().get("ok") is False

    dev = db.query(Device).filter(Device.device_id == "DevCrossRotB001").first()
    assert dev.token_hash == old_hash


def test_devices_cross_user_list_isolation(client, db):
    user_a = _create_user(db, "DevListA")
    user_b = _create_user(db, "DevListB")
    client.post(
        "/devices/register",
        json=_register_body("DevListBOnly"),
        headers=_auth_header(user_b.id),
    )

    response = client.get("/devices", headers=_auth_header(user_a.id))
    assert response.status_code == 200
    devices = (response.json().get("data") or {}).get("devices") or []
    assert all(d.get("device_id") != "DevListBOnly" for d in devices)
