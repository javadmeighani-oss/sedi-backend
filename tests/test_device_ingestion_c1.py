# tests/test_device_ingestion_c1.py
"""
Device Ingestion Tests (Release C1)

Deterministic tests for device event ingestion:
- Token validation
- Event creation and deduplication
- Memory fact mapping
- Health alert triggers
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models import DeviceEvent, User, UserMemoryFact
from app.services.device_ingestion import ingest_event, build_dedupe_key
from app.services.memory.memory_repository import MemoryRepository


@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(app)


@pytest.fixture
def db():
    """Database session fixture"""
    from app.database import Base, engine, SessionLocal
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(db: Session):
    """Create test user"""
    user = User(
        id=999,
        name="Test User",
        secret_key="test_key",
        preferred_language="en"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    # Cleanup
    db.delete(user)
    db.commit()


@pytest.fixture
def device_token(monkeypatch):
    """Set device token for testing"""
    monkeypatch.setenv("DEVICE_INGEST_TOKEN", "test-device-token-123")
    return "test-device-token-123"


def test_build_dedupe_key():
    """Test dedupe key generation"""
    recorded_at = datetime(2026, 2, 2, 10, 33, 0)
    key = build_dedupe_key("heart_rate", 1, recorded_at)
    # Should round to 5-minute bucket: 10:30
    assert key == "heart_rate:1:2026-02-02T10:30"
    
    # Test with different minute (should round down)
    recorded_at2 = datetime(2026, 2, 2, 10, 37, 0)
    key2 = build_dedupe_key("heart_rate", 1, recorded_at2)
    assert key2 == "heart_rate:1:2026-02-02T10:35"


def test_ingest_event_creates_device_event(db: Session, test_user):
    """Test that ingest_event creates DeviceEvent"""
    event, dedupe_key = ingest_event(
        db=db_session,
        user_id=test_user.id,
        event_type="heart_rate",
        payload={"bpm": 82, "quality": "good"},
        device_id="Sedi001",
        recorded_at=datetime(2026, 2, 2, 10, 30, 0)
    )
    
    assert event is not None
    assert event.id is not None
    assert event.user_id == test_user.id
    assert event.event_type == "heart_rate"
    assert event.device_id == "Sedi001"
    assert event.dedupe_key == dedupe_key
    assert "bpm" in event.payload_json
    
    # Verify in DB
    db_event = db.query(DeviceEvent).filter(DeviceEvent.id == event.id).first()
    assert db_event is not None
    assert db_event.user_id == test_user.id


def test_ingest_event_deduplication(db: Session, test_user):
    """Test that duplicate events are prevented"""
    recorded_at = datetime(2026, 2, 2, 10, 33, 0)
    
    # First event
    event1, dedupe_key1 = ingest_event(
        db=db_session,
        user_id=test_user.id,
        event_type="heart_rate",
        payload={"bpm": 82},
        recorded_at=recorded_at
    )
    assert event1 is not None
    
    # Second event with same time bucket (should be duplicate)
    event2, dedupe_key2 = ingest_event(
        db=db_session,
        user_id=test_user.id,
        event_type="heart_rate",
        payload={"bpm": 85},
        recorded_at=datetime(2026, 2, 2, 10, 34, 0)  # Same 5-min bucket
    )
    assert event2 is None  # Duplicate
    assert dedupe_key1 == dedupe_key2
    
    # Verify only one event in DB
    count = db.query(DeviceEvent).filter(
        DeviceEvent.user_id == test_user.id,
        DeviceEvent.dedupe_key == dedupe_key1
    ).count()
    assert count == 1


def test_ingest_event_maps_to_memory_fact(db: Session, test_user):
    """Test that device event maps to UserMemoryFact with source='device'"""
    event, _ = ingest_event(
        db=db,
        user_id=test_user.id,
        event_type="heart_rate",
        payload={"bpm": 82, "quality": "good"},
        device_id="Sedi001"
    )
    
    assert event is not None
    
    # Check memory fact was created
    repo = MemoryRepository(db)
    fact = repo.get_fact(
        user_id=test_user.id,
        domain="vitals",
        key="heart_rate_bpm"
    )
    
    assert fact is not None
    assert fact.source == "device"
    assert fact.domain == "vitals"
    assert fact.key == "heart_rate_bpm"
    
    import json
    value = json.loads(fact.value_json)
    assert value["bpm"] == 82
    assert value.get("device_id") == "Sedi001"


def test_ingest_endpoint_requires_token(client, device_token):
    """Test that /device/ingest requires valid X-DEVICE-TOKEN"""
    # Request without token
    response = client.post(
        "/device/ingest",
        json={
            "user_id": 1,
            "event_type": "heart_rate",
            "payload": {"bpm": 82}
        }
    )
    assert response.status_code == 422  # Missing header
    
    # Request with invalid token
    response = client.post(
        "/device/ingest",
        json={
            "user_id": 1,
            "event_type": "heart_rate",
            "payload": {"bpm": 82}
        },
        headers={"X-DEVICE-TOKEN": "wrong-token"}
    )
    assert response.status_code == 401
    assert "Invalid device token" in response.json()["detail"]


def test_ingest_endpoint_success(client, db: Session, test_user, device_token):
    """Test successful ingestion via endpoint"""
    response = client.post(
        "/device/ingest",
        json={
            "user_id": test_user.id,
            "device_id": "Sedi001",
            "event_type": "heart_rate",
            "payload": {"bpm": 82, "quality": "good"},
            "recorded_at": "2026-02-02T10:30:00Z"
        },
        headers={"X-DEVICE-TOKEN": device_token}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "event_id" in data["data"]
    assert data["data"]["event_id"] is not None
    assert "dedupe_key" in data["data"]


def test_ingest_endpoint_duplicate(client, db: Session, test_user, device_token):
    """Test duplicate event handling via endpoint"""
    recorded_at = "2026-02-02T10:30:00Z"
    
    # First request
    response1 = client.post(
        "/device/ingest",
        json={
            "user_id": test_user.id,
            "event_type": "heart_rate",
            "payload": {"bpm": 82},
            "recorded_at": recorded_at
        },
        headers={"X-DEVICE-TOKEN": device_token}
    )
    assert response1.status_code == 200
    assert response1.json()["data"]["event_id"] is not None
    
    # Second request (duplicate)
    response2 = client.post(
        "/device/ingest",
        json={
            "user_id": test_user.id,
            "event_type": "heart_rate",
            "payload": {"bpm": 85},
            "recorded_at": recorded_at  # Same time bucket
        },
        headers={"X-DEVICE-TOKEN": device_token}
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["ok"] is True
    assert data2["data"]["event_id"] is None  # Duplicate
    assert "duplicate" in data2["data"].get("message", "").lower()


def test_ingest_endpoint_invalid_user(client, db: Session, device_token):
    """Test ingestion with non-existent user"""
    response = client.post(
        "/device/ingest",
        json={
            "user_id": 99999,
            "event_type": "heart_rate",
            "payload": {"bpm": 82}
        },
        headers={"X-DEVICE-TOKEN": device_token}
    )
    
    assert response.status_code == 200  # Endpoint returns 200 with error in body
    data = response.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "USER_NOT_FOUND"


def test_ingest_endpoint_empty_payload(client, db: Session, test_user, device_token):
    """Test ingestion with empty payload"""
    response = client.post(
        "/device/ingest",
        json={
            "user_id": test_user.id,
            "event_type": "heart_rate",
            "payload": {}
        },
        headers={"X-DEVICE-TOKEN": device_token}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "INVALID_PAYLOAD"


def test_ingest_endpoint_unsupported_event_type(client, db: Session, test_user, device_token):
    """Test ingestion with unsupported event type"""
    response = client.post(
        "/device/ingest",
        json={
            "user_id": test_user.id,
            "event_type": "unsupported_type",
            "payload": {"value": 123}
        },
        headers={"X-DEVICE-TOKEN": device_token}
    )
    
    # Should fail validation at Pydantic level or service level
    # Depending on implementation, might be 422 or 200 with error
    assert response.status_code in [200, 422]
    if response.status_code == 200:
        data = response.json()
        assert data["ok"] is False
