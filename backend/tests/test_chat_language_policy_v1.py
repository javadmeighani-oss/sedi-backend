from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app


def test_chat_accept_language_en_drives_response_language_for_commands(monkeypatch):
    """
    V1 policy: language is resolved from Accept-Language (primary) then user preference.
    This test uses a deterministic chat command (no GPT).
    """
    client = TestClient(app)

    # Create a user (use existing onboarding/register endpoint used in other tests)
    # We keep this minimal and follow the project's current interact contract.
    payload = {
        "name": "John",
        "phone": "+10000000000",
        "age": 30
    }
    r = client.post("/interact/register", json=payload, headers={"Accept-Language": "en"})
    assert r.status_code == 200
    user_id = r.json()["user_id"]

    # Send a deterministic command that is handled before GPT:
    # timezone: <IANA>
    msg = {"user_id": user_id, "message": "timezone: Asia/Tehran"}
    r2 = client.post("/interact", json=msg, headers={"Accept-Language": "en"})
    assert r2.status_code == 200
    data = r2.json()
    assert data["language"] == "en"
