"""
Release D Acceptance Suite

NOTE:
These acceptance tests are intended to be run on Linux server or CI
(not on Windows dev machines without Python).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models import Device, Medication, Notification, User, UserMedication
from backend.tests.test_db_config import get_test_database_url


# Notification.type values from production (notification_engine.py)
NOTIFICATION_TYPE_HEALTH_ALERT = "health_alert"
NOTIFICATION_TYPE_DEVICE_DISCONNECTED = "device_disconnected"

# Blocked DB URL substrings (case-insensitive)
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
    raise RuntimeError(
        "Refusing to run acceptance tests: ENV or APP_ENV indicates production."
    )
if _is_production_db_url(_test_db_url):
    raise RuntimeError(
        "Refusing to run acceptance tests against a production-like DB URL. "
        "Set TEST_DATABASE_URL to a safe test database (e.g. sedi_test)."
    )


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


class _SessionContext:
    """Context manager that provides the session but does NOT close it on exit.
    The scheduler uses 'with next(get_db()) as db:' which would call Session.close()
    and detach release_d_user. We avoid that by wrapping the session."""
    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args: object) -> None:
        # Do not close - session is managed by the test fixture
        pass


@pytest.fixture()
def patch_scheduler_db(monkeypatch: pytest.MonkeyPatch, db: Session) -> None:
    """
    Ensure scheduler jobs use the same test DB session as the test.
    Scheduler uses get_db() and 'with next(get_db()) as db:' which would close
    the session on exit and detach objects like release_d_user. We yield a
    wrapper that provides the session but does not close it.
    """
    import backend.app.core.scheduler as sched_mod

    def _get_db_override():
        yield _SessionContext(db)

    monkeypatch.setattr(sched_mod, "get_db", _get_db_override, raising=True)


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
    patch_scheduler_db: None,
) -> None:
    import backend.app.core.scheduler as sched_mod

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

    from backend.app.core.scheduler import run_device_disconnected_check

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
    patch_scheduler_db: None,
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

    from backend.app.core.scheduler import run_medication_reminders

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
