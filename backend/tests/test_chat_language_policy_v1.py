from __future__ import annotations

import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import User
from backend.app.database import get_db

from backend.app.main import app


def test_chat_accept_language_en_drives_response_language_for_commands(monkeypatch):
    """
    V1 policy: language is resolved from Accept-Language (primary) then user preference.
    This test uses a deterministic chat command (no GPT).
    """
    # IMPORTANT:
    # Ensure this test NEVER hits production-like DB settings.
    # We override get_db() to use DATABASE_URL configured by tests/conftest.py.
    test_db_url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    assert test_db_url, "Tests must provide DATABASE_URL (or TEST_DATABASE_URL) for test DB"

    engine = create_engine(test_db_url)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)

    # IMPORTANT: Do not call /interact/onboarding in tests.
    # Onboarding may use a production-like DATABASE_URL in some environments.
    # Instead, create a user directly using the test DB session (same pattern as other tests).
    db_gen = override_get_db()
    db = next(db_gen)
    try:
        u = User(name="John", secret_key="test", preferred_language="fa")
        db.add(u)
        db.commit()
        db.refresh(u)
        user_id = u.id
    finally:
        db_gen.close()
        app.dependency_overrides.pop(get_db, None)

    # Send a deterministic command that is handled before GPT:
    # timezone: <IANA>
    msg = {"user_id": user_id, "message": "timezone: Asia/Tehran"}
    r2 = client.post("/interact/chat", json=msg, headers={"Accept-Language": "en"})
    assert r2.status_code == 200
    data = r2.json()
    assert data["language"] == "en"
