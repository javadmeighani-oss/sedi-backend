"""Regression: POST /interact/onboarding must not crash when resolving request language."""

from __future__ import annotations

from unittest.mock import patch


def test_onboarding_setup_returns_user_id_without_nameerror(client):
    """setup_onboarding uses FastAPI Request for language resolution."""
    with patch(
        "backend.app.core.conversation.brain.ConversationBrain.get_initial_message",
        return_value="Hello!",
    ):
        response = client.post(
            "/interact/onboarding",
            json={"name": "Pilot User"},
            headers={"Accept-Language": "en"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body.get("user_id")
    assert body["user_id"] > 0
    assert body.get("message")
    assert body.get("language") == "en"
