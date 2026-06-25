from __future__ import annotations

from backend.app.models import User
from backend.app.main import app
from backend.app.core.security import create_access_token


def test_chat_accept_language_en_drives_response_language_for_commands(client, db, monkeypatch):
    """
    V1 policy: language is resolved from Accept-Language (primary) then user preference.
    This test uses a deterministic chat command (no GPT).
    """
    # IMPORTANT:
    # Use conftest-provided client/db so we NEVER touch production-like DB.
    u = User(name="John", secret_key="test", preferred_language="fa")
    db.add(u)
    db.commit()
    db.refresh(u)
    user_id = u.id
    access_token = create_access_token({"user_id": user_id})

    # Send a deterministic command that is handled before GPT:
    # timezone: <IANA>
    msg = {"user_id": user_id, "message": "timezone: Asia/Tehran"}
    r2 = client.post(
        "/interact/chat",
        json=msg,
        headers={
            "Accept-Language": "en",
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["language"] == "en"
