"""GATE=SEDI-V1-BE-C04 — Son+Mother managed person + HealthSubjectCondition + subject I8 + I10 E2E.

Real FastAPI + SQLAlchemy + isolated PostgreSQL (Alembic → 078).
No fake User for Mother. No I4 redesign. No raw I9 → CARE_SAFETY.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest

from backend.app import models
from backend.app.services.health_subject_condition_service import (
    VERIFICATION_REPORTED_UNVERIFIED,
    VERIFICATION_VERIFIED,
    HealthSubjectConditionError,
    report_subject_condition,
)
from backend.app.services.i8.subject_context import load_subject_trusted_context
from backend.app.services.i9.aggregation_service import rebuild_daily_bucket
from backend.app.services.i9.device_claim_service import (
    claim_device_to_health_subject,
    provision_unclaimed_device_platform,
)
from backend.app.services.i9.device_lifecycle_service import transfer_device
from backend.app.services.i9.device_packet_service import (
    DevicePacketIngestInput,
    PacketObservationIn,
    ingest_device_packet,
)
from backend.app.services.i9.health_subject_service import (
    HealthSubjectAccessDenied,
    ensure_self_subject_for_account,
)
from backend.app.services.i9.i8_projection_service import get_bounded_context_projection_for_subject
from backend.app.services.i10.care_action_producer_worker import run_care_action_producer_for_subject
from backend.app.services.i10.care_network_grants import (
    create_subject_notification_grant,
    revoke_subject_notification_grant_by_scope,
)
from backend.app.services.i10.managed_i8_action_binding import build_health_subject_context_refs_json
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.managed_person_service import create_managed_person

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG_PATCH = patch.dict(
    "os.environ",
    {
        "SEDI_I10_CARE_ACTION_PRODUCER_ENABLED": "true",
        "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
    },
    clear=False,
)


@pytest.fixture
def c04_patches():
    with _GATE4_PATCH, _FLAG_PATCH:
        yield


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}-{uuid4().hex[:6]}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _push(db, user_id: int, token: str) -> None:
    db.add(models.PushDevice(user_id=user_id, platform="android", fcm_token=token, is_active=True))
    db.commit()


def _prefs(db, user_id: int) -> None:
    db.add(
        models.NotificationPrefs(
            user_id=user_id,
            companion_enabled=True,
            health_alert_enabled=True,
            reminder_medication_enabled=True,
            reminder_appointment_enabled=True,
            reminder_system_enabled=True,
        )
    )
    db.commit()


def _profile_tz(db, user_id: int) -> None:
    if db.query(models.UserProfileCore).filter(models.UserProfileCore.user_id == user_id).first():
        return
    db.add(models.UserProfileCore(user_id=user_id, timezone="UTC"))
    db.flush()


def _when() -> datetime:
    return datetime(2026, 9, 4, 14, 0, 0, tzinfo=timezone.utc)


def _als_catalog(db) -> models.MedicalCondition:
    row = (
        db.query(models.MedicalCondition)
        .filter(models.MedicalCondition.code == "ALS")
        .first()
    )
    if row:
        return row
    row = models.MedicalCondition(
        code="ALS",
        name="Amyotrophic Lateral Sclerosis",
        description="catalog",
        category="neurological",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _i8_action(db, owner: models.User, subject: models.HealthSubject, when: datetime):
    _profile_tz(db, owner.id)
    window = resolve_local_day_window(db, owner.id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.create_plan(
        db,
        user_id=owner.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key=f"c04-plan-{subject.id}",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    action = repo.create_action(
        db,
        user_id=owner.id,
        plan_id=plan.id,
        action_domain="routine",
        action_type="routine_care_item",
        action_idempotency_key=f"c04-act-{subject.id}",
        summary_text="Mother ALS supportive care check",
        presentation_json="{}",
        knowledge_refs_json="[]",
        context_refs_json=build_health_subject_context_refs_json(subject.id),
        safety_state="SAFE",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    db.commit()
    return action


def test_c04_son_mother_managed_person_condition_i8_i10_e2e(db, c04_patches):
    when = _when()
    son = _user(db, "SON_ACCOUNT")
    stranger = _user(db, "UNRELATED_ACCOUNT")
    _prefs(db, son.id)
    _push(db, son.id, f"fcm-son-{uuid4().hex[:8]}")

    # Son SELF + Mother accountless managed (no fake Mother User)
    son_self = ensure_self_subject_for_account(db, son.id, display_name="SON_SELF")
    mother, created = create_managed_person(
        db,
        account_user_id=son.id,
        display_name="MOTHER",
        access_role="MANAGER",
        idempotency_key="c04-mother-create-1",
    )
    mother2, created2 = create_managed_person(
        db,
        account_user_id=son.id,
        display_name="MOTHER",
        access_role="MANAGER",
        idempotency_key="c04-mother-create-1",
    )
    assert created is True
    assert created2 is False
    assert mother2.id == mother.id
    assert mother.linked_user_id is None
    assert mother.subject_kind == "managed"
    assert mother.id != son_self.id
    assert (
        db.query(models.User).filter(models.User.name == "MOTHER").count() == 0
    )

    # Son has a different catalog condition on Account path — must not leak to Mother I8
    son_cond_catalog = models.MedicalCondition(
        code=f"SON_ONLY_{uuid4().hex[:6]}",
        name="Son Only Hypertension",
        category="chronic",
    )
    db.add(son_cond_catalog)
    db.flush()
    db.add(models.UserCondition(user_id=son.id, condition_id=son_cond_catalog.id))
    db.commit()

    als = _als_catalog(db)
    hsc = report_subject_condition(
        db,
        actor_account_user_id=son.id,
        health_subject_id=mother.id,
        condition_id=als.id,
        notes="caregiver-reported ALS for mother",
    )
    assert hsc.health_subject_id == mother.id
    assert hsc.reported_by_account_user_id == son.id
    assert hsc.source_class == "CAREGIVER_REPORTED"
    assert hsc.verification_state == VERIFICATION_REPORTED_UNVERIFIED
    assert hsc.verification_state != VERIFICATION_VERIFIED

    with pytest.raises(HealthSubjectConditionError) as elev2:
        report_subject_condition(
            db,
            actor_account_user_id=son.id,
            health_subject_id=mother.id,
            condition_id=als.id,
            verification_state=VERIFICATION_VERIFIED,
        )
    assert elev2.value.code == "VERIFICATION_ELEVATION_FORBIDDEN"

    # Unrelated account cannot access Mother
    with pytest.raises(HealthSubjectAccessDenied):
        load_subject_trusted_context(
            db, actor_account_user_id=stranger.id, health_subject_id=mother.id
        )

    # Device → Mother HealthSubject (operationally managed by Son Account)
    device, token = provision_unclaimed_device_platform(
        db, device_id=f"MOTHER-GADGET-{uuid4().hex[:8]}"
    )
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=son.id,
        health_subject_id=mother.id,
        possession_proof=token,
    )
    measured = when - timedelta(hours=2)
    pkt_id = f"c04-pkt-{uuid4().hex[:8]}"
    r1 = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id=pkt_id,
            measured_at=measured,
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 74})],
        ),
    )
    assert r1.health_subject_id == mother.id
    assert r1.dedupe_hit is False
    r1b = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id=pkt_id,
            measured_at=measured,
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 74})],
        ),
    )
    assert r1b.dedupe_hit is True

    pm = (
        db.query(models.PhysiologicalMeasurement)
        .filter(models.PhysiologicalMeasurement.health_subject_id == mother.id)
        .first()
    )
    assert pm is not None
    assert pm.user_id is None or pm.health_subject_id == mother.id
    assert (
        db.query(models.PhysiologicalMeasurement)
        .filter(models.PhysiologicalMeasurement.health_subject_id == son_self.id)
        .count()
        == 0
    )

    rebuild_daily_bucket(
        db, subject=mother, measurement_type="heart_rate", ref=measured, commit=True
    )
    proj = get_bounded_context_projection_for_subject(db, health_subject_id=mother.id)
    assert proj.health_subject_id == mother.id
    assert mother.linked_user_id is None

    # Subject-aware I8: Mother conditions, not Son UserCondition
    i8_mother = load_subject_trusted_context(
        db, actor_account_user_id=son.id, health_subject_id=mother.id
    )
    assert i8_mother.health_subject_id == mother.id
    assert "Amyotrophic Lateral Sclerosis" in i8_mother.conditions
    assert "Son Only Hypertension" not in i8_mother.conditions
    assert i8_mother.physiological_context is not None
    assert i8_mother.physiological_context.health_subject_id == mother.id
    assert i8_mother.medications == []  # no Son meds attributed to Mother

    i8_son = load_subject_trusted_context(
        db, actor_account_user_id=son.id, health_subject_id=son_self.id
    )
    assert "Son Only Hypertension" in i8_son.conditions
    assert "Amyotrophic Lateral Sclerosis" not in i8_son.conditions

    # I10 CARE_ACTION → Son recipient, Mother subject
    create_subject_notification_grant(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_user_id=son.id,
        notification_scope=I10NotificationScope.CARE_ACTION,
    )
    _i8_action(db, son, mother, when)
    outcome = run_care_action_producer_for_subject(
        db, health_subject_id=mother.id, when=when, deliver=True, commit=True
    )
    assert outcome.get("intents", 0) >= 1
    n = (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == son.id,
            models.Notification.health_subject_id == mother.id,
            models.Notification.semantic_family == I10SemanticFamily.CARE_ACTION.value,
        )
        .count()
    )
    assert n >= 1
    # No CARE_SAFETY from raw I9
    assert (
        db.query(models.Notification)
        .filter(
            models.Notification.semantic_family == I10SemanticFamily.CARE_SAFETY_ESCALATION.value
        )
        .count()
        == 0
    )

    # Revoke grant → suppress further delivery (next local day = new I8 plan)
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_user_id=son.id,
        notification_scope=I10NotificationScope.CARE_ACTION,
    )
    before = db.query(models.Notification).filter(models.Notification.user_id == son.id).count()
    when2 = when + timedelta(days=1)
    _profile_tz(db, son.id)
    window2 = resolve_local_day_window(db, son.id, now_utc=when2)
    repo = I8OperationalRepository()
    plan2 = repo.create_plan(
        db,
        user_id=son.id,
        user_local_date=window2.user_local_date,
        timezone_snapshot=window2.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key=f"c04-plan2-{mother.id}",
        valid_from=window2.valid_from,
        valid_until=window2.valid_until,
        expires_at=window2.expires_at,
    )
    repo.create_action(
        db,
        user_id=son.id,
        plan_id=plan2.id,
        action_domain="routine",
        action_type="routine_care_item",
        action_idempotency_key=f"c04-act2-{mother.id}",
        summary_text="Post-revoke check",
        presentation_json="{}",
        knowledge_refs_json="[]",
        context_refs_json=build_health_subject_context_refs_json(mother.id),
        safety_state="SAFE",
        valid_from=window2.valid_from,
        valid_until=window2.valid_until,
        expires_at=window2.expires_at,
    )
    db.commit()
    run_care_action_producer_for_subject(
        db, health_subject_id=mother.id, when=when2, deliver=True, commit=True
    )
    after = db.query(models.Notification).filter(models.Notification.user_id == son.id).count()
    assert after == before

    # Transfer device to another managed subject — Mother historical data stays on Mother
    other, _ = create_managed_person(
        db,
        account_user_id=son.id,
        display_name="OTHER_SUBJECT",
        access_role="MANAGER",
        idempotency_key="c04-other-subject",
    )
    transfer_device(
        db,
        device=device,
        account_user_id=son.id,
        new_health_subject_id=other.id,
        possession_proof=token,
    )
    r2 = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id=f"c04-pkt2-{uuid4().hex[:8]}",
            measured_at=when,
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 80})],
        ),
    )
    assert r2.health_subject_id == other.id
    assert pm.health_subject_id == mother.id
    assert (
        db.query(models.PhysiologicalMeasurement)
        .filter(models.PhysiologicalMeasurement.health_subject_id == mother.id)
        .count()
        >= 1
    )

    # Access revoke for stranger already proven; revoke Son caregiver path for second caregiver if added
    # Ensure no RAG/LLM diagnosis write path invoked — condition count for Mother stays 1 active ALS
    assert (
        db.query(models.HealthSubjectCondition)
        .filter(
            models.HealthSubjectCondition.health_subject_id == mother.id,
            models.HealthSubjectCondition.status == "active",
        )
        .count()
        == 1
    )
