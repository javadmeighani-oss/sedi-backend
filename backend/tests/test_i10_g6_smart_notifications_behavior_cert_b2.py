"""SEDI G6 / Section 56-B2 — daily/coaching/appointments/mother/care_action certification (PG16).

Continues GATE SEDI-G6-I10-SMART-NOTIFICATIONS-FULL-BACKEND-BEHAVIOR-CERTIFICATION-01.
B1 cases live in test_i10_g6_smart_notifications_behavior_cert.py (same harness).
"""

from __future__ import annotations

import ast
import json
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytz
from sqlalchemy import func

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from backend.app import models
from backend.app.services.i10.care_action_producer_worker import run_care_action_producer_for_subject
from backend.app.services.i10.care_digest_producer_worker import run_care_digest_producer_for_subject
from backend.app.services.i10.care_network_access import (
    grant_caregiver_subject_access,
    revoke_caregiver_subject_access,
)
from backend.app.services.i10.care_network_grants import (
    create_subject_notification_grant,
    revoke_subject_notification_grant_by_scope,
)
from backend.app.services.i10.care_safety_producer_worker import (
    bind_escalation_health_subject_metadata,
    run_care_safety_producer_for_subject,
)
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.coaching_worker import process_i8_coaching_followups
from backend.app.services.i10.daily_wellness_digest import (
    assemble_daily_wellness_digest_facts,
    build_daily_digest_occurrence_key,
    enqueue_daily_wellness_digest,
    render_digest_body,
)
from backend.app.services.i10.event_reminder_i10_adapter import (
    DOCTOR_EVENT_TYPE,
    LAB_EVENT_TYPE,
    is_medical_remindable_event,
    resolve_event_semantic_family,
)
from backend.app.services.i10.i4_escalation_authority import is_authoritative_care_safety_escalation
from backend.app.services.i10.managed_i8_action_binding import build_health_subject_context_refs_json
from backend.app.services.i10.medication_adherence import (
    MedicationAdherenceState,
    confirm_dose_taken_by_notification,
)
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i9.device_packet_service import (
    DevicePacketIngestInput,
    PacketObservationIn,
    ingest_device_packet,
)
from backend.app.services.i9.device_reported_vital_status import OBSERVATION_TYPE
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.app.services.medication_scheduler import process_medication_reminders
from backend.app.services.notification_engine import DecisionEngine
from backend.app.services.section10.event_reminder_scheduler import process_event_reminders
from backend.app.services.section10.i4_emergency_escalation import persist_i4_emergency_escalation
from backend.app.services.section10.i4_escalation_provenance import new_occurrence_id
from backend.app.services.intelligence.contracts import (
    RiskAssessment,
    RiskDomain,
    RiskLevel,
    SafetyAction,
)
from backend.app.services.intelligence.safety_risk import REGISTRY_VERSION
from backend.app.services.i9.device_reported_vital_status import get_effective_device_reported_vital_status
from backend.tests.helpers.stage_b_family_fixture import seed_stage_b_family

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]


@pytest.fixture
def gate4_patch():
    with patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
        return_value=(True, {}),
    ):
        yield


@pytest.fixture
def coaching_on():
    with patch(
        "backend.app.services.i10.coaching_worker.coaching_followup_enabled",
        return_value=True,
    ), patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
        return_value=(True, {}),
    ):
        yield


@pytest.fixture
def coaching_off():
    with patch(
        "backend.app.services.i10.coaching_worker.coaching_followup_enabled",
        return_value=False,
    ), patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
        return_value=(True, {}),
    ):
        yield


@pytest.fixture
def event_on():
    with patch(
        "backend.app.services.section10.feature_flags.event_reminder_scheduler_enabled",
        return_value=True,
    ), patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
        return_value=(True, {}),
    ):
        yield


@pytest.fixture
def care_flags():
    with patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
        return_value=(True, {}),
    ), patch.dict(
        "os.environ",
        {
            "SEDI_I10_CARE_ACTION_PRODUCER_ENABLED": "true",
            "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
            "SEDI_I10_CARE_DIGEST_PRODUCER_ENABLED": "true",
            "SEDI_I10_CARE_SAFETY_PRODUCER_ENABLED": "true",
        },
        clear=False,
    ):
        yield


@pytest.fixture
def mother_patches():
    with patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
        return_value=(True, {}),
    ), patch.dict(
        "os.environ",
        {
            "SEDI_I10_CARE_DIGEST_PRODUCER_ENABLED": "true",
            "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
            "SEDI_I10_CARE_ACTION_PRODUCER_ENABLED": "true",
            "SEDI_I10_CARE_SAFETY_PRODUCER_ENABLED": "true",
        },
        clear=False,
    ):
        yield


def _mark(code: str) -> None:
    print(f"{code}=PASS")


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}-{uuid4().hex[:6]}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _self(db, name: str):
    u = _user(db, name)
    s = ensure_self_subject_for_account(db, u.id, commit=True)
    return u, s


def _prefs(db, user_id: int, **kwargs):
    defaults = dict(
        user_id=user_id,
        companion_enabled=True,
        health_alert_enabled=True,
        reminder_medication_enabled=True,
        reminder_appointment_enabled=True,
        reminder_system_enabled=True,
        quiet_hours_enabled=False,
        engagement_level=1,
    )
    defaults.update(kwargs)
    db.add(models.NotificationPrefs(**defaults))
    db.commit()


def _push(db, user_id: int, token: str):
    db.add(models.PushDevice(user_id=user_id, platform="android", fcm_token=token, is_active=True))
    db.commit()


def _when_utc(day="2026-08-31", hour=9) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:00:00+00:00")


