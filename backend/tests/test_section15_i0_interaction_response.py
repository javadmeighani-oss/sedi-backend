"""Section 15-I0 — InteractionResponse schema regression for reminder clarification."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.app.models import User
from backend.app.schemas.chat import ChatRequest
from backend.app.schemas.interaction import InteractionResponse


@pytest.fixture
def mock_request():
    request = MagicMock()
    request.headers = {"Accept-Language": "en"}
    return request


@pytest.fixture
def user(db):
    u = User(name="I0 Reminder User", secret_key="i0", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={
        "created": False,
        "reason": "needs_clarification",
        "clarification_message": "legacy-must-not-surface",
    },
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_reminder_clarification_uses_message_not_reply(
    mock_cmd, mock_reminder, mock_process, db, user, mock_request
):
    """I3 clarification is returned on InteractionResponse.message (not reply)."""
    from backend.app.models import UserProfileCore
    from backend.app.routers.interact import chat
    import asyncio

    if db.query(UserProfileCore).filter(UserProfileCore.user_id == user.id).first() is None:
        db.add(UserProfileCore(user_id=user.id, timezone="UTC"))
        db.commit()

    payload = ChatRequest(message="remind me to call the doctor")
    resp = asyncio.run(chat(mock_request, payload, db, user))

    assert isinstance(resp, InteractionResponse)
    assert "date" in resp.message.lower() or "time" in resp.message.lower()
    assert "legacy-must-not-surface" not in resp.message
    assert not hasattr(resp, "reply") or getattr(resp, "reply", None) is None
    assert resp.user_id == user.id
    assert resp.language
    assert isinstance(resp.timestamp, datetime)
    mock_process.assert_not_called()
    mock_reminder.assert_not_called()


def test_interaction_response_rejects_reply_kwarg():
    """Guardrail: constructing with reply= must not silently succeed."""
    with pytest.raises((ValidationError, TypeError)):
        InteractionResponse(  # type: ignore[call-arg]
            reply="should fail",
            language="en",
            timestamp=datetime.utcnow(),
        )


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={
        "created": False,
        "reason": "needs_clarification",
        "clarification_message": "Need a time.",
    },
)
def test_reminder_clarification_still_requires_auth_dependency(
    mock_reminder, mock_process, db, user, mock_request
):
    """Unauthenticated clients never reach this path: chat requires get_current_user."""
    from backend.app.routers.interact import chat
    import asyncio
    from fastapi import HTTPException

    # Calling without a user object is not how FastAPI wires Depends; simulate mismatch.
    payload = ChatRequest(message="remind me later")
    # Chat expects a User from Depends; invoking with wrong user_id in body still
    # requires JWT identity — mismatch must remain 403.
    other = User(name="Other", secret_key="x", preferred_language="en")
    db.add(other)
    db.commit()
    db.refresh(other)

    payload_mismatch = ChatRequest(message="remind me later", user_id=other.id)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat(mock_request, payload_mismatch, db, user))
    assert exc.value.status_code == 403
    mock_process.assert_not_called()
