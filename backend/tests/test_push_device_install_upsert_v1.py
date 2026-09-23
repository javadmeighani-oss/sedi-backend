"""PushDevice register upsert by installation device_id (no schema change)."""

from __future__ import annotations

from backend.app.core.security import create_access_token
from backend.app.models import PushDevice, User


def _tok(n: int) -> str:
    return (f"fcm{n}" + "x" * 80)[:96]


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


def _user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _register(client, user_id: int, token: str, device_id: str | None = None):
    body = {
        "user_id": user_id,
        "platform": "android",
        "fcm_token": token,
    }
    if device_id is not None:
        body["device_id"] = device_id
    return client.post(
        "/notifications/push/register",
        headers=_auth(user_id),
        json=body,
    )


def test_same_install_new_token_updates_same_row(client, db):
    u = _user(db, "InstallRotate")
    r1 = _register(client, u.id, _tok(1), "install-a")
    assert r1.status_code == 200
    row_id = r1.json()["data"]["device_id"]
    r2 = _register(client, u.id, _tok(2), "install-a")
    assert r2.status_code == 200
    assert r2.json()["data"]["device_id"] == row_id
    rows = db.query(PushDevice).filter(PushDevice.user_id == u.id).all()
    assert len(rows) == 1
    assert rows[0].id == row_id
    assert rows[0].device_id == "install-a"
    assert rows[0].fcm_token == _tok(2)
    assert rows[0].is_active is True


def test_same_install_same_token_same_row(client, db):
    u = _user(db, "InstallRepeat")
    r1 = _register(client, u.id, _tok(3), "install-b")
    r2 = _register(client, u.id, _tok(3), "install-b")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["data"]["device_id"] == r2.json()["data"]["device_id"]
    assert db.query(PushDevice).filter(PushDevice.user_id == u.id).count() == 1


def test_two_device_ids_two_active_rows(client, db):
    u = _user(db, "MultiInstall")
    a = _register(client, u.id, _tok(4), "install-one")
    b = _register(client, u.id, _tok(5), "install-two")
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["data"]["device_id"] != b.json()["data"]["device_id"]
    rows = db.query(PushDevice).filter(PushDevice.user_id == u.id, PushDevice.is_active.is_(True)).all()
    assert len(rows) == 2


def test_legacy_register_without_device_id(client, db):
    u = _user(db, "LegacyNoDevice")
    r1 = _register(client, u.id, _tok(6), None)
    r2 = _register(client, u.id, _tok(6), None)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["data"]["device_id"] == r2.json()["data"]["device_id"]
    assert db.query(PushDevice).filter(PushDevice.user_id == u.id).count() == 1
    assert db.query(PushDevice).filter(PushDevice.user_id == u.id).one().device_id is None


def test_legacy_token_row_acquires_device_id(client, db):
    u = _user(db, "LegacyAttach")
    first = _register(client, u.id, _tok(7), None)
    assert first.status_code == 200
    row_id = first.json()["data"]["device_id"]
    second = _register(client, u.id, _tok(7), "install-attached")
    assert second.status_code == 200
    assert second.json()["data"]["device_id"] == row_id
    assert db.query(PushDevice).filter(PushDevice.user_id == u.id).count() == 1
    assert db.query(PushDevice).filter(PushDevice.id == row_id).one().device_id == "install-attached"


def test_push_register_jwt_ownership(client, db):
    owner = _user(db, "OwnerJwt")
    other = _user(db, "OtherJwt")
    r = client.post(
        "/notifications/push/register",
        headers=_auth(owner.id),
        json={
            "user_id": other.id,
            "platform": "android",
            "fcm_token": _tok(8),
            "device_id": "install-x",
        },
    )
    assert r.status_code == 403
    assert (
        db.query(PushDevice)
        .filter(PushDevice.user_id.in_([owner.id, other.id]))
        .count()
        == 0
    )