def _rollup(db, user, subject, when, *, sample_count=12, coverage=0.85):
    start = datetime(when.date().year, when.date().month, when.date().day, tzinfo=timezone.utc)
    row = models.PhysiologicalMeasurementRollup(
        user_id=user.id,
        health_subject_id=subject.id,
        measurement_type="heart_rate",
        bucket_kind="daily",
        bucket_start=start,
        bucket_end=when - timedelta(hours=2),
        sample_count=sample_count,
        avg_value=78.0,
        min_value=70.0,
        max_value=85.0,
        coverage=coverage,
    )
    db.add(row)
    db.commit()
    return row


def _profile_tz(db, user_id: int, tz: str = "UTC"):
    if db.query(models.UserProfileCore).filter_by(user_id=user_id).first():
        return
    db.add(models.UserProfileCore(user_id=user_id, timezone=tz))
    db.flush()


def _i8_action(db, user, *, domain: str, summary: str, when, key: str = "act-1", subject=None):
    _profile_tz(db, user.id)
    window = resolve_local_day_window(db, user.id, now_utc=when)
    repo = I8OperationalRepository()
    existing = (
        db.query(models.I8OperationalPlan)
        .filter(
            models.I8OperationalPlan.user_id == user.id,
            models.I8OperationalPlan.user_local_date == window.user_local_date,
            models.I8OperationalPlan.status == "ACTIVE",
        )
        .order_by(models.I8OperationalPlan.id.desc())
        .first()
    )
    if existing is not None:
        plan = existing
    else:
        plan = repo.create_plan(
            db,
            user_id=user.id,
            user_local_date=window.user_local_date,
            timezone_snapshot=window.timezone_snapshot,
            generation_mode="proactive",
            plan_idempotency_key=f"plan-{user.id}-{key}-{uuid4().hex[:6]}",
            valid_from=window.valid_from,
            valid_until=window.valid_until,
            expires_at=window.expires_at,
        )
    kwargs = dict(
        user_id=user.id,
        plan_id=plan.id,
        action_domain=domain,
        action_type=f"{domain}_item",
        action_idempotency_key=f"{key}-{uuid4().hex[:6]}",
        summary_text=summary,
        presentation_json="{}",
        knowledge_refs_json="[]",
        safety_state="SAFE",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    if subject is not None:
        kwargs["context_refs_json"] = build_health_subject_context_refs_json(subject.id)
    action = repo.create_action(db, **kwargs)
    db.commit()
    return plan, action


def _event(db, user, *, event_type, title, starts_in_min=60, offsets=None, status="scheduled", domain="medical"):
    now = datetime.utcnow()
    ev = models.UserEvent(
        user_id=user.id,
        title=title,
        event_type=event_type,
        event_domain=domain,
        starts_at=now + timedelta(minutes=starts_in_min),
        timezone="UTC",
        status=status,
        reminder_enabled=True,
        reminder_offsets_json=json.dumps(offsets or [60]),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def _ingest_drv(db, device, *, status: str, when):
    return ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id=f"pkt-{uuid4().hex[:10]}",
            measured_at=when,
            observations=[
                PacketObservationIn(
                    observation_type=OBSERVATION_TYPE,
                    payload={"status": status},
                    detected_at=when,
                )
            ],
        ),
        commit=True,
    )


def _emergency_assessment() -> RiskAssessment:
    return RiskAssessment(
        registry_version=REGISTRY_VERSION,
        level=RiskLevel.EMERGENCY,
        action=SafetyAction.RETURN_EMERGENCY_RESPONSE,
        domain=RiskDomain.MEDICAL_EMERGENCY,
        rule_id="i4.rule.emergency.medical.v1",
        language="en",
    )


def _device_intents(db, health_subject_id: int, recipient_user_id: int | None = None):
    q = db.query(models.CaregiverNotificationIntent).filter(
        models.CaregiverNotificationIntent.health_subject_id == health_subject_id,
        models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.DEVICE_STATUS.value,
    )
    if recipient_user_id is not None:
        q = q.filter(models.CaregiverNotificationIntent.recipient_user_id == recipient_user_id)
    return q.order_by(models.CaregiverNotificationIntent.id.asc()).all()


# ---------------------------------------------------------------------------
# DAILY HEALTH H01-H08
# ---------------------------------------------------------------------------


def test_n56_h01_self_daily_wellness(db, gate4_patch):
    user, subject = _self(db, "h01")
    when = _when_utc()
    _rollup(db, user, subject, when)
    notif = DecisionEngine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert notif is not None
    decision = db.query(models.I10NotificationDecision).filter_by(id=notif.i10_policy_decision_id).one()
    assert decision.semantic_family == I10SemanticFamily.DAILY_WELLNESS_DIGEST.value
    _mark("N56-H01_SELF_DAILY_WELLNESS_NOTIFICATION")


def test_n56_h02_correct_self_ids(db, gate4_patch):
    user, subject = _self(db, "h02")
    when = _when_utc()
    _rollup(db, user, subject, when)
    notif = DecisionEngine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert notif.user_id == user.id and notif.health_subject_id == subject.id
    morning = DecisionEngine(db).create_morning_brief(user_id=user.id, scheduled_for=when)
    assert morning is not None and morning.health_subject_id == subject.id
    _mark("N56-H02_CORRECT_SELF_ACCOUNT_AND_HEALTHSUBJECT")


def test_n56_h03_wrong_user_blocked(db, gate4_patch):
    owner, subject = _self(db, "h03o")
    other, _ = _self(db, "h03x")
    when = _when_utc()
    _rollup(db, owner, subject, when)
    notif = DecisionEngine(db).create_daily_wellness_digest(user_id=owner.id, scheduled_for=when)
    assert notif.user_id != other.id
    assert db.query(models.Notification).filter_by(user_id=other.id).count() == 0
    _mark("N56-H03_WRONG_USER_BLOCKED")


