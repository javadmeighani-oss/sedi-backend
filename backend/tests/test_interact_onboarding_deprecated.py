"""Legacy onboarding deprecation (Gate 1)."""

from unittest.mock import patch


def test_onboarding_works_when_legacy_enabled(client):
    with patch(
        "backend.app.routers.interact._legacy_onboarding_enabled",
        return_value=True,
    ), patch(
        "backend.app.core.conversation.brain.ConversationBrain.get_initial_message",
        return_value="Hello!",
    ):
        r = client.post("/interact/onboarding", json={"name": "Legacy User"})
    assert r.status_code == 200


def test_onboarding_returns_410_when_disabled(client):
    with patch(
        "backend.app.routers.interact._legacy_onboarding_enabled",
        return_value=False,
    ):
        r = client.post("/interact/onboarding", json={"name": "Blocked"})
    assert r.status_code == 410
