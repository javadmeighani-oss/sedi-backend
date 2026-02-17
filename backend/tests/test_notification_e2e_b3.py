"""
Release B3: Minimal E2E Notification API test (deterministic)

Scenario:
1) Create a notification via DecisionEngine contract (no scheduler)
2) GET /notifications/unread returns it
3) POST /notifications/{id}/mark-read hides it from unread
4) POST /notifications/{id}/feedback accepts payload

Notes:
- No OpenAI calls: NOTIF_AI_ENHANCE defaults false.
- Contract language is validated indirectly by checking English fallback body.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine, SessionLocal
from app.models import User
from app.services.notification_engine import DecisionEngine


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
def user_en(db):
    u = User(name="E2E User", secret_key="e2e", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_notifications_e2e_unread_markread_feedback(db, user_en):
    engine = DecisionEngine(db)

    # 1) Create via contract method (language should resolve to en)
    created = engine.create_morning_brief(user_id=user_en.id, memory_context=None, scheduled_for=None)
    assert created is not None
    assert created.user_id == user_en.id
    assert created.type == "morning_brief"
    assert created.is_read is False
    assert created.body and len(created.body.strip()) > 0
    # English fallback signature
    assert "good morning" in created.body.lower()

    # 2) Unread returns it
    r1 = client.get("/notifications/unread", params={"user_id": user_en.id, "limit": 5})
    assert r1.status_code == 200
    j1 = r1.json()
    assert j1["ok"] is True
    ids = [n["id"] for n in j1["data"]["notifications"]]
    assert created.id in ids

    # 3) Mark read hides it
    r2 = client.post(f"/notifications/{created.id}/mark-read", params={"user_id": user_en.id})
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2["ok"] is True

    r3 = client.get("/notifications/unread", params={"user_id": user_en.id, "limit": 5})
    assert r3.status_code == 200
    j3 = r3.json()
    assert j3["ok"] is True
    ids2 = [n["id"] for n in j3["data"]["notifications"]]
    assert created.id not in ids2

    # 4) Feedback accepts payload
    r4 = client.post(
        f"/notifications/{created.id}/feedback",
        params={"user_id": user_en.id},
        json={"feedback": "neutral", "reason": "e2e", "action": "irrelevant"},
    )
    assert r4.status_code == 200
    j4 = r4.json()
    assert j4["ok"] is True