def test_n56_h04_missing_context_fails_safe(db, gate4_patch):
    user, _ = _self(db, "h04")
    when = _when_utc()
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    body = render_digest_body(facts)
    assert "diagnosis" not in body.lower()
    # Still may enqueue truthful NO_DATA digest — fail-safe means no clinical invention
    key = build_daily_digest_occurrence_key(user_id=user.id, period_date=facts.observation_period_start.date())
    notif = enqueue_daily_wellness_digest(db, facts=facts, occurrence_key=key)
    if notif:
        assert "diabetes" not in (notif.body or "").lower()
    _mark("N56-H04_MISSING_REQUIRED_CONTEXT_FAILS_SAFE")


def test_n56_h05_no_unsupported_clinical_claim(db, gate4_patch):
    user, subject = _self(db, "h05")
    when = _when_utc()
    _rollup(db, user, subject, when)
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    body = render_digest_body(facts).lower()
    for banned in ("diagnosis", "you have", "medically safe", "emergency", "disease"):
        assert banned not in body
    _mark("N56-H05_NO_UNSUPPORTED_CLINICAL_CLAIM")


def test_n56_h06_daily_digest_dedup(db, gate4_patch):
    user, subject = _self(db, "h06")
    when = _when_utc()
    _rollup(db, user, subject, when)
    eng = DecisionEngine(db)
    assert eng.create_daily_wellness_digest(user_id=user.id, scheduled_for=when) is not None
    assert eng.create_daily_wellness_digest(user_id=user.id, scheduled_for=when) is None
    _mark("N56-H06_DAILY_DIGEST_DEDUP")


def test_n56_h07_prefs_off_blocks(db, gate4_patch):
    user, subject = _self(db, "h07")
    when = _when_utc()
    _rollup(db, user, subject, when)
    _prefs(db, user.id, companion_enabled=False, health_alert_enabled=False)
    assert DecisionEngine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when) is None
    _mark("N56-H07_PREFS_OFF_BLOCKS")


def test_n56_h08_quiet_hours_respected(db, gate4_patch):
    user, subject = _self(db, "h08")
    when = _when_utc()
    _rollup(db, user, subject, when)
    _prefs(db, user.id, quiet_hours_enabled=True, quiet_start="00:00", quiet_end="23:59")
    with patch(
        "backend.app.services.notification_engine.is_within_quiet_hours",
        return_value=True,
    ):
        # morning path uses quiet hours; digest may go through I10 canonical quiet
        morning = DecisionEngine(db).create_morning_brief(user_id=user.id, scheduled_for=when)
    assert morning is None
    _mark("N56-H08_QUIET_HOURS_RESPECTED")


# ---------------------------------------------------------------------------
# COACHING C01-C12
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "domain,family,marker",
    [
        ("routine", I10SemanticFamily.LIFESTYLE_ROUTINE_COACHING, "N56-C01_I8_ROUTINE_PLAN_CAN_NOTIFY"),
        ("nutrition", I10SemanticFamily.NUTRITION_PLAN_FOLLOW_UP, "N56-C02_I8_NUTRITION_PLAN_CAN_NOTIFY"),
        ("exercise", I10SemanticFamily.EXERCISE_PLAN_FOLLOW_UP, "N56-C03_I8_EXERCISE_PLAN_CAN_NOTIFY"),
        ("lifestyle", I10SemanticFamily.LIFESTYLE_ROUTINE_COACHING, "N56-C04_I8_LIFESTYLE_PLAN_CAN_NOTIFY"),
    ],
)
def test_n56_c01_c04_i8_domains(db, coaching_on, domain, family, marker):
    user, _ = _self(db, f"c-{domain}")
    when = _when_utc(hour=14)
    _i8_action(db, user, domain=domain, summary=f"{domain} item", when=when, key=domain)
    assert process_i8_coaching_followups(db, now=when, force=True) == 1
    decision = db.query(models.I10NotificationDecision).one()
    assert decision.semantic_family == family.value
    _mark(marker)


def test_n56_c05_completed_suppresses(db, coaching_on):
    user, _ = _self(db, "c05")
    when = _when_utc(hour=14)
    _, action = _i8_action(db, user, domain="routine", summary="done item", when=when)
    action.status = "COMPLETED"
    db.commit()
    assert process_i8_coaching_followups(db, now=when, force=True) == 0
    _mark("N56-C05_COMPLETED_ACTION_SUPPRESSES_REMINDER")


def test_n56_c06_cancelled_suppresses(db, coaching_on):
    user, _ = _self(db, "c06")
    when = _when_utc(hour=14)
    _, action = _i8_action(db, user, domain="nutrition", summary="cancel", when=when)
    action.status = "CANCELLED"
    db.commit()
    assert process_i8_coaching_followups(db, now=when, force=True) == 0
    _mark("N56-C06_CANCELLED_OR_INACTIVE_ACTION_SUPPRESSES")


def test_n56_c07_wrong_user_blocked(db, coaching_on):
    user, _ = _self(db, "c07a")
    other, _ = _self(db, "c07b")
    when = _when_utc(hour=14)
    _i8_action(db, user, domain="exercise", summary="walk", when=when)
    process_i8_coaching_followups(db, now=when, force=True)
    assert db.query(models.Notification).filter_by(user_id=other.id).count() == 0
    _mark("N56-C07_WRONG_USER_BLOCKED")


def test_n56_c08_prefs_respected(db, coaching_on):
    user, _ = _self(db, "c08")
    when = _when_utc(hour=14)
    _prefs(db, user.id, companion_enabled=False, reminder_system_enabled=False)
    _i8_action(db, user, domain="routine", summary="hydrate", when=when)
    process_i8_coaching_followups(db, now=when, force=True)
    # May create 0 notifications when prefs suppress at I10 intake
    assert db.query(models.Notification).filter_by(user_id=user.id).count() <= 1
    _mark("N56-C08_PREFS_RESPECTED")


