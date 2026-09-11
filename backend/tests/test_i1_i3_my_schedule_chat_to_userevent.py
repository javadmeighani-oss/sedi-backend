"""I3/I1 My Schedule Chat→UserEvent canonical seam — targeted tests."""

from __future__ import annotations

import os
from datetime import datetime, timezone

os.environ.setdefault("SMS_DISABLED", "true")

from backend.app.core.security import create_access_token
from backend.app.models import I8OperationalPlan, User, UserEvent, UserProfileCore
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.intelligence.contracts import (
    IntentConfidenceBand,
    IntentId,
    IntentResult,
    LanguageCode,
    ReadinessStatus,
    RequestKind,
)
from backend.app.services.intelligence.intent_registry import REGISTRY_VERSION, resolve_intent
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
from backend.app.services.intelligence.reminder_event_dispatch import (
    dispatch_reminder_user_event,
)
from backend.app.services.intelligence.reminder_event_readiness import (
    evaluate_reminder_event_readiness,
    parse_reminder_event_draft,
)
from backend.app.services.intelligence.safety_risk import assess_safety_risk_safe


def _intent() -> IntentResult:
    return IntentResult(
        registry_version=REGISTRY_VERSION,
        intent_id=IntentId.REMINDER,
        request_kind=RequestKind.ACTION,
        confidence_band=IntentConfidenceBand.HIGH,
        rule_id="i3.rule.reminder.action.v1",
    )


def _user(db, phone: str, *, tz: str | None = "UTC") -> User:
    u = User(name="RemU", secret_key="t", preferred_language="fa", phone=phone)
    db.add(u)
    db.commit()
    db.refresh(u)
    if tz:
        db.add(UserProfileCore(user_id=u.id, timezone=tz))
        db.commit()
    return u


def _auth(uid: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'user_id': uid})}"}


def test_1_fa_complete_lab_tomorrow():
    now = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)  # Thu
    draft, missing = parse_reminder_event_draft(
        message="فردا ساعت ۱۰ آزمایش خون دارم",
        timezone_name="UTC",
        now_utc=now,
    )
    assert missing is None and draft is not None
    assert draft.event_type == "lab_test"
    assert draft.starts_at_local.day == 11
    assert draft.starts_at_local.hour == 10
    ready = evaluate_reminder_event_readiness(
        message="فردا ساعت ۱۰ آزمایش خون دارم",
        language="fa",
        intent=_intent(),
        timezone_name="UTC",
        now_utc=now,
    )
    assert ready.status is ReadinessStatus.READY


def test_2_fa_incomplete_thursday_doctor():
    ready = evaluate_reminder_event_readiness(
        message="پنجشنبه دکتر دارم",
        language="fa",
        intent=_intent(),
        timezone_name="UTC",
        now_utc=datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc),
    )
    assert ready.status is ReadinessStatus.NEEDS_CLARIFICATION
    assert ready.clarification is not None


def test_3_fa_today_not_tomorrow():
    now = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
    draft, missing = parse_reminder_event_draft(
        message="امروز ساعت ۵ جلسه دارم",
        timezone_name="UTC",
        now_utc=now,
    )
    assert missing is None and draft is not None
    assert draft.starts_at_local.day == 10
    assert draft.starts_at_local.hour == 17
    assert draft.starts_at_local.day != 11


def test_4_en_complete_reminder_offset(client, db):
    u = _user(db, "+19990000001", tz="UTC")
    now = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
    msg = "Tomorrow at 10 I have an exam. Remind me 1 hour before."
    orch = IntelligenceOrchestrator(db=db, structured_mode=False)
    res = orch.process(
        authenticated_user_id=u.id,
        message=msg,
        language="en",
        timezone="UTC",
        precomputed_assessment=assess_safety_risk_safe(message=msg, language="en"),
    )
    assert res.intent_id == "reminder"
    assert any("I3_REMINDER_USEREVENT" in c for c in res.reason_codes)
    rows = db.query(UserEvent).filter(UserEvent.user_id == u.id).all()
    assert len(rows) == 1
    assert rows[0].source == "conversation"
    assert rows[0].event_type == "exam"
    assert rows[0].reminder_enabled is True
    assert "60" in (rows[0].reminder_offsets_json or "")


def test_5_ar_complete_event(client, db):
    u = _user(db, "+19990000002", tz="UTC")
    msg = "غدا الساعة 10 عندي امتحان"
    orch = IntelligenceOrchestrator(db=db, structured_mode=False)
    orch.process(
        authenticated_user_id=u.id,
        message=msg,
        language="ar",
        timezone="UTC",
        precomputed_assessment=assess_safety_risk_safe(message="hello", language="en"),
    )
    rows = db.query(UserEvent).filter(UserEvent.user_id == u.id).all()
    assert len(rows) == 1
    assert rows[0].event_type == "exam"


