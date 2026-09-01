"""I10-B13 I8 plan coaching — lifestyle/nutrition/exercise via canonical I10 (PostgreSQL)."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import pytz
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.database import get_db as _app_get_db
from backend.app.main import app as sedi_app
from backend.app.schemas.chat import ChatRequest
from backend.app.services.i10.coaching_followup_types import resolve_coaching_domain
from backend.app.services.i10.coaching_i10_adapter import build_coaching_occurrence_key, render_coaching_copy
from backend.app.services.i10.coaching_worker import (
    is_action_eligible,
    list_eligible_coaching_actions,
    process_i8_coaching_followups,
    process_single_coaching_action,
)
from backend.app.services.i10.policy_types import I10PrivacyClass, I10SemanticFamily
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.repository import I8OperationalRepository
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
    "backend.app.services.i10.coaching_worker.coaching_followup_enabled",
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


def _user(db, name: str = "coach-user") -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    ensure_self_subject_for_account(db, row.id, commit=True)
    return row


def _profile_tz(db, user_id: int, tz: str = "UTC") -> None:
    existing = db.query(models.UserProfileCore).filter(models.UserProfileCore.user_id == user_id).first()
    if existing:
        return
    row = models.UserProfileCore(user_id=user_id, timezone=tz)
    db.add(row)
    db.flush()


def _when() -> datetime:
    return datetime(2026, 8, 31, 14, 0, 0, tzinfo=timezone.utc)


def _plan_action(
    db,
    user: models.User,
    *,
    domain: str,
    summary: str,
    when: datetime | None = None,
    action_key: str = "act-1",
) -> tuple[models.I8OperationalPlan, models.I8OperationalPlanAction]:
    when = when or _when()
    _profile_tz(db, user.id)
    window = resolve_local_day_window(db, user.id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.create_plan(
        db,
        user_id=user.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key=f"plan-{user.id}-{action_key}",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    action = repo.create_action(
        db,
        user_id=user.id,
        plan_id=plan.id,
        action_domain=domain,
        action_type=f"{domain}_item",
        action_idempotency_key=action_key,
        summary_text=summary,
        presentation_json="{}",
        knowledge_refs_json="[]",
        safety_state="SAFE",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    db.commit()
    return plan, action


# --- LIFESTYLE ---


def test_lifestyle_eligible_produces_i10(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _plan_action(db, user, domain="routine", summary="Hydration break", when=when)
    assert process_i8_coaching_followups(db, now=when, force=True) == 1
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == notif.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.LIFESTYLE_ROUTINE_COACHING.value
    action = db.query(models.I8OperationalPlanAction).one()
    assert action.status == "ACTIVE"


# --- NUTRITION ---


def test_nutrition_plan_follow_up_real_path(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _plan_action(db, user, domain="nutrition", summary="Lunch portion", when=when)
    assert process_i8_coaching_followups(db, now=when, force=True) == 1
    notif = db.query(models.Notification).one()
    assert "registered in today's plan" in (notif.body or "")
    assert "skipped" not in (notif.body or "").lower()
    decision = db.query(models.I10NotificationDecision).one()
    assert decision.semantic_family == I10SemanticFamily.NUTRITION_PLAN_FOLLOW_UP.value


def test_no_persisted_plan_no_notification(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    assert process_i8_coaching_followups(db, now=when, force=True) == 0


# --- EXERCISE ---


def test_exercise_plan_follow_up_real_path(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _plan_action(db, user, domain="exercise", summary="Morning walk", when=when)
    assert process_i8_coaching_followups(db, now=when, force=True) == 1
    decision = db.query(models.I10NotificationDecision).one()
    assert decision.semantic_family == I10SemanticFamily.EXERCISE_PLAN_FOLLOW_UP.value


def test_cross_domain_not_treated_as_exercise_plan(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _plan_action(db, user, domain="cross_domain", summary="Generic hint", when=when)
    assert resolve_coaching_domain("cross_domain") is None
    assert process_i8_coaching_followups(db, now=when, force=True) == 0


# --- Idempotency ---


def test_same_occurrence_duplicate_blocked(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _plan_action(db, user, domain="routine", summary="Stretch", when=when)
    assert process_i8_coaching_followups(db, now=when, force=True) == 1
    assert process_i8_coaching_followups(db, now=when, force=True) == 0
    assert db.query(func.count(models.Notification.id)).scalar() == 1


def test_different_plan_item_allowed(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _profile_tz(db, user.id)
    window = resolve_local_day_window(db, user.id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.create_plan(
        db,
        user_id=user.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key="multi-meal-plan",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    for key, summary in (("a1", "Breakfast"), ("a2", "Dinner")):
        repo.create_action(
            db,
            user_id=user.id,
            plan_id=plan.id,
            action_domain="nutrition",
            action_type="meal",
            action_idempotency_key=key,
            summary_text=summary,
            presentation_json="{}",
            knowledge_refs_json="[]",
            safety_state="SAFE",
            valid_from=window.valid_from,
            valid_until=window.valid_until,
            expires_at=window.expires_at,
        )
    db.commit()
    assert process_i8_coaching_followups(db, now=when, force=True) == 2


def test_occurrence_key_not_forever_dedupe():
    assert build_coaching_occurrence_key(action_id=1, valid_from_iso="2026-08-31T00:00:00+00:00") != build_coaching_occurrence_key(
        action_id=2, valid_from_iso="2026-08-31T00:00:00+00:00"
    )


# --- Future / terminal ---


def test_future_valid_from_not_eligible(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _profile_tz(db, user.id)
    window = resolve_local_day_window(db, user.id, now_utc=when)
    future_from = when + timedelta(hours=6)
    repo = I8OperationalRepository()
    plan = repo.create_plan(
        db,
        user_id=user.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key="future-plan",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    action = repo.create_action(
        db,
        user_id=user.id,
        plan_id=plan.id,
        action_domain="routine",
        action_type="routine_item",
        action_idempotency_key="future-act",
        summary_text="Later task",
        presentation_json="{}",
        knowledge_refs_json="[]",
        safety_state="SAFE",
        valid_from=future_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    db.commit()
    assert is_action_eligible(action, plan, now=when) is False
    assert process_i8_coaching_followups(db, now=when, force=True) == 0


def test_completed_action_suppressed(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _, action = _plan_action(db, user, domain="exercise", summary="Run", when=when)
    action.status = "COMPLETED"
    db.commit()
    assert process_i8_coaching_followups(db, now=when, force=True) == 0


# --- Truthfulness ---


def test_no_response_not_not_done_in_copy(db):
    user = _user(db, "Sam")
    when = _when()
    _profile_tz(db, user.id)
    window = resolve_local_day_window(db, user.id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.create_plan(
        db,
        user_id=user.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key="p1",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    action = repo.create_action(
        db,
        user_id=user.id,
        plan_id=plan.id,
        action_domain="nutrition",
        action_type="meal",
        action_idempotency_key="m1",
        summary_text="Snack",
        presentation_json="{}",
        knowledge_refs_json="[]",
        safety_state="SAFE",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    db.commit()
    from backend.app.services.i10.coaching_followup_types import CoachingPlanDomain

    _t, body, _ = render_coaching_copy(db, action, domain=CoachingPlanDomain.NUTRITION)
    assert "failed" not in body.lower()
    assert "not done" not in body.lower()
    assert "Was it completed?" in body


def test_action_status_unchanged_after_notify(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _, action = _plan_action(db, user, domain="routine", summary="Walk", when=when)
    process_i8_coaching_followups(db, now=when, force=True)
    db.refresh(action)
    assert action.status == "ACTIVE"


# --- I6 preferences ---


def test_i6_preference_disabled_suppresses(db, flag_patch, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_POLICY_ENFORCE", "true")
    user = _user(db)
    when = _when()
    _plan_action(db, user, domain="routine", summary="Meditation", when=when)
    db.add(
        models.NotificationPrefs(
            user_id=user.id,
            companion_enabled=False,
            health_alert_enabled=True,
        )
    )
    db.commit()
    assert process_i8_coaching_followups(db, now=when, force=True) == 0


def test_i6_preference_enabled_allows(db, flag_patch, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_POLICY_ENFORCE", "true")
    user = _user(db)
    when = _when()
    _plan_action(db, user, domain="routine", summary="Meditation", when=when)
    db.add(
        models.NotificationPrefs(
            user_id=user.id,
            companion_enabled=True,
            health_alert_enabled=True,
        )
    )
    db.commit()
    assert process_i8_coaching_followups(db, now=when, force=True) == 1


# --- I7 boundary ---


def test_i7_unavailable_still_works(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _plan_action(db, user, domain="lifestyle", summary="Journal", when=when)
    assert process_i8_coaching_followups(db, now=when, force=True) == 1


def test_no_raw_i7_in_worker():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "coaching_worker.py"
    text = root.read_text(encoding="utf-8")
    assert "narrative_summary" not in text
    assert "ConversationMemory" not in text


# --- I9 / RAG ---


def test_no_raw_i9_in_b13_modules():
    for name in ("coaching_worker.py", "coaching_i10_adapter.py"):
        text = (Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / name).read_text()
        assert "PhysiologicalMeasurement" not in text


def test_no_direct_rag():
    for name in ("coaching_worker.py", "coaching_i10_adapter.py"):
        text = (Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / name).read_text()
        for term in ("rag_service", "RAGService", "retrieve_augmented"):
            assert term not in text


# --- Chat API ---


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_real_chat_continuation(
    mock_cmd, mock_reminder, mock_brain, db, flag_patch, gate4_patch, monkeypatch
):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    mock_brain.return_value = {"message": "Ok", "language": "en"}
    user = _user(db)
    when = _when()
    _plan_action(db, user, domain="nutrition", summary="Lunch", when=when)
    process_i8_coaching_followups(db, now=when, force=True)
    notif = db.query(models.Notification).one()

    from backend.app.routers.interact import chat
    from starlette.requests import Request

    payload = ChatRequest(
        message="about lunch",
        source_notification_id=notif.id,
        conversation_id="b13-conv",
        interaction_source="notification",
    )
    scope = {"type": "http", "headers": [], "method": "POST", "path": "/interact/chat"}
    request = Request(scope)
    resp = asyncio.run(chat(request, payload, db, user))
    assert resp.continued_from_notification is True
    assert resp.source_notification_id == notif.id


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_cross_user_denied(
    mock_cmd, mock_reminder, mock_brain, db, flag_patch, gate4_patch, monkeypatch
):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    owner = _user(db, "owner")
    other = _user(db, "other")
    when = _when()
    _plan_action(db, owner, domain="routine", summary="Task", when=when)
    process_i8_coaching_followups(db, now=when, force=True)
    notif = db.query(models.Notification).one()
    from backend.app.routers.interact import chat
    from starlette.requests import Request

    payload = ChatRequest(message="hi", source_notification_id=notif.id)
    scope = {"type": "http", "headers": [], "method": "POST", "path": "/interact/chat"}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat(Request(scope), payload, db, other))
    assert exc.value.status_code == 403


# --- Transaction failure ---


def test_enqueue_failure_no_false_completion(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _, action = _plan_action(db, user, domain="routine", summary="Task", when=when)
    from backend.app.services.i10.intake import I10IntakeResult
    from backend.app.services.i10.policy_types import I10DecisionValue

    with patch(
        "backend.app.services.i10.coaching_i10_adapter.enqueue_i10_notification",
        return_value=I10IntakeResult(
            decision=I10DecisionValue.SUPPRESS,
            reason_code="TEST_FAIL",
            decision_id=None,
            notification_id=None,
            recipient_kind=None,
        ),
    ):
        assert process_single_coaching_action(db, action, now=when) is False
    db.refresh(action)
    assert action.status == "ACTIVE"


# --- Boundaries ---


def test_no_direct_notification_orm_write():
    text = Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "coaching_i10_adapter.py"
    assert "models.Notification(" not in text.read_text()


def test_no_direct_fcm():
    text = Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "coaching_i10_adapter.py"
    assert "fcm" not in text.read_text().lower()


def test_privacy_lifestyle_private(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _plan_action(db, user, domain="routine", summary="Break", when=when)
    process_i8_coaching_followups(db, now=when, force=True)
    notif = db.query(models.Notification).one()
    assert notif.privacy_class == I10PrivacyClass.PRIVATE.value


def test_privacy_nutrition_health_sensitive(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _plan_action(db, user, domain="nutrition", summary="Meal", when=when)
    process_i8_coaching_followups(db, now=when, force=True)
    notif = db.query(models.Notification).one()
    assert notif.privacy_class == I10PrivacyClass.HEALTH_SENSITIVE.value


def test_self_health_subject(db, flag_patch, gate4_patch):
    user = _user(db)
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    when = _when()
    _plan_action(db, user, domain="exercise", summary="Yoga", when=when)
    process_i8_coaching_followups(db, now=when, force=True)
    notif = db.query(models.Notification).one()
    assert notif.health_subject_id == subject.id


def test_notification_follow_up_intent():
    intent = resolve_intent(message="continue", language="en", has_verified_notification_origin=True)
    assert intent.intent_id is IntentId.NOTIFICATION_FOLLOW_UP


def test_coaching_flag_default_off(monkeypatch):
    monkeypatch.delenv("SEDI_I10_COACHING_FOLLOWUP_ENABLED", raising=False)
    assert s10_flags.coaching_followup_enabled() is False


def test_worker_inactive_when_flag_off(db, gate4_patch):
    user = _user(db)
    when = _when()
    _plan_action(db, user, domain="routine", summary="X", when=when)
    assert process_i8_coaching_followups(db, now=when) == 0


def test_b13_does_not_auto_create_care_followup(db, flag_patch, gate4_patch):
    user = _user(db)
    when = _when()
    _plan_action(db, user, domain="routine", summary="X", when=when)
    before = db.query(models.CareFollowUpTask).count()
    process_i8_coaching_followups(db, now=when, force=True)
    assert db.query(models.CareFollowUpTask).count() == before


def test_lifestyle_scheduler_no_direct_orm():
    text = Path(__file__).resolve().parents[1] / "app" / "services" / "section10" / "lifestyle_reminder_scheduler.py"
    assert "models.Notification(" not in text.read_text()