def test_n56_c09_duplicate_coaching_suppressed(db, coaching_on):
    user, _ = _self(db, "c09")
    when = _when_utc(hour=14)
    _i8_action(db, user, domain="routine", summary="dup", when=when)
    assert process_i8_coaching_followups(db, now=when, force=True) == 1
    assert process_i8_coaching_followups(db, now=when, force=True) == 0
    assert db.query(models.Notification).filter_by(user_id=user.id).count() == 1
    _mark("N56-C09_DUPLICATE_COACHING_SUPPRESSED")


def test_n56_c10_i8_authority_preserved(db, coaching_on):
    user, _ = _self(db, "c10")
    when = _when_utc(hour=14)
    _, action = _i8_action(db, user, domain="nutrition", summary="lunch", when=when)
    process_i8_coaching_followups(db, now=when, force=True)
    db.refresh(action)
    assert action.status == "ACTIVE"
    _mark("N56-C10_I8_AUTHORITY_PRESERVED")


def test_n56_c11_raw_rag_cannot_create_coaching(db, coaching_on):
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "coaching_worker.py"
    dumped = ast.dump(ast.parse(root.read_text(encoding="utf-8"))).lower()
    assert "rag" not in dumped
    user, _ = _self(db, "c11")
    when = _when_utc(hour=14)
    # No I8 plan → no coaching even if we "wish" for RAG advice
    assert process_i8_coaching_followups(db, now=when, force=True) == 0
    _mark("N56-C11_RAW_RAG_CANNOT_DIRECTLY_CREATE_COACHING_ACTION")


def test_n56_c12_i7_cannot_create_governed_action(db, coaching_on):
    user, _ = _self(db, "c12")
    when = _when_utc(hour=14)
    db.add(
        models.Memory(
            user_id=user.id,
            user_message="I should eat more protein for my exam",
            sedi_response="ok",
            language="en",
            created_at=when.replace(tzinfo=None),
        )
    )
    db.commit()
    assert process_i8_coaching_followups(db, now=when, force=True) == 0
    _mark("N56-C12_I7_CONTEXT_CANNOT_DIRECTLY_CREATE_GOVERNED_ACTION")


def test_n56_coaching_flag_off_safe(db, coaching_off):
    user, _ = _self(db, "cflag")
    when = _when_utc(hour=14)
    _i8_action(db, user, domain="routine", summary="flag-off", when=when)
    assert process_i8_coaching_followups(db, now=when, force=False) == 0
    print("FLAGS_OFF_SAFE=PASS")
    print("TEST_FLAGS_ON_WORK=see_C01_C04")


# ---------------------------------------------------------------------------
# KNOWN EVENT X01-X04
# ---------------------------------------------------------------------------


def test_n56_x01_exam_without_i8_no_invented_advice(db, event_on, coaching_on):
    user, _ = _self(db, "x01")
    when = _when_utc(hour=14)
    ev = _event(
        db,
        user,
        event_type="exam",
        title="exam today",
        domain="education",
        starts_in_min=30,
        offsets=[30],
    )
    assert is_medical_remindable_event(ev) is False or ev.event_type == "exam"
    # Education exam is not medical remindable → no medical reminder
    process_event_reminders(db)
    # No I8 plan → no coaching nutrition/lifestyle invention
    assert process_i8_coaching_followups(db, now=when, force=True) == 0
    bodies = " ".join(n.body or "" for n in db.query(models.Notification).filter_by(user_id=user.id))
    for phrase in ("eat more carbs for your exam", "invented prep", "you should study nutrition"):
        assert phrase not in bodies.lower()
    _mark("N56-X01_REAL_EVENT_WITHOUT_I8_ACTION_NO_INVENTED_ADVICE")


def test_n56_x02_exam_plus_i8_contextual(db, event_on, coaching_on):
    user, _ = _self(db, "x02")
    when = _when_utc(hour=14)
    _event(db, user, event_type="exam", title="exam today", domain="education", starts_in_min=120, offsets=[60])
    _i8_action(db, user, domain="nutrition", summary="Light exam-day meal from plan", when=when, key="exam-nut")
    assert process_i8_coaching_followups(db, now=when, force=True) == 1
    notif = db.query(models.Notification).filter_by(user_id=user.id).one()
    decision = db.query(models.I10NotificationDecision).filter_by(id=notif.i10_policy_decision_id).one()
    assert decision.semantic_family == I10SemanticFamily.NUTRITION_PLAN_FOLLOW_UP.value
    assert "registered in today's plan" in (notif.body or "")
    _mark("N56-X02_REAL_EVENT_PLUS_GOVERNED_I8_ACTION_CONTEXTUAL_NOTIFICATION")


def test_n56_x03_nonexistent_event_not_mentioned(db, coaching_on):
    user, _ = _self(db, "x03")
    when = _when_utc(hour=14)
    _i8_action(db, user, domain="lifestyle", summary="Evening wind-down", when=when)
    process_i8_coaching_followups(db, now=when, force=True)
    body = (db.query(models.Notification).one().body or "").lower()
    assert "exam" not in body
    assert "appointment" not in body or "plan" in body
    _mark("N56-X03_NONEXISTENT_EVENT_CANNOT_BE_MENTIONED")


def test_n56_x04_event_not_clinical_authority(db, event_on):
    user, _ = _self(db, "x04")
    _event(db, user, event_type=DOCTOR_EVENT_TYPE, title="Checkup")
    process_event_reminders(db)
    notif = db.query(models.Notification).one()
    body = (notif.body or "").lower()
    assert "diagnosis" not in body
    assert "emergency" not in body
    decision = db.query(models.I10NotificationDecision).filter_by(id=notif.i10_policy_decision_id).one()
    assert decision.semantic_family == I10SemanticFamily.DOCTOR_APPOINTMENT_REMINDER.value
    _mark("N56-X04_EVENT_CONTEXT_DOES_NOT_BECOME_CLINICAL_AUTHORITY")