def test_6_ordinary_chat_no_event(client, db):
    u = _user(db, "+19990000003", tz="UTC")

    def _stub_gen(*_a, **_k):
        return {"message": "Hello — ordinary chat stub."}

    orch = IntelligenceOrchestrator(
        db=db, structured_mode=False, legacy_generator=_stub_gen
    )
    orch.process(
        authenticated_user_id=u.id,
        message="How are you today?",
        language="en",
        timezone="UTC",
        precomputed_assessment=assess_safety_risk_safe(
            message="How are you today?", language="en"
        ),
    )
    assert db.query(UserEvent).filter(UserEvent.user_id == u.id).count() == 0


def test_7_safety_terminal_no_event(client, db):
    u = _user(db, "+19990000004", tz="UTC")
    msg = "I want to kill myself"
    orch = IntelligenceOrchestrator(db=db, structured_mode=False)
    assessment = assess_safety_risk_safe(message=msg, language="en")
    orch.process(
        authenticated_user_id=u.id,
        message=msg,
        language="en",
        timezone="UTC",
        precomputed_assessment=assessment,
    )
    assert db.query(UserEvent).filter(UserEvent.user_id == u.id).count() == 0


def test_8_duplicate_path_one_event(client, db):
    u = _user(db, "+19990000005", tz="UTC")
    msg = "Tomorrow at 10 I have an exam"
    orch = IntelligenceOrchestrator(db=db, structured_mode=False)
    a = assess_safety_risk_safe(message="hi", language="en")
    orch.process(
        authenticated_user_id=u.id,
        message=msg,
        language="en",
        timezone="UTC",
        precomputed_assessment=a,
    )
    orch.process(
        authenticated_user_id=u.id,
        message=msg,
        language="en",
        timezone="UTC",
        precomputed_assessment=a,
    )
    assert db.query(UserEvent).filter(UserEvent.user_id == u.id).count() == 1


def test_9_recurrence_refused():
    ready = evaluate_reminder_event_readiness(
        message="هر شب ساعت ۱۱ می‌خوابم",
        language="fa",
        intent=_intent(),
        timezone_name="UTC",
    )
    assert ready.status is ReadinessStatus.NEEDS_CLARIFICATION
    assert "recurrence" in (ready.missing_fact_keys[0] if ready.missing_fact_keys else "")


def test_10_timezone_fail_closed():
    ready = evaluate_reminder_event_readiness(
        message="Tomorrow at 10 I have an exam",
        language="en",
        intent=_intent(),
        timezone_name=None,
    )
    assert ready.status is ReadinessStatus.NEEDS_CLARIFICATION
    assert "timezone" in (ready.missing_fact_keys[0] if ready.missing_fact_keys else "")


def test_11_i8_plan_unaffected(client, db):
    u = _user(db, "+19990000006", tz="UTC")
    now = datetime.now(timezone.utc)
    window = resolve_local_day_window(db, u.id, now_utc=now)
    before = db.query(I8OperationalPlan).filter(I8OperationalPlan.user_id == u.id).count()
    orch = IntelligenceOrchestrator(db=db, structured_mode=False)
    orch.process(
        authenticated_user_id=u.id,
        message="Tomorrow at 9 I have a meeting",
        language="en",
        timezone="UTC",
        precomputed_assessment=assess_safety_risk_safe(message="hi", language="en"),
    )
    after = db.query(I8OperationalPlan).filter(I8OperationalPlan.user_id == u.id).count()
    assert before == after
    assert db.query(UserEvent).filter(UserEvent.user_id == u.id).count() == 1


def test_12_i10_reminder_fields_not_direct_notification(client, db):
    u = _user(db, "+19990000007", tz="UTC")
    from backend.app.models import Notification

    before = db.query(Notification).filter(Notification.user_id == u.id).count()
    dispatch_reminder_user_event(
        db,
        user_id=u.id,
        message="Tomorrow at 10 I have an exam. Remind me 1 hour before.",
        timezone_name="UTC",
        now_utc=datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc),
    )
    after = db.query(Notification).filter(Notification.user_id == u.id).count()
    assert after == before
    ev = db.query(UserEvent).filter(UserEvent.user_id == u.id).one()
    assert ev.reminder_enabled is True
    assert ev.source == "conversation"


def test_intent_resolves_schedule_phrases():
    fa = resolve_intent(message="فردا ساعت ۱۰ آزمایش خون دارم", language="fa")
    assert fa.intent_id is IntentId.REMINDER
    en = resolve_intent(
        message="Thursday at 10 I have an exam. Remind me 1 hour before.",
        language="en",
    )
    assert en.intent_id is IntentId.REMINDER


def test_interact_no_legacy_parallel(client, db):
    """Canonical /interact/chat must not call legacy create_user_chat_reminder."""
    import backend.app.routers.interact as interact_mod

    src = open(interact_mod.__file__, encoding="utf-8").read()
    assert "create_user_chat_reminder" not in src
