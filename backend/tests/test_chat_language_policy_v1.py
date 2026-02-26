from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.models import User
from backend.tests.conftest import TestingSessionLocal

from backend.app.main import app


def test_chat_accept_language_en_drives_response_language_for_commands(monkeypatch):
    """
    V1 policy: language is resolved from Accept-Language (primary) then user preference.
    This test uses a deterministic chat command (no GPT).
    """
    client = TestClient(app)

    # IMPORTANT: Do not call /interact/onboarding in tests.
    # Onboarding may use a production-like DATABASE_URL in some environments.
    # Instead, create a user directly using the test DB session (same pattern as other tests).
    db = TestingSessionLocal()
    try:
        u = User(name="John", secret_key="test", preferred_language="fa")
        db.add(u)
        db.commit()
        db.refresh(u)
        user_id = u.id
    finally:
        db.close()

    # Send a deterministic command that is handled before GPT:
    # timezone: <IANA>
    msg = {"user_id": user_id, "message": "timezone: Asia/Tehran"}
    r2 = client.post("/interact/chat", json=msg, headers={"Accept-Language": "en"})
    assert r2.status_code == 200
    data = r2.json()
    assert data["language"] == "en"