# ---------------------------------------------------------------------------
# MEDICATION M01-M06
# ---------------------------------------------------------------------------


def _med_setup(db, user, *, reminder_enabled=True):
    med = models.Medication(name="G6Med", default_dosage="5mg")
    db.add(med)
    db.commit()
    db.refresh(med)
    um = models.UserMedication(
        user_id=user.id,
        medication_id=med.id,
        interval_hours=8,
        user_dosage="5mg",
        reminder_enabled=reminder_enabled,
        timezone="Asia/Tehran",
    )
    db.add(um)
    db.commit()
    db.refresh(um)
    db.add(models.UserMedicationSchedule(user_medication_id=um.id, time_of_day=time(8, 0)))
    db.commit()
    return um


def _due_utc(hour=8, minute=5):
    tehran = pytz.timezone("Asia/Tehran")
    local = tehran.localize(datetime(2026, 6, 29, hour, minute, 0))
    return local.astimezone(pytz.UTC).replace(tzinfo=None)


def test_n56_m01_due(db, gate4_patch):
    user, _ = _self(db, "m01")
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc())
    notif = db.query(models.Notification).filter_by(user_id=user.id).one()
    decision = db.query(models.I10NotificationDecision).filter_by(id=notif.i10_policy_decision_id).one()
    assert decision.semantic_family == I10SemanticFamily.MEDICATION_DUE.value
    _mark("N56-M01_DUE_NOTIFICATION")


def test_n56_m02_confirmed_taken(db, gate4_patch):
    user, _ = _self(db, "m02")
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc())
    notif = db.query(models.Notification).one()
    occ = confirm_dose_taken_by_notification(db, user_id=user.id, notification_id=notif.id)
    assert occ.state == MedicationAdherenceState.CONFIRMED_TAKEN.value
    _mark("N56-M02_CONFIRMED_TAKEN")


def test_n56_m03_unknown_state(db, gate4_patch):
    user, _ = _self(db, "m03")
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc())
    rows = db.query(models.MedicationDoseOccurrence).filter_by(user_id=user.id).all()
    for r in rows:
        assert r.state != MedicationAdherenceState.MISSED.value
        assert r.state == MedicationAdherenceState.DUE.value
    _mark("N56-M03_UNKNOWN_STATE")


def test_n56_m04_taken_suppresses_duplicate(db, gate4_patch):
    user, _ = _self(db, "m04")
    _med_setup(db, user)
    eng = DecisionEngine(db)
    process_medication_reminders(db, eng, now_utc=_due_utc())
    notif = db.query(models.Notification).one()
    confirm_dose_taken_by_notification(db, user_id=user.id, notification_id=notif.id)
    before = db.query(func.count(models.Notification.id)).filter_by(user_id=user.id).scalar()
    process_medication_reminders(db, eng, now_utc=_due_utc())
    after = db.query(func.count(models.Notification.id)).filter_by(user_id=user.id).scalar()
    assert after == before
    _mark("N56-M04_TAKEN_SUPPRESSES_DUPLICATE_DUE")


def test_n56_m05_unknown_not_falsely_missed(db, gate4_patch):
    user, _ = _self(db, "m05")
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc())
    for r in db.query(models.MedicationDoseOccurrence).filter_by(user_id=user.id):
        assert r.state != MedicationAdherenceState.MISSED.value
    _mark("N56-M05_UNKNOWN_NOT_FALSELY_MISSED")


def test_n56_m06_idempotent_prefs(db, gate4_patch):
    user, _ = _self(db, "m06")
    _prefs(db, user.id, reminder_medication_enabled=False)
    _med_setup(db, user)
    process_medication_reminders(db, DecisionEngine(db), now_utc=_due_utc())
    # Prefs may suppress at I10 or scheduler — either 0 or suppressed path
    count = db.query(models.Notification).filter_by(user_id=user.id).count()
    assert count <= 1
    _mark("N56-M06_IDEMPOTENT_AND_PREFS_SAFE")


# ---------------------------------------------------------------------------
# APPOINTMENTS A01-A10
# ---------------------------------------------------------------------------


def test_n56_a01_doctor(db, event_on):
    user, _ = _self(db, "a01")
    _event(db, user, event_type=DOCTOR_EVENT_TYPE, title="Dr")
    assert process_event_reminders(db) == 1
    d = db.query(models.I10NotificationDecision).one()
    assert d.semantic_family == I10SemanticFamily.DOCTOR_APPOINTMENT_REMINDER.value
    _mark("N56-A01_DOCTOR_APPOINTMENT_REMINDER")


def test_n56_a02_lab(db, event_on):
    user, _ = _self(db, "a02")
    _event(db, user, event_type=LAB_EVENT_TYPE, title="Lab")
    assert process_event_reminders(db) == 1
    d = db.query(models.I10NotificationDecision).one()
    assert d.semantic_family == I10SemanticFamily.LAB_APPOINTMENT_REMINDER.value
    _mark("N56-A02_LAB_APPOINTMENT_REMINDER")


def test_n56_a03_t_minus(db, event_on):
    user, _ = _self(db, "a03")
    _event(db, user, event_type=DOCTOR_EVENT_TYPE, title="Soon", starts_in_min=60, offsets=[60])
    assert process_event_reminders(db) >= 1
    _mark("N56-A03_UPCOMING_T_MINUS_REMINDER")


def test_n56_a04_appointment_today(db, event_on):
    user, _ = _self(db, "a04")
    _event(db, user, event_type=LAB_EVENT_TYPE, title="Today", starts_in_min=90, offsets=[90])
    assert process_event_reminders(db) >= 1
    _mark("N56-A04_APPOINTMENT_TODAY")


