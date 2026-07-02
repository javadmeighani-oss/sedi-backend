"""Gate 4C — InteractionEvent + notification-to-chat continuity tests."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.app.models import InteractionEvent, Notification, NotificationFeedback, User
from backend.app.schemas.chat import ChatRequest
from backend.app.services.gate4.interaction_event_service import (
    create_chat_message_event,
    create_interaction_event,
    create_notification_action_event,
    create_notification_open_chat_event,
)
from backend.app.services.gate4.notification_contract import SmartNotificationAction


@pytest.fixture
def auth_override():
    """Override JWT dependency to avoid SQLite cross-thread issues in async routes."""
    from backend.app.main import app as sedi_app
    from backend.app.routers.auth_otp import get_current_user

    def _set(user: User) -> None:
        sedi_app.dependency_overrides[get_current_user] = lambda: user

    yield _set
    sedi_app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_request():
    request = MagicMock()
    request.headers = {"Accept-Language": "en"}
    return request


async def _call_chat(mock_request, payload: ChatRequest, db, user: User):
    from backend.app.routers.interact import chat

    return await chat(mock_request, payload, db, user)


@pytest.fixture
def user_a(db):
    u = User(name="Gate4C User A", secret_key="g4c", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def user_b(db):
    u = User(name="Gate4C User B", secret_key="g4c2", preferred_language="fa")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def notification_for_a(db, user_a):
    n = Notification(
        user_id=user_a.id,
        type="companion",
        title="Hello",
        body="Check in",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def test_service_creates_interaction_event(db, user_a):
    row = create_interaction_event(
        db,
        user_id=user_a.id,
        event_type="system_event",
        source="system",
        metadata={"note": "test"},
    )
    db.commit()
    assert row.id is not None
    assert row.interaction_channel == "text"
    stored = db.query(InteractionEvent).filter(InteractionEvent.id == row.id).one()
    assert stored.event_type == "system_event"
    assert json.loads(stored.metadata_json)["note"] == "test"


def test_notification_action_creates_event(db, user_a, notification_for_a):
    row = create_notification_action_event(
        db,
        user_id=user_a.id,
        notification_id=notification_for_a.id,
        canonical_action=SmartNotificationAction.ACK_THANKS.value,
    )
    db.commit()
    assert row.event_type == "notification_ack"
    assert row.source_notification_id == notification_for_a.id
    meta = json.loads(row.metadata_json)
    assert meta["canonical_action_id"] == "ACK_THANKS"


def test_open_chat_action_creates_notification_open_chat_event(db, user_a, notification_for_a):
    row = create_notification_open_chat_event(
        db,
        user_id=user_a.id,
        notification_id=notification_for_a.id,
        conversation_id="conv-1",
    )
    db.commit()
    assert row.event_type == "notification_open_chat"
    assert row.conversation_id == "conv-1"


def test_legacy_open_chat_normalizes_to_open_chat_event(db, user_a, notification_for_a):
    row = create_notification_action_event(
        db,
        user_id=user_a.id,
        notification_id=notification_for_a.id,
        canonical_action="OPEN_CHAT",
        legacy_event_type="open",
    )
    db.commit()
    assert row.event_type == "notification_open_chat"


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_chat_old_payload_still_works(mock_cmd, mock_process, client, db, user_a, auth_override):
    auth_override(user_a)
    mock_process.return_value = {"message": "Hi there", "language": "en"}
    r = client.post(
        "/interact/chat",
        json={"message": "hello"},
        headers={"Accept-Language": "en"},
    )
    assert r.status_code == 200
    assert r.json()["message"] == "Hi there"
    assert db.query(InteractionEvent).filter(InteractionEvent.user_id == user_a.id).count() == 0


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_chat_accepts_source_notification_id(
    mock_cmd, mock_process, db, user_a, notification_for_a, mock_request
):
    mock_process.return_value = {"message": "Continuing", "language": "en"}
    payload = ChatRequest(
        message="let's talk",
        source_notification_id=notification_for_a.id,
        conversation_id="c-42",
        thread_id="t-7",
    )
    resp = asyncio.run(_call_chat(mock_request, payload, db, user_a))
    assert resp.message == "Continuing"
    assert resp.continued_from_notification is True
    assert resp.source_notification_id == notification_for_a.id
    assert resp.conversation_id == "c-42"
    assert mock_process.call_args.kwargs.get("notification_context") is not None
    evt = (
        db.query(InteractionEvent)
        .filter(
            InteractionEvent.user_id == user_a.id,
            InteractionEvent.event_type == "chat_message",
        )
        .one()
    )
    assert evt.source == "notification"
    assert evt.source_notification_id == notification_for_a.id
    assert evt.conversation_id == "c-42"
    assert evt.thread_id == "t-7"
    assert evt.interaction_channel == "text"
    meta = json.loads(evt.metadata_json)
    assert meta.get("continued_from_notification") is True
    assert meta.get("message_length") == len("let's talk")


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_chat_rejects_foreign_notification(
    mock_cmd, mock_process, db, user_a, user_b, notification_for_a, mock_request
):
    mock_process.return_value = {"message": "nope", "language": "en"}
    payload = ChatRequest(message="hi", source_notification_id=notification_for_a.id)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_call_chat(mock_request, payload, db, user_b))
    assert exc.value.status_code == 403


def test_chat_rejects_missing_notification(db, user_a, mock_request):
    payload = ChatRequest(message="hi", source_notification_id=999999)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_call_chat(mock_request, payload, db, user_a))
    assert exc.value.status_code == 404


def test_feedback_creates_interaction_event(db, user_a, notification_for_a):
    from backend.app.routers.notifications import submit_notification_feedback

    result = submit_notification_feedback(
        notification_id=notification_for_a.id,
        payload={"reaction": "like", "timestamp": datetime.utcnow().isoformat()},
        auth_user=user_a,
        user_id=None,
        db=db,
    )
    assert result.ok is True
    fb = db.query(NotificationFeedback).filter(
        NotificationFeedback.notification_id == notification_for_a.id
    ).one()
    assert fb.action == "like"
    evt = (
        db.query(InteractionEvent)
        .filter(InteractionEvent.source_notification_id == notification_for_a.id)
        .one()
    )
    assert evt.event_type == "notification_ack"


def test_feedback_open_chat_legacy_creates_open_chat_event(db, user_a, notification_for_a):
    from backend.app.routers.notifications import submit_notification_feedback

    submit_notification_feedback(
        notification_id=notification_for_a.id,
        payload={"reaction": "interact", "action_id": "open_chat"},
        auth_user=user_a,
        user_id=None,
        db=db,
    )
    evt = (
        db.query(InteractionEvent)
        .filter(InteractionEvent.source_notification_id == notification_for_a.id)
        .order_by(InteractionEvent.id.desc())
        .first()
    )
    assert evt.event_type == "notification_open_chat"


def test_chat_message_event_defaults_text_channel(db, user_a):
    row = create_chat_message_event(db, user_id=user_a.id)
    db.commit()
    assert row.interaction_channel == "text"
    assert row.source == "chat"


def test_conversation_and_thread_optional(db, user_a, notification_for_a):
    row = create_chat_message_event(
        db,
        user_id=user_a.id,
        source_notification_id=notification_for_a.id,
        conversation_id=None,
        thread_id=None,
    )
    db.commit()
    assert row.conversation_id is None
    assert row.thread_id is None


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_chat_rejects_unknown_fields(mock_cmd, mock_process, client, db, user_a, auth_override):
    auth_override(user_a)
    r = client.post(
        "/interact/chat",
        json={"message": "hello", "unexpected_field": 1},
        headers={"Accept-Language": "en"},
    )
    assert r.status_code == 422
    mock_process.assert_not_called()


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_brain_receives_no_notification_context_in_normal_chat(
    mock_cmd, mock_process, client, db, user_a, auth_override
):
    auth_override(user_a)
    mock_process.return_value = {"message": "Hi", "language": "en"}
    r = client.post(
        "/interact/chat",
        json={"message": "hello"},
        headers={"Accept-Language": "en"},
    )
    assert r.status_code == 200
    assert mock_process.call_args.kwargs.get("notification_context") is None


def test_chat_requires_jwt(client, db):
    u = User(name="Gate4C No JWT", secret_key="g4c-nojwt", preferred_language="en")
    db.add(u)
    db.commit()
    r = client.post(
        "/interact/chat",
        json={"message": "hello"},
        headers={"Accept-Language": "en"},
    )
    assert r.status_code == 401


def test_deliver_pending_requires_admin(client):
    r = client.post("/notifications/deliver_pending?limit=10")
    assert r.status_code in (401, 403)
