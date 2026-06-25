"""GPT/OpenAI failures on POST /interact/chat must return 502 gpt_failure (not HTTP 200 fallback)."""

from __future__ import annotations

from unittest.mock import patch

from backend.app.core.security import create_access_token
from backend.app.models import User


class APIError(Exception):
    """Simulated OpenAI provider error for tests."""


def test_chat_gpt_failure_returns_502_gpt_failure(client, db):
    user = User(name="GptFailUser", secret_key="test", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"user_id": user.id})

    with patch(
        "backend.app.core.conversation.prompts.client.responses.create",
        side_effect=APIError("OpenAI rate limit exceeded"),
    ):
        response = client.post(
            "/interact/chat",
            json={"user_id": user.id, "message": "Hello Sedi, how are you today?"},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept-Language": "en",
            },
        )

    assert response.status_code == 502
    body = response.json()
    assert body.get("error") == "gpt_failure"
    assert "detail" in body
    assert "rate limit" not in body["detail"].lower()
    assert "openai" not in body["detail"].lower()
    assert "sk-" not in body["detail"]