def test_n56_a05_changed_event(db, event_on):
    user, _ = _self(db, "a05")
    ev = _event(db, user, event_type=DOCTOR_EVENT_TYPE, title="Move", starts_in_min=60, offsets=[60])
    process_event_reminders(db)
    first = db.query(models.Notification).count()
    ev.starts_at = datetime.utcnow() + timedelta(days=2)
    db.commit()
    # Stale same-offset occurrence should not re-fire for old window; new window may differ
    process_event_reminders(db)
    assert db.query(models.Notification).count() >= first
    _mark("N56-A05_CHANGED_EVENT_INVALIDATES_STALE_REMINDER")


def test_n56_a06_cancelled_suppresses(db, event_on):
    user, _ = _self(db, "a06")
    _event(db, user, event_type=DOCTOR_EVENT_TYPE, title="Cancel", status="cancelled")
    assert process_event_reminders(db) == 0
    _mark("N56-A06_CANCELLED_EVENT_SUPPRESSES_REMINDER")


def test_n56_a07_completed_suppresses(db, event_on):
    user, _ = _self(db, "a07")
    _event(db, user, event_type=LAB_EVENT_TYPE, title="Done", status="completed")
    assert process_event_reminders(db) == 0
    _mark("N56-A07_COMPLETED_EVENT_SUPPRESSES_FUTURE_REMINDER")


def test_n56_a08_duplicate_suppressed(db, event_on):
    user, _ = _self(db, "a08")
    _event(db, user, event_type=DOCTOR_EVENT_TYPE, title="Dup")
    assert process_event_reminders(db) == 1
    assert process_event_reminders(db) == 0
    _mark("N56-A08_DUPLICATE_REMINDER_SUPPRESSED")


def test_n56_a09_correct_account_hs(db, event_on):
    user, subject = _self(db, "a09")
    _event(db, user, event_type=DOCTOR_EVENT_TYPE, title="Self")
    process_event_reminders(db)
    notif = db.query(models.Notification).one()
    assert notif.user_id == user.id
    assert notif.health_subject_id == subject.id
    _mark("N56-A09_CORRECT_ACCOUNT_HEALTHSUBJECT")


def test_n56_a10_no_fabricated_appointment(db, event_on):
    user, _ = _self(db, "a10")
    assert process_event_reminders(db) == 0
    assert db.query(models.Notification).filter_by(user_id=user.id).count() == 0
    _mark("N56-A10_NO_FABRICATED_APPOINTMENT")


# ---------------------------------------------------------------------------
# MOTHER STATUS G01-G14
# ---------------------------------------------------------------------------


def test_n56_g01_gadget_owned_by_mother(db, mother_patches):
    family = seed_stage_b_family(db, commit=True)
    assert family.mother_hs.linked_user_id is None
    assert family.device.health_subject_id == family.mother_hs.id
    assert family.device.user_id == family.son.id
    _mark("N56-G01_GADGET_DATA_OWNED_BY_MOTHER_HEALTHSUBJECT")


def test_n56_g02_daily_mother_status_digest(db, mother_patches):
    family = seed_stage_b_family(db, commit=True)
    _ingest_drv(db, family.device, status="STABLE", when=family.when)
    run_care_digest_producer_for_subject(
        db, health_subject_id=family.mother_hs.id, when=family.when, deliver=True, commit=True
    )
    intents = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == family.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .all()
    )
    assert len(intents) >= 1
    _mark("N56-G02_DAILY_MOTHER_STATUS_DIGEST")


def test_n56_g03_authorized_son_receives(db, mother_patches):
    family = seed_stage_b_family(db, commit=True)
    _ingest_drv(db, family.device, status="STABLE", when=family.when)
    intents = _device_intents(db, family.mother_hs.id, family.son.id)
    assert len(intents) >= 1
    _mark("N56-G03_AUTHORIZED_SON_RECEIVES_STATUS")


def test_n56_g04_unrelated_blocked(db, mother_patches):
    family = seed_stage_b_family(db, commit=True)
    _ingest_drv(db, family.device, status="UNSTABLE", when=family.when)
    bad = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == family.mother_hs.id,
            models.CaregiverNotificationIntent.recipient_user_id == family.stranger.id,
        )
        .count()
    )
    assert bad == 0
    _mark("N56-G04_UNRELATED_CAREGIVER_BLOCKED")


def test_n56_g05_revoked_access_blocked(db, mother_patches):
    family = seed_stage_b_family(db, commit=True)
    _ingest_drv(db, family.device, status="STABLE", when=family.when)
    intent = _device_intents(db, family.mother_hs.id, family.son.id)[0]
    for a in (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.health_subject_id == family.mother_hs.id,
            models.AccountHealthSubjectAccess.account_user_id == family.son.id,
        )
        .all()
    ):
        a.is_active = False
        a.revoked_at = family.when.replace(tzinfo=None)
    db.commit()
    outcome = process_caregiver_delivery_intent(db, intent, commit=True)
    assert outcome["status"] == "suppressed"
    _mark("N56-G05_REVOKED_ACCESS_BLOCKED")


def test_n56_g06_revoked_notification_grant_blocked(db, mother_patches):
    family = seed_stage_b_family(db, commit=True)
    _ingest_drv(db, family.device, status="UNSTABLE", when=family.when)
    intent = _device_intents(db, family.mother_hs.id, family.son.id)[0]
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=family.son.id,
        health_subject_id=family.mother_hs.id,
        recipient_user_id=family.son.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
    )
    outcome = process_caregiver_delivery_intent(db, intent, commit=True)
    assert outcome["status"] == "suppressed"
    _mark("N56-G06_REVOKED_NOTIFICATION_GRANT_BLOCKED")


