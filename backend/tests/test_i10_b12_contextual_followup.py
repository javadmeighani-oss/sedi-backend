"""I10-B12 contextual follow-up — CareFollowUpTask, canonical I10, real PostgreSQL."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.database import get_db as _app_get_db
from backend.app.main import app as sedi_app
from backend.app.schemas.chat import ChatRequest
from backend.app.services.i10.contextual_followup_i10_adapter import (
    build_followup_occurrence_key,
    render_followup_copy,
)
from backend.app.services.i10.contextual_followup_types import FollowUpTaskSource, FollowUpTaskStatus
from backend.app.services.i10.contextual_followup_worker import (
    create_post_event_follow_up_task,
    create_structured_follow_up_task,
    is_task_eligible,
    process_due_follow_up_tasks,
    process_single_follow_up_task,
)
from backend.app.services.i10.policy_types import I10PrivacyClass, I10SemanticFamily
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.app.services.intelligence.contracts import IntentId
from backend.app.services.intelligence.intent_registry import resolve_intent
from backend.app.services.section10 import feature_flags as s10_flags

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG_PATCH = patch(
    "backend.app.services.section10.feature_flags.contextual_followup_enabled",
    return_value=True,
)


@pytest.fixture
def gate4_patch():
    with _GATE4_PATCH:
        yield


@pytest.fixture
def flag_patch():
    with _FLAG_PATCH:
        yield


@pytest.fixture()
def client(db):
    def _get_db_override():
        yield db

    sedi_app.dependency_overrides[_app_get_db] = _get_db_override
    try:
        with TestClient(sedi_app) as c:
            yield c
    finally:
        sedi_app.dependency_overrides.pop(_app_get_db, None)


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}


def _user(db, name: str = "follow-user") -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    ensure_self_subject_for_account(db, row.id, commit=True)
    return row


def _now() -> datetime:
    return datetime(2026, 8, 31, 14, 0, 0)


def _task(
    db,
    user: models.User,
    *,
    due_at: datetime,
    source: FollowUpTaskSource = FollowUpTaskSource.GENERAL_CONTEXTUAL,
    status: str = FollowUpTaskStatus.OPEN.value,
    title: str = "Continue topic",
) -> models.CareFollowUpTask:
    return create_structured_follow_up_task(
        db,
        user_id=user.id,
        title=title,
        due_at=due_at,
        source=source,
        follow_up_kind=source.value,
    )


# --- Audit constants ---


def test_followup_model_fields_exist():
    cols = {c.name for c in models.CareFollowUpTask.__table__.columns}
    assert {"id", "user_id", "title", "status", "due_at", "source"}.issubset(cols)
    assert "expires_at" not in cols


# --- A. Future task ---


def test_future_task_not_eligible(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    task = _task(db, user, due_at=when + timedelta(hours=2))
    assert is_task_eligible(task, when) is False
    assert process_due_follow_up_tasks(db, now=when) == 0
    assert db.query(models.Notification).count() == 0
    assert task.status == FollowUpTaskStatus.OPEN.value


# --- B. Due task ---


def test_due_task_produces_i10_notification(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    task = _task(db, user, due_at=when - timedelta(minutes=5))
    db.commit()
    assert process_due_follow_up_tasks(db, now=when) == 1
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    assert notif.i10_policy_decision_id is not None
    assert notif.user_id == user.id
    assert notif.source_type == "care_follow_up_task"
    assert notif.source_id == str(task.id)
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == notif.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP.value


# --- C. Idempotency ---


def test_same_task_duplicate_blocked(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    _task(db, user, due_at=when - timedelta(minutes=1))
    db.commit()
    assert process_due_follow_up_tasks(db, now=when) == 1
    assert process_due_follow_up_tasks(db, now=when) == 0
    assert db.query(func.count(models.Notification.id)).scalar() == 1


# --- D. New task ---


def test_new_followup_task_allowed(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    _task(db, user, due_at=when - timedelta(minutes=1), title="First")
    _task(db, user, due_at=when - timedelta(minutes=1), title="Second")
    db.commit()
    assert process_due_follow_up_tasks(db, now=when) == 2
    assert db.query(func.count(models.Notification.id)).filter(
        models.Notification.user_id == user.id
    ).scalar() == 2


# --- E. Terminal tasks ---


def test_completed_task_suppressed(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    task = _task(db, user, due_at=when - timedelta(minutes=1))
    task.status = FollowUpTaskStatus.DONE.value
    db.commit()
    assert process_due_follow_up_tasks(db, now=when) == 0


def test_cancelled_task_suppressed(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    task = _task(db, user, due_at=when - timedelta(minutes=1))
    task.status = FollowUpTaskStatus.CANCELLED.value
    db.commit()
    assert process_due_follow_up_tasks(db, now=when) == 0


def test_notified_task_suppressed(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    task = _task(db, user, due_at=when - timedelta(minutes=1))
    task.status = FollowUpTaskStatus.NOTIFIED.value
    db.commit()
    assert process_due_follow_up_tasks(db, now=when) == 0


# --- F. Post-event truthfulness ---


def test_post_event_followup_asks_does_not_assert_attendance(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    event = models.UserEvent(
        user_id=user.id,
        title="Dr Visit",
        event_type="doctor_visit",
        event_domain="medical",
        starts_at=when - timedelta(hours=3),
        ends_at=when - timedelta(hours=2),
        timezone="UTC",
        status="scheduled",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    task = create_post_event_follow_up_task(
        db, user_id=user.id, event=event, due_at=when, source_notification_id=None
    )
    assert task is not None
    db.commit()
    assert process_due_follow_up_tasks(db, now=when) == 1
    notif = db.query(models.Notification).one()
    body = (notif.body or "").lower()
    assert "how did your appointment go" in body
    for term in ("completed", "attended", "missed", "went well"):
        assert term not in body
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.notification_id == notif.id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.POST_EVENT_FOLLOW_UP.value


def test_post_event_eligible_without_attendance_authority(db):
    user = _user(db)
    when = _now()
    event = models.UserEvent(
        user_id=user.id,
        title="Lab",
        event_type="lab_test",
        event_domain="medical",
        starts_at=when - timedelta(hours=1),
        ends_at=when - timedelta(minutes=30),
        timezone="UTC",
        status="scheduled",
    )
    db.add(event)
    db.commit()
    task = create_post_event_follow_up_task(db, user_id=user.id, event=event, due_at=when)
    assert task is not None
    assert task.source == FollowUpTaskSource.POST_EVENT.value


# --- G. Chat continuation real API ---


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_real_chat_continuation_via_interact_api(
    mock_cmd, mock_reminder, mock_brain, client, db, flag_patch, gate4_patch, monkeypatch
):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    mock_brain.return_value = {"message": "Glad to continue.", "language": "en"}
    user = _user(db, "Javad")
    when = _now()
    _task(db, user, due_at=when - timedelta(minutes=1), title="Feeling tired")
    db.commit()
    assert process_due_follow_up_tasks(db, now=when) == 1
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()

    from backend.app.routers.interact import chat

    payload = ChatRequest(
        message="let's continue",
        source_notification_id=notif.id,
        conversation_id="b12-conv",
        interaction_source="notification",
    )
    from backend.app.models import InteractionEvent

    async def _run():
        from starlette.requests import Request
        scope = {"type": "http", "headers": [], "method": "POST", "path": "/interact/chat"}
        request = Request(scope)
        return await chat(request, payload, db, user)

    resp = asyncio.run(_run())
    assert resp.continued_from_notification is True
    assert resp.source_notification_id == notif.id
    nctx = mock_brain.call_args.kwargs.get("notification_context") or {}
    assert "body" not in nctx
    events = db.query(InteractionEvent).filter(
        InteractionEvent.user_id == user.id,
        InteractionEvent.source_notification_id == notif.id,
    ).all()
    assert len(events) == 1


def test_safe_notification_context_reconstruction(db, flag_patch, gate4_patch):
    from backend.app.services.gate4.notification_chat_context import build_safe_chat_context

    user = _user(db)
    when = _now()
    _task(db, user, due_at=when - timedelta(minutes=1))
    db.commit()
    process_due_follow_up_tasks(db, now=when)
    notif = db.query(models.Notification).one()
    ctx = build_safe_chat_context(notif)
    assert ctx["category"] == "care_follow_up"
    assert "follow_up_task" in str(notif.source_id)
    assert "SECRET TRANSCRIPT" not in str(ctx)


# --- H. Authorization ---


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_cross_user_source_notification_denied(
    mock_cmd, mock_reminder, mock_brain, db, flag_patch, gate4_patch, monkeypatch
):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    owner = _user(db, "owner")
    other = _user(db, "other")
    when = _now()
    _task(db, owner, due_at=when - timedelta(minutes=1))
    db.commit()
    process_due_follow_up_tasks(db, now=when)
    notif = db.query(models.Notification).filter(models.Notification.user_id == owner.id).one()

    from backend.app.routers.interact import chat
    from starlette.requests import Request

    payload = ChatRequest(message="hi", source_notification_id=notif.id)
    scope = {"type": "http", "headers": [], "method": "POST", "path": "/interact/chat"}
    request = Request(scope)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat(request, payload, db, other))
    assert exc.value.status_code == 403


# --- I. Transaction failure ---


def test_enqueue_failure_does_not_mark_notified(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    task = _task(db, user, due_at=when - timedelta(minutes=1))
    db.commit()
    from backend.app.services.i10.policy_types import I10DecisionValue
    from backend.app.services.i10.intake import I10IntakeResult

    with patch(
        "backend.app.services.i10.contextual_followup_i10_adapter.enqueue_i10_notification",
        return_value=I10IntakeResult(
            decision=I10DecisionValue.SUPPRESS,
            reason_code="TEST_FAIL",
            decision_id=None,
            notification_id=None,
            recipient_kind=None,
        ),
    ):
        assert process_single_follow_up_task(db, task, now=when) is False
    db.refresh(task)
    assert task.status == FollowUpTaskStatus.OPEN.value
    assert db.query(models.Notification).count() == 0


def test_retry_after_failure_no_duplicate_state(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    task = _task(db, user, due_at=when - timedelta(minutes=1))
    db.commit()
    from backend.app.services.i10.policy_types import I10DecisionValue
    from backend.app.services.i10.intake import I10IntakeResult

    with patch(
        "backend.app.services.i10.contextual_followup_i10_adapter.enqueue_i10_notification",
        return_value=I10IntakeResult(
            decision=I10DecisionValue.SUPPRESS,
            reason_code="TEST_FAIL",
            decision_id=None,
            notification_id=None,
            recipient_kind=None,
        ),
    ):
        process_single_follow_up_task(db, task, now=when)
    db.commit()
    assert process_due_follow_up_tasks(db, now=when) == 1
    assert db.query(func.count(models.Notification.id)).scalar() == 1


# --- Additional coverage ---


def test_no_raw_chat_in_worker_module():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "contextual_followup_worker.py"
    text = root.read_text(encoding="utf-8")
    for term in ("ConversationMemory", "get_recent_messages", "transcript", "UserMemory"):
        assert term not in text


def test_no_direct_rag_in_b12_modules():
    for name in (
        "contextual_followup_worker.py",
        "contextual_followup_i10_adapter.py",
    ):
        root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / name
        text = root.read_text(encoding="utf-8")
        for term in ("rag_service", "RAGService", "retrieve_augmented"):
            assert term not in text


def test_no_direct_notification_orm_write():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "contextual_followup_i10_adapter.py"
    text = root.read_text(encoding="utf-8")
    assert "models.Notification(" not in text


def test_no_direct_fcm():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "contextual_followup_i10_adapter.py"
    text = root.read_text(encoding="utf-8").lower()
    assert "fcm" not in text


def test_profile_name_optional_in_copy(db):
    user = models.User(secret_key="sk-noname", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    task = _task(db, user, due_at=_now())
    _title, body, _ = render_followup_copy(db, task)
    assert body.startswith("you asked")


def test_profile_name_used_when_available(db):
    user = _user(db, name="Javad")
    task = _task(db, user, due_at=_now())
    _title, body, _ = render_followup_copy(db, task)
    assert body.startswith("Javad,")


def test_privacy_general_private(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    _task(db, user, due_at=when - timedelta(minutes=1), source=FollowUpTaskSource.GENERAL_CONTEXTUAL)
    db.commit()
    process_due_follow_up_tasks(db, now=when)
    notif = db.query(models.Notification).one()
    assert notif.privacy_class == I10PrivacyClass.PRIVATE.value


def test_privacy_post_event_health_sensitive(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    event = models.UserEvent(
        user_id=user.id,
        title="Visit",
        event_type="doctor_visit",
        event_domain="medical",
        starts_at=when - timedelta(hours=2),
        ends_at=when - timedelta(hours=1),
        timezone="UTC",
        status="scheduled",
    )
    db.add(event)
    db.commit()
    create_post_event_follow_up_task(db, user_id=user.id, event=event, due_at=when)
    db.commit()
    process_due_follow_up_tasks(db, now=when)
    notif = db.query(models.Notification).one()
    assert notif.privacy_class == I10PrivacyClass.HEALTH_SENSITIVE.value


def test_followup_source_preserved(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    task = _task(db, user, due_at=when - timedelta(minutes=1), source=FollowUpTaskSource.GENERAL_CONTEXTUAL)
    db.commit()
    process_due_follow_up_tasks(db, now=when)
    notif = db.query(models.Notification).one()
    assert notif.source_type == "care_follow_up_task"
    assert notif.source_id == str(task.id)


def test_occurrence_key_not_forever_dedupe():
    assert build_followup_occurrence_key(task_id=1) != build_followup_occurrence_key(task_id=2)


def test_notification_follow_up_intent_compatible():
    intent = resolve_intent(
        message="let's talk",
        language="en",
        has_verified_notification_origin=True,
    )
    assert intent.intent_id is IntentId.NOTIFICATION_FOLLOW_UP


def test_feature_flag_default_off(monkeypatch):
    monkeypatch.delenv("SEDI_I10_CONTEXTUAL_FOLLOWUP_ENABLED", raising=False)
    assert s10_flags.contextual_followup_enabled() is False


def test_worker_inactive_when_flag_off(db, gate4_patch, monkeypatch):
    monkeypatch.delenv("SEDI_I10_CONTEXTUAL_FOLLOWUP_ENABLED", raising=False)
    user = _user(db)
    when = _now()
    _task(db, user, due_at=when - timedelta(minutes=1))
    db.commit()
    assert process_due_follow_up_tasks(db, now=when) == 0


def test_task_marked_notified_after_success(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    task = _task(db, user, due_at=when - timedelta(minutes=1))
    db.commit()
    process_due_follow_up_tasks(db, now=when)
    db.refresh(task)
    assert task.status == FollowUpTaskStatus.NOTIFIED.value


def test_self_health_subject_attribution(db, flag_patch, gate4_patch):
    user = _user(db)
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    when = _now()
    _task(db, user, due_at=when - timedelta(minutes=1))
    db.commit()
    process_due_follow_up_tasks(db, now=when)
    notif = db.query(models.Notification).one()
    assert notif.health_subject_id == subject.id


def test_no_raw_measurement_values_in_body(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _now()
    _task(db, user, due_at=when - timedelta(minutes=1), title="Heart rate topic")
    db.commit()
    process_due_follow_up_tasks(db, now=when)
    notif = db.query(models.Notification).one()
    assert "bpm" not in (notif.body or "").lower()


def test_safe_notification_context_adapter_bounded(db, flag_patch, gate4_patch):
    from backend.app.services.intelligence.adapters import SafeNotificationContextAdapter

    user = _user(db)
    when = _now()
    _task(db, user, due_at=when - timedelta(minutes=1))
    db.commit()
    process_due_follow_up_tasks(db, now=when)
    notif = db.query(models.Notification).one()
    from backend.app.services.gate4.notification_chat_context import build_safe_chat_context

    ctx = build_safe_chat_context(notif)
    items = SafeNotificationContextAdapter().load(
        authenticated_user_id=user.id,
        notification_context=ctx,
        source_notification_id=notif.id,
    )
    blob = " ".join(i.display_text for i in items)
    assert str(notif.id) in blob
    assert "RAW" not in blob
