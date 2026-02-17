# tests/test_devices_c2.py
"""
Release C2: Device Identity v1 tests

- register -> ingest using returned token works
- revoke blocks ingest
- rotate changes token
- hybrid mode prefers DB token when valid and can fallback to legacy
"""

import os
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine, SessionLocal
from app.models import User, Device
from app.core.device_auth import hash_device_token


client = TestClient(app)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = next(SessionLocal())
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def user(db):
    u = User(name="Device Owner", secret_key="pw", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_register_and_ingest_with_db_token_hybrid(db, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)  # no legacy token

    # Register
    r = client.post(f"/devices/register?user_id={user.id}", json={"device_id": "Sedi001", "device_type": "heart_rate"})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    token = j["data"]["token"]
    assert isinstance(token, str) and len(token) >= 32

    # Ensure DB stores hash, not raw
    dev = db.query(Device).filter(Device.device_id == "Sedi001").first()
    assert dev is not None
    assert dev.token_hash == hash_device_token(token)
    assert dev.token_hash != token
    assert dev.status == "active"

    # Ingest with DB token
    ing = client.post(
        "/device/ingest",
        headers={"X-DEVICE-TOKEN": token},
        json={"user_id": user.id, "device_id": "Sedi001", "event_type": "heart_rate", "payload": {"bpm": 80}},
    )
    assert ing.status_code == 200
    j2 = ing.json()
    assert j2["ok"] is True
    assert j2["data"]["dedupe_key"].startswith(f"heart_rate:{user.id}:")


def test_revoke_blocks_ingest(db, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)

    r = client.post(f"/devices/register?user_id={user.id}", json={"device_id": "Sedi002", "device_type": "heart_rate"})
    token = r.json()["data"]["token"]

    rev = client.post(f"/devices/Sedi002/revoke?user_id={user.id}")
    assert rev.status_code == 200
    assert rev.json()["ok"] is True

    ing = client.post(
        "/device/ingest",
        headers={"X-DEVICE-TOKEN": token},
        json={"user_id": user.id, "device_id": "Sedi002", "event_type": "heart_rate", "payload": {"bpm": 81}},
    )
    assert ing.status_code == 401


def test_rotate_changes_token(db, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)

    r = client.post(f"/devices/register?user_id={user.id}", json={"device_id": "Sedi003", "device_type": "heart_rate"})
    token1 = r.json()["data"]["token"]

    rot = client.post(f"/devices/Sedi003/rotate-token?user_id={user.id}")
    assert rot.status_code == 200
    token2 = rot.json()["data"]["token"]
    assert token2 != token1

    # Old token should fail
    ing_old = client.post(
        "/device/ingest",
        headers={"X-DEVICE-TOKEN": token1},
        json={"user_id": user.id, "device_id": "Sedi003", "event_type": "heart_rate", "payload": {"bpm": 82}},
    )
    assert ing_old.status_code == 401

    # New token should work
    ing_new = client.post(
        "/device/ingest",
        headers={"X-DEVICE-TOKEN": token2},
        json={"user_id": user.id, "device_id": "Sedi003", "event_type": "heart_rate", "payload": {"bpm": 82}},
    )
    assert ing_new.status_code == 200
    assert ing_new.json()["ok"] is True


def test_hybrid_fallback_to_legacy_when_db_rejects(db, user, monkeypatch):
    monkeypatch.setenv("DEVICE_AUTH_MODE", "hybrid")
    monkeypatch.setenv("DEVICE_INGEST_TOKEN", "legacy-secret")

    # Register device (DB token exists)
    r = client.post(f"/devices/register?user_id={user.id}", json={"device_id": "Sedi004", "device_type": "heart_rate"})
    assert r.status_code == 200

    # Use legacy token (should still pass in hybrid fallback)
    ing = client.post(
        "/device/ingest",
        headers={"X-DEVICE-TOKEN": "legacy-secret"},
        json={"user_id": user.id, "device_id": "Sedi004", "event_type": "heart_rate", "payload": {"bpm": 83}},
    )
    assert ing.status_code == 200
    assert ing.json()["ok"] is True