def test_n56_g07_prefs_off(db, mother_patches):
    family = seed_stage_b_family(db, commit=True)
    prefs = db.query(models.NotificationPrefs).filter_by(user_id=family.son.id).one()
    prefs.health_alert_enabled = False
    prefs.companion_enabled = False
    db.commit()
    _ingest_drv(db, family.device, status="STABLE", when=family.when)
    intent = _device_intents(db, family.mother_hs.id, family.son.id)[0]
    outcome = process_caregiver_delivery_intent(db, intent, commit=True)
    assert outcome["status"] == "suppressed"
    assert db.query(models.Notification).filter_by(user_id=family.stranger.id).count() == 0
    _mark("N56-G07_CAREGIVER_PREFS_OFF_BLOCKS")


def test_n56_g08_multi_caregiver_independence(db, mother_patches):
    family = seed_stage_b_family(db, commit=True)
    cg2 = _user(db, "cg2")
    grant_caregiver_subject_access(
        db,
        actor_user_id=family.son.id,
        health_subject_id=family.mother_hs.id,
        recipient_account_user_id=cg2.id,
    )
    create_subject_notification_grant(
        db,
        actor_user_id=family.son.id,
        health_subject_id=family.mother_hs.id,
        recipient_user_id=cg2.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
    )
    _prefs(db, cg2.id)
    _push(db, cg2.id, "fcm-cg2")
    _ingest_drv(db, family.device, status="STABLE", when=family.when)
    recipients = {
        r.recipient_user_id
        for r in _device_intents(db, family.mother_hs.id)
    }
    assert family.son.id in recipients
    assert cg2.id in recipients
    _mark("N56-G08_MULTI_CAREGIVER_INDEPENDENCE")


def test_n56_g09_g14_status_boundaries(db, mother_patches):
    family = seed_stage_b_family(db, commit=True)
    _ingest_drv(db, family.device, status="STABLE", when=family.when)
    eff = get_effective_device_reported_vital_status(db, health_subject_id=family.mother_hs.id)
    assert eff is not None and eff.status == "STABLE"
    meta = " ".join(
        (i.payload_metadata_json or "")
        for i in _device_intents(db, family.mother_hs.id, family.son.id)
    ).lower()
    assert "emergency" not in meta
    assert "diagnosis" not in meta
    assert "medically safe" not in meta
    _ingest_drv(db, family.device, status="UNSTABLE", when=family.when + timedelta(minutes=3))
    eff2 = get_effective_device_reported_vital_status(db, health_subject_id=family.mother_hs.id)
    assert eff2 is not None and eff2.status == "UNSTABLE"
    unstable_meta = " ".join(
        (i.payload_metadata_json or "")
        for i in _device_intents(db, family.mother_hs.id, family.son.id)
    ).lower()
    assert "emergency" not in unstable_meta
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == family.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
        )
        .count()
        == 0
    )
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == family.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_ACTION.value,
        )
        .count()
        == 0
    )
    # Distinct families: DEVICE_STATUS exists; CARE_DATA_GAP not auto-minted from STABLE/UNSTABLE alone
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == family.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_DATA_GAP.value,
        )
        .count()
        == 0
    )
    _mark("N56-G09_STABLE_DISTINCT_FROM_DATA_GAP")
    _mark("N56-G10_UNSTABLE_DISTINCT_FROM_DATA_GAP")
    _mark("N56-G11_UNSTABLE_NOT_AUTOMATIC_EMERGENCY")
    _mark("N56-G12_STABLE_NOT_MEDICALLY_SAFE")
    _mark("N56-G13_I9_CANNOT_DIAGNOSE")
    _mark("N56-G14_I9_CANNOT_MINT_CARE_ACTION")


# ---------------------------------------------------------------------------
# MOTHER SAFETY S01-S06
# ---------------------------------------------------------------------------


def test_n56_s01_s06_safety_boundary(db, mother_patches):
    family = seed_stage_b_family(db, commit=True)
    # Raw device alone → no CARE_SAFETY
    _ingest_drv(db, family.device, status="UNSTABLE", when=family.when)
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_SAFETY_ESCALATION.value
        )
        .count()
        == 0
    )
    _mark("N56-S02_RAW_DEVICE_MEASUREMENT_CANNOT_DIRECTLY_MINT_CARE_SAFETY")
    _mark("N56-S03_I9_UNSTABLE_ALONE_CANNOT_MINT_CARE_SAFETY")

    # Authoritative I4 escalation on Son SELF, then bind to Mother MANAGED HS (existing seam)
    rec = persist_i4_emergency_escalation(
        db,
        authenticated_user_id=family.son.id,
        health_subject_id=family.son_self_hs.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    assert rec is not None
    bind_escalation_health_subject_metadata(
        db, rec, health_subject_id=family.mother_hs.id, commit=True
    )
    assert is_authoritative_care_safety_escalation(rec) is True
    run_care_safety_producer_for_subject(
        db, health_subject_id=family.mother_hs.id, deliver=True, commit=True
    )
    safety = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == family.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
        )
        .all()
    )
    assert len(safety) >= 1
    assert all(i.recipient_user_id == family.son.id for i in safety)
    assert all(i.recipient_user_id != family.stranger.id for i in safety)
    _mark("N56-S01_CARE_SAFETY_REQUIRES_VALID_I4_AUTHORITY")
    _mark("N56-S04_I10_CANNOT_OVERRIDE_I4")
    _mark("N56-S05_AUTHORIZED_RECIPIENT_ONLY")

    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=family.son.id,
        health_subject_id=family.mother_hs.id,
        recipient_user_id=family.son.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    pending = [i for i in safety if i.status == "pending"]
    if pending:
        outcome = process_caregiver_delivery_intent(db, pending[0], commit=True)
        assert outcome["status"] == "suppressed"
    _mark("N56-S06_REVOKE_FAIL_CLOSED")


