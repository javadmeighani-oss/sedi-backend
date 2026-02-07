"""
Release D Acceptance Suite

NOTE:
These acceptance tests are intended to be run on Linux server or CI
(not on Windows dev machines without Python).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Use running app package (app = backend/app when run from backend); avoid backend.app.* (mixed layout)
_backend_dir = Path(__file__).resolve().parents[2]
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from app.database import Base, DATABASE_URL, SessionLocal, engine
from app.main import app
from app.models import Device, Medication, Notification, User, UserMedication


# Notification.type values from production (notification_engine.py)
NOTIFICATION_TYPE_HEALTH_ALERT = "health_alert"
NOTIFICATION_TYPE_DEVICE_DISCONNECTED = "device_disconnected"

# Blocked DATABASE_URL substrings (case-insensitive). Avoid broad terms to reduce false positives.
_BLOCKED_DB_SUBSTRINGS = (
    "91.107.168.130",   # known production host/IP
    "sedi_prod",        # exact production DB name if used
    "production",       # URL path/host containing "production"
)


def _is_production_db_url(url: str) -> bool:
    u = (url or "").lower()
    return any(blocked in u for blocked in _BLOCKED_DB_SUBSTRINGS)


def _env_indicates_production() -> bool:
    env = (os.environ.get("ENV") or "").lower()
    app_env = (os.environ.get("APP_ENV") or "").lower()
    return env == "production" or app_env == "production"


if _env_indicates_production():
    raise RuntimeError(
        "Refusing to run acceptance tests: ENV or APP_ENV indicates production."
    )
if _is_production_db_url(DATABASE_URL or ""):
    raise RuntimeError(
        "Refusing to run acceptance tests against a production-like DATABASE_URL. "
        "Point DATABASE_URL to a safe test database before running."
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def db() -> Session:
    # Force fresh schema (avoids stale table missing e.g. sent_at)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def release_d_user(db: Session) -> User:
    user = db.query(User).filter(User.id == 1).first()
    if user is None:
        user = User(
            id=1,
            name="Release D User",
            secret_key="release-d-secret",
            preferred_language="en",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture
def device_auth_legacy(monkeypatch) -> str:
    # Auth reads DEVICE_AUTH_MODE / DEVICE_INGEST_TOKEN at request time (device_auth._get_*), so setenv is sufficient.
    monkeypatch.setenv("DEVICE_AUTH_MODE", "legacy_only")
    monkeypatch.setenv("DEVICE_INGEST_TOKEN", "release-d-ingest-token")
    return "release-d-ingest-token"


# /device/ingest expects header X-DEVICE-TOKEN (FastAPI Header alias in device_auth.get_device_token).
def _device_ingest_headers(token: str) -> dict:
    return {"X-DEVICE-TOKEN": token}


def test_release_d_abnormal_hr_creates_health_alert(
    client: TestClient,
    db: Session,
    release_d_user: User,
    device_auth_legacy: str,
) -> None:
    response = client.post(
        "/device/ingest",
        json={
            "user_id": release_d_user.id,
            "device_id": "Sedi001",
            "event_type": "heart_rate",
            "payload": {"bpm": 180},
            "recorded_at": "2026-02-06T12:00:00Z",
        },
        headers=_device_ingest_headers(device_auth_legacy),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("ok") is True
    assert "data" in data

    db.expire_all()
    # Query only columns that exist (avoid sent_at if table schema is stale)
    rows = (
        db.query(
            Notification.id,
            Notification.user_id,
            Notification.type,
            Notification.body,
            Notification.priority,
        )
        .filter(
            Notification.user_id == release_d_user.id,
            Notification.type == NOTIFICATION_TYPE_HEALTH_ALERT,
        )
        .all()
    )
    assert len(rows) >= 1
    row = rows[0]
    assert row.body and len(row.body.strip()) > 0
    assert row.priority in ("high", "critical")


def test_release_d_device_disconnected_creates_notification(
    db: Session,
    release_d_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.scheduler as sched_mod

    monkeypatch.setenv("DEVICE_DISCONNECTED_THRESHOLD_MIN", "15")
    sched_mod.DEVICE_DISCONNECTED_THRESHOLD_MIN = 15

    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=16)

    device = Device(
        user_id=release_d_user.id,
        device_id="SediDisconnected001",
        device_type="heart_rate",
        status="active",
        token_hash="acceptance-test-placeholder",
        last_seen_at=cutoff,
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    from app.core.scheduler import run_device_disconnected_check

    run_device_disconnected_check()

    db.expire_all()
    # Query only columns that exist (avoid sent_at if table schema is stale)
    rows = (
        db.query(
            Notification.id,
            Notification.user_id,
            Notification.type,
            Notification.body,
            Notification.dedupe_key,
        )
        .filter(
            Notification.user_id == release_d_user.id,
            Notification.type == NOTIFICATION_TYPE_DEVICE_DISCONNECTED,
        )
        .all()
    )
    assert len(rows) >= 1
    row = rows[0]
    assert "device_disconnected" in (row.dedupe_key or "")


def test_release_d_medication_reminder_creates_notification(
    db: Session,
    release_d_user: User,
) -> None:
    med = Medication(
        name="TestMed ReleaseD",
        generic_name="TestGeneric",
        default_dosage="10mg",
    )
    db.add(med)
    db.commit()
    db.refresh(med)

    um = UserMedication(
        user_id=release_d_user.id,
        medication_id=med.id,
        interval_hours=8,
    )
    db.add(um)
    db.commit()

    from app.core.scheduler import run_medication_reminders

    run_medication_reminders()

    db.expire_all()
    # Query only columns that exist (avoid sent_at if table schema is stale)
    rows = (
        db.query(
            Notification.id,
            Notification.user_id,
            Notification.type,
            Notification.body,
        )
        .filter(
            Notification.user_id == release_d_user.id,
            Notification.type == NOTIFICATION_TYPE_HEALTH_ALERT,
        )
        .all()
    )
    medication_name = "TestMed ReleaseD"
    reminder_rows = [r for r in rows if r.body and medication_name in r.body]
    assert len(reminder_rows) >= 1, (
        f"Expected at least one health_alert with body containing {medication_name!r}"
    )
    row = reminder_rows[0]
    assert row.body
    assert medication_name in row.body
