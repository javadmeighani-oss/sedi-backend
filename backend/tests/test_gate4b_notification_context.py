"""Gate 4-B — notification traceability context tests."""

import json

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.app.models import Notification, User
from backend.app.services.gate4.notification_context import (
    NotificationCategory,
    NotificationRiskLevel,
    NotificationSourceType,
    build_scheduler_context,
    map_notification_type_to_category,
    map_priority_to_risk_level,
    resolve_effective_category,
    resolve_effective_risk_level,
    resolve_traceability_fields,
    sanitize_notification_context,
    serialize_notification_context,
)
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.notification_engine import NotificationBuilder


@pytest.fixture
def test_user(db: Session):
    user = User(
        id=901,
        name="Gate4B Test User",
        secret_key="secret",
        preferred_language="en",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_notification_category_constants():
    assert NotificationCategory.DAILY_STATUS.value == "daily_status"
    assert NotificationCategory.MEDICATION_REMINDER.value == "medication_reminder"
    assert NotificationCategory.SYSTEM.value == "system"


def test_notification_source_type_constants():
    assert NotificationSourceType.MEDICATION_SCHEDULE.value == "medication_schedule"
    assert NotificationSourceType.SYSTEM_SCHEDULER.value == "system_scheduler"


def test_map_notification_type_to_category():
    assert map_notification_type_to_category("morning_brief") == "daily_status"
    assert map_notification_type_to_category("connection_ping") == "engagement_checkin"
    assert map_notification_type_to_category("companion_ping") == "engagement_checkin"
    assert map_notification_type_to_category("device_disconnected") == "device_alert"
    assert map_notification_type_to_category(
        "health_alert",
        {"alert_code": "medication_reminder"},
    ) == "medication_reminder"
    assert map_notification_type_to_category("health_alert") == "health_status"
    assert map_notification_type_to_category("unknown_type") == "system"


def test_map_priority_to_risk_level():
    assert map_priority_to_risk_level("critical") == NotificationRiskLevel.CRITICAL.value
    assert map_priority_to_risk_level("high") == NotificationRiskLevel.HIGH.value
    assert map_priority_to_risk_level("low") == NotificationRiskLevel.LOW.value
    assert map_priority_to_risk_level("normal") == NotificationRiskLevel.NORMAL.value


def test_sanitize_notification_context_allowlist():
    cleaned = sanitize_notification_context(
        {
            "template_key": "morning",
            "job_id": "morning_notifications",
            "schedule_time": "08:00",
        }
    )
    assert cleaned == {
        "template_key": "morning",
        "job_id": "morning_notifications",
        "schedule_time": "08:00",
    }


def test_sanitize_notification_context_drops_forbidden_keys():
    cleaned = sanitize_notification_context(
        {
            "template_key": "medication_reminder",
            "phone": "09120000000",
            "raw_message": "secret text",
            "dosage_instructions": "take 2 pills",
            "device_payload": "{}",
            "api_key": "abc",
        }
    )
    assert cleaned == {"template_key": "medication_reminder"}
    assert "phone" not in (cleaned or {})
    assert "raw_message" not in (cleaned or {})


def test_serialize_notification_context_empty():
    assert serialize_notification_context(None) is None
    assert serialize_notification_context({}) is None


def test_resolve_effective_category_fallback():
    assert resolve_effective_category(
        category=None,
        notification_type="morning_brief",
    ) == "daily_status"
    assert resolve_effective_category(
        category="device_alert",
        notification_type="device_disconnected",
    ) == "device_alert"


def test_resolve_effective_risk_level_fallback():
    assert resolve_effective_risk_level(risk_level=None, priority="high") == "high"
    assert resolve_effective_risk_level(risk_level="low", priority="critical") == "low"


def test_resolve_traceability_fields_defaults():
    fields = resolve_traceability_fields(
        notification_type="morning_brief",
        priority="normal",
    )
    assert fields["category"] == "daily_status"
    assert fields["risk_level"] == "normal"
    assert fields["source_type"] is None
    assert fields["context_json"] is None


def test_resolve_traceability_fields_medication():
    fields = resolve_traceability_fields(
        notification_type="health_alert",
        priority="high",
        category=NotificationCategory.MEDICATION_REMINDER.value,
        source_type=NotificationSourceType.MEDICATION_SCHEDULE.value,
        source_id="42",
        context={"schedule_time": "08:00", "template_key": "medication_reminder"},
        template_key="medication_reminder",
        metadata={"alert_code": "medication_reminder"},
    )
    assert fields["category"] == "medication_reminder"
    assert fields["source_type"] == "medication_schedule"
    assert fields["source_id"] == "42"
    parsed = json.loads(fields["context_json"])
    assert parsed["schedule_time"] == "08:00"
    assert "dosage" not in json.dumps(parsed)


def test_notification_model_has_gate4b_columns():
    mapper = inspect(Notification)
    col_names = {c.key for c in mapper.columns}
    for name in (
        "category",
        "source_type",
        "source_id",
        "context_json",
        "risk_level",
        "template_key",
    ):
        assert name in col_names


def test_notification_builder_persist_sets_traceability(db: Session, test_user):
    builder = NotificationBuilder(db)
    payload = NotificationPayload(
        user_id=test_user.id,
        type="morning_brief",
        title="Good morning",
        body="Hello",
        priority="normal",
        dedupe_key=f"test_gate4b:{test_user.id}:morning",
        category=NotificationCategory.DAILY_STATUS.value,
        source_type=NotificationSourceType.DAILY_ROUTINE.value,
        template_key="morning",
        context=build_scheduler_context(job_id="morning_notifications", template_key="morning"),
    )
    notif = builder.persist(payload, check_dedupe=False)
    assert notif is not None
    assert notif.category == "daily_status"
    assert notif.source_type == "daily_routine"
    assert notif.risk_level == "normal"
    assert notif.template_key == "morning"
    assert notif.context_json is not None


def test_notification_builder_legacy_payload_still_works(db: Session, test_user):
    builder = NotificationBuilder(db)
    payload = NotificationPayload(
        user_id=test_user.id,
        type="connection_ping",
        title="Hi",
        body="Checking in",
        priority="low",
        dedupe_key=f"test_gate4b_legacy:{test_user.id}:ping",
        metadata={"language": "en"},
    )
    notif = builder.persist(payload, check_dedupe=False)
    assert notif is not None
    assert notif.category == "engagement_checkin"
    assert notif.risk_level == "low"


def test_feedback_copies_source_to_interaction_event(db: Session, test_user):
    from backend.app.models import Notification as NotifModel
    from backend.app.services.gate4.interaction_event_service import (
        create_notification_action_event_from_feedback,
    )

    notif = NotifModel(
        user_id=test_user.id,
        type="morning_brief",
        title="t",
        body="b",
        priority="normal",
        category="daily_status",
        source_type="daily_routine",
        source_id="1",
        risk_level="normal",
        template_key="morning",
        dedupe_key=f"test_fb_src:{test_user.id}",
        status="queued",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    event = create_notification_action_event_from_feedback(
        db,
        user_id=test_user.id,
        notification_id=notif.id,
        payload={"action_id": "ACK_THANKS", "reaction": "interact"},
        legacy_event_type="like",
    )
    db.commit()
    assert event.source_notification_id == notif.id
    assert event.source_type == "daily_routine"
    assert event.source_id == "1"


def test_push_payload_omits_source_id_by_default():
    from backend.app.services.gate4.push_payload import build_gate4_push_data_payload

    data = build_gate4_push_data_payload(
        notification_id=10,
        user_id=1,
        title="t",
        body="b",
        category="daily_status",
        risk="normal",
        priority="normal",
        language="en",
        deeplink_url="sedi://chat?from=notif&id=10",
        source_type="daily_routine",
        source_id="99",
        template_key="morning",
        include_source_refs=False,
    )
    assert data["gate4_category"] == "daily_status"
    assert data["gate4_template_key"] == "morning"
    assert "source_id" not in data
    assert "source_type" not in data