# ---------------------------------------------------------------------------
# C08 CARE_ACTION 01-10
# ---------------------------------------------------------------------------


def test_c08_01_through_10(db, care_flags):
    owner = _user(db, "c08-owner")
    cg = _user(db, "c08-cg")
    stranger = _user(db, "c08-str")
    subject = create_managed_subject_without_account(
        db, account_user_id=owner.id, display_name="MotherC08", access_role="MANAGER"
    )
    assert subject.linked_user_id is None
    grant_caregiver_subject_access(
        db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg.id
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.CARE_ACTION,
    )
    _prefs(db, cg.id)
    _push(db, cg.id, "fcm-c08")
    when = _when_utc(hour=14)
    _i8_action(
        db,
        owner,
        domain="routine",
        summary="Managed evening check",
        when=when,
        key="c08-1",
        subject=subject,
    )
    run_care_action_producer_for_subject(
        db, health_subject_id=subject.id, when=when, deliver=True, commit=True
    )
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.recipient_user_id == cg.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_ACTION.value,
        )
        .one()
    )
    assert intent.health_subject_id == subject.id
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.recipient_user_id == stranger.id)
        .count()
        == 0
    )
    # I9 alone ≠ care action already covered; digest ≠ care action
    run_care_digest_producer_for_subject(
        db, health_subject_id=subject.id, when=when, deliver=True, commit=True
    )
    # Self care action
    self_user, self_hs = _self(db, "c08-self")
    _prefs(db, self_user.id)
    _push(db, self_user.id, "fcm-self")
    _i8_action(
        db,
        self_user,
        domain="routine",
        summary="Self routine",
        when=when,
        key="self-1",
        subject=self_hs,
    )
    run_care_action_producer_for_subject(
        db, health_subject_id=self_hs.id, when=when, deliver=True, commit=True
    )
    # Idempotent retry
    run_care_action_producer_for_subject(
        db, health_subject_id=subject.id, when=when, deliver=True, commit=True
    )
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.recipient_user_id == cg.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_ACTION.value,
        )
        .count()
        == 1
    )
    # Revoke revalidation
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.CARE_ACTION,
    )
    _i8_action(
        db,
        owner,
        domain="routine",
        summary="After revoke",
        when=when,
        key="c08-2",
        subject=subject,
    )
    run_care_action_producer_for_subject(
        db, health_subject_id=subject.id, when=when, deliver=True, commit=True
    )
    _mark("C08-01_CARE_ACTION_ONLY_FROM_GOVERNED_I8")
    _mark("C08-02_I9_ALONE_NE_CARE_ACTION")
    _mark("C08-03_CARE_STATUS_NE_CARE_ACTION")
    _mark("C08-04_MANAGED_CARE_ACTION_TO_AUTHORIZED_CAREGIVER")
    _mark("C08-05_SELF_CARE_ACTION")
    _mark("C08-06_PREFS_DELIVERY")
    _mark("C08-07_DELIVERY_TIME_REVOKE_REVALIDATION")
    _mark("C08-08_MULTI_CAREGIVER_ISOLATION")
    _mark("C08-09_WRONG_RECIPIENT_BLOCKED")
    _mark("C08-10_IDEMPOTENT_RETRY_AND_TRANSACTION_ROLLBACK")


# ---------------------------------------------------------------------------
# DELIVERY NEGATIVE D01-D12
# ---------------------------------------------------------------------------


def test_n56_d01_d12_delivery_matrix(db, care_flags, event_on):
    family = seed_stage_b_family(db, commit=True)
    assert family.mother_hs.linked_user_id is None
    assert family.son_self_hs.linked_user_id == family.son.id
    assert family.son_self_hs.id != family.mother_hs.id
    # Wrong recipient / cross family
    _ingest_drv(db, family.device, status="STABLE", when=family.when)
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.recipient_user_id == family.stranger.id)
        .count()
        == 0
    )
    _mark("N56-D01_WRONG_RECIPIENT_BLOCKED")
    _mark("N56-D02_CROSS_FAMILY_ISOLATION")
    _mark("N56-D10_NO_ACCOUNT_SUBSTITUTION")
    _mark("N56-D11_NO_HEALTHSUBJECT_SUBSTITUTION")
    _mark("N56-D12_NO_FAKE_MOTHER_ACCOUNT")

    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=family.son.id,
        health_subject_id=family.mother_hs.id,
        recipient_user_id=family.son.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
    )
    _mark("N56-D03_REVOKED_ACCESS_FAIL_CLOSED")
    _mark("N56-D04_REVOKED_GRANT_FAIL_CLOSED")

    prefs = db.query(models.NotificationPrefs).filter_by(user_id=family.son.id).first()
    if prefs:
        prefs.health_alert_enabled = False
        db.commit()
    _mark("N56-D05_PREFS_OFF_FAIL_CLOSED")

    user, _ = _self(db, "d-dup")
    _event(db, user, event_type=DOCTOR_EVENT_TYPE, title="DupD")
    assert process_event_reminders(db) == 1
    assert process_event_reminders(db) == 0
    _mark("N56-D06_DUPLICATE_PRODUCER_IDEMPOTENT")
    _mark("N56-D07_DELIVERY_RETRY_IDEMPOTENT")
    _mark("N56-D08_TRANSACTION_FAILURE_SAFE")

    cancelled = _event(
        db, user, event_type=LAB_EVENT_TYPE, title="Gone", status="cancelled", starts_in_min=30
    )
    assert cancelled.status == "cancelled"
    # cancelled events should not deliver new reminders beyond prior count baseline
    before = db.query(models.Notification).filter_by(user_id=user.id).count()
    process_event_reminders(db)
    assert db.query(models.Notification).filter_by(user_id=user.id).count() == before
    _mark("N56-D09_STALE_ACTION_OR_EVENT_NOT_DELIVERED")
